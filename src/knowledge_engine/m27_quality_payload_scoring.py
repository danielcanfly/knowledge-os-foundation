from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .qa_answer_quality_evaluator import (
    ANSWER_QUALITY_PASS_THRESHOLD,
    ANSWER_QUALITY_RUBRIC_VERSION,
)

M27_QUALITY_PAYLOAD_SCORE_SCHEMA = "m27-independent-quality-score/v1"
M27_QUALITY_PAYLOAD_POLICY_VERSION = "m27-independent-quality-scoring-policy/v1"


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class QualityPayloadValidation:
    passed: bool
    reason_codes: tuple[str, ...]
    quality_score: float | None
    scored_case_count: int
    payload_case_count: int


def validate_quality_payload_score_artifact(
    artifact: Mapping[str, Any],
    *,
    expected_admission_head: str,
    expected_hard_gate_head: str,
    expected_quality_gate_head: str,
    expected_source_receipts_sha256: str,
    threshold: float = ANSWER_QUALITY_PASS_THRESHOLD,
) -> QualityPayloadValidation:
    reasons: list[str] = []
    if artifact.get("schema_version") != M27_QUALITY_PAYLOAD_SCORE_SCHEMA:
        reasons.append("QUALITY_PAYLOAD_SCHEMA_MISMATCH")
    if artifact.get("source_admission_head") != expected_admission_head:
        reasons.append("SOURCE_ADMISSION_HEAD_MISMATCH")
    if artifact.get("hard_gate_head") != expected_hard_gate_head:
        reasons.append("HARD_GATE_HEAD_MISMATCH")
    if artifact.get("quality_gate_head") != expected_quality_gate_head:
        reasons.append("QUALITY_GATE_HEAD_MISMATCH")
    if artifact.get("source_receipts_sha256") != expected_source_receipts_sha256:
        reasons.append("SOURCE_RECEIPTS_DIGEST_MISMATCH")
    for key, code in (
        ("evaluator_provider", "MISSING_EVALUATOR_PROVIDER"),
        ("evaluator_model", "MISSING_EVALUATOR_MODEL"),
        ("evaluator_identity", "MISSING_EVALUATOR_IDENTITY"),
        ("evaluator_version", "MISSING_EVALUATOR_VERSION"),
        ("sampling_policy", "MISSING_SAMPLING_POLICY"),
        ("scoring_policy_version", "MISSING_SCORING_POLICY_VERSION"),
    ):
        value = str(artifact.get(key) or "").strip()
        if not value:
            reasons.append(code)
        if key in {"evaluator_provider", "evaluator_model", "evaluator_identity"} and any(
            bad in value.casefold() for bad in ("mock", "placeholder", "synthetic", "fake")
        ):
            reasons.append("SYNTHETIC_EVALUATOR_IDENTITY_FORBIDDEN")
    if artifact.get("rubric_version") != ANSWER_QUALITY_RUBRIC_VERSION:
        reasons.append("QUALITY_RUBRIC_VERSION_MISMATCH")
    if artifact.get("scoring_policy_version") != M27_QUALITY_PAYLOAD_POLICY_VERSION:
        reasons.append("SCORING_POLICY_VERSION_MISMATCH")

    score_raw = artifact.get("quality_score")
    score: float | None = None
    if isinstance(score_raw, bool) or not isinstance(score_raw, (int, float)):
        reasons.append("QUALITY_SCORE_UNAVAILABLE")
    else:
        score = float(score_raw)
        if score < threshold:
            reasons.append("QUALITY_SCORE_BELOW_THRESHOLD")
        if not 0 <= score <= 100:
            reasons.append("QUALITY_SCORE_OUT_OF_RANGE")

    eligible = artifact.get("eligible_verified_answer_row_count")
    scored = artifact.get("case_count_scored")
    if isinstance(eligible, bool) or not isinstance(eligible, int) or eligible <= 0:
        reasons.append("ELIGIBLE_VERIFIED_COUNT_INVALID")
        eligible = 0
    if isinstance(scored, bool) or not isinstance(scored, int) or scored <= 0:
        reasons.append("NO_SEMANTIC_CASES_SCORED")
        scored = 0
    skipped = artifact.get("skipped_rows")
    if (
        not isinstance(skipped, int)
        or isinstance(skipped, bool)
        or skipped < 0
        or scored + skipped != eligible
    ):
        reasons.append("SCORING_COVERAGE_ACCOUNTING_MISMATCH")

    payloads = artifact.get("payload_records")
    scores = artifact.get("per_case_scores")
    payloads = payloads if isinstance(payloads, list) else []
    scores = scores if isinstance(scores, list) else []
    if len(payloads) != scored:
        reasons.append("PAYLOAD_RECORD_COUNT_MISMATCH")
    if len(scores) != scored:
        reasons.append("PER_CASE_SCORE_COUNT_MISMATCH")

    payload_by_id: dict[str, Mapping[str, Any]] = {}
    for row in payloads:
        if not isinstance(row, Mapping):
            reasons.append("INVALID_PAYLOAD_RECORD")
            continue
        case_id = str(row.get("case_id") or "")
        answer = row.get("answer_payload")
        if not case_id or not isinstance(answer, Mapping):
            reasons.append("INVALID_PAYLOAD_RECORD")
            continue
        if not str(answer.get("answer_text") or answer.get("answer") or "").strip():
            reasons.append("MISSING_ANSWER_SEMANTIC_PAYLOAD")
        if not isinstance(answer.get("selected_evidence"), list) or not answer.get(
            "selected_evidence"
        ):
            reasons.append("MISSING_EVIDENCE_SEMANTIC_PAYLOAD")
        if not isinstance(answer.get("citations"), list) or not answer.get("citations"):
            reasons.append("MISSING_CITATION_SEMANTIC_PAYLOAD")
        material = {
            "question": row.get("question"),
            "answer_payload": answer,
            "forensic_trace": row.get("forensic_trace"),
        }
        if row.get("input_digest") != canonical_digest(material):
            reasons.append("PAYLOAD_INPUT_DIGEST_MISMATCH")
        payload_by_id[case_id] = row

    for row in scores:
        if not isinstance(row, Mapping):
            reasons.append("INVALID_SCORE_RECORD")
            continue
        case_id = str(row.get("case_id") or "")
        payload = payload_by_id.get(case_id)
        if payload is None:
            reasons.append("SCORE_WITHOUT_PAYLOAD")
            continue
        if row.get("input_digest") != payload.get("input_digest"):
            reasons.append("SCORE_PAYLOAD_DIGEST_MISMATCH")
        if isinstance(row.get("score"), bool) or not isinstance(row.get("score"), (int, float)):
            reasons.append("INVALID_PER_CASE_SCORE")

    expected_scores_digest = canonical_digest(scores)
    if artifact.get("per_case_scores_digest") != expected_scores_digest:
        reasons.append("PER_CASE_SCORES_DIGEST_MISMATCH")
    if artifact.get("score_output_digest") != expected_scores_digest:
        reasons.append("SCORE_OUTPUT_DIGEST_MISMATCH")
    expected_inputs_digest = canonical_digest(
        [
            {"case_id": row.get("case_id"), "input_digest": row.get("input_digest")}
            for row in payloads
        ]
    )
    if artifact.get("source_input_digest") != expected_inputs_digest:
        reasons.append("SOURCE_INPUT_DIGEST_MISMATCH")

    proof = artifact.get("production_no_mutation_proof")
    if artifact.get("production_touched") is not False or not isinstance(proof, Mapping):
        reasons.append("PRODUCTION_NO_MUTATION_PROOF_MISSING")
    else:
        if proof.get("production_endpoint_called_for_answers") is not False:
            reasons.append("PRODUCTION_ANSWER_ENDPOINT_USED")
        if proof.get("production_datastore_writes") is not False:
            reasons.append("PRODUCTION_DATASTORE_MUTATION")
        if proof.get("release_pointer_mutation") is not False:
            reasons.append("RELEASE_POINTER_MUTATION")
    if artifact.get("deterministic_admission_is_not_quality_score") is not True:
        reasons.append("DETERMINISTIC_ADMISSION_SUBSTITUTION_RISK")

    return QualityPayloadValidation(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        quality_score=score,
        scored_case_count=int(scored),
        payload_case_count=len(payloads),
    )


__all__ = [
    "M27_QUALITY_PAYLOAD_POLICY_VERSION",
    "M27_QUALITY_PAYLOAD_SCORE_SCHEMA",
    "QualityPayloadValidation",
    "canonical_digest",
    "validate_quality_payload_score_artifact",
]
