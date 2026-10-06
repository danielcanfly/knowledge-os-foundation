from __future__ import annotations

import pytest

from knowledge_engine.m27_decision_trace import (
    BudgetClass,
    ComputeTier,
    ContextSource,
    DecisionReasonCode,
    DecisionRoute,
    DecisionTraceEvent,
    SafeAbstentionOutcome,
    StatusClass,
)
from knowledge_engine.m27_mcp_readonly_transport import (
    McpReadonlyTransportError,
    McpReadonlyTransportPolicy,
    ReadOnlyMcpTransport,
)
from knowledge_engine.m27_readonly_tools import runtime_health_view
from knowledge_engine.m27_tool_contracts import RuntimeHealthInput
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor


class RuntimeProvider:
    def __init__(self) -> None:
        self.health_calls = 0

    def get_trace(self, request: object) -> object:
        raise AssertionError("trace should not be called")

    def get_budget(self, request: object) -> object:
        raise AssertionError("budget should not be called")

    def get_health(self, request: RuntimeHealthInput) -> object:
        self.health_calls += 1
        return runtime_health_view(
            {"freshness": "snapshot", "data": {"overall_status": "read_only"}}
        )


def _trace_for_import_sanity() -> DecisionTraceEvent:
    return DecisionTraceEvent(
        trace_id="00000000-0000-4000-8000-000000000002",
        route=DecisionRoute.SEMANTIC_CLOSURE,
        reason_code=DecisionReasonCode.ROUTE_SELECTED,
        compute_tier=ComputeTier.STANDARD,
        deadline_budget_class=BudgetClass.HEALTHY,
        provider_budget_class=BudgetClass.HEALTHY,
        provider_attempt_count=1,
        context_sources=(ContextSource.LEXICAL,),
        evidence_count=1,
        citation_count=1,
        status_class=StatusClass.CITED_ANSWER,
        safe_abstention_outcome=SafeAbstentionOutcome.DID_NOT_ABSTAIN,
    )


def test_optional_mcp_transport_dispatches_allowed_readonly_tool_only() -> None:
    _trace_for_import_sanity()
    runtime = RuntimeProvider()
    transport = ReadOnlyMcpTransport(
        tool_executor=ReadOnlyToolExecutor(runtime_provider=runtime)
    )

    result = transport.dispatch(
        "runtime.get_health",
        RuntimeHealthInput(),
        policy=McpReadonlyTransportPolicy(
            enabled=True,
            authorization_token="task:mcp:001",
        ),
    )

    assert result.status_code == "M27_MCP_READONLY_TRANSPORT_COMPLETED"
    assert result.manifest_mode == "READ_ONLY_ISOLATED"
    assert result.result.record.capability_name == "runtime.get_health"
    assert result.result.record.read_only is True
    assert result.result.record.supports_mutation is False
    assert result.result.record.exposes_raw_infra is False
    assert runtime.health_calls == 1


def test_mcp_transport_is_default_disabled_and_rejects_forbidden_capability() -> None:
    transport = ReadOnlyMcpTransport(tool_executor=ReadOnlyToolExecutor())

    with pytest.raises(McpReadonlyTransportError):
        transport.dispatch(
            "runtime.get_health",
            RuntimeHealthInput(),
            policy=McpReadonlyTransportPolicy(
                enabled=False,
                authorization_token="task:mcp:002",
            ),
        )
    with pytest.raises(McpReadonlyTransportError):
        transport.dispatch(
            "shell.exec",
            RuntimeHealthInput(),
            policy=McpReadonlyTransportPolicy(
                enabled=True,
                authorization_token="task:mcp:003",
            ),
        )
