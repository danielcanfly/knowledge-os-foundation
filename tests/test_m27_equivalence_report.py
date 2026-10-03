from __future__ import annotations

from knowledge_engine.m27_decision_trace import GuardOutcome, TraceGuard
from knowledge_engine.m27_equivalence_report import build_equivalence_report
from knowledge_engine.m27_replay_harness import (
    EquivalenceClassification,
    ResponseStatusClass,
    capture_sanitized_replay_input,
    run_replay_equivalence,
)


def _equivalent_case():
    replay_input = capture_sanitized_replay_input(
        case_id="report-cited",
        routing_signal={
            "route": "SEMANTIC_CLOSURE",
            "reason": "support_gap",
            "deadline_remaining_ms": 7000,
            "minimum_budget_ms": 4500,
            "provider_attempts_remaining": 1,
            "affordable": True,
        },
        compiled_output={
            "status": "compiled",
            "context_manifest": {"selected_passage_ids": ["ev-1", "ev-2"]},
            "citations": [{}, {}],
        },
        verification_output={
            "status": "owner_only_cited_answer",
            "terminal_status": "answered",
            "safe_abstention": False,
            "provider_call_count": 1,
            "material_claim_support_verified": True,
            "citation_locator_valid": True,
            "unsupported_accepted_claims": 0,
            "repair_attempted": False,
            "answer_source": "provider_verified",
            "citations": [
                {
                    "citation_id": "C1",
                    "claim_id": "claim_1",
                    "evidence_id": "ev-1",
                    "locator_id": "loc-1",
                    "source_identity": "src-1",
                }
            ],
        },
        guard_outcomes={
            TraceGuard.BAD_TEMPLATE: GuardOutcome.PASSED,
            TraceGuard.UNSUPPORTED_MATERIAL_CLAIM: GuardOutcome.PASSED,
            TraceGuard.GENERIC_EXTRACTIVE_FALLBACK: GuardOutcome.BLOCKED,
        },
    )
    return run_replay_equivalence(replay_input)


def _legacy_drift_case():
    replay_input = capture_sanitized_replay_input(
        case_id="report-legacy-drift",
        routing_signal={
            "route": "SAFE_ABSTENTION",
            "reason": "deadline_or_provider_budget_blocked:SEMANTIC_CLOSURE:repair",
            "deadline_remaining_ms": 700,
            "minimum_budget_ms": 4500,
            "provider_attempts_remaining": 0,
            "affordable": False,
        },
        verification_output={
            "status": "owner_only_safe_abstention",
            "terminal_status": "safe_abstention",
            "safe_abstention": True,
            "provider_call_count": 2,
            "material_claim_support_verified": True,
            "citation_locator_valid": True,
            "unsupported_accepted_claims": 0,
            "repair_attempted": True,
            "answer_source": "safe_abstention",
            "citations": [],
        },
        legacy_expected_status_class=ResponseStatusClass.CITED_ANSWER,
    )
    return run_replay_equivalence(replay_input)


def test_report_summarizes_available_equivalence_and_unavailable_fields() -> None:
    report = build_equivalence_report([_equivalent_case()])

    assert report.case_count == 1
    assert report.available_signals_equivalent is True
    assert report.threatens_production_invariants is False
    assert report.ready_for_next_stage_review is True
    counts = dict(report.field_classification_counts)
    assert counts[EquivalenceClassification.EQUIVALENT.value] > 0
    assert counts[EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1.value] > 0
    assert report.normalization_drift_fields == ()
    assert report.unsafe_drift_fields == ()


def test_report_preserves_legacy_expectation_drift_as_non_runtime_drift() -> None:
    report = build_equivalence_report([_legacy_drift_case()])

    assert report.available_signals_equivalent is True
    assert report.threatens_production_invariants is False
    assert report.legacy_expectation_drift_fields == (
        "report-legacy-drift:legacy_expectation.response_status_class",
    )


def test_report_markdown_never_contains_replay_values() -> None:
    result = _equivalent_case()
    report = build_equivalence_report([result])

    markdown = report.render_markdown()

    assert "provider_verified" not in markdown
    assert "support_gap" not in markdown
    assert "ev-1" not in markdown
    assert "src-1" not in markdown
    assert "report-cited:guard.BAD_TEMPLATE" in markdown


def test_report_dict_is_fixed_summary_shape_without_raw_payloads() -> None:
    report = build_equivalence_report([_equivalent_case(), _legacy_drift_case()])

    payload = report.as_dict()

    assert set(payload) == {
        "case_count",
        "overall_classification_counts",
        "field_classification_counts",
        "unsafe_drift_fields",
        "normalization_drift_fields",
        "legacy_expectation_drift_fields",
        "expected_unavailable_stage1_fields",
        "missing_signal_fields",
        "available_signals_equivalent",
        "threatens_production_invariants",
        "ready_for_next_stage_review",
    }
    assert payload["case_count"] == 2
    assert payload["available_signals_equivalent"] is True


def test_empty_report_is_safe_and_reviewable() -> None:
    report = build_equivalence_report([])

    assert report.case_count == 0
    assert report.available_signals_equivalent is True
    assert report.threatens_production_invariants is False
    assert report.render_markdown().endswith("\n")
