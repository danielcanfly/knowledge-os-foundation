from __future__ import annotations

import pytest

from knowledge_engine.m27_tool_contracts import (
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    ToolDescriptor,
    ToolDomain,
    ToolRiskClass,
)
from knowledge_engine.m27_tool_registry import (
    DuplicateCapabilityError,
    ForbiddenCapabilityError,
    ToolRegistry,
    UnknownCapabilityError,
    build_stage5_readonly_registry,
)


def _descriptor(
    name: str,
    *,
    domain: ToolDomain = ToolDomain.KNOWLEDGE,
    read_only: bool = True,
    supports_mutation: bool = False,
    exposes_raw_infra: bool = False,
    requires_authorization: bool = True,
) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        description="Synthetic registry-boundary test capability.",
        domain=domain,
        read_only=read_only,
        risk_class=ToolRiskClass.DOMAIN_METADATA_READ,
        input_contract=KnowledgeSearchInput,
        output_contract=KnowledgeSearchOutput,
        requires_authorization=requires_authorization,
        supports_network=False,
        supports_mutation=supports_mutation,
        exposes_raw_infra=exposes_raw_infra,
    )


def test_stage5_registry_contains_only_expected_domain_capabilities() -> None:
    registry = build_stage5_readonly_registry()

    assert tuple(item.name for item in registry.list()) == (
        "evidence.inspect",
        "evidence.verify",
        "knowledge.expand",
        "knowledge.search",
        "runtime.get_budget",
        "runtime.get_health",
        "runtime.get_trace",
    )
    assert len(registry) == 7


def test_every_registered_tool_is_read_only_authorized_boundary_and_infra_hidden() -> None:
    registry = build_stage5_readonly_registry()

    for descriptor in registry.list():
        assert descriptor.read_only is True
        assert descriptor.supports_mutation is False
        assert descriptor.exposes_raw_infra is False
        assert descriptor.requires_authorization is True
        assert descriptor.supports_network is False


def test_registry_resolve_list_and_describe_are_descriptor_only() -> None:
    registry = build_stage5_readonly_registry()

    resolved = registry.resolve("evidence.inspect")
    described = registry.describe("evidence.inspect")

    assert resolved.name == "evidence.inspect"
    assert described["read_only"] is True
    assert [item.name for item in registry.list(domain=ToolDomain.EVIDENCE)] == [
        "evidence.inspect",
        "evidence.verify",
    ]
    assert not hasattr(registry, "invoke")
    assert not hasattr(registry, "execute")


def test_registry_rejects_duplicate_and_unknown_capabilities() -> None:
    registry = ToolRegistry()
    descriptor = _descriptor("knowledge.search")

    registry.register(descriptor)
    with pytest.raises(DuplicateCapabilityError):
        registry.register(descriptor)
    with pytest.raises(UnknownCapabilityError):
        registry.resolve("knowledge.expand")


@pytest.mark.parametrize(
    ("name", "domain"),
    [
        ("release.promote", ToolDomain.RUNTIME),
        ("release.rollback", ToolDomain.RUNTIME),
        ("ingestion.finalize", ToolDomain.RUNTIME),
        ("qdrant.raw_search", ToolDomain.KNOWLEDGE),
        ("r2.raw_get", ToolDomain.KNOWLEDGE),
        ("sqlite.raw_query", ToolDomain.RUNTIME),
        ("admin.mutate", ToolDomain.RUNTIME),
        ("knowledge.raw_search", ToolDomain.KNOWLEDGE),
        ("knowledge.qdrant_search", ToolDomain.KNOWLEDGE),
        ("runtime.sqlite_query", ToolDomain.RUNTIME),
        ("evidence.admin_update", ToolDomain.EVIDENCE),
        ("runtime.release_rollback", ToolDomain.RUNTIME),
        ("runtime.shell_exec", ToolDomain.RUNTIME),
    ],
)
def test_registry_rejects_forbidden_or_equivalent_capability_names(
    name: str,
    domain: ToolDomain,
) -> None:
    registry = ToolRegistry()

    with pytest.raises(ForbiddenCapabilityError):
        registry.register(_descriptor(name, domain=domain))


def test_registry_rejects_write_mutation_raw_infra_and_auth_bypass_descriptors() -> None:
    registry = ToolRegistry()

    with pytest.raises(ForbiddenCapabilityError, match="read-only"):
        registry.register(_descriptor("knowledge.search", read_only=False))

    with pytest.raises(ForbiddenCapabilityError, match="mutation"):
        registry.register(
            _descriptor("knowledge.search", supports_mutation=True)
        )

    with pytest.raises(ForbiddenCapabilityError, match="raw infrastructure"):
        registry.register(
            _descriptor("knowledge.search", exposes_raw_infra=True)
        )

    with pytest.raises(ForbiddenCapabilityError, match="authorization"):
        registry.register(
            _descriptor("knowledge.search", requires_authorization=False)
        )


def test_registry_rejects_namespace_domain_mismatch() -> None:
    registry = ToolRegistry()

    with pytest.raises(ForbiddenCapabilityError):
        registry.register(
            _descriptor(
                "runtime.get_health",
                domain=ToolDomain.KNOWLEDGE,
            )
        )
