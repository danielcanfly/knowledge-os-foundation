from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .m27_compute_policy import ComputePolicyObservation
from .m27_context_orchestrator import RuntimeTaskKind, RuntimeTaskProfile
from .m27_decision_trace import BudgetClass, ComputeTier, ProviderAttemptClass


class AdaptiveReasonCode(StrEnum):
    NO_CONTEXT_FAST = "NO_CONTEXT_FAST"
    TOOL_FAST = "TOOL_FAST"
    DIRECT_KNOWLEDGE_STANDARD = "DIRECT_KNOWLEDGE_STANDARD"
    MULTILINGUAL_STANDARD = "MULTILINGUAL_STANDARD"
    RETRIEVAL_HARD_DEEP = "RETRIEVAL_HARD_DEEP"
    RETRIEVAL_HARD_BUDGET_DOWNGRADE = "RETRIEVAL_HARD_BUDGET_DOWNGRADE"
    DEADLINE_PRESSURE_FAST = "DEADLINE_PRESSURE_FAST"
    OPS_STANDARD = "OPS_STANDARD"
    SAFE_ABSTENTION_FAIL_CLOSED = "SAFE_ABSTENTION_FAIL_CLOSED"
    BUDGET_FAIL_CLOSED = "BUDGET_FAIL_CLOSED"
    TELEMETRY_PROGRESS = "TELEMETRY_PROGRESS"
    TELEMETRY_NO_EVIDENCE_GAIN = "TELEMETRY_NO_EVIDENCE_GAIN"
    TELEMETRY_EMPTY_FIRST_ROUND_PROBE = "TELEMETRY_EMPTY_FIRST_ROUND_PROBE"
    TELEMETRY_LATENCY_PRESSURE = "TELEMETRY_LATENCY_PRESSURE"
    TELEMETRY_PROVIDER_BUDGET = "TELEMETRY_PROVIDER_BUDGET"
    TELEMETRY_ROUND_LIMIT = "TELEMETRY_ROUND_LIMIT"
    TELEMETRY_VERIFIED = "TELEMETRY_VERIFIED"


@dataclass(frozen=True, slots=True)
class AdaptiveComputeBudget:
    tier: ComputeTier
    max_continuation_rounds: int
    max_tool_calls: int
    max_provider_calls: int
    reason_codes: tuple[str, ...]
    authoritative: bool = True
    source: str = "m27-adaptive-compute/v1"

    def __post_init__(self) -> None:
        if self.max_continuation_rounds not in (0, 1, 2):
            raise ValueError("continuation rounds must be bounded to 0..2")
        if not 0 <= self.max_tool_calls <= 6:
            raise ValueError("tool calls must be bounded to 0..6")
        if not 0 <= self.max_provider_calls <= 12:
            raise ValueError("provider calls must be bounded to 0..12")

    def as_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier.value,
            "max_continuation_rounds": self.max_continuation_rounds,
            "max_tool_calls": self.max_tool_calls,
            "max_provider_calls": self.max_provider_calls,
            "reason_codes": list(self.reason_codes),
            "authoritative": self.authoritative,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class AdaptiveContinuationDecision:
    allowed: bool
    reason_code: AdaptiveReasonCode


class AdaptiveComputeController:
    """Bounded deterministic compute control from task profile, budgets and safe telemetry."""

    HARD_MAX_CONTINUATION_ROUNDS = 2
    HARD_MAX_TOOL_CALLS = 6
    HARD_MAX_PROVIDER_CALLS = 12
    LATENCY_PRESSURE_MS = 2_000.0

    def decide_initial(
        self,
        *,
        kind: RuntimeTaskKind,
        profile: RuntimeTaskProfile,
        compute: ComputePolicyObservation,
        requested_max_rounds: int,
        requested_max_tool_calls: int,
    ) -> AdaptiveComputeBudget:
        requested_rounds = max(0, min(requested_max_rounds, self.HARD_MAX_CONTINUATION_ROUNDS))
        requested_tools = max(0, min(requested_max_tool_calls, self.HARD_MAX_TOOL_CALLS))
        provider_remaining = compute.provider_attempts_remaining
        provider_cap = (
            min(provider_remaining, self.HARD_MAX_PROVIDER_CALLS)
            if isinstance(provider_remaining, int) and not isinstance(provider_remaining, bool)
            else 0
        )

        exhausted = (
            compute.deadline_budget_class is BudgetClass.EXHAUSTED
            or compute.provider_budget_class is BudgetClass.EXHAUSTED
            or compute.provider_attempt_class is ProviderAttemptClass.NONE
        )
        if exhausted:
            return AdaptiveComputeBudget(
                tier=ComputeTier.FAIL_CLOSED,
                max_continuation_rounds=0,
                max_tool_calls=0,
                max_provider_calls=0,
                reason_codes=(AdaptiveReasonCode.BUDGET_FAIL_CLOSED.value,),
            )
        if profile is RuntimeTaskProfile.SAFE_ABSTENTION:
            return AdaptiveComputeBudget(
                tier=ComputeTier.FAIL_CLOSED,
                max_continuation_rounds=0,
                max_tool_calls=0,
                max_provider_calls=0,
                reason_codes=(AdaptiveReasonCode.SAFE_ABSTENTION_FAIL_CLOSED.value,),
            )
        if profile is RuntimeTaskProfile.GENERAL:
            return AdaptiveComputeBudget(
                ComputeTier.STANDARD,
                requested_rounds,
                requested_tools,
                provider_cap,
                (AdaptiveReasonCode.DIRECT_KNOWLEDGE_STANDARD.value,),
            )
        if kind is RuntimeTaskKind.NO_CONTEXT:
            return AdaptiveComputeBudget(
                ComputeTier.FAST, 0, 0, min(provider_cap, 1),
                (AdaptiveReasonCode.NO_CONTEXT_FAST.value,),
            )
        if profile is RuntimeTaskProfile.DEADLINE_PRESSURE:
            return AdaptiveComputeBudget(
                ComputeTier.FAST, 0, min(requested_tools, 1), min(provider_cap, 2),
                (AdaptiveReasonCode.DEADLINE_PRESSURE_FAST.value,),
            )
        if kind is RuntimeTaskKind.TOOL or profile is RuntimeTaskProfile.TOOL_LOOKUP:
            return AdaptiveComputeBudget(
                ComputeTier.FAST, 0, min(requested_tools, 1), min(provider_cap, 1),
                (AdaptiveReasonCode.TOOL_FAST.value,),
            )
        if profile is RuntimeTaskProfile.RETRIEVAL_HARD:
            healthy = (
                compute.deadline_budget_class is BudgetClass.HEALTHY
                and compute.provider_budget_class is BudgetClass.HEALTHY
                and compute.provider_attempt_class is ProviderAttemptClass.MULTIPLE
            )
            if healthy:
                return AdaptiveComputeBudget(
                    ComputeTier.DEEP,
                    min(requested_rounds, 2),
                    min(requested_tools, 3),
                    provider_cap,
                    (AdaptiveReasonCode.RETRIEVAL_HARD_DEEP.value,),
                )
            return AdaptiveComputeBudget(
                ComputeTier.STANDARD,
                min(requested_rounds, 1),
                min(requested_tools, 2),
                min(provider_cap, 2),
                (AdaptiveReasonCode.RETRIEVAL_HARD_BUDGET_DOWNGRADE.value,),
            )
        if profile is RuntimeTaskProfile.MULTILINGUAL_KNOWLEDGE:
            return AdaptiveComputeBudget(
                ComputeTier.STANDARD,
                min(requested_rounds, 1),
                min(requested_tools, 2),
                min(provider_cap, 2),
                (AdaptiveReasonCode.MULTILINGUAL_STANDARD.value,),
            )
        if kind is RuntimeTaskKind.OPS or profile is RuntimeTaskProfile.OPS_DIAGNOSTIC:
            return AdaptiveComputeBudget(
                ComputeTier.STANDARD,
                min(requested_rounds, 1),
                min(requested_tools, 3),
                min(provider_cap, 2),
                (AdaptiveReasonCode.OPS_STANDARD.value,),
            )
        return AdaptiveComputeBudget(
            ComputeTier.STANDARD,
            min(requested_rounds, 1),
            min(requested_tools, 2),
            min(provider_cap, 2),
            (AdaptiveReasonCode.DIRECT_KNOWLEDGE_STANDARD.value,),
        )

    def decide_continuation(
        self,
        *,
        budget: AdaptiveComputeBudget,
        telemetry: Mapping[str, object],
        completed_rounds: int,
        tool_calls: int,
        provider_calls: int,
        verified: bool,
    ) -> AdaptiveContinuationDecision:
        if verified:
            return AdaptiveContinuationDecision(False, AdaptiveReasonCode.TELEMETRY_VERIFIED)
        if completed_rounds >= budget.max_continuation_rounds:
            return AdaptiveContinuationDecision(False, AdaptiveReasonCode.TELEMETRY_ROUND_LIMIT)
        if tool_calls >= budget.max_tool_calls or provider_calls >= budget.max_provider_calls:
            return AdaptiveContinuationDecision(False, AdaptiveReasonCode.TELEMETRY_PROVIDER_BUDGET)
        evidence_delta = telemetry.get("evidence_delta")
        if not isinstance(evidence_delta, int) or evidence_delta <= 0:
            if completed_rounds == 0:
                return AdaptiveContinuationDecision(
                    True, AdaptiveReasonCode.TELEMETRY_EMPTY_FIRST_ROUND_PROBE
                )
            return AdaptiveContinuationDecision(
                False, AdaptiveReasonCode.TELEMETRY_NO_EVIDENCE_GAIN
            )
        round_total_ms = telemetry.get("round_total_ms")
        if (
            isinstance(round_total_ms, (int, float))
            and not isinstance(round_total_ms, bool)
            and float(round_total_ms) >= self.LATENCY_PRESSURE_MS
        ):
            return AdaptiveContinuationDecision(
                False, AdaptiveReasonCode.TELEMETRY_LATENCY_PRESSURE
            )
        return AdaptiveContinuationDecision(True, AdaptiveReasonCode.TELEMETRY_PROGRESS)


__all__ = [
    "AdaptiveReasonCode",
    "AdaptiveComputeBudget",
    "AdaptiveContinuationDecision",
    "AdaptiveComputeController",
]
