from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from .m27_feature_flags import M27FeatureFlags

TRACE_SCHEMA_VERSION = "m27-sanitized-decision-trace/v1"


class DecisionRoute(StrEnum):
    FAST_RETRY_ONCE = "FAST_RETRY_ONCE"
    SEMANTIC_CLOSURE = "SEMANTIC_CLOSURE"
    CLAIM_WEAKENING = "CLAIM_WEAKENING"
    EVIDENCE_SLOT_REALIGNMENT = "EVIDENCE_SLOT_REALIGNMENT"
    CONTRADICTION_TRIAGE = "CONTRADICTION_TRIAGE"
    SAFE_ABSTENTION = "SAFE_ABSTENTION"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class DecisionReasonCode(StrEnum):
    ROUTE_SELECTED = "ROUTE_SELECTED"
    LOW_INFORMATION_RETRY = "LOW_INFORMATION_RETRY"
    QUESTION_ALIGNMENT_GAP = "QUESTION_ALIGNMENT_GAP"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    CITATION_GAP = "CITATION_GAP"
    CLAIM_SUPPORT_GAP = "CLAIM_SUPPORT_GAP"
    DEADLINE_PRESSURE_ALLOWED = "DEADLINE_PRESSURE_ALLOWED"
    DEADLINE_OR_PROVIDER_BUDGET_BLOCKED = "DEADLINE_OR_PROVIDER_BUDGET_BLOCKED"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class ComputeTier(StrEnum):
    LEGACY_M26 = "LEGACY_M26"
    FAST = "FAST"
    STANDARD = "STANDARD"
    DEEP = "DEEP"
    FAIL_CLOSED = "FAIL_CLOSED"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class BudgetClass(StrEnum):
    HEALTHY = "HEALTHY"
    CONSTRAINED = "CONSTRAINED"
    EXHAUSTED = "EXHAUSTED"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class ProviderAttemptClass(StrEnum):
    NONE = "NONE"
    ONE = "ONE"
    MULTIPLE = "MULTIPLE"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class ContextSource(StrEnum):
    LEXICAL = "LEXICAL"
    DENSE = "DENSE"
    GRAPH = "GRAPH"
    IDENTIFIER = "IDENTIFIER"
    CONTEXT_COMPILER = "CONTEXT_COMPILER"
    PRODUCTION_BUNDLE = "PRODUCTION_BUNDLE"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class StatusClass(StrEnum):
    CITED_ANSWER = "CITED_ANSWER"
    SAFE_ABSTENTION = "SAFE_ABSTENTION"
    ERROR = "ERROR"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class SafeAbstentionOutcome(StrEnum):
    ABSTAINED = "ABSTAINED"
    DID_NOT_ABSTAIN = "DID_NOT_ABSTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


class TraceGuard(StrEnum):
    ADMISSION = "ADMISSION"
    BAD_TEMPLATE = "BAD_TEMPLATE"
    CITATION_BINDING = "CITATION_BINDING"
    GENERIC_EXTRACTIVE_FALLBACK = "GENERIC_EXTRACTIVE_FALLBACK"
    PUBLICATION = "PUBLICATION"
    UNSUPPORTED_MATERIAL_CLAIM = "UNSUPPORTED_MATERIAL_CLAIM"


class GuardOutcome(StrEnum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNAVAILABLE_IN_STAGE1 = "UNAVAILABLE_IN_STAGE1"


@dataclass(frozen=True, slots=True)
class GuardObservation:
    guard: TraceGuard
    outcome: GuardOutcome

    def __post_init__(self) -> None:
        _require_enum("guard", self.guard, TraceGuard)
        _require_enum("outcome", self.outcome, GuardOutcome)

    def as_dict(self) -> dict[str, str]:
        return {
            "guard": self.guard.value,
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True, slots=True)
class DecisionTraceEvent:
    """Sanitized observability-only trace event.

    This schema intentionally has no arbitrary metadata or payload field. It
    cannot represent raw query/answer/evidence/source text, credentials, or
    environment values.
    """

    trace_id: str
    route: DecisionRoute
    reason_code: DecisionReasonCode
    compute_tier: ComputeTier
    deadline_budget_class: BudgetClass
    provider_budget_class: BudgetClass
    provider_attempt_count: int | None
    context_sources: tuple[ContextSource, ...]
    evidence_count: int
    citation_count: int
    status_class: StatusClass
    safe_abstention_outcome: SafeAbstentionOutcome
    guard_outcomes: tuple[GuardObservation, ...] = ()

    def __post_init__(self) -> None:
        _require_canonical_uuid("trace_id", self.trace_id)
        _require_enum("route", self.route, DecisionRoute)
        _require_enum("reason_code", self.reason_code, DecisionReasonCode)
        _require_enum("compute_tier", self.compute_tier, ComputeTier)
        _require_enum("deadline_budget_class", self.deadline_budget_class, BudgetClass)
        _require_enum("provider_budget_class", self.provider_budget_class, BudgetClass)
        _require_optional_nonnegative_int(
            "provider_attempt_count",
            self.provider_attempt_count,
        )
        _require_enum_tuple("context_sources", self.context_sources, ContextSource)
        _require_nonnegative_int("evidence_count", self.evidence_count)
        _require_nonnegative_int("citation_count", self.citation_count)
        _require_enum("status_class", self.status_class, StatusClass)
        _require_enum(
            "safe_abstention_outcome",
            self.safe_abstention_outcome,
            SafeAbstentionOutcome,
        )
        _require_guard_observations(self.guard_outcomes)

    @property
    def provider_attempt_class(self) -> ProviderAttemptClass:
        count = self.provider_attempt_count
        if count is None:
            return ProviderAttemptClass.UNAVAILABLE_IN_STAGE1
        if count == 0:
            return ProviderAttemptClass.NONE
        if count == 1:
            return ProviderAttemptClass.ONE
        return ProviderAttemptClass.MULTIPLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": self.trace_id,
            "route": self.route.value,
            "reason_code": self.reason_code.value,
            "compute_tier": self.compute_tier.value,
            "deadline_budget_class": self.deadline_budget_class.value,
            "provider_budget_class": self.provider_budget_class.value,
            "provider_attempt_count": self.provider_attempt_count,
            "provider_attempt_class": self.provider_attempt_class.value,
            "context_sources": [source.value for source in self.context_sources],
            "evidence_count": self.evidence_count,
            "citation_count": self.citation_count,
            "status_class": self.status_class.value,
            "safe_abstention_outcome": self.safe_abstention_outcome.value,
            "guard_outcomes": [guard.as_dict() for guard in self.guard_outcomes],
        }


def new_trace_id() -> str:
    return str(uuid4())


def emit_decision_trace_if_enabled(
    event: DecisionTraceEvent,
    *,
    flags: M27FeatureFlags,
    sink: Callable[[DecisionTraceEvent], None],
) -> bool:
    """Emit one sanitized event only when the effective M27 flag is enabled."""

    if not flags.context_runtime_shadow_trace_enabled:
        return False
    sink(event)
    return True


def _require_canonical_uuid(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a canonical UUID string")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a canonical UUID string") from exc
    if str(parsed) != value:
        raise ValueError(f"{name} must use canonical lowercase UUID form")


def _require_enum(name: str, value: object, enum_type: type[StrEnum]) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{name} must be {enum_type.__name__}")


def _require_enum_tuple(
    name: str,
    values: object,
    enum_type: type[StrEnum],
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple of {enum_type.__name__}")
    if any(not isinstance(value, enum_type) for value in values):
        raise TypeError(f"{name} must contain only {enum_type.__name__}")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")


def _require_nonnegative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_nonnegative_int(name: str, value: object) -> None:
    if value is None:
        return
    _require_nonnegative_int(name, value)


def _require_guard_observations(values: object) -> None:
    if not isinstance(values, tuple):
        raise TypeError("guard_outcomes must be a tuple of GuardObservation")
    if any(not isinstance(value, GuardObservation) for value in values):
        raise TypeError("guard_outcomes must contain only GuardObservation")
    guards = [value.guard for value in values]
    if len(set(guards)) != len(guards):
        raise ValueError("guard_outcomes must not contain duplicate guards")
