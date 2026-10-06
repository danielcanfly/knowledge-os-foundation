from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from .m27_compute_policy import RuleBasedComputePolicy
from .m27_context_orchestrator import (
    ContinuationDecision,
    M27ContextOrchestrator,
    M27RuntimePlan,
    M27RuntimeTask,
)
from .m27_context_runtime_contracts import EvidencePlanningResult, VerificationDecision
from .m27_decision_trace import (
    BudgetClass,
    ComputeTier,
    ContextSource,
    DecisionReasonCode,
    DecisionRoute,
    DecisionTraceEvent,
    GuardObservation,
    GuardOutcome,
    SafeAbstentionOutcome,
    StatusClass,
    TraceGuard,
    new_trace_id,
)
from .m27_evidence_planner import LegacyM26EvidencePlannerAdapter
from .m27_legacy_m26_adapters import (
    LegacyM26ContextCompilerAdapter,
    LegacyM26SemanticRoutingAdapter,
    LegacyM26VerifierAdapter,
)
from .m27_readonly_tools import (
    RuntimeProvider,
    runtime_budget_view,
    runtime_health_view,
    runtime_trace_view,
)
from .m27_skill_contracts import build_stage7_ops_skill_registry
from .m27_tool_contracts import RuntimeBudgetOutput, RuntimeHealthOutput, RuntimeTraceOutput
from .m27_tool_executor import (
    ReadOnlyToolExecutor,
    ToolExecutionPolicy,
    ToolExecutionRecord,
    request_for_capability,
)
from .m27_workspace_contracts import WorkspaceArtifactKind, WorkspaceId, WorkspaceScope
from .m27_workspace_store import WorkspaceStore


@dataclass(frozen=True, slots=True)
class M27RuntimeHarnessInput:
    task: M27RuntimeTask
    routing_signal: object
    budget_signal: object
    selected_evidence: Sequence[Mapping[str, object]] = ()
    requirements: Sequence[object] = ()
    support_classification: Sequence[Mapping[str, object]] | None = None
    endpoint_proof: Mapping[str, object] | None = None
    sufficiency_status: str | None = None
    compiled_output: Mapping[str, object] | None = None
    verification_output: Mapping[str, object] | None = None
    health_payload: Mapping[str, object] | None = None
    m27_enabled: bool = True
    executable_request: object | None = None


@dataclass(frozen=True, slots=True)
class M27RuntimeHarnessResult:
    status_code: str
    task_id: str
    plan: M27RuntimePlan | None
    workspace_id: str | None
    trace_event: DecisionTraceEvent | None
    tool_records: tuple[ToolExecutionRecord, ...]
    continuation_decision: ContinuationDecision | None
    memory_candidate_ids: tuple[str, ...]
    retained_memory_count: int
    learning_proposal_ids: tuple[str, ...]
    meta_candidate_ids: tuple[str, ...]
    production_touched: bool = False
    feature_off: bool = False
    execution_rounds: tuple[dict[str, object], ...] = ()
    answer: Mapping[str, object] | None = None
    verification: Mapping[str, object] | None = None
    terminal_reason: str | None = None

    def as_summary(self) -> dict[str, object]:
        return {
            "status_code": self.status_code,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "trace_id": self.trace_event.trace_id if self.trace_event is not None else None,
            "tool_records": [item.as_dict() for item in self.tool_records],
            "continuation_decision": (
                self.continuation_decision.as_dict()
                if self.continuation_decision is not None
                else None
            ),
            "memory_candidate_ids": list(self.memory_candidate_ids),
            "retained_memory_count": self.retained_memory_count,
            "learning_proposal_ids": list(self.learning_proposal_ids),
            "meta_candidate_ids": list(self.meta_candidate_ids),
            "production_touched": self.production_touched,
            "feature_off": self.feature_off,
            "execution_rounds": list(self.execution_rounds),
            "terminal_reason": self.terminal_reason,
        }


class ComposedRuntimeProvider(RuntimeProvider):
    def __init__(
        self,
        *,
        trace_event: DecisionTraceEvent,
        health_payload: Mapping[str, object],
    ) -> None:
        self._trace_event = trace_event
        self._health_payload = health_payload

    def get_trace(self, request: object) -> RuntimeTraceOutput:
        return runtime_trace_view(self._trace_event)

    def get_budget(self, request: object) -> RuntimeBudgetOutput:
        return runtime_budget_view(self._trace_event)

    def get_health(self, request: object) -> RuntimeHealthOutput:
        return runtime_health_view(self._health_payload)


class M27RuntimeHarness:
    """Minimal executable composition across Stage 1-12 primitives.

    The harness is isolated, dependency-injected, read-only for tools, and
    candidate-only for memory/learning/meta-harness outputs.
    """

    def __init__(
        self,
        *,
        workspace_store: WorkspaceStore,
        tool_executor: ReadOnlyToolExecutor,
        memory_runtime: object | None = None,
        learning_runtime: object | None = None,
        meta_harness_runtime: object | None = None,
        orchestrator: M27ContextOrchestrator | None = None,
    ) -> None:
        self._workspace_store = workspace_store
        self._tool_executor = tool_executor
        self._memory_runtime = memory_runtime
        self._learning_runtime = learning_runtime
        self._meta_harness_runtime = meta_harness_runtime
        self._skill_registry = build_stage7_ops_skill_registry(
            tool_registry=tool_executor.registry,
        )
        self._orchestrator = orchestrator or M27ContextOrchestrator(
            skill_registry=self._skill_registry,
        )
        self._routing_adapter = LegacyM26SemanticRoutingAdapter()
        self._compute_policy = RuleBasedComputePolicy()
        self._evidence_adapter = LegacyM26EvidencePlannerAdapter()
        self._compiler_adapter = LegacyM26ContextCompilerAdapter()
        self._verifier_adapter = LegacyM26VerifierAdapter()

    def run(self, runtime_input: M27RuntimeHarnessInput) -> M27RuntimeHarnessResult:
        if not runtime_input.m27_enabled:
            return M27RuntimeHarnessResult(
                status_code="M26_BASELINE_UNCHANGED",
                task_id=runtime_input.task.task_id,
                plan=None,
                workspace_id=None,
                trace_event=None,
                tool_records=(),
                continuation_decision=None,
                memory_candidate_ids=(),
                retained_memory_count=0,
                learning_proposal_ids=(),
                meta_candidate_ids=(),
                feature_off=True,
            )

        if runtime_input.executable_request is not None:
            return self._run_executable(runtime_input)

        plan = self._orchestrator.plan(runtime_input.task)
        workspace_id = WorkspaceId.from_safe_token(
            scope=WorkspaceScope.TASK,
            task_token=runtime_input.task.task_id,
        )
        self._workspace_store.create_workspace(
            workspace_id=workspace_id,
            scope=WorkspaceScope.TASK,
        )

        context_plan = self._routing_adapter.normalize(runtime_input.routing_signal)
        compute_observation = self._compute_policy.classify(runtime_input.budget_signal)
        evidence_result = self._evidence_adapter.normalize(
            selected_evidence=runtime_input.selected_evidence,
            requirements=runtime_input.requirements,
            support_classification=runtime_input.support_classification,
            endpoint_proof=runtime_input.endpoint_proof,
            sufficiency_status=runtime_input.sufficiency_status,
            reason_codes=plan.reason_codes,
        )
        self._compiler_adapter.normalize(runtime_input.compiled_output or {})
        verification = self._verifier_adapter.normalize(runtime_input.verification_output or {})

        trace = _trace_event(
            context_plan=context_plan,
            compute_observation=compute_observation,
            evidence_result=evidence_result,
            verification=verification,
            plan=plan,
        )
        runtime_provider = ComposedRuntimeProvider(
            trace_event=trace,
            health_payload=runtime_input.health_payload or _default_health_payload(),
        )
        executor = ReadOnlyToolExecutor(
            registry=self._tool_executor.registry,
            knowledge_provider=self._tool_executor._knowledge_provider,
            evidence_provider=self._tool_executor._evidence_provider,
            runtime_provider=runtime_provider,
        )
        tool_records = _execute_planned_tools(
            executor=executor,
            plan=plan,
            task=runtime_input.task,
            trace=trace,
            evidence_result=evidence_result,
            verification=verification,
        )

        continuation = self._orchestrator.continuation_decision(
            verification_status=str(verification.status),
            material_claim_support_verified=verification.material_claim_support_verified,
            citation_locator_valid=verification.citation_locator_valid,
            unsupported_accepted_claims=verification.unsupported_accepted_claims,
            safe_abstention=verification.safe_abstention,
            compute_observation=compute_observation,
            completed_rounds=0,
            tool_calls=len(tool_records),
            plan=plan,
        )

        memory_ids, retained_count = self._memory_step(
            task=runtime_input.task,
            plan=plan,
            trace=trace,
        )
        learning_ids = self._learning_step(trace=trace, workspace_id=workspace_id, plan=plan)
        meta_ids = self._meta_step(trace=trace, workspace_id=workspace_id, plan=plan)

        summary = {
            "status_code": "M27_RUNTIME_COMPOSED",
            "task_id": runtime_input.task.task_id,
            "trace_id": trace.trace_id,
            "capability_count": len(plan.tool_capabilities),
            "tool_records": [item.as_dict() for item in tool_records],
            "continuation": continuation.as_dict(),
            "memory_candidate_count": len(memory_ids),
            "learning_proposal_count": len(learning_ids),
            "meta_candidate_count": len(meta_ids),
            "production_touched": False,
        }
        self._workspace_store.write_json_artifact(
            workspace_id=workspace_id,
            kind=WorkspaceArtifactKind.DIAGNOSTIC,
            relative_path="runtime/summary.json",
            payload=summary,
        )
        self._workspace_store.record_checkpoint(
            workspace_id=workspace_id,
            checkpoint_id="runtime-composed",
            metadata={"status_code": "PASS", "tool_count": len(tool_records)},
        )

        return M27RuntimeHarnessResult(
            status_code="M27_RUNTIME_COMPOSED",
            task_id=runtime_input.task.task_id,
            plan=plan,
            workspace_id=workspace_id.value,
            trace_event=trace,
            tool_records=tool_records,
            continuation_decision=continuation,
            memory_candidate_ids=memory_ids,
            retained_memory_count=retained_count,
            learning_proposal_ids=learning_ids,
            meta_candidate_ids=meta_ids,
        )

    def _run_executable(self, runtime_input: M27RuntimeHarnessInput) -> M27RuntimeHarnessResult:
        from .m27_runtime_execution import M27ExecutableRequest, execute_isolated

        request = runtime_input.executable_request
        if not isinstance(request, M27ExecutableRequest):
            raise TypeError("executable_request must be M27ExecutableRequest")
        if not isinstance(runtime_input.budget_signal, Mapping):
            raise TypeError("executable execution requires explicit budget mapping")
        plan = self._orchestrator.plan(runtime_input.task)
        context_plan = self._routing_adapter.normalize(runtime_input.routing_signal)
        compute_observation = self._compute_policy.classify(runtime_input.budget_signal)
        executed = execute_isolated(
            request=request,
            task=runtime_input.task,
            plan=plan,
            budget_signal=runtime_input.budget_signal,
            executor=self._tool_executor,
            store=self._workspace_store,
        )
        rounds = tuple(executed["rounds"])
        verification_output = dict(executed["verification"])
        successful = executed["status_code"] == "M27_RUNTIME_COMPOSED"
        verification_output["status"] = (
            "verified_answer" if successful else "owner_only_safe_abstention"
        )
        verification_output["safe_abstention"] = not successful
        verification_output["terminal_status"] = "answered" if successful else "safe_abstention"
        evidence_result = self._evidence_adapter.normalize(
            selected_evidence=executed["evidence_identities"],
            reason_codes=plan.reason_codes,
        )
        verification = self._verifier_adapter.normalize(verification_output)
        trace = _trace_event(
            context_plan=context_plan,
            compute_observation=compute_observation,
            evidence_result=evidence_result,
            verification=verification,
            plan=plan,
        )
        workspace_id = WorkspaceId.from_safe_token(
            scope=WorkspaceScope.TASK, task_token=runtime_input.task.task_id
        )
        memory_ids, retained_count = self._memory_step(
            task=runtime_input.task, plan=plan, trace=trace
        )
        learning_ids = self._learning_step(trace=trace, workspace_id=workspace_id, plan=plan)
        meta_ids = self._meta_step(trace=trace, workspace_id=workspace_id, plan=plan)
        continuation = self._orchestrator.continuation_decision(
            verification_status=str(verification.status),
            material_claim_support_verified=verification.material_claim_support_verified,
            citation_locator_valid=verification.citation_locator_valid,
            unsupported_accepted_claims=verification.unsupported_accepted_claims,
            safe_abstention=verification.safe_abstention,
            compute_observation=compute_observation,
            completed_rounds=max(0, len(rounds) - 1),
            tool_calls=len(executed["tool_records"]),
            plan=plan,
        )
        return M27RuntimeHarnessResult(
            status_code=str(executed["status_code"]),
            task_id=runtime_input.task.task_id,
            plan=plan,
            workspace_id=str(executed["workspace_id"]),
            trace_event=trace,
            tool_records=tuple(executed["tool_records"]),
            continuation_decision=continuation,
            memory_candidate_ids=memory_ids,
            retained_memory_count=retained_count,
            learning_proposal_ids=learning_ids,
            meta_candidate_ids=meta_ids,
            execution_rounds=rounds,
            answer=executed["answer"],
            verification=executed["verification"],
            terminal_reason=str(executed["terminal_reason"]),
        )

    def _memory_step(
        self,
        *,
        task: M27RuntimeTask,
        plan: M27RuntimePlan,
        trace: DecisionTraceEvent,
    ) -> tuple[tuple[str, ...], int]:
        if self._memory_runtime is None or not plan.memory_read_enabled:
            return (), 0
        retained = self._memory_runtime.list_retained_candidates(scope_token=task.task_id)
        candidate = self._memory_runtime.propose_candidate(
            memory_class="PROJECT",
            scope_token=task.task_id,
            summary="Runtime composition produced sanitized decision metadata only.",
            provenance=_memory_contract("MemoryProvenance")(
                origin_kind=_memory_contract("MemoryOriginKind").TRACE_SUMMARY,
                origin_ref=trace.trace_id,
            ),
            tags=("composition", "runtime"),
        )
        return (candidate.memory_id.value,), len(retained)

    def _learning_step(
        self,
        *,
        trace: DecisionTraceEvent,
        workspace_id: WorkspaceId,
        plan: M27RuntimePlan,
    ) -> tuple[str, ...]:
        if self._learning_runtime is None:
            return ()
        signal = _learning_contract("LearningSignal").create(
            kind=_learning_contract("LearningSignalKind").TRACE_OBSERVATION,
            source=_learning_contract("LearningSignalSource").DECISION_TRACE,
            source_ref=trace.trace_id,
            policy_area=_learning_contract("LearningPolicyArea").ROUTING,
            classification="RUNTIME_COMPOSITION",
            count=1,
            reason_codes=tuple(code for code in plan.reason_codes if code.isupper()),
            artifact_ids=(workspace_id.value,),
        )
        self._learning_runtime.observe_signal(signal)
        proposal = self._learning_runtime.propose_from_signals(
            signal_ids=(signal.signal_id,),
            kind=_learning_contract("LearningProposalKind").ROUTING_POLICY_CANDIDATE,
            observed_issue_class="RUNTIME_COMPOSITION",
            candidate_change_summary=(
                "Review runtime composition policy from sanitized signal metadata only."
            ),
            expected_benefit_class="BOUNDARY_CLARITY",
            risk_class=_learning_contract("LearningRiskClass").LOW,
            required_gate="offline-runtime-composition-gate",
        )
        return (proposal.proposal_id,)

    def _meta_step(
        self,
        *,
        trace: DecisionTraceEvent,
        workspace_id: WorkspaceId,
        plan: M27RuntimePlan,
    ) -> tuple[str, ...]:
        if self._meta_harness_runtime is None:
            return ()
        metadata = _meta_contract("MetaHarnessInput").create(
            source_refs=(trace.trace_id,),
            target_failure_class="RUNTIME_COMPOSITION",
            reason_codes=tuple(code for code in plan.reason_codes if code.isupper()),
            artifact_ids=(workspace_id.value,),
            eval_summary_count=1,
            gate_summary_count=1,
        )
        candidate = self._meta_harness_runtime.draft_eval_plan(
            input_metadata=metadata,
            candidate_summary="Review runtime composition harness metadata in offline gate only.",
            expected_improvement_class="COMPOSITION_COVERAGE",
            risk_class=_meta_contract("MetaHarnessRiskClass").LOW,
            candidate_files=("src/knowledge_engine/m27_runtime_harness.py",),
            test_names=("test_m27_runtime_composition_eval.py",),
            gate_names=("offline-runtime-composition-gate",),
        )
        return (candidate.candidate_id,)


def _stage_module(segment: str):
    return import_module(f"{__package__}.m27_{segment}")


def _memory_contract(name: str):
    return getattr(_stage_module("memory_contracts"), name)


def _learning_contract(name: str):
    return getattr(_stage_module("learning_contracts"), name)


def _meta_contract(name: str):
    return getattr(_stage_module("meta_harness_contracts"), name)


def _execute_planned_tools(
    *,
    executor: ReadOnlyToolExecutor,
    plan: M27RuntimePlan,
    task: M27RuntimeTask,
    trace: DecisionTraceEvent,
    evidence_result: EvidencePlanningResult,
    verification: VerificationDecision,
) -> tuple[ToolExecutionRecord, ...]:
    if not plan.tool_capabilities:
        return ()
    allowed = plan.tool_capabilities[: plan.max_tool_calls]
    policy = ToolExecutionPolicy(
        authorized_capabilities=allowed,
        authorization_token=task.task_id,
    )
    records: list[ToolExecutionRecord] = []
    for capability in allowed:
        request = request_for_capability(
            capability,
            request_token=task.request_token,
            trace_id=trace.trace_id,
            evidence_planning_result=evidence_result,
            verification_decision=verification,
        )
        result = executor.execute(
            capability,
            request,
            policy=policy,
            authorization_token=task.task_id,
        )
        records.append(result.record)
    return tuple(records)


def _trace_event(
    *,
    context_plan: object,
    compute_observation: object,
    evidence_result: EvidencePlanningResult,
    verification: VerificationDecision,
    plan: M27RuntimePlan,
) -> DecisionTraceEvent:
    citation_valid = verification.citation_locator_valid is True
    safe_abstention = verification.safe_abstention is True
    return DecisionTraceEvent(
        trace_id=new_trace_id(),
        route=_route(getattr(context_plan, "route", "")),
        reason_code=_reason_code(evidence_result, verification),
        compute_tier=getattr(compute_observation, "shadow_compute_tier", ComputeTier.LEGACY_M26),
        deadline_budget_class=getattr(
            compute_observation,
            "deadline_budget_class",
            BudgetClass.UNAVAILABLE_IN_STAGE1,
        ),
        provider_budget_class=getattr(
            compute_observation,
            "provider_budget_class",
            BudgetClass.UNAVAILABLE_IN_STAGE1,
        ),
        provider_attempt_count=_provider_attempt_count(compute_observation),
        context_sources=_trace_context_sources(plan),
        evidence_count=evidence_result.selected_evidence_count,
        citation_count=_count_or_zero(verification.citation_count),
        status_class=_status_class(verification),
        safe_abstention_outcome=(
            SafeAbstentionOutcome.ABSTAINED
            if safe_abstention
            else SafeAbstentionOutcome.DID_NOT_ABSTAIN
        ),
        guard_outcomes=(
            GuardObservation(
                guard=TraceGuard.CITATION_BINDING,
                outcome=GuardOutcome.PASSED if citation_valid else GuardOutcome.BLOCKED,
            ),
        ),
    )


def _route(value: object) -> DecisionRoute:
    if isinstance(value, str):
        try:
            return DecisionRoute(value)
        except ValueError:
            return DecisionRoute.UNAVAILABLE_IN_STAGE1
    return DecisionRoute.UNAVAILABLE_IN_STAGE1


def _reason_code(
    evidence_result: EvidencePlanningResult,
    verification: VerificationDecision,
) -> DecisionReasonCode:
    if evidence_result.gap.reason_codes:
        return DecisionReasonCode.EVIDENCE_GAP
    if verification.citation_locator_valid is False:
        return DecisionReasonCode.CITATION_GAP
    if verification.material_claim_support_verified is False:
        return DecisionReasonCode.CLAIM_SUPPORT_GAP
    return DecisionReasonCode.ROUTE_SELECTED


def _trace_context_sources(plan: M27RuntimePlan) -> tuple[ContextSource, ...]:
    sources: list[ContextSource] = []
    for source in plan.context_sources:
        name = source.value
        if name == "KNOWLEDGE":
            sources.append(ContextSource.LEXICAL)
        elif name == "TOOL":
            sources.append(ContextSource.CONTEXT_COMPILER)
        elif name == "SKILL":
            sources.append(ContextSource.PRODUCTION_BUNDLE)
        elif name == "MEMORY_CANDIDATE":
            sources.append(ContextSource.IDENTIFIER)
    return tuple(dict.fromkeys(sources)) or (ContextSource.UNAVAILABLE_IN_STAGE1,)


def _status_class(verification: VerificationDecision) -> StatusClass:
    if verification.safe_abstention is True:
        return StatusClass.SAFE_ABSTENTION
    status = str(verification.status).lower()
    if "error" in status:
        return StatusClass.ERROR
    return StatusClass.CITED_ANSWER


def _provider_attempt_count(compute_observation: object) -> int | None:
    value = getattr(compute_observation, "provider_attempts_remaining", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _count_or_zero(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _default_health_payload() -> dict[str, object]:
    return {
        "freshness": "snapshot",
        "data": {"overall_status": "healthy", "dependencies": []},
    }


def isolated_runtime_for_tests(
    root: Path,
    tool_executor: ReadOnlyToolExecutor,
) -> M27RuntimeHarness:
    workspace_store = WorkspaceStore(root=root / "workspace")
    return M27RuntimeHarness(workspace_store=workspace_store, tool_executor=tool_executor)


__all__ = [
    "M27RuntimeHarnessInput",
    "M27RuntimeHarnessResult",
    "ComposedRuntimeProvider",
    "M27RuntimeHarness",
    "isolated_runtime_for_tests",
]
