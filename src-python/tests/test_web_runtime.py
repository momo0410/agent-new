from __future__ import annotations

import pytest

from app.core.web_model import AuthSession, WebCrawlerPolicy, WebEndpoint, WebRuleEngine, WebSessionStore
from app.core.web_runtime import (
    BrowserAutomationPlugin,
    ScopedWebCrawler,
    WebFetch,
    WebRoleComparator,
)


def test_scoped_crawler_discovers_links_and_rechecks_redirect_scope():
    policy = WebCrawlerPolicy(allowed_origins=("https://fixture.local",), max_depth=2)
    responses = {
        "https://fixture.local/": WebFetch(
            "https://fixture.local/",
            200,
            headers={"Location": "https://outside.local/redirect"},
            body='<a href="/admin">admin</a>',
            request_id="root",
        ),
        "https://fixture.local/admin": WebFetch(
            "https://fixture.local/admin",
            403,
            body="forbidden",
            request_id="admin",
        ),
    }

    crawl = ScopedWebCrawler(policy, lambda url, _method: responses[url]).crawl(["https://fixture.local/"])
    assert len(crawl.observations) == 2
    assert any(item["url"] == "https://outside.local/redirect" for item in crawl.blocked)
    assert len(crawl.sites["site_fixture_local"].endpoints) == 2


def test_role_comparator_uses_paired_response_judge():
    endpoint = WebEndpoint.create("https://fixture.local/item/1")
    result = WebRoleComparator().compare(
        endpoint=endpoint,
        low_privilege=WebFetch(endpoint.url, 200, body="item"),
        high_privilege=WebFetch(endpoint.url, 200, body="secret-item"),
    )
    assert result.accepted
    assert result.judge_id == "authorization-difference"


def test_web_policy_blocks_dangerous_methods():
    policy = WebCrawlerPolicy(allowed_origins=("https://fixture.local",))
    assert not policy.permits("https://fixture.local/", depth=0, method="DELETE")[0]


def test_crawler_blocks_dangerous_links_and_tracks_rate_and_query_parameters():
    policy = WebCrawlerPolicy(
        allowed_origins=("https://fixture.local",),
        max_requests_per_second=10,
    )
    responses = {
        "https://fixture.local/?id=1": WebFetch(
            "https://fixture.local/?id=1",
            200,
            headers={"Set-Cookie": "sid=fixture"},
            body='<a href="/logout">logout</a><a href="/safe">safe</a>',
        ),
        "https://fixture.local/safe": WebFetch("https://fixture.local/safe", 200, body="ok"),
    }
    delays: list[float] = []
    crawl = ScopedWebCrawler(policy, lambda url, _method: responses[url], sleep=delays.append).crawl(
        ["https://fixture.local/?id=1"]
    )
    assert crawl.request_count == 2
    assert crawl.rate_delays == 1
    assert any("logout" in item["url"] for item in crawl.blocked)
    endpoint = next(iter(crawl.sites["site_fixture_local"].endpoints.values()))
    assert endpoint.parameters[0].name == "id"

    session = AuthSession("session-1", "student")
    session.set_cookie("sid", "fixture")
    assert session.request_headers()["Cookie"] == "sid=fixture"
    assert WebSessionStore().redacted() == []


def test_web_rule_engine_and_browser_trace_replay():
    findings = WebRuleEngine().evaluate({"role_difference": True, "evidence_refs": ["e1"]})
    assert findings[0].category == "authorization"
    assert findings[0].evidence_refs == ("e1",)

    browser = BrowserAutomationPlugin("fixture-browser-1")
    browser.record_dom("https://fixture.local/", "<main>fixture</main>")
    browser.record_network("GET", "https://fixture.local/", 200, response="ok")
    browser.record_action("click", "#login", "secret-input")
    assert "secret-input" not in str(browser.trace.as_dict())
    assert browser.replay(lambda action: action.kind) == ["click"]
    with pytest.raises(ValueError):
        browser.replay(lambda action: action.kind, browser_version="other")
