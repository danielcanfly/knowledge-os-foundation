from __future__ import annotations

import pytest

import knowledge_engine.m27_skill_runner as skill_runner_module
from knowledge_engine.m27_context_runtime_contracts import (
    EvidenceGapSummary,
    EvidenceIdentity,
    EvidencePlanningResult,
    VerificationDecision,
)
from knowledge_engine.m27_decision_trace import (
    BudgetClass,
    ComputeTier,
    ContextSource,
    DecisionReasonCode,
    DecisionRoute,
    DecisionTraceEvent,
    SafeAbstentionOutcome,
    StatusClass,
)
from knowledge_engine.m27_readonly_tools import (
    ExistingResultEvidenceProvider,
    runtime_budget_view,
    runtime_health_view,
    runtime_trace_view,
)
from knowledge_engine.m27_skill_contracts import SkillOutputKind, build_stage7_ops_skill_registry
from knowledge_engine.m27_skill_runner import (
    ReadOnlySkillRunner,
    SkillRunnerAuthorizationError,
    SkillRunnerContext,
    SkillRunnerPolicy,
)
from knowledge_engine.m27_tool_contracts import RuntimeHealthInput, RuntimeLookupInput
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor


class CountingRuntimeProvider:
    def __init__(self, trace: DecisionTraceEvent) -> None:
        self.trace = trace
        self.trace_calls = 0
        self.budget_calls = 0
        self.health_calls = 0

    def get_trace(self, request: RuntimeLookupInput) -> object:
        self.trace_calls += 1
        return runtime_trace_view(self.trace)

    def get_budget(self, request: RuntimeLookupInput) -> object:
        self.budget_calls += 1
        return runtime_budget_view(self.trace)

    def get_health(self, request: RuntimeHealthInput) -> object:
        self.health_calls += 1
        return runtime_health_view(
            {
                "freshness": "snapshot",
                "data": {
                    "overall_status": "healthy",
                    "dependencies": (
                        {"key": "retrieval", "status": "healthy", "freshness": "snapshot"},
                    ),
                },
            }
        )


def _trace() -> DecisionTraceEvent:
    return DecisionTraceEvent(
        trace_id="00000000-0000-4000-8000-000000000001",
        route=DecisionRoute.SEMANTIC_CLOSURE,
        reason_code=DecisionReasonCode.ROUTE_SELECTED,
        compute_tier=ComputeTier.STANDARD,
        deadline_budget_class=BudgetClass.HEALTHY,
        provider_budget_class=BudgetClass.HEALTHY,
        provider_attempt_count=1,
        context_sources=(ContextSource.LEXICAL,),
        evidence_count=1,
        citation_count=1,
        status_class=StatusClass.CITED_ANSWER,
        safe_abstention_outcome=SafeAbstentionOutcome.DID_NOT_ABSTAIN,
    )


def _planning() -> EvidencePlanningResult:
    return EvidencePlanningResult(
        selected_evidence=(EvidenceIdentity("ev-1", "p-1", "src-1", "loc-1", "passage"),),
        selected_evidence_count=1,
        selected_evidence_ids=("ev-1",),
        selected_passage_ids=("p-1",),
        source_identities=("src-1",),
        distinct_source_count=1,
        locator_ids=("loc-1",),
        requirement_ids=("req-1",),
        gap=EvidenceGapSummary(
            covered_requirement_ids=("req-1",),
            missing_requirement_ids=(),
            coverage_status="covered",
            sufficiency_status="sufficient",
            recovered_requirement_ids=(),
            bounded_recovery_used=False,
        ),
    )


def _verification() -> VerificationDecision:
    return VerificationDecision(
        status="verified_answer",
        terminal_status="answered",
        safe_abstention=False,
        reason_codes=("verified",),
        provider_call_count=1,
        material_claim_support_verified=True,
        citation_locator_valid=True,
        unsupported_accepted_claims=0,
        repair_attempted=False,
        citation_count=1,
        answer_source="isolated_runtime",
    )


def _context() -> SkillRunnerContext:
    return SkillRunnerContext(
        request_token="request:skill:001",
        trace_id="00000000-0000-4000-8000-000000000001",
        evidence_planning_result=_planning(),
        verification_decision=_verification(),
    )


def test_diagnose_latency_skill_executes_readonly_tools_end_to_end() -> None:
    runtime = CountingRuntimeProvider(_trace())
    executor = ReadOnlyToolExecutor(
        evidence_provider=ExistingResultEvidenceProvider(), runtime_provider=runtime
    )
    registry = build_stage7_ops_skill_registry(tool_registry=executor.registry)
    descriptor = registry.resolve("diagnose-latency")
    runner = ReadOnlySkillRunner(skill_registry=registry, tool_executor=executor)

    result = runner.run(
        "diagnose-latency",
        context=_context(),
        policy=SkillRunnerPolicy.for_skill(
            descriptor,
            authorization_token="task:skill:001",
            max_tool_calls=3,
        ),
    )

    assert result.status_code == "M27_SKILL_RUN_COMPLETED"
    assert result.output_kind is SkillOutputKind.DIAGNOSTIC_REPORT
    assert [item.capability_name for item in result.boundaries] == [
        "runtime.get_trace",
        "runtime.get_budget",
        "runtime.get_health",
    ]
    assert result.tool_call_count == 3
    assert runtime.trace_calls == 1
    assert runtime.budget_calls == 1
    assert runtime.health_calls == 1
    assert all(item.record.read_only for item in result.boundaries)
    assert all(not item.record.supports_mutation for item in result.boundaries)
    assert all(not item.record.exposes_raw_infra for item in result.boundaries)
    assert result.candidate_actions == (
        "report_only",
        "candidate_followup_only",
        "no_production_mutation",
    )
    assert "answer_text" not in repr(result.as_dict()).casefold()


def test_skill_runner_budget_stops_before_second_tool_call() -> None:
    runtime = CountingRuntimeProvider(_trace())
    executor = ReadOnlyToolExecutor(runtime_provider=runtime)
    registry = build_stage7_ops_skill_registry(tool_registry=executor.registry)
    descriptor = registry.resolve("diagnose-latency")

    result = ReadOnlySkillRunner(skill_registry=registry, tool_executor=executor).run(
        "diagnose-latency",
        context=_context(),
        policy=SkillRunnerPolicy.for_skill(
            descriptor,
            authorization_token="task:skill:002",
            max_tool_calls=1,
        ),
    )

    assert result.status_code == "M27_SKILL_RUN_BUDGET_EXHAUSTED"
    assert result.tool_call_count == 1
    assert runtime.trace_calls == 1
    assert runtime.budget_calls == 0
    assert runtime.health_calls == 0


def test_skill_runner_requires_all_skill_capabilities_to_be_authorized() -> None:
    runtime = CountingRuntimeProvider(_trace())
    executor = ReadOnlyToolExecutor(runtime_provider=runtime)
    registry = build_stage7_ops_skill_registry(tool_registry=executor.registry)

    with pytest.raises(SkillRunnerAuthorizationError):
        ReadOnlySkillRunner(skill_registry=registry, tool_executor=executor).run(
            "diagnose-latency",
            context=_context(),
            policy=SkillRunnerPolicy(
                skill_name="diagnose-latency",
                authorized_capabilities=("runtime.get_trace",),
                authorization_token="task:skill:003",
                max_tool_calls=3,
            ),
        )
    assert runtime.trace_calls == 0
    assert runtime.budget_calls == 0
    assert runtime.health_calls == 0


def test_skill_runner_timeout_fails_closed_before_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(skill_runner_module.time, "monotonic", lambda: next(ticks))
    runtime = CountingRuntimeProvider(_trace())
    executor = ReadOnlyToolExecutor(runtime_provider=runtime)
    registry = build_stage7_ops_skill_registry(tool_registry=executor.registry)
    descriptor = registry.resolve("diagnose-latency")

    result = ReadOnlySkillRunner(skill_registry=registry, tool_executor=executor).run(
        "diagnose-latency",
        context=_context(),
        policy=SkillRunnerPolicy.for_skill(
            descriptor,
            authorization_token="task:skill:004",
            max_tool_calls=3,
            timeout_ms=1,
        ),
    )

    assert result.status_code == "M27_SKILL_RUN_TIMEOUT"
    assert result.tool_call_count == 0
    assert runtime.trace_calls == 0
    assert runtime.budget_calls == 0
    assert runtime.health_calls == 0
