from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .m27_context_runtime_contracts import (
    STAGE1_UNAVAILABLE,
    ComputeDecision,
    Stage1Unavailable,
)
from .m27_decision_trace import BudgetClass, ComputeTier, ProviderAttemptClass
from .m27_legacy_m26_adapters import LegacyM26DeadlineBudgetAdapter

FAST_RETRY_ONCE = "FAST_RETRY_ONCE"
SEMANTIC_CLOSURE = "SEMANTIC_CLOSURE"
CLAIM_WEAKENING = "CLAIM_WEAKENING"
EVIDENCE_SLOT_REALIGNMENT = "EVIDENCE_SLOT_REALIGNMENT"
CONTRADICTION_TRIAGE = "CONTRADICTION_TRIAGE"
SAFE_ABSTENTION = "SAFE_ABSTENTION"

_STANDARD_RECOVERY_ROUTES = frozenset(
    {
        SEMANTIC_CLOSURE,
        CLAIM_WEAKENING,
        EVIDENCE_SLOT_REALIGNMENT,
        CONTRADICTION_TRIAGE,
    }
)
_DEADLINE_PRESSURE_PREFIX = "deadline_pressure_allowed:"
_BUDGET_BLOCK_PREFIX = "deadline_or_provider_budget_blocked:"


class ShadowComputeReasonCode(StrEnum):
    FAST_RETRY_ROUTE = "FAST_RETRY_ROUTE"
    BOUNDED_SEMANTIC_RECOVERY_ROUTE = "BOUNDED_SEMANTIC_RECOVERY_ROUTE"
    DEADLINE_PRESSURE_PRESERVED = "DEADLINE_PRESSURE_PRESERVED"
    EXISTING_SAFE_ABSTENTION = "EXISTING_SAFE_ABSTENTION"
    EXISTING_BUDGET_BLOCK = "EXISTING_BUDGET_BLOCK"
    INCOMPLETE_LEGACY_SIGNAL = "INCOMPLETE_LEGACY_SIGNAL"
    UNKNOWN_LEGACY_ROUTE = "UNKNOWN_LEGACY_ROUTE"
    INCONSISTENT_LEGACY_SIGNAL = "INCONSISTENT_LEGACY_SIGNAL"


@dataclass(frozen=True, slots=True)
class ComputePolicyObservation:
    """Privacy-safe shadow classification over one already-produced M26 decision."""

    legacy: ComputeDecision
    budget_headroom_ms: int | Stage1Unavailable
    deadline_budget_class: BudgetClass
    provider_budget_class: BudgetClass
    provider_attempt_class: ProviderAttemptClass
    shadow_compute_tier: ComputeTier
    shadow_reason_code: ShadowComputeReasonCode
    deadline_pressure_allowed: bool
    shadow_only: bool = True
    authoritative: bool = False
    source: str = "rule_based_compute_policy_shadow/v1"

    @property
    def legacy_route(self) -> str | Stage1Unavailable:
        return self.legacy.route

    @property
    def legacy_reason(self) -> str | Stage1Unavailable:
        return self.legacy.reason

    @property
    def deadline_remaining_ms(self) -> int | Stage1Unavailable:
        return self.legacy.deadline_remaining_ms

    @property
    def minimum_budget_ms(self) -> int | Stage1Unavailable:
        return self.legacy.minimum_budget_ms

    @property
    def provider_attempts_remaining(self) -> int | Stage1Unavailable:
        return self.legacy.provider_attempts_remaining

    @property
    def affordable(self) -> bool | Stage1Unavailable:
        return self.legacy.affordable

    def as_dict(self) -> dict[str, Any]:
        return {
            "legacy_route": self.legacy_route,
            "legacy_reason": self.legacy_reason,
            "deadline_remaining_ms": self.deadline_remaining_ms,
            "minimum_budget_ms": self.minimum_budget_ms,
            "budget_headroom_ms": self.budget_headroom_ms,
            "provider_attempts_remaining": self.provider_attempts_remaining,
            "affordable": self.affordable,
            "shadow_compute_tier": self.shadow_compute_tier.value,
            "shadow_reason_code": self.shadow_reason_code.value,
            "deadline_budget_class": self.deadline_budget_class.value,
            "provider_budget_class": self.provider_budget_class.value,
            "provider_attempt_class": self.provider_attempt_class.value,
            "deadline_pressure_allowed": self.deadline_pressure_allowed,
            "shadow_only": self.shadow_only,
            "authoritative": self.authoritative,
            "source": self.source,
        }


class RuleBasedComputePolicy:
    """Deterministic observer over existing M26 deadline/provider budget signals.

    This policy has no execution authority. It does not allocate calls, alter a route,
    extend a deadline, change retrieval, change repair allowance, or change an answer.
    """

    def __init__(self, adapter: LegacyM26DeadlineBudgetAdapter | None = None) -> None:
        self._adapter = adapter or LegacyM26DeadlineBudgetAdapter()

    def classify(self, budget_signal: object) -> ComputePolicyObservation:
        legacy = self._adapter.normalize(budget_signal)
        headroom = _budget_headroom_ms(legacy)
        deadline_class = _deadline_budget_class(legacy)
        provider_class = _provider_budget_class(legacy.provider_attempts_remaining)
        provider_attempt_class = _provider_attempt_class(legacy.provider_attempts_remaining)
        deadline_pressure = _has_reason_prefix(legacy.reason, _DEADLINE_PRESSURE_PREFIX)
        tier, reason_code = _shadow_tier(
            legacy,
            deadline_pressure=deadline_pressure,
        )
        return ComputePolicyObservation(
            legacy=legacy,
            budget_headroom_ms=headroom,
            deadline_budget_class=deadline_class,
            provider_budget_class=provider_class,
            provider_attempt_class=provider_attempt_class,
            shadow_compute_tier=tier,
            shadow_reason_code=reason_code,
            deadline_pressure_allowed=deadline_pressure,
        )

    def normalize(self, budget_signal: object) -> ComputeDecision:
        """Preserve the canonical ComputePolicy protocol's legacy normalization API."""

        return self._adapter.normalize(budget_signal)


def _shadow_tier(
    legacy: ComputeDecision,
    *,
    deadline_pressure: bool,
) -> tuple[ComputeTier, ShadowComputeReasonCode]:
    route = legacy.route
    reason = legacy.reason

    if route == SAFE_ABSTENTION:
        if _has_reason_prefix(reason, _BUDGET_BLOCK_PREFIX):
            return ComputeTier.FAIL_CLOSED, ShadowComputeReasonCode.EXISTING_BUDGET_BLOCK
        return ComputeTier.FAIL_CLOSED, ShadowComputeReasonCode.EXISTING_SAFE_ABSTENTION

    if not _core_budget_signals_available(legacy):
        return ComputeTier.LEGACY_M26, ShadowComputeReasonCode.INCOMPLETE_LEGACY_SIGNAL

    if route == FAST_RETRY_ONCE:
        if legacy.affordable is True and not deadline_pressure:
            return ComputeTier.FAST, ShadowComputeReasonCode.FAST_RETRY_ROUTE
        return ComputeTier.LEGACY_M26, ShadowComputeReasonCode.INCONSISTENT_LEGACY_SIGNAL

    if route in _STANDARD_RECOVERY_ROUTES:
        if deadline_pressure:
            if legacy.provider_attempts_remaining > 0 and legacy.affordable is False:
                return (
                    ComputeTier.STANDARD,
                    ShadowComputeReasonCode.DEADLINE_PRESSURE_PRESERVED,
                )
            return ComputeTier.LEGACY_M26, ShadowComputeReasonCode.INCONSISTENT_LEGACY_SIGNAL
        if legacy.affordable is True:
            return (
                ComputeTier.STANDARD,
                ShadowComputeReasonCode.BOUNDED_SEMANTIC_RECOVERY_ROUTE,
            )
        return ComputeTier.LEGACY_M26, ShadowComputeReasonCode.INCONSISTENT_LEGACY_SIGNAL

    return ComputeTier.LEGACY_M26, ShadowComputeReasonCode.UNKNOWN_LEGACY_ROUTE


def _core_budget_signals_available(legacy: ComputeDecision) -> bool:
    return (
        isinstance(legacy.route, str)
        and legacy.route != STAGE1_UNAVAILABLE
        and isinstance(legacy.reason, str)
        and legacy.reason != STAGE1_UNAVAILABLE
        and _is_int(legacy.deadline_remaining_ms)
        and _is_int(legacy.minimum_budget_ms)
        and _is_int(legacy.provider_attempts_remaining)
        and isinstance(legacy.affordable, bool)
    )


def _budget_headroom_ms(legacy: ComputeDecision) -> int | Stage1Unavailable:
    if not _is_int(legacy.deadline_remaining_ms) or not _is_int(legacy.minimum_budget_ms):
        return STAGE1_UNAVAILABLE
    return legacy.deadline_remaining_ms - legacy.minimum_budget_ms


def _deadline_budget_class(legacy: ComputeDecision) -> BudgetClass:
    remaining = legacy.deadline_remaining_ms
    minimum = legacy.minimum_budget_ms
    if not _is_int(remaining) or not _is_int(minimum):
        return BudgetClass.UNAVAILABLE_IN_STAGE1
    if remaining <= 0:
        return BudgetClass.EXHAUSTED
    if remaining < minimum:
        return BudgetClass.CONSTRAINED
    return BudgetClass.HEALTHY


def _provider_budget_class(value: int | Stage1Unavailable) -> BudgetClass:
    if not _is_int(value):
        return BudgetClass.UNAVAILABLE_IN_STAGE1
    if value <= 0:
        return BudgetClass.EXHAUSTED
    if value == 1:
        return BudgetClass.CONSTRAINED
    return BudgetClass.HEALTHY


def _provider_attempt_class(value: int | Stage1Unavailable) -> ProviderAttemptClass:
    if not _is_int(value):
        return ProviderAttemptClass.UNAVAILABLE_IN_STAGE1
    if value <= 0:
        return ProviderAttemptClass.NONE
    if value == 1:
        return ProviderAttemptClass.ONE
    return ProviderAttemptClass.MULTIPLE


def _has_reason_prefix(reason: str | Stage1Unavailable, prefix: str) -> bool:
    return isinstance(reason, str) and reason != STAGE1_UNAVAILABLE and reason.startswith(prefix)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
