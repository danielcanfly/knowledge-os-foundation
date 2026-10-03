from __future__ import annotations

import ast
import inspect

import pytest

import knowledge_engine.m27_mcp_contracts as mcp_contracts
import knowledge_engine.m27_mcp_exposure as mcp_exposure
from knowledge_engine.m27_mcp_contracts import (
    ForbiddenMcpCapabilityError,
    McpExposurePolicy,
)
from knowledge_engine.m27_mcp_exposure import (
    McpToolAdapter,
    build_mcp_manifest,
    build_stage9_mcp_manifest,
)
from knowledge_engine.m27_tool_contracts import (
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    ToolDescriptor,
    ToolDomain,
    ToolRiskClass,
)
from knowledge_engine.m27_tool_registry import (
    ForbiddenCapabilityError,
    ToolRegistry,
    build_stage5_readonly_registry,
)

EXPECTED = (
    "evidence.inspect",
    "evidence.verify",
    "knowledge.expand",
    "knowledge.search",
    "runtime.get_budget",
    "runtime.get_health",
    "runtime.get_trace",
)


def _safe_descriptor(
    name: str,
    *,
    read_only: bool = True,
    supports_mutation: bool = False,
    exposes_raw_infra: bool = False,
) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        description="Synthetic descriptor for Stage 9 boundary tests.",
        domain=ToolDomain.KNOWLEDGE,
        read_only=read_only,
        risk_class=ToolRiskClass.DOMAIN_METADATA_READ,
        input_contract=KnowledgeSearchInput,
        output_contract=KnowledgeSearchOutput,
        requires_authorization=True,
        supports_network=False,
        supports_mutation=supports_mutation,
        exposes_raw_infra=exposes_raw_infra,
    )


def test_default_policy_exposes_zero_active_mcp_tools() -> None:
    manifest = build_stage9_mcp_manifest()

    assert manifest.enabled is False
    assert manifest.tools == ()
    assert manifest.mode.value == "DISABLED"


def test_enabled_isolated_policy_exposes_only_seven_stage5_capabilities() -> None:
    manifest = build_stage9_mcp_manifest(
        McpExposurePolicy(enabled=True, isolated_runtime=True)
    )

    assert manifest.enabled is True
    assert tuple(item.mcp_name for item in manifest.tools) == EXPECTED
    assert tuple(item.native_capability_name for item in manifest.tools) == EXPECTED


def test_every_exposed_descriptor_preserves_readonly_authorization_boundary() -> None:
    manifest = build_stage9_mcp_manifest(
        McpExposurePolicy(enabled=True, isolated_runtime=True)
    )

    for descriptor in manifest.tools:
        assert descriptor.read_only is True
        assert descriptor.requires_authorization is True
        assert descriptor.supports_mutation is False
        assert descriptor.exposes_raw_infra is False
        assert descriptor.default_enabled is False
        assert descriptor.isolated_runtime_required is True


def test_manifest_is_deterministic_and_sorted() -> None:
    policy = McpExposurePolicy(enabled=True, isolated_runtime=True)

    first = build_stage9_mcp_manifest(policy)
    second = build_stage9_mcp_manifest(policy)

    assert first == second
    assert tuple(item.mcp_name for item in first.tools) == tuple(
        sorted(item.mcp_name for item in first.tools)
    )


def test_stage9_does_not_bypass_stage5_registry_mutation_rejection() -> None:
    registry = ToolRegistry()

    with pytest.raises(ForbiddenCapabilityError):
        registry.register(
            _safe_descriptor(
                "knowledge.search",
                read_only=False,
                supports_mutation=True,
            )
        )


def test_stage9_does_not_bypass_stage5_registry_raw_infra_rejection() -> None:
    registry = ToolRegistry()

    with pytest.raises(ForbiddenCapabilityError):
        registry.register(
            _safe_descriptor("knowledge.search", exposes_raw_infra=True)
        )


def test_unknown_registered_capability_is_still_rejected_by_stage9_allowlist() -> None:
    registry = ToolRegistry()
    registry.register(_safe_descriptor("knowledge.preview"))

    with pytest.raises(ForbiddenMcpCapabilityError):
        build_mcp_manifest(
            registry,
            McpExposurePolicy(enabled=True, isolated_runtime=True),
        )


def test_adapter_resolves_through_tool_registry_not_raw_provider() -> None:
    registry = build_stage5_readonly_registry()
    adapter = McpToolAdapter(tool_registry=registry)

    assert adapter.adapt("evidence.verify").mcp_name == "evidence.verify"
    assert not hasattr(adapter, "provider")
    assert not hasattr(adapter, "call_provider")


def test_descriptor_payload_does_not_expose_raw_backend_paths_or_credentials() -> None:
    payload = repr(
        build_stage9_mcp_manifest(
            McpExposurePolicy(enabled=True, isolated_runtime=True)
        ).as_dict()
    ).casefold()

    for forbidden in (
        "qdrant",
        "sqlite",
        "filesystem_path",
        "credential",
        "api_key",
        "secret",
        "/home/",
        "r2.raw",
        "object_key",
        "http_endpoint",
    ):
        assert forbidden not in payload


def test_no_execution_or_network_server_api_exists() -> None:
    forbidden_api_names = {
        "run_tool",
        "execute_tool",
        "invoke_tool",
        "call_provider",
        "start_server",
        "listen",
        "serve",
        "run",
        "execute",
        "invoke",
    }

    module_names = set(dir(mcp_contracts)) | set(dir(mcp_exposure))
    adapter_names = set(dir(McpToolAdapter))

    assert forbidden_api_names.isdisjoint(module_names)
    assert forbidden_api_names.isdisjoint(adapter_names)


def test_stage7_skills_and_stage8_workspace_are_not_exposed_or_imported() -> None:
    manifest = build_stage9_mcp_manifest(
        McpExposurePolicy(enabled=True, isolated_runtime=True)
    )
    names = tuple(item.mcp_name for item in manifest.tools)

    assert all(not name.startswith("skill.") for name in names)
    assert all(not name.startswith("workspace.") for name in names)

    source = inspect.getsource(mcp_contracts) + inspect.getsource(mcp_exposure)
    assert "m27_skill_contracts" not in source
    assert "m27_workspace_contracts" not in source
    assert "m27_workspace_store" not in source


def test_mcp_modules_have_no_m26_or_production_runtime_import_dependency() -> None:
    for module in (mcp_contracts, mcp_exposure):
        tree = ast.parse(inspect.getsource(module))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)

        assert all("m26_" not in name for name in imported)
        assert all("production" not in name for name in imported)
        assert all("workspace" not in name for name in imported)
        assert all("skill" not in name for name in imported)


def test_default_off_manifest_does_not_require_provider_or_runtime_wiring() -> None:
    registry = build_stage5_readonly_registry()

    manifest = build_mcp_manifest(registry, McpExposurePolicy())

    assert manifest.tools == ()
