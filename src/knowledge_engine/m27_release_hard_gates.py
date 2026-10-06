from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .m27_isolated_streaming import M27_ISOLATED_STREAM_SCHEMA

M27_RELEASE_HARD_GATE_SCHEMA = "m27-release-hard-gates/v1"
M27_QUALITY_GATE_SCHEMA = "m27-release-quality-hard-gate/v1"
M27_STREAMING_GATE_SCHEMA = "m27-first-answer-text-streaming-gate/v1"
M27_RELEASE_HARD_GATE_READY = "M27_RELEASE_HARD_GATES_READY"
M27_RELEASE_HARD_GATE_NOT_READY = "M27_RELEASE_HARD_GATES_NOT_READY_WITH_DIAGNOSIS"
M27_RELEASE_HARD_GATE_BLOCKED = "M27_RELEASE_HARD_GATE_CLOSURE_BLOCKED"


def _stable_json(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(prefix: str, data: Mapping[str, Any]) -> str:
    return f"{prefix}_{hashlib.sha256(_stable_json(data)).hexdigest()[:24]}"


def _summary(receipts: Mapping[str, Any]) -> Mapping[str, Any]:
    gates = receipts.get("gates")
    if not isinstance(gates, Mapping):
        return {}
    full523 = gates.get("full523")
    if not isinstance(full523, Mapping):
        return {}
    summary = full523.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _cleanup(receipts: Mapping[str, Any]) -> Mapping[str, Any]:
    cleanup = receipts.get("cleanup_after_full523") or receipts.get("cleanup")
    return cleanup if isinstance(cleanup, Mapping) else {}


def _release(receipts: Mapping[str, Any]) -> Mapping[str, Any]:
    release = receipts.get("release")
    return release if isinstance(release, Mapping) else {}


def admission_receipts_checks(receipts: Mapping[str, Any]) -> dict[str, Any]:
    summary = _summary(receipts)
    cleanup = _cleanup(receipts)
    release = _release(receipts)
    reasons: list[str] = []
    if not summary:
        reasons.append("MISSING_FULL523_RECEIPTS")
    if summary.get("gate") != "full523" or summary.get("case_count") != 523:
        reasons.append("MISSING_FULL523")
    if summary.get("gate_pass") is not True or summary.get("passed_count") != 523:
        reasons.append("FULL523_NOT_PASSED")
    if float(summary.get("cited_final_answer_rate", 0.0) or 0.0) < 0.95:
        reasons.append("CITED_FINAL_ANSWER_RATE_BELOW_THRESHOLD")
    if summary.get("verified_answer_cited_count") != summary.get("verified_answer_expected_count"):
        reasons.append("CITED_FINAL_ANSWER_COUNT_MISMATCH")
    if float(summary.get("safe_terminal_correctness", 0.0) or 0.0) < 1.0:
        reasons.append("SAFE_TERMINAL_CORRECTNESS_NOT_100")
    if float(summary.get("citation_provenance_integrity", 0.0) or 0.0) < 1.0:
        reasons.append("CITATION_PROVENANCE_INTEGRITY_NOT_100")
    if summary.get("production_no_mutation") is not True:
        reasons.append("PRODUCTION_MUTATION_EVIDENCE")
    if cleanup.get("production_touched") is not False:
        reasons.append("POST_CLEANUP_PRODUCTION_MUTATION_EVIDENCE")
    if cleanup.get("owned_eval_containers_after") not in (0, None):
        reasons.append("EVAL_CONTAINER_LEFT_RUNNING")
    if cleanup.get("port_18080_listeners_after") not in (0, None):
        reasons.append("ISOLATED_LISTENER_LEFT_RUNNING")
    if release.get("deployment_performed") is not False:
        reasons.append("DEPLOYMENT_WAS_PERFORMED")
    if release.get("deployment_authorized") is not False:
        reasons.append("DEPLOYMENT_AUTHORIZATION_PRESENT")
    return {
        "schema_version": "m27-admission-receipt-hard-gate-checks/v1",
        "passed": not reasons,
        "reason_codes": tuple(sorted(set(reasons))),
        "full523": {
            "case_count": summary.get("case_count"),
            "passed_count": summary.get("passed_count"),
            "cited_final_answer_rate": summary.get("cited_final_answer_rate"),
            "verified_answer_cited_count": summary.get("verified_answer_cited_count"),
            "verified_answer_expected_count": summary.get("verified_answer_expected_count"),
            "safe_terminal_correctness": summary.get("safe_terminal_correctness"),
            "safe_terminal_correct_count": summary.get("safe_terminal_correct_count"),
            "safe_terminal_expected_count": summary.get("safe_terminal_expected_count"),
            "citation_provenance_integrity": summary.get("citation_provenance_integrity"),
            "quality_score": summary.get("quality_score"),
            "streaming_status": summary.get("streaming_status"),
        },
        "production_no_mutation": summary.get("production_no_mutation") is True
        and cleanup.get("production_touched") is False,
        "release_report_only": release.get("canary_plan_report_only") is True
        and release.get("deployment_performed") is False,
    }


@dataclass(frozen=True, slots=True)
class QualityScoreEvidence:
    score: float | None
    evaluator_identity: str | None
    rubric_version: str | None
    artifact_version: str | None = None
    stale: bool = False
    notes: str = ""


def evaluate_quality_hard_gate(
    *,
    admission_receipts: Mapping[str, Any],
    evidence: QualityScoreEvidence | None = None,
    threshold: float = 85.0,
) -> dict[str, Any]:
    receipt_checks = admission_receipts_checks(admission_receipts)
    reasons = list(receipt_checks["reason_codes"])
    evidence = evidence or QualityScoreEvidence(
        score=None,
        evaluator_identity=None,
        rubric_version=None,
        notes=(
            "No independent semantic quality evaluator was configured "
            "for the deterministic admission harness."
        ),
    )
    if evidence.score is None:
        reasons.append("QUALITY_SCORER_UNAVAILABLE")
    if not evidence.evaluator_identity:
        reasons.append("MISSING_EVALUATOR_IDENTITY")
    if not evidence.rubric_version:
        reasons.append("MISSING_RUBRIC_VERSION")
    if evidence.stale:
        reasons.append("STALE_QUALITY_ARTIFACT")
    if evidence.score is not None and float(evidence.score) < threshold:
        reasons.append("QUALITY_SCORE_BELOW_THRESHOLD")
    passed = not reasons
    artifact = {
        "schema_version": M27_QUALITY_GATE_SCHEMA,
        "quality_score": evidence.score,
        "threshold": threshold,
        "evaluator_identity": evidence.evaluator_identity,
        "rubric_version": evidence.rubric_version,
        "artifact_version": evidence.artifact_version,
        "stale": evidence.stale,
        "independent_quality_score_available": evidence.score is not None
        and bool(evidence.evaluator_identity)
        and bool(evidence.rubric_version),
        "deterministic_admission_is_not_quality_score": True,
        "admission_receipts": receipt_checks,
        "passed": passed,
        "release_blocking": not passed,
        "reason_codes": tuple(sorted(set(reasons))),
        "notes": evidence.notes,
    }
    return {**artifact, "artifact_id": _sha("m27_quality_gate", artifact)}


def evaluate_streaming_hard_gate(
    events: Sequence[Mapping[str, Any]], *, final_answer_text: str | None = None
) -> dict[str, Any]:
    names = [str(event.get("event", "")) for event in events]
    reasons: list[str] = []
    if not events:
        reasons.append("FIRST_ANSWER_TEXT_STREAMING_NOT_PROVEN")
    if any(event.get("schema_version") != M27_ISOLATED_STREAM_SCHEMA for event in events):
        reasons.append("STREAM_SCHEMA_MISMATCH")
    material_indices = [
        index
        for index, name in enumerate(names)
        if name in {"verified_claim_ready", "cited_segment_ready"}
    ]
    final_indices = [index for index, name in enumerate(names) if name == "final_answer_done"]
    safe_terminal_indices = [
        index for index, name in enumerate(names) if name == "safe_abstention_done"
    ]
    if safe_terminal_indices and material_indices:
        reasons.append("SAFE_TERMINAL_EMITTED_MATERIAL_TEXT")
    if not material_indices:
        reasons.append("FIRST_MATERIAL_TEXT_EVENT_MISSING")
    if not final_indices:
        reasons.append("FINAL_ANSWER_DONE_MISSING")
    if material_indices and final_indices and min(material_indices) >= final_indices[-1]:
        reasons.append("MATERIAL_TEXT_NOT_BEFORE_FINAL_COMPLETION")
    cited_segments = [event for event in events if event.get("event") == "cited_segment_ready"]
    if final_answer_text is not None:
        segment_text = str(cited_segments[-1].get("text", "")) if cited_segments else ""
        if segment_text != final_answer_text:
            reasons.append("FINAL_ANSWER_PARITY_MISMATCH")
    for event in events:
        if event.get("event") in {"verified_claim_ready", "cited_segment_ready"}:
            citations = event.get("citations")
            if not isinstance(citations, list) or not citations:
                reasons.append("MATERIAL_TEXT_WITHOUT_CITATIONS")
                break
    passed = not reasons
    artifact = {
        "schema_version": M27_STREAMING_GATE_SCHEMA,
        "endpoint_path": "/v1/answers/stream",
        "stream_schema": M27_ISOLATED_STREAM_SCHEMA,
        "passed": passed,
        "release_blocking": not passed,
        "reason_codes": tuple(sorted(set(reasons))),
        "event_sequence": tuple(names),
        "first_material_event_index": min(material_indices) if material_indices else None,
        "final_answer_done_index": final_indices[-1] if final_indices else None,
        "safe_terminal_emits_no_material_text": not (safe_terminal_indices and material_indices),
        "final_answer_parity_checked": final_answer_text is not None,
    }
    return {**artifact, "artifact_id": _sha("m27_streaming_gate", artifact)}


def decide_release_hard_gates(
    *,
    admission_receipts: Mapping[str, Any],
    quality_gate: Mapping[str, Any],
    streaming_gate: Mapping[str, Any],
) -> dict[str, Any]:
    admission = admission_receipts_checks(admission_receipts)
    blockers: list[str] = []
    if not admission["passed"]:
        blockers.extend(str(code) for code in admission["reason_codes"])
    if quality_gate.get("passed") is not True:
        blockers.extend(str(code) for code in quality_gate.get("reason_codes", ()))
    if streaming_gate.get("passed") is not True:
        blockers.extend(str(code) for code in streaming_gate.get("reason_codes", ()))
    if not admission.get("production_no_mutation"):
        blockers.append("PRODUCTION_MUTATION_EVIDENCE")
    if not admission.get("release_report_only"):
        blockers.append("RELEASE_PLAN_NOT_REPORT_ONLY")
    blockers = sorted(set(blockers))
    status = M27_RELEASE_HARD_GATE_READY if not blockers else M27_RELEASE_HARD_GATE_NOT_READY
    decision = {
        "schema_version": M27_RELEASE_HARD_GATE_SCHEMA,
        "status": status,
        "release_ready": status == M27_RELEASE_HARD_GATE_READY,
        "production_deployment_ready": status == M27_RELEASE_HARD_GATE_READY,
        "report_only_candidate_preserved": admission.get("passed") is True,
        "admission_receipts": admission,
        "quality_gate": dict(quality_gate),
        "streaming_gate": dict(streaming_gate),
        "production_touched": False,
        "deployment_performed": False,
        "remaining_blockers": tuple(blockers),
    }
    return {**decision, "decision_id": _sha("m27_release_hard_gate", decision)}


__all__ = [
    "M27_RELEASE_HARD_GATE_BLOCKED",
    "M27_RELEASE_HARD_GATE_NOT_READY",
    "M27_RELEASE_HARD_GATE_READY",
    "QualityScoreEvidence",
    "admission_receipts_checks",
    "decide_release_hard_gates",
    "evaluate_quality_hard_gate",
    "evaluate_streaming_hard_gate",
]
