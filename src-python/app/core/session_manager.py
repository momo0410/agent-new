from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
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
    target_id: str = ""
    scope_id: str = ""
    command_outputs: list[str] = field(default_factory=list)
    command_fingerprints: list[str] = field(default_factory=list)
    identity_confirmed: bool = False
    heartbeat_count: int = 0
    last_command_at: datetime | None = None
    closed: bool = False

@dataclass(frozen=True)
class SessionVerification:
    valid: bool
    session_id: str
    reason: str
    identity: str = ""
    evidence: dict[str, object] | None = None


class SessionManager:
    def __init__(self, *, default_ttl_seconds: int = 900):
        self.default_ttl_seconds = max(30, min(default_ttl_seconds, 86400))
        self._sessions: dict[str, ManagedSession] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        task_id: str,
        target: str,
        transport: str,
        owner: str,
        ttl_seconds: int | None = None,
        target_id: str = "",
        scope_id: str = "",
    ) -> ManagedSession:
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
            target_id=target_id,
            scope_id=scope_id,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> ManagedSession | None:
        with self._lock:
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
        session.identity_confirmed = True
        session.last_heartbeat = datetime.now(timezone.utc)
        return SessionVerification(True, session_id, "session verified", session.identity)

    def record_command(self, session_id: str, *, command: str, output: str, marker: str = "") -> SessionVerification:
        """Record one command/output pair without treating it as a session proof."""
        session = self.get(session_id)
        if session is None:
            return SessionVerification(False, session_id, "session missing, closed or expired")
        normalized_command = " ".join(str(command).split())[:500]
        fingerprint = secrets.token_hex(16) if not normalized_command else __import__("hashlib").sha256(normalized_command.encode()).hexdigest()
        if fingerprint not in session.command_fingerprints:
            session.command_fingerprints.append(fingerprint)
        text = str(output)[:4000]
        if marker and marker not in text:
            return SessionVerification(False, session_id, "random command marker was not echoed")
        session.command_outputs.append(text)
        session.last_command_at = datetime.now(timezone.utc)
        return SessionVerification(True, session_id, "command output recorded", session.identity)

    def verify_strict(
        self,
        session_id: str,
        *,
        task_id: str,
        target: str,
        outputs: list[str],
        identity: str,
        heartbeat_output: str,
        marker: str | None = None,
        scope_id: str | None = None,
    ) -> SessionVerification:
        """Apply the full PRD session gate in one deterministic operation."""
        session = self.get(session_id)
        if session is None:
            return SessionVerification(False, session_id, "session missing, closed or expired")
        target_ok = session.task_id == task_id and session.target.strip().lower().rstrip(".") == target.strip().lower().rstrip(".")
        if scope_id and session.scope_id and scope_id != session.scope_id:
            target_ok = False
        marker_value = marker or session.challenge
        clean_outputs = [str(item) for item in outputs if str(item)]
        marker_ok = bool(marker_value and any(marker_value in item for item in clean_outputs))
        distinct = len(clean_outputs) >= 2 and clean_outputs[0] != clean_outputs[1]
        identity_ok = bool(str(identity).strip())
        heartbeat_ok = bool(session.challenge in str(heartbeat_output) or marker_value in str(heartbeat_output))
        if not (target_ok and marker_ok and distinct and identity_ok and heartbeat_ok):
            return SessionVerification(
                False,
                session_id,
                "strict session proof incomplete",
                str(identity).strip()[:160],
                {
                    "target_bound": target_ok,
                    "marker_echoed": marker_ok,
                    "distinct_commands": distinct,
                    "identity_confirmed": identity_ok,
                    "heartbeat": heartbeat_ok,
                },
            )
        session.command_outputs = clean_outputs[:8]
        session.identity = str(identity).strip()[:160]
        session.identity_confirmed = True
        session.heartbeat_count += 1
        session.last_heartbeat = datetime.now(timezone.utc)
        return SessionVerification(
            True,
            session_id,
            "strict session verified",
            session.identity,
            {"target_bound": True, "marker_echoed": True, "distinct_commands": True, "identity_confirmed": True, "heartbeat": True},
        )

    def heartbeat(self, session_id: str, *, output: str = "") -> bool:
        session = self.get(session_id)
        if session is None or session.challenge not in output:
            return False
        session.last_heartbeat = datetime.now(timezone.utc)
        session.heartbeat_count += 1
        return True

    def close(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.closed = True
        return True

    def snapshot(self, session_id: str) -> dict[str, object] | None:
        session = self.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session.session_id,
            "task_id": session.task_id,
            "target": session.target,
            "transport": session.transport,
            "owner": session.owner,
            "scope_id": session.scope_id,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "last_heartbeat": session.last_heartbeat.isoformat(),
            "identity": session.identity,
            "identity_confirmed": session.identity_confirmed,
            "heartbeat_count": session.heartbeat_count,
            "command_count": len(session.command_outputs),
            "closed": session.closed,
        }

    def close_task(self, task_id: str) -> int:
        count = 0
        for session in self._sessions.values():
            if session.task_id == task_id and not session.closed:
                session.closed = True
                count += 1
        return count
