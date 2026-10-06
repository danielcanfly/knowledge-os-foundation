from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .qa_answer_quality_evaluator import (
    ANSWER_QUALITY_PASS_THRESHOLD,
    ANSWER_QUALITY_RUBRIC_VERSION,
    SEMANTIC_EVALUATOR_VERSION,
)

M27_INDEPENDENT_QUALITY_SCHEMA = "m27-independent-quality-score/v1"
M27_SCORING_POLICY_VERSION = "m27-independent-quality-scoring-policy/v1"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def per_case_scores_digest(rows: list[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class IndependentQualityArtifactValidation:
    passed: bool
    reason_codes: tuple[str, ...]
    quality_score: float | None
    evaluator_identity: str | None
    evaluator_provider: str | None
    evaluator_model: str | None
    rubric_version: str | None
    scoring_policy_version: str | None
    artifact_id: str | None
    case_count_scored: int
    sampling_policy: str | None
    source_receipts_sha256: str | None


def validate_independent_quality_artifact(
    artifact: Mapping[str, Any],
    *,
    expected_source_receipts_sha256: str,
    expected_release_candidate_head: str,
    expected_hard_gate_head: str,
    threshold: float = ANSWER_QUALITY_PASS_THRESHOLD,
) -> IndependentQualityArtifactValidation:
    reasons: list[str] = []
    if artifact.get("schema_version") != M27_INDEPENDENT_QUALITY_SCHEMA:
        reasons.append("QUALITY_ARTIFACT_SCHEMA_MISMATCH")
    if artifact.get("release_candidate_head") != expected_release_candidate_head:
        reasons.append("QUALITY_ARTIFACT_RELEASE_CANDIDATE_MISMATCH")
    if artifact.get("hard_gate_head") != expected_hard_gate_head:
        reasons.append("QUALITY_ARTIFACT_HARD_GATE_HEAD_MISMATCH")
    source_hash = str(artifact.get("source_receipts_sha256") or "").strip() or None
    if source_hash != expected_source_receipts_sha256:
        reasons.append("QUALITY_ARTIFACT_SOURCE_RECEIPTS_MISMATCH")

    evaluator_identity = str(artifact.get("evaluator_identity") or "").strip() or None
    evaluator_provider = str(artifact.get("evaluator_provider") or "").strip() or None
    evaluator_model = str(artifact.get("evaluator_model") or "").strip() or None
    rubric_version = str(artifact.get("rubric_version") or "").strip() or None
    scoring_policy_version = str(artifact.get("scoring_policy_version") or "").strip() or None
    if not evaluator_identity:
        reasons.append("MISSING_EVALUATOR_IDENTITY")
    if not evaluator_provider:
        reasons.append("MISSING_EVALUATOR_PROVIDER")
    if not evaluator_model:
        reasons.append("MISSING_EVALUATOR_MODEL")
    if not rubric_version:
        reasons.append("MISSING_RUBRIC_VERSION")
    elif rubric_version != ANSWER_QUALITY_RUBRIC_VERSION:
        reasons.append("QUALITY_RUBRIC_VERSION_MISMATCH")
    if not scoring_policy_version:
        reasons.append("MISSING_SCORING_POLICY_VERSION")
    elif scoring_policy_version != M27_SCORING_POLICY_VERSION:
        reasons.append("SCORING_POLICY_VERSION_MISMATCH")

    raw_score = artifact.get("quality_score")
    score: float | None = None
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        reasons.append("QUALITY_SCORER_UNAVAILABLE")
    else:
        score = float(raw_score)
        if score < 0 or score > 100:
            reasons.append("QUALITY_SCORE_OUT_OF_RANGE")
        elif score < threshold:
            reasons.append("QUALITY_SCORE_BELOW_THRESHOLD")

    case_count = artifact.get("case_count_scored")
    if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count <= 0:
        reasons.append("NO_SEMANTIC_CASES_SCORED")
        case_count = 0
    sampling_policy = str(artifact.get("sampling_policy") or "").strip() or None
    if not sampling_policy:
        reasons.append("MISSING_SAMPLING_POLICY")

    rows = artifact.get("per_case_scores")
    expected_digest = str(artifact.get("per_case_scores_digest") or "").strip()
    if not isinstance(rows, list) or not rows:
        reasons.append("MISSING_PER_CASE_SCORE_EVIDENCE")
    else:
        normalized_rows = [row for row in rows if isinstance(row, Mapping)]
        if len(normalized_rows) != len(rows) or len(rows) != case_count:
            reasons.append("PER_CASE_SCORE_COUNT_MISMATCH")
        if not expected_digest or per_case_scores_digest(normalized_rows) != expected_digest:
            reasons.append("PER_CASE_SCORES_DIGEST_MISMATCH")

    if artifact.get("production_touched") is not False:
        reasons.append("PRODUCTION_MUTATION_EVIDENCE")
    if artifact.get("deterministic_admission_is_not_quality_score") is not True:
        reasons.append("DETERMINISTIC_ADMISSION_QUALITY_SUBSTITUTION_RISK")

    artifact_reasons = artifact.get("reason_codes")
    if isinstance(artifact_reasons, list):
        reasons.extend(str(code) for code in artifact_reasons if str(code).strip())

    return IndependentQualityArtifactValidation(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        quality_score=score,
        evaluator_identity=evaluator_identity,
        evaluator_provider=evaluator_provider,
        evaluator_model=evaluator_model,
        rubric_version=rubric_version,
        scoring_policy_version=scoring_policy_version,
        artifact_id=str(artifact.get("artifact_id") or "").strip() or None,
        case_count_scored=int(case_count),
        sampling_policy=sampling_policy,
        source_receipts_sha256=source_hash,
    )


def unavailable_quality_artifact(
    *,
    release_candidate_head: str,
    hard_gate_head: str,
    source_receipts_sha256: str,
    reason_codes: list[str],
    notes: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": M27_INDEPENDENT_QUALITY_SCHEMA,
        "artifact_id": "m27-independent-quality-unavailable",
        "release_candidate_head": release_candidate_head,
        "hard_gate_head": hard_gate_head,
        "source_receipts_sha256": source_receipts_sha256,
        "evaluator_identity": None,
        "evaluator_provider": None,
        "evaluator_model": None,
        "evaluator_contract_available": True,
        "evaluator_contract_version": SEMANTIC_EVALUATOR_VERSION,
        "rubric_version": ANSWER_QUALITY_RUBRIC_VERSION,
        "scoring_policy_version": M27_SCORING_POLICY_VERSION,
        "threshold": ANSWER_QUALITY_PASS_THRESHOLD,
        "quality_score": None,
        "passed": False,
        "case_count_scored": 0,
        "sampling_policy": "preferred-all-verified-answer-rows; no scoring performed",
        "per_case_scores": [],
        "per_case_scores_digest": per_case_scores_digest([]),
        "safe_terminals_policy": (
            "separate appropriateness/correctness evidence; "
            "not substituted for semantic answer score"
        ),
        "deterministic_admission_is_not_quality_score": True,
        "production_touched": False,
        "reason_codes": sorted(set(reason_codes)),
        "notes": notes,
    }
    return payload


__all__ = [
    "M27_INDEPENDENT_QUALITY_SCHEMA",
    "M27_SCORING_POLICY_VERSION",
    "IndependentQualityArtifactValidation",
    "per_case_scores_digest",
    "sha256_file",
    "unavailable_quality_artifact",
    "validate_independent_quality_artifact",
]
