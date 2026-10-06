from __future__ import annotations

from dataclasses import dataclass

from .m27_mcp_contracts import McpExposurePolicy
from .m27_mcp_exposure import build_stage9_mcp_manifest
from .m27_tool_executor import (
    ReadOnlyToolExecutor,
    ToolExecutionPolicy,
    ToolExecutionResult,
)


class McpReadonlyTransportError(RuntimeError):
    """Raised when optional MCP transport crosses the isolated read-only boundary."""


@dataclass(frozen=True, slots=True)
class McpReadonlyTransportPolicy:
    """Local-only MCP transport policy.

    This activates MCP as a bounded transport shim, not a network server. It can
    only dispatch native Stage 5 read-only capabilities that are also present in
    the default-off Stage 9 manifest allowlist.
    """

    enabled: bool
    authorization_token: str
    isolated_runtime: bool = True
    allow_network_listener: bool = False
    allow_mutation: bool = False
    allow_raw_infra: bool = False

    def __post_init__(self) -> None:
        if not self.authorization_token:
            raise McpReadonlyTransportError("authorization_token is required")
        if self.isolated_runtime is not True:
            raise McpReadonlyTransportError("MCP transport requires isolated runtime")
        if self.allow_network_listener or self.allow_mutation or self.allow_raw_infra:
            raise McpReadonlyTransportError(
                "MCP transport cannot expose network listener, mutation, or raw infra"
            )


@dataclass(frozen=True, slots=True)
class McpReadonlyTransportResult:
    status_code: str
    capability_name: str
    manifest_mode: str
    result: ToolExecutionResult

    def as_dict(self) -> dict[str, object]:
        return {
            "status_code": self.status_code,
            "capability_name": self.capability_name,
            "manifest_mode": self.manifest_mode,
            "record": self.result.record.as_dict(),
        }


class ReadOnlyMcpTransport:
    """Optional local MCP dispatch shim over the existing ToolExecutor."""

    def __init__(self, *, tool_executor: ReadOnlyToolExecutor) -> None:
        self._tool_executor = tool_executor

    def dispatch(
        self,
        capability_name: str,
        request: object,
        *,
        policy: McpReadonlyTransportPolicy,
    ) -> McpReadonlyTransportResult:
        if not policy.enabled:
            raise McpReadonlyTransportError("MCP transport is disabled")
        manifest = build_stage9_mcp_manifest(
            McpExposurePolicy(enabled=True, isolated_runtime=True)
        )
        allowed_names = tuple(item.mcp_name for item in manifest.tools)
        if capability_name not in allowed_names:
            raise McpReadonlyTransportError(
                f"capability is not in MCP read-only allowlist: {capability_name}"
            )
        execution_policy = ToolExecutionPolicy(
            authorized_capabilities=(capability_name,),
            authorization_token=policy.authorization_token,
        )
        result = self._tool_executor.execute(
            capability_name,
            request,
            policy=execution_policy,
            authorization_token=policy.authorization_token,
        )
        return McpReadonlyTransportResult(
            status_code="M27_MCP_READONLY_TRANSPORT_COMPLETED",
            capability_name=capability_name,
            manifest_mode=manifest.mode.value,
            result=result,
        )


__all__ = [
    "McpReadonlyTransportError",
    "McpReadonlyTransportPolicy",
    "McpReadonlyTransportResult",
    "ReadOnlyMcpTransport",
]
