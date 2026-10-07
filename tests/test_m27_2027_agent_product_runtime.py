from __future__ import annotations

from pathlib import Path

from knowledge_engine.m27_agent_product_runtime import (
    M27_PRODUCT_SLO_MS,
    M27SloComputePolicy,
    M27VerifierGap,
    build_agent_native_product_answer,
    canonicalize_question,
    canonicalize_question_for_retrieval,
    strict_product_success,
)
from knowledge_engine.m27_isolated_streaming import runtime_progress_event


def _ev(idx: int, source: str, text: str) -> dict[str, str]:
    return {
        "evidence_id": f"ev-{idx}",
        "source_identity": source,
        "source_id": source,
        "locator_id": f"loc-{idx}",
        "section_id": f"sec-{idx}",
        "evidence_type": "passage",
        "passage_text": text,
    }


def test_claim_native_product_answer_is_publishable_and_streamable() -> None:
    result = build_agent_native_product_answer(
        question="How does Kubernetes help AI infrastructure?",
        intent_class="direct_grounded_knowledge",
        evidence=(
            _ev(1, "k8s-a", "Kubernetes coordinates services, scheduling, rollouts, and recovery for AI infrastructure so models can run as dependable services."),
            _ev(2, "k8s-b", "AI infrastructure needs orchestration around GPU workloads, routing, observability, isolation, and operational control rather than only a model file."),
            _ev(3, "k8s-c", "A production AI service uses runtime boundaries, citations, verification, and monitoring to avoid treating inference as a black box."),
        ),
    )
    assert result.publishable is True
    assert strict_product_success(result.answer) is True
    assert result.micro_timeline.first_verified_claim_ready_ms is not None
    assert result.micro_timeline.final_emitted_ms is not None
    assert result.micro_timeline.first_verified_claim_ready_ms <= result.micro_timeline.final_emitted_ms
    mapped = [runtime_progress_event(event) for event in result.stream_events()]
    assert any(item and item[0] == "verified_claim_ready" for item in mapped)
    assert any(item and item[0] == "cited_segment_ready" for item in mapped)


def test_empty_nonterminal_is_not_a_valid_product_result() -> None:
    result = build_agent_native_product_answer(
        question="What is RAG in AI infrastructure?",
        intent_class="direct_grounded_knowledge",
        evidence=(),
    )
    runtime = result.as_runtime_result(question_sha256="abc")
    assert runtime["status_code"] == "M27_RUNTIME_SAFE_TERMINAL"
    assert runtime["terminal_reason"] == M27VerifierGap.TRUE_NO_EVIDENCE.value
    assert runtime["verification"]["safe_terminal_justification"]["structured"] is True


def test_thin_one_citation_broad_answer_cannot_count_as_success() -> None:
    result = build_agent_native_product_answer(
        question="How can one AI platform safely serve many companies?",
        intent_class="direct_grounded_knowledge",
        evidence=(_ev(1, "tenant-a", "Multi tenant platforms need isolation."),),
    )
    assert result.publishable is False
    assert M27VerifierGap.INSUFFICIENT_SOURCE_BREADTH.value in result.gap_taxonomy


def test_gap_taxonomy_serializes_safely() -> None:
    values = {item.value for item in M27VerifierGap}
    assert "MULTILINGUAL_SUPPORT_MISMATCH" in values
    assert "PRODUCT_THIN_SURFACE" in values
    assert all(" " not in value and value.upper() == value for value in values)


def test_slo_compute_policy_caps_provider_attempts() -> None:
    policy = M27SloComputePolicy()
    assert policy.deadline_ms == M27_PRODUCT_SLO_MS
    assert policy.deadline_ms < 15000
    assert policy.provider_attempts_allowed == 0
    assert policy.deterministic_repair_first is True


def test_multilingual_canonicalization_before_retrieval() -> None:
    zh = canonicalize_question_for_retrieval("一個 AI 平台要怎麼安全地服務多家公司？")
    ja = canonicalize_question_for_retrieval("AI インフラで Kubernetes は何をしますか？")
    canonical, lang = canonicalize_question("AI インフラで Kubernetes は何をしますか？")
    assert lang == "ja"
    assert "multi tenant" in zh.casefold()
    assert "english corpus canonical concepts" in zh.casefold()
    assert "kubernetes ai infrastructure" in ja.casefold()
    assert "kubernetes ai infrastructure" in canonical.casefold()


def test_receipt_micro_timeline_fields_exist() -> None:
    result = build_agent_native_product_answer(
        question="What is LocalBridge MCP?",
        intent_class="direct_grounded_knowledge",
        evidence=(
            _ev(1, "mcp-a", "LocalBridge MCP connects local files and tools to an agent through a controlled bridge with explicit permissions."),
            _ev(2, "mcp-b", "MCP stands for Model Context Protocol and describes a tool context interface for agentic systems."),
        ),
    )
    timeline = result.as_runtime_result(question_sha256="abc")["verification"]["micro_timeline"]
    for key in (
        "retrieval_start_ms",
        "evidence_admission_start_ms",
        "answer_planning_start_ms",
        "claim_graph_start_ms",
        "first_claim_verification_start_ms",
        "first_verified_claim_ready_ms",
        "first_citation_bound_ms",
        "first_cited_segment_ready_ms",
        "first_material_emitted_ms",
        "provider_call_count",
        "verifier_exclusive_duration_ms",
        "final_emitted_ms",
    ):
        assert key in timeline


def test_m27_runtime_does_not_import_m26_mature_answer_composer() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime = (root / "src/knowledge_engine/m27_runtime_execution.py").read_text()
    agent = (root / "src/knowledge_engine/m27_agent_product_runtime.py").read_text()
    assert "synthesize_and_verify" not in runtime
    assert "mature answer composer" not in agent.casefold()
