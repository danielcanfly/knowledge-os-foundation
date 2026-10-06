from __future__ import annotations

import json
import shutil
import statistics
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from tests.test_m26_aq_canonical_semantic_contract_convergence import _CompactAbstainingProvider
from tests.test_m27_production_evidence_bridge import (
    ProductionKnowledgeProvider,
    _production_bridge_material,
    _provider,
    _request,
)

from knowledge_engine.m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from knowledge_engine.m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor
from knowledge_engine.m27_workspace_store import WorkspaceStore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/m27/research/fresh_small_smoke_receipts.json"
WORK = Path("/tmp/m27-fresh-small-smoke-workspaces")


def runtime_input(
    request: Any, case_id: str, *, attempts: int = 8, m27_enabled: bool = True
) -> M27RuntimeHarnessInput:
    return M27RuntimeHarnessInput(
        task=M27RuntimeTask(
            task_id=f"task:fresh-smoke:{case_id}",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token=f"request:fresh-smoke:{case_id}",
            max_continuation_rounds=0,
            max_tool_calls=3,
        ),
        routing_signal={"route": "SEMANTIC_CLOSURE", "reason": "fresh_small_smoke"},
        budget_signal={
            "route": "SEMANTIC_CLOSURE",
            "reason": "bounded_semantic_recovery",
            "deadline_remaining_ms": 60000,
            "minimum_budget_ms": 500,
            "provider_attempts_remaining": attempts,
            "affordable": True,
        },
        executable_request=request,
        m27_enabled=m27_enabled,
    )


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    evidence, authority = _production_bridge_material()
    if case.get("knowledge_source") == "wrong":
        knowledge = ProductionKnowledgeProvider(evidence, source="wrong-source")
    elif case.get("knowledge_locator") == "wrong":
        knowledge = ProductionKnowledgeProvider(evidence, locator="wrong-locator")
    else:
        knowledge = ProductionKnowledgeProvider(evidence)
    provider = (
        _CompactAbstainingProvider() if case["expectation"] == "safe_abstention" else _provider()
    )
    request = _request(provider, evidence, authority)
    request = replace(request, question=case["question"])
    harness = M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=WORK / case["case_id"] / "workspace"),
        tool_executor=ReadOnlyToolExecutor(knowledge_provider=knowledge),
    )
    start_ns = time.perf_counter_ns()
    result = harness.run(
        runtime_input(
            request,
            case["case_id"],
            attempts=case.get("attempts", 8),
            m27_enabled=case.get("m27_enabled", True),
        )
    )
    latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
    verification = dict(result.verification or {})
    citations = verification.get("citations") if isinstance(verification, dict) else None
    citation_count = len(citations) if isinstance(citations, list) else 0
    provider_calls = int(getattr(provider, "calls", 0))
    round_terminal = None
    if result.execution_rounds:
        round_terminal = result.execution_rounds[-1].get("terminal_reason")
    passed = False
    if case["expectation"] == "verified_cited_answer":
        passed = (
            result.status_code == "M27_RUNTIME_COMPOSED"
            and result.answer is not None
            and citation_count > 0
            and verification.get("production_evidence_authority") is True
            and verification.get("evidence_authority") == "production_equivalent"
            and result.production_touched is False
        )
    elif case["expectation"] == "safe_abstention":
        passed = (
            result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
            and round_terminal == "VERIFIER_GAP_SAFE_TERMINAL"
            and citation_count == 0
            and result.production_touched is False
        )
    elif case["expectation"] == "rejected_before_provider":
        passed = (
            result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
            and round_terminal == "VERIFIER_GAP_SAFE_TERMINAL"
            and provider_calls == 0
            and citation_count == 0
            and result.production_touched is False
        )
    elif case["expectation"] == "budget_terminal":
        passed = (
            result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
            and result.terminal_reason == "BUDGET_NOT_AUTHORITATIVE"
            and provider_calls == 0
            and result.production_touched is False
        )
    elif case["expectation"] == "m26_invariant":
        passed = (
            result.status_code == "M26_BASELINE_UNCHANGED"
            and result.feature_off is True
            and provider_calls == 0
            and result.production_touched is False
        )
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "question": case["question"],
        "expectation": case["expectation"],
        "passed": passed,
        "status_code": result.status_code,
        "terminal_reason": result.terminal_reason,
        "round_terminal_reason": round_terminal,
        "provider_calls": provider_calls,
        "knowledge_searches": knowledge.searches,
        "citation_count": citation_count,
        "answer_present": result.answer is not None,
        "production_touched": result.production_touched,
        "feature_off": result.feature_off,
        "latency_ms": round(latency_ms, 3),
        "runtime_telemetry": result.runtime_telemetry,
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[index]


def main() -> int:
    if WORK.exists():
        shutil.rmtree(WORK)
    cases = [
        {
            "case_id": "SMOKE001",
            "category": "cited_answer",
            "question": "What does Graphology do for graph data?",
            "expectation": "verified_cited_answer",
        },
        {
            "case_id": "SMOKE002",
            "category": "cited_answer",
            "question": "How does Graphology help with graph analysis?",
            "expectation": "verified_cited_answer",
        },
        {
            "case_id": "SMOKE003",
            "category": "cited_answer",
            "question": "What storage role does Graphology provide?",
            "expectation": "verified_cited_answer",
        },
        {
            "case_id": "SMOKE004",
            "category": "multilingual",
            "question": "Graphology 對 graph data 的用途是什麼？",
            "expectation": "verified_cited_answer",
        },
        {
            "case_id": "SMOKE005",
            "category": "retrieval_hard",
            "question": "When evidence is bound, what does Graphology do?",
            "expectation": "verified_cited_answer",
        },
        {
            "case_id": "SMOKE006",
            "category": "abstention",
            "question": (
                "Only answer if the evidence supports every requested detail "
                "about Graphology pricing."
            ),
            "expectation": "safe_abstention",
        },
        {
            "case_id": "SMOKE007",
            "category": "abstention",
            "question": "Only answer if evidence states Graphology deployment dates.",
            "expectation": "safe_abstention",
        },
        {
            "case_id": "SMOKE008",
            "category": "retrieval_hard",
            "question": "Reject drifted source identity before publication.",
            "expectation": "rejected_before_provider",
            "knowledge_source": "wrong",
        },
        {
            "case_id": "SMOKE009",
            "category": "retrieval_hard",
            "question": "Reject drifted locator identity before publication.",
            "expectation": "rejected_before_provider",
            "knowledge_locator": "wrong",
        },
        {
            "case_id": "SMOKE010",
            "category": "deadline_pressure",
            "question": "What does Graphology do under exhausted provider budget?",
            "expectation": "budget_terminal",
            "attempts": 0,
        },
        {
            "case_id": "SMOKE011",
            "category": "m26_baseline_invariant",
            "question": "M27 feature off should leave M26 baseline unchanged.",
            "expectation": "m26_invariant",
            "m27_enabled": False,
        },
        {
            "case_id": "SMOKE012",
            "category": "cited_answer",
            "question": "Summarize Graphology using only the bound evidence.",
            "expectation": "verified_cited_answer",
        },
    ]
    receipts = [run_case(case) for case in cases]
    latencies = [float(item["latency_ms"]) for item in receipts]
    summary = {
        "schema_version": "m27-fresh-small-smoke/v1",
        "case_count": len(receipts),
        "passed_count": sum(1 for item in receipts if item["passed"]),
        "failed_cases": [item["case_id"] for item in receipts if not item["passed"]],
        "p50_latency_ms": round(statistics.median(latencies), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
        "max_latency_ms": round(max(latencies), 3),
        "provider_calls_total": sum(int(item["provider_calls"]) for item in receipts),
        "production_touched_any": any(bool(item["production_touched"]) for item in receipts),
        "streaming_status": (
            "unsupported_by_05R_preflight_endpoint; harness-level smoke "
            "records terminal answer receipts"
        ),
        "cases": receipts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed_count"] == summary["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
