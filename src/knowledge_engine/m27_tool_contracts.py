from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any

from .m27_context_runtime_contracts import (
    EvidenceIdentity,
    EvidencePlanningResult,
    VerificationDecision,
)
from .m27_decision_trace import DecisionTraceEvent

TOOL_CONTRACT_SCHEMA_VERSION = "m27-native-readonly-tool/v1"

_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,256}$")
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class ToolDomain(StrEnum):
    KNOWLEDGE = "knowledge"
    EVIDENCE = "evidence"
    RUNTIME = "runtime"


class ToolRiskClass(StrEnum):
    DOMAIN_METADATA_READ = "DOMAIN_METADATA_READ"
    EVIDENCE_METADATA_READ = "EVIDENCE_METADATA_READ"
    RUNTIME_OBSERVABILITY_READ = "RUNTIME_OBSERVABILITY_READ"


class ToolContractError(ValueError):
    """Raised when a native capability contract violates the Stage 5 boundary."""


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    domain: ToolDomain
    read_only: bool
    risk_class: ToolRiskClass
    input_contract: type[Any]
    output_contract: type[Any]
    requires_authorization: bool
    supports_network: bool
    supports_mutation: bool
    exposes_raw_infra: bool

    def __post_init__(self) -> None:
        if not _CAPABILITY_RE.fullmatch(self.name):
            raise ToolContractError("capability name must use lower-case domain.action form")
        if not self.description.strip():
            raise ToolContractError("capability description must not be empty")
        if not isinstance(self.domain, ToolDomain):
            raise ToolContractError("domain must be a ToolDomain")
        if not isinstance(self.risk_class, ToolRiskClass):
            raise ToolContractError("risk_class must be a ToolRiskClass")
        if not is_dataclass(self.input_contract):
            raise ToolContractError("input_contract must be a dataclass type")
        if not is_dataclass(self.output_contract):
            raise ToolContractError("output_contract must be a dataclass type")
        for name, value in (
            ("read_only", self.read_only),
            ("requires_authorization", self.requires_authorization),
            ("supports_network", self.supports_network),
            ("supports_mutation", self.supports_mutation),
            ("exposes_raw_infra", self.exposes_raw_infra),
        ):
            if not isinstance(value, bool):
                raise ToolContractError(f"{name} must be bool")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": TOOL_CONTRACT_SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "domain": self.domain.value,
            "read_only": self.read_only,
            "risk_class": self.risk_class.value,
            "input_contract": self.input_contract.__name__,
            "output_contract": self.output_contract.__name__,
            "requires_authorization": self.requires_authorization,
            "supports_network": self.supports_network,
            "supports_mutation": self.supports_mutation,
            "exposes_raw_infra": self.exposes_raw_infra,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeSearchInput:
    request_token: str
    max_results: int = 8
    scope_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_safe_id("request_token", self.request_token)
        _require_positive_limit("max_results", self.max_results)
        _require_safe_id_tuple("scope_ids", self.scope_ids)


@dataclass(frozen=True, slots=True)
class KnowledgeExpandInput:
    seed_ids: tuple[str, ...]
    max_results: int = 8

    def __post_init__(self) -> None:
        _require_safe_id_tuple("seed_ids", self.seed_ids, allow_empty=False)
        _require_positive_limit("max_results", self.max_results)


@dataclass(frozen=True, slots=True)
class KnowledgeItemRef:
    knowledge_id: str
    source_identity: str | None = None
    locator_id: str | None = None
    evidence_type: str | None = None

    def __post_init__(self) -> None:
        _require_safe_id("knowledge_id", self.knowledge_id)
        _require_optional_safe_id("source_identity", self.source_identity)
        _require_optional_safe_id("locator_id", self.locator_id)
        _require_optional_safe_id("evidence_type", self.evidence_type)


@dataclass(frozen=True, slots=True)
class KnowledgeSearchOutput:
    items: tuple[KnowledgeItemRef, ...]
    total_count: int
    truncated: bool = False

    def __post_init__(self) -> None:
        _require_items(self.items)
        _require_nonnegative_int("total_count", self.total_count)
        _require_bool("truncated", self.truncated)


@dataclass(frozen=True, slots=True)
class KnowledgeExpandOutput:
    items: tuple[KnowledgeItemRef, ...]
    total_count: int
    truncated: bool = False

    def __post_init__(self) -> None:
        _require_items(self.items)
        _require_nonnegative_int("total_count", self.total_count)
        _require_bool("truncated", self.truncated)


@dataclass(frozen=True, slots=True)
class EvidenceInspectInput:
    planning_result: EvidencePlanningResult


@dataclass(frozen=True, slots=True)
class EvidenceInspectOutput:
    selected_evidence: tuple[EvidenceIdentity, ...]
    selected_evidence_count: int
    distinct_source_count: int | str
    requirement_count: int | str
    covered_requirement_count: int | str
    missing_requirement_count: int | str
    coverage_status: str
    sufficiency_status: str
    bounded_recovery_used: bool | str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonnegative_int("selected_evidence_count", self.selected_evidence_count)
        _require_count_or_unavailable("distinct_source_count", self.distinct_source_count)
        _require_count_or_unavailable("requirement_count", self.requirement_count)
        _require_count_or_unavailable(
            "covered_requirement_count", self.covered_requirement_count
        )
        _require_count_or_unavailable(
            "missing_requirement_count", self.missing_requirement_count
        )
        _require_safe_code_or_unavailable("coverage_status", self.coverage_status)
        _require_safe_code_or_unavailable("sufficiency_status", self.sufficiency_status)
        if not isinstance(self.bounded_recovery_used, (bool, str)):
            raise ToolContractError("bounded_recovery_used must be bool or unavailable marker")
        _require_safe_code_tuple("reason_codes", self.reason_codes)


@dataclass(frozen=True, slots=True)
class EvidenceVerifyInput:
    verification_decision: VerificationDecision


@dataclass(frozen=True, slots=True)
class EvidenceVerifyOutput:
    status: str
    terminal_status: str
    safe_abstention: bool | str
    material_claim_support_verified: bool | str
    citation_locator_valid: bool | str
    unsupported_accepted_claims: int | str
    repair_attempted: bool | str
    citation_count: int | str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_safe_code_or_unavailable("status", self.status)
        _require_safe_code_or_unavailable("terminal_status", self.terminal_status)
        _require_bool_or_unavailable("safe_abstention", self.safe_abstention)
        _require_bool_or_unavailable(
            "material_claim_support_verified",
            self.material_claim_support_verified,
        )
        _require_bool_or_unavailable("citation_locator_valid", self.citation_locator_valid)
        _require_count_or_unavailable(
            "unsupported_accepted_claims", self.unsupported_accepted_claims
        )
        _require_bool_or_unavailable("repair_attempted", self.repair_attempted)
        _require_count_or_unavailable("citation_count", self.citation_count)
        _require_safe_code_tuple("reason_codes", self.reason_codes)


@dataclass(frozen=True, slots=True)
class RuntimeLookupInput:
    trace_id: str

    def __post_init__(self) -> None:
        _require_safe_id("trace_id", self.trace_id)


@dataclass(frozen=True, slots=True)
class RuntimeHealthInput:
    scope: str = "runtime"

    def __post_init__(self) -> None:
        _require_safe_id("scope", self.scope)


@dataclass(frozen=True, slots=True)
class RuntimeTraceOutput:
    trace_id: str
    route: str
    reason_code: str
    compute_tier: str
    deadline_budget_class: str
    provider_budget_class: str
    provider_attempt_count: int | None
    context_sources: tuple[str, ...]
    evidence_count: int
    citation_count: int
    status_class: str
    safe_abstention_outcome: str
    guard_outcomes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_safe_id("trace_id", self.trace_id)
        for name, value in (
            ("route", self.route),
            ("reason_code", self.reason_code),
            ("compute_tier", self.compute_tier),
            ("deadline_budget_class", self.deadline_budget_class),
            ("provider_budget_class", self.provider_budget_class),
            ("status_class", self.status_class),
            ("safe_abstention_outcome", self.safe_abstention_outcome),
        ):
            _require_safe_code_or_unavailable(name, value)
        if self.provider_attempt_count is not None:
            _require_nonnegative_int("provider_attempt_count", self.provider_attempt_count)
        _require_safe_code_tuple("context_sources", self.context_sources)
        _require_nonnegative_int("evidence_count", self.evidence_count)
        _require_nonnegative_int("citation_count", self.citation_count)
        for guard, outcome in self.guard_outcomes:
            _require_safe_code_or_unavailable("guard", guard)
            _require_safe_code_or_unavailable("guard_outcome", outcome)


@dataclass(frozen=True, slots=True)
class RuntimeBudgetOutput:
    trace_id: str
    compute_tier: str
    deadline_budget_class: str
    provider_budget_class: str
    provider_attempt_count: int | None
    provider_attempt_class: str

    def __post_init__(self) -> None:
        _require_safe_id("trace_id", self.trace_id)
        for name, value in (
            ("compute_tier", self.compute_tier),
            ("deadline_budget_class", self.deadline_budget_class),
            ("provider_budget_class", self.provider_budget_class),
            ("provider_attempt_class", self.provider_attempt_class),
        ):
            _require_safe_code_or_unavailable(name, value)
        if self.provider_attempt_count is not None:
            _require_nonnegative_int("provider_attempt_count", self.provider_attempt_count)


@dataclass(frozen=True, slots=True)
class RuntimeHealthDependency:
    key: str
    status: str
    freshness: str

    def __post_init__(self) -> None:
        _require_safe_id("key", self.key)
        _require_safe_code_or_unavailable("status", self.status)
        _require_safe_code_or_unavailable("freshness", self.freshness)


@dataclass(frozen=True, slots=True)
class RuntimeHealthOutput:
    overall_status: str
    freshness: str
    dependency_count: int
    dependencies: tuple[RuntimeHealthDependency, ...]

    def __post_init__(self) -> None:
        _require_safe_code_or_unavailable("overall_status", self.overall_status)
        _require_safe_code_or_unavailable("freshness", self.freshness)
        _require_nonnegative_int("dependency_count", self.dependency_count)
        if self.dependency_count != len(self.dependencies):
            raise ToolContractError("dependency_count must match dependencies")


def forbidden_payload_field_names() -> frozenset[str]:
    return frozenset(
        {
            "query",
            "raw_query",
            "answer",
            "raw_answer",
            "evidence_text",
            "full_evidence_text",
            "source_text",
            "full_source_text",
            "secret",
            "api_key",
            "token",
            "credential",
            "environment_value",
            "env_value",
            "private_payload",
            "payload",
            "raw_sql",
            "sql",
            "filesystem_path",
            "object_key",
            "http_endpoint",
        }
    )


def contract_field_names(contract: type[Any]) -> frozenset[str]:
    if not is_dataclass(contract):
        raise ToolContractError("contract must be a dataclass type")
    return frozenset(item.name for item in fields(contract))


def _require_safe_id(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ToolContractError(f"{name} must be a sanitized opaque/domain identifier")


def _require_optional_safe_id(name: str, value: object) -> None:
    if value is None:
        return
    _require_safe_id(name, value)


def _require_safe_id_tuple(
    name: str,
    values: object,
    *,
    allow_empty: bool = True,
) -> None:
    if not isinstance(values, tuple):
        raise ToolContractError(f"{name} must be a tuple")
    if not allow_empty and not values:
        raise ToolContractError(f"{name} must not be empty")
    for value in values:
        _require_safe_id(name, value)


def _require_safe_code_or_unavailable(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SAFE_CODE_RE.fullmatch(value):
        raise ToolContractError(f"{name} must be a sanitized enum/code")


def _require_safe_code_tuple(name: str, values: object) -> None:
    if not isinstance(values, tuple):
        raise ToolContractError(f"{name} must be a tuple")
    for value in values:
        _require_safe_code_or_unavailable(name, value)


def _require_positive_limit(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ToolContractError(f"{name} must be an integer in [1, 100]")


def _require_nonnegative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ToolContractError(f"{name} must be a non-negative integer")


def _require_count_or_unavailable(name: str, value: object) -> None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return
    _require_safe_code_or_unavailable(name, value)


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ToolContractError(f"{name} must be bool")


def _require_bool_or_unavailable(name: str, value: object) -> None:
    if isinstance(value, bool):
        return
    _require_safe_code_or_unavailable(name, value)


def _require_items(items: object) -> None:
    if not isinstance(items, tuple) or any(
        not isinstance(item, KnowledgeItemRef) for item in items
    ):
        raise ToolContractError("items must be a tuple of KnowledgeItemRef")


__all__ = [
    "TOOL_CONTRACT_SCHEMA_VERSION",
    "ToolDomain",
    "ToolRiskClass",
    "ToolContractError",
    "ToolDescriptor",
    "KnowledgeSearchInput",
    "KnowledgeExpandInput",
    "KnowledgeItemRef",
    "KnowledgeSearchOutput",
    "KnowledgeExpandOutput",
    "EvidenceInspectInput",
    "EvidenceInspectOutput",
    "EvidenceVerifyInput",
    "EvidenceVerifyOutput",
    "RuntimeLookupInput",
    "RuntimeHealthInput",
    "RuntimeTraceOutput",
    "RuntimeBudgetOutput",
    "RuntimeHealthDependency",
    "RuntimeHealthOutput",
    "DecisionTraceEvent",
    "forbidden_payload_field_names",
    "contract_field_names",
]
