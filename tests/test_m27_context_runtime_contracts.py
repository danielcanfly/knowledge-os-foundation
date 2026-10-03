from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from knowledge_engine.m27_context_runtime_contracts import (
    STAGE1_UNAVAILABLE,
    ComputeDecision,
    ContextPlan,
    DecisionTraceEvent,
    EvidencePlan,
    RuntimeTraceStore,
)
from knowledge_engine.m27_decision_trace import (
    BudgetClass,
    ComputeTier,
    ContextSource,
    DecisionReasonCode,
    DecisionRoute,
    SafeAbstentionOutcome,
    StatusClass,
    new_trace_id,
)
from knowledge_engine.m27_decision_trace import (
    DecisionTraceEvent as CanonicalDecisionTraceEvent,
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


def _sanitized_event() -> DecisionTraceEvent:
    return DecisionTraceEvent(
        trace_id=new_trace_id(),
        route=DecisionRoute.SEMANTIC_CLOSURE,
        reason_code=DecisionReasonCode.CLAIM_SUPPORT_GAP,
        compute_tier=ComputeTier.UNAVAILABLE_IN_STAGE1,
        deadline_budget_class=BudgetClass.UNAVAILABLE_IN_STAGE1,
        provider_budget_class=BudgetClass.UNAVAILABLE_IN_STAGE1,
        provider_attempt_count=None,
        context_sources=(ContextSource.UNAVAILABLE_IN_STAGE1,),
        evidence_count=0,
        citation_count=0,
        status_class=StatusClass.UNAVAILABLE_IN_STAGE1,
        safe_abstention_outcome=SafeAbstentionOutcome.UNAVAILABLE_IN_STAGE1,
    )


def test_runtime_trace_store_protocol_uses_canonical_sanitized_trace_event() -> None:
    assert DecisionTraceEvent is CanonicalDecisionTraceEvent
    store = _TraceStore()
    event = _sanitized_event()

    assert isinstance(store, RuntimeTraceStore)
    store.record(event)
    assert store.events == [event]
    assert not hasattr(event, "metadata")
    assert not hasattr(event, "payload")


def test_evidence_plan_defaults_do_not_claim_unobserved_signals() -> None:
    plan = EvidencePlan()

    assert plan.selected_evidence_count == STAGE1_UNAVAILABLE
    assert plan.source_count == STAGE1_UNAVAILABLE
    assert plan.retrieval_round_count == STAGE1_UNAVAILABLE
