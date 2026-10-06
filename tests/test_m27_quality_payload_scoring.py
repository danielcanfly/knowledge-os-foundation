from __future__ import annotations

from knowledge_engine.m27_quality_payload_scoring import (
    canonical_digest,
    validate_quality_payload_score_artifact,
)

ADMISSION_HEAD = "f406be4a07ae360655e073c4dea1e13fe2796689"
HARD_GATE_HEAD = "e864417c2380f2ce8d6c24576fb129c37b95ccad"
QUALITY_GATE_HEAD = "80b0b0ddc1ccc52ccb86b3acb1d2e9782579102a"
SOURCE = "a" * 64


def artifact() -> dict:
    payload = {
        "case_id": "F523-001-R01",
        "category": "cited_answer",
        "question": "What does Graphology do?",
        "answer_payload": {
            "answer_text": "Graphology stores graph data. [[claim_1]]",
            "selected_evidence": [{"text": "Graphology stores graph data."}],
            "citations": [{"claim_id": "claim_1", "evidence_id": "e1"}],
        },
        "forensic_trace": {"production_touched": False},
    }
    payload["input_digest"] = canonical_digest(
        {
            "question": payload["question"],
            "answer_payload": payload["answer_payload"],
            "forensic_trace": payload["forensic_trace"],
        }
    )
    scores = [
        {
            "case_id": payload["case_id"],
            "input_digest": payload["input_digest"],
            "score": 91,
            "result": "pass",
        }
    ]
    digest = canonical_digest(scores)
    inputs = canonical_digest(
        [{"case_id": payload["case_id"], "input_digest": payload["input_digest"]}]
    )
    return {
        "schema_version": "m27-independent-quality-score/v1",
        "source_admission_head": ADMISSION_HEAD,
        "release_candidate_head": ADMISSION_HEAD,
        "hard_gate_head": HARD_GATE_HEAD,
        "quality_gate_head": QUALITY_GATE_HEAD,
        "source_receipts_sha256": SOURCE,
        "evaluator_provider": "minimax",
        "evaluator_model": "MiniMax-M3",
        "evaluator_identity": "repo-qualified-minimax-answer-quality-evaluator",
        "evaluator_version": "aq-semantic-evaluator/v3",
        "rubric_version": "ANSWER_QUALITY_RUBRIC_v1",
        "scoring_policy_version": "m27-independent-quality-scoring-policy/v1",
        "sampling_policy": "unique-question-stratified-all-verified-categories/v1",
        "eligible_verified_answer_row_count": 1,
        "case_count_scored": 1,
        "skipped_rows": 0,
        "payload_records": [payload],
        "source_input_digest": inputs,
        "per_case_scores": scores,
        "per_case_scores_digest": digest,
        "score_output_digest": digest,
        "quality_score": 91.0,
        "production_touched": False,
        "production_no_mutation_proof": {
            "production_endpoint_called_for_answers": False,
            "production_datastore_writes": False,
            "release_pointer_mutation": False,
        },
        "deterministic_admission_is_not_quality_score": True,
    }


def validate(value: dict):
    return validate_quality_payload_score_artifact(
        value,
        expected_admission_head=ADMISSION_HEAD,
        expected_hard_gate_head=HARD_GATE_HEAD,
        expected_quality_gate_head=QUALITY_GATE_HEAD,
        expected_source_receipts_sha256=SOURCE,
    )


def test_quality_payload_contract_accepts_traceable_real_score_artifact():
    assert validate(artifact()).passed is True


def test_fail_closed_missing_payload():
    value = artifact()
    value["payload_records"] = []
    assert "PAYLOAD_RECORD_COUNT_MISMATCH" in validate(value).reason_codes


def test_fail_closed_synthetic_placeholder_score():
    value = artifact()
    value["evaluator_identity"] = "synthetic-placeholder-judge"
    assert "SYNTHETIC_EVALUATOR_IDENTITY_FORBIDDEN" in validate(value).reason_codes


def test_fail_closed_missing_evaluator_identity_as_credential_proxy():
    value = artifact()
    value["evaluator_identity"] = None
    assert "MISSING_EVALUATOR_IDENTITY" in validate(value).reason_codes


def test_no_production_mutation_proof_is_required():
    value = artifact()
    value["production_no_mutation_proof"]["production_datastore_writes"] = True
    assert "PRODUCTION_DATASTORE_MUTATION" in validate(value).reason_codes
