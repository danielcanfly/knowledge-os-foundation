from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from .m27_memory_contracts import (
    MemoryActivation,
    MemoryCandidate,
    MemoryClass,
)
from .m27_memory_runtime import GovernedMemoryRuntime


class MemoryActivationError(RuntimeError):
    """Raised when governed memory activation is asked to widen authority."""


class MemoryReadTraceReason(StrEnum):
    EXPLICIT_TASK_MEMORY_READ = "EXPLICIT_TASK_MEMORY_READ"
    MEMORY_RUNTIME_UNAVAILABLE = "MEMORY_RUNTIME_UNAVAILABLE"
    MEMORY_RUNTIME_DISABLED = "MEMORY_RUNTIME_DISABLED"
    TASK_POLICY_DENIED = "TASK_POLICY_DENIED"


class MemoryAuthorityStatus(StrEnum):
    AUXILIARY_CONTEXT_ONLY = "AUXILIARY_CONTEXT_ONLY"


class MemoryReader(Protocol):
    activation: MemoryActivation

    def list_retained_candidates(
        self,
        *,
        scope_token: str | None = None,
        memory_class: MemoryClass | None = None,
    ) -> tuple[MemoryCandidate, ...]: ...


_ALLOWED_TASK_KINDS = (RuntimeTaskKind.KNOWLEDGE, RuntimeTaskKind.OPS)
_DEFAULT_ALLOWED_CLASSES = (MemoryClass.PROJECT, MemoryClass.EPISODIC)


@dataclass(frozen=True, slots=True)
class GovernedMemoryReadPolicy:
    """Explicit policy for reading memory into the isolated runtime.

    Memory read is allowed only as scoped, reviewed, auxiliary context. It is not
    citation material, source provenance, release material, or a substitute for
    evidence.
    """

    enabled: bool = True
    require_task_allow_memory_read: bool = True
    require_isolated_runtime: bool = True
    allowed_task_kinds: tuple[RuntimeTaskKind, ...] = _ALLOWED_TASK_KINDS
    allowed_memory_classes: tuple[MemoryClass, ...] = _DEFAULT_ALLOWED_CLASSES
    scope_binding: str = "TASK_ID"
    max_items: int = 8

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise MemoryActivationError("enabled must be bool")
        if not isinstance(self.require_task_allow_memory_read, bool):
            raise MemoryActivationError("require_task_allow_memory_read must be bool")
        if not isinstance(self.require_isolated_runtime, bool):
            raise MemoryActivationError("require_isolated_runtime must be bool")
        if not self.allowed_task_kinds or any(
            not isinstance(kind, RuntimeTaskKind) for kind in self.allowed_task_kinds
        ):
            raise MemoryActivationError("allowed_task_kinds must be RuntimeTaskKind tuple")
        if not self.allowed_memory_classes or any(
            not isinstance(memory_class, MemoryClass)
            for memory_class in self.allowed_memory_classes
        ):
            raise MemoryActivationError("allowed_memory_classes must be MemoryClass tuple")
        if set(self.allowed_memory_classes) - set(_DEFAULT_ALLOWED_CLASSES):
            raise MemoryActivationError("memory read cannot admit forbidden classes")
        if self.scope_binding != "TASK_ID":
            raise MemoryActivationError("memory read scope must be bound to task_id")
        if (
            isinstance(self.max_items, bool)
            or not isinstance(self.max_items, int)
            or not 1 <= self.max_items <= 32
        ):
            raise MemoryActivationError("max_items must be bounded 1..32")

    def as_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "require_task_allow_memory_read": self.require_task_allow_memory_read,
            "require_isolated_runtime": self.require_isolated_runtime,
            "allowed_task_kinds": [kind.value for kind in self.allowed_task_kinds],
            "allowed_memory_classes": [
                memory_class.value for memory_class in self.allowed_memory_classes
            ],
            "scope_binding": self.scope_binding,
            "max_items": self.max_items,
            "authority": memory_authority_boundary(),
        }


DEFAULT_MEMORY_READ_POLICY = GovernedMemoryReadPolicy()


@dataclass(frozen=True, slots=True)
class MemoryReadDecision:
    allowed: bool
    scope_token: str | None
    allowed_memory_classes: tuple[MemoryClass, ...]
    trace_reason: MemoryReadTraceReason
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "scope_token": self.scope_token,
            "allowed_memory_classes": [
                memory_class.value for memory_class in self.allowed_memory_classes
            ],
            "trace_reason": self.trace_reason.value,
            "reason_codes": list(self.reason_codes),
            "authority": memory_authority_boundary(),
        }


@dataclass(frozen=True, slots=True)
class AuxiliaryMemoryContext:
    memory_id: str
    memory_class: MemoryClass
    scope_token: str
    summary: str
    tags: tuple[str, ...]
    trace_reason: MemoryReadTraceReason

    def __post_init__(self) -> None:
        if self.scope_token.startswith("source:") or self.scope_token.startswith("release:"):
            raise MemoryActivationError("memory scope cannot impersonate source/release scope")
        if self.trace_reason is not MemoryReadTraceReason.EXPLICIT_TASK_MEMORY_READ:
            raise MemoryActivationError("memory context requires explicit read trace reason")

    def as_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "memory_class": self.memory_class.value,
            "scope_token": self.scope_token,
            "summary": self.summary,
            "tags": list(self.tags),
            "trace_reason": self.trace_reason.value,
            "authority_status": MemoryAuthorityStatus.AUXILIARY_CONTEXT_ONLY.value,
            "authority": memory_authority_boundary(),
        }


@dataclass(frozen=True, slots=True)
class MemoryReadResult:
    decision: MemoryReadDecision
    auxiliary_context: tuple[AuxiliaryMemoryContext, ...]

    @property
    def retained_count(self) -> int:
        return len(self.auxiliary_context)

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.as_dict(),
            "retained_count": self.retained_count,
            "auxiliary_context": [item.as_dict() for item in self.auxiliary_context],
            "authority": memory_authority_boundary(),
        }


def memory_authority_boundary() -> dict[str, bool | str]:
    return {
        "status": MemoryAuthorityStatus.AUXILIARY_CONTEXT_ONLY.value,
        "knowledge_authority": False,
        "citation_eligible": False,
        "source_identity_eligible": False,
        "locator_eligible": False,
        "release_eligible": False,
        "can_satisfy_evidence_requirements": False,
        "can_override_answer": False,
        "can_promote_to_knowledge": False,
        "production_write": False,
    }


def decide_memory_read(
    *,
    task: M27RuntimeTask,
    memory_runtime: MemoryReader | None,
    policy: GovernedMemoryReadPolicy = DEFAULT_MEMORY_READ_POLICY,
) -> MemoryReadDecision:
    if not policy.enabled:
        return _deny(MemoryReadTraceReason.TASK_POLICY_DENIED, "MEMORY_POLICY_DISABLED")
    if policy.require_task_allow_memory_read and not task.allow_memory_read:
        return _deny(
            MemoryReadTraceReason.TASK_POLICY_DENIED,
            "TASK_DID_NOT_ALLOW_MEMORY_READ",
        )
    if task.kind not in policy.allowed_task_kinds:
        return _deny(
            MemoryReadTraceReason.TASK_POLICY_DENIED,
            "TASK_KIND_NOT_MEMORY_ELIGIBLE",
        )
    if memory_runtime is None:
        return _deny(
            MemoryReadTraceReason.MEMORY_RUNTIME_UNAVAILABLE,
            "MEMORY_RUNTIME_UNAVAILABLE",
        )
    activation = getattr(memory_runtime, "activation", None)
    if not isinstance(activation, MemoryActivation) or not activation.enabled:
        return _deny(
            MemoryReadTraceReason.MEMORY_RUNTIME_DISABLED,
            "MEMORY_RUNTIME_DISABLED",
        )
    if policy.require_isolated_runtime and not activation.isolated_runtime:
        return _deny(
            MemoryReadTraceReason.MEMORY_RUNTIME_DISABLED,
            "MEMORY_RUNTIME_NOT_ISOLATED",
        )
    return MemoryReadDecision(
        allowed=True,
        scope_token=task.task_id,
        allowed_memory_classes=policy.allowed_memory_classes,
        trace_reason=MemoryReadTraceReason.EXPLICIT_TASK_MEMORY_READ,
        reason_codes=(
            "EXPLICIT_TASK_MEMORY_READ",
            "REVIEWED_CANDIDATES_ONLY",
            "TASK_SCOPE_BOUND",
            "AUXILIARY_CONTEXT_ONLY",
            "NO_CITATION_AUTHORITY",
        ),
    )


def read_auxiliary_memory_context(
    *,
    task: M27RuntimeTask,
    memory_runtime: GovernedMemoryRuntime | None,
    policy: GovernedMemoryReadPolicy = DEFAULT_MEMORY_READ_POLICY,
) -> MemoryReadResult:
    decision = decide_memory_read(
        task=task,
        memory_runtime=memory_runtime,
        policy=policy,
    )
    if not decision.allowed:
        return MemoryReadResult(decision=decision, auxiliary_context=())
    if decision.scope_token != task.task_id:
        raise MemoryActivationError("memory read decision escaped task scope")
    assert decision.scope_token is not None

    retained: list[MemoryCandidate] = []
    for memory_class in decision.allowed_memory_classes:
        retained.extend(
            memory_runtime.list_retained_candidates(
                scope_token=decision.scope_token,
                memory_class=memory_class,
            )
        )
    retained.sort(key=lambda candidate: candidate.memory_id.value)
    context = tuple(
        AuxiliaryMemoryContext(
            memory_id=candidate.memory_id.value,
            memory_class=candidate.memory_class,
            scope_token=candidate.scope_token,
            summary=candidate.summary,
            tags=candidate.tags,
            trace_reason=decision.trace_reason,
        )
        for candidate in retained[: policy.max_items]
    )
    return MemoryReadResult(decision=decision, auxiliary_context=context)


def assert_memory_cannot_satisfy_evidence(
    memory_context: tuple[AuxiliaryMemoryContext, ...],
) -> None:
    for item in memory_context:
        payload = item.as_dict()
        forbidden_keys = {
            "citation",
            "citations",
            "source_identity",
            "source_id",
            "locator",
            "locator_id",
            "release_id",
            "manifest_sha256",
        }
        if forbidden_keys & set(payload):
            raise MemoryActivationError("memory context exposed evidence authority fields")
        authority = payload.get("authority")
        if not isinstance(authority, dict):
            raise MemoryActivationError("memory context authority is missing")
        if any(
            authority.get(flag) is not False
            for flag in (
                "knowledge_authority",
                "citation_eligible",
                "source_identity_eligible",
                "locator_eligible",
                "release_eligible",
                "can_satisfy_evidence_requirements",
                "can_override_answer",
                "can_promote_to_knowledge",
                "production_write",
            )
        ):
            raise MemoryActivationError("memory context authority boundary widened")


def answer_with_auxiliary_memory(
    *,
    answer: dict[str, object],
    memory_context: tuple[AuxiliaryMemoryContext, ...],
) -> dict[str, object]:
    """Return the evidence answer unchanged while recording memory sidecar metadata."""

    assert_memory_cannot_satisfy_evidence(memory_context)
    if not answer:
        return {}
    result = dict(answer)
    result["auxiliary_memory"] = {
        "used_for_authority": False,
        "answer_overridden": False,
        "retained_count": len(memory_context),
        "memory_ids": [item.memory_id for item in memory_context],
        "authority": memory_authority_boundary(),
    }
    return result


def _deny(reason: MemoryReadTraceReason, code: str) -> MemoryReadDecision:
    return MemoryReadDecision(
        allowed=False,
        scope_token=None,
        allowed_memory_classes=(),
        trace_reason=reason,
        reason_codes=(code,),
    )


__all__ = [
    "AuxiliaryMemoryContext",
    "DEFAULT_MEMORY_READ_POLICY",
    "GovernedMemoryReadPolicy",
    "MemoryActivationError",
    "MemoryAuthorityStatus",
    "MemoryReadDecision",
    "MemoryReadResult",
    "MemoryReadTraceReason",
    "answer_with_auxiliary_memory",
    "assert_memory_cannot_satisfy_evidence",
    "decide_memory_read",
    "memory_authority_boundary",
    "read_auxiliary_memory_context",
]
