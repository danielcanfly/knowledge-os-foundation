from __future__ import annotations

from .m27_mcp_contracts import (
    DEFAULT_MCP_EXPOSURE_POLICY,
    MCP_EXPOSURE_SCHEMA_VERSION,
    McpExposureManifest,
    McpExposurePolicy,
    McpExposureRegistry,
    McpToolDescriptor,
    _descriptor_from_native,
)
from .m27_tool_registry import ToolRegistry, build_stage5_readonly_registry


class McpToolAdapter:
    """Static registry-to-descriptor adapter.

    The adapter resolves through ToolRegistry so Stage 9 cannot bypass Stage 5
    registration policy. It has no provider call or tool execution surface.
    """

    def __init__(self, *, tool_registry: ToolRegistry) -> None:
        if not isinstance(tool_registry, ToolRegistry):
            raise TypeError("tool_registry must be ToolRegistry")
        self._tool_registry = tool_registry

    def adapt(self, native_capability_name: str) -> McpToolDescriptor:
        native = self._tool_registry.resolve(native_capability_name)
        return _descriptor_from_native(native)


def build_mcp_manifest(
    tool_registry: ToolRegistry,
    policy: McpExposurePolicy = DEFAULT_MCP_EXPOSURE_POLICY,
) -> McpExposureManifest:
    """Build a deterministic, static Stage 9 MCP exposure manifest."""

    if not isinstance(tool_registry, ToolRegistry):
        raise TypeError("tool_registry must be ToolRegistry")
    if not isinstance(policy, McpExposurePolicy):
        raise TypeError("policy must be McpExposurePolicy")

    if not policy.enabled:
        return McpExposureManifest(
            schema_version=MCP_EXPOSURE_SCHEMA_VERSION,
            mode=policy.mode,
            enabled=False,
            tools=(),
            policy=policy,
        )

    adapter = McpToolAdapter(tool_registry=tool_registry)
    descriptors = tuple(
        sorted(
            (adapter.adapt(item.name) for item in tool_registry.list()),
            key=lambda item: item.mcp_name,
        )
    )
    registry = McpExposureRegistry(descriptors)
    return McpExposureManifest(
        schema_version=MCP_EXPOSURE_SCHEMA_VERSION,
        mode=policy.mode,
        enabled=True,
        tools=registry.list(),
        policy=policy,
    )


def build_stage9_mcp_manifest(
    policy: McpExposurePolicy = DEFAULT_MCP_EXPOSURE_POLICY,
) -> McpExposureManifest:
    """Build from the canonical Stage 5 read-only registry only."""

    return build_mcp_manifest(build_stage5_readonly_registry(), policy)


__all__ = [
    "McpToolAdapter",
    "build_mcp_manifest",
    "build_stage9_mcp_manifest",
]
