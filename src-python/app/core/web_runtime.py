"""Small transport-neutral Web runtime for scoped crawling and role checks."""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit
from uuid import uuid4

from .judges import JudgeRegistry, JudgeResult
from .web_model import (
    AuthSession,
    WebCrawlerPolicy,
    WebEndpoint,
    WebParameter,
    WebSessionStore,
    WebSite,
    body_hash,
)


@dataclass(frozen=True)
class WebFetch:
    url: str
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    request_id: str = ""
    facts: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WebObservation:
    url: str
    depth: int
    status_code: int
    body_hash: str
    role: str
    endpoint_id: str
    links: tuple[str, ...] = ()
    blocked_reason: str = ""
    facts: dict[str, object] = field(default_factory=dict)


@dataclass
class WebCrawlResult:
    sites: dict[str, WebSite] = field(default_factory=dict)
    observations: list[WebObservation] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)
    request_count: int = 0
    rate_delays: int = 0


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.methods: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in {"a", "link", "script", "img", "form"}:
            return
        attr_map = {str(key).lower(): value for key, value in attrs}
        method = str(attr_map.get("method") or "GET").upper()
        for key, value in attrs:
            if key.lower() in {"href", "src", "action"} and value:
                self.links.append(value)
                self.methods[value] = method if tag.lower() == "form" else "GET"


class ScopedWebCrawler:
    """Run a deterministic crawl against an injected transport."""

    def __init__(
        self,
        policy: WebCrawlerPolicy,
        fetch: Callable[[str, str], WebFetch],
        *,
        session_store: WebSessionStore | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self.fetch = fetch
        self.session_store = session_store or WebSessionStore()
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    def crawl(
        self,
        seeds: list[str],
        *,
        role: str = "anonymous",
        session: AuthSession | None = None,
    ) -> WebCrawlResult:
        result = WebCrawlResult()
        queue: deque[tuple[str, int]] = deque((str(seed), 0) for seed in seeds if str(seed).strip())
        seen: set[str] = set()
        if session is not None:
            self.session_store.put(session)
        while queue:
            url, depth = queue.popleft()
            normalized = self._normalize_url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            allowed, reason = self.policy.permits(normalized, depth=depth, method="GET")
            if not allowed:
                result.blocked.append({"url": normalized, "reason": reason})
                continue
            result.rate_delays += self._pace()
            response = self.fetch(normalized, "GET")
            result.request_count += 1
            if session is not None:
                session.apply_set_cookie_headers({
                    key: value for key, value in response.headers.items() if key.lower() == "set-cookie"
                })
            if len(response.body.encode("utf-8", errors="replace")) > self.policy.max_content_bytes:
                result.blocked.append({"url": normalized, "reason": "content size exceeded"})
                continue
            endpoint = WebEndpoint.create(normalized, source=response.request_id)
            for name, value in parse_qsl(urlsplit(normalized).query, keep_blank_values=True):
                endpoint.parameters.append(
                    WebParameter(name=name, location="query", schema={"example": value})
                )
            endpoint.observe_response(response.body, status_code=response.status_code, role=role)
            site = self._site_for(normalized, result.sites)
            site.add_endpoint(endpoint)
            parser = _LinkParser()
            try:
                parser.feed(response.body)
            except Exception:
                parser.links = []
            links: list[str] = []
            for link in parser.links:
                candidate = self._normalize_url(urljoin(normalized, link))
                if candidate and candidate not in links:
                    links.append(candidate)
                    method = parser.methods.get(link, "GET")
                    candidate_allowed, candidate_reason = self.policy.permits(
                        candidate,
                        depth=depth + 1,
                        method=method,
                    )
                    if not candidate_allowed:
                        result.blocked.append({"url": candidate, "reason": candidate_reason})
                        continue
                    if depth < self.policy.max_depth:
                        queue.append((candidate, depth + 1))
                    if self._is_static_asset(candidate):
                        site.static_assets.add(candidate)
            redirect = self._header(response.headers, "location")
            if redirect and self.policy.follow_redirects:
                redirect_url = self._normalize_url(urljoin(normalized, redirect))
                redirect_allowed, redirect_reason = self.policy.permits(
                    redirect_url,
                    depth=depth + 1,
                    method="GET",
                )
                if redirect_allowed:
                    queue.append((redirect_url, depth + 1))
                else:
                    result.blocked.append({"url": redirect_url, "reason": redirect_reason})
            result.observations.append(
                WebObservation(
                    url=normalized,
                    depth=depth,
                    status_code=response.status_code,
                    body_hash=body_hash(response.body),
                    role=role,
                    endpoint_id=endpoint.endpoint_id,
                    links=tuple(links),
                    facts=self._observation_facts(normalized, response, parser, role),
                )
            )
        return result

    @staticmethod
    def _observation_facts(
        url: str,
        response: WebFetch,
        parser: _LinkParser,
        role: str,
    ) -> dict[str, object]:
        """Derive bounded, explainable rule facts from a response.

        Fixture transports may provide explicit facts; inferred facts only add
        high-signal markers and never turn a response into a confirmed finding.
        """
        facts: dict[str, object] = dict(response.facts or {})
        body = str(response.body or "")
        query_values = [value for _, value in parse_qsl(urlsplit(url).query, keep_blank_values=True) if value]
        if any(value in body for value in query_values):
            facts.setdefault("reflected_input", True)
        lowered = body.lower()
        if re.search(r"(?:api[_-]?key|secret|password|authorization\s*[:=])", lowered):
            facts.setdefault("secret_marker", True)
        if re.search(r"(?:traceback|stack trace|exception at|sql syntax|debug toolbar)", lowered):
            facts.setdefault("verbose_error", True)
        if "{{" in body or "}}" in body or "<%" in body:
            facts.setdefault("template_marker", True)
        if re.search(r"(?:callback|fetch_url|url\s*=\s*https?://|webhook)", lowered):
            facts.setdefault("server_request_observed", True)
        if any("multipart/form-data" in str(value).lower() for value in parser.methods.values()):
            facts.setdefault("file_processing_observed", True)
        if response.status_code in {401, 403}:
            facts.setdefault("auth_transition", True)
        facts.setdefault("role", role)
        facts.setdefault("status_code", response.status_code)
        return facts

    def _pace(self) -> int:
        rate = float(self.policy.max_requests_per_second)
        if rate <= 0 or self._last_request_at is None:
            self._last_request_at = self._clock()
            return 0
        minimum_gap = 1.0 / rate
        elapsed = self._clock() - self._last_request_at
        if elapsed < minimum_gap:
            self._sleep(minimum_gap - elapsed)
            self._last_request_at = self._clock()
            return 1
        self._last_request_at = self._clock()
        return 0

    @staticmethod
    def _header(headers: dict[str, str], name: str) -> str:
        wanted = name.lower()
        for key, value in headers.items():
            if str(key).lower() == wanted:
                return str(value or "").strip()
        return ""

    @staticmethod
    def _normalize_url(url: str) -> str:
        parts = urlsplit(str(url).strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return ""
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))

    @staticmethod
    def _site_for(url: str, sites: dict[str, WebSite]) -> WebSite:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}".lower()
        site_id = "site_" + re.sub(r"[^a-z0-9]+", "_", parts.netloc.lower()).strip("_")
        if site_id not in sites:
            sites[site_id] = WebSite(site_id=site_id, origin=origin, virtual_hosts={parts.netloc.lower()})
        return sites[site_id]

    @staticmethod
    def _is_static_asset(url: str) -> bool:
        return bool(re.search(r"\.(?:js|css|png|jpg|jpeg|gif|svg|ico|woff2?)(?:$|\?)", url.lower()))


class WebRoleComparator:
    """Compare same-resource responses without treating status text as proof."""

    def __init__(self, registry: JudgeRegistry | None = None) -> None:
        self.registry = registry or JudgeRegistry()

    def compare(
        self,
        *,
        endpoint: WebEndpoint,
        low_privilege: WebFetch,
        high_privilege: WebFetch,
        resource: str = "",
    ) -> JudgeResult:
        return self.registry.evaluate(
            "authorization-difference",
            {
                "low_privilege": {
                    "status_code": low_privilege.status_code,
                    "body_hash": body_hash(low_privilege.body),
                },
                "high_privilege": {
                    "status_code": high_privilege.status_code,
                    "body_hash": body_hash(high_privilege.body),
                },
                "resource": resource or endpoint.url,
            },
        )


@dataclass(frozen=True)
class BrowserAction:
    sequence: int
    kind: str
    target: str
    value_hash: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserNetworkRecord:
    sequence: int
    method: str
    url: str
    status_code: int
    request_hash: str
    response_hash: str


@dataclass
class BrowserTrace:
    browser_version: str
    trace_id: str = field(default_factory=lambda: f"trace_{uuid4().hex}")
    dom_snapshots: list[dict[str, str]] = field(default_factory=list)
    network: list[BrowserNetworkRecord] = field(default_factory=list)
    actions: list[BrowserAction] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def record_dom(self, url: str, dom: str) -> None:
        self.dom_snapshots.append({"url": _redact_url(url), "dom_hash": body_hash(dom), "dom": _redact_dom(dom)[:500_000]})

    def record_network(self, method: str, url: str, status_code: int, request: str = "", response: str = "") -> None:
        self.network.append(BrowserNetworkRecord(
            len(self.network) + 1,
            str(method).upper(),
            _redact_url(url),
            int(status_code),
            body_hash(request),
            body_hash(response),
        ))

    def record_action(self, kind: str, target: str, value: str = "", **metadata: str) -> None:
        self.actions.append(BrowserAction(
            len(self.actions) + 1,
            str(kind),
            str(target),
            body_hash(value) if value else "",
            {
                str(key): (
                    body_hash(str(item))
                    if any(token in str(key).lower() for token in ("value", "token", "secret", "password", "cookie"))
                    else str(item)[:200]
                )
                for key, item in metadata.items()
            },
        ))

    def as_dict(self, *, include_dom: bool = True) -> dict[str, object]:
        dom = self.dom_snapshots if include_dom else [
            {"url": item["url"], "dom_hash": item["dom_hash"]} for item in self.dom_snapshots
        ]
        return {
            "trace_id": self.trace_id,
            "browser_version": self.browser_version,
            "created_at": self.created_at.isoformat(),
            "dom_snapshots": dom,
            "network": [item.__dict__ for item in self.network],
            "actions": [item.__dict__ for item in self.actions],
        }


class BrowserAutomationPlugin:
    """Browser capture/replay contract with no hard dependency on a browser."""

    def __init__(self, browser_version: str, *, trace: BrowserTrace | None = None) -> None:
        self.browser_version = str(browser_version)
        self.trace = trace or BrowserTrace(self.browser_version)

    def record_dom(self, url: str, dom: str) -> None:
        self.trace.record_dom(url, dom)

    def record_network(self, method: str, url: str, status_code: int, request: str = "", response: str = "") -> None:
        self.trace.record_network(method, url, status_code, request, response)

    def record_action(self, kind: str, target: str, value: str = "", **metadata: str) -> None:
        self.trace.record_action(kind, target, value, **metadata)

    def replay(self, executor: Callable[[BrowserAction], object], *, browser_version: str | None = None) -> list[object]:
        requested = str(browser_version or self.browser_version)
        if requested != self.trace.browser_version:
            raise ValueError("browser trace version mismatch")
        return [executor(action) for action in sorted(self.trace.actions, key=lambda item: item.sequence)]


def _redact_text(value: str) -> str:
    text = str(value or "")
    return re.sub(
        r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)(\s*[:=]\s*)([^\s<&\"']+)",
        lambda match: f"{match.group(1)}{match.group(2)}<redacted:{body_hash(match.group(3))[:12]}>",
        text,
    )


def _redact_dom(value: str) -> str:
    """Redact textual secrets and values embedded in form controls."""
    text = _redact_text(value)
    pattern = re.compile(r"(?is)(<input\b[^>]*\bvalue\s*=\s*)(['\"]?)([^\s>\"']+)(\2)")
    return pattern.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted:{body_hash(match.group(3))[:12]}>{match.group(4)}",
        text,
    )


def _redact_url(value: str) -> str:
    parts = urlsplit(str(value or ""))
    if not parts.query:
        return str(value or "")
    query = []
    for item in parts.query.split("&"):
        if "=" not in item:
            query.append(item)
            continue
        key, raw = item.split("=", 1)
        if any(token in key.lower() for token in ("token", "secret", "password", "key", "auth")):
            raw = "<redacted>"
        query.append(f"{key}={raw}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(query), parts.fragment))


__all__ = [
    "WebFetch", "WebObservation", "WebCrawlResult", "ScopedWebCrawler", "WebRoleComparator",
    "BrowserAction", "BrowserNetworkRecord", "BrowserTrace", "BrowserAutomationPlugin",
]
