from __future__ import annotations

import json

import pytest

from knowledge_engine.m27_runtime_telemetry import assert_privacy_safe_telemetry
from tests.test_m27_runtime_finalization import (
    ANSWER,
    QUESTION,
    KnowledgeProvider,
    _harness,
    _input,
    _provider,
    _request,
)


def test_runtime_telemetry_has_stable_round_level_latency_attribution(tmp_path):
    knowledge = KnowledgeProvider()
    result = _harness(tmp_path, knowledge).run(_input(_request(_provider())))

    telemetry = result.runtime_telemetry
    assert telemetry is not None
    assert telemetry["schema_version"] == "m27-runtime-telemetry/v1"
    assert telemetry["request_id"] == "request:isolated:001"
    assert telemetry["task_id"] == "task:isolated:001"
    assert telemetry["route"] == "SEMANTIC_CLOSURE"
    assert telemetry["task_kind"] == "KNOWLEDGE"
    assert telemetry["tool_call_count"] == 1
    assert telemetry["provider_call_count"] >= 2
    assert telemetry["model_call_count"] == telemetry["provider_call_count"]
    assert telemetry["retrieval_evidence_count"] == 1
    assert telemetry["terminal_reason"] == "VERIFIED_CITED_ANSWER"
    assert telemetry["estimated_cost_usd"] is None
    assert telemetry["cost_reason_code"] == "COST_UNAVAILABLE"

    rounds = telemetry["rounds"]
    assert len(rounds) == 1
    round0 = rounds[0]
    assert round0["continuation_decision"] == "TERMINAL"
    assert round0["compiler_status"] in {"COMPILED", "COMPILED_WITH_WARNINGS"}
    assert round0["provider_call_count"] >= 2
    assert round0["model_call_count"] == round0["provider_call_count"]
    assert round0["verifier_status"] == "OWNER_ONLY_CITED_ANSWER"
    assert set(round0["stage_latency_ms"]) == {
        "tool_ms",
        "evidence_binding_ms",
        "compiler_ms",
        "provider_ms",
        "verifier_ms",
        "round_total_ms",
    }
    assert all(value >= 0 for value in round0["stage_latency_ms"].values())
    assert round0["stage_latency_ms"]["round_total_ms"] >= round0["stage_latency_ms"]["tool_ms"]
    assert round0["stage_latency_ms"]["round_total_ms"] >= round0["stage_latency_ms"]["compiler_ms"]


def test_runtime_telemetry_records_actual_continuation_rounds(tmp_path):
    from tests.test_m26_aq_canonical_semantic_contract_convergence import (
        _CompactAbstainingProvider,
    )

    result = _harness(tmp_path, KnowledgeProvider()).run(
        _input(_request(_CompactAbstainingProvider()), max_rounds=1, attempts=12)
    )
    telemetry = result.runtime_telemetry
    assert telemetry is not None
    assert telemetry["continuation_rounds"] == 1
    assert len(telemetry["rounds"]) == 2
    assert telemetry["rounds"][0]["continuation_allowed"] is True
    assert telemetry["rounds"][0]["continuation_decision"] == "CONTINUE"
    assert telemetry["rounds"][1]["continuation_allowed"] is False
    assert telemetry["rounds"][1]["continuation_decision"] == "TERMINAL"
    assert telemetry["rounds"][1]["terminal_reason"] == "VERIFIER_GAP_SAFE_TERMINAL"


def test_runtime_telemetry_does_not_leak_query_evidence_answer_or_prompt(tmp_path):
    result = _harness(tmp_path, KnowledgeProvider()).run(_input(_request(_provider())))
    telemetry = result.runtime_telemetry
    assert telemetry is not None
    serialized = json.dumps(telemetry, sort_keys=True)

    assert QUESTION not in serialized
    assert ANSWER not in serialized
    assert "Graphology stores graph data and supports graph analysis." not in serialized
    assert "instruction" not in serialized.lower()
    assert "prompt" not in serialized.lower()
    assert "passage_text" not in serialized.lower()
    assert_privacy_safe_telemetry(telemetry)


def test_privacy_guard_rejects_raw_payload_keys():
    with pytest.raises(ValueError, match="forbidden telemetry field"):
        assert_privacy_safe_telemetry(
            {
                "schema_version": "m27-runtime-telemetry/v1",
                "rounds": [{"raw_prompt": "do not persist me"}],
            }
        )


def test_pre_execution_budget_terminal_still_emits_safe_zero_round_telemetry(tmp_path):
    result = _harness(tmp_path, KnowledgeProvider()).run(_input(_request(_provider()), attempts=0))
    telemetry = result.runtime_telemetry
    assert telemetry is not None
    assert telemetry["rounds"] == []
    assert telemetry["tool_call_count"] == 0
    assert telemetry["provider_call_count"] == 0
    assert telemetry["terminal_reason"] == "BUDGET_NOT_AUTHORITATIVE"
    assert telemetry["feature_flags"]["M27_ENABLED"] is True
    assert telemetry["feature_flags"]["ISOLATED_EXECUTABLE_RUNTIME"] is True
