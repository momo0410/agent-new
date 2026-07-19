from __future__ import annotations

import asyncio
import json
import zipfile

from app.core.report_contract import ReportCompletenessValidator, ReportSnapshot
from app.core.report_export import ReportExporter, build_report_document
from app.routers import api
from app.services.pentest_agent.state import State


def test_report_export_formats_share_integrity_and_redact_secrets(tmp_path):
    document = build_report_document(
        {
            "targets": ["TARGET"],
            "findings": [{"target": "TARGET", "name": "fixture finding"}],
            "canonical_evidence": [{"evidence_id": "e1", "status": "INCONCLUSIVE", "password": "SECRET"}],
            "actions_taken": [{"id": "a1", "tool": "probe", "status": "completed"}],
            "event_count": 3,
        },
        task_id="task-report",
    )
    result = ReportExporter(document).export(tmp_path)
    assert set(result["paths"]) == {"md", "html", "json", "pdf", "docx"}
    assert all(path.exists() and path.stat().st_size > 0 for path in map(__import__("pathlib").Path, result["paths"].values()))
    json_payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert json_payload["integrity_hash"] == result["integrity_hash"]
    assert "SECRET" not in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert (tmp_path / "report.pdf").read_bytes().startswith(b"%PDF-")
    digest = result["integrity_hash"].encode()
    assert digest in (tmp_path / "report.md").read_bytes()
    assert digest in (tmp_path / "report.html").read_bytes()
    assert digest in (tmp_path / "report.pdf").read_bytes()
    with zipfile.ZipFile(tmp_path / "report.docx") as archive:
        assert digest in archive.read("word/document.xml")


def test_high_risk_report_fields_mark_gaps_and_preserve_provenance():
    document = build_report_document(
        {
            "targets": ["TARGET"],
            "vulnerabilities": [{
                "finding_id": "v1",
                "target": "TARGET",
                "name": "high risk fixture",
                "severity": "high",
                "why_suspected": "observable banner mismatch",
                "evidence_refs": ["evidence:e1"],
            }],
            "web_findings": [{
                "finding_id": "w1",
                "url": "https://TARGET/path",
                "rule_id": "RULE-1",
                "status": "POTENTIALLY_VULNERABLE",
                "reason": "fixture fact matched",
                "evidence_refs": ["web:endpoint:hash"],
            }],
            "environment_fingerprint": {"python": "3.14", "platform": "fixture"},
            "runtime_snapshot": {
                "schema_version": "runtime-snapshot.v1",
                "tools": {"fixture-tool": {"version": "1.2.3", "status": "ok"}},
                "snapshot_hash": "runtime-hash",
            },
            "scope_contract": {
                "scope_id": "scope-report",
                "policy_version": "scope.v1",
                "policy_template_id": "course",
                "policy_template_version": "1",
                "policy_template_hash": "template-hash",
            },
            "scope_token_id": "scope-token-id",
            "autonomy_mode": "supervised",
            "autonomy_history": [{"previous": "advisory", "current": "supervised"}],
            "action_limit": "probe",
            "action_limit_history": [{"previous": "observe", "current": "probe"}],
            "tool_fallbacks": [{"schema_version": "tool-fallback.v1"}],
            "model_calls": [{"call_id": "model-1", "route_strategy": "strong"}],
            "browser_traces": {"trace-1": {"browser_version": "fixture"}},
            "event_integrity": {"event_count": 4, "last_hash": "event-hash", "sealed": True},
        },
        task_id="task-provenance",
    )
    assert len(document["technical_findings"]) == 2
    high_risk = document["technical_findings"][0]
    assert high_risk["risk_class"] == "high"
    assert high_risk["why_suspected"] == "observable banner mismatch"
    assert high_risk["verification_method"] == "[MISSING]"
    assert set(high_risk["missing_fields"]) >= {
        "verification_method", "impact", "reproduction", "remediation",
    }
    web = document["technical_findings"][1]
    assert web["source_type"] == "deterministic_web_rule"
    assert web["verification_method"] == "WebRuleEngine:RULE-1"
    provenance = document["provenance"]
    assert provenance["environment_fingerprint"]["python"] == "3.14"
    assert provenance["tool_versions"]["fixture-tool"]["version"] == "1.2.3"
    assert provenance["scope_contract_id"] == "scope-report"
    assert len(provenance["scope_contract_hash"]) == 64
    assert provenance["event_chain_hash"] == "event-hash"
    assert provenance["browser_trace_ids"] == ["trace-1"]
    assert provenance["model_calls"][0]["route_strategy"] == "strong"


def test_report_export_api_returns_format_manifest(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_report-api.json"
    State(str(state_path))
    monkeypatch.setitem(api._pentest_tasks, "report-api", {"state_file": str(state_path)})
    result = asyncio.run(api.pentest_export_report(api.ReportExportRequest(task_id="report-api", formats=["json", "pdf"])))
    assert result["formats"] == ["json", "pdf"]
    assert set(result["files"]) == {"json", "pdf"}


def test_report_completeness_gate_identifies_incomplete_high_risk_finding():
    document = build_report_document(
        {
            "targets": ["TARGET"],
            "vulnerabilities": [{
                "finding_id": "high-1",
                "target": "TARGET",
                "severity": "critical",
                "why_suspected": "fixture signal",
            }],
        },
        task_id="task-gate",
    )
    snapshot = ReportSnapshot.from_document(document)
    check = ReportCompletenessValidator().validate(snapshot)
    assert not check.complete
    assert check.incomplete_high_risk_findings == ("high-1",)
    assert "high-risk findings" in " ".join(check.reasons)
