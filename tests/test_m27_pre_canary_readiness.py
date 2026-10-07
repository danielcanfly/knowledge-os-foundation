from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from knowledge_engine.m27_canary_telemetry import (
    CanaryIdentity,
    CanaryTelemetryRecord,
    append_canary_telemetry,
)

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "src/knowledge_engine/m27_test_page_executor.py"


def test_executor_has_no_unreachable_statements_after_product_return() -> None:
    tree = ast.parse(EXECUTOR.read_text())
    run_execution = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run_execution"
    )
    product_returns = [
        (index, node)
        for index, node in enumerate(run_execution.body)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "as_runtime_result"
    ]
    assert len(product_returns) == 1
    index, _ = product_returns[0]
    assert index == len(run_execution.body) - 1


def test_executor_product_path_does_not_delegate_to_m26_composer() -> None:
    source = EXECUTOR.read_text()
    forbidden = (
        "run_owner_arbitrary_query(",
        "synthesize_and_verify(",
        "_synthesize_and_verify(",
        "M27RuntimeHarness(",
    )
    assert all(token not in source for token in forbidden)
    assert "build_agent_native_product_answer(" in source


def test_canary_identity_requires_auditable_fields() -> None:
    with pytest.raises(ValueError, match="IDENTITY_REQUIRED"):
        CanaryIdentity(route_id="", candidate_id="candidate-1", candidate_git_sha="abc", canary_mode="owner_only")
    with pytest.raises(ValueError, match="MODE_UNSUPPORTED"):
        CanaryIdentity(route_id="route-1", candidate_id="candidate-1", candidate_git_sha="abc", canary_mode="public")


def test_canary_telemetry_persists_required_identity_and_outcome(tmp_path: Path) -> None:
    identity = CanaryIdentity(
        route_id="owner-test-answers-v1",
        candidate_id="m27-stage27",
        candidate_git_sha="dd3275bbb9b2c65772005ca468387a9b76500eeb",
        candidate_runtime_identity="sha256:example-immutable-runtime-digest",
        canary_mode="owner_only",
    )
    record = CanaryTelemetryRecord(
        identity=identity,
        request_id="req-1",
        terminal_kind="publishable_answer",
        first_material_latency_ms=123.4,
        final_latency_ms=130.1,
        product_gate_outcome="pass",
        stop_condition_flags={"latency": False, "quality": False},
    )
    sink = tmp_path / "canary.jsonl"
    append_canary_telemetry(sink, record)
    payload = json.loads(sink.read_text().strip())
    for key in (
        "route_id",
        "candidate_id",
        "candidate_git_sha",
        "candidate_runtime_identity",
        "canary_mode",
        "request_id",
        "terminal_kind",
        "first_material_latency_ms",
        "final_latency_ms",
        "product_gate_outcome",
        "stop_condition_flags",
    ):
        assert key in payload
    assert payload["schema_version"] == "m27-canary-telemetry/v1"
