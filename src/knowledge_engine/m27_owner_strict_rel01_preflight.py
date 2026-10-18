"""Fail-closed, metrics-only Owner P4 REL01 readiness preflight.

This module must NEVER certify REL01 or Production by itself. It audits exact
numerical boundaries, record completeness, rubric scope, and formal receipts,
then returns HOLD until an independent trusted issuer verifies signed Product,
H01, H03 and P3 source-bound evidence.

Unlike m27_release_hard_gates/v1, the Owner's additional user request requires
strict >95% actual success, >85 quality and complete-final-answer p95 <15s.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA = "m27.owner-strict-rel01-preflight/nonprod.v1"
EXACT_523 = 523
MIN_STRICT_SUCCESS_523 = 497
RUBRIC_SHA256 = "f0f3c2e66dad1b4520a77835d2340f4e471a3af435e2e5f2232f3855640db849"
NO_FORMAL_CERTIFICATE = "NOT_CERTIFIED_NONPROD_PREFLIGHT"


def _json_hash(obj: Mapping[str, Any]) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    candidate = float(value)
    return candidate if math.isfinite(candidate) else None


def check_owner_strict_metrics(
    cases: Sequence[Mapping[str, Any]] | None,
    quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate all actual rows, not summary-only or prefilled PASS fields.

    A local passing metrics vector is NOT independent authority. The actual
    evaluation must arrive from sealed evaluators on the same signed Product.
    """
    reasons: list[str] = []
    count = len(cases) if isinstance(cases, (list, tuple)) else 0
    if count != EXACT_523:
        reasons.append("FORMAL_523_RAW_CASES_MISSING")
    ids: set[str] = set()
    source_versions: set[str] = set()
    image_digests: set[str] = set()
    latency_ms: list[float] = []
    actual_success = 0
    for row in cases if isinstance(cases, (list, tuple)) else ():
        if not isinstance(row, Mapping):
            reasons.append("INVALID_CASE_RECORD")
            continue
        cid = row.get("case_id")
        if not isinstance(cid, str) or not cid or cid in ids:
            reasons.append("CASE_ID_MISSING_OR_DUPLICATE")
        else:
            ids.add(cid)
        s = row.get("source_head")
        i = row.get("signed_image_digest")
        if not isinstance(s, str) or len(s) != 40:
            reasons.append("CASE_SOURCE_HEAD_UNPINNED")
        else:
            source_versions.add(s)
        if not isinstance(i, str) or not i.startswith("sha256:") or len(i) != 71:
            reasons.append("CASE_SIGNED_IMAGE_DIGEST_MISSING")
        else:
            image_digests.add(i)
        sec = _finite_float(row.get("final_answer_latency_ms"))
        if sec is None or sec <= 0:
            reasons.append("LATENCY_MISSING_INVALID_OR_TIMEOUT_EXCLUDED")
        else:
            latency_ms.append(sec)
        if row.get("timed_out") is True or row.get("terminal_error") is True:
            reasons.append("TIMEOUT_OR_TERMINAL_ERROR_MUST_BE_ACCOUNTED")
        if row.get("independent_result") == "verified_success":
            if row.get("cited_final") is True and row.get("claim_supported") is True:
                actual_success += 1
            else:
                reasons.append("SUCCESS_WITHOUT_VERIFIED_CITATION_AND_CLAIM")
    if len(source_versions) != 1 or len(image_digests) != 1:
        reasons.append("SOURCE_IMAGE_NOT_SAME_VERSION")
    if count != len(latency_ms):
        reasons.append("LATENCY_DENOMINATOR_NOT_COMPLETE")
    if count == EXACT_523 and actual_success <= 0.95 * EXACT_523:
        reasons.append("ACTUAL_SUCCESS_NOT_STRICTLY_ABOVE_95_PERCENT")
    if count == EXACT_523 and actual_success < MIN_STRICT_SUCCESS_523:
        reasons.append("STRICT_SUCCESS_COUNT_BELOW_497")
    p95 = None
    if len(latency_ms) == EXACT_523:
        # Empirical nearest rank: ceil(0.95*523)=497th ordered observation.
        p95 = sorted(latency_ms)[math.ceil(0.95 * EXACT_523) - 1]
        if p95 >= 15000:
            reasons.append("COMPLETE_ANSWER_P95_NOT_STRICTLY_BELOW_15S")
    quality = quality if isinstance(quality, Mapping) else {}
    score = _finite_float(quality.get("score"))
    if score is None:
        reasons.append("INDEPENDENT_QUALITY_MISSING")
    elif score <= 85.0 or score > 100.0 or score < 0.0:
        reasons.append("QUALITY_NOT_STRICTLY_ABOVE_85")
    if quality.get("rubric_sha256") != RUBRIC_SHA256:
        reasons.append("OWNER_RUBRIC_SHA_MISMATCH")
    # The Owner file is explicitly a Suggested Questions / homepage rubric.
    # A scorer must independently attest its applicability to any QA set.
    if quality.get("rubric_scope") != "homepage_suggested_questions":
        reasons.append("RUBRIC_IS_NOT_A_GENERIC_TASK_QUALITY_STANDARD")
    if quality.get("independent_evaluator_attested") is not True:
        reasons.append("INDEPENDENT_EVALUATOR_NOT_ATTESTED")
    if quality.get("same_source_head") not in source_versions:
        reasons.append("QUALITY_SOURCE_HEAD_MISMATCH")
    if quality.get("same_signed_image_digest") not in image_digests:
        reasons.append("QUALITY_IMAGE_MISMATCH")
    result = {
        "schema": SCHEMA,
        "raw_case_count": count,
        "distinct_case_ids": len(ids),
        "independent_successes_with_citations": actual_success,
        "success_rate": actual_success / EXACT_523 if count == EXACT_523 else None,
        "measured_complete_answer_p95_ms": p95,
        "quality_score": score,
        "rubric_scope": quality.get("rubric_scope"),
        "metrics_consistent": not reasons,
        "formal_rel01_certified": False,
        "production_deployment_authorized": False,
        "reason_codes": sorted(set(reasons)),
    }
    result["preflight_sha256"] = _json_hash(result)
    return result


def current_formal_admission(
    metrics: Mapping[str, Any],
    *,
    trusted_registry: Mapping[str, Any] | None,
    official_gates: Mapping[str, Any] | None,
    validated_independent_receipts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only actual source admission. Never promotes self-declared evidence.

    Until an external signature verifier is integrated under a registered key,
    positive metrics and arbitrary JSON receipt booleans cannot certify REL01.
    """
    why = list(metrics.get("reason_codes", ()))
    if metrics.get("metrics_consistent") is not True:
        why.append("OWNER_STRICT_METRICS_NOT_PROVEN")
    reg = trusted_registry if isinstance(trusted_registry, Mapping) else {}
    if reg.get("schema") != "m27.d02.trust-registry/v1" or (
        not isinstance(reg.get("formal_enabled_issuer_count"), int)
        or reg.get("formal_enabled_issuer_count") <= 0
    ):
        why.append("NO_INDEPENDENT_ENABLED_TRUST_ROOT")
    if not isinstance(reg.get("issuers"), Mapping) or not reg.get("issuers"):
        why.append("NO_AUTHENTIC_ISSUER_REGISTRY_ENTRIES")
    gate = official_gates if isinstance(official_gates, Mapping) else {}
    delivery = gate.get("delivery") if isinstance(gate.get("delivery"), Mapping) else {}
    for key in ("C28", "E27", "B27", "F35", "REL01"):
        if delivery.get(key) != "PASS":
            why.append(key + "_OFFICIAL_RECEIPT_NOT_PASS")
    # No trusted independent cryptographic verification function is connected.
    # Deliberately reject even user-supplied {signed:true} / {verified:true}.
    why.append("NO_INDEPENDENT_CRYPTOGRAPHIC_RECEIPT_VERIFIER")
    result = {
        "schema": SCHEMA,
        "stage": "REL01_NONPROD_READONLY",
        "status": "HOLD",
        "qualified_product": False,
        "rel01_certified": False,
        "rel02_authorized": False,
        "production_deployed": False,
        "reason_codes": sorted(set(why)),
        "numeric_preflight_sha256": metrics.get("preflight_sha256"),
        "untrusted_receipt_fields_ignored": bool(validated_independent_receipts),
    }
    result["read_only_decision_sha256"] = _json_hash(result)
    return result


def evaluate_current_official_paths(*, trust_registry: Path, gate_state: Path) -> dict[str, Any]:
    """Fail closed from real current files, never load protected Gold or raw cases."""
    registry = json.loads(trust_registry.read_text(encoding="utf-8"))
    gates = json.loads(gate_state.read_text(encoding="utf-8"))
    # Real independent 523 raw cases are not admitted under P3 as of this time.
    metrics = check_owner_strict_metrics(None, None)
    return current_formal_admission(metrics, trusted_registry=registry, official_gates=gates)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="NONPROD READ-ONLY failclosed Owner strict REL01 preflight"
    )
    parser.add_argument("--trust-registry", type=Path, required=True)
    parser.add_argument("--official-gates", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate_current_official_paths(
            trust_registry=args.trust_registry,
            gate_state=args.official_gates,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        result = {
            "schema": SCHEMA, "status": "HOLD",
            "rel01_certified": False, "rel02_authorized": False,
            "production_deployed": False,
            "reason_codes": ["INVALID_OR_UNAVAILABLE_OFFICIAL_EVIDENCE"],
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("rel01_certified") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
