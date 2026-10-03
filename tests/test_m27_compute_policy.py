from __future__ import annotations

import json
from copy import deepcopy

import pytest

from knowledge_engine.m26_aq_semantic_contract import SemanticRoutingDecision
from knowledge_engine.m27_compute_policy import (
    CLAIM_WEAKENING,
    CONTRADICTION_TRIAGE,
    EVIDENCE_SLOT_REALIGNMENT,
    FAST_RETRY_ONCE,
    SAFE_ABSTENTION,
    SEMANTIC_CLOSURE,
    RuleBasedComputePolicy,
    ShadowComputeReasonCode,
)
from knowledge_engine.m27_context_runtime_contracts import STAGE1_UNAVAILABLE
from knowledge_engine.m27_decision_trace import BudgetClass, ComputeTier, ProviderAttemptClass


def _decision(
    route: str,
    *,
    reason: str = "test_reason",
    deadline_remaining_ms: int = 8_000,
    minimum_budget_ms: int = 4_500,
    provider_attempts_remaining: int = 2,
) -> SemanticRoutingDecision:
    return SemanticRoutingDecision(
        route=route,
        reason=reason,
        deadline_remaining_ms=deadline_remaining_ms,
        minimum_budget_ms=minimum_budget_ms,
        provider_attempts_remaining=provider_attempts_remaining,
    )


def test_fast_retry_classifies_fast_only_when_existing_m26_signal_is_affordable() -> None:
    signal = _decision(
        FAST_RETRY_ONCE,
        minimum_budget_ms=7_000,
        deadline_remaining_ms=8_500,
        provider_attempts_remaining=2,
    )

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.legacy_route == FAST_RETRY_ONCE
    assert observed.legacy_reason == "test_reason"
    assert observed.deadline_remaining_ms == 8_500
    assert observed.minimum_budget_ms == 7_000
    assert observed.budget_headroom_ms == 1_500
    assert observed.provider_attempts_remaining == 2
    assert observed.affordable is True
    assert observed.shadow_compute_tier is ComputeTier.FAST
    assert observed.shadow_reason_code is ShadowComputeReasonCode.FAST_RETRY_ROUTE
    assert observed.deadline_budget_class is BudgetClass.HEALTHY
    assert observed.provider_budget_class is BudgetClass.HEALTHY
    assert observed.provider_attempt_class is ProviderAttemptClass.MULTIPLE
    assert observed.shadow_only is True
    assert observed.authoritative is False


@pytest.mark.parametrize(
    "route",
    [
        SEMANTIC_CLOSURE,
        EVIDENCE_SLOT_REALIGNMENT,
        CLAIM_WEAKENING,
        CONTRADICTION_TRIAGE,
    ],
)
def test_existing_bounded_semantic_recovery_routes_classify_standard(route: str) -> None:
    signal = _decision(route, provider_attempts_remaining=1)

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.shadow_compute_tier is ComputeTier.STANDARD
    assert (
        observed.shadow_reason_code
        is ShadowComputeReasonCode.BOUNDED_SEMANTIC_RECOVERY_ROUTE
    )
    assert observed.provider_budget_class is BudgetClass.CONSTRAINED
    assert observed.provider_attempt_class is ProviderAttemptClass.ONE


def test_deadline_pressure_is_preserved_without_becoming_deep_authority() -> None:
    signal = _decision(
        SEMANTIC_CLOSURE,
        reason="deadline_pressure_allowed:SEMANTIC_CLOSURE:semantic_support_gap",
        deadline_remaining_ms=500,
        minimum_budget_ms=4_500,
        provider_attempts_remaining=1,
    )
    assert signal.affordable is False

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.shadow_compute_tier is ComputeTier.STANDARD
    assert observed.shadow_compute_tier is not ComputeTier.DEEP
    assert observed.deadline_pressure_allowed is True
    assert observed.shadow_reason_code is ShadowComputeReasonCode.DEADLINE_PRESSURE_PRESERVED
    assert observed.deadline_budget_class is BudgetClass.CONSTRAINED
    assert observed.provider_budget_class is BudgetClass.CONSTRAINED
    assert observed.budget_headroom_ms == -4_000
    assert observed.authoritative is False


def test_safe_abstention_budget_block_classifies_fail_closed_without_new_failure_action() -> None:
    signal = _decision(
        SAFE_ABSTENTION,
        reason="deadline_or_provider_budget_blocked:FAST_RETRY_ONCE:fast_provider_abstained",
        deadline_remaining_ms=3_000,
        minimum_budget_ms=7_000,
        provider_attempts_remaining=0,
    )

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.shadow_compute_tier is ComputeTier.FAIL_CLOSED
    assert observed.shadow_reason_code is ShadowComputeReasonCode.EXISTING_BUDGET_BLOCK
    assert observed.provider_budget_class is BudgetClass.EXHAUSTED
    assert observed.provider_attempt_class is ProviderAttemptClass.NONE
    assert observed.affordable is False
    assert observed.authoritative is False


def test_existing_safe_abstention_alone_is_sufficient_fail_closed_signal() -> None:
    signal = _decision(
        SAFE_ABSTENTION,
        reason="contradiction_without_sufficient_diverse_evidence",
        deadline_remaining_ms=12_000,
        minimum_budget_ms=1_000,
        provider_attempts_remaining=3,
    )

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.shadow_compute_tier is ComputeTier.FAIL_CLOSED
    assert observed.shadow_reason_code is ShadowComputeReasonCode.EXISTING_SAFE_ABSTENTION
    assert observed.deadline_budget_class is BudgetClass.HEALTHY
    assert observed.provider_budget_class is BudgetClass.HEALTHY


def test_deep_is_not_guessed_from_specialized_semantic_route() -> None:
    policy = RuleBasedComputePolicy()

    tiers = {
        policy.classify(_decision(route)).shadow_compute_tier
        for route in (CLAIM_WEAKENING, EVIDENCE_SLOT_REALIGNMENT, CONTRADICTION_TRIAGE)
    }

    assert tiers == {ComputeTier.STANDARD}
    assert ComputeTier.DEEP not in tiers


def test_missing_budget_signal_stays_legacy_m26_instead_of_inventing_tier() -> None:
    observed = RuleBasedComputePolicy().classify(
        {"route": SEMANTIC_CLOSURE, "reason": "semantic_support_gap"}
    )

    assert observed.shadow_compute_tier is ComputeTier.LEGACY_M26
    assert observed.shadow_reason_code is ShadowComputeReasonCode.INCOMPLETE_LEGACY_SIGNAL
    assert observed.deadline_remaining_ms == STAGE1_UNAVAILABLE
    assert observed.minimum_budget_ms == STAGE1_UNAVAILABLE
    assert observed.budget_headroom_ms == STAGE1_UNAVAILABLE
    assert observed.provider_attempts_remaining == STAGE1_UNAVAILABLE
    assert observed.affordable == STAGE1_UNAVAILABLE
    assert observed.deadline_budget_class is BudgetClass.UNAVAILABLE_IN_STAGE1
    assert observed.provider_budget_class is BudgetClass.UNAVAILABLE_IN_STAGE1
    assert observed.provider_attempt_class is ProviderAttemptClass.UNAVAILABLE_IN_STAGE1


def test_unknown_route_with_complete_budget_stays_legacy_m26() -> None:
    observed = RuleBasedComputePolicy().classify(_decision("UNKNOWN_FUTURE_ROUTE"))

    assert observed.shadow_compute_tier is ComputeTier.LEGACY_M26
    assert observed.shadow_reason_code is ShadowComputeReasonCode.UNKNOWN_LEGACY_ROUTE


def test_inconsistent_fast_signal_does_not_get_forced_into_a_tier() -> None:
    signal = _decision(
        FAST_RETRY_ONCE,
        deadline_remaining_ms=1_000,
        minimum_budget_ms=7_000,
        provider_attempts_remaining=1,
    )
    assert signal.affordable is False

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.shadow_compute_tier is ComputeTier.LEGACY_M26
    assert observed.shadow_reason_code is ShadowComputeReasonCode.INCONSISTENT_LEGACY_SIGNAL


def test_deadline_exhaustion_class_is_derived_only_from_existing_minimum_budget() -> None:
    signal = _decision(
        SEMANTIC_CLOSURE,
        reason="deadline_pressure_allowed:SEMANTIC_CLOSURE:semantic_support_gap",
        deadline_remaining_ms=0,
        minimum_budget_ms=4_500,
        provider_attempts_remaining=1,
    )

    observed = RuleBasedComputePolicy().classify(signal)

    assert observed.deadline_budget_class is BudgetClass.EXHAUSTED
    assert observed.budget_headroom_ms == -4_500
    assert observed.shadow_compute_tier is ComputeTier.STANDARD


def test_classification_preserves_input_mapping_and_ignores_private_payload_fields() -> None:
    signal = {
        "route": SEMANTIC_CLOSURE,
        "reason": "semantic_support_gap",
        "deadline_remaining_ms": 7_000,
        "minimum_budget_ms": 4_500,
        "provider_attempts_remaining": 2,
        "affordable": True,
        "raw_query": "PRIVATE QUERY",
        "raw_answer": "PRIVATE ANSWER",
        "evidence_body": "PRIVATE EVIDENCE",
        "provider_prompt": "PRIVATE PROMPT",
        "secret": "PRIVATE SECRET",
    }
    before = deepcopy(signal)

    observed = RuleBasedComputePolicy().classify(signal)
    serialized = json.dumps(observed.as_dict(), sort_keys=True)

    assert signal == before
    assert observed.shadow_compute_tier is ComputeTier.STANDARD
    for forbidden in (
        "PRIVATE QUERY",
        "PRIVATE ANSWER",
        "PRIVATE EVIDENCE",
        "PRIVATE PROMPT",
        "PRIVATE SECRET",
    ):
        assert forbidden not in serialized


def test_normalize_keeps_canonical_compute_decision_and_does_not_assign_shadow_tier() -> None:
    signal = _decision(SEMANTIC_CLOSURE)
    normalized = RuleBasedComputePolicy().normalize(signal)

    assert normalized.route == signal.route
    assert normalized.reason == signal.reason
    assert normalized.deadline_remaining_ms == signal.deadline_remaining_ms
    assert normalized.minimum_budget_ms == signal.minimum_budget_ms
    assert normalized.provider_attempts_remaining == signal.provider_attempts_remaining
    assert normalized.affordable is signal.affordable
    assert normalized.compute_tier == STAGE1_UNAVAILABLE
