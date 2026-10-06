from __future__ import annotations

from knowledge_engine.m27_compute_policy import RuleBasedComputePolicy
from knowledge_engine.m27_context_orchestrator import (
    ContinuationReasonCode,
    M27ContextOrchestrator,
    M27RuntimeTask,
    RuntimeContextSource,
    RuntimeTaskKind,
)
from knowledge_engine.m27_skill_contracts import build_stage7_ops_skill_registry
from knowledge_engine.m27_tool_registry import build_stage5_readonly_registry


def _orchestrator() -> M27ContextOrchestrator:
    return M27ContextOrchestrator(
        skill_registry=build_stage7_ops_skill_registry(
            tool_registry=build_stage5_readonly_registry(),
        ),
    )


def _compute(route: str = "SEMANTIC_CLOSURE", attempts: int = 1):
    return RuleBasedComputePolicy().classify(
        {
            "route": route,
            "reason": "bounded_semantic_recovery",
            "deadline_remaining_ms": 2000,
            "minimum_budget_ms": 500,
            "provider_attempts_remaining": attempts,
            "affordable": True,
        }
    )


def test_no_context_plan_selects_no_resources() -> None:
    plan = _orchestrator().plan(
        M27RuntimeTask(
            task_id="task:no-context:001",
            kind=RuntimeTaskKind.NO_CONTEXT,
            request_token="request:no-context:001",
        )
    )

    assert plan.context_sources == ()
    assert plan.tool_capabilities == ()
    assert plan.selected_skill_name is None
    assert plan.memory_read_enabled is False


def test_knowledge_plan_selects_knowledge_search_only() -> None:
    plan = _orchestrator().plan(
        M27RuntimeTask(
            task_id="task:knowledge:001",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:knowledge:001",
        )
    )

    assert plan.context_sources == (RuntimeContextSource.KNOWLEDGE,)
    assert plan.tool_capabilities == ("knowledge.search",)


def test_tool_plan_uses_requested_readonly_capability() -> None:
    plan = _orchestrator().plan(
        M27RuntimeTask(
            task_id="task:tool:001",
            kind=RuntimeTaskKind.TOOL,
            request_token="request:tool:001",
            requested_capability="runtime.get_health",
        )
    )

    assert plan.context_sources == (RuntimeContextSource.TOOL,)
    assert plan.tool_capabilities == ("runtime.get_health",)


def test_ops_latency_plan_selects_descriptor_only_skill() -> None:
    plan = _orchestrator().plan(
        M27RuntimeTask(
            task_id="task:ops:001",
            kind=RuntimeTaskKind.OPS,
            request_token="request:ops:001",
            ops_intent="latency",
        )
    )

    assert plan.context_sources == (RuntimeContextSource.SKILL,)
    assert plan.selected_skill_name == "diagnose-latency"
    assert "runtime.get_trace" in plan.tool_capabilities
    assert plan.selected_skill_plan is not None
    assert plan.selected_skill_plan.execution_status == "DESCRIPTIVE_ONLY"


def test_memory_is_selected_only_when_explicitly_allowed() -> None:
    without_memory = _orchestrator().plan(
        M27RuntimeTask(
            task_id="task:memory:001",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:memory:001",
        )
    )
    with_memory = _orchestrator().plan(
        M27RuntimeTask(
            task_id="task:memory:002",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:memory:002",
            allow_memory_read=True,
        )
    )

    assert RuntimeContextSource.MEMORY_CANDIDATE not in without_memory.context_sources
    assert RuntimeContextSource.MEMORY_CANDIDATE in with_memory.context_sources


def test_continuation_allows_one_bounded_round_for_verifier_gap() -> None:
    orchestrator = _orchestrator()
    plan = orchestrator.plan(
        M27RuntimeTask(
            task_id="task:continue:001",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:continue:001",
            max_continuation_rounds=1,
            max_tool_calls=4,
        )
    )

    decision = orchestrator.continuation_decision(
        verification_status="needs_repair",
        material_claim_support_verified=False,
        citation_locator_valid=True,
        unsupported_accepted_claims=0,
        safe_abstention=False,
        compute_observation=_compute(),
        completed_rounds=0,
        tool_calls=1,
        plan=plan,
    )

    assert decision.allowed is True
    assert decision.reason_code is ContinuationReasonCode.VERIFIER_GAP_BOUNDED_CONTINUATION


def test_continuation_blocks_when_round_budget_is_exhausted() -> None:
    orchestrator = _orchestrator()
    plan = orchestrator.plan(
        M27RuntimeTask(
            task_id="task:continue:002",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:continue:002",
            max_continuation_rounds=1,
        )
    )

    decision = orchestrator.continuation_decision(
        verification_status="needs_repair",
        material_claim_support_verified=False,
        citation_locator_valid=True,
        unsupported_accepted_claims=0,
        safe_abstention=False,
        compute_observation=_compute(),
        completed_rounds=1,
        tool_calls=1,
        plan=plan,
    )

    assert decision.allowed is False
    assert decision.reason_code is ContinuationReasonCode.MAX_CONTINUATION_ROUNDS_EXHAUSTED


def test_continuation_blocks_when_provider_attempt_budget_is_exhausted() -> None:
    orchestrator = _orchestrator()
    plan = orchestrator.plan(
        M27RuntimeTask(
            task_id="task:continue:003",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:continue:003",
        )
    )

    decision = orchestrator.continuation_decision(
        verification_status="needs_repair",
        material_claim_support_verified=False,
        citation_locator_valid=True,
        unsupported_accepted_claims=0,
        safe_abstention=False,
        compute_observation=_compute(attempts=0),
        completed_rounds=0,
        tool_calls=1,
        plan=plan,
    )

    assert decision.allowed is False
    assert decision.reason_code is ContinuationReasonCode.PROVIDER_BUDGET_EXHAUSTED
