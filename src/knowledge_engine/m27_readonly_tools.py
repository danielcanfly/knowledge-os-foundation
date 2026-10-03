from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from .m27_context_runtime_contracts import (
    STAGE1_UNAVAILABLE,
    STAGE3_UNAVAILABLE,
    EvidencePlanningResult,
    VerificationDecision,
)
from .m27_decision_trace import DecisionTraceEvent
from .m27_tool_contracts import (
    EvidenceInspectInput,
    EvidenceInspectOutput,
    EvidenceVerifyInput,
    EvidenceVerifyOutput,
    KnowledgeExpandInput,
    KnowledgeExpandOutput,
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    RuntimeBudgetOutput,
    RuntimeHealthDependency,
    RuntimeHealthInput,
    RuntimeHealthOutput,
    RuntimeLookupInput,
    RuntimeTraceOutput,
)

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_ALLOWED_HEALTH_STATUS = frozenset(
    {
        "healthy",
        "degraded",
        "warning",
        "failed",
        "error",
        "unavailable",
        "read_only",
        "unknown",
    }
)
_ALLOWED_FRESHNESS = frozenset(
    {"live", "near_live", "delayed", "snapshot", "stale", "unknown"}
)


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Injected domain provider boundary.

    Stage 5 ships no live implementation. A later stage may provide a read-only
    implementation after policy/authorization has been evaluated outside this
    provider boundary.
    """

    def search(self, request: KnowledgeSearchInput) -> KnowledgeSearchOutput: ...

    def expand(self, request: KnowledgeExpandInput) -> KnowledgeExpandOutput: ...


@runtime_checkable
class EvidenceProvider(Protocol):
    """Injected evidence capability boundary over already-produced decisions."""

    def inspect(self, request: EvidenceInspectInput) -> EvidenceInspectOutput: ...

    def verify(self, request: EvidenceVerifyInput) -> EvidenceVerifyOutput: ...


@runtime_checkable
class RuntimeProvider(Protocol):
    """Injected runtime metadata boundary; no process/control-plane authority."""

    def get_trace(self, request: RuntimeLookupInput) -> RuntimeTraceOutput: ...

    def get_budget(self, request: RuntimeLookupInput) -> RuntimeBudgetOutput: ...

    def get_health(self, request: RuntimeHealthInput) -> RuntimeHealthOutput: ...


class ExistingResultEvidenceProvider:
    """Pure adapter over already-produced Stage 1/3 domain objects."""

    def inspect(self, request: EvidenceInspectInput) -> EvidenceInspectOutput:
        return evidence_inspection_view(request.planning_result)

    def verify(self, request: EvidenceVerifyInput) -> EvidenceVerifyOutput:
        return verification_inspection_view(request.verification_decision)


def evidence_inspection_view(
    planning: EvidencePlanningResult,
) -> EvidenceInspectOutput:
    gap = planning.gap
    return EvidenceInspectOutput(
        selected_evidence=planning.selected_evidence,
        selected_evidence_count=planning.selected_evidence_count,
        distinct_source_count=_count_or_marker(planning.distinct_source_count),
        requirement_count=_tuple_count_or_marker(planning.requirement_ids),
        covered_requirement_count=_tuple_count_or_marker(
            gap.covered_requirement_ids
        ),
        missing_requirement_count=_tuple_count_or_marker(
            gap.missing_requirement_ids
        ),
        coverage_status=_safe_code(gap.coverage_status, STAGE3_UNAVAILABLE),
        sufficiency_status=_safe_code(
            gap.sufficiency_status,
            STAGE3_UNAVAILABLE,
        ),
        bounded_recovery_used=(
            gap.bounded_recovery_used
            if isinstance(gap.bounded_recovery_used, bool)
            else STAGE3_UNAVAILABLE
        ),
        reason_codes=_safe_reason_codes(gap.reason_codes),
    )


def verification_inspection_view(
    decision: VerificationDecision,
) -> EvidenceVerifyOutput:
    return EvidenceVerifyOutput(
        status=_safe_code(decision.status, STAGE1_UNAVAILABLE),
        terminal_status=_safe_code(
            decision.terminal_status,
            STAGE1_UNAVAILABLE,
        ),
        safe_abstention=_bool_or_marker(decision.safe_abstention),
        material_claim_support_verified=_bool_or_marker(
            decision.material_claim_support_verified
        ),
        citation_locator_valid=_bool_or_marker(decision.citation_locator_valid),
        unsupported_accepted_claims=_count_or_marker(
            decision.unsupported_accepted_claims
        ),
        repair_attempted=_bool_or_marker(decision.repair_attempted),
        citation_count=_count_or_marker(decision.citation_count),
        reason_codes=_safe_reason_codes(decision.reason_codes),
    )


def runtime_trace_view(event: DecisionTraceEvent) -> RuntimeTraceOutput:
    return RuntimeTraceOutput(
        trace_id=event.trace_id,
        route=event.route.value,
        reason_code=event.reason_code.value,
        compute_tier=event.compute_tier.value,
        deadline_budget_class=event.deadline_budget_class.value,
        provider_budget_class=event.provider_budget_class.value,
        provider_attempt_count=event.provider_attempt_count,
        context_sources=tuple(item.value for item in event.context_sources),
        evidence_count=event.evidence_count,
        citation_count=event.citation_count,
        status_class=event.status_class.value,
        safe_abstention_outcome=event.safe_abstention_outcome.value,
        guard_outcomes=tuple(
            (item.guard.value, item.outcome.value) for item in event.guard_outcomes
        ),
    )


def runtime_budget_view(event: DecisionTraceEvent) -> RuntimeBudgetOutput:
    return RuntimeBudgetOutput(
        trace_id=event.trace_id,
        compute_tier=event.compute_tier.value,
        deadline_budget_class=event.deadline_budget_class.value,
        provider_budget_class=event.provider_budget_class.value,
        provider_attempt_count=event.provider_attempt_count,
        provider_attempt_class=event.provider_attempt_class.value,
    )


def runtime_health_view(payload: Mapping[str, object]) -> RuntimeHealthOutput:
    """Reduce an already-produced health payload to domain-level safe metadata.

    Request IDs, maintenance details, expected/observed values, backend identities,
    paths, endpoints, credentials and raw dependency detail are intentionally
    discarded.
    """

    data = payload.get("data")
    data_mapping = data if isinstance(data, Mapping) else {}

    raw_overall = data_mapping.get("overall_status")
    overall_status = (
        raw_overall
        if isinstance(raw_overall, str) and raw_overall in _ALLOWED_HEALTH_STATUS
        else "unknown"
    )

    raw_freshness = payload.get("freshness")
    freshness = (
        raw_freshness
        if isinstance(raw_freshness, str) and raw_freshness in _ALLOWED_FRESHNESS
        else "unknown"
    )

    dependencies = _health_dependencies(data_mapping.get("dependencies"))
    return RuntimeHealthOutput(
        overall_status=overall_status,
        freshness=freshness,
        dependency_count=len(dependencies),
        dependencies=dependencies,
    )


def _health_dependencies(value: object) -> tuple[RuntimeHealthDependency, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()

    result: list[RuntimeHealthDependency] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        key = item.get("key")
        status = item.get("status")
        freshness = item.get("freshness")
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key)
        ):
            continue
        normalized_status = (
            status
            if isinstance(status, str) and status in _ALLOWED_HEALTH_STATUS
            else "unknown"
        )
        normalized_freshness = (
            freshness
            if isinstance(freshness, str) and freshness in _ALLOWED_FRESHNESS
            else "unknown"
        )
        result.append(
            RuntimeHealthDependency(
                key=key,
                status=normalized_status,
                freshness=normalized_freshness,
            )
        )
    return tuple(result)


def _safe_code(value: object, unavailable: str) -> str:
    if isinstance(value, str) and _SAFE_CODE_RE.fullmatch(value):
        return value
    return unavailable


def _safe_reason_codes(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        value
        for value in values
        if isinstance(value, str) and _SAFE_CODE_RE.fullmatch(value)
    )


def _tuple_count_or_marker(value: object) -> int | str:
    if isinstance(value, tuple):
        return len(value)
    return STAGE3_UNAVAILABLE


def _count_or_marker(value: object) -> int | str:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if value == STAGE3_UNAVAILABLE:
        return STAGE3_UNAVAILABLE
    return STAGE1_UNAVAILABLE


def _bool_or_marker(value: object) -> bool | str:
    if isinstance(value, bool):
        return value
    return STAGE1_UNAVAILABLE


__all__ = [
    "KnowledgeProvider",
    "EvidenceProvider",
    "RuntimeProvider",
    "ExistingResultEvidenceProvider",
    "evidence_inspection_view",
    "verification_inspection_view",
    "runtime_trace_view",
    "runtime_budget_view",
    "runtime_health_view",
]
