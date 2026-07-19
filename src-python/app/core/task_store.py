"""Event-sourced task aggregate with idempotent action recovery."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .event_store import EventProjectorRegistry, EventStore


def initial_task_read_model() -> dict[str, Any]:
    """Return the stable empty read model used for event replay and recovery."""
    return {
        "schema_version": "task-read-model.v1",
        "status": "created",
        "phase": "init",
        "targets": [],
        "actions": {},
        "evidence": {},
        "findings": {},
        "assets": {},
        "budget": {},
        "warnings": [],
        "mission_control": {},
        "web_observations": [],
        "web_blocked": [],
        "web_findings": [],
        "browser_traces": {},
        "intelligence": [],
        "observations": {},
        "asset_imports": [],
        "sessions": {},
        "candidates": [],
        "phase_history": [],
        "token_usage": {},
        "report_snapshots": [],
        "autonomy_mode": "supervised",
        "autonomy_history": [],
        "autonomy_blocks": [],
        "action_limit": "post_verify",
        "action_limit_history": [],
        "action_limit_blocks": [],
        "tool_fallbacks": [],
        "model_calls": [],
        "runtime_snapshot": {},
        "versions": {},
        "global_kill_switch": {"enabled": False},
        "timeline": [],
    }


def default_projectors() -> EventProjectorRegistry:
    registry = EventProjectorRegistry()

    def created(state, event):
        config = event.payload.get("config")
        if isinstance(config, dict):
            state.update(config)
        state.update({key: value for key, value in event.payload.items() if key != "config"})
        state["task_id"] = str(event.task_id)
        state.setdefault("status", "created")
        state.setdefault("actions", {})
        state.setdefault("evidence", {})
        state.setdefault("findings", {})
        state.setdefault("assets", {})
        state.setdefault("budget", {})
        state.setdefault("warnings", [])
        state.setdefault("mission_control", {})
        state.setdefault("web_observations", [])
        state.setdefault("web_blocked", [])
        state.setdefault("web_findings", [])
        state.setdefault("browser_traces", {})
        state.setdefault("intelligence", [])
        state.setdefault("observations", {})
        state.setdefault("asset_imports", [])
        state.setdefault("sessions", {})
        state.setdefault("candidates", [])
        state.setdefault("phase_history", [])
        state.setdefault("token_usage", {})
        state.setdefault("report_snapshots", [])
        state.setdefault("autonomy_mode", "supervised")
        state.setdefault("autonomy_history", [])
        state.setdefault("autonomy_blocks", [])
        state.setdefault("action_limit", "post_verify")
        state.setdefault("action_limit_history", [])
        state.setdefault("action_limit_blocks", [])
        state.setdefault("tool_fallbacks", [])
        state.setdefault("model_calls", [])
        state.setdefault("runtime_snapshot", {})
        state.setdefault("versions", {})
        state.setdefault("global_kill_switch", {"enabled": False})
        state.setdefault("timeline", [])
        return state

    def scope_created(state, event):
        state["scope"] = {**dict(state.get("scope") or {}), **event.payload}
        state["scope_id"] = str(event.payload.get("scope_id", state.get("scope_id", "")))
        return state

    def target_added(state, event):
        target = str(event.payload.get("target", "")).strip()
        targets = state.setdefault("targets", [])
        if target and target not in targets:
            targets.append(target)
        return state

    def phase_changed(state, event):
        current = str(event.payload.get("current") or event.new_state or "").lower()
        previous = str(event.payload.get("previous") or event.previous_state or "").lower()
        if current:
            state["phase"] = current
        history = state.setdefault("phase_history", [])
        item = {
            "previous": previous,
            "current": current,
            "reason": str(event.reason or event.payload.get("reason", "")),
            "sequence": event.sequence,
        }
        if item not in history:
            history.append(item)
        state["phase_history"] = history[-100:]
        return state

    def candidate_ranked(state, event):
        candidates = event.payload.get("candidates", [])
        if isinstance(candidates, list):
            state["candidates"] = [item for item in candidates if isinstance(item, dict)][-500:]
        return state

    def action_updated(state, event):
        action_id = str(event.payload.get("action_id", ""))
        if action_id:
            action = state.setdefault("actions", {}).setdefault(action_id, {})
            action.update(event.payload)
            action["sequence"] = event.sequence
        return state

    def session_recorded(state, event):
        session_id = str(event.payload.get("session_id", event.event_id))
        state.setdefault("sessions", {})[session_id] = {**event.payload, "sequence": event.sequence}
        return state

    def token_usage_recorded(state, event):
        usage = state.setdefault("token_usage", {})
        for key, value in event.payload.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[str(key)] = value
        return state

    def report_snapshot_recorded(state, event):
        snapshots = state.setdefault("report_snapshots", [])
        item = {**event.payload, "sequence": event.sequence}
        if item not in snapshots:
            snapshots.append(item)
        state["report_snapshots"] = snapshots[-20:]
        return state

    def status(state, event):
        state["status"] = str(
            event.new_state or event.payload.get("status", event.event_type.split(".")[-1])
        ).lower()
        state["status_reason"] = event.reason
        return state

    def mission_status(state, event):
        status_value = str(
            event.new_state or event.payload.get("status", event.event_type.split(".")[-1])
        ).lower()
        if status_value == "resumed":
            status_value = "running"
        reason = str(event.reason or event.payload.get("reason", ""))
        control = dict(state.get("mission_control") or {})
        control.update({
            "mission_id": str(event.payload.get("mission_id", control.get("mission_id", ""))),
            "status": status_value,
            "canonical_status": str(event.new_state or status_value).upper(),
            "reason": reason,
            "paused": status_value == "paused",
            "cancel_requested": status_value in {"cancelling", "cancelled"},
            "updated_at": event.timestamp.isoformat(),
        })
        state["mission_control"] = control
        state["mission_status"] = control["canonical_status"]
        state["status"] = status_value
        state["status_reason"] = reason
        return state

    def action_started(state, event):
        state.setdefault("actions", {})[str(event.payload.get("action_id", event.event_id))] = {
            **event.payload,
            "status": "running",
            "sequence": event.sequence,
            "idempotency_key": event.idempotency_key,
        }
        return state

    def action_finished(state, event):
        action_id = str(event.payload.get("action_id", ""))
        action = state.setdefault("actions", {}).setdefault(action_id, {})
        action.update(event.payload)
        default_status = "cancelled" if event.event_type == "action.cancelled" else "completed"
        action["status"] = str(event.payload.get("status", default_status))
        action["sequence"] = event.sequence
        return state

    def evidence_recorded(state, event):
        evidence_id = str(event.payload.get("evidence_id", event.event_id))
        record = dict(event.payload)
        record["sequence"] = event.sequence
        record["evidence_refs"] = list(event.evidence_refs)
        state.setdefault("evidence", {})[evidence_id] = record
        return state

    def finding_transitioned(state, event):
        finding_id = str(
            event.payload.get("finding_id")
            or event.payload.get("finding_key")
            or event.event_id
        )
        finding = state.setdefault("findings", {}).setdefault(finding_id, {})
        finding.update(event.payload)
        finding["status"] = str(
            event.new_state
            or event.payload.get("new_state")
            or event.payload.get("status")
            or finding.get("status", "INCONCLUSIVE")
        ).upper()
        finding["reason"] = str(event.reason or event.payload.get("reason", ""))
        finding["sequence"] = event.sequence
        finding["evidence_refs"] = sorted(set(finding.get("evidence_refs", []) + list(event.evidence_refs)))
        return state

    def asset_observed(state, event):
        asset_id = str(event.payload.get("asset_id") or event.payload.get("node_id") or event.event_id)
        asset = state.setdefault("assets", {}).setdefault(asset_id, {})
        asset.update(event.payload)
        asset["sequence"] = event.sequence
        return state

    def budget_updated(state, event):
        budget = state.setdefault("budget", {})
        for key, value in event.payload.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                budget[str(key)] = value
        return state

    def policy_denied(state, event):
        warning = {
            "event_id": event.event_id,
            "reason": str(event.reason or event.payload.get("reason", "policy denied")),
            "action_id": str(event.payload.get("action_id", "")),
            "sequence": event.sequence,
        }
        warnings = state.setdefault("warnings", [])
        if warning not in warnings:
            warnings.append(warning)
        return state

    def web_observation(state, event):
        observations = state.setdefault("web_observations", [])
        item = {**event.payload, "sequence": event.sequence}
        key = (str(item.get("endpoint_id", "")), str(item.get("body_hash", "")))
        if not any(
            isinstance(existing, dict)
            and (str(existing.get("endpoint_id", "")), str(existing.get("body_hash", ""))) == key
            for existing in observations
        ):
            observations.append(item)
        state["web_observations"] = observations[-5000:]
        return state

    def web_blocked(state, event):
        blocked = state.setdefault("web_blocked", [])
        item = {**event.payload, "sequence": event.sequence}
        if item not in blocked:
            blocked.append(item)
        state["web_blocked"] = blocked[-2000:]
        return state

    def web_finding(state, event):
        findings = state.setdefault("web_findings", [])
        item = {**event.payload, "sequence": event.sequence, "evidence_refs": list(event.evidence_refs)}
        key = str(item.get("finding_id", ""))
        if key and not any(isinstance(existing, dict) and str(existing.get("finding_id", "")) == key for existing in findings):
            findings.append(item)
        state["web_findings"] = findings[-2000:]
        return state

    def web_browser_trace(state, event):
        traces = state.setdefault("browser_traces", {})
        trace_id = str(event.payload.get("trace_id", event.event_id))
        traces[trace_id] = {**event.payload, "sequence": event.sequence}
        return state

    def intelligence_recorded(state, event):
        records = state.setdefault("intelligence", [])
        item = {**event.payload, "sequence": event.sequence}
        if item not in records:
            records.append(item)
        state["intelligence"] = records[-1000:]
        return state

    def autonomy_changed(state, event):
        current = str(event.new_state or event.payload.get("current", "supervised")).lower()
        state["autonomy_mode"] = current
        history = state.setdefault("autonomy_history", [])
        item = {
            "previous": str(event.previous_state or event.payload.get("previous", "")).lower(),
            "current": current,
            "actor": str(event.actor),
            "reason": str(event.reason or ""),
            "sequence": event.sequence,
        }
        if item not in history:
            history.append(item)
        state["autonomy_history"] = history[-100:]
        return state

    def tool_fallback(state, event):
        history = state.setdefault("tool_fallbacks", [])
        item = {**event.payload, "sequence": event.sequence}
        if item not in history:
            history.append(item)
        state["tool_fallbacks"] = history[-500:]
        return state

    def observation_recorded(state, event):
        observation_id = str(event.payload.get("observation_id") or event.event_id)
        record = {**event.payload, "sequence": event.sequence, "evidence_refs": list(event.evidence_refs)}
        state.setdefault("observations", {})[observation_id] = record
        return state

    def asset_inventory_imported(state, event):
        imports = state.setdefault("asset_imports", [])
        item = {**event.payload, "sequence": event.sequence}
        import_id = str(item.get("import_id", ""))
        if import_id and any(
            isinstance(existing, dict) and str(existing.get("import_id", "")) == import_id
            for existing in imports
        ):
            return state
        imports.append(item)
        state["asset_imports"] = imports[-100:]
        return state

    def runtime_snapshot_recorded(state, event):
        snapshot = state.setdefault("runtime_snapshot", {})
        snapshot.update(event.payload)
        snapshot["sequence"] = event.sequence
        return state

    def kill_switch_changed(state, event):
        state["global_kill_switch"] = {
            **dict(state.get("global_kill_switch") or {}),
            **event.payload,
            "sequence": event.sequence,
        }
        return state

    def autonomy_blocked(state, event):
        blocks = state.setdefault("autonomy_blocks", [])
        item = {**event.payload, "sequence": event.sequence, "reason": event.reason or event.payload.get("reason", "")}
        if item not in blocks:
            blocks.append(item)
        state["autonomy_blocks"] = blocks[-200:]
        return state

    def action_limit_changed(state, event):
        current = str(event.new_state or event.payload.get("current", "post_verify"))
        state["action_limit"] = current
        history = state.setdefault("action_limit_history", [])
        item = {
            "previous": str(event.previous_state or event.payload.get("previous", "")),
            "current": current,
            "actor": str(event.actor),
            "reason": str(event.reason or event.payload.get("reason", "")),
            "sequence": event.sequence,
        }
        if item not in history:
            history.append(item)
        state["action_limit_history"] = history[-100:]
        return state

    def action_limit_blocked(state, event):
        blocks = state.setdefault("action_limit_blocks", [])
        item = {**event.payload, "sequence": event.sequence, "reason": event.reason or event.payload.get("reason", "")}
        if item not in blocks:
            blocks.append(item)
        state["action_limit_blocks"] = blocks[-200:]
        return state

    def model_called(state, event):
        calls = state.setdefault("model_calls", [])
        item = {**event.payload, "sequence": event.sequence}
        if item not in calls:
            calls.append(item)
        state["model_calls"] = calls[-500:]
        return state

    registry.register("task.created", created)
    registry.register("scope.created", scope_created)
    registry.register("target.added", target_added)
    for event_type in (
        "task.running", "task.paused", "task.resumed", "task.stopped",
        "task.cancelling", "task.cancelled", "task.completed", "task.failed",
    ):
        registry.register(event_type, status)
    for event_type in (
        "mission.running", "mission.paused", "mission.resumed", "mission.cancelling",
        "mission.cancelled", "mission.completed", "mission.failed",
    ):
        registry.register(event_type, mission_status)
    registry.register("action.started", action_started)
    registry.register("action.finished", action_finished)
    registry.register("action.cancelled", action_finished)
    registry.register("action.updated", action_updated)
    registry.register("candidate.ranked", candidate_ranked)
    registry.register("phase.changed", phase_changed)
    registry.register("evidence.recorded", evidence_recorded)
    registry.register("finding.transitioned", finding_transitioned)
    registry.register("finding.observed", finding_transitioned)
    registry.register("finding.updated", finding_transitioned)
    registry.register("vulnerability.recorded", finding_transitioned)
    registry.register("asset.observed", asset_observed)
    registry.register("asset.updated", asset_observed)
    registry.register("budget.updated", budget_updated)
    registry.register("policy.denied", policy_denied)
    registry.register("web.observation", web_observation)
    registry.register("web.blocked", web_blocked)
    registry.register("web.finding", web_finding)
    registry.register("web.browser_trace", web_browser_trace)
    registry.register("intelligence.recorded", intelligence_recorded)
    registry.register("autonomy.changed", autonomy_changed)
    registry.register("tool.fallback", tool_fallback)
    registry.register("observation.recorded", observation_recorded)
    registry.register("asset.inventory.imported", asset_inventory_imported)
    registry.register("runtime.snapshot", runtime_snapshot_recorded)
    registry.register("system.kill_switch.changed", kill_switch_changed)
    registry.register("autonomy.blocked", autonomy_blocked)
    registry.register("action_limit.changed", action_limit_changed)
    registry.register("action_limit.blocked", action_limit_blocked)
    registry.register("model.called", model_called)
    registry.register("model.route", model_called)
    registry.register("session.recorded", session_recorded)
    registry.register("session.updated", session_recorded)
    registry.register("token.usage", token_usage_recorded)
    registry.register("report.snapshot", report_snapshot_recorded)
    return registry


class EventSourcedTaskStore:
    def __init__(self, path: str | Path):
        self.events = EventStore(path)
        self.projectors = default_projectors()
        self._lock = threading.RLock()

    def create(self, task_id: str, config: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.events.read():
                state = self.rebuild()
                if state.get("task_id") != task_id:
                    raise ValueError("event stream already belongs to another task")
                return state
            immutable = json.loads(json.dumps(config, ensure_ascii=False, default=str))
            self.events.append(task_id, "task.created", {"task_id": task_id, "config": immutable}, actor="task-api", idempotency_key=f"task.create:{task_id}")
            return self.rebuild()

    def append_action_started(self, task_id: str, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        if not idempotency_key:
            raise ValueError("action idempotency key is required")
        action_id = str(action.get("action_id", ""))
        if not action_id:
            raise ValueError("action_id is required")
        self.events.append(task_id, "action.started", dict(action), actor="executor", idempotency_key=f"start:{idempotency_key}")
        return self.rebuild()

    def append_action_finished(self, task_id: str, action_id: str, result: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        payload = {"action_id": action_id, **result}
        self.events.append(task_id, "action.finished", payload, actor="executor", idempotency_key=f"finish:{idempotency_key}")
        return self.rebuild()

    def transition(self, task_id: str, previous: str, new: str, *, reason: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
        self.events.append(
            task_id,
            f"task.{new.lower()}",
            {"status": new},
            actor="orchestrator",
            previous_state=previous,
            new_state=new,
            reason=reason,
            evidence_refs=evidence_refs or [],
            idempotency_key=f"task.transition:{previous}:{new}:{reason}",
        )
        return self.rebuild()

    def rebuild(self) -> dict[str, Any]:
        return self.projectors.rebuild(self.events, initial=initial_task_read_model())

    def replay_manifest(self) -> dict[str, Any]:
        """Return integrity and read-model cursors from a fresh event replay."""
        projected = self.rebuild()
        manifest = self.events.integrity_manifest()
        return {
            "schema_version": "task-replay.v1",
            "task_id": projected.get("task_id", ""),
            "sequence": int(projected.get("sequence", 0) or 0),
            "event_count": manifest["event_count"],
            "last_hash": manifest["last_hash"],
            "timeline_count": len(projected.get("timeline", [])),
            "read_model_hash": __import__("hashlib").sha256(
                json.dumps(projected, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
        }

    def recoverable_actions(self) -> list[dict[str, Any]]:
        state = self.rebuild()
        actions = state.get("actions", {})
        return [
            dict(action)
            for action in actions.values()
            if isinstance(action, dict) and action.get("status") == "running"
        ]

    def completed_idempotency_keys(self) -> set[str]:
        return {
            event.idempotency_key.removeprefix("finish:")
            for event in self.events.read()
            if event.event_type == "action.finished" and event.idempotency_key
        }

    def snapshot(self, path: str | Path) -> dict[str, Any]:
        state = self.rebuild()
        payload = {
            "schema_version": "task-snapshot.v1",
            "state": state,
            "event_manifest": self.events.integrity_manifest(),
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return payload
