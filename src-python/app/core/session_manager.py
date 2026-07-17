from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class ManagedSession:
    session_id: str
    task_id: str
    target: str
    transport: str
    owner: str
    challenge: str
    created_at: datetime
    expires_at: datetime
    last_heartbeat: datetime
    identity: str = ""
    privilege: str = "unknown"
    closed: bool = False


@dataclass(frozen=True)
class SessionVerification:
    valid: bool
    session_id: str
    reason: str
    identity: str = ""


class SessionManager:
    def __init__(self, *, default_ttl_seconds: int = 900):
        self.default_ttl_seconds = max(30, min(default_ttl_seconds, 86400))
        self._sessions: dict[str, ManagedSession] = {}

    def create(self, *, task_id: str, target: str, transport: str, owner: str, ttl_seconds: int | None = None) -> ManagedSession:
        now = datetime.now(timezone.utc)
        ttl = max(30, min(ttl_seconds or self.default_ttl_seconds, 86400))
        session = ManagedSession(
            session_id=f"session_{secrets.token_urlsafe(12)}",
            task_id=task_id,
            target=target,
            transport=transport,
            owner=owner,
            challenge=f"SDIT_CHALLENGE_{secrets.token_urlsafe(18)}",
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            last_heartbeat=now,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> ManagedSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.closed or session.expires_at <= datetime.now(timezone.utc):
            session.closed = True
            return None
        return session

    def verify(self, session_id: str, *, task_id: str, target: str, output: str, identity: str) -> SessionVerification:
        session = self.get(session_id)
        if session is None:
            return SessionVerification(False, session_id, "session missing, closed or expired")
        if session.task_id != task_id or session.target.strip().lower() != target.strip().lower():
            return SessionVerification(False, session_id, "task or target binding mismatch")
        if session.challenge not in output:
            return SessionVerification(False, session_id, "challenge was not echoed")
        if not identity.strip():
            return SessionVerification(False, session_id, "identity proof is empty")
        session.identity = identity.strip()[:160]
        session.last_heartbeat = datetime.now(timezone.utc)
        return SessionVerification(True, session_id, "session verified", session.identity)

    def heartbeat(self, session_id: str, *, output: str = "") -> bool:
        session = self.get(session_id)
        if session is None or session.challenge not in output:
            return False
        session.last_heartbeat = datetime.now(timezone.utc)
        return True

    def close(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.closed = True
        return True

    def close_task(self, task_id: str) -> int:
        count = 0
        for session in self._sessions.values():
            if session.task_id == task_id and not session.closed:
                session.closed = True
                count += 1
        return count

