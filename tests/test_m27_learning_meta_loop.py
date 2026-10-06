from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from knowledge_engine.m27_learning_contracts import UnsafeLearningPayloadError
from knowledge_engine.m27_learning_meta_loop import (
    OfflineFailureClass,
    OfflineLearningMetaHarnessLoop,
    SanitizedObservationSource,
    SanitizedOfflineObservation,
    classify_failure_mode,
    learning_meta_loop_governance,
    mine_failure_modes,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "knowledge_engine" / "m27_learning_meta_loop.py"


def _observation(
    observed_class: str = "CITATION_RATE_BELOW_GATE",
    *,
    source: SanitizedObservationSource = SanitizedObservationSource.EVAL_SUMMARY,
    source_ref: str = "eval:smoke-citation-001",
    reason_codes: tuple[str, ...] = ("CITATION_GATE_MISS",),
    artifact_ids: tuple[str, ...] = ("artifact:offline-eval-001",),
    citation_rate_percent: int | None = 92,
    latency_p95_ms: int | None = None,
    retrieval_empty_count: int = 0,
    evidence_gap_count: int = 0,
    gate_blocked: bool = False,
) -> SanitizedOfflineObservation:
    return SanitizedOfflineObservation(
        source=source,
        source_ref=source_ref,
        observed_class=observed_class,
        count=2,
        reason_codes=reason_codes,
        artifact_ids=artifact_ids,
        latency_p95_ms=latency_p95_ms,
        citation_rate_percent=citation_rate_percent,
        retrieval_empty_count=retrieval_empty_count,
        evidence_gap_count=evidence_gap_count,
        gate_blocked=gate_blocked,
        summary="Sanitized aggregate metrics only.",
    )


def test_sanitized_observation_rejects_raw_private_payload_markers() -> None:
    with pytest.raises(UnsafeLearningPayloadError):
        SanitizedOfflineObservation(
            source=SanitizedObservationSource.RUNTIME_TRACE,
            source_ref="trace:raw-query-attempt",
            observed_class="CITATION_GAP",
            summary="sanitized aggregate only",
        )


@pytest.mark.parametrize(
    ("observation", "expected"),
    (
        (_observation(), OfflineFailureClass.CITATION_GAP),
        (
            _observation(
                "P95_LATENCY_BREACH",
                citation_rate_percent=None,
                latency_p95_ms=19000,
            ),
            OfflineFailureClass.LATENCY_BUDGET_EXCEEDED,
        ),
        (
            _observation(
                "NO_EVIDENCE_GAIN",
                citation_rate_percent=None,
                retrieval_empty_count=3,
            ),
            OfflineFailureClass.EMPTY_RETRIEVAL,
        ),
        (
            _observation(
                "PROD_EVIDENCE_BRIDGE_GAP",
                citation_rate_percent=None,
                evidence_gap_count=1,
            ),
            OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP,
        ),
        (
            _observation(
                "MEMORY_EVIDENCE_DENIAL",
                citation_rate_percent=None,
            ),
            OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY,
        ),
    ),
)
def test_failure_classification_is_deterministic(
    observation: SanitizedOfflineObservation,
    expected: OfflineFailureClass,
) -> None:
    assert classify_failure_mode(observation) is expected


def test_failure_mining_groups_sanitized_reports_without_payloads() -> None:
    observations = (
        _observation(source_ref="eval:citation-b"),
        _observation(source_ref="eval:citation-a", artifact_ids=("artifact:offline-eval-002",)),
        _observation(
            "P95_LATENCY_BREACH",
            source_ref="budget:latency-a",
            source=SanitizedObservationSource.RUNTIME_BUDGET,
            citation_rate_percent=None,
            latency_p95_ms=18100,
            reason_codes=("P95_GATE_MISS",),
            artifact_ids=("artifact:offline-budget-001",),
        ),
    )

    mined = mine_failure_modes(observations)

    assert tuple(item.failure_class for item in mined) == (
        OfflineFailureClass.CITATION_GAP,
        OfflineFailureClass.LATENCY_BUDGET_EXCEEDED,
    )
    citation = mined[0]
    assert citation.aggregate_count == 4
    assert citation.source_refs == ("eval:citation-a", "eval:citation-b")
    assert citation.as_dict()["raw_payload_present"] is False


def test_loop_generates_ready_for_review_learning_proposals_and_eval_candidates() -> None:
    loop = OfflineLearningMetaHarnessLoop()
    result = loop.run(
        (
            _observation(source_ref="eval:citation-a"),
            _observation(
                "P95_LATENCY_BREACH",
                source=SanitizedObservationSource.RUNTIME_BUDGET,
                source_ref="budget:latency-a",
                reason_codes=("P95_GATE_MISS",),
                artifact_ids=("artifact:offline-budget-001",),
                citation_rate_percent=None,
                latency_p95_ms=19000,
            ),
        )
    )

    assert len(result.mined_failures) == 2
    assert len(result.learning_signals) == 2
    assert len(result.learning_proposals) == 2
    assert len(result.meta_harness_candidates) == 2
    assert result.ready_for_review_count == 4
    assert all(item.requires_human_review for item in result.learning_proposals)
    assert all(item.requires_offline_gate for item in result.learning_proposals)
    assert all(item.auto_apply is False for item in result.learning_proposals)
    assert all(item.production_write is False for item in result.learning_proposals)
    assert all(item.requires_human_review for item in result.meta_harness_candidates)
    assert all(item.auto_apply is False for item in result.meta_harness_candidates)
    assert all(item.auto_merge is False for item in result.meta_harness_candidates)
    assert all(item.auto_promote is False for item in result.meta_harness_candidates)
    assert all(item.production_write is False for item in result.meta_harness_candidates)


def test_loop_is_deterministic_and_idempotent() -> None:
    observations = (
        _observation(source_ref="eval:citation-a"),
        _observation(source_ref="eval:citation-b"),
    )
    first = OfflineLearningMetaHarnessLoop().run(observations).as_dict()
    second = OfflineLearningMetaHarnessLoop().run(tuple(reversed(observations))).as_dict()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_review_packet_contains_sanitized_metadata_only() -> None:
    loop = OfflineLearningMetaHarnessLoop()
    result = loop.run((_observation(),))
    packet = loop.render_review_packet(result)
    encoded = json.dumps(packet, sort_keys=True)

    assert packet["governance"] == learning_meta_loop_governance()
    assert "raw_query" not in encoded
    assert "raw_answer" not in encoded
    assert "full_evidence_body" not in encoded
    assert "provider_prompt" not in encoded
    assert "production_path" not in encoded
    assert '"runtime_behavior_change": false' in encoded


def test_review_packet_governance_has_no_authority() -> None:
    governance = learning_meta_loop_governance()
    assert governance["sanitized_inputs_only"] is True
    assert governance["raw_private_payload_allowed"] is False
    assert governance["requires_human_review"] is True
    assert governance["requires_offline_gate"] is True
    assert governance["self_patching"] is False
    assert governance["auto_apply"] is False
    assert governance["auto_merge"] is False
    assert governance["auto_promote"] is False
    assert governance["production_write"] is False
    assert governance["runtime_behavior_change"] is False
    assert governance["deployment_authority"] is False


@pytest.mark.parametrize(
    "name",
    (
        "apply_patch",
        "self_patch",
        "auto_apply",
        "auto_merge",
        "auto_promote",
        "promote_release",
        "deploy",
        "write_production",
        "write_to_qdrant",
        "write_to_r2",
        "write_to_sqlite",
        "execute_skill",
        "invoke_mcp",
        "restart_production",
    ),
)
def test_loop_exposes_no_mutation_methods(name: str) -> None:
    assert not hasattr(OfflineLearningMetaHarnessLoop, name)


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_loop_has_no_provider_backend_or_production_dependencies() -> None:
    imports = _imports_for(SRC)
    forbidden_fragments = (
        "openai",
        "anthropic",
        "google",
        "qdrant",
        "boto",
        "sqlite",
        "psycopg",
        "requests",
        "httpx",
        "subprocess",
        "pathlib",
        "os",
        "shutil",
    )
    assert all(
        not any(fragment in imported.casefold() for fragment in forbidden_fragments)
        for imported in imports
    )


def test_loop_not_wired_into_runtime_execution_or_production_surfaces() -> None:
    protected = (
        "m27_runtime_harness.py",
        "m27_runtime_execution.py",
        "m27_production_evidence_bridge.py",
        "m27_tool_executor.py",
        "m27_skill_runner.py",
        "m27_memory_activation.py",
    )
    offenders: list[str] = []
    for name in protected:
        path = ROOT / "src" / "knowledge_engine" / name
        if path.exists() and "m27_learning_meta_loop" in path.read_text(encoding="utf-8"):
            offenders.append(name)
    assert offenders == []
