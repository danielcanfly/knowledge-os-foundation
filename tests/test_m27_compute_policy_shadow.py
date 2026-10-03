from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine.m26_aq_semantic_contract import SemanticRoutingDecision
from knowledge_engine.m27_compute_policy import (
    SEMANTIC_CLOSURE,
    RuleBasedComputePolicy,
)
from knowledge_engine.m27_compute_policy_shadow import (
    M27_COMPUTE_POLICY_SHADOW_ENABLED,
    ComputePolicyShadowFlags,
    classify_shadow_compute,
    load_compute_policy_shadow_flags,
    observe_shadow_compute_if_enabled,
)
from knowledge_engine.m27_decision_trace import ComputeTier
from knowledge_engine.m27_replay_harness import (
    EquivalenceClassification,
    capture_sanitized_replay_input,
    run_replay_equivalence,
)


def _signal() -> SemanticRoutingDecision:
    return SemanticRoutingDecision(
        route=SEMANTIC_CLOSURE,
        reason="semantic_support_gap",
        deadline_remaining_ms=7_000,
        minimum_budget_ms=4_500,
        provider_attempts_remaining=2,
    )


def _comparison(result, field: str):
    return next(item for item in result.comparisons if item.field == field)


def test_shadow_flag_defaults_off() -> None:
    flags = load_compute_policy_shadow_flags(environ={}, isolated_runtime=True)

    assert flags.requested is False
    assert flags.isolated_runtime is True
    assert flags.enabled is False


def test_shadow_flag_requires_explicit_isolated_runtime_even_when_requested() -> None:
    flags = load_compute_policy_shadow_flags(
        environ={M27_COMPUTE_POLICY_SHADOW_ENABLED: "true"},
        isolated_runtime=False,
    )

    assert flags.requested is True
    assert flags.enabled is False


def test_shadow_flag_can_enable_only_for_explicit_isolated_m27() -> None:
    flags = load_compute_policy_shadow_flags(
        environ={M27_COMPUTE_POLICY_SHADOW_ENABLED: "YES"},
        isolated_runtime=True,
    )

    assert flags.enabled is True


def test_disabled_shadow_observer_has_no_result_or_side_effect() -> None:
    signal = _signal()

    observed = observe_shadow_compute_if_enabled(
        signal,
        flags=ComputePolicyShadowFlags(requested=False, isolated_runtime=True),
    )

    assert observed is None


def test_enabled_shadow_observer_is_non_authoritative() -> None:
    observed = observe_shadow_compute_if_enabled(
        _signal(),
        flags=ComputePolicyShadowFlags(requested=True, isolated_runtime=True),
    )

    assert observed is not None
    assert observed.shadow_compute_tier is ComputeTier.STANDARD
    assert observed.shadow_only is True
    assert observed.authoritative is False


@dataclass
class _NoExecutionSignal:
    route: str = SEMANTIC_CLOSURE
    reason: str = "semantic_support_gap"
    deadline_remaining_ms: int = 7_000
    minimum_budget_ms: int = 4_500
    provider_attempts_remaining: int = 2
    provider_call_count: int = 3
    retrieval_round_count: int = 4
    answer_marker: str = "unchanged-answer"

    @property
    def affordable(self) -> bool:
        return True

    def call(self, *_args, **_kwargs):
        raise AssertionError("shadow policy must not call provider")

    def retrieve(self, *_args, **_kwargs):
        raise AssertionError("shadow policy must not retrieve")

    def repair(self, *_args, **_kwargs):
        raise AssertionError("shadow policy must not repair")

    def verify(self, *_args, **_kwargs):
        raise AssertionError("shadow policy must not deepen verification")


def test_shadow_classification_adds_no_provider_retrieval_repair_or_answer_mutation() -> None:
    signal = _NoExecutionSignal()
    before = (
        signal.route,
        signal.reason,
        signal.provider_call_count,
        signal.retrieval_round_count,
        signal.answer_marker,
    )

    observed = classify_shadow_compute(signal)

    after = (
        signal.route,
        signal.reason,
        signal.provider_call_count,
        signal.retrieval_round_count,
        signal.answer_marker,
    )
    assert after == before
    assert observed.legacy_route == signal.route
    assert observed.shadow_only is True
    assert observed.authoritative is False


def test_stage2_replay_lens_preserves_same_raw_m26_budget_fields() -> None:
    signal = _signal()
    before = signal.public()

    shadow = RuleBasedComputePolicy().classify(signal)
    replay = capture_sanitized_replay_input(
        case_id="stage4-budget-equivalence",
        routing_signal=signal,
    )
    result = run_replay_equivalence(replay)
    after = signal.public()

    assert after == before
    assert shadow.shadow_compute_tier is ComputeTier.STANDARD
    assert shadow.authoritative is False
    for field in (
        "route",
        "route_reason",
        "deadline_remaining_ms",
        "minimum_budget_ms",
        "provider_attempts_remaining",
        "deadline_affordable",
    ):
        assert _comparison(result, field).classification is EquivalenceClassification.EQUIVALENT


def test_stage2_replay_compute_tier_gap_remains_explicit_not_backfilled_authoritatively() -> None:
    signal = _signal()
    shadow = classify_shadow_compute(signal)
    replay = capture_sanitized_replay_input(
        case_id="stage4-shadow-tier",
        routing_signal=signal,
        compute_tier=shadow.shadow_compute_tier.value,
    )
    result = run_replay_equivalence(replay)

    comparison = _comparison(result, "compute_tier")
    assert comparison.legacy_value == ComputeTier.STANDARD.value
    assert comparison.classification is EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    assert shadow.shadow_only is True
    assert shadow.authoritative is False
