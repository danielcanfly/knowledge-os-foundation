from __future__ import annotations

from dataclasses import fields

import pytest

from knowledge_engine.m27_tool_contracts import (
    EvidenceInspectOutput,
    KnowledgeItemRef,
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    RuntimeBudgetOutput,
    RuntimeHealthOutput,
    RuntimeLookupInput,
    RuntimeTraceOutput,
    ToolContractError,
    ToolDescriptor,
    ToolDomain,
    ToolRiskClass,
    contract_field_names,
    forbidden_payload_field_names,
)


def _descriptor(**overrides):
    values = {
        "name": "knowledge.search",
        "description": "Read sanitized domain knowledge metadata.",
        "domain": ToolDomain.KNOWLEDGE,
        "read_only": True,
        "risk_class": ToolRiskClass.DOMAIN_METADATA_READ,
        "input_contract": KnowledgeSearchInput,
        "output_contract": KnowledgeSearchOutput,
        "requires_authorization": True,
        "supports_network": False,
        "supports_mutation": False,
        "exposes_raw_infra": False,
    }
    values.update(overrides)
    return ToolDescriptor(**values)


def test_descriptor_serializes_machine_verifiable_risk_metadata() -> None:
    descriptor = _descriptor()
    payload = descriptor.as_dict()

    assert payload["name"] == "knowledge.search"
    assert payload["domain"] == "knowledge"
    assert payload["read_only"] is True
    assert payload["supports_mutation"] is False
    assert payload["exposes_raw_infra"] is False
    assert payload["requires_authorization"] is True
    assert payload["input_contract"] == "KnowledgeSearchInput"
    assert payload["output_contract"] == "KnowledgeSearchOutput"


def test_descriptor_can_describe_unsafe_capability_for_registry_to_reject() -> None:
    descriptor = _descriptor(read_only=False, supports_mutation=True)

    assert descriptor.read_only is False
    assert descriptor.supports_mutation is True


def test_contracts_do_not_expose_raw_payload_fields() -> None:
    forbidden = forbidden_payload_field_names()
    contracts = (
        KnowledgeSearchInput,
        KnowledgeSearchOutput,
        EvidenceInspectOutput,
        RuntimeTraceOutput,
        RuntimeBudgetOutput,
        RuntimeHealthOutput,
    )

    for contract in contracts:
        assert forbidden.isdisjoint(contract_field_names(contract))


def test_knowledge_search_input_accepts_only_sanitized_opaque_token() -> None:
    request = KnowledgeSearchInput(
        request_token="fixture:req-01",
        max_results=5,
        scope_ids=("scope-A",),
    )

    assert request.max_results == 5

    with pytest.raises(ToolContractError):
        KnowledgeSearchInput(request_token="raw customer question with spaces")


def test_knowledge_results_contain_ids_not_text_bodies() -> None:
    output = KnowledgeSearchOutput(
        items=(
            KnowledgeItemRef(
                knowledge_id="kn-01",
                source_identity="source-A",
                locator_id="loc-01",
                evidence_type="passage",
            ),
        ),
        total_count=1,
    )

    field_names = {field.name for field in fields(output.items[0])}
    assert {
        "text",
        "body",
        "content",
        "passage_text",
        "source_text",
        "raw_payload",
    }.isdisjoint(field_names)


def test_runtime_lookup_rejects_free_form_sensitive_text() -> None:
    with pytest.raises(ToolContractError):
        RuntimeLookupInput(trace_id="customer secret trace please")


def test_descriptor_rejects_non_dataclass_contract_types() -> None:
    with pytest.raises(ToolContractError, match="dataclass"):
        _descriptor(input_contract=dict)
