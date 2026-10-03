from __future__ import annotations

import re
from collections.abc import Iterable

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
    RuntimeHealthInput,
    RuntimeHealthOutput,
    RuntimeLookupInput,
    RuntimeTraceOutput,
    ToolContractError,
    ToolDescriptor,
    ToolDomain,
    ToolRiskClass,
)

_FORBIDDEN_EXACT = frozenset(
    {
        "release.promote",
        "release.rollback",
        "ingestion.finalize",
        "qdrant.raw_search",
        "r2.raw_get",
        "sqlite.raw_query",
        "admin.mutate",
    }
)
_FORBIDDEN_NAMESPACE_TOKENS = frozenset(
    {
        "qdrant",
        "r2",
        "sqlite",
        "admin",
        "release",
        "ingestion",
        "database",
        "storage",
        "objectstore",
        "object_store",
        "filesystem",
        "docker",
        "process",
    }
)
_FORBIDDEN_ACTION_TOKENS = frozenset(
    {
        "raw",
        "sql",
        "mutate",
        "mutation",
        "write",
        "delete",
        "remove",
        "update",
        "create",
        "put",
        "patch",
        "post",
        "promote",
        "promotion",
        "rollback",
        "finalize",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "env",
        "environment",
        "execute",
        "exec",
        "shell",
    }
)
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


class ToolRegistryError(ValueError):
    """Base error for native Stage 5 registry failures."""


class DuplicateCapabilityError(ToolRegistryError):
    """Raised when a capability is registered twice."""


class UnknownCapabilityError(ToolRegistryError):
    """Raised when a capability is not present in the registry."""


class ForbiddenCapabilityError(ToolRegistryError):
    """Raised when a capability violates the Stage 5 domain/read-only boundary."""


class ToolRegistry:
    """Descriptor-only native registry.

    The registry intentionally has no execute/invoke path. It describes capability
    shape and risk metadata but does not grant authority, obtain credentials, call
    providers, or touch infrastructure.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor) -> ToolDescriptor:
        _validate_registry_descriptor(descriptor)
        if descriptor.name in self._descriptors:
            raise DuplicateCapabilityError(
                f"capability already registered: {descriptor.name}"
            )
        self._descriptors[descriptor.name] = descriptor
        return descriptor

    def resolve(self, name: str) -> ToolDescriptor:
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise UnknownCapabilityError(f"unknown capability: {name}") from exc

    def list(self, *, domain: ToolDomain | None = None) -> tuple[ToolDescriptor, ...]:
        values: Iterable[ToolDescriptor] = self._descriptors.values()
        if domain is not None:
            values = (item for item in values if item.domain is domain)
        return tuple(sorted(values, key=lambda item: item.name))

    def describe(self, name: str) -> dict[str, object]:
        return self.resolve(name).as_dict()

    def __len__(self) -> int:
        return len(self._descriptors)


def build_stage5_readonly_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for descriptor in stage5_tool_descriptors():
        registry.register(descriptor)
    return registry


def stage5_tool_descriptors() -> tuple[ToolDescriptor, ...]:
    return (
        ToolDescriptor(
            name="knowledge.search",
            description=(
                "Search through an injected domain knowledge provider and return "
                "sanitized knowledge/source/locator identities only."
            ),
            domain=ToolDomain.KNOWLEDGE,
            read_only=True,
            risk_class=ToolRiskClass.DOMAIN_METADATA_READ,
            input_contract=KnowledgeSearchInput,
            output_contract=KnowledgeSearchOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
        ToolDescriptor(
            name="knowledge.expand",
            description=(
                "Expand already-known domain identifiers through an injected "
                "read-only knowledge provider without starting an agentic loop."
            ),
            domain=ToolDomain.KNOWLEDGE,
            read_only=True,
            risk_class=ToolRiskClass.DOMAIN_METADATA_READ,
            input_contract=KnowledgeExpandInput,
            output_contract=KnowledgeExpandOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
        ToolDescriptor(
            name="evidence.inspect",
            description=(
                "Inspect an already-produced Stage 3 evidence plan as identities, "
                "counts, coverage and gap metadata without evidence bodies."
            ),
            domain=ToolDomain.EVIDENCE,
            read_only=True,
            risk_class=ToolRiskClass.EVIDENCE_METADATA_READ,
            input_contract=EvidenceInspectInput,
            output_contract=EvidenceInspectOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
        ToolDescriptor(
            name="evidence.verify",
            description=(
                "Inspect an already-produced verification decision without rerunning "
                "the verifier or answer path."
            ),
            domain=ToolDomain.EVIDENCE,
            read_only=True,
            risk_class=ToolRiskClass.EVIDENCE_METADATA_READ,
            input_contract=EvidenceVerifyInput,
            output_contract=EvidenceVerifyOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
        ToolDescriptor(
            name="runtime.get_trace",
            description=(
                "Return the existing sanitized M27 decision-trace shape only."
            ),
            domain=ToolDomain.RUNTIME,
            read_only=True,
            risk_class=ToolRiskClass.RUNTIME_OBSERVABILITY_READ,
            input_contract=RuntimeLookupInput,
            output_contract=RuntimeTraceOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
        ToolDescriptor(
            name="runtime.get_budget",
            description=(
                "Return normalized compute/budget metadata from an existing "
                "sanitized runtime trace."
            ),
            domain=ToolDomain.RUNTIME,
            read_only=True,
            risk_class=ToolRiskClass.RUNTIME_OBSERVABILITY_READ,
            input_contract=RuntimeLookupInput,
            output_contract=RuntimeBudgetOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
        ToolDescriptor(
            name="runtime.get_health",
            description=(
                "Return a domain-level health snapshot containing status, freshness "
                "and dependency counts only."
            ),
            domain=ToolDomain.RUNTIME,
            read_only=True,
            risk_class=ToolRiskClass.RUNTIME_OBSERVABILITY_READ,
            input_contract=RuntimeHealthInput,
            output_contract=RuntimeHealthOutput,
            requires_authorization=True,
            supports_network=False,
            supports_mutation=False,
            exposes_raw_infra=False,
        ),
    )


def _validate_registry_descriptor(descriptor: ToolDescriptor) -> None:
    if not isinstance(descriptor, ToolDescriptor):
        raise ToolRegistryError("registry accepts ToolDescriptor instances only")

    if descriptor.name in _FORBIDDEN_EXACT:
        raise ForbiddenCapabilityError(
            f"forbidden Stage 5 capability: {descriptor.name}"
        )

    namespace, action = descriptor.name.split(".", 1)
    if namespace not in {domain.value for domain in ToolDomain}:
        raise ForbiddenCapabilityError(
            f"namespace is not an agent-facing Stage 5 domain: {namespace}"
        )
    if namespace != descriptor.domain.value:
        raise ForbiddenCapabilityError("capability namespace must match descriptor domain")


    tokens = tuple(
        token
        for token in _TOKEN_SPLIT_RE.split(f"{namespace}.{action}".casefold())
        if token
    )
    if any(token in _FORBIDDEN_NAMESPACE_TOKENS for token in tokens):
        raise ForbiddenCapabilityError(
            f"capability exposes a forbidden infrastructure/admin namespace: {descriptor.name}"
        )
    if any(token in _FORBIDDEN_ACTION_TOKENS for token in tokens):
        raise ForbiddenCapabilityError(
            f"capability action violates the Stage 5 read-only/domain boundary: {descriptor.name}"
        )

    if descriptor.read_only is not True:
        raise ForbiddenCapabilityError("registered Stage 5 tools must be read-only")
    if descriptor.supports_mutation is not False:
        raise ForbiddenCapabilityError(
            "registered Stage 5 tools must not support mutation"
        )
    if descriptor.exposes_raw_infra is not False:
        raise ForbiddenCapabilityError(
            "registered Stage 5 tools must not expose raw infrastructure"
        )
    if descriptor.requires_authorization is not True:
        raise ForbiddenCapabilityError(
            "Stage 5 capability descriptors must preserve the authorization boundary"
        )


def clone_descriptor(
    descriptor: ToolDescriptor,
    *,
    name: str | None = None,
    read_only: bool | None = None,
    supports_mutation: bool | None = None,
    exposes_raw_infra: bool | None = None,
    requires_authorization: bool | None = None,
) -> ToolDescriptor:
    """Test/helper constructor that still runs ToolDescriptor validation."""

    try:
        return ToolDescriptor(
            name=name if name is not None else descriptor.name,
            description=descriptor.description,
            domain=descriptor.domain,
            read_only=read_only if read_only is not None else descriptor.read_only,
            risk_class=descriptor.risk_class,
            input_contract=descriptor.input_contract,
            output_contract=descriptor.output_contract,
            requires_authorization=(
                requires_authorization
                if requires_authorization is not None
                else descriptor.requires_authorization
            ),
            supports_network=descriptor.supports_network,
            supports_mutation=(
                supports_mutation
                if supports_mutation is not None
                else descriptor.supports_mutation
            ),
            exposes_raw_infra=(
                exposes_raw_infra
                if exposes_raw_infra is not None
                else descriptor.exposes_raw_infra
            ),
        )
    except ToolContractError:
        raise


__all__ = [
    "ToolRegistry",
    "ToolRegistryError",
    "DuplicateCapabilityError",
    "UnknownCapabilityError",
    "ForbiddenCapabilityError",
    "build_stage5_readonly_registry",
    "stage5_tool_descriptors",
    "clone_descriptor",
]
