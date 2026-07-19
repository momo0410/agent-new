from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.contracts import ScopeContract
from app.routers import api
from app.services.pentest_agent.state import State


def test_web_crawl_api_persists_scoped_fixture_observations(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_web-api.json"
    state = State(str(state_path))
    scope = ScopeContract(
        owner="fixture-owner",
        allowed_targets=["fixture.local"],
        allowed_ports=[80],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state.data["scope_contract"] = scope.model_dump(mode="json")
    state.save()
    monkeypatch.setitem(api._pentest_tasks, "web-api", {"state_file": str(state_path)})

    request = api.WebCrawlRequest(
        task_id="web-api",
        seeds=["http://fixture.local/?page=1"],
        fixtures={
            "http://fixture.local/?page=1": api.WebFixtureResponse(
                body='<a href="/safe">safe</a><a href="/logout">logout</a>',
                request_id="root",
                headers={"Set-Cookie": "sid=fixture"},
            ),
            "http://fixture.local/safe": api.WebFixtureResponse(body="safe"),
        },
    )
    result = asyncio.run(api.agent_web_crawl(request))
    assert result["request_count"] == 2
    assert result["session_id"].startswith("web_")
    assert any("logout" in item["url"] for item in result["blocked"])
    reloaded = State(str(state_path))
    assert reloaded.data["web_observations"]
    assert reloaded.data["event_count"] >= 3


def test_web_crawl_api_emits_rule_findings_and_browser_trace_replay(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_web-findings.json"
    state = State(str(state_path))
    scope = ScopeContract(
        owner="fixture-owner",
        allowed_targets=["fixture.local"],
        allowed_ports=[80],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state.data["scope_contract"] = scope.model_dump(mode="json")
    state.save()
    monkeypatch.setitem(api._pentest_tasks, "web-findings", {"state_file": str(state_path)})

    result = asyncio.run(
        api.agent_web_crawl(
            api.WebCrawlRequest(
                task_id="web-findings",
                seeds=["http://fixture.local/"],
                session_id="web-findings-session",
                fixtures={
                    "http://fixture.local/": api.WebFixtureResponse(
                        body="fixture response",
                        facts={
                            "reflected_input": True,
                            "input_validation_status": "POTENTIALLY_VULNERABLE",
                            "input_validation_reason": "reflection observed in fixture",
                        },
                    )
                },
            )
        )
    )
    assert result["findings"]
    assert result["findings"][0]["rule_id"] == "web.input-validation.v1"
    reloaded = State(str(state_path))
    assert reloaded.data["web_findings"]
    assert any(event.event_type == "web.finding" for event in reloaded.event_store.read())

    trace_result = asyncio.run(
        api.agent_web_browser_trace(
            api.BrowserTraceRequest(
                task_id="web-findings",
                browser_version="chromium-1",
                trace_id="trace-fixture",
                dom_snapshots=[
                    {"url": "http://fixture.local/?token=SECRET", "dom": "<input value=SECRET>"}
                ],
                network=[
                    {
                        "method": "GET",
                        "url": "http://fixture.local/?token=SECRET",
                        "status_code": 200,
                        "request": "token=SECRET",
                        "response": "ok",
                    }
                ],
                actions=[{"kind": "click", "target": "#submit", "value": "SECRET"}],
                replay=True,
            )
        )
    )
    assert trace_result["replay"][0]["kind"] == "click"
    encoded = str(trace_result["trace"])
    assert "SECRET" not in encoded

    with pytest.raises(api.HTTPException) as exc_info:
        asyncio.run(
            api.agent_web_browser_trace(
                api.BrowserTraceRequest(
                    task_id="web-findings",
                    browser_version="chromium-1",
                    trace_id="trace-mismatch",
                    actions=[{"kind": "click", "target": "#x"}],
                    replay=True,
                    replay_browser_version="chromium-2",
                )
            )
        )
    assert exc_info.value.status_code == 409
