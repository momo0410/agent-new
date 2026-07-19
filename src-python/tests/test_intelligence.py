from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.intelligence import (
    IntelligenceCatalog,
    IntelligenceParser,
    IntelligenceScorer,
    IntelligenceSource,
)


def test_parser_normalizes_online_record_and_removes_target_specific_values():
    record = IntelligenceParser.parse(
        {
            "cve_id": "CVE-2099-0001",
            "product": "Example HTTP Server",
            "version": "2.4.49",
            "platform": "linux",
            "description": "Test at 192.0.2.10 using password=TOPSECRET; proof-of-concept only",
            "validation_evidence": ["fixture response marker"],
            "cvss_score": 9.1,
            "published": "2025-01-01T00:00:00Z",
        }
    )
    assert record.risk == "critical"
    assert "192.0.2.10" not in record.sanitized_summary
    assert "TOPSECRET" not in record.sanitized_summary
    assert record.known_pseudocode
    assert record.source_chain


def test_scorer_blocks_mismatch_and_keeps_uncertain_record_suspected():
    source = IntelligenceSource(source_id="nvd:1", credibility=0.95)
    record = IntelligenceParser.parse(
        {
            "record_id": "r1",
            "product": "Example HTTP Server",
            "versions": ["2.4.49"],
            "platforms": ["linux"],
            "validation_evidence": ["reproduction fixture"],
            "risk": "high",
        },
        source=source,
    )
    scorer = IntelligenceScorer()
    mismatch = scorer.score(record, {"product": "Other Server", "version": "2.4.49", "platform": "linux"})
    assert mismatch.status == "INCONCLUSIVE"
    unknown = scorer.score(record, {"product": "Example HTTP Server", "platform": "linux"})
    assert unknown.status == "CANDIDATE"
    assert unknown.score > 0


def test_catalog_uses_source_agreement_and_preserves_provenance():
    old = datetime.now(timezone.utc) - timedelta(days=30)
    first = IntelligenceParser.parse(
        {"record_id": "same", "product": "demo", "validation_evidence": ["a"], "published_at": old.isoformat()},
        source=IntelligenceSource(source_id="source-a", credibility=0.8, published_at=old),
    )
    second = IntelligenceParser.parse(
        {"record_id": "same", "product": "demo", "validation_evidence": ["b"], "published_at": old.isoformat()},
        source=IntelligenceSource(source_id="source-b", credibility=0.9, published_at=old),
    )
    catalog = IntelligenceCatalog()
    catalog.add(first)
    catalog.add(second)
    candidates = catalog.candidates({"product": "demo", "version": "1.0", "platform": "linux"})
    assert len(candidates) == 1
    assert set(candidates[0].source_refs) == {"source-a", "source-b"}
    assert candidates[0].status == "CANDIDATE"


def test_state_keeps_legacy_intel_and_structured_candidates(tmp_path):
    from app.services.pentest_agent.state import State

    state = State(str(tmp_path / "state.json"))
    assert state.add_service_intel(
        "Example HTTP Server 2.4.49",
        {
            "tool": "search_cve",
            "data": {
                "source": "NVD",
                "cve_matches": [
                    {
                        "cve_id": "CVE-2099-0002",
                        "version": "2.4.49",
                        "validation_evidence": ["fixture marker"],
                        "cvss_score": 8.0,
                    }
                ],
            },
        },
    )
    assert state.data["service_intel"]
    assert state.data["structured_intel"]
    assert state.data["intel_candidates"]
    assert state.data["intel_candidates"][0]["source_refs"]
