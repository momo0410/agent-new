from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone


class LocalSessionAuth:
    """Process-bound short-lived token used by the local desktop bridge."""

    def __init__(self, *, ttl_seconds: int = 3600):
        self.token = os.getenv("SDIT_LOCAL_SESSION_TOKEN", "").strip() or secrets.token_urlsafe(32)
        self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(300, min(ttl_seconds, 86400)))
        self.allowed_origins = {
            item.strip().rstrip("/")
            for item in os.getenv(
                "SDIT_ALLOWED_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:1420,http://127.0.0.1:1420,tauri://localhost",
            ).split(",")
            if item.strip()
        }

    def is_valid(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(str(token), self.token) and self.expires_at > datetime.now(timezone.utc)

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return True
        return origin.rstrip("/") in self.allowed_origins

