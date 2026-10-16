from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdmissionEvidence:
    expected_denominator: int
    observed_denominator: int
    passed_count: int
    safe_terminal_expected: int
    safe_terminal_correct: int
    candidate_commit: str
    expected_candidate_commit: str
    source_tree: str
    expected_source_tree: str
    clock_monotonic: bool
    latency_p95_ms: float | None
    latency_limit_ms: float
    idp_receipt_valid: bool
    signer_receipt_valid: bool
    source_fresh: bool
    issuer_authorized: bool
    custody_independent: bool
    release_authorized: bool
    production_touched: bool = False


def evaluate_f35_rel01(evidence: AdmissionEvidence) -> dict[str, object]:
    reasons: list[str] = []
    if evidence.observed_denominator != evidence.expected_denominator:
        reasons.append("FIXED_DENOMINATOR_MISMATCH")
    if evidence.passed_count != evidence.expected_denominator:
        reasons.append("FULL_DENOMINATOR_NOT_PASSED")
    if evidence.safe_terminal_correct != evidence.safe_terminal_expected:
        reasons.append("FALSE_SAFE_OR_UNSAFE_TERMINAL")
    if evidence.candidate_commit != evidence.expected_candidate_commit:
        reasons.append("CANDIDATE_COMMIT_MISMATCH")
    if evidence.source_tree != evidence.expected_source_tree:
        reasons.append("SOURCE_TREE_MISMATCH")
    if not evidence.clock_monotonic:
        reasons.append("CLOCK_NOT_MONOTONIC")
    if evidence.latency_p95_ms is None:
        reasons.append("LATENCY_MISSING")
    elif evidence.latency_p95_ms > evidence.latency_limit_ms:
        reasons.append("LATENCY_OUTLIER")
    if not evidence.idp_receipt_valid:
        reasons.append("IDP_RECEIPT_ABSENT_OR_INVALID")
    if not evidence.signer_receipt_valid:
        reasons.append("SIGNER_RECEIPT_ABSENT_OR_INVALID")
    if not evidence.source_fresh:
        reasons.append("STALE_SOURCE")
    if not evidence.issuer_authorized:
        reasons.append("WRONG_OR_UNAUTHORIZED_ISSUER")
    if not evidence.custody_independent:
        reasons.append("CUSTODY_NOT_INDEPENDENT")
    if not evidence.release_authorized:
        reasons.append("REL01_AUTHORIZATION_ABSENT")
    if evidence.production_touched:
        reasons.append("PRODUCTION_TOUCH_FORBIDDEN")
    passed = not reasons
    return {
        "schema": "m27-b03-r01-f35-rel01-admission-gate/v1",
        "passed": passed,
        "f35_status": "CERTIFIED" if passed else "HOLD",
        "rel01_status": "CERTIFIED" if passed else "NOT_CERTIFIED",
        "rel02_status": "NO_GO",
        "formal_product_go": False,
        "production_touched": evidence.production_touched,
        "reason_codes": sorted(set(reasons)),
        "observed_denominator": evidence.observed_denominator,
        "expected_denominator": evidence.expected_denominator,
    }
