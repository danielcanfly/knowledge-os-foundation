from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .m27_tool_contracts import (
    ToolDescriptor,
    ToolRiskClass,
    contract_field_names,
    forbidden_payload_field_names,
)

MCP_EXPOSURE_SCHEMA_VERSION = "m27-readonly-mcp-exposure/v1"

_ALLOWED_NATIVE_CAPABILITIES = frozenset(
    {
        "knowledge.search",
        "knowledge.expand",
        "evidence.inspect",
        "evidence.verify",
        "runtime.get_trace",
        "runtime.get_budget",
        "runtime.get_health",
    }
)
_FORBIDDEN_EXACT_NAMES = frozenset(
    {
        "release.promote",
        "release.rollback",
        "ingestion.finalize",
        "ingest-and-update-knowledge",
        "promote-knowledge-release",
        "workspace.write",
        "workspace.read_raw",
        "memory.read",
        "memory.write",
        "agent.run",
        "skill.execute",
        "tool.invoke_raw",
        "qdrant.raw_search",
        "r2.raw_get",
        "sqlite.raw_query",
        "admin.mutate",
        "shell.exec",
        "env.dump",
    }
)
_FORBIDDEN_PREFIXES = (
    "release.",
    "ingestion.",
    "workspace.",
    "memory.",
    "agent.",
    "skill.",
    "tool.",
    "qdrant.",
    "r2.",
    "sqlite.",
    "admin.",
    "docker.",
    "filesystem.",
    "process.",
    "shell.",
    "env.",
    "secret.",
    "credential.",
)
_FORBIDDEN_DESCRIPTOR_TERMS = frozenset(
    {
        "qdrant",
        "sqlite",
        "docker",
        "filesystem",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "environment_value",
        "env_value",
        "object_key",
        "raw_sql",
        "http_endpoint",
    }
)
_SAFE_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class McpExposureError(ValueError):
    """Base error for Stage 9 MCP exposure contract failures."""


class ForbiddenMcpCapabilityError(McpExposureError):
    """Raised when a capability is outside the Stage 9 read-only allowlist."""


class McpExposureMode(StrEnum):
    DISABLED = "DISABLED"
    READ_ONLY_ISOLATED = "READ_ONLY_ISOLATED"


@dataclass(frozen=True, slots=True)
class McpToolInputSchema:
    contract_name: str
    field_names: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_contract_schema(self.contract_name, self.field_names)

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_name": self.contract_name,
            "field_names": self.field_names,
        }


@dataclass(frozen=True, slots=True)
class McpToolOutputSchema:
    contract_name: str
    field_names: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_contract_schema(self.contract_name, self.field_names)

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_name": self.contract_name,
            "field_names": self.field_names,
        }


@dataclass(frozen=True, slots=True)
class McpExposurePolicy:
    enabled: bool = False
    isolated_runtime: bool = False
    isolated_runtime_required: bool = True
    allow_network_server: bool = False
    allow_mutation: bool = False

    def __post_init__(self) -> None:
        values = (
            self.enabled,
            self.isolated_runtime,
            self.isolated_runtime_required,
            self.allow_network_server,
            self.allow_mutation,
        )
        if any(not isinstance(value, bool) for value in values):
            raise McpExposureError("MCP exposure policy fields must be bool")
        if self.isolated_runtime_required is not True:
            raise McpExposureError("Stage 9 always requires an isolated runtime")
        if self.allow_network_server:
            raise McpExposureError("Stage 9 cannot enable a network MCP server")
        if self.allow_mutation:
            raise McpExposureError("Stage 9 cannot enable mutation")
        if self.enabled and not self.isolated_runtime:
            raise McpExposureError(
                "MCP exposure can be enabled only when isolated_runtime is true"
            )

    @property
    def mode(self) -> McpExposureMode:
        if self.enabled:
            return McpExposureMode.READ_ONLY_ISOLATED
        return McpExposureMode.DISABLED

    def as_dict(self) -> dict[str, bool]:
        return {
            "enabled": self.enabled,
            "isolated_runtime": self.isolated_runtime,
            "isolated_runtime_required": self.isolated_runtime_required,
            "allow_network_server": self.allow_network_server,
            "allow_mutation": self.allow_mutation,
        }


DEFAULT_MCP_EXPOSURE_POLICY = McpExposurePolicy()


@dataclass(frozen=True, slots=True)
class McpToolDescriptor:
    schema_version: str
    mcp_name: str
    native_capability_name: str
    description: str
    read_only: bool
    requires_authorization: bool
    supports_mutation: bool
    exposes_raw_infra: bool
    risk_class: str
    input_contract: McpToolInputSchema
    output_contract: McpToolOutputSchema
    default_enabled: bool
    isolated_runtime_required: bool

    def __post_init__(self) -> None:
        if self.schema_version != MCP_EXPOSURE_SCHEMA_VERSION:
            raise McpExposureError("MCP descriptor schema version mismatch")
        validate_mcp_capability_name(self.mcp_name)
        validate_mcp_capability_name(self.native_capability_name)
        if self.mcp_name != self.native_capability_name:
            raise McpExposureError("MCP name must preserve the native capability name")
        if not isinstance(self.description, str) or not self.description.strip():
            raise McpExposureError("MCP descriptor description must not be empty")
        if self.read_only is not True:
            raise McpExposureError("MCP descriptors must remain read-only")
        if self.requires_authorization is not True:
            raise McpExposureError("MCP descriptors must preserve authorization")
        if self.supports_mutation is not False:
            raise McpExposureError("MCP descriptors must not support mutation")
        if self.exposes_raw_infra is not False:
            raise McpExposureError("MCP descriptors must not expose raw infrastructure")
        if self.default_enabled is not False:
            raise McpExposureError("MCP descriptors must be default-off")
        if self.isolated_runtime_required is not True:
            raise McpExposureError("MCP descriptors require the isolated runtime")
        if not isinstance(self.input_contract, McpToolInputSchema):
            raise McpExposureError("input_contract must be McpToolInputSchema")
        if not isinstance(self.output_contract, McpToolOutputSchema):
            raise McpExposureError("output_contract must be McpToolOutputSchema")
        _reject_raw_infra_text(self.description)
        _reject_raw_infra_text(self.input_contract.contract_name)
        _reject_raw_infra_text(self.output_contract.contract_name)
        for field_name in (
            self.input_contract.field_names + self.output_contract.field_names
        ):
            _reject_raw_infra_text(field_name)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mcp_name": self.mcp_name,
            "native_capability_name": self.native_capability_name,
            "description": self.description,
            "read_only": self.read_only,
            "requires_authorization": self.requires_authorization,
            "supports_mutation": self.supports_mutation,
            "exposes_raw_infra": self.exposes_raw_infra,
            "risk_class": self.risk_class,
            "input_contract": self.input_contract.as_dict(),
            "output_contract": self.output_contract.as_dict(),
            "default_enabled": self.default_enabled,
            "isolated_runtime_required": self.isolated_runtime_required,
        }


@dataclass(frozen=True, slots=True)
class McpExposureManifest:
    schema_version: str
    mode: McpExposureMode
    enabled: bool
    tools: tuple[McpToolDescriptor, ...]
    policy: McpExposurePolicy

    def __post_init__(self) -> None:
        if self.schema_version != MCP_EXPOSURE_SCHEMA_VERSION:
            raise McpExposureError("MCP manifest schema version mismatch")
        if not isinstance(self.mode, McpExposureMode):
            raise McpExposureError("mode must be McpExposureMode")
        if not isinstance(self.enabled, bool):
            raise McpExposureError("enabled must be bool")
        if not isinstance(self.policy, McpExposurePolicy):
            raise McpExposureError("policy must be McpExposurePolicy")
        if self.mode is not self.policy.mode or self.enabled is not self.policy.enabled:
            raise McpExposureError("manifest mode/enabled must match policy")
        if not self.enabled and self.tools:
            raise McpExposureError("disabled MCP manifest must expose zero tools")
        if any(not isinstance(item, McpToolDescriptor) for item in self.tools):
            raise McpExposureError("manifest tools must be McpToolDescriptor values")
        names = tuple(item.mcp_name for item in self.tools)
        if names != tuple(sorted(names)):
            raise McpExposureError("manifest tools must be deterministically sorted")
        if len(names) != len(set(names)):
            raise McpExposureError("manifest tool names must be unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "enabled": self.enabled,
            "policy": self.policy.as_dict(),
            "tools": tuple(item.as_dict() for item in self.tools),
        }


class McpExposureRegistry:
    """Descriptor-only Stage 9 view. No execution or provider surface exists."""

    def __init__(self, descriptors: tuple[McpToolDescriptor, ...] = ()) -> None:
        self._descriptors: dict[str, McpToolDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: McpToolDescriptor) -> McpToolDescriptor:
        if not isinstance(descriptor, McpToolDescriptor):
            raise McpExposureError("registry accepts McpToolDescriptor only")
        if descriptor.mcp_name in self._descriptors:
            raise McpExposureError(f"duplicate MCP descriptor: {descriptor.mcp_name}")
        self._descriptors[descriptor.mcp_name] = descriptor
        return descriptor

    def resolve(self, name: str) -> McpToolDescriptor:
        validate_mcp_capability_name(name)
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise McpExposureError(f"unknown MCP descriptor: {name}") from exc

    def list(self) -> tuple[McpToolDescriptor, ...]:
        return tuple(sorted(self._descriptors.values(), key=lambda item: item.mcp_name))

    def describe(self, name: str) -> dict[str, object]:
        return self.resolve(name).as_dict()

    def __len__(self) -> int:
        return len(self._descriptors)


def allowed_stage9_native_capabilities() -> tuple[str, ...]:
    return tuple(sorted(_ALLOWED_NATIVE_CAPABILITIES))


def validate_mcp_capability_name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise ForbiddenMcpCapabilityError("MCP capability name must be a non-empty string")
    normalized = name.casefold()
    if normalized in _FORBIDDEN_EXACT_NAMES or normalized.startswith(_FORBIDDEN_PREFIXES):
        raise ForbiddenMcpCapabilityError(f"forbidden Stage 9 MCP capability: {name}")
    if not _SAFE_CAPABILITY_RE.fullmatch(name):
        raise ForbiddenMcpCapabilityError(
            "MCP capability must preserve lower-case domain.action native naming"
        )
    if name not in _ALLOWED_NATIVE_CAPABILITIES:
        raise ForbiddenMcpCapabilityError(
            f"capability is not in the stable Stage 5 MCP allowlist: {name}"
        )
    return name


def _descriptor_from_native(native: ToolDescriptor) -> McpToolDescriptor:
    """Convert a registry-resolved Stage 5 descriptor to a static MCP descriptor."""

    if not isinstance(native, ToolDescriptor):
        raise McpExposureError("native descriptor must be ToolDescriptor")
    validate_mcp_capability_name(native.name)
    if native.read_only is not True:
        raise McpExposureError("native capability is not read-only")
    if native.requires_authorization is not True:
        raise McpExposureError("native capability lost authorization metadata")
    if native.supports_mutation is not False:
        raise McpExposureError("native capability supports mutation")
    if native.exposes_raw_infra is not False:
        raise McpExposureError("native capability exposes raw infrastructure")

    forbidden_fields = forbidden_payload_field_names()
    input_fields = tuple(sorted(contract_field_names(native.input_contract)))
    output_fields = tuple(sorted(contract_field_names(native.output_contract)))
    if forbidden_fields.intersection(input_fields):
        raise McpExposureError("native input contract contains forbidden raw payload fields")
    if forbidden_fields.intersection(output_fields):
        raise McpExposureError("native output contract contains forbidden raw payload fields")

    return McpToolDescriptor(
        schema_version=MCP_EXPOSURE_SCHEMA_VERSION,
        mcp_name=native.name,
        native_capability_name=native.name,
        description=native.description,
        read_only=True,
        requires_authorization=True,
        supports_mutation=False,
        exposes_raw_infra=False,
        risk_class=_risk_class_value(native.risk_class),
        input_contract=McpToolInputSchema(
            contract_name=native.input_contract.__name__,
            field_names=input_fields,
        ),
        output_contract=McpToolOutputSchema(
            contract_name=native.output_contract.__name__,
            field_names=output_fields,
        ),
        default_enabled=False,
        isolated_runtime_required=True,
    )


def _risk_class_value(value: Any) -> str:
    if isinstance(value, ToolRiskClass):
        return value.value
    raise McpExposureError("native risk_class must be ToolRiskClass")


def _validate_contract_schema(contract_name: object, field_names: object) -> None:
    if not isinstance(contract_name, str) or not contract_name:
        raise McpExposureError("contract_name must be a non-empty string")
    if not isinstance(field_names, tuple):
        raise McpExposureError("field_names must be a tuple")
    if tuple(sorted(field_names)) != field_names:
        raise McpExposureError("contract field_names must be deterministically sorted")
    if len(set(field_names)) != len(field_names):
        raise McpExposureError("contract field_names must be unique")
    forbidden = forbidden_payload_field_names()
    if forbidden.intersection(field_names):
        raise McpExposureError("contract exposes forbidden raw payload fields")
    _reject_raw_infra_text(contract_name)
    for field_name in field_names:
        if not isinstance(field_name, str) or not field_name:
            raise McpExposureError("contract field names must be non-empty strings")
        _reject_raw_infra_text(field_name)


def _reject_raw_infra_text(value: str) -> None:
    normalized = value.casefold()
    tokens = set(re.split(r"[^a-z0-9_]+", normalized))
    if _FORBIDDEN_DESCRIPTOR_TERMS.intersection(tokens):
        raise McpExposureError("MCP descriptor contains forbidden raw infrastructure text")


__all__ = [
    "MCP_EXPOSURE_SCHEMA_VERSION",
    "McpExposureError",
    "ForbiddenMcpCapabilityError",
    "McpExposureMode",
    "McpToolInputSchema",
    "McpToolOutputSchema",
    "McpExposurePolicy",
    "DEFAULT_MCP_EXPOSURE_POLICY",
    "McpToolDescriptor",
    "McpExposureManifest",
    "McpExposureRegistry",
    "allowed_stage9_native_capabilities",
    "validate_mcp_capability_name",
]
