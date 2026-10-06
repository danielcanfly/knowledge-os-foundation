from __future__ import annotations

from knowledge_engine.m27_independent_quality_scorer import (
    M27_INDEPENDENT_QUALITY_SCHEMA,
    M27_SCORING_POLICY_VERSION,
    per_case_scores_digest,
    validate_independent_quality_artifact,
)


def _artifact(score: float = 91.0) -> dict:
    rows = [
        {"case_id": "F523-001-R01", "score": 92, "result": "pass"},
        {"case_id": "F523-002-R01", "score": 90, "result": "pass"},
    ]
    return {
        "schema_version": M27_INDEPENDENT_QUALITY_SCHEMA,
        "artifact_id": "quality-001",
        "release_candidate_head": "release-head",
        "hard_gate_head": "hard-gate-head",
        "source_receipts_sha256": "source-hash",
        "evaluator_identity": "independent-semantic-quality-evaluator:v1",
        "evaluator_provider": "independent-provider",
        "evaluator_model": "independent-model",
        "rubric_version": "ANSWER_QUALITY_RUBRIC_v1",
        "scoring_policy_version": M27_SCORING_POLICY_VERSION,
        "threshold": 85,
        "quality_score": score,
        "passed": score >= 85,
        "case_count_scored": len(rows),
        "sampling_policy": "deterministic representative sample",
        "per_case_scores": rows,
        "per_case_scores_digest": per_case_scores_digest(rows),
        "deterministic_admission_is_not_quality_score": True,
        "production_touched": False,
        "reason_codes": [],
    }


def _validate(artifact: dict):
    return validate_independent_quality_artifact(
        artifact,
        expected_source_receipts_sha256="source-hash",
        expected_release_candidate_head="release-head",
        expected_hard_gate_head="hard-gate-head",
    )


def test_valid_independent_quality_artifact_closes_quality_contract() -> None:
    result = _validate(_artifact())
    assert result.passed is True
    assert result.quality_score == 91.0
    assert result.reason_codes == ()


def test_missing_evaluator_identity_fails_closed() -> None:
    artifact = _artifact()
    artifact["evaluator_identity"] = None
    result = _validate(artifact)
    assert result.passed is False
    assert "MISSING_EVALUATOR_IDENTITY" in result.reason_codes


def test_missing_rubric_version_fails_closed() -> None:
    artifact = _artifact()
    artifact["rubric_version"] = None
    result = _validate(artifact)
    assert result.passed is False
    assert "MISSING_RUBRIC_VERSION" in result.reason_codes


def test_score_below_85_fails_closed() -> None:
    result = _validate(_artifact(84.0))
    assert result.passed is False
    assert "QUALITY_SCORE_BELOW_THRESHOLD" in result.reason_codes


def test_stale_or_mismatched_source_receipts_fail_closed() -> None:
    artifact = _artifact()
    artifact["source_receipts_sha256"] = "stale-hash"
    result = _validate(artifact)
    assert result.passed is False
    assert "QUALITY_ARTIFACT_SOURCE_RECEIPTS_MISMATCH" in result.reason_codes


def test_deterministic_admission_cannot_substitute_for_quality() -> None:
    artifact = _artifact()
    artifact["deterministic_admission_is_not_quality_score"] = False
    result = _validate(artifact)
    assert result.passed is False
    assert "DETERMINISTIC_ADMISSION_QUALITY_SUBSTITUTION_RISK" in result.reason_codes


def test_production_mutation_evidence_fails_closed() -> None:
    artifact = _artifact()
    artifact["production_touched"] = True
    result = _validate(artifact)
    assert result.passed is False
    assert "PRODUCTION_MUTATION_EVIDENCE" in result.reason_codes
