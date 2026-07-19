"""Modern Web attack-surface model independent of any scanner brand."""
from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _url_key(url: str) -> str:
    parts = urlsplit(str(url).strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", "", ""))


@dataclass(frozen=True)
class WebParameter:
    name: str
    location: str
    required: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()


@dataclass
class WebEndpoint:
    endpoint_id: str
    url: str
    method: str = "GET"
    parameters: list[WebParameter] = field(default_factory=list)
    auth_required: bool | None = None
    roles_seen: set[str] = field(default_factory=set)
    source_refs: list[str] = field(default_factory=list)
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    response_hashes: list[str] = field(default_factory=list)
    dangerous: bool = False

    @classmethod
    def create(cls, url: str, *, method: str = "GET", source: str = "") -> WebEndpoint:
        normalized = _url_key(url)
        endpoint_id = "endpoint_" + hashlib.sha256(f"{method.upper()} {normalized}".encode()).hexdigest()[:20]
        return cls(endpoint_id, normalized, method.upper(), source_refs=[source] if source else [])

    def observe_response(self, body: str, *, status_code: int, role: str = "anonymous") -> str:
        digest = hashlib.sha256(str(body).encode("utf-8", errors="replace")).hexdigest()
        if digest not in self.response_hashes:
            self.response_hashes.append(digest)
        self.roles_seen.add(role)
        if self.auth_required is None:
            self.auth_required = status_code in {401, 403}
        return digest


@dataclass
class WebSite:
    site_id: str
    origin: str
    virtual_hosts: set[str] = field(default_factory=set)
    endpoints: dict[str, WebEndpoint] = field(default_factory=dict)
    static_assets: set[str] = field(default_factory=set)
    api_schemas: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_endpoint(self, endpoint: WebEndpoint) -> WebEndpoint:
        existing = self.endpoints.get(endpoint.endpoint_id)
        if existing is None:
            self.endpoints[endpoint.endpoint_id] = endpoint
            return endpoint
        existing.source_refs = sorted(set(existing.source_refs + endpoint.source_refs))
        existing.parameters.extend(item for item in endpoint.parameters if item not in existing.parameters)
        existing.roles_seen.update(endpoint.roles_seen)
        existing.dangerous = existing.dangerous or endpoint.dangerous
        return existing


@dataclass(frozen=True)
class WebRole:
    role_id: str
    label: str
    credential_ref: str = ""


@dataclass
class AuthSession:
    session_id: str
    role_id: str
    cookies: dict[str, str] = field(default_factory=dict)
    csrf_token_ref: str = ""
    expires_at: datetime | None = None
    valid: bool = True

    def is_valid(self) -> bool:
        return self.valid and (self.expires_at is None or self.expires_at > datetime.now(timezone.utc))

    def set_cookie(self, name: str, value: str) -> None:
        if name and self.is_valid():
            self.cookies[str(name).strip()] = str(value)

    def apply_set_cookie_headers(self, headers: dict[str, str] | Iterable[str]) -> None:
        values = headers.values() if isinstance(headers, dict) else headers
        for header in values:
            first = str(header).split(";", 1)[0]
            if "=" not in first:
                continue
            name, value = first.split("=", 1)
            self.set_cookie(name.strip(), value.strip())

    def request_headers(self) -> dict[str, str]:
        if not self.is_valid():
            return {}
        headers = {"Cookie": "; ".join(f"{name}={value}" for name, value in sorted(self.cookies.items()))}
        if self.csrf_token_ref:
            headers["X-CSRF-Token-Ref"] = self.csrf_token_ref
        return headers


class WebSessionStore:
    """Ephemeral role/session state; values are kept in memory only."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, AuthSession] = {}

    def put(self, session: AuthSession) -> AuthSession:
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AuthSession | None:
        with self._lock:
            session = self._sessions.get(str(session_id))
            return session if session and session.is_valid() else None

    def invalidate(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(str(session_id))
            if not session:
                return False
            session.valid = False
            return True

    def redacted(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "session_id": session.session_id,
                    "role_id": session.role_id,
                    "cookie_names": sorted(session.cookies),
                    "csrf_bound": bool(session.csrf_token_ref),
                    "valid": session.is_valid(),
                }
                for session in self._sessions.values()
            ]


@dataclass(frozen=True)
class WebRequestObservation:
    request_id: str
    endpoint_id: str
    role_id: str
    status_code: int
    body_hash: str
    headers: dict[str, str] = field(default_factory=dict)
    source_ref: str = ""


@dataclass(frozen=True)
class WebRule:
    rule_id: str
    category: str
    version: str
    required_observations: tuple[str, ...]
    dangerous: bool = False


@dataclass(frozen=True)
class WebCrawlerPolicy:
    allowed_origins: tuple[str, ...]
    max_depth: int = 3
    max_requests_per_second: float = 2.0
    max_content_bytes: int = 2_000_000
    follow_redirects: bool = True
    allow_dangerous_methods: bool = False
    allow_dangerous_links: bool = False
    user_agent: str = "SDIT-WebRuntime/1"

    def permits(self, url: str, *, depth: int, method: str = "GET", content_length: int = 0) -> tuple[bool, str]:
        origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}".lower().rstrip("/")
        allowed = {item.lower().rstrip("/") for item in self.allowed_origins}
        if origin not in allowed:
            return False, "origin outside web scope"
        if depth > self.max_depth:
            return False, "crawl depth exceeded"
        if content_length > self.max_content_bytes:
            return False, "content size exceeded"
        if method.upper() in {"DELETE", "PURGE", "TRACE"} and not self.allow_dangerous_methods:
            return False, "dangerous HTTP method is disabled"
        if self.is_dangerous_url(url) and not self.allow_dangerous_links:
            return False, "dangerous link is disabled"
        return True, "allowed"

    @staticmethod
    def is_dangerous_url(url: str) -> bool:
        text = str(url).lower()
        return bool(re.search(r"(?:logout|logoff|delete|remove|destroy|purge|shutdown|reset|drop)(?:[/?#=&]|$)", text))


@dataclass(frozen=True)
class WebRuleFinding:
    rule_id: str
    category: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...] = ()


class WebRuleEngine:
    """Small deterministic rule catalog for non-shell Web outcomes."""

    DEFAULT_RULES = (
        WebRule("web.input-validation.v1", "input_validation", "1", ("reflected_input",)),
        WebRule("web.authentication.v1", "authentication", "1", ("auth_transition",)),
        WebRule("web.authorization.v1", "authorization", "1", ("role_difference",)),
        WebRule("web.server-request.v1", "server_side_request", "1", ("server_request_observed",)),
        WebRule("web.template.v1", "template", "1", ("template_marker",)),
        WebRule("web.file-processing.v1", "file_processing", "1", ("file_processing_observed",)),
        WebRule("web.sensitive-info.v1", "sensitive_information", "1", ("secret_marker",)),
        WebRule("web.error-config.v1", "error_configuration", "1", ("verbose_error",)),
    )

    def __init__(self, rules: Iterable[WebRule] | None = None) -> None:
        self.rules = tuple(rules or self.DEFAULT_RULES)

    def evaluate(self, observation: dict[str, Any]) -> list[WebRuleFinding]:
        facts = {str(key).lower(): value for key, value in observation.items()}
        findings: list[WebRuleFinding] = []
        for rule in self.rules:
            matched = [fact for fact in rule.required_observations if facts.get(fact)]
            if not matched:
                continue
            status = str(facts.get(f"{rule.category}_status", "POTENTIALLY_VULNERABLE")).upper()
            findings.append(WebRuleFinding(
                rule.rule_id,
                rule.category,
                status,
                str(facts.get(f"{rule.category}_reason", f"observed {', '.join(matched)}"))[:500],
                tuple(str(item) for item in facts.get("evidence_refs", ()) if str(item)),
            ))
        return findings


def body_hash(body: str | bytes) -> str:
    value = body if isinstance(body, bytes) else str(body).encode("utf-8", errors="replace")
    return hashlib.sha256(value).hexdigest()
