from __future__ import annotations

import pytest

from knowledge_engine.m27_context_runtime_contracts import (
    EvidenceGapSummary,
    EvidenceIdentity,
    EvidencePlanningResult,
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
    new_trace_id,
)
from knowledge_engine.m27_readonly_tools import (
    ExistingResultEvidenceProvider,
    runtime_budget_view,
    runtime_health_view,
    runtime_trace_view,
)
from knowledge_engine.m27_tool_contracts import (
    EvidenceInspectInput,
    KnowledgeExpandOutput,
    KnowledgeItemRef,
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    RuntimeHealthInput,
    RuntimeLookupInput,
)
from knowledge_engine.m27_tool_executor import (
    ReadOnlyToolExecutor,
    ToolAuthorizationError,
    ToolExecutionPolicy,
    ToolProviderUnavailableError,
)


class FakeKnowledgeProvider:
    def __init__(self) -> None:
        self.search_count = 0
        self.expand_count = 0

    def search(self, request: KnowledgeSearchInput) -> KnowledgeSearchOutput:
        self.search_count += 1
        return KnowledgeSearchOutput(
            items=(KnowledgeItemRef("knowledge-1", "source-A", "loc-1", "passage"),),
            total_count=1,
        )

    def expand(self, request: object) -> KnowledgeExpandOutput:
        self.expand_count += 1
        return KnowledgeExpandOutput(
            items=(KnowledgeItemRef("knowledge-2", "source-B", "loc-2", "passage"),),
            total_count=1,
        )


class FakeRuntimeProvider:
    def __init__(self, event: DecisionTraceEvent) -> None:
        self.event = event

    def get_trace(self, request: RuntimeLookupInput) -> object:
        return runtime_trace_view(self.event)

    def get_budget(self, request: RuntimeLookupInput) -> object:
        return runtime_budget_view(self.event)

    def get_health(self, request: RuntimeHealthInput) -> object:
        return runtime_health_view({"freshness": "snapshot", "data": {"overall_status": "healthy"}})


def _trace() -> DecisionTraceEvent:
    return DecisionTraceEvent(
        trace_id=new_trace_id(),
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


def test_executor_invokes_authorized_read_only_provider() -> None:
    knowledge = FakeKnowledgeProvider()
    executor = ReadOnlyToolExecutor(knowledge_provider=knowledge)
    policy = ToolExecutionPolicy(
        authorized_capabilities=("knowledge.search",),
        authorization_token="task:tool:001",
    )

    result = executor.execute(
        "knowledge.search",
        KnowledgeSearchInput("task:tool:001"),
        policy=policy,
        authorization_token="task:tool:001",
    )

    assert result.record.capability_name == "knowledge.search"
    assert result.record.read_only is True
    assert result.record.supports_mutation is False
    assert result.record.exposes_raw_infra is False
    assert knowledge.search_count == 1


def test_executor_blocks_unauthorized_capability_before_provider_call() -> None:
    knowledge = FakeKnowledgeProvider()
    executor = ReadOnlyToolExecutor(knowledge_provider=knowledge)
    policy = ToolExecutionPolicy(
        authorized_capabilities=("knowledge.search",),
        authorization_token="task:tool:002",
    )

    with pytest.raises(ToolAuthorizationError):
        executor.execute(
            "knowledge.expand",
            KnowledgeSearchInput("task:tool:002"),
            policy=policy,
            authorization_token="task:tool:002",
        )
    assert knowledge.expand_count == 0


def test_executor_requires_matching_authorization_token() -> None:
    executor = ReadOnlyToolExecutor(knowledge_provider=FakeKnowledgeProvider())
    policy = ToolExecutionPolicy(
        authorized_capabilities=("knowledge.search",),
        authorization_token="task:tool:003",
    )

    with pytest.raises(ToolAuthorizationError):
        executor.execute(
            "knowledge.search",
            KnowledgeSearchInput("task:tool:003"),
            policy=policy,
            authorization_token="task:other",
        )


def test_executor_fails_closed_when_provider_missing() -> None:
    executor = ReadOnlyToolExecutor()
    policy = ToolExecutionPolicy(
        authorized_capabilities=("knowledge.search",),
        authorization_token="task:tool:004",
    )

    with pytest.raises(ToolProviderUnavailableError):
        executor.execute(
            "knowledge.search",
            KnowledgeSearchInput("task:tool:004"),
            policy=policy,
            authorization_token="task:tool:004",
        )


def test_executor_can_invoke_existing_evidence_and_runtime_views() -> None:
    event = _trace()
    executor = ReadOnlyToolExecutor(
        evidence_provider=ExistingResultEvidenceProvider(),
        runtime_provider=FakeRuntimeProvider(event),
    )
    policy = ToolExecutionPolicy(
        authorized_capabilities=("evidence.inspect", "runtime.get_budget", "runtime.get_trace"),
        authorization_token="task:tool:005",
    )

    inspected = executor.execute(
        "evidence.inspect",
        EvidenceInspectInput(_planning()),
        policy=policy,
        authorization_token="task:tool:005",
    )
    trace = executor.execute(
        "runtime.get_trace",
        RuntimeLookupInput(event.trace_id),
        policy=policy,
        authorization_token="task:tool:005",
    )

    assert inspected.record.capability_name == "evidence.inspect"
    assert trace.record.capability_name == "runtime.get_trace"
