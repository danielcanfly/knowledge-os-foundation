from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from knowledge_engine.m27_context_runtime_contracts import (
    STAGE1_UNAVAILABLE,
    ComputeDecision,
    ContextPlan,
    DecisionTraceEvent,
    EvidencePlan,
    PolicyDecision,
    RuntimeTraceStore,
)


def test_unavailable_stage1_marker_is_explicit() -> None:
    plan = ContextPlan(route="SEMANTIC_CLOSURE", reason="support_gap")

    assert plan.planning_mode == "unavailable_in_stage1"
    assert plan.evidence_plan.selected_evidence_ids == STAGE1_UNAVAILABLE
    assert plan.evidence_plan.retrieval_round_count == STAGE1_UNAVAILABLE


def test_contracts_are_frozen_value_objects() -> None:
    decision = ComputeDecision(
        route="SEMANTIC_CLOSURE",
        reason="support_gap",
        deadline_remaining_ms=5000,
        minimum_budget_ms=4500,
        provider_attempts_remaining=1,
        affordable=True,
    )

    with pytest.raises(FrozenInstanceError):
        decision.route = "SAFE_ABSTENTION"  # type: ignore[misc]


class _TraceStore:
    def __init__(self) -> None:
        self.events: list[DecisionTraceEvent] = []

    def record(self, event: DecisionTraceEvent) -> None:
        self.events.append(event)


def test_runtime_trace_store_protocol_is_structural() -> None:
    store = _TraceStore()
    event = DecisionTraceEvent(
        trace_id="trace-1",
        stage="routing",
        decision=PolicyDecision(
            policy_name="legacy_m26_semantic_routing",
            decision="SEMANTIC_CLOSURE",
        ),
    )

    assert isinstance(store, RuntimeTraceStore)
    store.record(event)
    assert store.events == [event]


def test_evidence_plan_defaults_do_not_claim_unobserved_signals() -> None:
    plan = EvidencePlan()

    assert plan.selected_evidence_count == STAGE1_UNAVAILABLE
    assert plan.source_count == STAGE1_UNAVAILABLE
    assert plan.retrieval_round_count == STAGE1_UNAVAILABLE
