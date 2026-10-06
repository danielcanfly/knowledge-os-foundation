from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .m27_learning_contracts import (
    LearningPolicyArea,
    LearningProposal,
    LearningProposalKind,
    LearningRiskClass,
    LearningSignal,
    LearningSignalKind,
    LearningSignalSource,
    validate_artifact_ids,
    validate_nonnegative_int,
    validate_reason_codes,
    validate_safe_code,
    validate_safe_token,
    validate_sanitized_learning_text,
)
from .m27_learning_runtime import LearningRuntime
from .m27_meta_harness_contracts import (
    MetaHarnessCandidate,
    MetaHarnessInput,
    MetaHarnessRiskClass,
)
from .m27_meta_harness_contracts import (
    validate_safe_token_tuple as validate_meta_token_tuple,
)
from .m27_meta_harness_runtime import MetaHarnessRuntime


class LearningMetaLoopError(RuntimeError):
    """Raised when the offline loop is asked to exceed review-only authority."""


class SanitizedObservationSource(StrEnum):
    RUNTIME_TRACE = "RUNTIME_TRACE"
    RUNTIME_BUDGET = "RUNTIME_BUDGET"
    RUNTIME_HEALTH = "RUNTIME_HEALTH"
    SMOKE_REPORT = "SMOKE_REPORT"
    ADMISSION_REPORT = "ADMISSION_REPORT"
    GATE_SUMMARY = "GATE_SUMMARY"
    EVAL_SUMMARY = "EVAL_SUMMARY"


class OfflineFailureClass(StrEnum):
    CITATION_GAP = "CITATION_GAP"
    LATENCY_BUDGET_EXCEEDED = "LATENCY_BUDGET_EXCEEDED"
    EMPTY_RETRIEVAL = "EMPTY_RETRIEVAL"
    EVIDENCE_BUNDLE_BRIDGE_GAP = "EVIDENCE_BUNDLE_BRIDGE_GAP"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    TOOL_POLICY_DENIAL = "TOOL_POLICY_DENIAL"
    MEMORY_AUTHORITY_BOUNDARY = "MEMORY_AUTHORITY_BOUNDARY"
    SMOKE_GATE_BLOCKED = "SMOKE_GATE_BLOCKED"
    GENERAL_OFFLINE_FAILURE = "GENERAL_OFFLINE_FAILURE"


_SOURCE_TO_SIGNAL_SOURCE = {
    SanitizedObservationSource.RUNTIME_TRACE: LearningSignalSource.RUNTIME_TRACE,
    SanitizedObservationSource.RUNTIME_BUDGET: LearningSignalSource.RUNTIME_BUDGET,
    SanitizedObservationSource.RUNTIME_HEALTH: LearningSignalSource.RUNTIME_HEALTH,
    SanitizedObservationSource.SMOKE_REPORT: LearningSignalSource.GATE_SUMMARY,
    SanitizedObservationSource.ADMISSION_REPORT: LearningSignalSource.GATE_SUMMARY,
    SanitizedObservationSource.GATE_SUMMARY: LearningSignalSource.GATE_SUMMARY,
    SanitizedObservationSource.EVAL_SUMMARY: LearningSignalSource.EVAL_SUMMARY,
}

_SOURCE_TO_SIGNAL_KIND = {
    SanitizedObservationSource.RUNTIME_TRACE: LearningSignalKind.TRACE_OBSERVATION,
    SanitizedObservationSource.RUNTIME_BUDGET: LearningSignalKind.BUDGET_OBSERVATION,
    SanitizedObservationSource.RUNTIME_HEALTH: LearningSignalKind.HEALTH_OBSERVATION,
    SanitizedObservationSource.SMOKE_REPORT: LearningSignalKind.GATE_SUMMARY,
    SanitizedObservationSource.ADMISSION_REPORT: LearningSignalKind.GATE_SUMMARY,
    SanitizedObservationSource.GATE_SUMMARY: LearningSignalKind.GATE_SUMMARY,
    SanitizedObservationSource.EVAL_SUMMARY: LearningSignalKind.EVAL_SUMMARY,
}

_FAILURE_POLICY_AREA = {
    OfflineFailureClass.CITATION_GAP: LearningPolicyArea.EVAL_GATE,
    OfflineFailureClass.LATENCY_BUDGET_EXCEEDED: LearningPolicyArea.COMPUTE,
    OfflineFailureClass.EMPTY_RETRIEVAL: LearningPolicyArea.RETRIEVAL,
    OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP: LearningPolicyArea.ROUTING,
    OfflineFailureClass.UNSUPPORTED_CLAIM: LearningPolicyArea.GUARDRAIL,
    OfflineFailureClass.TOOL_POLICY_DENIAL: LearningPolicyArea.ROUTING,
    OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY: LearningPolicyArea.MEMORY,
    OfflineFailureClass.SMOKE_GATE_BLOCKED: LearningPolicyArea.EVAL_GATE,
    OfflineFailureClass.GENERAL_OFFLINE_FAILURE: LearningPolicyArea.GUARDRAIL,
}

_FAILURE_PROPOSAL_KIND = {
    OfflineFailureClass.CITATION_GAP: LearningProposalKind.EVAL_GATE_CANDIDATE,
    OfflineFailureClass.LATENCY_BUDGET_EXCEEDED: LearningProposalKind.COMPUTE_POLICY_CANDIDATE,
    OfflineFailureClass.EMPTY_RETRIEVAL: LearningProposalKind.RETRIEVAL_POLICY_CANDIDATE,
    OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP: LearningProposalKind.ROUTING_POLICY_CANDIDATE,
    OfflineFailureClass.UNSUPPORTED_CLAIM: LearningProposalKind.GUARDRAIL_HARDENING_CANDIDATE,
    OfflineFailureClass.TOOL_POLICY_DENIAL: LearningProposalKind.ROUTING_POLICY_CANDIDATE,
    OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY: LearningProposalKind.MEMORY_POLICY_CANDIDATE,
    OfflineFailureClass.SMOKE_GATE_BLOCKED: LearningProposalKind.EVAL_GATE_CANDIDATE,
    OfflineFailureClass.GENERAL_OFFLINE_FAILURE: LearningProposalKind.GUARDRAIL_HARDENING_CANDIDATE,
}

_FAILURE_CANDIDATE_FILES = {
    OfflineFailureClass.CITATION_GAP: (
        "src/knowledge_engine/m27_context_evidence_boundary.py",
        "tests/test_m27_context_evidence_boundary.py",
    ),
    OfflineFailureClass.LATENCY_BUDGET_EXCEEDED: (
        "src/knowledge_engine/m27_adaptive_compute.py",
        "tests/test_m27_adaptive_compute.py",
    ),
    OfflineFailureClass.EMPTY_RETRIEVAL: (
        "src/knowledge_engine/m27_bounded_agentic_retrieval.py",
        "tests/test_m27_bounded_agentic_retrieval.py",
    ),
    OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP: (
        "src/knowledge_engine/m27_production_evidence_bridge.py",
        "tests/test_m27_production_evidence_bridge.py",
    ),
    OfflineFailureClass.UNSUPPORTED_CLAIM: (
        "src/knowledge_engine/m27_context_evidence_boundary.py",
        "tests/test_m27_context_evidence_boundary.py",
    ),
    OfflineFailureClass.TOOL_POLICY_DENIAL: (
        "src/knowledge_engine/m27_tool_executor.py",
        "tests/test_m27_tool_executor.py",
    ),
    OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY: (
        "src/knowledge_engine/m27_memory_activation.py",
        "tests/test_m27_memory_activation.py",
    ),
    OfflineFailureClass.SMOKE_GATE_BLOCKED: (
        "src/knowledge_engine/m27_isolated_admission_harness.py",
        "tests/test_m27_isolated_admission_harness.py",
    ),
    OfflineFailureClass.GENERAL_OFFLINE_FAILURE: (
        "src/knowledge_engine/m27_runtime_harness.py",
        "tests/test_m27_runtime_composition_eval.py",
    ),
}


@dataclass(frozen=True, slots=True)
class SanitizedOfflineObservation:
    """Sanitized telemetry/report summary accepted by the offline loop."""

    source: SanitizedObservationSource
    source_ref: str
    observed_class: str
    count: int = 1
    reason_codes: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    latency_p95_ms: int | None = None
    citation_rate_percent: int | None = None
    retrieval_empty_count: int = 0
    evidence_gap_count: int = 0
    gate_blocked: bool = False
    summary: str = "Sanitized offline observation."

    def __post_init__(self) -> None:
        if not isinstance(self.source, SanitizedObservationSource):
            raise LearningMetaLoopError("source must be SanitizedObservationSource")
        validate_safe_token("source_ref", self.source_ref)
        validate_safe_code("observed_class", self.observed_class)
        validate_nonnegative_int("count", self.count)
        validate_reason_codes(self.reason_codes)
        validate_artifact_ids(self.artifact_ids)
        validate_nonnegative_int("retrieval_empty_count", self.retrieval_empty_count)
        validate_nonnegative_int("evidence_gap_count", self.evidence_gap_count)
        if self.latency_p95_ms is not None:
            validate_nonnegative_int("latency_p95_ms", self.latency_p95_ms)
        if self.citation_rate_percent is not None:
            validate_nonnegative_int("citation_rate_percent", self.citation_rate_percent)
            if self.citation_rate_percent > 100:
                raise LearningMetaLoopError("citation_rate_percent must be <= 100")
        if not isinstance(self.gate_blocked, bool):
            raise LearningMetaLoopError("gate_blocked must be bool")
        validate_sanitized_learning_text("summary", self.summary)

    @property
    def normalized_reason_codes(self) -> tuple[str, ...]:
        return validate_reason_codes(self.reason_codes)

    @property
    def normalized_artifact_ids(self) -> tuple[str, ...]:
        return validate_artifact_ids(self.artifact_ids)

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source.value,
            "source_ref": self.source_ref,
            "observed_class": self.observed_class,
            "count": self.count,
            "reason_codes": list(self.normalized_reason_codes),
            "artifact_ids": list(self.normalized_artifact_ids),
            "latency_p95_ms": self.latency_p95_ms,
            "citation_rate_percent": self.citation_rate_percent,
            "retrieval_empty_count": self.retrieval_empty_count,
            "evidence_gap_count": self.evidence_gap_count,
            "gate_blocked": self.gate_blocked,
            "summary_present": bool(self.summary),
            "raw_payload_present": False,
        }


@dataclass(frozen=True, slots=True)
class FailureMiningResult:
    failure_class: OfflineFailureClass
    policy_area: LearningPolicyArea
    observations: tuple[SanitizedOfflineObservation, ...]
    aggregate_count: int
    source_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.failure_class, OfflineFailureClass):
            raise LearningMetaLoopError("failure_class must be OfflineFailureClass")
        if not isinstance(self.policy_area, LearningPolicyArea):
            raise LearningMetaLoopError("policy_area must be LearningPolicyArea")
        if not self.observations:
            raise LearningMetaLoopError("failure mining result requires observations")
        validate_nonnegative_int("aggregate_count", self.aggregate_count)
        validate_meta_token_tuple("source_refs", self.source_refs, allow_empty=False)
        validate_reason_codes(self.reason_codes)
        validate_artifact_ids(self.artifact_ids)

    def as_dict(self) -> dict[str, object]:
        return {
            "failure_class": self.failure_class.value,
            "policy_area": self.policy_area.value,
            "aggregate_count": self.aggregate_count,
            "source_refs": list(self.source_refs),
            "reason_codes": list(self.reason_codes),
            "artifact_ids": list(self.artifact_ids),
            "raw_payload_present": False,
        }


@dataclass(frozen=True, slots=True)
class LearningMetaLoopResult:
    mined_failures: tuple[FailureMiningResult, ...]
    learning_signals: tuple[LearningSignal, ...]
    learning_proposals: tuple[LearningProposal, ...]
    meta_harness_candidates: tuple[MetaHarnessCandidate, ...]

    @property
    def ready_for_review_count(self) -> int:
        return len(self.learning_proposals) + len(self.meta_harness_candidates)

    def as_dict(self) -> dict[str, object]:
        return {
            "mined_failures": [item.as_dict() for item in self.mined_failures],
            "learning_signals": [item.as_dict() for item in self.learning_signals],
            "learning_proposals": [item.as_dict() for item in self.learning_proposals],
            "meta_harness_candidates": [item.as_dict() for item in self.meta_harness_candidates],
            "ready_for_review_count": self.ready_for_review_count,
            "governance": learning_meta_loop_governance(),
        }


class OfflineLearningMetaHarnessLoop:
    """Governed offline loop from sanitized evidence to review-only candidates."""

    def __init__(
        self,
        *,
        learning_runtime: LearningRuntime | None = None,
        meta_harness_runtime: MetaHarnessRuntime | None = None,
    ) -> None:
        self._learning_runtime = learning_runtime or LearningRuntime()
        self._meta_harness_runtime = meta_harness_runtime or MetaHarnessRuntime()

    def run(self, observations: tuple[SanitizedOfflineObservation, ...]) -> LearningMetaLoopResult:
        if not isinstance(observations, tuple) or not observations:
            raise LearningMetaLoopError("offline loop requires sanitized observations")
        if any(not isinstance(item, SanitizedOfflineObservation) for item in observations):
            raise LearningMetaLoopError(
                "offline loop accepts SanitizedOfflineObservation values only"
            )

        mined = mine_failure_modes(observations)
        signals: list[LearningSignal] = []
        proposals: list[LearningProposal] = []
        candidates: list[MetaHarnessCandidate] = []
        for failure in mined:
            signal_ids: list[str] = []
            for observation in failure.observations:
                signal = observation_to_learning_signal(observation, failure.failure_class)
                self._learning_runtime.observe_signal(signal)
                signals.append(signal)
                signal_ids.append(signal.signal_id)
            proposal = self._learning_runtime.propose_from_signals(
                signal_ids=tuple(signal_ids),
                kind=_FAILURE_PROPOSAL_KIND[failure.failure_class],
                observed_issue_class=failure.failure_class.value,
                candidate_change_summary=candidate_change_summary_for_failure(
                    failure.failure_class
                ),
                expected_benefit_class=expected_benefit_for_failure(failure.failure_class),
                risk_class=risk_class_for_failure(failure.failure_class),
                required_gate=required_learning_gate_for_failure(failure.failure_class),
            )
            ready_proposal = self._learning_runtime.mark_proposal_ready_for_review(
                proposal.proposal_id
            )
            proposals.append(ready_proposal)

            input_metadata = MetaHarnessInput.create(
                source_refs=tuple(sorted(set(failure.source_refs + (proposal.proposal_id,)))),
                target_failure_class=failure.failure_class.value,
                reason_codes=failure.reason_codes,
                artifact_ids=failure.artifact_ids,
                eval_summary_count=sum(
                    item.count
                    for item in failure.observations
                    if item.source is SanitizedObservationSource.EVAL_SUMMARY
                ),
                gate_summary_count=sum(
                    item.count
                    for item in failure.observations
                    if item.source
                    in {
                        SanitizedObservationSource.GATE_SUMMARY,
                        SanitizedObservationSource.SMOKE_REPORT,
                        SanitizedObservationSource.ADMISSION_REPORT,
                    }
                ),
            )
            candidate = self._meta_harness_runtime.draft_eval_plan(
                input_metadata=input_metadata,
                candidate_summary=eval_plan_summary_for_failure(failure.failure_class),
                expected_improvement_class=expected_benefit_for_failure(failure.failure_class),
                risk_class=meta_risk_class_for_failure(failure.failure_class),
                candidate_files=_FAILURE_CANDIDATE_FILES[failure.failure_class],
                test_names=test_names_for_failure(failure.failure_class),
                gate_names=gate_names_for_failure(failure.failure_class),
            )
            ready_candidate = self._meta_harness_runtime.mark_candidate_ready_for_review(
                candidate.candidate_id
            )
            candidates.append(ready_candidate)

        return LearningMetaLoopResult(
            mined_failures=tuple(mined),
            learning_signals=tuple(sorted(signals, key=lambda item: item.signal_id)),
            learning_proposals=tuple(sorted(proposals, key=lambda item: item.proposal_id)),
            meta_harness_candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        )

    def render_review_packet(self, result: LearningMetaLoopResult) -> dict[str, object]:
        if not isinstance(result, LearningMetaLoopResult):
            raise LearningMetaLoopError("review packet requires LearningMetaLoopResult")
        return {
            "governance": learning_meta_loop_governance(),
            "mined_failures": [item.as_dict() for item in result.mined_failures],
            "learning_proposal_reports": [
                self._learning_runtime.render_proposal_report(item.proposal_id)
                for item in result.learning_proposals
            ],
            "meta_harness_reports": [
                self._meta_harness_runtime.render_meta_harness_report(item.candidate_id)
                for item in result.meta_harness_candidates
            ],
        }


def mine_failure_modes(
    observations: tuple[SanitizedOfflineObservation, ...],
) -> tuple[FailureMiningResult, ...]:
    buckets: dict[OfflineFailureClass, list[SanitizedOfflineObservation]] = {}
    for observation in observations:
        failure_class = classify_failure_mode(observation)
        buckets.setdefault(failure_class, []).append(observation)

    mined: list[FailureMiningResult] = []
    for failure_class in sorted(buckets, key=lambda item: item.value):
        items = tuple(sorted(buckets[failure_class], key=lambda item: item.source_ref))
        source_refs = tuple(sorted({item.source_ref for item in items}))
        reason_codes = validate_reason_codes(
            tuple(code for item in items for code in item.normalized_reason_codes)
        )
        artifact_ids = validate_artifact_ids(
            tuple(artifact for item in items for artifact in item.normalized_artifact_ids)
        )
        mined.append(
            FailureMiningResult(
                failure_class=failure_class,
                policy_area=_FAILURE_POLICY_AREA[failure_class],
                observations=items,
                aggregate_count=sum(item.count for item in items),
                source_refs=source_refs,
                reason_codes=reason_codes,
                artifact_ids=artifact_ids,
            )
        )
    return tuple(mined)


def classify_failure_mode(observation: SanitizedOfflineObservation) -> OfflineFailureClass:
    if not isinstance(observation, SanitizedOfflineObservation):
        raise LearningMetaLoopError("classify_failure_mode requires sanitized observation")
    observed = observation.observed_class
    reasons = set(observation.normalized_reason_codes)

    if observed in {"CITATION_GAP", "CITATION_RATE_BELOW_GATE"} or (
        observation.citation_rate_percent is not None and observation.citation_rate_percent < 95
    ):
        return OfflineFailureClass.CITATION_GAP
    if observed in {"P95_LATENCY_BREACH", "LATENCY_BUDGET_EXCEEDED"} or (
        observation.latency_p95_ms is not None and observation.latency_p95_ms > 15000
    ):
        return OfflineFailureClass.LATENCY_BUDGET_EXCEEDED
    if observed in {"EMPTY_RETRIEVAL", "NO_EVIDENCE_GAIN"} or observation.retrieval_empty_count > 0:
        return OfflineFailureClass.EMPTY_RETRIEVAL
    if (
        observed in {"EVIDENCE_BUNDLE_BRIDGE_GAP", "PROD_EVIDENCE_BRIDGE_GAP"}
        or observation.evidence_gap_count > 0
    ):
        return OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP
    if observed in {"UNSUPPORTED_CLAIM", "CLAIM_SUPPORT_GAP"}:
        return OfflineFailureClass.UNSUPPORTED_CLAIM
    if observed in {"TOOL_POLICY_DENIAL", "TOOL_ALLOWLIST_DENIAL"}:
        return OfflineFailureClass.TOOL_POLICY_DENIAL
    if observed in {"MEMORY_AUTHORITY_BOUNDARY", "MEMORY_EVIDENCE_DENIAL"}:
        return OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY
    if observation.gate_blocked or "GATE_BLOCKED" in reasons:
        return OfflineFailureClass.SMOKE_GATE_BLOCKED
    return OfflineFailureClass.GENERAL_OFFLINE_FAILURE


def observation_to_learning_signal(
    observation: SanitizedOfflineObservation,
    failure_class: OfflineFailureClass,
) -> LearningSignal:
    return LearningSignal.create(
        kind=_SOURCE_TO_SIGNAL_KIND[observation.source],
        source=_SOURCE_TO_SIGNAL_SOURCE[observation.source],
        source_ref=observation.source_ref,
        policy_area=_FAILURE_POLICY_AREA[failure_class],
        classification=failure_class.value,
        count=observation.count,
        reason_codes=observation.normalized_reason_codes,
        artifact_ids=observation.normalized_artifact_ids,
    )


def candidate_change_summary_for_failure(failure_class: OfflineFailureClass) -> str:
    if failure_class is OfflineFailureClass.CITATION_GAP:
        return "Review citation gate candidate before runtime change."
    if failure_class is OfflineFailureClass.LATENCY_BUDGET_EXCEEDED:
        return "Review compute budget candidate with offline latency evidence."
    if failure_class is OfflineFailureClass.EMPTY_RETRIEVAL:
        return "Review bounded retrieval fallback from sanitized empty signals."
    if failure_class is OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP:
        return "Review evidence bridge candidate with offline receipts only."
    if failure_class is OfflineFailureClass.UNSUPPORTED_CLAIM:
        return "Review claim-support guardrail before answer-path change."
    if failure_class is OfflineFailureClass.TOOL_POLICY_DENIAL:
        return "Review readonly tool-routing without widening authority."
    if failure_class is OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY:
        return "Review memory-boundary test preserving auxiliary authority."
    if failure_class is OfflineFailureClass.SMOKE_GATE_BLOCKED:
        return "Review smoke-gate diagnostic candidate before retry."
    return "Review bounded offline harness candidate for observed failure."


def eval_plan_summary_for_failure(failure_class: OfflineFailureClass) -> str:
    return (
        "Draft a metadata-only offline evaluation plan for "
        f"{failure_class.value.lower()} with human review before patching."
    )


def expected_benefit_for_failure(failure_class: OfflineFailureClass) -> str:
    benefits = {
        OfflineFailureClass.CITATION_GAP: "HIGHER_CITATION_GATE_SENSITIVITY",
        OfflineFailureClass.LATENCY_BUDGET_EXCEEDED: "LOWER_P95_LATENCY",
        OfflineFailureClass.EMPTY_RETRIEVAL: "LOWER_EMPTY_RETRIEVAL_RATE",
        OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP: "HIGHER_EVIDENCE_BRIDGE_COVERAGE",
        OfflineFailureClass.UNSUPPORTED_CLAIM: "LOWER_UNSUPPORTED_CLAIM_RATE",
        OfflineFailureClass.TOOL_POLICY_DENIAL: "HIGHER_TOOL_ROUTE_EXPLAINABILITY",
        OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY: "STRONGER_MEMORY_AUTHORITY_BOUNDARY",
        OfflineFailureClass.SMOKE_GATE_BLOCKED: "HIGHER_SMOKE_GATE_DIAGNOSTIC_POWER",
        OfflineFailureClass.GENERAL_OFFLINE_FAILURE: "HIGHER_OFFLINE_GATE_COVERAGE",
    }
    return benefits[failure_class]


def risk_class_for_failure(failure_class: OfflineFailureClass) -> LearningRiskClass:
    if failure_class in {
        OfflineFailureClass.EVIDENCE_BUNDLE_BRIDGE_GAP,
        OfflineFailureClass.UNSUPPORTED_CLAIM,
        OfflineFailureClass.MEMORY_AUTHORITY_BOUNDARY,
    }:
        return LearningRiskClass.HIGH
    if failure_class in {
        OfflineFailureClass.CITATION_GAP,
        OfflineFailureClass.EMPTY_RETRIEVAL,
        OfflineFailureClass.TOOL_POLICY_DENIAL,
        OfflineFailureClass.SMOKE_GATE_BLOCKED,
    }:
        return LearningRiskClass.MEDIUM
    return LearningRiskClass.LOW


def meta_risk_class_for_failure(failure_class: OfflineFailureClass) -> MetaHarnessRiskClass:
    learning_risk = risk_class_for_failure(failure_class)
    if learning_risk is LearningRiskClass.HIGH:
        return MetaHarnessRiskClass.HIGH
    if learning_risk is LearningRiskClass.MEDIUM:
        return MetaHarnessRiskClass.MEDIUM
    return MetaHarnessRiskClass.LOW


def required_learning_gate_for_failure(failure_class: OfflineFailureClass) -> str:
    return f"offline.{failure_class.value.lower().replace('_', '-')}.review.v1"


def test_names_for_failure(failure_class: OfflineFailureClass) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "learning-meta.contracts",
                f"learning-meta.{failure_class.value.lower().replace('_', '-')}",
            }
        )
    )


def gate_names_for_failure(failure_class: OfflineFailureClass) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "offline.human-review-required",
                "offline.no-auto-apply",
                required_learning_gate_for_failure(failure_class),
            }
        )
    )


def learning_meta_loop_governance() -> dict[str, bool | str]:
    return {
        "status": "REVIEW_ONLY_META_HARNESS_CANDIDATE",
        "sanitized_inputs_only": True,
        "raw_private_payload_allowed": False,
        "proposal_only": True,
        "candidate_only": True,
        "requires_human_review": True,
        "requires_offline_gate": True,
        "self_patching": False,
        "auto_apply": False,
        "auto_merge": False,
        "auto_promote": False,
        "production_write": False,
        "runtime_behavior_change": False,
        "release_authority": False,
        "deployment_authority": False,
    }


__all__ = [
    "LearningMetaLoopError",
    "SanitizedObservationSource",
    "OfflineFailureClass",
    "SanitizedOfflineObservation",
    "FailureMiningResult",
    "LearningMetaLoopResult",
    "OfflineLearningMetaHarnessLoop",
    "mine_failure_modes",
    "classify_failure_mode",
    "observation_to_learning_signal",
    "learning_meta_loop_governance",
]
