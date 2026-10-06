from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .m27_readonly_tools import EvidenceProvider, KnowledgeProvider, RuntimeProvider
from .m27_tool_contracts import (
    EvidenceInspectInput,
    EvidenceVerifyInput,
    KnowledgeExpandInput,
    KnowledgeSearchInput,
    RuntimeHealthInput,
    RuntimeLookupInput,
    ToolDescriptor,
)
from .m27_tool_registry import ToolRegistry, build_stage5_readonly_registry

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class ToolExecutionError(RuntimeError):
    """Base error for the M27 read-only execution boundary."""


class ToolAuthorizationError(ToolExecutionError):
    """Raised when deterministic policy has not authorized a read-only call."""


class ToolMutationBlockedError(ToolExecutionError):
    """Raised when a descriptor crosses the read-only/no-infra boundary."""


class ToolProviderUnavailableError(ToolExecutionError):
    """Raised when an approved provider has not been injected."""


@dataclass(frozen=True, slots=True)
class ToolExecutionPolicy:
    """Deterministic authorization for one composed runtime run."""

    authorized_capabilities: tuple[str, ...]
    authorization_token: str
    isolated_runtime: bool = True
    read_only_only: bool = True
    allow_network: bool = False
    allow_mutation: bool = False

    def __post_init__(self) -> None:
        if not self.authorized_capabilities:
            raise ToolAuthorizationError("at least one capability must be authorized")
        if tuple(sorted(set(self.authorized_capabilities))) != self.authorized_capabilities:
            raise ToolAuthorizationError("authorized_capabilities must be unique and sorted")
        if not _SAFE_TOKEN_RE.fullmatch(self.authorization_token):
            raise ToolAuthorizationError("authorization_token must be sanitized")
        for capability in self.authorized_capabilities:
            if not _SAFE_TOKEN_RE.fullmatch(capability):
                raise ToolAuthorizationError("capability names must be sanitized")
        if not self.isolated_runtime:
            raise ToolAuthorizationError("M27 tool execution requires isolated runtime")
        if not self.read_only_only or self.allow_mutation or self.allow_network:
            raise ToolAuthorizationError("M27 tool execution is read-only and network-free")

    def require(self, descriptor: ToolDescriptor, *, authorization_token: str) -> None:
        _assert_read_only_descriptor(descriptor)
        if authorization_token != self.authorization_token:
            raise ToolAuthorizationError("authorization token mismatch")
        if descriptor.name not in self.authorized_capabilities:
            raise ToolAuthorizationError(f"capability not authorized: {descriptor.name}")


@dataclass(frozen=True, slots=True)
class ToolExecutionRecord:
    capability_name: str
    input_contract: str
    output_contract: str
    read_only: bool
    supports_mutation: bool
    exposes_raw_infra: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "capability_name": self.capability_name,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "read_only": self.read_only,
            "supports_mutation": self.supports_mutation,
            "exposes_raw_infra": self.exposes_raw_infra,
        }



@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    record: ToolExecutionRecord
    output: object



class ReadOnlyToolExecutor:
    """Actual invocation boundary for Stage 5 read-only capabilities."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        knowledge_provider: KnowledgeProvider | None = None,
        evidence_provider: EvidenceProvider | None = None,
        runtime_provider: RuntimeProvider | None = None,
    ) -> None:
        self._registry = registry or build_stage5_readonly_registry()
        self._knowledge_provider = knowledge_provider
        self._evidence_provider = evidence_provider
        self._runtime_provider = runtime_provider

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def execute(
        self,
        capability_name: str,
        request: object,
        *,
        policy: ToolExecutionPolicy,
        authorization_token: str,
    ) -> ToolExecutionResult:
        descriptor = self._registry.resolve(capability_name)
        policy.require(descriptor, authorization_token=authorization_token)
        if not isinstance(request, descriptor.input_contract):
            raise ToolExecutionError(
                f"{capability_name} requires {descriptor.input_contract.__name__}"
            )

        output = self._dispatch(capability_name, request)
        if not isinstance(output, descriptor.output_contract):
            raise ToolExecutionError(
                f"{capability_name} returned non-contract output "
                f"{type(output).__name__}"
            )
        return ToolExecutionResult(
            record=ToolExecutionRecord(
                capability_name=descriptor.name,
                input_contract=descriptor.input_contract.__name__,
                output_contract=descriptor.output_contract.__name__,
                read_only=descriptor.read_only,
                supports_mutation=descriptor.supports_mutation,
                exposes_raw_infra=descriptor.exposes_raw_infra,
            ),
            output=output,
        )

    def _dispatch(self, capability_name: str, request: object) -> object:
        if capability_name == "knowledge.search":
            provider = self._require_provider(self._knowledge_provider, capability_name)
            return provider.search(request)  # type: ignore[arg-type]
        if capability_name == "knowledge.expand":
            provider = self._require_provider(self._knowledge_provider, capability_name)
            return provider.expand(request)  # type: ignore[arg-type]
        if capability_name == "evidence.inspect":
            provider = self._require_provider(self._evidence_provider, capability_name)
            return provider.inspect(request)  # type: ignore[arg-type]
        if capability_name == "evidence.verify":
            provider = self._require_provider(self._evidence_provider, capability_name)
            return provider.verify(request)  # type: ignore[arg-type]
        if capability_name == "runtime.get_trace":
            provider = self._require_provider(self._runtime_provider, capability_name)
            return provider.get_trace(request)  # type: ignore[arg-type]
        if capability_name == "runtime.get_budget":
            provider = self._require_provider(self._runtime_provider, capability_name)
            return provider.get_budget(request)  # type: ignore[arg-type]
        if capability_name == "runtime.get_health":
            provider = self._require_provider(self._runtime_provider, capability_name)
            return provider.get_health(request)  # type: ignore[arg-type]
        raise ToolExecutionError(f"unsupported capability dispatch: {capability_name}")

    @staticmethod
    def _require_provider(provider: Any, capability_name: str) -> Any:
        if provider is None:
            raise ToolProviderUnavailableError(
                f"provider not injected for capability: {capability_name}"
            )
        return provider



def _assert_read_only_descriptor(descriptor: ToolDescriptor) -> None:
    if not descriptor.read_only:
        raise ToolMutationBlockedError("descriptor is not read-only")
    if descriptor.supports_mutation:
        raise ToolMutationBlockedError("descriptor supports mutation")
    if descriptor.exposes_raw_infra:
        raise ToolMutationBlockedError("descriptor exposes raw infrastructure")
    if descriptor.supports_network:
        raise ToolMutationBlockedError("descriptor supports network access")
    if not descriptor.requires_authorization:
        raise ToolAuthorizationError("descriptor must require authorization")


def request_for_capability(
    capability_name: str,
    *,
    request_token: str,
    trace_id: str,
    evidence_planning_result: object,
    verification_decision: object,
    seed_ids: tuple[str, ...] = (),
) -> object:
    """Build the typed Stage 5 request for a sanitized capability name."""

    if capability_name == "knowledge.search":
        return KnowledgeSearchInput(request_token=request_token)
    if capability_name == "knowledge.expand":
        seeds = seed_ids or (request_token,)
        return KnowledgeExpandInput(seed_ids=seeds)
    if capability_name == "evidence.inspect":
        return EvidenceInspectInput(evidence_planning_result)  # type: ignore[arg-type]
    if capability_name == "evidence.verify":
        return EvidenceVerifyInput(verification_decision)  # type: ignore[arg-type]
    if capability_name == "runtime.get_trace":
        return RuntimeLookupInput(trace_id=trace_id)
    if capability_name == "runtime.get_budget":
        return RuntimeLookupInput(trace_id=trace_id)
    if capability_name == "runtime.get_health":
        return RuntimeHealthInput(scope="runtime")
    raise ToolExecutionError(f"no request builder for capability: {capability_name}")


__all__ = [
    "ToolExecutionError",
    "ToolAuthorizationError",
    "ToolMutationBlockedError",
    "ToolProviderUnavailableError",
    "ToolExecutionPolicy",
    "ToolExecutionRecord",
    "ToolExecutionResult",
    "ReadOnlyToolExecutor",
    "request_for_capability",
]
