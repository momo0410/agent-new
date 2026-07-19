from __future__ import annotations

import asyncio

from app.core.secret_store import SecretStore
from app.routers import api


class _ConnectionManager:
    @staticmethod
    def decrypt_password(_encrypted: str) -> str:
        return "SENSITIVE_VALUE"


class _SshManager:
    def __init__(self) -> None:
        self.password = None

    async def connect(self, **kwargs):
        self.password = kwargs.get("password")
        return "connected"


def test_decrypt_endpoint_returns_only_opaque_reference(monkeypatch):
    monkeypatch.setattr(api, "get_connection_manager", lambda: _ConnectionManager())
    response = asyncio.run(api.decrypt_password(api.DecryptPasswordRequest(encrypted_password="ciphertext")))
    assert "decrypted" not in response
    assert response["secret_ref"].startswith("secret_")
    assert "SENSITIVE_VALUE" not in str(response)


def test_connect_resolves_secret_reference_inside_backend(monkeypatch):
    manager = _SshManager()
    monkeypatch.setattr(api, "get_ssh_manager", lambda: manager)
    secret = api._ssh_secret_store.put("SENSITIVE_VALUE", kind="ssh-password", ttl_seconds=60)
    request = api.ConnectWithAuthRequest(
        host="TARGET",
        username="user",
        auth_type="password",
        secret_ref=secret.ref,
    )
    response = asyncio.run(api.ssh_connect_with_auth(request))
    assert response["message"] == "connected"
    assert manager.password == "SENSITIVE_VALUE"


def test_model_secret_endpoint_returns_opaque_runtime_reference(monkeypatch):
    store = SecretStore(service="fixture-model", persistent=False)
    monkeypatch.setattr(api, "_model_secret_store", store)
    response = asyncio.run(
        api.store_model_secret(
            api.ModelSecretRequest(api_key="MODEL_SECRET", provider="fixture")
        )
    )
    assert response["secret_ref"].startswith("secret_")
    assert "MODEL_SECRET" not in str(response)
    assert api._resolve_model_api_key(response["secret_ref"]) == "MODEL_SECRET"
