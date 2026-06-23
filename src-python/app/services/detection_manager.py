import re
from typing import Any, Dict, List, Optional
from app.models.types import (
    BackdoorScanResult,
    CpuTestResult,
    DiskTestResult,
    FilePermissionResult,
    FirewallCheckResult,
    GenericDetectionResult,
    LogAnalysisResult,
    MemoryTestResult,
    NetworkTestResult,
    PortScanResult,
    ProcessAnalysisResult,
    SSHAuditResult,
    UserAuditResult,
)
from app.services.ssh_manager import SSHManager
def _extract_port_from_netstat(line: str) -> Optional[int]:
    matches = re.findall(r':(\d+)', line)
    if matches:
        return int(matches[-1])
    return None
def _identify_service(port: int) -> str:
    services = {
        20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp",
        53: "dns", 80: "http", 110: "pop3", 143: "imap", 443: "https",
        465: "smtps", 587: "submission", 993: "imaps", 995: "pop3s",
        1433: "mssql", 1521: "oracle", 3306: "mysql", 3389: "rdp",
        5432: "postgresql", 5900: "vnc", 6379: "redis", 8080: "http-proxy",
        8443: "https-alt", 9200: "elasticsearch", 27017: "mongodb",
    }
    return services.get(port, "unknown")
async def detect_port_scan(manager: SSHManager) -> PortScanResult:
    cmd = "(netstat -tlnp 2>/dev/null | grep LISTEN || ss -tlnp 2>/dev/null | grep LISTEN) || true"
    output = await manager.execute_command(cmd)
    open_ports = []
    for line in output.output.split("\n"):
        if "LISTEN" in line:
            port = _extract_port_from_netstat(line)
            if port:
                service = _identify_service(port)
                open_ports.append({"port": port, "service": service, "state": "LISTEN"})
    seen = set()
    unique_ports = []
    for p in open_ports:
        if p["port"] not in seen:
            seen.add(p["port"])
            unique_ports.append(p)
    unique_ports.sort(key=lambda x: x["port"])
    return PortScanResult(open_ports=unique_ports, total_open=len(unique_ports))
async def detect_user_audit(manager: SSHManager) -> UserAuditResult:
    passwd_output = await manager.execute_command("cat /etc/passwd")
    root_users = []
    recent_users = []
    for line in passwd_output.output.split("\n"):
        parts = line.split(":")
        if len(parts) >= 7:
            username = parts[0]
            uid = int(parts[2]) if parts[2].isdigit() else 9999
            gid = int(parts[3]) if parts[3].isdigit() else 9999
            home = parts[5]
            shell = parts[6]
            user_info = {"username": username, "uid": uid, "gid": gid, "shell": shell, "home": home}
            if uid == 0:
                root_users.append(user_info)
            if 1000 <= uid < 60000:
                recent_users.append(user_info)
    shadow_cmd = "sudo cat /etc/shadow 2>/dev/null | grep -E '^[^:]+::' | cut -d: -f1"
    shadow_output = await manager.execute_command(shadow_cmd)
    empty_password_users = [l.strip() for l in shadow_output.output.split("\n") if l.strip()]
    return UserAuditResult(
        users=root_users + recent_users[:5],
        risk_users=root_users,
        risk_level="high" if len(root_users) > 1 else "low",
        details=f"发现 {len(root_users)} 个root用户, {len(empty_password_users)} 个空密码用户",
    )
async def detect_backdoor(manager: SSHManager) -> BackdoorScanResult:
    cron_cmd = (
        "(crontab -l 2>/dev/null; sudo crontab -l 2>/dev/null; cat /etc/crontab 2>/dev/null) | "
        "grep -v '^#' | grep -v '^$' | grep -E '(curl|wget|nc|bash|sh|python)'"
    )
    cron_output = await manager.execute_command(cron_cmd)
    suspicious_cron = [l.strip() for l in cron_output.output.split("\n") if l.strip()]
    autostart_cmd = "find /etc/init.d /etc/systemd/system /etc/rc*.d -type f 2>/dev/null | head -20"
    autostart_output = await manager.execute_command(autostart_cmd)
    suspicious_autostart = [l.strip() for l in autostart_output.output.split("\n") if l.strip()][:10]
    ssh_keys_cmd = (
        "find /home /root -name authorized_keys 2>/dev/null | "
        "xargs cat 2>/dev/null | grep -v '^#' | grep -v '^$' | head -5"
    )
    keys_output = await manager.execute_command(ssh_keys_cmd)
    suspicious_ssh_keys = [l.strip()[:60] + "..." for l in keys_output.output.split("\n") if l.strip()]
    return BackdoorScanResult(
        suspicious_files=[{"path": x} for x in (suspicious_cron + suspicious_autostart)],
        risk_level="high" if suspicious_cron else "low",
        details=f"发现 {len(suspicious_cron)} 个可疑cron任务, {len(suspicious_autostart)} 个启动项",
    )
async def detect_process_analysis(manager: SSHManager) -> ProcessAnalysisResult:
    cmd = "ps aux --sort=-%cpu | head -50"
    output = await manager.execute_command(cmd)
    suspicious_processes = []
    high_resource_processes = []
    for line in output.output.split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            proc = {
                "user": parts[0], "pid": int(parts[1]) if parts[1].isdigit() else 0,
                "cpu": float(parts[2]) if parts[2] else 0,
                "mem": float(parts[3]) if parts[3] else 0,
                "command": parts[10],
            }
            if proc["cpu"] > 50 or proc["mem"] > 50:
                high_resource_processes.append(proc)
            suspicious_keywords = ["nc", "ncat", "socat", "cryptominer", "xmrig"]
            if any(kw in proc["command"].lower() for kw in suspicious_keywords):
                suspicious_processes.append(proc)
    return ProcessAnalysisResult(
        processes=high_resource_processes + suspicious_processes,
        suspicious_processes=suspicious_processes,
        risk_level="high" if suspicious_processes else "low",
        details=f"发现 {len(suspicious_processes)} 个可疑进程, {len(high_resource_processes)} 个高资源进程",
    )
async def detect_file_permission(manager: SSHManager) -> FilePermissionResult:
    suid_cmd = "find / -perm -4000 -type f 2>/dev/null | head -30"
    suid_output = await manager.execute_command(suid_cmd)
    suid_files = [l.strip() for l in suid_output.output.split("\n") if l.strip()]
    sensitive_cmd = (
        "ls -la /etc/shadow /etc/passwd /etc/ssh/sshd_config 2>/dev/null | "
        "grep -E '(world|other)'"
    )
    sensitive_output = await manager.execute_command(sensitive_cmd)
    sensitive_issues = [l.strip() for l in sensitive_output.output.split("\n") if l.strip()]
    return FilePermissionResult(
        risky_files=[{"path": x} for x in (suid_files + sensitive_issues)],
        risk_level="medium" if len(suid_files) > 20 else "low",
        details=f"发现 {len(suid_files)} 个SUID文件, {len(sensitive_issues)} 个权限问题",
    )
async def detect_ssh_audit(manager: SSHManager) -> SSHAuditResult:
    cmd = "cat /etc/ssh/sshd_config 2>/dev/null"
    output = await manager.execute_command(cmd)
    config = output.output.lower()
    permit_root_login = "permitrootlogin yes" in config or "permitrootlogin without-password" not in config and "permitrootlogin no" not in config
    password_auth = "passwordauthentication yes" in config or "passwordauthentication" not in config
    default_port = "port 22" in config or "port " not in config
    issues = []
    if permit_root_login:
        issues.append("允许root登录")
    if password_auth:
        issues.append("允许密码认证")
    if default_port:
        issues.append("使用默认SSH端口(22)")
    return SSHAuditResult(
        config_issues=[{"issue": i} for i in issues],
        risk_level="high" if len(issues) >= 2 else "medium" if issues else "low",
        details=", ".join(issues) if issues else "SSH配置安全",
    )
async def detect_log_analysis(manager: SSHManager) -> LogAnalysisResult:
    cmd = (
        "grep -i 'failed\\|error\\|invalid' /var/log/auth.log 2>/dev/null | tail -20 || "
        "journalctl -u sshd --since '1 hour ago' 2>/dev/null | grep -i 'failed' | tail -20"
    )
    output = await manager.execute_command(cmd)
    entries = [l.strip() for l in output.output.split("\n") if l.strip()]
    brute_force_count = len([e for e in entries if "failed" in e.lower()])
    return LogAnalysisResult(
        entries=[{"line": e} for e in entries],
        risk_level="high" if brute_force_count > 10 else "medium" if brute_force_count > 3 else "low",
        details=f"发现 {brute_force_count} 次失败登录尝试",
    )
async def detect_firewall_check(manager: SSHManager) -> FirewallCheckResult:
    iptables_cmd = "sudo iptables -L -n 2>/dev/null | head -20"
    iptables_output = await manager.execute_command(iptables_cmd)
    ufw_cmd = "sudo ufw status 2>/dev/null"
    ufw_output = await manager.execute_command(ufw_cmd)
    firewalld_cmd = "sudo firewall-cmd --state 2>/dev/null"
    firewalld_output = await manager.execute_command(firewalld_cmd)
    firewall_active = (
        "active" in ufw_output.output.lower()
        or "running" in firewalld_output.output.lower()
        or len(iptables_output.output.strip()) > 50
    )
    rules = [l.strip() for l in iptables_output.output.split("\n") if l.strip()][:10]
    return FirewallCheckResult(
        status="active" if firewall_active else "inactive",
        rules=[{"rule": r} for r in rules],
        risk_level="high" if not firewall_active else "low",
        details="防火墙已启用" if firewall_active else "防火墙未启用",
    )
async def detect_cpu_test(manager: SSHManager) -> CpuTestResult:
    cmd = "lscpu | grep -E '^(CPU\\(s\\)|Model name|CPU MHz)' && echo '---' && top -bn1 | head -5"
    output = await manager.execute_command(cmd)
    return CpuTestResult(cpu_info=output.output, cpu_usage=0.0, details=output.output)
async def detect_memory_test(manager: SSHManager) -> MemoryTestResult:
    cmd = "free -h"
    output = await manager.execute_command(cmd)
    lines = output.output.strip().split("\n")
    total = used = free = "N/A"
    usage_percent = 0.0
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 4:
            total, used, free = parts[1], parts[2], parts[3]
    return MemoryTestResult(total=total, used=used, free=free, usage_percent=usage_percent, details=output.output)
async def detect_disk_test(manager: SSHManager) -> DiskTestResult:
    cmd = "df -h"
    output = await manager.execute_command(cmd)
    disks = []
    for line in output.output.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 6:
            disks.append({"filesystem": parts[0], "size": parts[1], "used": parts[2], "avail": parts[3], "use%": parts[4], "mount": parts[5]})
    return DiskTestResult(disks=disks, details=output.output)
async def detect_network_test(manager: SSHManager) -> NetworkTestResult:
    cmd = "ip addr show 2>/dev/null || ifconfig 2>/dev/null"
    output = await manager.execute_command(cmd)
    return NetworkTestResult(interfaces=[{"info": output.output}], connections=[], details=output.output)
async def _generic_detection(
    manager: SSHManager,
    title: str,
    cmd: str,
    items_are_issues: bool = True,
) -> GenericDetectionResult:
    output = await manager.execute_command(cmd)
    items = [l.strip() for l in output.output.split("\n") if l.strip()]
    if items_are_issues:
        risk_level = "high" if len(items) > 5 else "medium" if items else "low"
        status = "fail" if items else "pass"
        details = f"发现 {len(items)} 个问题"
    else:
        status = "pass" if items else "fail"
        risk_level = "low" if items else "medium"
        details = f"已获取 {len(items)} 条配置信息" if items else "未获取到有效配置"
    return GenericDetectionResult(
        title=title, status=status, items=[{"line": i} for i in items],
        risk_level=risk_level, details=details,
    )
async def detect_password_policy(manager: SSHManager) -> GenericDetectionResult:
    cmd = "grep -v '^#' /etc/login.defs 2>/dev/null | grep -E '(PASS_MAX_DAYS|PASS_MIN_DAYS|PASS_MIN_LEN|PASS_WARN_AGE)'"
    return await _generic_detection(manager, "密码策略检查", cmd)
async def detect_sudo_config(manager: SSHManager) -> GenericDetectionResult:
    cmd = "sudo -l 2>/dev/null | grep -E '(NOPASSWD|ALL)'"
    return await _generic_detection(manager, "Sudo 配置审计", cmd)
async def detect_pam_config(manager: SSHManager) -> GenericDetectionResult:
    cmd = "grep -v '^#' /etc/pam.d/common-auth /etc/pam.d/sshd 2>/dev/null | grep -v '^$'"
    return await _generic_detection(manager, "PAM 配置检查", cmd, items_are_issues=False)
async def detect_account_lockout(manager: SSHManager) -> GenericDetectionResult:
    cmd = "grep -v '^#' /etc/pam.d/common-auth 2>/dev/null | grep -i 'pam_faillock\\|pam_tally'"
    output = await manager.execute_command(cmd)
    items = [l.strip() for l in output.output.split("\n") if l.strip()]
    return GenericDetectionResult(
        title="账号锁定策略检查", status="pass" if items else "fail",
        items=[{"line": i} for i in items] if items else [{"line": "未配置账号锁定策略"}],
        risk_level="low" if items else "high", details="已配置" if items else "未配置账号锁定策略",
    )
async def detect_selinux_status(manager: SSHManager) -> GenericDetectionResult:
    cmd = "getenforce 2>/dev/null || echo 'Not installed'"
    output = await manager.execute_command(cmd)
    status_val = output.output.strip().lower()
    return GenericDetectionResult(
        title="SELinux/AppArmor 状态检查",
        status="pass" if "enforcing" in status_val else "fail",
        items=[{"status": status_val}],
        risk_level="low" if "enforcing" in status_val else "medium",
        details=f"SELinux状态: {status_val}",
    )
async def detect_kernel_params(manager: SSHManager) -> GenericDetectionResult:
    cmd = "sysctl -a 2>/dev/null | grep -E '(net.ipv4.ip_forward|net.ipv4.conf.all.rp_filter|kernel.exec-shield)' | head -10"
    return await _generic_detection(manager, "内核参数检查", cmd, items_are_issues=False)
async def detect_system_updates(manager: SSHManager) -> GenericDetectionResult:
    cmd = "apt list --upgradable 2>/dev/null | head -20 || yum check-update 2>/dev/null | head -20"
    return await _generic_detection(manager, "系统补丁状态检查", cmd)
async def detect_unnecessary_services(manager: SSHManager) -> GenericDetectionResult:
    cmd = "systemctl list-units --type=service --state=running 2>/dev/null | head -30"
    return await _generic_detection(manager, "不必要服务检查", cmd, items_are_issues=False)
async def detect_auto_start_services(manager: SSHManager) -> GenericDetectionResult:
    cmd = "systemctl list-unit-files --state=enabled 2>/dev/null | head -30"
    return await _generic_detection(manager, "自启动服务审计", cmd, items_are_issues=False)
async def detect_audit_config(manager: SSHManager) -> GenericDetectionResult:
    cmd = "systemctl is-active auditd 2>/dev/null && auditctl -l 2>/dev/null | head -10 || echo 'auditd not running'"
    return await _generic_detection(manager, "审计配置检查", cmd)
async def detect_history_audit(manager: SSHManager) -> GenericDetectionResult:
    cmd = "cat ~/.bash_history 2>/dev/null | tail -20"
    return await _generic_detection(manager, "历史命令审计", cmd)
async def detect_ntp_config(manager: SSHManager) -> GenericDetectionResult:
    cmd = "timedatectl 2>/dev/null || ntpq -p 2>/dev/null | head -5"
    return await _generic_detection(manager, "NTP 配置检查", cmd, items_are_issues=False)
async def detect_dns_config(manager: SSHManager) -> GenericDetectionResult:
    cmd = "cat /etc/resolv.conf 2>/dev/null"
    return await _generic_detection(manager, "DNS 配置检查", cmd)