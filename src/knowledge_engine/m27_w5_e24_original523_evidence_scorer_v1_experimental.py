"""Read-only, fail-closed original-523 signed evidence evaluator.

No hidden question bodies, provider, VM or network calls. The historical Stage30O
results and unsigned A19/F20 V2 contract are never accepted as current outcomes.
Only *independently provisioned* Ed25519 roots can validate assertions; local
synthetic roots NEVER confer official release authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "m27.w5.e24.signed_original523.v1"
ROSTER_VERSION = "m27.w5.e24.immutable_roster.v1"
OUTCOMES_VERSION = "m27.w5.e24.current_outcomes.v1"
REGISTRY_VERSION = "m27.w5.e24.external_trust_registry.v1"
HISTORICAL_SHA256 = "e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137"
BUCKETS = {
    ("live", "verified_cited_answer"): 237,
    ("live", "safe_abstention"): 52,
    ("live", "rejected_before_provider"): 52,
    ("replay", "budget_terminal"): 26,
    ("replay", "m26_invariant"): 26,
    ("replay", "governance_contract"): 130,
}
LIVE = frozenset(k for k in BUCKETS if k[0] == "live")
SCORED_STATUSES = frozenset({
    "COMPLETE_CITED_FINAL", "SAFE_ABSTENTION", "REJECTED_BEFORE_PROVIDER",
    "REPLAY_PASS", "TIMEOUT", "ERROR", "CANCELLED", "WRONG_REJECTION",
    "WRONG_ABSTENTION", "MISSING", "REPLAY_FAIL",
})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
RECEIPT_KEYS = frozenset({
    "case_id", "mode", "expectation", "status", "timing", "client_complete",
    "client_ack_sha256", "answer_sha256", "provider_dispatch_count",
    "provider_telemetry_proven", "authority_trace_sha256", "leak_detected",
    "source_assertion", "grader_assertion",
})
SOURCE_KEYS = frozenset({
    "case_id", "run_id", "answer_sha256", "source_sha256", "revision",
    "span_start", "span_end", "source_index_sha256",
    "permission_grant_sha256", "valid",
})
GRADE_KEYS = frozenset({
    "case_id", "run_id", "answer_sha256", "source_claim_sha256",
    "score", "critical_error", "pass", "category",
})
TIMING_KEYS = frozenset({"start_ns", "end_ns", "first_substantive_ns"})
MAX_BYTES = 10 * 1024 * 1024


class Denied(ValueError):
    """Denied admission, with stable, safe machine-readable cause."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class OpaqueAssignment:
    case_id: str
    mode: str
    expectation: str


@dataclass(frozen=True, slots=True)
class CaseDecision:
    fingerprint: str
    mode: str
    expectation: str
    status: str
    qualified: bool
    reason: str
    duration_ms: float | None


def canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def is_sha(v: object) -> bool:
    return isinstance(v, str) and HEX64.fullmatch(v) is not None


def is_ident(v: object) -> bool:
    return isinstance(v, str) and IDENT.fullmatch(v) is not None


def integer(v: object, minimum: int = 0) -> bool:
    return type(v) is int and v >= minimum


def required(condition: bool, reason: str) -> None:
    if not condition:
        raise Denied(reason)


def signed_payload(item: Any, *, role: str, roots: dict[str, Any]) -> dict[str, Any]:
    required(isinstance(item, dict), "SIGNED_OBJECT_REQUIRED")
    required(set(item) == {"payload", "signature"}, "SIGNED_ENVELOPE_FIELDS_INVALID")
    data = item["payload"]
    claim = item["signature"]
    required(isinstance(data, dict) and isinstance(claim, dict), "SIGNED_ENVELOPE_INVALID")
    required(set(claim) == {"key_id", "signature_hex"}, "SIGNATURE_FIELDS_INVALID")
    root = roots.get(role)
    required(isinstance(root, dict), "MISSING_INDEPENDENT_ROLE_ROOT_" + role)
    required(claim["key_id"] == root.get("key_id"), "UNTRUSTED_SIGNER_" + role)
    required(root.get("role") == role, "ROLE_MISMATCH_" + role)
    required(root.get("tier") in {"AUTHENTICATED_EXTERNAL", "SYNTHETIC_FIXTURE"},
             "TRUST_TIER_INVALID")
    required(is_ident(root.get("principal")), "SIGNER_IDENTITY_MISSING")
    key_hex = root.get("public_key_hex")
    sig_hex = claim.get("signature_hex")
    required(isinstance(key_hex, str) and re.fullmatch(r"[0-9a-f]{64}", key_hex)
             is not None, "PUBLIC_KEY_INVALID_" + role)
    required(isinstance(sig_hex, str) and re.fullmatch(r"[0-9a-f]{128}", sig_hex)
             is not None, "SIGNATURE_FORMAT_INVALID_" + role)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(
            bytes.fromhex(sig_hex), canonical(data),
        )
    except ImportError as exc:
        raise Denied("CRYPTOGRAPHIC_VERIFIER_NOT_INSTALLED") from exc
    except Exception as exc:
        raise Denied("SIGNATURE_VERIFICATION_FAILED_" + role) from exc
    return data


def trusted_roots(registry: dict[str, Any], pinned_sha256: str) -> dict[str, Any]:
    required(is_sha(pinned_sha256) and sha(registry) == pinned_sha256,
             "EXTERNALLY_PINNED_ROOT_HASH_MISMATCH")
    required(registry.get("schema") == REGISTRY_VERSION, "TRUST_SCHEMA_INVALID")
    roots = registry.get("roots")
    required(isinstance(roots, dict), "ROOTS_INVALID")
    required(set(roots) == {
        "rights_issuer", "evaluator", "observer", "source_verifier", "grader",
    }, "FIVE_SEPARATE_TRUST_ROLES_REQUIRED")
    principals = [v.get("principal") for v in roots.values() if isinstance(v, dict)]
    keys = [v.get("key_id") for v in roots.values() if isinstance(v, dict)]
    required(len(principals) == 5 and len(set(principals)) == 5
             and len(set(keys)) == 5, "SIGNER_INDEPENDENCE_NOT_PROVEN")
    tiers = {v.get("tier") for v in roots.values()}
    required(len(tiers) == 1, "MIXED_TRUST_TIERS_INVALID")
    return roots


def read_json(path: str) -> dict[str, Any]:
    """Bounded, regular, non-symlink, single-fd read; JSON duplicate keys denied."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        required(stat.S_ISREG(st.st_mode) and st.st_size <= MAX_BYTES,
                 "INPUT_NOT_BOUNDED_REGULAR_FILE")
        chunks: list[bytes] = []
        total = 0
        while True:
            piece = os.read(fd, 65536)
            if not piece:
                break
            total += len(piece)
            required(total <= MAX_BYTES, "INPUT_TOO_LARGE")
            chunks.append(piece)
    finally:
        os.close(fd)

    def no_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, val in items:
            required(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = val
        return result

    try:
        doc = json.loads(b"".join(chunks), object_pairs_hook=no_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             Denied("NONFINITE_NUMBER")
                         ))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Denied("JSON_INVALID") from exc
    required(isinstance(doc, dict), "ROOT_NOT_OBJECT")
    return doc


def freeze_roster(roster: dict[str, Any]) -> tuple[OpaqueAssignment, ...]:
    required(roster.get("schema") == ROSTER_VERSION, "ROSTER_SCHEMA_INVALID")
    required(set(roster) == {"schema", "cases"}, "ROSTER_HIDDEN_FIELDS_OR_EXTRA_DATA")
    cases = roster.get("cases")
    required(isinstance(cases, list) and len(cases) == 523, "FROZEN_523_COUNT_INVALID")
    counts: Counter[tuple[str, str]] = Counter()
    result: list[OpaqueAssignment] = []
    seen: set[str] = set()
    for case in cases:
        required(isinstance(case, dict) and set(case) == {
            "case_id", "mode", "expectation",
        }, "ROSTER_CASE_FIELDS_OR_HIDDEN_CONTENT")
        obj = OpaqueAssignment(**case)
        required(is_ident(obj.case_id), "CASE_ID_INVALID")
        required(obj.case_id not in seen, "DUPLICATE_ROSTER_ID")
        seen.add(obj.case_id)
        counts[(obj.mode, obj.expectation)] += 1
        result.append(obj)
    required(dict(counts) == BUCKETS, "IMMUTABLE_MODE_DENOMINATOR_TAMPER")
    return tuple(result)


def approved_manifest(
    item: dict[str, Any], roots: dict[str, Any], roster: dict[str, Any],
    outcomes: dict[str, Any], now: datetime,
) -> dict[str, Any]:
    required(item.get("contract_status") == "APPROVED"
             and item.get("schema") == VERSION, "DRAFT_OR_UNAPPROVED_CONTRACT")
    required(set(item) == {"schema", "contract_status", "payload", "signatures"},
             "MANIFEST_FIELDS_INVALID")
    payload = item["payload"]
    signatures = item["signatures"]
    required(isinstance(payload, dict) and isinstance(signatures, dict),
             "MANIFEST_AUTHORITY_INVALID")
    required(set(payload) == {
        "source_corpus_sha256", "roster_sha256", "outcomes_sha256",
        "official_run_id", "purpose", "mode_counts", "rights_grant_sha256",
        "rubric_sha256", "source_index_sha256", "image_sha256",
        "runner_sha256", "build_sha256", "client_instrumentation_sha256",
        "candidate_git40", "candidate_tree40", "license_scope",
        "independent_native_client", "independent_grader",
        "issued_at_utc", "expires_at_utc",
    }, "MANIFEST_UNRECOGNIZED_OR_HIDDEN_FIELDS")
    required(set(signatures) == {"rights_issuer", "evaluator"},
             "DUAL_APPROVAL_REQUIRED")
    for role in ("rights_issuer", "evaluator"):
        signed = {"payload": payload, "signature": signatures[role]}
        signed_payload(signed, role=role, roots=roots)
    required(payload.get("source_corpus_sha256") == HISTORICAL_SHA256,
             "ORIGINAL_SOURCE_LINEAGE_NOT_PINNED")
    required(payload.get("roster_sha256") == sha(roster), "FROZEN_ROSTER_SHA_MISMATCH")
    required(payload.get("outcomes_sha256") == sha(outcomes), "OUTCOME_SHA_MISMATCH")
    required(payload.get("mode_counts") == {
        f"{m}/{e}": n for (m, e), n in BUCKETS.items()
    }, "MANIFEST_DENOMINATOR_TAMPER")
    required(is_ident(payload.get("official_run_id"))
             and payload.get("purpose") == "ORIGINAL523_CURRENT_EVALUATION_ONE_SHOT",
             "OFFICIAL_CURRENT_RUN_BINDING_MISSING")
    for key in ("rights_grant_sha256", "rubric_sha256", "source_index_sha256",
                "image_sha256", "runner_sha256", "build_sha256",
                "client_instrumentation_sha256"):
        required(is_sha(payload.get(key)), "MANIFEST_PIN_MISSING_" + key)
    for key in ("candidate_git40", "candidate_tree40"):
        v = payload.get(key)
        required(isinstance(v, str) and HEX40.fullmatch(v) is not None,
                 "CANDIDATE_PIN_MISSING_" + key)
    required(payload.get("license_scope") == "EVALUATION_ONLY",
             "SOURCE_RIGHTS_NOT_EVALUATION_ONLY")
    required(payload.get("independent_native_client") is True
             and payload.get("independent_grader") is True,
             "INDEPENDENT_CLIENT_OR_GRADER_UNVERIFIED")
    try:
        issued = datetime.fromisoformat(payload["issued_at_utc"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(payload["expires_at_utc"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise Denied("AUTHORITY_WINDOW_INVALID") from exc
    required(issued.tzinfo is not None and expires.tzinfo is not None,
             "AUTHORITY_TIMEZONE_REQUIRED")
    required(issued <= now < expires, "AUTHORITY_EXPIRED_OR_NOT_YET_ISSUED")
    return payload


def _proof(
    item: Any, role: str, roots: dict[str, Any], expected: dict[str, Any],
    allowed: frozenset[str],
) -> dict[str, Any]:
    data = signed_payload(item, role=role, roots=roots)
    required(set(data) == allowed, role.upper() + "_ASSERTION_FIELDS_INVALID")
    for k, v in expected.items():
        required(data.get(k) == v, role.upper() + "_ASSERTION_UNBOUND_" + k)
    return data


def _duration(entry: dict[str, Any], mode: str) -> tuple[float | None, bool]:
    if mode != "live":
        required(entry.get("timing") is None, "REPLAY_IN_LIVE_TIMING_POPULATION")
        return None, False
    timing = entry.get("timing")
    if not isinstance(timing, dict) or set(timing) != TIMING_KEYS:
        return None, False
    start = timing.get("start_ns")
    end = timing.get("end_ns")
    first = timing.get("first_substantive_ns")
    if not integer(start) or not integer(end) or end < start:
        return None, False
    if first is not None and not integer(first):
        return None, False
    valid_first = first is not None and start < first < end
    return (end - start) / 1_000_000, valid_first


def _case_score(
    assignment: OpaqueAssignment, entry: dict[str, Any], roots: dict[str, Any],
    manifest: dict[str, Any],
) -> CaseDecision:
    fp = hashlib.sha256(("E24-opaque:" + assignment.case_id).encode()).hexdigest()[:20]
    bucket = assignment.expectation
    required(set(entry) <= RECEIPT_KEYS, "PROTECTED_TEXT_OR_UNEXPECTED_RECEIPT_FIELD")
    required(entry.get("case_id") == assignment.case_id
             and entry.get("mode") == assignment.mode
             and entry.get("expectation") == bucket, "OUTCOME_MODE_MISMATCH")
    status = entry.get("status")
    required(status in SCORED_STATUSES, "UNRECOGNIZED_TERMINAL_STATUS")
    dur, first_ok = _duration(entry, assignment.mode)
    context = {
        "case_id": assignment.case_id,
        "run_id": manifest["official_run_id"],
        "answer_sha256": entry.get("answer_sha256"),
    }
    grade = _proof(entry.get("grader_assertion"), "grader", roots, context,
                   GRADE_KEYS)
    required(grade.get("category") == bucket and type(grade.get("pass")) is bool
             and type(grade.get("critical_error")) is bool,
             "INDEPENDENT_GRADE_MALFORMED")
    if entry.get("leak_detected") is not False:
        return CaseDecision(fp, assignment.mode, bucket, status, False,
                            "PROTECTED_ANSWER_LEAK_OR_UNKNOWN", dur)
    if assignment.mode == "live" and dur is None:
        return CaseDecision(fp, "live", bucket, status, False,
                            "CLIENT_LATENCY_UNKNOWN", None)
    if bucket == "verified_cited_answer":
        if status != "COMPLETE_CITED_FINAL":
            return CaseDecision(fp, "live", bucket, status, False,
                                "NO_COMPLETE_CITED_FINAL", dur)
        if not is_sha(entry.get("answer_sha256")):
            return CaseDecision(fp, "live", bucket, status, False,
                                "ANSWER_DIGEST_MISSING", dur)
        proof = _proof(entry.get("source_assertion"), "source_verifier", roots,
                       context, SOURCE_KEYS)
        allowed = (
            is_sha(proof.get("source_sha256"))
            and is_ident(proof.get("revision"))
            and is_sha(proof.get("source_index_sha256"))
            and proof.get("source_index_sha256") == manifest["source_index_sha256"]
            and proof.get("permission_grant_sha256") == manifest["rights_grant_sha256"]
            and integer(proof.get("span_start"))
            and integer(proof.get("span_end"), 1)
            and proof["span_end"] > proof["span_start"]
            and proof.get("valid") is True
        )
        grade_ok = (
            type(grade.get("score")) in (int, float)
            and math.isfinite(grade["score"]) and 85 <= grade["score"] <= 100
            and grade.get("critical_error") is False
            and grade.get("pass") is True
            and grade.get("source_claim_sha256") == sha(proof)
        )
        client_ok = (entry.get("client_complete") is True and first_ok
                     and is_sha(entry.get("client_ack_sha256")))
        if not allowed:
            why = "SOURCE_NATIVE_SPAN_REVISION_PERMISSION_INVALID"
        elif not grade_ok:
            why = "INDEPENDENT_QUALITY_BELOW_85_OR_CRITICAL"
        elif not client_ok:
            why = "CLIENT_PRETERMINAL_SUBSTANTIVE_ACK_MISSING"
        else:
            why = "QUALIFIED_SOURCE_NATIVE_CITED_FINAL"
        return CaseDecision(fp, "live", bucket, status, why.startswith("QUALIFIED"),
                            why, dur)
    if bucket == "safe_abstention":
        ok = (status == "SAFE_ABSTENTION" and grade.get("pass") is True
              and entry.get("client_complete") is True
              and is_sha(entry.get("client_ack_sha256")))
        return CaseDecision(fp, "live", bucket, status, ok,
                            "SAFE_ABSTENTION_VERIFIED" if ok else
                            "SAFE_ABSTENTION_NOT_INDEPENDENTLY_VALID", dur)
    if bucket == "rejected_before_provider":
        ok = (status == "REJECTED_BEFORE_PROVIDER"
              and grade.get("pass") is True
              and entry.get("provider_dispatch_count") == 0
              and type(entry.get("provider_dispatch_count")) is int
              and entry.get("provider_telemetry_proven") is True
              and is_sha(entry.get("authority_trace_sha256")))
        return CaseDecision(fp, "live", bucket, status, ok,
                            "PREPROVIDER_ZERO_DISPATCH_VERIFIED" if ok else
                            "PROVIDER_DISPATCH_NOT_INDEPENDENTLY_ZERO", dur)
    ok = status == "REPLAY_PASS" and grade.get("pass") is True
    return CaseDecision(fp, "replay", bucket, status, ok,
                        "REPLAY_CONTRACT_VERIFIED" if ok else
                        "REPLAY_CONTROL_FAILED", None)


def _p95(values: list[float], n: int) -> float | None:
    if len(values) != n:
        return None
    return sorted(values)[math.ceil(n * 0.95) - 1]


def evaluate(
    manifest: dict[str, Any], roster: dict[str, Any],
    outcomes: dict[str, Any], registry: dict[str, Any], pinned_root_sha: str,
    *, now: datetime | None = None,
) -> dict[str, Any]:
    """Produce immutable-compatible metadata only; never certify release."""
    now = now or datetime.now(UTC)
    roots = trusted_roots(registry, pinned_root_sha)
    assignments = freeze_roster(roster)
    binding = approved_manifest(manifest, roots, roster, outcomes, now)
    required(outcomes.get("schema") == OUTCOMES_VERSION, "OUTCOME_SCHEMA_INVALID")
    data = signed_payload(outcomes.get("signed"), role="observer", roots=roots)
    required(set(outcomes) == {"schema", "signed"}, "OUTCOMES_FIELDS_INVALID")
    required(set(data) == {
        "run_id", "candidate_image_sha256", "roster_sha256", "receipts",
    }, "OUTCOME_ENVELOPE_HIDDEN_FIELDS")
    required(data.get("run_id") == binding["official_run_id"]
             and data.get("candidate_image_sha256") == binding["image_sha256"]
             and data.get("roster_sha256") == sha(roster), "HISTORICAL_OR_STALE_OUTCOME")
    entries = data.get("receipts")
    required(isinstance(entries, list), "OUTCOMES_NOT_LIST")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        required(isinstance(entry, dict), "OUTCOME_ENTRY_NOT_OBJECT")
        cid = entry.get("case_id")
        required(is_ident(cid), "OUTCOME_CASE_ID_INVALID")
        required(cid not in indexed, "DUPLICATE_OUTCOME_ID")
        indexed[cid] = entry
    expected = {a.case_id for a in assignments}
    required(not (indexed.keys() - expected), "UNKNOWN_OR_HIDDEN_CASE_ID")
    decisions: list[CaseDecision] = []
    for case in assignments:
        if case.case_id not in indexed:
            fp = sha({"case": case.case_id})[:20]
            decisions.append(CaseDecision(fp, case.mode, case.expectation,
                                          "MISSING", False,
                                          "MISSING_SIGNED_CURRENT_OUTCOME", None))
            continue
        decisions.append(_case_score(case, indexed[case.case_id], roots, binding))
    scores = Counter((x.mode, x.expectation) for x in decisions if x.qualified)
    cited = scores[("live", "verified_cited_answer")]
    safe = scores[("live", "safe_abstention")]
    rejected = scores[("live", "rejected_before_provider")]
    replay = sum(scores[b] for b in BUCKETS if b[0] == "replay")
    all_live = [d.duration_ms for d in decisions if d.mode == "live"
                and d.duration_ms is not None]
    all_answerable = [d.duration_ms for d in decisions
                      if d.expectation == "verified_cited_answer"
                      and d.duration_ms is not None]
    p95_live = _p95(all_live, 341)
    p95_cited = _p95(all_answerable, 237)
    all_tiers = {root["tier"] for root in roots.values()}
    synthetic = all_tiers == {"SYNTHETIC_FIXTURE"}
    complete = len(entries) == 523
    gates = {
        "cited_at_least_226_of_237": cited >= 226,
        "safe_abstention_52_of_52": safe == 52,
        "preprovider_zero_dispatch_52_of_52": rejected == 52,
        "replay_182_of_182": replay == 182,
        "p95_live341_at_most_15000ms": (p95_live is not None
                                         and p95_live <= 15000),
        "p95_cited237_at_most_15000ms": (p95_cited is not None
                                          and p95_cited <= 15000),
        "exactly_523_current_outcomes": complete,
    }
    all_met = all(gates.values())
    status = ("SYNTHETIC_CALIBRATION_ONLY" if synthetic else
              "SIGNED_EVIDENCE_ELIGIBLE_FOR_INDEPENDENT_ACCEPTANCE"
              if all_met else "SIGNED_EVIDENCE_GATES_NOT_MET")
    return {
        "schema": "m27.w5.e24.redacted_result.v1",
        "status": status,
        "official_523_run_certified": False,
        "w5_full_complete": False,
        "w6_authorized": False,
        "rel01_certified": False,
        "rel02_authorized": False,
        "production_authorized": False,
        "candidate_current_claim_only": True,
        "historical_stage30o_as_current_score": False,
        "synthetic": synthetic,
        "counts": {
            "assigned": 523, "live": 341, "replay": 182,
            "cited_qualified": cited, "cited_denominator": 237,
            "safe_qualified": safe, "safe_denominator": 52,
            "preprovider_qualified": rejected, "preprovider_denominator": 52,
            "replay_qualified": replay, "replay_denominator": 182,
            "outcomes_supplied": len(entries),
        },
        "p95_ms": {"live341": p95_live, "cited237": p95_cited},
        "gates": gates,
        "all_draft_gates_met": all_met,
        "reasons_by_case": [d.__dict__ if hasattr(d, "__dict__") else {
            "fingerprint": d.fingerprint, "mode": d.mode,
            "expectation": d.expectation, "status": d.status,
            "qualified": d.qualified, "reason": d.reason,
            "duration_ms": d.duration_ms,
        } for d in decisions],
        "input_sha256": {
            "manifest": sha(manifest), "roster": sha(roster),
            "outcomes": sha(outcomes), "trusted_registry": sha(registry),
        },
    }


def write_result(path: str, result: dict[str, Any]) -> str:
    """No overwrite of previous run; create restrictive regular-file output."""
    data = canonical(result) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--roster", required=True)
    ap.add_argument("--outcomes", required=True)
    ap.add_argument("--trusted-registry", required=True)
    ap.add_argument("--trusted-registry-sha256", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    try:
        docs = [read_json(p) for p in (
            args.manifest, args.roster, args.outcomes, args.trusted_registry
        )]
        result = evaluate(*docs, args.trusted_registry_sha256)
        # Even a perfectly passing synthetic fixture is never an official PASS.
        code = (22 if result["synthetic"] else
                0 if result["all_draft_gates_met"] else 20)
    except (Denied, OSError, TypeError, KeyError, ValueError) as exc:
        why = exc.reason if isinstance(exc, Denied) else "INVALID_INPUT_OR_FILE"
        result = {
            "schema": "m27.w5.e24.redacted_result.v1",
            "status": "OFFICIAL_523_NOT_RUN_EVALUATOR_RIGHTS_NOT_ESTABLISHED",
            "admission_denied_reason": why, "official_523_run_certified": False,
            "w5_full_complete": False, "w6_authorized": False,
            "rel01_certified": False, "rel02_authorized": False,
            "production_authorized": False,
        }
        code = 20
    try:
        digest = write_result(args.output, result)
        print(json.dumps({"status": result["status"],
                          "output_sha256": digest, "exit_code": code},
                         sort_keys=True))
    except OSError:
        print("E24_OUTPUT_WRITE_DENIED", file=sys.stderr)
        return 21
    return code


if __name__ == "__main__":
    raise SystemExit(main())
