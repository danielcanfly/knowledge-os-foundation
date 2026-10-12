"""B24 sealed Phase B200 *metadata* admission: no holdout reading or execution.

Trust anchors MUST be independently enrolled out of band. A developer-supplied
test key or a valid signature alone never establishes a lawful external grant.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

PHASE = "NEW_UNSEEN_PHASE_B200"
NOT_ADMITTED = "NOT_ADMITTED"
NOT_EXECUTED = "PHASE_B200_EVALUATION_NOT_EXECUTED"
ROLES = ("custodian", "rights_issuer", "builder", "runner", "client", "rubric")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,95}$")
OUTCOMES = frozenset(("ANSWER", "ABSTAIN", "ERROR", "TIMEOUT", "DENIED"))
CASE_FIELDS = frozenset(("id", "outcome", "grade", "critical", "source_revision",
                         "source_id", "citation_start", "citation_end", "span_verified"))
MAX_JSON_BYTES = 2_000_000
# Explicit allowlists prevent case bodies, model outputs and grading keys being
# smuggled into the evaluator-side metadata protocol.
ADMISSION_FIELDS = {
    "custodian": {"actor_id", "evaluation_id", "population", "historical_m26_reuse",
                  "case_ids", "case_count", "roster_sha256", "sealed_corpus_sha256",
                  "history_exclusion_sha256", "source_revision_index_sha256",
                  "history_overlap_count", "previously_exposed",
                  "sealed_by_independent_custodian", "developer_has_case_access",
                  "answer_keys_exposed", "sealed_at_ms", "rubric_sha256",
                  "rights_grant_sha256"},
    "rights_issuer": {"actor_id", "evaluation_id", "scope", "lawful_controller",
                      "can_use_unseen_corpus", "valid_until_ms",
                      "source_revision_index_sha256", "cohort_roster_sha256",
                      "allowed_image_sha256"},
    "builder": {"actor_id", "evaluation_id", "image_sha256", "runner_sha256",
                "client_auth_sha256", "signed_oci_digest", "signed_image",
                "candidate_lock_at_ms"},
    "runner": {"actor_id", "evaluation_id", "runner_sha256", "sealed_execution",
               "one_shot", "developer_can_read_cases", "can_read_answer_keys",
               "authorized_until_ms", "nonce", "intent"},
    "client": {"actor_id", "evaluation_id", "client_auth_sha256", "native_client_ack",
               "ack_digest", "authorized_until_ms", "nonce", "intent"},
    "rubric": {"actor_id", "evaluation_id", "rubric_sha256", "frozen_at_ms",
               "approved_independent_grader", "grade_only_output",
               "zero_critical_errors", "passing_grade", "authorized_until_ms"},
}
RUN_RESULT_FIELDS = {"evaluation_id", "nonce", "roster_sha256", "image_sha256",
                     "attempt_ids", "terminal_ids"}
GRADE_RESULT_FIELDS = {"evaluation_id", "nonce", "roster_sha256", "runner_digest",
                       "results"}
SOURCE_RESULT_FIELDS = {"evaluation_id", "nonce", "roster_sha256", "grade_digest",
                        "source_span_audit", "critical_error_audit",
                        "signed_grading_keys_kept_private"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _ident(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENT.fullmatch(value))


def _integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _same_fields(value: Any, fields: set[str]) -> bool:
    return type(value) is dict and set(value) == fields


def _deny(reason: str) -> dict[str, Any]:
    return {"admission": NOT_ADMITTED, "reason": reason,
            "evaluation": NOT_EXECUTED, "official_score": None,
            "w5_full_complete": False, "production_authorized": False}


def _signed_bytes(role: str, payload: dict[str, Any]) -> bytes:
    return b"M27-B24-v1\x00" + role.encode() + b"\x00" + json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def verify_envelope(envelope: Any, role: str, roots: Any) -> tuple[bool, str]:
    """Cryptographic check only; real root enrollment is separately controlled."""
    if not _same_fields(envelope, {"role", "key_id", "payload", "signature"}):
        return False, "ENVELOPE_SCHEMA"
    if envelope["role"] != role or not _ident(envelope["key_id"]):
        return False, "ROLE_OR_KEY"
    if not isinstance(envelope["payload"], dict):
        return False, "PAYLOAD_SCHEMA"
    if not _same_fields(roots, set(ROLES)) or not isinstance(roots.get(role), dict):
        return False, "TRUST_ROOTS_MISSING"
    key = roots[role].get(envelope["key_id"])
    if not isinstance(key, str):
        return False, "UNTRUSTED_SIGNER"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public = base64.b64decode(key, validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
        if len(public) != 32 or len(signature) != 64:
            return False, "INVALID_SIGNING_MATERIAL"
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, _signed_bytes(role, envelope["payload"])
        )
    except (ImportError, ValueError, TypeError, KeyError):
        return False, "SIGNATURE_INVALID"
    except Exception as error:
        # InvalidSignature derives from Exception; never include raw input/errors.
        if type(error).__name__ == "InvalidSignature":
            return False, "SIGNATURE_INVALID"
        return False, "SIGNATURE_UNVERIFIED"
    return True, "CRYPTO_VALID"


def _check_no_developer_roles(envelopes: dict[str, Any]) -> bool:
    """All six roles must be independently key-isolated, not one owner signing all."""
    ids = [(envelopes[r]["key_id"], str(envelopes[r]["payload"].get("actor_id", "")))
           for r in ROLES]
    return len(set(ids)) == len(ROLES) and len({x[0] for x in ids}) == len(ROLES) \
        and len({x[1] for x in ids}) == len(ROLES) \
        and all(_ident(x[1]) and "developer" not in x[1].lower() for x in ids)


def admit(manifests: Any, trusted_roots: Any, *, now_ms: int | None = None,
          pinned_root_sha256: str | None = None) -> dict[str, Any]:
    """Validate sealed metadata only, without opening cases or grader answer keys.

    pinned_root_sha256 MUST be authenticated from an independent external channel.
    This function cannot make an arbitrary caller-supplied trust root independent.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    if not _integer(now_ms, 1):
        return _deny("CLOCK_INVALID")
    if not _sha(pinned_root_sha256) or digest(trusted_roots) != pinned_root_sha256:
        return _deny("TRUST_ANCHOR_NOT_PINNED")
    if not _same_fields(manifests, set(ROLES)):
        return _deny("REQUIRED_SIGNED_MANIFEST_MISSING")
    for role in ROLES:
        valid, reason = verify_envelope(manifests[role], role, trusted_roots)
        if not valid:
            return _deny(role.upper() + "_" + reason)
    if not _check_no_developer_roles(manifests):
        return _deny("SIGNER_INDEPENDENCE_UNVERIFIED")
    p = {r: manifests[r]["payload"] for r in ROLES}
    if any(not _same_fields(p[r], ADMISSION_FIELDS[r]) for r in ROLES):
        return _deny("MANIFEST_SCHEMA_VIOLATION")
    evaluation = p["custodian"].get("evaluation_id")
    if not _ident(evaluation) or any(x.get("evaluation_id") != evaluation for x in p.values()):
        return _deny("EVALUATION_ID_MISMATCH")
    c, rights, build, runner, client, rubric = (p[x] for x in ROLES)
    if c.get("population") != PHASE or c.get("historical_m26_reuse") is not False:
        return _deny("NOT_NEW_UNSEEN_HOLDOUT")
    ids = c.get("case_ids")
    if (type(ids) is not list or len(ids) != 200
            or any(not _ident(x) for x in ids) or len(set(ids)) != 200):
        return _deny("EXACT_200_DISTINCT_IDS_REQUIRED")
    if (c.get("case_count") != 200 or not _integer(c.get("case_count"))
            or c.get("roster_sha256") != digest(ids)):
        return _deny("ROSTER_COMMITMENT_INVALID")
    if not all(_sha(c.get(k)) for k in ("sealed_corpus_sha256", "history_exclusion_sha256",
                                         "source_revision_index_sha256")):
        return _deny("SEALED_COMMITMENTS_MISSING")
    if (not _integer(c.get("history_overlap_count"))
            or c["history_overlap_count"] != 0 or c.get("previously_exposed") is not False):
        return _deny("HISTORICAL_CONTAMINATION")
    if c.get("sealed_by_independent_custodian") is not True:
        return _deny("CUSTODIAN_NOT_INDEPENDENT")
    if c.get("developer_has_case_access") is not False or c.get("answer_keys_exposed") is not False:
        return _deny("SEALED_CASE_ACCESS_VIOLATION")
    prelock = c.get("sealed_at_ms")
    locked = build.get("candidate_lock_at_ms")
    if not (_integer(prelock, 1) and _integer(locked, 1) and prelock < locked <= now_ms):
        return _deny("COMMITMENT_NOT_BEFORE_CANDIDATE_LOCK")
    if (c.get("rubric_sha256") != rubric.get("rubric_sha256")
            or c.get("rights_grant_sha256") != digest(rights)
            or not _integer(rubric.get("frozen_at_ms"), 1)
            or rubric["frozen_at_ms"] >= locked):
        return _deny("PRECOMMITTED_RUBRIC_OR_RIGHTS_MISMATCH")
    if (rights.get("scope") != PHASE or rights.get("lawful_controller") is not True
            or rights.get("can_use_unseen_corpus") is not True
            or not _integer(rights.get("valid_until_ms"), 1)
            or rights["valid_until_ms"] <= now_ms):
        return _deny("RIGHTS_EXPIRED_OR_NOT_GRANTED")
    if (rights.get("source_revision_index_sha256") != c["source_revision_index_sha256"]
            or rights.get("cohort_roster_sha256") != c["roster_sha256"]):
        return _deny("SOURCE_RIGHTS_SCOPE_MISMATCH")
    for field in ("image_sha256", "runner_sha256", "client_auth_sha256"):
        if not _sha(build.get(field)):
            return _deny("CANDIDATE_PROVENANCE_MISSING")
    if (not _sha(build.get("signed_oci_digest")) or build.get("signed_image") is not True
            or rights.get("allowed_image_sha256") != build["image_sha256"]):
        return _deny("IMMUTABLE_IMAGE_NOT_AUTHORIZED")
    if (runner.get("runner_sha256") != build["runner_sha256"]
            or runner.get("sealed_execution") is not True
            or runner.get("one_shot") is not True
            or runner.get("developer_can_read_cases") is not False
            or runner.get("can_read_answer_keys") is not False
            or not _integer(runner.get("authorized_until_ms"), 1)
            or runner["authorized_until_ms"] <= now_ms):
        return _deny("INDEPENDENT_RUNNER_NOT_AUTHORIZED")
    if (client.get("client_auth_sha256") != build["client_auth_sha256"]
            or client.get("native_client_ack") is not True
            or not _sha(client.get("ack_digest"))
            or not _integer(client.get("authorized_until_ms"), 1)
            or client["authorized_until_ms"] <= now_ms):
        return _deny("AUTHENTICATED_CLIENT_ACK_MISSING")
    if (rubric.get("approved_independent_grader") is not True
            or rubric.get("grade_only_output") is not True
            or rubric.get("zero_critical_errors") is not True
            or not _sha(rubric.get("rubric_sha256"))
            or not _integer(rubric.get("passing_grade"), 0)
            or rubric["passing_grade"] > 100
            or not _integer(rubric.get("authorized_until_ms"), 1)
            or rubric["authorized_until_ms"] <= now_ms):
        return _deny("INDEPENDENT_GRADING_CONTRACT_MISSING")
    if (not _ident(runner.get("nonce")) or runner.get("nonce") != client.get("nonce")
            or runner.get("intent") != "RUN_ONCE_BLINDED"
            or client.get("intent") != "RUN_ONCE_BLINDED"):
        return _deny("ONE_SHOT_INTENT_INVALID")
    # Identity validation is local cryptography + metadata, not a verified external run.
    return {"admission": "EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY",
            "reason": "SIGNED_METADATA_VERIFIED_EXTERNAL_TRUST_IS_OUT_OF_BAND",
            "evaluation": NOT_EXECUTED, "official_score": None,
            "evaluation_id": evaluation, "case_count": 200,
            "nonce": runner["nonce"], "roster_sha256": c["roster_sha256"],
            "candidate_image_sha256": build["image_sha256"],
            "w5_full_complete": False, "production_authorized": False}


def reserve_one_shot(metadata: dict[str, Any], state_dir: str | Path) -> bool:
    """Atomic irreversible intent reservation. Must run on custodian-controlled host.

    Only metadata in the ready state is accepted. This does not invoke a provider,
    open any sealed case, grade data, or certify independent authority.
    """
    if metadata.get("admission") != "EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY":
        return False
    evaluation, nonce = metadata.get("evaluation_id"), metadata.get("nonce")
    if not _ident(evaluation) or not _ident(nonce):
        return False
    base = Path(state_dir)
    if not base.is_dir() or base.is_symlink():
        return False
    marker = hashlib.sha256((evaluation + "\x00" + nonce).encode()).hexdigest()
    try:
        os.mkdir(base / ("claimed-" + marker), mode=0o700)
    except (OSError, ValueError):
        return False
    return True


def verify_grade_only(manifests: Any, roots: Any, grade_envelope: Any,
                      runner_envelope: Any, source_envelope: Any,
                      *, now_ms: int | None = None,
                      pinned_root_sha256: str | None = None) -> dict[str, Any]:
    """Audit full 200 attempted/terminal/graded cases and signatures, never score hidden data."""
    admitted = admit(manifests, roots, now_ms=now_ms,
                     pinned_root_sha256=pinned_root_sha256)
    if admitted["admission"] != "EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY":
        return admitted
    for role, env in (("rubric", grade_envelope), ("runner", runner_envelope),
                      ("custodian", source_envelope)):
        verified, reason = verify_envelope(env, role, roots)
        if not verified:
            return _deny("RESULT_" + role.upper() + "_" + reason)
    grade = grade_envelope["payload"]
    run = runner_envelope["payload"]
    proof = source_envelope["payload"]
    if (not _same_fields(run, RUN_RESULT_FIELDS)
            or not _same_fields(grade, GRADE_RESULT_FIELDS)
            or not _same_fields(proof, SOURCE_RESULT_FIELDS)):
        return _deny("GRADE_ONLY_RESULT_SCHEMA")
    cids = manifests["custodian"]["payload"]["case_ids"]
    if (grade.get("evaluation_id") != admitted["evaluation_id"]
            or run.get("evaluation_id") != admitted["evaluation_id"]
            or proof.get("evaluation_id") != admitted["evaluation_id"]
            or any(x.get("nonce") != admitted["nonce"] for x in (grade, run, proof))):
        return _deny("RESULT_RUN_OR_NONCE_MISMATCH")
    if (run.get("roster_sha256") != admitted["roster_sha256"]
            or grade.get("roster_sha256") != admitted["roster_sha256"]
            or proof.get("roster_sha256") != admitted["roster_sha256"]):
        return _deny("POSTFREEZE_ROSTER_SWAP")
    if (run.get("image_sha256") != admitted["candidate_image_sha256"]
            or grade.get("runner_digest") != digest(run)
            or proof.get("grade_digest") != digest(grade)):
        return _deny("RESULT_CHAIN_DIGEST_MISMATCH")
    attempts, terminals, graded = (run.get("attempt_ids"), run.get("terminal_ids"),
                                   grade.get("results"))
    if (type(attempts) is not list or type(terminals) is not list
            or len(attempts) != 200 or len(terminals) != 200
            or len(set(attempts)) != 200 or len(set(terminals)) != 200
            or set(attempts) != set(cids) or set(terminals) != set(cids)
            or type(graded) is not list or len(graded) != 200):
        return _deny("ALL_200_ATTEMPTED_AND_TERMINAL_REQUIRED")
    if (len({x.get("id") for x in graded if isinstance(x, dict)}) != 200
            or {x.get("id") for x in graded if isinstance(x, dict)} != set(cids)):
        return _deny("ALL_200_GRADED_REQUIRED")
    if (proof.get("source_span_audit") is not True
            or proof.get("critical_error_audit") is not True
            or proof.get("signed_grading_keys_kept_private") is not True):
        return _deny("SOURCE_SPAN_INDEPENDENT_AUDIT_MISSING")
    passing = 0
    failures = 0
    for r in graded:
        if not isinstance(r, dict) or set(r) != CASE_FIELDS:
            return _deny("GRADE_ONLY_SCHEMA_VIOLATION")
        if (r["outcome"] not in OUTCOMES or not _integer(r["grade"])
                or r["grade"] > 100 or type(r["critical"]) is not bool
                or type(r["span_verified"]) is not bool):
            return _deny("GRADE_VALUE_INVALID")
        if not (_ident(r["source_revision"]) and _ident(r["source_id"])
                and _integer(r["citation_start"]) and _integer(r["citation_end"])
                and r["citation_end"] > r["citation_start"]):
            return _deny("SOURCE_SPAN_INVALID")
        if (r["outcome"] != "ANSWER" or r["critical"] or not r["span_verified"]):
            if r["grade"] != 0:
                return _deny("FAULT_MUST_SCORE_ZERO")
            failures += 1
        elif r["grade"] >= manifests["rubric"]["payload"]["passing_grade"]:
            passing += 1
        else:
            failures += 1
    return {"evaluation": "SIGNED_GRADE_ONLY_METADATA_AUDIT",
            "admission": "EXTERNAL_AUTHORITY_INDEPENDENT_ACCEPTANCE_PENDING",
            "attempted": 200, "terminal": 200, "graded": 200,
            "passing": passing, "failing": failures,
            "critical_errors": sum(bool(r["critical"]) for r in graded),
            "official_score": None, "certified": False,
            "w5_full_complete": False, "production_authorized": False}


def _read_limited(path: str) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("INPUT_DENIED")
    with p.open("rb") as handle:
        data = handle.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("INPUT_TOO_LARGE")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("INPUT_SCHEMA")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B24 metadata-only sealed admission")
    parser.add_argument("--manifest")
    parser.add_argument("--trust")
    parser.add_argument("--pinned-root-sha256")
    args = parser.parse_args(argv)
    try:
        if not args.manifest or not args.trust:
            result = _deny("SEALED_MANIFEST_OR_TRUST_ROOT_ABSENT")
        else:
            result = admit(_read_limited(args.manifest), _read_limited(args.trust),
                           pinned_root_sha256=args.pinned_root_sha256)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        result = _deny("INPUT_NOT_ADMITTED")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["admission"] == "EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY" else 20


if __name__ == "__main__":
    sys.exit(main())
