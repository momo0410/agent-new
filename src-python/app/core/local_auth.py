from __future__ import annotations

import os
import secrets
import threading
import time
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
        self.allowed_hosts = {
            item.strip().lower()
            for item in os.getenv("SDIT_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")
            if item.strip()
        }
        self.max_request_bytes = int(os.getenv("SDIT_MAX_REQUEST_BYTES", "4194304"))
        self.requests_per_minute = int(os.getenv("SDIT_REQUESTS_PER_MINUTE", "600"))
        self._request_times: dict[str, list[float]] = {}
        self._ws_tickets: dict[str, datetime] = {}
        self._lock = threading.RLock()
        self._revoked = False

    def is_valid(self, token: str | None) -> bool:
        return (
            not self._revoked
            and bool(token)
            and secrets.compare_digest(str(token), self.token)
            and self.expires_at > datetime.now(timezone.utc)
        )

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return False
        return origin.rstrip("/") in self.allowed_origins

    def host_allowed(self, host: str | None) -> bool:
        value = str(host or "").split(":", 1)[0].strip("[]").lower()
        return value in self.allowed_hosts

    def rate_allowed(self, client_key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._request_times.get(client_key, []) if now - stamp < 60.0]
            if len(recent) >= self.requests_per_minute:
                self._request_times[client_key] = recent
                return False
            recent.append(now)
            self._request_times[client_key] = recent
            return True

    def issue_ws_ticket(self, token: str | None, *, ttl_seconds: int = 30) -> str | None:
        if not self.is_valid(token):
            return None
        ticket = secrets.token_urlsafe(24)
        with self._lock:
            self._ws_tickets[ticket] = datetime.now(timezone.utc) + timedelta(seconds=max(5, min(ttl_seconds, 120)))
        return ticket

    def consume_ws_ticket(self, ticket: str | None) -> bool:
        if not ticket:
            return False
        with self._lock:
            expiry = self._ws_tickets.pop(str(ticket), None)
        return bool(expiry and expiry > datetime.now(timezone.utc))

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True
            self._ws_tickets.clear()

    def rotate(self, *, ttl_seconds: int = 3600) -> str:
        with self._lock:
            self.token = secrets.token_urlsafe(32)
            self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(300, min(ttl_seconds, 86400)))
            self._revoked = False
            self._ws_tickets.clear()
            return self.token
