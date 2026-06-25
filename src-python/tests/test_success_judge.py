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
