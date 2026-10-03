from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .m27_tool_registry import ToolRegistry, build_stage5_readonly_registry

SKILL_RUNTIME_SCHEMA_VERSION = "m27-ops-skill-runtime/v1"

_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,256}$")

_DEFERRED_SKILLS = frozenset(
    {
        "answer-from-knowledge",
        "deep-research",
        "ingest-and-update-knowledge",
        "promote-knowledge-release",
    }
)
_ALLOWED_STAGE7_OPS_SKILLS = frozenset(
    {
        "investigate-answer-failure",
        "investigate-retrieval-failure",
        "diagnose-latency",
        "run-quality-gate",
    }
)

_FORBIDDEN_SKILL_TOKENS = frozenset(
    {
        "answer",
        "research",
        "ingest",
        "update",
        "promote",
        "release",
        "rollback",
        "write",
        "delete",
        "mutate",
        "memory",
        "workspace",
        "mcp",
    }
)
_DEFAULT_PROHIBITED_ACTIONS = (
    "grant_authorization",
    "invoke_tool",
    "execute_shell",
    "write_production_state",
    "promote_release",
    "rollback_release",
    "modify_ingestion",
    "read_raw_infrastructure",
    "store_raw_query_or_answer",
)


class SkillRuntimeError(ValueError):
    """Raised when a Stage 7 skill violates the ops-only runtime boundary."""


class DuplicateSkillError(SkillRuntimeError):
    """Raised when a skill is registered twice."""


class UnknownSkillError(SkillRuntimeError):
    """Raised when a skill is not registered."""


class ForbiddenSkillError(SkillRuntimeError):
    """Raised when a skill attempts to cross Stage 7 boundaries."""


class SkillCategory(StrEnum):
    OPS_INVESTIGATION = "OPS_INVESTIGATION"
    OPS_DIAGNOSIS = "OPS_DIAGNOSIS"
    OPS_QUALITY_GATE = "OPS_QUALITY_GATE"


class SkillStepKind(StrEnum):
    COLLECT_METADATA = "COLLECT_METADATA"
    COMPARE_SIGNALS = "COMPARE_SIGNALS"
    IDENTIFY_GAPS = "IDENTIFY_GAPS"
    DIAGNOSE_BUDGET = "DIAGNOSE_BUDGET"
    REPORT_ONLY = "REPORT_ONLY"
    CANDIDATE_ONLY = "CANDIDATE_ONLY"


class SkillOutputKind(StrEnum):
    INVESTIGATION_REPORT = "INVESTIGATION_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    QUALITY_GATE_REPORT = "QUALITY_GATE_REPORT"
    FOLLOWUP_CANDIDATE = "FOLLOWUP_CANDIDATE"


@dataclass(frozen=True, slots=True)
class SkillStep:
    step_id: str
    title: str
    kind: SkillStepKind
    capability_names: tuple[str, ...] = ()
    report_only: bool = True
    grants_authority: bool = False
    supports_mutation: bool = False
    production_write: bool = False

    def __post_init__(self) -> None:
        _require_safe_id("step_id", self.step_id)
        if not self.title.strip():
            raise SkillRuntimeError("step title must not be empty")
        if not isinstance(self.kind, SkillStepKind):
            raise SkillRuntimeError("step kind must be SkillStepKind")
        _require_capability_tuple(self.capability_names)
        _require_bool("report_only", self.report_only)
        _require_bool("grants_authority", self.grants_authority)
        _require_bool("supports_mutation", self.supports_mutation)
        _require_bool("production_write", self.production_write)
        if self.report_only is not True:
            raise ForbiddenSkillError("Stage 7 skill steps must be report-only")
        if self.grants_authority or self.supports_mutation or self.production_write:
            raise ForbiddenSkillError(
                "Stage 7 skill steps must not grant authority or mutate state"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "kind": self.kind.value,
            "capability_names": self.capability_names,
            "report_only": self.report_only,
            "grants_authority": self.grants_authority,
            "supports_mutation": self.supports_mutation,
            "production_write": self.production_write,
        }


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    name: str
    description: str
    category: SkillCategory
    allowed_capabilities: tuple[str, ...]
    steps: tuple[SkillStep, ...]
    outputs: tuple[SkillOutputKind, ...]
    grants_authority: bool = False
    can_execute_tools: bool = False
    supports_mutation: bool = False
    production_write: bool = False
    answer_path: bool = False
    mcp_exposed: bool = False

    def __post_init__(self) -> None:
        _require_skill_name(self.name)
        if not self.description.strip():
            raise SkillRuntimeError("skill description must not be empty")
        if not isinstance(self.category, SkillCategory):
            raise SkillRuntimeError("category must be SkillCategory")
        _require_capability_tuple(self.allowed_capabilities)
        if not self.steps:
            raise SkillRuntimeError("skill must have at least one step")
        if any(not isinstance(step, SkillStep) for step in self.steps):
            raise SkillRuntimeError("steps must contain only SkillStep")
        if not self.outputs:
            raise SkillRuntimeError("skill must declare at least one output kind")
        if any(not isinstance(output, SkillOutputKind) for output in self.outputs):
            raise SkillRuntimeError("outputs must contain only SkillOutputKind")
        for name, value in (
            ("grants_authority", self.grants_authority),
            ("can_execute_tools", self.can_execute_tools),
            ("supports_mutation", self.supports_mutation),
            ("production_write", self.production_write),
            ("answer_path", self.answer_path),
            ("mcp_exposed", self.mcp_exposed),
        ):
            _require_bool(name, value)
        if any(
            (
                self.grants_authority,
                self.can_execute_tools,
                self.supports_mutation,
                self.production_write,
                self.answer_path,
                self.mcp_exposed,
            )
        ):
            raise ForbiddenSkillError("Stage 7 skills are descriptive ops plans only")
        step_caps = tuple(
            dict.fromkeys(capability for step in self.steps for capability in step.capability_names)
        )
        if any(capability not in self.allowed_capabilities for capability in step_caps):
            raise SkillRuntimeError("step capabilities must be listed in allowed_capabilities")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SKILL_RUNTIME_SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "allowed_capabilities": self.allowed_capabilities,
            "steps": tuple(step.as_dict() for step in self.steps),
            "outputs": tuple(output.value for output in self.outputs),
            "grants_authority": self.grants_authority,
            "can_execute_tools": self.can_execute_tools,
            "supports_mutation": self.supports_mutation,
            "production_write": self.production_write,
            "answer_path": self.answer_path,
            "mcp_exposed": self.mcp_exposed,
        }


@dataclass(frozen=True, slots=True)
class SkillPlan:
    skill_name: str
    step_count: int
    required_capabilities: tuple[str, ...]
    steps: tuple[SkillStep, ...]
    outputs: tuple[SkillOutputKind, ...]
    authority_status: str = "NO_AUTHORITY_GRANTED"
    execution_status: str = "DESCRIPTIVE_ONLY"
    prohibited_actions: tuple[str, ...] = _DEFAULT_PROHIBITED_ACTIONS

    def __post_init__(self) -> None:
        _require_skill_name(self.skill_name)
        if self.step_count != len(self.steps):
            raise SkillRuntimeError("step_count must equal number of steps")
        _require_capability_tuple(self.required_capabilities)
        if self.authority_status != "NO_AUTHORITY_GRANTED":
            raise ForbiddenSkillError("skill plan must not grant authority")
        if self.execution_status != "DESCRIPTIVE_ONLY":
            raise ForbiddenSkillError("skill plan must not execute")
        _require_safe_id_tuple("prohibited_actions", self.prohibited_actions)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SKILL_RUNTIME_SCHEMA_VERSION,
            "skill_name": self.skill_name,
            "step_count": self.step_count,
            "required_capabilities": self.required_capabilities,
            "steps": tuple(step.as_dict() for step in self.steps),
            "outputs": tuple(output.value for output in self.outputs),
            "authority_status": self.authority_status,
            "execution_status": self.execution_status,
            "prohibited_actions": self.prohibited_actions,
        }


class SkillRegistry:
    """Stage 7 descriptor-only ops skill registry.

    This registry has no run/execute/invoke method. It can produce a plan, but
    it cannot call tools, grant authorization, obtain credentials, write state,
    promote releases, or expose MCP.
    """

    def __init__(self, *, tool_registry: ToolRegistry | None = None) -> None:
        self._tool_registry = tool_registry or build_stage5_readonly_registry()
        self._skills: dict[str, SkillDescriptor] = {}

    def register(self, descriptor: SkillDescriptor) -> SkillDescriptor:
        _validate_skill_descriptor(descriptor, tool_registry=self._tool_registry)
        if descriptor.name in self._skills:
            raise DuplicateSkillError(f"skill already registered: {descriptor.name}")
        self._skills[descriptor.name] = descriptor
        return descriptor

    def resolve(self, name: str) -> SkillDescriptor:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise UnknownSkillError(f"unknown skill: {name}") from exc

    def list(self, *, category: SkillCategory | None = None) -> tuple[SkillDescriptor, ...]:
        values = self._skills.values()
        if category is not None:
            values = (skill for skill in values if skill.category is category)
        return tuple(sorted(values, key=lambda skill: skill.name))

    def describe(self, name: str) -> dict[str, object]:
        return self.resolve(name).as_dict()

    def plan(self, name: str) -> SkillPlan:
        descriptor = self.resolve(name)
        return SkillPlan(
            skill_name=descriptor.name,
            step_count=len(descriptor.steps),
            required_capabilities=descriptor.allowed_capabilities,
            steps=descriptor.steps,
            outputs=descriptor.outputs,
        )

    def __len__(self) -> int:
        return len(self._skills)


def build_stage7_ops_skill_registry(
    *,
    tool_registry: ToolRegistry | None = None,
) -> SkillRegistry:
    registry = SkillRegistry(tool_registry=tool_registry)
    for descriptor in stage7_ops_skill_descriptors():
        registry.register(descriptor)
    return registry


def stage7_ops_skill_descriptors() -> tuple[SkillDescriptor, ...]:
    return (
        _skill_investigate_answer_failure(),
        _skill_investigate_retrieval_failure(),
        _skill_diagnose_latency(),
        _skill_run_quality_gate(),
    )


def deferred_stage7_skill_names() -> tuple[str, ...]:
    return tuple(sorted(_DEFERRED_SKILLS))


def _skill_investigate_answer_failure() -> SkillDescriptor:
    caps = (
        "runtime.get_trace",
        "evidence.verify",
        "evidence.inspect",
        "runtime.get_budget",
    )
    return SkillDescriptor(
        name="investigate-answer-failure",
        description="Plan a report-only investigation of cited-answer or abstention failures.",
        category=SkillCategory.OPS_INVESTIGATION,
        allowed_capabilities=caps,
        outputs=(SkillOutputKind.INVESTIGATION_REPORT, SkillOutputKind.FOLLOWUP_CANDIDATE),
        steps=(
            SkillStep(
                "collect-runtime-trace",
                "Collect sanitized runtime trace metadata",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_trace",),
            ),
            SkillStep(
                "inspect-verification",
                "Inspect existing verification decision metadata",
                SkillStepKind.IDENTIFY_GAPS,
                ("evidence.verify",),
            ),
            SkillStep(
                "inspect-evidence-plan",
                "Inspect existing evidence coverage and gap metadata",
                SkillStepKind.IDENTIFY_GAPS,
                ("evidence.inspect",),
            ),
            SkillStep(
                "write-report",
                "Produce an investigation report and candidate next actions only",
                SkillStepKind.REPORT_ONLY,
                (),
            ),
        ),
    )


def _skill_investigate_retrieval_failure() -> SkillDescriptor:
    caps = (
        "runtime.get_trace",
        "evidence.inspect",
        "knowledge.search",
        "knowledge.expand",
    )
    return SkillDescriptor(
        name="investigate-retrieval-failure",
        description=(
            "Plan a report-only investigation of retrieval gaps using "
            "read-only domain capability metadata."
        ),
        category=SkillCategory.OPS_INVESTIGATION,
        allowed_capabilities=caps,
        outputs=(SkillOutputKind.INVESTIGATION_REPORT, SkillOutputKind.FOLLOWUP_CANDIDATE),
        steps=(
            SkillStep(
                "collect-runtime-trace",
                "Collect sanitized runtime trace metadata",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_trace",),
            ),
            SkillStep(
                "inspect-evidence-gaps",
                "Inspect existing evidence gap metadata",
                SkillStepKind.IDENTIFY_GAPS,
                ("evidence.inspect",),
            ),
            SkillStep(
                "compare-readonly-search",
                "Compare read-only knowledge identities without answer publication",
                SkillStepKind.COMPARE_SIGNALS,
                ("knowledge.search", "knowledge.expand"),
            ),
            SkillStep(
                "write-report",
                "Produce retrieval failure report and candidate hypotheses only",
                SkillStepKind.REPORT_ONLY,
                (),
            ),
        ),
    )


def _skill_diagnose_latency() -> SkillDescriptor:
    caps = (
        "runtime.get_trace",
        "runtime.get_budget",
        "runtime.get_health",
    )
    return SkillDescriptor(
        name="diagnose-latency",
        description=(
            "Plan a report-only latency diagnosis from sanitized trace, "
            "budget, and health metadata."
        ),
        category=SkillCategory.OPS_DIAGNOSIS,
        allowed_capabilities=caps,
        outputs=(SkillOutputKind.DIAGNOSTIC_REPORT, SkillOutputKind.FOLLOWUP_CANDIDATE),
        steps=(
            SkillStep(
                "collect-runtime-trace",
                "Collect sanitized runtime trace metadata",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_trace",),
            ),
            SkillStep(
                "inspect-budget",
                "Inspect normalized compute and provider budget metadata",
                SkillStepKind.DIAGNOSE_BUDGET,
                ("runtime.get_budget",),
            ),
            SkillStep(
                "inspect-health",
                "Inspect domain-level runtime health metadata",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_health",),
            ),
            SkillStep(
                "write-diagnosis",
                "Produce latency diagnosis and candidate next checks only",
                SkillStepKind.REPORT_ONLY,
                (),
            ),
        ),
    )


def _skill_run_quality_gate() -> SkillDescriptor:
    caps = (
        "runtime.get_health",
        "runtime.get_trace",
        "runtime.get_budget",
        "evidence.verify",
    )
    return SkillDescriptor(
        name="run-quality-gate",
        description="Plan a quality-gate report without executing evals or promoting releases.",
        category=SkillCategory.OPS_QUALITY_GATE,
        allowed_capabilities=caps,
        outputs=(SkillOutputKind.QUALITY_GATE_REPORT, SkillOutputKind.FOLLOWUP_CANDIDATE),
        steps=(
            SkillStep(
                "inspect-health",
                "Inspect domain-level health metadata before any external gate",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_health",),
            ),
            SkillStep(
                "collect-trace-sample",
                "Collect sanitized trace/budget metadata for gate context",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_trace", "runtime.get_budget"),
            ),
            SkillStep(
                "inspect-verifier-summary",
                "Inspect existing verification metadata only",
                SkillStepKind.COLLECT_METADATA,
                ("evidence.verify",),
            ),
            SkillStep(
                "write-gate-plan",
                "Produce a quality-gate command/report candidate only",
                SkillStepKind.CANDIDATE_ONLY,
                (),
            ),
        ),
    )


def _validate_skill_descriptor(descriptor: SkillDescriptor, *, tool_registry: ToolRegistry) -> None:
    if not isinstance(descriptor, SkillDescriptor):
        raise SkillRuntimeError("registry accepts SkillDescriptor instances only")
    if descriptor.name in _DEFERRED_SKILLS:
        raise ForbiddenSkillError(f"skill is deferred beyond Stage 7: {descriptor.name}")
    if descriptor.name not in _ALLOWED_STAGE7_OPS_SKILLS:
        tokens = tuple(token for token in descriptor.name.split("-") if token)
        if any(token in _FORBIDDEN_SKILL_TOKENS for token in tokens):
            raise ForbiddenSkillError(f"skill crosses Stage 7 ops-only boundary: {descriptor.name}")
    for capability in descriptor.allowed_capabilities:
        tool = tool_registry.resolve(capability)
        if not tool.read_only or tool.supports_mutation or tool.exposes_raw_infra:
            raise ForbiddenSkillError(f"skill capability is not safe read-only: {capability}")
        if not tool.requires_authorization:
            raise ForbiddenSkillError(
                f"skill capability must preserve authorization boundary: {capability}"
            )


def _require_skill_name(value: object) -> None:
    if not isinstance(value, str) or not _SKILL_NAME_RE.fullmatch(value):
        raise SkillRuntimeError("skill name must be lower-case kebab-case")


def _require_safe_id(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise SkillRuntimeError(f"{name} must be a safe identifier")


def _require_safe_id_tuple(name: str, values: object) -> None:
    if not isinstance(values, tuple):
        raise SkillRuntimeError(f"{name} must be a tuple")
    for value in values:
        _require_safe_id(name, value)


def _require_capability_tuple(values: object) -> None:
    if not isinstance(values, tuple):
        raise SkillRuntimeError("capabilities must be a tuple")
    if len(set(values)) != len(values):
        raise SkillRuntimeError("capabilities must not contain duplicates")
    for value in values:
        if not isinstance(value, str) or not _CAPABILITY_RE.fullmatch(value):
            raise SkillRuntimeError("capability names must use domain.action form")


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise SkillRuntimeError(f"{name} must be bool")


__all__ = [
    "SKILL_RUNTIME_SCHEMA_VERSION",
    "SkillRuntimeError",
    "DuplicateSkillError",
    "UnknownSkillError",
    "ForbiddenSkillError",
    "SkillCategory",
    "SkillStepKind",
    "SkillOutputKind",
    "SkillStep",
    "SkillDescriptor",
    "SkillPlan",
    "SkillRegistry",
    "build_stage7_ops_skill_registry",
    "stage7_ops_skill_descriptors",
    "deferred_stage7_skill_names",
]
