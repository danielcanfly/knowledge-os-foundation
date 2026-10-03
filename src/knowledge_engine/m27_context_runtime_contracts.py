from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from .m27_decision_trace import DecisionTraceEvent

STAGE1_UNAVAILABLE = "unavailable_in_stage1"
Stage1Unavailable = Literal["unavailable_in_stage1"]
Stage1Availability = Literal["available", "unavailable_in_stage1"]


@dataclass(frozen=True)
class PolicyDecision:
    policy_name: str
    decision: str
    reason_codes: tuple[str, ...] = ()
    source: str = "legacy_m26"
    availability: Stage1Availability = "available"


@dataclass(frozen=True)
class ComputeDecision:
    route: str | Stage1Unavailable
    reason: str | Stage1Unavailable
    deadline_remaining_ms: int | Stage1Unavailable
    minimum_budget_ms: int | Stage1Unavailable
    provider_attempts_remaining: int | Stage1Unavailable
    affordable: bool | Stage1Unavailable
    compute_tier: str | Stage1Unavailable = STAGE1_UNAVAILABLE
    source: str = "legacy_m26_deadline_budget"


@dataclass(frozen=True)
class EvidencePlan:
    selected_evidence_ids: tuple[str, ...] | Stage1Unavailable = STAGE1_UNAVAILABLE
    selected_evidence_count: int | Stage1Unavailable = STAGE1_UNAVAILABLE
    source_count: int | Stage1Unavailable = STAGE1_UNAVAILABLE
    retrieval_round_count: int | Stage1Unavailable = STAGE1_UNAVAILABLE
    reason_codes: tuple[str, ...] = ()
    source: str = "legacy_m26"


@dataclass(frozen=True)
class ContextPlan:
    route: str | Stage1Unavailable
    reason: str | Stage1Unavailable
    evidence_plan: EvidencePlan = field(default_factory=EvidencePlan)
    planning_mode: str | Stage1Unavailable = STAGE1_UNAVAILABLE
    source: str = "legacy_m26_semantic_routing"


@dataclass(frozen=True)
class ContextCompileResult:
    status: str | Stage1Unavailable
    context_manifest_sha256: str | None | Stage1Unavailable
    evidence_budget_sha256: str | None | Stage1Unavailable
    token_budget: int | Stage1Unavailable
    measured_token_estimate: int | Stage1Unavailable
    selected_passage_ids: tuple[str, ...] | Stage1Unavailable
    citation_count: int | Stage1Unavailable
    safe_for_provider: bool | Stage1Unavailable
    prompt_injection_quarantined: bool | Stage1Unavailable
    reason_codes: tuple[str, ...] = ()
    source: str = "legacy_m26_context_compiler"


@dataclass(frozen=True)
class VerificationDecision:
    status: str | Stage1Unavailable
    terminal_status: str | Stage1Unavailable
    safe_abstention: bool | Stage1Unavailable
    reason_codes: tuple[str, ...]
    provider_call_count: int | Stage1Unavailable
    material_claim_support_verified: bool | Stage1Unavailable
    citation_locator_valid: bool | Stage1Unavailable
    unsupported_accepted_claims: int | Stage1Unavailable
    repair_attempted: bool | Stage1Unavailable
    citation_count: int | Stage1Unavailable
    answer_source: str | Stage1Unavailable
    source: str = "legacy_m26_verifier"


@runtime_checkable
class RuntimeTraceStore(Protocol):
    def record(self, event: DecisionTraceEvent) -> None:
        """Persist or emit one already-sanitized decision event."""


@runtime_checkable
class ContextPlanner(Protocol):
    def normalize(self, routing_signal: object) -> ContextPlan:
        """Normalize an already-produced routing signal without changing it."""


@runtime_checkable
class ComputePolicy(Protocol):
    def normalize(self, budget_signal: object) -> ComputeDecision:
        """Normalize already-produced deadline/provider budget signals."""


@runtime_checkable
class ContextCompiler(Protocol):
    def normalize(self, compiled_output: Mapping[str, object]) -> ContextCompileResult:
        """Normalize an already-produced M26 context package."""


@runtime_checkable
class Verifier(Protocol):
    def normalize(self, verification_output: Mapping[str, object]) -> VerificationDecision:
        """Normalize an already-produced M26 verification/final response."""
