import re
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.models.types import FileAnalysisResult
from app.services.ssh_manager import SSHManager
async def sftp_file_analysis(manager: SSHManager, path: str, action: Optional[str] = None) -> Dict[str, Any]:
    if not manager.is_connected():
        raise ConnectionError("没有活动的 SSH 连接")
    if action:
        return await _execute_independent_analysis(manager, path, action)
    return await _execute_full_analysis(manager, path)
async def sftp_file_analysis_independent(manager: SSHManager, path: str, action: Optional[str] = None) -> Dict[str, Any]:
    return await sftp_file_analysis(manager, path, action)
async def _execute_full_analysis(manager: SSHManager, path: str) -> Dict[str, Any]:
    stat_cmd = f'stat -c "%F|%s|%a|%U|%G|%W|%Y|%X" "{path}" 2>/dev/null'
    stat_output = await manager.execute_command(stat_cmd)
    file_type = "unknown"
    size = 0
    permissions = ""
    owner = ""
    group = ""
    created = ""
    modified = ""
    accessed = ""
    if stat_output.exit_code == 0:
        parts = stat_output.output.strip().split("|")
        if len(parts) >= 8:
            file_type = parts[0]
            try:
                size = int(parts[1])
            except ValueError:
                pass
            permissions = parts[2]
            owner = parts[3]
            group = parts[4]
            for i, key in [(5, "created"), (6, "modified"), (7, "accessed")]:
                try:
                    ts = int(parts[i])
                    if ts > 0:
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                        if key == "created":
                            created = dt
                        elif key == "modified":
                            modified = dt
                        else:
                            accessed = dt
                except (ValueError, IndexError):
                    pass
    hash_cmd = f'md5sum "{path}" 2>/dev/null && sha1sum "{path}" 2>/dev/null && sha256sum "{path}" 2>/dev/null'
    hash_output = await manager.execute_command(hash_cmd)
    hash_md5 = None
    hash_sha1 = None
    hash_sha256 = None
    hash_lines = hash_output.output.strip().split("\n")
    if len(hash_lines) >= 1 and hash_lines[0].strip():
        hash_md5 = hash_lines[0].split()[0] if hash_lines[0].split() else None
    if len(hash_lines) >= 2 and hash_lines[1].strip():
        hash_sha1 = hash_lines[1].split()[0] if hash_lines[1].split() else None
    if len(hash_lines) >= 3 and hash_lines[2].strip():
        hash_sha256 = hash_lines[2].split()[0] if hash_lines[2].split() else None
    is_suid = False
    is_sgid = False
    is_world_writable = False
    is_hidden = path.split("/")[-1].startswith(".")
    if permissions:
        try:
            perm_int = int(permissions, 8)
            is_suid = bool(perm_int & 0o4000)
            is_sgid = bool(perm_int & 0o2000)
            is_world_writable = bool(perm_int & 0o0002)
        except ValueError:
            pass
    risk_indicators = []
    if is_suid:
        risk_indicators.append("SUID位已设置")
    if is_sgid:
        risk_indicators.append("SGID位已设置")
    if is_world_writable:
        risk_indicators.append("全局可写")
    if is_hidden:
        risk_indicators.append("隐藏文件")
    risk_level = "low"
    if size < 1024 * 1024:
        content_cmd = f'head -c 1048576 "{path}" 2>/dev/null'
        content_output = await manager.execute_command(content_cmd)
        content = content_output.output
        suspicious_patterns = [
            (r'eval\s*\(', "使用eval()"),
            (r'exec\s*\(', "使用exec()"),
            (r'system\s*\(', "使用system()"),
            (r'os\.system', "使用os.system"),
            (r'subprocess', "使用subprocess"),
            (r'rm\s+-rf', "危险rm命令"),
            (r'chmod\s+777', "危险chmod"),
            (r'/etc/passwd', "访问passwd文件"),
            (r'/etc/shadow', "访问shadow文件"),
        ]
        for pattern, desc in suspicious_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                risk_indicators.append(desc)
    if len(risk_indicators) >= 3:
        risk_level = "high"
    elif risk_indicators:
        risk_level = "medium"
    return FileAnalysisResult(
        path=path,
        file_type=file_type,
        size=size,
        permissions=permissions,
        owner=owner,
        group=group,
        hash_md5=hash_md5,
        hash_sha1=hash_sha1,
        hash_sha256=hash_sha256,
        modified=modified,
        created=created,
        accessed=accessed,
        is_suid=is_suid,
        is_sgid=is_sgid,
        is_world_writable=is_world_writable,
        is_hidden=is_hidden,
        risk_indicators=risk_indicators,
        risk_level=risk_level,
        details=f"发现 {len(risk_indicators)} 个风险指标" if risk_indicators else "未发现风险",
    ).model_dump()
async def _execute_independent_analysis(manager: SSHManager, path: str, action: str) -> Dict[str, Any]:
    commands = {
        'hash': f'md5sum "{path}" 2>/dev/null && sha1sum "{path}" 2>/dev/null && sha256sum "{path}" 2>/dev/null',
        'signature': f'file -b "{path}"',
        'permissions': f'ls -lh "{path}" && stat -c \'%A %a %U:%G\' "{path}"',
        'timestamps': f'stat "{path}"',
        'inode': f'stat -c \'Inode: %i\\nLinks: %h\\nDevice: %d\\nSize: %s bytes\' "{path}"',
        'mime-type': f'file -b --mime-type "{path}"',
        'file-size': f'du -h "{path}" && ls -lh "{path}"',
        'strings': f'strings -n 8 "{path}" 2>/dev/null | head -100',
        'hex-dump': f'xxd "{path}" 2>/dev/null | head -50',
        'line-count': f'wc -l "{path}"',
        'archive-list': f'tar -tzf "{path}" 2>/dev/null || unzip -l "{path}" 2>/dev/null',
        'elf-header': f'readelf -h "{path}" 2>/dev/null',
        'processes': f'lsof "{path}" 2>/dev/null || fuser -v "{path}" 2>/dev/null',
        'package-owner': f'dpkg -S "{path}" 2>/dev/null || rpm -qf "{path}" 2>/dev/null',
        'hard-links': f'find / -samefile "{path}" 2>/dev/null',
        'process-maps': f'grep "{path}" /proc/*/maps 2>/dev/null',
        'xattr': f'getfattr -d "{path}" 2>/dev/null || xattr -l "{path}" 2>/dev/null',
        'capabilities': f'getcap "{path}" 2>/dev/null',
        'selinux-context': f'ls -Z "{path}" 2>/dev/null',
        'dynamic-deps': f'ldd "{path}" 2>/dev/null',
        'config-references': f'grep -r "{path}" /etc/ 2>/dev/null | head -20',
        'symlink-analysis': f'ls -l "{path}" && readlink -f "{path}" 2>/dev/null',
    }
    suspicious_actions = {'suspicious-path', 'hidden-file', 'suid-sgid'}
    if action in suspicious_actions:
        return await _execute_suspicious_analysis(manager, path, action)
    cmd = commands.get(action)
    if not cmd:
        raise ValueError(f"未知的分析动作: {action}")
    result = await manager.execute_command(cmd)
    return {
        "action": action,
        "file_path": path,
        "result": result.output if result.exit_code == 0 else (result.output if result.output.strip() else "未检测到相关信息（可能需要 root 权限或该文件无此属性）"),
        "exit_code": result.exit_code,
        "timestamp": datetime.now(tz=timezone.utc).isoformat()
    }


async def _execute_suspicious_analysis(manager: SSHManager, path: str, action: str) -> Dict[str, Any]:
    now = datetime.now(tz=timezone.utc).isoformat()
    base = {"action": action, "file_path": path, "exit_code": 0, "timestamp": now}

    if action == "suspicious-path":
        suspicious_patterns = {
            "/tmp/": "临时目录",
            "/dev/shm/": "共享内存目录",
            "/var/tmp/": "持久临时目录",
            "..": "路径穿越",
        }
        found = []
        for pattern, desc in suspicious_patterns.items():
            if pattern in path:
                found.append(f"  匹配: {pattern} → {desc}")
        if found:
            base["result"] = f"检测到可疑路径特征:\n文件路径: {path}\n\n匹配项:\n" + "\n".join(found) + "\n\n建议: 该文件位于常见攻击者利用的目录中，请确认是否为合法文件。"
        else:
            base["result"] = f"路径安全\n文件路径: {path}\n\n未检测到可疑路径特征（/tmp/、/dev/shm/、/var/tmp/、路径穿越）。"
        return base

    if action == "hidden-file":
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        if filename.startswith("."):
            base["result"] = f"检测到隐藏文件\n文件名: {filename}\n文件路径: {path}\n\n该文件以点号(.)开头，属于隐藏文件。\n\n常见隐藏文件:\n  .bash_history  - Shell 历史记录\n  .ssh/          - SSH 配置目录\n  .env           - 环境变量\n  .git/          - Git 仓库\n\n建议: 确认该隐藏文件是否为系统正常配置文件。"
        else:
            base["result"] = f"非隐藏文件\n文件名: {filename}\n文件路径: {path}\n\n该文件不以点号开头，不属于隐藏文件。"
        return base

    if action == "suid-sgid":
        stat_cmd = f'stat -c "%a %F" "{path}" 2>/dev/null'
        stat_result = await manager.execute_command(stat_cmd)
        if stat_result.exit_code != 0 or not stat_result.output.strip():
            find_cmd = f'find "{path}" -perm /6000 -ls 2>/dev/null'
            find_result = await manager.execute_command(find_cmd)
            if find_result.exit_code == 0 and find_result.output.strip():
                base["result"] = f"检测到 SUID/SGID\n文件路径: {path}\n\n详细信息:\n{find_result.output}\n\nSUID/SGID 文件允许用户以文件所有者身份执行，可能被用于提权攻击。\n建议: 确认该权限设置是否必要。"
            else:
                base["result"] = f"未检测到 SUID/SGID\n文件路径: {path}\n\n该文件未设置 SUID 或 SGID 位，或需要 root 权限才能检测。"
            return base

        parts = stat_result.output.strip().split()
        perm_str = parts[0] if len(parts) > 0 else ""
        file_type = parts[1] if len(parts) > 1 else ""
        try:
            perm_int = int(perm_str, 8)
            is_suid = bool(perm_int & 0o4000)
            is_sgid = bool(perm_int & 0o2000)
        except ValueError:
            is_suid = False
            is_sgid = False

        lines = [f"文件路径: {path}", f"权限: {perm_str}  类型: {file_type}", ""]
        if is_suid:
            lines.append("SUID 位已设置 — 该文件以所有者身份执行，可能被用于提权！")
        if is_sgid:
            lines.append("SGID 位已设置 — 该文件以所属组身份执行，可能被用于提权！")
        if not is_suid and not is_sgid:
            lines.append("未设置 SUID 或 SGID 位。")
        else:
            lines.append("")
            lines.append("建议: 确认 SUID/SGID 设置是否必要，常见合法 SUID 文件: passwd, sudo, ping")
        base["result"] = "\n".join(lines)
        return base

    base["result"] = "未知检测类型"
    return base