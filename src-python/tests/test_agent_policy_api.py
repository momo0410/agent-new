from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.contracts import ScopeContract
from app.core.policy_templates import CoursePolicyRegistry, CoursePolicyTemplate
from app.core.scope_policy import ScopePolicy
from app.routers import api


def _template() -> CoursePolicyTemplate:
    ceiling = ScopeContract(
        owner="course-admin",
        allowed_targets=["fixture.local"],
        allowed_ports=[80, 443],
        max_duration_seconds=600,
        max_commands=20,
        max_network_requests=100,
        max_requests_per_second=2,
        max_concurrency=2,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        data_handling="task_retained",
    )
    return CoursePolicyTemplate(
        template_id="fixture-course",
        version="1.0.0",
        owner="teacher",
        scope_ceiling=ceiling,
    )


def test_course_policy_publish_bind_get_and_audit(monkeypatch):
    registry = CoursePolicyRegistry()
    monkeypatch.setattr(api, "_course_policy_registry", registry)
    monkeypatch.setattr(api, "_pentest_scope_policy", ScopePolicy(course_policies=registry))
    template = _template()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            api.publish_course_policy(
                api.CoursePolicyPublishRequest(
                    template=template.model_dump(mode="json"),
                    actor="student",
                    actor_role="student",
                )
            )
        )
    assert exc_info.value.status_code == 400

    published = asyncio.run(
        api.publish_course_policy(
            api.CoursePolicyPublishRequest(
                template=template.model_dump(mode="json"),
                actor="teacher",
                actor_role="course_admin",
            )
        )
    )
    assert published["success"] is True
    fetched = asyncio.run(api.get_course_policy("fixture-course", "1.0.0"))
    assert fetched["template"]["template_id"] == "fixture-course"

    bound = asyncio.run(
        api.bind_course_policy(
            api.CoursePolicyBindRequest(
                template_id="fixture-course",
                version="1.0.0",
                actor="student",
                actor_role="student",
                values={
                    "owner": "student",
                    "allowed_targets": ["fixture.local"],
                    "allowed_ports": [80],
                    "max_duration_seconds": 300,
                    "max_commands": 10,
                },
            )
        )
    )
    assert bound["scope_contract"]["policy_template_id"] == "fixture-course"
    assert bound["scope_contract"]["policy_template_hash"]
    audit = asyncio.run(api.course_policy_audit())
    assert [item["event"] for item in audit["events"]] == [
        "course_policy.published", "course_policy.bound"
    ]


def test_course_policy_api_rejects_scope_widening(monkeypatch):
    registry = CoursePolicyRegistry()
    template = _template()
    registry.publish(template, actor="teacher", actor_role="course_admin")
    monkeypatch.setattr(api, "_course_policy_registry", registry)
    monkeypatch.setattr(api, "_pentest_scope_policy", ScopePolicy(course_policies=registry))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            api.bind_course_policy(
                api.CoursePolicyBindRequest(
                    template_id="fixture-course",
                    version="1.0.0",
                    values={
                        "owner": "student",
                        "allowed_targets": ["outside.fixture"],
                    },
                )
            )
        )
    assert exc_info.value.status_code == 400


def test_policy_routes_are_local_session_protected():
    import inspect

    from app import main

    assert "/api/v1/agent/policy" in inspect.getsource(main.local_agent_session_guard)
