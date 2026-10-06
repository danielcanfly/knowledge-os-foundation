from __future__ import annotations

from knowledge_engine.m27_release_hard_gates import (
    M27_RELEASE_HARD_GATE_NOT_READY,
    M27_RELEASE_HARD_GATE_READY,
    QualityScoreEvidence,
    decide_release_hard_gates,
    evaluate_quality_hard_gate,
    evaluate_streaming_hard_gate,
)


def _receipts() -> dict:
    return {
        "schema_version": "m27-admission-ladder-receipts/v2",
        "gates": {
            "full523": {
                "summary": {
                    "gate": "full523",
                    "case_count": 523,
                    "passed_count": 523,
                    "gate_pass": True,
                    "cited_final_answer_rate": 1.0,
                    "verified_answer_cited_count": 237,
                    "verified_answer_expected_count": 237,
                    "safe_terminal_correctness": 1.0,
                    "safe_terminal_correct_count": 130,
                    "safe_terminal_expected_count": 130,
                    "citation_provenance_integrity": 1.0,
                    "production_no_mutation": True,
                    "quality_score": None,
                    "streaming_status": "not_yet_supported_by_isolated_preflight_endpoint",
                }
            }
        },
        "cleanup_after_full523": {
            "owned_eval_containers_after": 0,
            "port_18080_listeners_after": 0,
            "production_touched": False,
        },
        "release": {
            "canary_plan_report_only": True,
            "deployment_authorized": False,
            "deployment_performed": False,
        },
    }


def _streaming_events() -> list[dict]:
    schema = "m27-isolated-first-answer-stream/v1"
    return [
        {"schema_version": schema, "event": "request_started"},
        {
            "schema_version": schema,
            "event": "verified_claim_ready",
            "text": "Claim.",
            "citations": [{"citation_id": "c1"}],
        },
        {
            "schema_version": schema,
            "event": "cited_segment_ready",
            "text": "Final answer.",
            "citations": [{"citation_id": "c1"}],
        },
        {"schema_version": schema, "event": "final_answer_done"},
    ]


def test_quality_gate_fails_closed_when_independent_scorer_unavailable() -> None:
    gate = evaluate_quality_hard_gate(admission_receipts=_receipts())
    assert gate["passed"] is False
    assert gate["release_blocking"] is True
    assert "QUALITY_SCORER_UNAVAILABLE" in gate["reason_codes"]
    assert gate["deterministic_admission_is_not_quality_score"] is True
    assert gate["admission_receipts"]["passed"] is True
    assert gate["admission_receipts"]["full523"]["passed_count"] == 523


def test_quality_gate_passes_only_with_independent_identity_rubric_and_score() -> None:
    gate = evaluate_quality_hard_gate(
        admission_receipts=_receipts(),
        evidence=QualityScoreEvidence(
            score=91.0,
            evaluator_identity="independent-semantic-quality-evaluator:v1",
            rubric_version="ANSWER_QUALITY_RUBRIC_v1",
            artifact_version="quality-artifact-001",
            evaluator_provider="independent-provider",
            evaluator_model="independent-model",
            scoring_policy_version="m27-independent-quality-scoring-policy/v1",
            source_receipts_sha256="abc",
            case_count_scored=237,
            sampling_policy="all verified-answer rows",
            per_case_scores_digest="digest",
        ),
    )
    assert gate["passed"] is True
    assert gate["release_blocking"] is False
    assert gate["quality_score"] == 91.0


def test_quality_gate_does_not_treat_full523_determinism_as_quality_score() -> None:
    receipts = _receipts()
    receipts["gates"]["full523"]["summary"]["quality_score"] = None
    gate = evaluate_quality_hard_gate(admission_receipts=receipts)
    assert "QUALITY_SCORER_UNAVAILABLE" in gate["reason_codes"]
    assert gate["quality_score"] is None


def test_streaming_gate_proves_material_before_final_and_parity() -> None:
    gate = evaluate_streaming_hard_gate(
        _streaming_events(), final_answer_text="Final answer."
    )
    assert gate["passed"] is True
    assert gate["first_material_event_index"] == 1
    assert gate["first_material_event_index"] < gate["final_answer_done_index"]


def test_streaming_gate_blocks_safe_terminal_material_leak() -> None:
    schema = "m27-isolated-first-answer-stream/v1"
    gate = evaluate_streaming_hard_gate(
        [
            {"schema_version": schema, "event": "request_started"},
            {"schema_version": schema, "event": "safe_abstention_done"},
            {
                "schema_version": schema,
                "event": "cited_segment_ready",
                "text": "leak",
                "citations": [{"citation_id": "c1"}],
            },
            {"schema_version": schema, "event": "final_answer_done"},
        ]
    )
    assert gate["passed"] is False
    assert "SAFE_TERMINAL_EMITTED_MATERIAL_TEXT" in gate["reason_codes"]


def test_combined_gate_not_ready_when_quality_unavailable_but_preserves_candidate() -> None:
    quality = evaluate_quality_hard_gate(admission_receipts=_receipts())
    streaming = evaluate_streaming_hard_gate(
        _streaming_events(), final_answer_text="Final answer."
    )
    decision = decide_release_hard_gates(
        admission_receipts=_receipts(), quality_gate=quality, streaming_gate=streaming
    )
    assert decision["status"] == M27_RELEASE_HARD_GATE_NOT_READY
    assert decision["report_only_candidate_preserved"] is True
    assert decision["production_touched"] is False
    assert "QUALITY_SCORER_UNAVAILABLE" in decision["remaining_blockers"]


def test_combined_gate_ready_only_when_quality_and_streaming_pass() -> None:
    quality = evaluate_quality_hard_gate(
        admission_receipts=_receipts(),
        evidence=QualityScoreEvidence(
            score=90.0,
            evaluator_identity="independent-semantic-quality-evaluator:v1",
            rubric_version="ANSWER_QUALITY_RUBRIC_v1",
            evaluator_provider="independent-provider",
            evaluator_model="independent-model",
            scoring_policy_version="m27-independent-quality-scoring-policy/v1",
            source_receipts_sha256="abc",
            case_count_scored=237,
            sampling_policy="all verified-answer rows",
            per_case_scores_digest="digest",
        ),
    )
    streaming = evaluate_streaming_hard_gate(
        _streaming_events(), final_answer_text="Final answer."
    )
    decision = decide_release_hard_gates(
        admission_receipts=_receipts(), quality_gate=quality, streaming_gate=streaming
    )
    assert decision["status"] == M27_RELEASE_HARD_GATE_READY
    assert decision["remaining_blockers"] == ()
