from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine.m27_mcp_contracts import (
    MCP_EXPOSURE_SCHEMA_VERSION,
    ForbiddenMcpCapabilityError,
    McpExposureError,
    McpExposurePolicy,
    allowed_stage9_native_capabilities,
    validate_mcp_capability_name,
)
from knowledge_engine.m27_mcp_exposure import McpToolAdapter
from knowledge_engine.m27_tool_registry import build_stage5_readonly_registry


def test_default_policy_is_off_isolated_and_non_mutating() -> None:
    policy = McpExposurePolicy()

    assert policy.enabled is False
    assert policy.isolated_runtime is False
    assert policy.isolated_runtime_required is True
    assert policy.allow_network_server is False
    assert policy.allow_mutation is False
    assert policy.as_dict()["enabled"] is False


def test_enabled_policy_requires_explicit_isolated_runtime() -> None:
    with pytest.raises(McpExposureError, match="isolated_runtime"):
        McpExposurePolicy(enabled=True)

    enabled = McpExposurePolicy(enabled=True, isolated_runtime=True)
    assert enabled.enabled is True
    assert enabled.isolated_runtime is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"isolated_runtime_required": False},
        {"allow_network_server": True},
        {"allow_mutation": True},
    ],
)
def test_policy_cannot_widen_stage9_authority(overrides: dict[str, bool]) -> None:
    with pytest.raises(McpExposureError):
        McpExposurePolicy(**overrides)


def test_adapter_preserves_stage5_risk_and_contract_metadata() -> None:
    registry = build_stage5_readonly_registry()
    adapter = McpToolAdapter(tool_registry=registry)

    descriptor = adapter.adapt("knowledge.search")
    payload = descriptor.as_dict()

    assert payload["schema_version"] == MCP_EXPOSURE_SCHEMA_VERSION
    assert payload["mcp_name"] == "knowledge.search"
    assert payload["native_capability_name"] == "knowledge.search"
    assert payload["read_only"] is True
    assert payload["requires_authorization"] is True
    assert payload["supports_mutation"] is False
    assert payload["exposes_raw_infra"] is False
    assert payload["default_enabled"] is False
    assert payload["isolated_runtime_required"] is True
    assert payload["input_contract"]["contract_name"] == "KnowledgeSearchInput"
    assert payload["output_contract"]["contract_name"] == "KnowledgeSearchOutput"


def test_descriptor_fixed_safety_fields_cannot_be_widened() -> None:
    descriptor = McpToolAdapter(
        tool_registry=build_stage5_readonly_registry()
    ).adapt("runtime.get_health")

    for change in (
        {"read_only": False},
        {"requires_authorization": False},
        {"supports_mutation": True},
        {"exposes_raw_infra": True},
        {"default_enabled": True},
        {"isolated_runtime_required": False},
    ):
        with pytest.raises(McpExposureError):
            replace(descriptor, **change)


@pytest.mark.parametrize(
    "name",
    [
        "release.promote",
        "workspace.write",
        "memory.write",
        "skill.execute",
        "qdrant.raw_search",
        "r2.raw_get",
        "sqlite.raw_query",
        "admin.mutate",
        "shell.exec",
        "env.dump",
        "release.rollback",
        "ingestion.finalize",
        "ingest-and-update-knowledge",
        "promote-knowledge-release",
        "workspace.read_raw",
        "memory.read",
        "agent.run",
        "tool.invoke_raw",
        "docker.ps",
        "filesystem.read",
        "process.list",
        "secret.read",
        "credential.read",
    ],
)
def test_forbidden_mcp_capability_names_are_rejected(name: str) -> None:
    with pytest.raises(ForbiddenMcpCapabilityError):
        validate_mcp_capability_name(name)


def test_unknown_domain_capability_is_rejected_even_if_name_shape_is_safe() -> None:
    with pytest.raises(ForbiddenMcpCapabilityError, match="allowlist"):
        validate_mcp_capability_name("knowledge.preview")


def test_allowlist_is_exactly_the_seven_stable_stage5_capabilities() -> None:
    assert allowed_stage9_native_capabilities() == (
        "evidence.inspect",
        "evidence.verify",
        "knowledge.expand",
        "knowledge.search",
        "runtime.get_budget",
        "runtime.get_health",
        "runtime.get_trace",
    )
