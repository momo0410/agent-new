from app.services.pentest_agent.agent import _auto_exploit_simple_vulns
from app.services.pentest_agent.state import State


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def run(self, tool, args):
        self.calls.append((tool, args))
        if "psql" in args:
            return {"stdout": "PostgreSQL 8.3.1 on i486-pc-linux-gnu\n(1 row)", "stderr": "", "returncode": 0}
        if "1524" in args:
            return {"stdout": "uid=0(root) gid=0(root)\nroot\n", "stderr": "", "returncode": 0}
        return {"stdout": "", "stderr": "", "returncode": 1, "error": "failed"}


def test_p13_direct_records_shell_and_credentials(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("192.168.136.137")
    state.add_finding({"ip": "192.168.136.137", "port": 1524, "service": "bindshell root shell"})
    state.add_finding({"ip": "192.168.136.137", "port": 5432, "service": "postgresql  PostgreSQL DB 8.3.0 - 8.3.7"})
    state.add_vulnerability({"name": "bindshell root shell", "severity": "critical", "target": "192.168.136.137", "ports": [1524]})
    state.add_vulnerability({"name": "postgres default credential", "severity": "high", "target": "192.168.136.137", "ports": [5432]})
    executor = FakeExecutor()

    assert _auto_exploit_simple_vulns(state, executor, round_num=1) is True

    assert any(a.get("host_compromise") for a in state.data["attack_surfaces"] if 1524 in a.get("ports", []))
    assert any(c.get("username") == "postgres" for c in state.data["credentials"])
