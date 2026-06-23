from fastapi.testclient import TestClient
from app.main import app
def test_detection_endpoints_return_400_without_ssh_connection() -> None:
    endpoints = [
        "/api/v1/detect/port-scan",
        "/api/v1/detect/user-audit",
        "/api/v1/detect/backdoor",
        "/api/v1/detect/process-analysis",
        "/api/v1/detect/file-permission",
        "/api/v1/detect/ssh-audit",
        "/api/v1/detect/log-analysis",
        "/api/v1/detect/firewall-check",
        "/api/v1/detect/password-policy",
        "/api/v1/detect/sudo-config",
        "/api/v1/detect/pam-config",
        "/api/v1/detect/account-lockout",
        "/api/v1/detect/selinux-status",
        "/api/v1/detect/kernel-params",
        "/api/v1/detect/system-updates",
        "/api/v1/detect/unnecessary-services",
        "/api/v1/detect/auto-start-services",
        "/api/v1/detect/audit-config",
        "/api/v1/detect/history-audit",
        "/api/v1/detect/ntp-config",
        "/api/v1/detect/dns-config",
        "/api/v1/detect/cpu-test",
        "/api/v1/detect/memory-test",
        "/api/v1/detect/disk-test",
        "/api/v1/detect/network-test",
    ]
    with TestClient(app, raise_server_exceptions=False) as client:
        for endpoint in endpoints:
            response = client.post(endpoint)
            assert response.status_code == 400, (
                f"{endpoint} returned {response.status_code}: {response.text}"
            )
            payload = response.json()
            assert isinstance(payload, dict)
            assert payload.get("detail")