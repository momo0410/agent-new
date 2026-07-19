"""Opaque secret references with an OS-keyring adapter and memory fallback."""
from __future__ import annotations

import hashlib
import secrets
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecretRef:
    ref: str
    kind: str
    fingerprint: str
    expires_at: float | None = None


class SecretStore:
    def __init__(self, *, service: str = "sdit", persistent: bool = True):
        self.service = service
        self._memory: dict[str, tuple[str, float | None]] = {}
        self._refs: dict[str, tuple[str, float | None]] = {}
        self._keyring = None
        if persistent:
            try:
                import keyring  # type: ignore
                self._keyring = keyring
            except Exception:
                self._keyring = None

    def put(
        self,
        value: str,
        *,
        kind: str = "secret",
        name: str | None = None,
        ttl_seconds: float | None = None,
    ) -> SecretRef:
        ref = f"secret_{secrets.token_urlsafe(18)}"
        fingerprint = hashlib.sha256(str(value).encode()).hexdigest()[:16]
        key = name or ref
        expires_at = time.time() + max(1.0, float(ttl_seconds)) if ttl_seconds is not None else None
        self._refs[ref] = (key, expires_at)
        if self._keyring is not None:
            try:
                self._keyring.set_password(self.service, key, str(value))
            except Exception:
                self._memory[ref] = (str(value), expires_at)
        else:
            self._memory[ref] = (str(value), expires_at)
        return SecretRef(ref, kind, fingerprint, expires_at)

    def resolve(self, ref: str, *, consume: bool = False) -> str | None:
        self.purge_expired()
        if ref in self._memory:
            value = self._memory[ref][0]
            if consume:
                self._memory.pop(ref, None)
                self._refs.pop(ref, None)
            return value
        if self._keyring is None:
            return None
        try:
            key = self._refs.get(ref, (ref, None))[0]
            value = self._keyring.get_password(self.service, key)
            if consume:
                self._keyring.delete_password(self.service, key)
                self._refs.pop(ref, None)
            return value
        except Exception:
            return None

    def delete(self, ref: str) -> None:
        self._memory.pop(ref, None)
        key = self._refs.pop(ref, (ref, None))[0]
        if self._keyring is not None:
            with suppress(Exception):
                self._keyring.delete_password(self.service, key)

    def purge_expired(self) -> int:
        now = time.time()
        expired = [
            ref
            for ref, (_key, expiry) in self._refs.items()
            if expiry is not None and expiry <= now
        ]
        for ref in expired:
            self._memory.pop(ref, None)
            self.delete(ref)
        return len(expired)

    def redact(self, value: Any) -> str:
        text = str(value)
        self.purge_expired()
        for ref, (secret, _expiry) in self._memory.items():
            if secret:
                text = text.replace(secret, f"[SECRET:{ref}]")
        return text
