from __future__ import annotations

import json

from knowledge_engine.m27_adaptive_compute import (
    AdaptiveComputeController,
    AdaptiveReasonCode,
)
from knowledge_engine.m27_compute_policy import RuleBasedComputePolicy
from knowledge_engine.m27_context_orchestrator import RuntimeTaskKind, RuntimeTaskProfile
from knowledge_engine.m27_decision_trace import ComputeTier


def _compute(*, attempts: int = 4, deadline: int = 8000, minimum: int = 1000):
    return RuleBasedComputePolicy().classify(
        {
            "route": "SEMANTIC_CLOSURE",
            "reason": "bounded_semantic_recovery",
            "deadline_remaining_ms": deadline,
            "minimum_budget_ms": minimum,
            "provider_attempts_remaining": attempts,
            "affordable": deadline >= minimum and attempts > 0,
        }
    )


def test_direct_knowledge_is_standard_and_bounded() -> None:
    decision = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.DIRECT_KNOWLEDGE,
        compute=_compute(),
        requested_max_rounds=99,
        requested_max_tool_calls=99,
    )

    assert decision.tier is ComputeTier.STANDARD
    assert decision.max_continuation_rounds == 1
    assert decision.max_tool_calls == 2
    assert decision.max_provider_calls == 2


def test_retrieval_hard_can_use_deep_only_with_healthy_budget() -> None:
    controller = AdaptiveComputeController()
    healthy = controller.decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=_compute(attempts=4),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )
    constrained = controller.decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=_compute(attempts=1),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )

    assert healthy.tier is ComputeTier.DEEP
    assert healthy.max_continuation_rounds == 2
    assert healthy.max_tool_calls == 3
    assert healthy.max_provider_calls == 4
    assert constrained.tier is ComputeTier.STANDARD
    assert constrained.max_continuation_rounds == 1
    assert constrained.max_provider_calls == 1


def test_deadline_pressure_forces_fast_no_continuation() -> None:
    decision = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.DEADLINE_PRESSURE,
        compute=_compute(deadline=2000, minimum=1000),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )

    assert decision.tier is ComputeTier.FAST
    assert decision.max_continuation_rounds == 0
    assert decision.max_tool_calls == 1


def test_exhausted_budget_fails_closed() -> None:
    decision = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=_compute(attempts=0),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )

    assert decision.tier is ComputeTier.FAIL_CLOSED
    assert decision.max_continuation_rounds == 0
    assert decision.max_tool_calls == 0
    assert decision.max_provider_calls == 0


def test_continuation_uses_telemetry_and_stops_stale_later_rounds() -> None:
    controller = AdaptiveComputeController()
    budget = controller.decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=_compute(attempts=4),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )
    go = controller.decide_continuation(
        budget=budget,
        telemetry={"evidence_delta": 1, "round_total_ms": 100.0},
        completed_rounds=0,
        tool_calls=1,
        provider_calls=1,
        verified=False,
    )
    probe = controller.decide_continuation(
        budget=budget,
        telemetry={"evidence_delta": 0, "round_total_ms": 100.0},
        completed_rounds=0,
        tool_calls=1,
        provider_calls=1,
        verified=False,
    )
    stop = controller.decide_continuation(
        budget=budget,
        telemetry={"evidence_delta": 0, "round_total_ms": 100.0},
        completed_rounds=1,
        tool_calls=2,
        provider_calls=2,
        verified=False,
    )

    assert go.allowed is True
    assert go.reason_code is AdaptiveReasonCode.TELEMETRY_PROGRESS
    assert probe.allowed is True
    assert probe.reason_code is AdaptiveReasonCode.TELEMETRY_EMPTY_FIRST_ROUND_PROBE
    assert stop.allowed is False
    assert stop.reason_code is AdaptiveReasonCode.TELEMETRY_NO_EVIDENCE_GAIN


def test_latency_pressure_stops_continuation() -> None:
    controller = AdaptiveComputeController()
    budget = controller.decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=_compute(attempts=4),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )
    decision = controller.decide_continuation(
        budget=budget,
        telemetry={"evidence_delta": 1, "round_total_ms": 2500.0},
        completed_rounds=0,
        tool_calls=1,
        provider_calls=1,
        verified=False,
    )

    assert decision.allowed is False
    assert decision.reason_code is AdaptiveReasonCode.TELEMETRY_LATENCY_PRESSURE


def test_no_unbounded_compute_even_with_extreme_requested_values() -> None:
    decision = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=_compute(attempts=999),
        requested_max_rounds=999,
        requested_max_tool_calls=999,
    )

    assert decision.max_continuation_rounds <= 2
    assert decision.max_tool_calls <= 6
    assert decision.max_provider_calls <= 12


def test_private_payload_does_not_enter_compute_decision() -> None:
    signal = {
        "route": "SEMANTIC_CLOSURE",
        "reason": "bounded_semantic_recovery",
        "deadline_remaining_ms": 8000,
        "minimum_budget_ms": 1000,
        "provider_attempts_remaining": 4,
        "affordable": True,
        "raw_query": "PRIVATE QUERY",
        "raw_answer": "PRIVATE ANSWER",
        "provider_prompt": "PRIVATE PROMPT",
        "secret": "PRIVATE SECRET",
    }
    decision = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.KNOWLEDGE,
        profile=RuntimeTaskProfile.RETRIEVAL_HARD,
        compute=RuleBasedComputePolicy().classify(signal),
        requested_max_rounds=2,
        requested_max_tool_calls=6,
    )
    encoded = json.dumps(decision.as_dict(), sort_keys=True)

    for forbidden in ("PRIVATE QUERY", "PRIVATE ANSWER", "PRIVATE PROMPT", "PRIVATE SECRET"):
        assert forbidden not in encoded
