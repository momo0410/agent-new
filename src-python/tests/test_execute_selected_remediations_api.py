from __future__ import annotations
from typing import Any, Dict, List
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.routers import api as api_router
class FakeSSHManager:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.calls: List[Dict[str, Any]] = []
    def is_connected(self) -> bool:
        return self._connected
    async def execute_command(self, command: str):
        self.calls.append({"command": command})
        return {"exit_code": 0, "output": "ok", "command": command}
class FakeSSHManagerDisconnected:
    def is_connected(self) -> bool:
        return False
    async def execute_command(self, command: str):
        raise ConnectionError("No active SSH connection")
def test_dry_run_no_ssh_connection_required(monkeypatch) -> None:
    fake_ssh = FakeSSHManagerDisconnected()
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: fake_ssh)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "dry run remediation",
            "dry_run": True,
            "selected_findings": [
                {
                    "finding_id": "f-1",
                    "title": "Patch sshd_config",
                    "commands": ["sed -i 's/no/yes/' /etc/ssh/sshd_config"],
                    "verify_commands": ["grep PermitRootLogin /etc/ssh/sshd_config"],
                    "rollback_commands": [
                        "cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config"
                    ],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "dry_run"
    assert payload["approval_tickets"]
    assert payload["results"][0]["execution_status"] == "dry_run"
    assert payload["results"][0]["approval_ticket"] is not None
def test_rollback_preview_no_ssh_connection_required(monkeypatch) -> None:
    fake_ssh = FakeSSHManagerDisconnected()
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: fake_ssh)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "rollback preview",
            "rollback_mode": "preview",
            "selected_findings": [
                {
                    "finding_id": "f-4",
                    "title": "Rollback ssh config",
                    "commands": ["sed -i 's/yes/no/' /etc/ssh/sshd_config"],
                    "verify_commands": [],
                    "rollback_commands": [
                        "cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config"
                    ],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "rollback_preview"
    assert payload["results"][0]["execution_status"] == "rollback_preview"
    assert payload["results"][0]["rollback_preview"]["supported"] is True
def test_dry_run_with_uninitialized_ssh_manager_no_500(monkeypatch) -> None:
    def _raise_uninitialized():
        raise HTTPException(status_code=500, detail="SSH manager is unavailable")
    monkeypatch.setattr(api_router, "get_ssh_manager", _raise_uninitialized)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "dry run without manager",
            "dry_run": True,
            "selected_findings": [
                {
                    "finding_id": "f-6",
                    "title": "No manager dry run",
                    "commands": ["echo dry-run"],
                    "verify_commands": ["echo verify"],
                    "rollback_commands": [],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "dry_run"
    assert payload["results"][0]["execution_status"] == "dry_run"
def test_rollback_preview_with_none_ssh_manager_no_500(monkeypatch) -> None:
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: None)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "rollback preview no ssh manager",
            "rollback_mode": "preview",
            "selected_findings": [
                {
                    "finding_id": "f-7",
                    "title": "Preview without manager",
                    "commands": ["echo mutate"],
                    "verify_commands": [],
                    "rollback_commands": ["echo rollback"],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "rollback_preview"
    assert payload["results"][0]["execution_status"] == "rollback_preview"
def test_no_ssh_connection_returns_error_not_500(monkeypatch) -> None:
    fake_ssh = FakeSSHManagerDisconnected()
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: fake_ssh)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "real execution",
            "dry_run": False,
            "selected_findings": [
                {
                    "finding_id": "f-5",
                    "title": "Fix firewall",
                    "commands": ["systemctl start firewalld"],
                    "verify_commands": [],
                    "rollback_commands": [],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert "error" in payload
    assert "SSH" in payload["error"]
def test_approval_required_before_mutation(monkeypatch) -> None:
    fake_ssh = FakeSSHManager()
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: fake_ssh)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "approval gate",
            "selected_findings": [
                {
                    "finding_id": "f-2",
                    "title": "Restart nginx",
                    "commands": ["systemctl restart nginx"],
                    "verify_commands": ["systemctl status nginx"],
                    "rollback_commands": ["systemctl restart nginx"],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "pending_approval"
    assert payload["results"][0]["execution_status"] == "pending_approval"
    assert payload["results"][0]["approval_ticket"] is not None
    assert fake_ssh.calls == []
def test_budget_guard_blocks_execution(monkeypatch) -> None:
    fake_ssh = FakeSSHManager()
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: fake_ssh)
    client = TestClient(app)
    response = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "budget guard",
            "approved_finding_ids": ["f-3"],
            "budget": {
                "max_steps": 1,
                "max_mutation_steps": 1,
                "max_ssh_commands": 1,
                "max_http_requests": 0,
            },
            "selected_findings": [
                {
                    "finding_id": "f-3",
                    "title": "Patch and verify",
                    "commands": ["sed -i 's/a/b/' /tmp/demo"],
                    "verify_commands": ["cat /tmp/demo"],
                    "rollback_commands": [],
                }
            ],
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "blocked"
    assert payload["results"][0]["execution_status"] == "blocked"
    assert "Budget exceeded" in (payload["results"][0]["error"] or "")
def test_regression_no_get_default_connection_id(monkeypatch) -> None:
    class RealisticFake:
        def __init__(self):
            self._connected = True
        def is_connected(self) -> bool:
            return self._connected
        async def execute_command(self, command: str):
            return {"exit_code": 0, "output": "ok", "command": command}
    fake = RealisticFake()
    assert not hasattr(fake, "get_default_connection_id")
    monkeypatch.setattr(api_router, "get_ssh_manager", lambda: fake)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/execute-selected-remediations",
        json={
            "task": "regression test",
            "dry_run": True,
            "selected_findings": [
                {
                    "finding_id": "reg-1",
                    "title": "Test",
                    "commands": ["echo hi"],
                    "verify_commands": [],
                    "rollback_commands": [],
                }
            ],
        },
    )
    client.close()
    assert resp.status_code == 200
    assert resp.json()["overall_status"] == "dry_run"