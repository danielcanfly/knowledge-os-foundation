from __future__ import annotations

import json

import pytest

from knowledge_engine.m26_aq_semantic_contract import SemanticRoutingDecision
from knowledge_engine.m27_decision_trace import GuardOutcome, TraceGuard
from knowledge_engine.m27_replay_harness import (
    MISSING_SIGNAL,
    EquivalenceClassification,
    ReplayCaseResult,
    ResponseStatusClass,
    SanitizedReplayInput,
    capture_sanitized_replay_input,
    classify_equivalence,
    classify_response_status,
    run_replay_equivalence,
)


def _comparison(result: ReplayCaseResult, field: str):
    return next(item for item in result.comparisons if item.field == field)


def _cited_input() -> SanitizedReplayInput:
    routing = SemanticRoutingDecision(
        route="SEMANTIC_CLOSURE",
        reason="semantic_support_gap",
        deadline_remaining_ms=7000,
        minimum_budget_ms=4500,
        provider_attempts_remaining=1,
    )
    compiled = {
        "status": "compiled",
        "context_manifest": {
            "selected_passage_ids": ["ev-01", "ev-02"],
            "token_budget": 4096,
        },
        "citations": [
            {"citation_id": "C1", "evidence_id": "ev-01"},
            {"citation_id": "C2", "evidence_id": "ev-02"},
        ],
        "instruction_blocks": [{"text": "must never persist"}],
    }
    verification = {
        "status": "owner_only_cited_answer",
        "terminal_status": "answered",
        "safe_abstention": False,
        "provider_call_count": 2,
        "material_claim_support_verified": True,
        "citation_locator_valid": True,
        "unsupported_accepted_claims": 0,
        "repair_attempted": True,
        "answer_source": "provider_verified_runtime_bound_semantic_closure",
        "answer_text": "sensitive raw answer must not persist",
        "raw_answer": "provider raw body must not persist",
        "citations": [
            {
                "citation_id": "C1",
                "claim_id": "claim_1",
                "evidence_id": "ev-01",
                "locator_id": "loc-01",
                "source_identity": "source-A",
                "exact_quote": "sensitive full evidence text must not persist",
            },
            {
                "citation_id": "C2",
                "claim_id": "claim_1",
                "evidence_id": "ev-02",
                "locator_id": "loc-02",
                "source_identity": "source-B",
                "exact_quote": "another sensitive evidence body",
            },
        ],
        "provider_prompt": "private provider prompt must not persist",
        "credential": "secret-token-must-not-persist",
    }
    return capture_sanitized_replay_input(
        case_id="cited-equivalent",
        routing_signal=routing,
        compiled_output=compiled,
        verification_output=verification,
        guard_outcomes={
            TraceGuard.BAD_TEMPLATE: GuardOutcome.PASSED,
            TraceGuard.UNSUPPORTED_MATERIAL_CLAIM: GuardOutcome.PASSED,
            TraceGuard.GENERIC_EXTRACTIVE_FALLBACK: GuardOutcome.BLOCKED,
        },
    )


def test_available_m26_signals_are_equivalent_after_stage1_normalization() -> None:
    result = run_replay_equivalence(_cited_input())

    assert result.available_signals_equivalent is True
    assert _comparison(result, "response_status_class").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "route").classification is EquivalenceClassification.EQUIVALENT
    assert _comparison(result, "deadline_remaining_ms").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "provider_attempts_remaining").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "selected_evidence_count").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "selected_evidence_ids").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "verification_citation_count").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "material_claim_support_verified").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "unsupported_accepted_claims").classification is (
        EquivalenceClassification.EQUIVALENT
    )


def test_stage1_unavailable_signals_are_not_falsely_equivalent() -> None:
    result = run_replay_equivalence(_cited_input())

    assert _comparison(result, "compute_tier").classification is (
        EquivalenceClassification.MISSING_SIGNAL
    )
    assert _comparison(result, "provider_budget_class").classification is (
        EquivalenceClassification.MISSING_SIGNAL
    )
    assert _comparison(result, "citation_shape").classification is (
        EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    )
    assert _comparison(result, "guard.BAD_TEMPLATE").classification is (
        EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    )
    assert _comparison(
        result, "guard.UNSUPPORTED_MATERIAL_CLAIM"
    ).classification is EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    assert _comparison(
        result, "guard.GENERIC_EXTRACTIVE_FALLBACK"
    ).classification is EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1


def test_explicit_existing_compute_signal_is_reported_as_stage1_unavailable() -> None:
    replay_input = capture_sanitized_replay_input(
        case_id="compute-signal-unavailable",
        routing_signal={
            "route": "SEMANTIC_CLOSURE",
            "reason": "support_gap",
            "deadline_remaining_ms": 7000,
            "minimum_budget_ms": 4500,
            "provider_attempts_remaining": 1,
            "affordable": True,
        },
        compute_tier="LEGACY_M26",
        provider_budget_class="HEALTHY",
        verification_output={
            "status": "owner_only_safe_abstention",
            "terminal_status": "safe_abstention",
            "safe_abstention": True,
            "citations": [],
        },
    )

    result = run_replay_equivalence(replay_input)

    assert _comparison(result, "compute_tier").classification is (
        EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    )
    assert _comparison(result, "provider_budget_class").classification is (
        EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    )


def test_safe_abstention_status_is_preserved() -> None:
    replay_input = capture_sanitized_replay_input(
        case_id="safe-abstention-equivalent",
        routing_signal={
            "route": "SAFE_ABSTENTION",
            "reason": "deadline_or_provider_budget_blocked:SEMANTIC_CLOSURE:support_gap",
            "deadline_remaining_ms": 800,
            "minimum_budget_ms": 4500,
            "provider_attempts_remaining": 0,
            "affordable": False,
        },
        verification_output={
            "status": "owner_only_safe_abstention",
            "terminal_status": "safe_abstention",
            "safe_abstention": True,
            "provider_call_count": 1,
            "material_claim_support_verified": True,
            "citation_locator_valid": True,
            "unsupported_accepted_claims": 0,
            "repair_attempted": True,
            "answer_source": "safe_abstention",
            "citations": [],
        },
    )

    result = run_replay_equivalence(replay_input)

    assert _comparison(result, "response_status_class").legacy_value == "SAFE_ABSTENTION"
    assert _comparison(result, "response_status_class").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert _comparison(result, "safe_abstention").classification is (
        EquivalenceClassification.EQUIVALENT
    )
    assert result.available_signals_equivalent is True


def test_missing_legacy_signal_is_never_treated_as_equivalent() -> None:
    replay_input = capture_sanitized_replay_input(
        case_id="missing-context",
        verification_output={
            "status": "owner_only_safe_abstention",
            "terminal_status": "safe_abstention",
            "safe_abstention": True,
            "citations": [],
        },
    )

    result = run_replay_equivalence(replay_input)

    assert _comparison(result, "context_compiler_status").classification is (
        EquivalenceClassification.MISSING_SIGNAL
    )
    assert _comparison(result, "selected_evidence_count").classification is (
        EquivalenceClassification.MISSING_SIGNAL
    )
    assert _comparison(result, "route").classification is (
        EquivalenceClassification.MISSING_SIGNAL
    )


def test_deferred_pa7_expectation_drift_is_classified_without_runtime_change() -> None:
    replay_input = capture_sanitized_replay_input(
        case_id="legacy-pa7-repair-expectation",
        routing_signal={
            "route": "SAFE_ABSTENTION",
            "reason": "deadline_or_provider_budget_blocked:SEMANTIC_CLOSURE:repair",
            "deadline_remaining_ms": 900,
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

    result = run_replay_equivalence(replay_input)
    drift = _comparison(result, "legacy_expectation.response_status_class")

    assert drift.legacy_value == "CITED_ANSWER"
    assert drift.normalized_value == "SAFE_ABSTENTION"
    assert drift.classification is EquivalenceClassification.LEGACY_EXPECTATION_DRIFT
    assert result.overall_classification is EquivalenceClassification.LEGACY_EXPECTATION_DRIFT
    assert result.available_signals_equivalent is True


def test_capture_and_result_do_not_persist_raw_sensitive_payloads() -> None:
    replay_input = _cited_input()
    result = run_replay_equivalence(replay_input)

    serialized = json.dumps(
        {
            "input": repr(replay_input),
            "result": result.as_dict(),
        },
        sort_keys=True,
    )
    forbidden_values = (
        "sensitive raw answer must not persist",
        "provider raw body must not persist",
        "sensitive full evidence text must not persist",
        "another sensitive evidence body",
        "private provider prompt must not persist",
        "secret-token-must-not-persist",
        "must never persist",
    )
    assert all(value not in serialized for value in forbidden_values)
    assert "exact_quote" not in serialized
    assert "provider_prompt" not in serialized
    assert "credential" not in serialized


def test_case_id_rejects_free_form_query_text() -> None:
    with pytest.raises(ValueError, match="sanitized identifier"):
        capture_sanitized_replay_input(
            case_id="What private question did the customer ask?",
        )


def test_unsafe_safety_critical_difference_has_distinct_classification() -> None:
    assert classify_equivalence(
        "CITED_ANSWER",
        "SAFE_ABSTENTION",
        safety_critical=True,
    ) is EquivalenceClassification.UNSAFE_DRIFT


def test_noncritical_difference_is_normalization_drift() -> None:
    assert classify_equivalence(
        "SEMANTIC_CLOSURE",
        "CLAIM_WEAKENING",
        safety_critical=False,
    ) is EquivalenceClassification.NORMALIZATION_DRIFT


def test_response_status_classifier_handles_error_and_unavailable() -> None:
    error = capture_sanitized_replay_input(
        case_id="error-status",
        verification_output={
            "status": "provider_error",
            "terminal_status": "failed",
        },
    )
    missing = capture_sanitized_replay_input(case_id="missing-status")

    assert classify_response_status(error.verification) is ResponseStatusClass.ERROR
    assert classify_response_status(missing.verification) is ResponseStatusClass.UNAVAILABLE
    assert missing.verification.status == MISSING_SIGNAL
