from __future__ import annotations

import time
from dataclasses import dataclass

from .m27_context_runtime_contracts import EvidencePlanningResult, VerificationDecision
from .m27_skill_contracts import (
    SkillDescriptor,
    SkillOutputKind,
    SkillRegistry,
    build_stage7_ops_skill_registry,
)
from .m27_tool_executor import (
    ReadOnlyToolExecutor,
    ToolExecutionPolicy,
    ToolExecutionRecord,
    request_for_capability,
)


class SkillRunnerError(RuntimeError):
    """Base error for isolated M27 skill activation failures."""


class SkillRunnerAuthorizationError(SkillRunnerError):
    """Raised when a skill/capability is outside the authorized boundary."""


class SkillRunnerBudgetError(SkillRunnerError):
    """Raised when a skill runner budget is invalid."""


@dataclass(frozen=True, slots=True)
class SkillRunnerPolicy:
    """Deterministic execution policy for one isolated ops-skill run."""

    skill_name: str
    authorized_capabilities: tuple[str, ...]
    authorization_token: str
    max_tool_calls: int = 4
    timeout_ms: int = 1_000
    isolated_runtime: bool = True
    read_only_only: bool = True
    allow_mutation: bool = False
    allow_network: bool = False
    allow_raw_infra: bool = False
    allow_mcp_transport: bool = False

    def __post_init__(self) -> None:
        if not self.skill_name:
            raise SkillRunnerAuthorizationError("skill_name is required")
        if tuple(sorted(set(self.authorized_capabilities))) != self.authorized_capabilities:
            raise SkillRunnerAuthorizationError(
                "authorized_capabilities must be unique and sorted"
            )
        if self.max_tool_calls < 0:
            raise SkillRunnerBudgetError("max_tool_calls must be non-negative")
        if self.timeout_ms <= 0:
            raise SkillRunnerBudgetError("timeout_ms must be positive")
        if not self.authorization_token:
            raise SkillRunnerAuthorizationError("authorization_token is required")
        if not self.isolated_runtime:
            raise SkillRunnerAuthorizationError("skill runner requires isolated runtime")
        if not self.read_only_only:
            raise SkillRunnerAuthorizationError("skill runner requires read-only mode")
        if self.allow_mutation or self.allow_network or self.allow_raw_infra:
            raise SkillRunnerAuthorizationError(
                "skill runner cannot allow mutation, network, or raw infra"
            )

    @classmethod
    def for_skill(
        cls,
        descriptor: SkillDescriptor,
        *,
        authorization_token: str,
        max_tool_calls: int | None = None,
        timeout_ms: int = 1_000,
        allow_mcp_transport: bool = False,
    ) -> SkillRunnerPolicy:
        return cls(
            skill_name=descriptor.name,
            authorized_capabilities=tuple(sorted(descriptor.allowed_capabilities)),
            authorization_token=authorization_token,
            max_tool_calls=(
                len(descriptor.allowed_capabilities)
                if max_tool_calls is None
                else max_tool_calls
            ),
            timeout_ms=timeout_ms,
            allow_mcp_transport=allow_mcp_transport,
        )


@dataclass(frozen=True, slots=True)
class SkillRunnerContext:
    """Body-free context needed to build existing read-only tool requests."""

    request_token: str
    trace_id: str
    evidence_planning_result: EvidencePlanningResult
    verification_decision: VerificationDecision
    seed_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillToolCallBoundary:
    skill_name: str
    step_id: str
    capability_name: str
    trace_id: str
    authorization_boundary: str
    call_index: int
    status: str
    record: ToolExecutionRecord

    def as_dict(self) -> dict[str, object]:
        return {
            "skill_name": self.skill_name,
            "step_id": self.step_id,
            "capability_name": self.capability_name,
            "trace_id": self.trace_id,
            "authorization_boundary": self.authorization_boundary,
            "call_index": self.call_index,
            "status": self.status,
            "record": self.record.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SkillRunnerResult:
    status_code: str
    skill_name: str
    output_kind: SkillOutputKind
    trace_id: str
    tool_call_count: int
    max_tool_calls: int
    timed_out: bool
    budget_exhausted: bool
    mcp_transport_used: bool
    boundaries: tuple[SkillToolCallBoundary, ...]
    candidate_actions: tuple[str, ...]

    @property
    def tool_records(self) -> tuple[ToolExecutionRecord, ...]:
        return tuple(item.record for item in self.boundaries)

    def as_dict(self) -> dict[str, object]:
        return {
            "status_code": self.status_code,
            "skill_name": self.skill_name,
            "output_kind": self.output_kind.value,
            "trace_id": self.trace_id,
            "tool_call_count": self.tool_call_count,
            "max_tool_calls": self.max_tool_calls,
            "timed_out": self.timed_out,
            "budget_exhausted": self.budget_exhausted,
            "mcp_transport_used": self.mcp_transport_used,
            "boundaries": tuple(item.as_dict() for item in self.boundaries),
            "candidate_actions": self.candidate_actions,
        }


class ReadOnlySkillRunner:
    """Bounded execution surface for existing report-only ops skills.

    SkillRegistry remains descriptor-only. This runner is the explicit activation
    boundary: it authorizes one skill, translates declared step capabilities to
    typed ToolExecutor calls, and returns a body-free report envelope.
    """

    def __init__(
        self,
        *,
        skill_registry: SkillRegistry | None = None,
        tool_executor: ReadOnlyToolExecutor,
    ) -> None:
        self._tool_executor = tool_executor
        self._skill_registry = skill_registry or build_stage7_ops_skill_registry(
            tool_registry=tool_executor.registry
        )

    @property
    def skill_registry(self) -> SkillRegistry:
        return self._skill_registry

    def run(
        self,
        skill_name: str,
        *,
        context: SkillRunnerContext,
        policy: SkillRunnerPolicy,
    ) -> SkillRunnerResult:
        descriptor = self._skill_registry.resolve(skill_name)
        _authorize_skill(descriptor, policy)
        tool_policy = ToolExecutionPolicy(
            authorized_capabilities=policy.authorized_capabilities,
            authorization_token=policy.authorization_token,
        )
        started = time.monotonic()
        boundaries: list[SkillToolCallBoundary] = []
        timed_out = False
        budget_exhausted = False

        for step in descriptor.steps:
            for capability in step.capability_names:
                if len(boundaries) >= policy.max_tool_calls:
                    budget_exhausted = True
                    break
                elapsed_ms = int((time.monotonic() - started) * 1_000)
                if elapsed_ms > policy.timeout_ms:
                    timed_out = True
                    break
                if capability not in descriptor.allowed_capabilities:
                    raise SkillRunnerAuthorizationError(
                        f"step capability not allowed by skill: {capability}"
                    )
                if capability not in policy.authorized_capabilities:
                    raise SkillRunnerAuthorizationError(
                        f"capability not authorized for skill run: {capability}"
                    )
                request = request_for_capability(
                    capability,
                    request_token=context.request_token,
                    trace_id=context.trace_id,
                    evidence_planning_result=context.evidence_planning_result,
                    verification_decision=context.verification_decision,
                    seed_ids=context.seed_ids,
                )
                result = self._tool_executor.execute(
                    capability,
                    request,
                    policy=tool_policy,
                    authorization_token=policy.authorization_token,
                )
                boundaries.append(
                    SkillToolCallBoundary(
                        skill_name=descriptor.name,
                        step_id=step.step_id,
                        capability_name=capability,
                        trace_id=context.trace_id,
                        authorization_boundary=_authorization_boundary(
                            descriptor.name, context.trace_id
                        ),
                        call_index=len(boundaries),
                        status="READ_ONLY_TOOL_COMPLETED",
                        record=result.record,
                    )
                )
            if timed_out or budget_exhausted:
                break

        status_code = "M27_SKILL_RUN_COMPLETED"
        if timed_out:
            status_code = "M27_SKILL_RUN_TIMEOUT"
        elif budget_exhausted:
            status_code = "M27_SKILL_RUN_BUDGET_EXHAUSTED"

        return SkillRunnerResult(
            status_code=status_code,
            skill_name=descriptor.name,
            output_kind=descriptor.outputs[0],
            trace_id=context.trace_id,
            tool_call_count=len(boundaries),
            max_tool_calls=policy.max_tool_calls,
            timed_out=timed_out,
            budget_exhausted=budget_exhausted,
            mcp_transport_used=policy.allow_mcp_transport,
            boundaries=tuple(boundaries),
            candidate_actions=(
                "report_only",
                "candidate_followup_only",
                "no_production_mutation",
            ),
        )


def _authorize_skill(descriptor: SkillDescriptor, policy: SkillRunnerPolicy) -> None:
    if descriptor.name != policy.skill_name:
        raise SkillRunnerAuthorizationError("policy skill_name mismatch")
    if descriptor.grants_authority or descriptor.supports_mutation or descriptor.production_write:
        raise SkillRunnerAuthorizationError("skill crosses mutation/authority boundary")
    if descriptor.answer_path or descriptor.mcp_exposed:
        raise SkillRunnerAuthorizationError("skill cannot enter answer path or MCP exposure")
    for capability in descriptor.allowed_capabilities:
        if capability not in policy.authorized_capabilities:
            raise SkillRunnerAuthorizationError(
                f"policy does not authorize declared capability: {capability}"
            )


def _authorization_boundary(skill_name: str, trace_id: str) -> str:
    return f"skill:{skill_name}:trace:{trace_id}"


__all__ = [
    "SkillRunnerError",
    "SkillRunnerAuthorizationError",
    "SkillRunnerBudgetError",
    "SkillRunnerPolicy",
    "SkillRunnerContext",
    "SkillToolCallBoundary",
    "SkillRunnerResult",
    "ReadOnlySkillRunner",
]
