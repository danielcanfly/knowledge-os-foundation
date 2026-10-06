from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .m27_compute_policy import ComputePolicyObservation
from .m27_decision_trace import BudgetClass, ProviderAttemptClass
from .m27_skill_contracts import SkillPlan, SkillRegistry


class RuntimeTaskKind(StrEnum):
    NO_CONTEXT = "NO_CONTEXT"
    KNOWLEDGE = "KNOWLEDGE"
    TOOL = "TOOL"
    OPS = "OPS"


class RuntimeTaskProfile(StrEnum):
    GENERAL = "GENERAL"
    DIRECT_KNOWLEDGE = "DIRECT_KNOWLEDGE"
    MULTILINGUAL_KNOWLEDGE = "MULTILINGUAL_KNOWLEDGE"
    RETRIEVAL_HARD = "RETRIEVAL_HARD"
    DEADLINE_PRESSURE = "DEADLINE_PRESSURE"
    SAFE_ABSTENTION = "SAFE_ABSTENTION"
    TOOL_LOOKUP = "TOOL_LOOKUP"
    OPS_DIAGNOSTIC = "OPS_DIAGNOSTIC"


class RuntimeContextSource(StrEnum):
    KNOWLEDGE = "KNOWLEDGE"
    TOOL = "TOOL"
    SKILL = "SKILL"
    MEMORY_CANDIDATE = "MEMORY_CANDIDATE"


class ContinuationReasonCode(StrEnum):
    VERIFICATION_SUFFICIENT = "VERIFICATION_SUFFICIENT"
    VERIFIER_GAP_BOUNDED_CONTINUATION = "VERIFIER_GAP_BOUNDED_CONTINUATION"
    MAX_CONTINUATION_ROUNDS_EXHAUSTED = "MAX_CONTINUATION_ROUNDS_EXHAUSTED"
    TOOL_CALL_BUDGET_EXHAUSTED = "TOOL_CALL_BUDGET_EXHAUSTED"
    DEADLINE_BUDGET_EXHAUSTED = "DEADLINE_BUDGET_EXHAUSTED"
    PROVIDER_BUDGET_EXHAUSTED = "PROVIDER_BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class M27RuntimeTask:
    task_id: str
    kind: RuntimeTaskKind
    request_token: str
    requested_capability: str | None = None
    ops_intent: str | None = None
    allow_memory_read: bool = False
    profile: RuntimeTaskProfile = RuntimeTaskProfile.GENERAL
    max_continuation_rounds: int = 1
    max_tool_calls: int = 6

    def __post_init__(self) -> None:
        if not self.task_id or " " in self.task_id:
            raise ValueError("task_id must be a sanitized non-empty identifier")
        if not self.request_token or " " in self.request_token:
            raise ValueError("request_token must be a sanitized non-empty identifier")
        if not isinstance(self.kind, RuntimeTaskKind):
            raise TypeError("kind must be RuntimeTaskKind")
        if not isinstance(self.profile, RuntimeTaskProfile):
            raise TypeError("profile must be RuntimeTaskProfile")
        if self.max_continuation_rounds < 0:
            raise ValueError("max_continuation_rounds must be non-negative")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls must be non-negative")
        if self.requested_capability is not None and " " in self.requested_capability:
            raise ValueError("requested_capability must be sanitized")
        if self.ops_intent is not None and " " in self.ops_intent:
            raise ValueError("ops_intent must be sanitized")


@dataclass(frozen=True, slots=True)
class M27RuntimePlan:
    task_id: str
    context_sources: tuple[RuntimeContextSource, ...]
    tool_capabilities: tuple[str, ...]
    selected_skill_name: str | None
    selected_skill_plan: SkillPlan | None
    memory_read_enabled: bool
    max_continuation_rounds: int
    max_tool_calls: int
    reason_codes: tuple[str, ...]

    def capability_budget_exceeded(self) -> bool:
        return len(self.tool_capabilities) > self.max_tool_calls


@dataclass(frozen=True, slots=True)
class ContinuationDecision:
    allowed: bool
    reason_code: ContinuationReasonCode
    completed_rounds: int
    max_rounds: int
    tool_calls: int
    max_tool_calls: int

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code.value,
            "completed_rounds": self.completed_rounds,
            "max_rounds": self.max_rounds,
            "tool_calls": self.tool_calls,
            "max_tool_calls": self.max_tool_calls,
        }


class M27ContextOrchestrator:
    """Deterministic source and continuation planner for composed M27 runs."""

    def __init__(self, *, skill_registry: SkillRegistry | None = None) -> None:
        self._skill_registry = skill_registry

    def plan(self, task: M27RuntimeTask) -> M27RuntimePlan:
        sources: list[RuntimeContextSource] = []
        capabilities: list[str] = []
        selected_skill_name: str | None = None
        selected_skill_plan: SkillPlan | None = None
        reasons: list[str] = [f"TASK_KIND_{task.kind.value}", f"TASK_PROFILE_{task.profile.value}"]

        if task.kind is RuntimeTaskKind.KNOWLEDGE:
            sources.append(RuntimeContextSource.KNOWLEDGE)
            capabilities.append("knowledge.search")
            reasons.append("KNOWLEDGE_SELECTED")
        elif task.kind is RuntimeTaskKind.TOOL:
            if task.requested_capability is None:
                raise ValueError("tool task requires requested_capability")
            sources.append(RuntimeContextSource.TOOL)
            capabilities.append(task.requested_capability)
            reasons.append("TOOL_SELECTED")
        elif task.kind is RuntimeTaskKind.OPS:
            sources.append(RuntimeContextSource.SKILL)
            selected_skill_name = self._select_skill(task.ops_intent)
            if self._skill_registry is None:
                raise ValueError("ops task requires an injected skill registry")
            selected_skill_plan = self._skill_registry.plan(selected_skill_name)
            capabilities.extend(selected_skill_plan.required_capabilities)
            selected = selected_skill_name.upper().replace("-", "_")
            reasons.append(f"SKILL_SELECTED_{selected}")
        elif task.kind is RuntimeTaskKind.NO_CONTEXT:
            reasons.append("NO_CONTEXT_SELECTED")
        else:
            raise ValueError(f"unsupported task kind: {task.kind}")

        if task.allow_memory_read:
            sources.append(RuntimeContextSource.MEMORY_CANDIDATE)
            reasons.append("MEMORY_READ_EXPLICIT_POLICY")

        return M27RuntimePlan(
            task_id=task.task_id,
            context_sources=tuple(dict.fromkeys(sources)),
            tool_capabilities=tuple(sorted(set(capabilities))),
            selected_skill_name=selected_skill_name,
            selected_skill_plan=selected_skill_plan,
            memory_read_enabled=task.allow_memory_read,
            max_continuation_rounds=task.max_continuation_rounds,
            max_tool_calls=task.max_tool_calls,
            reason_codes=tuple(reasons),
        )

    def continuation_decision(
        self,
        *,
        verification_status: str,
        material_claim_support_verified: bool | str,
        citation_locator_valid: bool | str,
        unsupported_accepted_claims: int | str,
        safe_abstention: bool | str,
        compute_observation: ComputePolicyObservation,
        completed_rounds: int,
        tool_calls: int,
        plan: M27RuntimePlan,
    ) -> ContinuationDecision:
        gap_present = _verification_gap_present(
            verification_status=verification_status,
            material_claim_support_verified=material_claim_support_verified,
            citation_locator_valid=citation_locator_valid,
            unsupported_accepted_claims=unsupported_accepted_claims,
            safe_abstention=safe_abstention,
        )
        if not gap_present:
            return _decision(
                False,
                ContinuationReasonCode.VERIFICATION_SUFFICIENT,
                completed_rounds,
                tool_calls,
                plan,
            )
        if completed_rounds >= plan.max_continuation_rounds:
            return _decision(
                False,
                ContinuationReasonCode.MAX_CONTINUATION_ROUNDS_EXHAUSTED,
                completed_rounds,
                tool_calls,
                plan,
            )
        if tool_calls >= plan.max_tool_calls:
            return _decision(
                False,
                ContinuationReasonCode.TOOL_CALL_BUDGET_EXHAUSTED,
                completed_rounds,
                tool_calls,
                plan,
            )
        if compute_observation.deadline_budget_class is BudgetClass.EXHAUSTED:
            return _decision(
                False,
                ContinuationReasonCode.DEADLINE_BUDGET_EXHAUSTED,
                completed_rounds,
                tool_calls,
                plan,
            )
        if compute_observation.provider_budget_class is BudgetClass.EXHAUSTED:
            return _decision(
                False,
                ContinuationReasonCode.PROVIDER_BUDGET_EXHAUSTED,
                completed_rounds,
                tool_calls,
                plan,
            )
        if compute_observation.provider_attempt_class is ProviderAttemptClass.NONE:
            return _decision(
                False,
                ContinuationReasonCode.PROVIDER_BUDGET_EXHAUSTED,
                completed_rounds,
                tool_calls,
                plan,
            )
        return _decision(
            True,
            ContinuationReasonCode.VERIFIER_GAP_BOUNDED_CONTINUATION,
            completed_rounds,
            tool_calls,
            plan,
        )

    @staticmethod
    def _select_skill(ops_intent: str | None) -> str:
        intent = (ops_intent or "").lower()
        if "latency" in intent:
            return "diagnose-latency"
        if "quality" in intent or "gate" in intent:
            return "run-quality-gate"
        if "retrieval" in intent:
            return "investigate-retrieval-failure"
        return "investigate-answer-failure"


def _verification_gap_present(
    *,
    verification_status: str,
    material_claim_support_verified: bool | str,
    citation_locator_valid: bool | str,
    unsupported_accepted_claims: int | str,
    safe_abstention: bool | str,
) -> bool:
    status = verification_status.lower()
    if status in {"verified_answer", "cited_answer", "answered"}:
        return False
    if safe_abstention is True:
        return True
    if material_claim_support_verified is False:
        return True
    if citation_locator_valid is False:
        return True
    if isinstance(unsupported_accepted_claims, int) and unsupported_accepted_claims > 0:
        return True
    return status not in {"verified_answer", "cited_answer", "answered"}


def _decision(
    allowed: bool,
    reason_code: ContinuationReasonCode,
    completed_rounds: int,
    tool_calls: int,
    plan: M27RuntimePlan,
) -> ContinuationDecision:
    return ContinuationDecision(
        allowed=allowed,
        reason_code=reason_code,
        completed_rounds=completed_rounds,
        max_rounds=plan.max_continuation_rounds,
        tool_calls=tool_calls,
        max_tool_calls=plan.max_tool_calls,
    )


__all__ = [
    "RuntimeTaskKind",
    "RuntimeTaskProfile",
    "RuntimeContextSource",
    "ContinuationReasonCode",
    "M27RuntimeTask",
    "M27RuntimePlan",
    "ContinuationDecision",
    "M27ContextOrchestrator",
]
