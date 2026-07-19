from __future__ import annotations

import pytest

from app.core.observation import ObservationRecord, ObservationStore
from app.services.pentest_agent.executor import Executor
from app.services.pentest_agent.state import State


def test_observation_record_is_hash_bound_redacted_and_replayable(tmp_path):
    record = ObservationRecord.create(
        task_id="task-observation",
        target="TARGET",
        source="fixture-tool",
        source_version="fixture 1.2",
        raw_output="80/tcp open http",
        raw_ref="raw://task-observation/a1",
        parser="parse_port_services",
        parser_version="parse_port_services.v2",
        facts=[{"port": 80, "password": "SECRET"}],
        action_id="a1",
        event_refs=["action:a1"],
    )
    assert record.verify_integrity()
    assert record.facts == [{"port": 80, "password": "[REDACTED]"}]
    with pytest.raises((TypeError, ValueError)):
        record.target = "OTHER"  # type: ignore[misc]

    store = ObservationStore(tmp_path / "observations.jsonl")
    assert store.append(record).observation_id == record.observation_id
    assert store.append(record).observation_id == record.observation_id
    assert store.verify()["observation_count"] == 1
    replayed = store.replay(
        record.observation_id,
        raw_loader=lambda ref: "80/tcp open http",
        parser=lambda raw: [{"raw": raw, "parser": "v3"}],
        parser_name="fixture-parser",
        parser_version="fixture-parser.v3",
    )
    assert replayed.parent_observation_id == record.observation_id
    assert replayed.parser_version == "fixture-parser.v3"
    assert store.verify()["observation_count"] == 2


def test_executor_attaches_observation_and_state_event(monkeypatch, tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("TARGET")
    executor = Executor(state=state, task_id="task-observation")
    cfg = {
        "command": "fixture {args}",
        "parser": "parse_raw",
        "parser_version": "fixture-parser.v1",
        "source": "fixture-plugin",
        "plugin_version": "fixture-plugin.v4",
        "timeout": 5,
    }
    probe = {"version": "fixture-binary 9.1"}
    monkeypatch.setattr(
        executor,
        "_select_tool_with_fallback",
        lambda tool, args: {"tool": "fixture", "cfg": cfg, "args": args, "probe": probe, "notes": []},
    )
    monkeypatch.setattr(
        executor,
        "_run_process",
        lambda *args, **kwargs: {
            "stdout": "fixture output",
            "stderr": "",
            "full_output": "fixture output",
            "returncode": 0,
            "parsed": [{"fact": "observed"}],
        },
    )
    state.start_action("fixture", "TARGET", llm_decision="fixture")
    result = executor.run("fixture", "TARGET", target="TARGET", action_type="scan")
    assert result["observation_id"].startswith("obs_")
    assert result["parser_version"] == "fixture-parser.v1"
    observations = state.observation_store.list()
    assert len(observations) == 1
    assert observations[0].source_version == "fixture-binary 9.1"
    events = state.event_store.read()
    assert any(event.event_type == "observation.recorded" for event in events)
    assert observations[0].raw_hash == result["raw_hash"]

