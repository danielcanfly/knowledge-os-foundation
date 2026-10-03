from __future__ import annotations

import json

from knowledge_engine.m27_context_runtime_contracts import (
    STAGE1_UNAVAILABLE,
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
    GuardObservation,
    GuardOutcome,
    SafeAbstentionOutcome,
    StatusClass,
    TraceGuard,
    new_trace_id,
)
from knowledge_engine.m27_readonly_tools import (
    EvidenceProvider,
    ExistingResultEvidenceProvider,
    KnowledgeProvider,
    RuntimeProvider,
    evidence_inspection_view,
    runtime_budget_view,
    runtime_health_view,
    runtime_trace_view,
    verification_inspection_view,
)
from knowledge_engine.m27_tool_contracts import (
    EvidenceInspectInput,
    EvidenceVerifyInput,
    KnowledgeExpandInput,
    KnowledgeExpandOutput,
    KnowledgeItemRef,
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    RuntimeBudgetOutput,
    RuntimeHealthInput,
    RuntimeHealthOutput,
    RuntimeLookupInput,
    RuntimeTraceOutput,
)


def _planning() -> EvidencePlanningResult:
    return EvidencePlanningResult(
        selected_evidence=(
            EvidenceIdentity(
                evidence_id="ev-01",
                passage_id="p-01",
                source_identity="source-A",
                locator_id="loc-01",
                evidence_type="passage",
            ),
        ),
        selected_evidence_count=1,
        selected_evidence_ids=("ev-01",),
        selected_passage_ids=("p-01",),
        source_identities=("source-A",),
        distinct_source_count=1,
        locator_ids=("loc-01",),
        requirement_ids=("req-01", "req-02"),
        gap=EvidenceGapSummary(
            covered_requirement_ids=("req-01",),
            missing_requirement_ids=("req-02",),
            coverage_status="gap_present",
            sufficiency_status="partially_sufficient",
            recovered_requirement_ids=(),
            bounded_recovery_used=False,
            reason_codes=("EVIDENCE_GAP",),
        ),
    )


def _verification() -> VerificationDecision:
    return VerificationDecision(
        status="verified_answer",
        terminal_status="answered",
        safe_abstention=False,
        reason_codes=("SUPPORT_VERIFIED", "bad code with spaces"),
        provider_call_count=1,
        material_claim_support_verified=True,
        citation_locator_valid=True,
        unsupported_accepted_claims=0,
        repair_attempted=False,
        citation_count=2,
        answer_source="strict_evidence_bound",
    )


def _trace() -> DecisionTraceEvent:
    return DecisionTraceEvent(
        trace_id=new_trace_id(),
        route=DecisionRoute.SEMANTIC_CLOSURE,
        reason_code=DecisionReasonCode.EVIDENCE_GAP,
        compute_tier=ComputeTier.STANDARD,
        deadline_budget_class=BudgetClass.CONSTRAINED,
        provider_budget_class=BudgetClass.HEALTHY,
        provider_attempt_count=1,
        context_sources=(ContextSource.LEXICAL, ContextSource.DENSE),
        evidence_count=4,
        citation_count=2,
        status_class=StatusClass.CITED_ANSWER,
        safe_abstention_outcome=SafeAbstentionOutcome.DID_NOT_ABSTAIN,
        guard_outcomes=(
            GuardObservation(
                guard=TraceGuard.CITATION_BINDING,
                outcome=GuardOutcome.PASSED,
            ),
        ),
    )


def test_evidence_inspection_reuses_stage3_identity_and_gap_metadata_only() -> None:
    output = evidence_inspection_view(_planning())
    serialized = json.dumps(output, default=repr, sort_keys=True)

    assert output.selected_evidence_count == 1
    assert output.distinct_source_count == 1
    assert output.requirement_count == 2
    assert output.covered_requirement_count == 1
    assert output.missing_requirement_count == 1
    assert output.coverage_status == "gap_present"
    assert "PRIVATE EVIDENCE BODY" not in serialized


def test_evidence_verify_inspects_existing_decision_without_answer_body() -> None:
    output = verification_inspection_view(_verification())
    serialized = json.dumps(output, default=repr, sort_keys=True)

    assert output.material_claim_support_verified is True
    assert output.citation_locator_valid is True
    assert output.unsupported_accepted_claims == 0
    assert output.reason_codes == ("SUPPORT_VERIFIED",)
    assert "answer" not in output.__dataclass_fields__
    assert "PRIVATE ANSWER" not in serialized


def test_existing_result_evidence_provider_is_pure_typed_adapter() -> None:
    provider = ExistingResultEvidenceProvider()

    inspected = provider.inspect(EvidenceInspectInput(_planning()))
    verified = provider.verify(EvidenceVerifyInput(_verification()))

    assert isinstance(provider, EvidenceProvider)
    assert inspected.selected_evidence_count == 1
    assert verified.status == "verified_answer"


def test_runtime_trace_and_budget_views_use_only_sanitized_trace_shape() -> None:
    event = _trace()

    trace = runtime_trace_view(event)
    budget = runtime_budget_view(event)

    assert isinstance(trace, RuntimeTraceOutput)
    assert isinstance(budget, RuntimeBudgetOutput)
    assert trace.trace_id == event.trace_id
    assert trace.evidence_count == 4
    assert budget.compute_tier == "STANDARD"
    assert budget.provider_attempt_count == 1


def test_runtime_health_view_drops_private_control_plane_and_identity_detail() -> None:
    payload = {
        "request_id": "req-secret",
        "freshness": "near_live",
        "data": {
            "overall_status": "healthy",
            "dependencies": [
                {
                    "key": "backend",
                    "status": "healthy",
                    "freshness": "live",
                    "detail": "PRIVATE ENDPOINT https://internal.example",
                    "expected": "secret-expected",
                    "observed": "secret-observed",
                },
                {
                    "key": "qdrant",
                    "status": "healthy",
                    "freshness": "near_live",
                    "detail": "PRIVATE COLLECTION INTERNALS",
                },
            ],
            "maintenance": {
                "filesystem_path": "/private/path",
                "docker": "control",
            },
        },
        "provenance": {"resource_identity": {"private": "value"}},
    }

    output = runtime_health_view(payload)
    serialized = json.dumps(output, default=repr, sort_keys=True)

    assert output.overall_status == "healthy"
    assert output.dependency_count == 2
    assert [item.key for item in output.dependencies] == ["backend", "qdrant"]
    for marker in (
        "req-secret",
        "PRIVATE ENDPOINT",
        "secret-expected",
        "secret-observed",
        "PRIVATE COLLECTION INTERNALS",
        "/private/path",
        "control",
    ):
        assert marker not in serialized


def test_provider_protocols_allow_dependency_injected_fake_only() -> None:
    class FakeKnowledgeProvider:
        def search(self, request: KnowledgeSearchInput) -> KnowledgeSearchOutput:
            assert request.request_token == "fixture:req-01"
            return KnowledgeSearchOutput(
                items=(KnowledgeItemRef("kn-01", "source-A", "loc-01", "passage"),),
                total_count=1,
            )

        def expand(self, request: KnowledgeExpandInput) -> KnowledgeExpandOutput:
            assert request.seed_ids == ("kn-01",)
            return KnowledgeExpandOutput(
                items=(KnowledgeItemRef("kn-02", "source-B", "loc-02", "passage"),),
                total_count=1,
            )

    class FakeRuntimeProvider:
        def get_trace(self, request: RuntimeLookupInput) -> RuntimeTraceOutput:
            assert request.trace_id == "trace-01"
            return runtime_trace_view(_trace())

        def get_budget(self, request: RuntimeLookupInput) -> RuntimeBudgetOutput:
            assert request.trace_id == "trace-01"
            return runtime_budget_view(_trace())

        def get_health(self, request: RuntimeHealthInput) -> RuntimeHealthOutput:
            assert request.scope == "runtime"
            return runtime_health_view(
                {"freshness": "unknown", "data": {"overall_status": "unknown"}}
            )

    assert isinstance(FakeKnowledgeProvider(), KnowledgeProvider)
    assert isinstance(FakeRuntimeProvider(), RuntimeProvider)


def test_runtime_and_evidence_outputs_do_not_contain_raw_private_payload_fields() -> None:
    outputs = (
        evidence_inspection_view(_planning()),
        verification_inspection_view(_verification()),
        runtime_trace_view(_trace()),
        runtime_budget_view(_trace()),
        runtime_health_view(
            {
                "freshness": "unknown",
                "data": {"overall_status": "unknown", "dependencies": []},
            }
        ),
    )

    serialized = json.dumps(outputs, default=repr, sort_keys=True)
    for forbidden in (
        "raw_query",
        "raw_answer",
        "full_evidence",
        "full_source",
        "credential",
        "api_key",
        "environment_value",
        "filesystem_path",
        "http_endpoint",
    ):
        assert forbidden not in serialized


def test_unavailable_verification_fields_remain_explicit() -> None:
    decision = VerificationDecision(
        status=STAGE1_UNAVAILABLE,
        terminal_status=STAGE1_UNAVAILABLE,
        safe_abstention=STAGE1_UNAVAILABLE,
        reason_codes=(),
        provider_call_count=STAGE1_UNAVAILABLE,
        material_claim_support_verified=STAGE1_UNAVAILABLE,
        citation_locator_valid=STAGE1_UNAVAILABLE,
        unsupported_accepted_claims=STAGE1_UNAVAILABLE,
        repair_attempted=STAGE1_UNAVAILABLE,
        citation_count=STAGE1_UNAVAILABLE,
        answer_source=STAGE1_UNAVAILABLE,
    )

    output = verification_inspection_view(decision)

    assert output.status == STAGE1_UNAVAILABLE
    assert output.safe_abstention == STAGE1_UNAVAILABLE
    assert output.citation_count == STAGE1_UNAVAILABLE
