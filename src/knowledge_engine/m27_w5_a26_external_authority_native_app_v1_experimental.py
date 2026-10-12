"""A26 fail-closed externally provisioned evaluation authority and client custody.

Does not fetch cases, contact endpoints, issue signer authority or mark release PASS.
An arbitrary locally created signature is NOT independent authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import stat
from collections import Counter
from pathlib import Path
from typing import Any

from .m27_w5_c24_client_observation_v1_experimental import (
    CasePlan,
    SourcePin,
    canonical,
    nearest_rank,
    verify_ed25519,
)
from .m27_w5_n25_native_client_trial_v1_experimental import AppAttachment, NativeTrial

SCHEMA = "m27.w5.a26.signed_evaluation_authority.v1"
NOT_PROVISIONED = "A26_AUTHORITY_NOT_PROVISIONED"
ROLES = frozenset({
    "source_rights", "app_controller", "evaluation_controller", "grader",
    "native_observer", "candidate_builder", "budget_controller",
})
ROLE_COUNTS = {
    "current523": {
        "live_cited": 237, "live_safe_abstain": 52,
        "live_preprovider_deny": 52, "replay_budget": 26,
        "replay_invariant": 26, "replay_governance": 130,
    },
    "phaseb200": {"blind": 200},
}
SAFE_IDS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
HEX = frozenset("0123456789abcdef")


class AuthorityDenied(ValueError):
    """Machine-readable refusal; never contains source text or signer secrets."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha256(canonical(value))


def pinned(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in HEX for c in value)


def ident(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 128 and all(c in SAFE_IDS for c in value)


def deny(condition: bool, reason: str) -> None:
    if not condition:
        raise AuthorityDenied(reason)


def loads_strict(data: bytes) -> Any:
    """Reject key overwrites, NaN, duplicates and lenient JSON parsing."""
    deny(len(data) <= 2_000_000, "JSON_TOO_LARGE")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in items:
            deny(k not in result, "DUPLICATE_JSON_KEY")
            result[k] = v
        return result

    def nonfinite(_: str) -> None:
        raise AuthorityDenied("NONFINITE_JSON_NUMBER")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite)


def _verify_roots(registry: dict, expected_sha: str, now: int) -> dict[str, dict]:
    deny(pinned(expected_sha) and digest(registry) == expected_sha,
         "REGISTRY_OUT_OF_BAND_PIN_MISSING_OR_MISMATCH")
    deny(registry.get("schema") == "m27.w5.external_trust_roots.v1",
         "ROOTS_SCHEMA_INVALID")
    deny(registry.get("independent_issuer") is True,
         "INDEPENDENT_REGISTRAR_REQUIRED")
    roots = registry.get("roots")
    deny(isinstance(roots, list) and bool(roots), "ROOTS_MISSING")
    result: dict[str, dict] = {}
    for item in roots:
        deny(isinstance(item, dict), "ROOT_SHAPE")
        key_id = item.get("key_id")
        deny(ident(key_id) and key_id not in result, "ROOT_ID_DUPLICATE_OR_INVALID")
        deny(item.get("revoked") is False and type(item.get("not_before")) is int
             and type(item.get("expires_at")) is int
             and item["not_before"] <= now < item["expires_at"], "ROOT_REVOKED_OR_EXPIRED")
        deny(isinstance(item.get("public_key_b64"), str), "ROOT_PUBLIC_KEY_MISSING")
        try:
            raw = base64.b64decode(item["public_key_b64"], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise AuthorityDenied("ROOT_PUBLIC_KEY_INVALID") from exc
        deny(len(raw) == 32 and isinstance(item.get("roles"), list)
             and len(item["roles"]) == 1 and ident(item["roles"][0]), "ROOT_ROLE_OR_KEY_INVALID")
        result[key_id] = item
    return result


def _check_assignments(purpose: str, assignments: Any, payload: dict) -> None:
    expected = ROLE_COUNTS[purpose]
    deny(isinstance(assignments, list) and len(assignments) == sum(expected.values()),
         "ASSIGNMENT_DENOMINATOR_INVALID")
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    for row in assignments:
        deny(isinstance(row, dict) and set(row) == {"case_id", "role"}, "ASSIGNMENT_SHAPE")
        case_id, role = row["case_id"], row["role"]
        deny(ident(case_id) and case_id not in ids and role in expected,
             "ASSIGNMENT_DUPLICATE_OR_ROLE")
        ids.add(case_id)
        counts[role] += 1
    deny(dict(counts) == expected and payload.get("role_counts") == expected,
         "ASSIGNMENT_ROLE_COUNTS_INVALID")
    deny(payload.get("assignment_roster_sha256") == digest(assignments),
         "ASSIGNMENT_ROSTER_PIN_MISMATCH")


def _check_payload(payload: dict, now: int) -> None:
    deny(payload.get("schema") == SCHEMA, "AUTHORITY_SCHEMA_INVALID")
    purpose = payload.get("purpose")
    deny(purpose in ROLE_COUNTS, "PURPOSE_NOT_APPROVED")
    for field in ("run_id", "nonce", "app_id", "endpoint_id"):
        deny(ident(payload.get(field)), "UNSAFE_ID:" + field)
    deny(type(payload.get("issued_at")) is int and type(payload.get("expires_at")) is int
         and payload["issued_at"] <= now < payload["expires_at"],
         "AUTHORITY_EXPIRED_OR_NOT_YET_VALID")
    deny(payload.get("revoked") is False
         and type(payload.get("revocation_checked_at")) is int
         and payload["issued_at"] <= payload["revocation_checked_at"] <= now
         and now - payload["revocation_checked_at"] <= 3600,
         "REVOCATION_STALE_OR_REVOKED")
    for field in (
        "candidate_image_sha256", "runner_sha256", "app_build_sha256",
        "client_instrumentation_sha256", "source_roster_sha256",
        "source_revision_index_sha256", "source_rights_grant_sha256",
        "assignment_roster_sha256", "rubric_sha256",
    ):
        deny(pinned(payload.get(field)), "IMMUTABLE_PIN_MISSING:" + field)
    rights = payload.get("rights")
    deny(isinstance(rights, dict) and rights.get("consent") is True
         and rights.get("revoked") is False
         and rights.get("permission_scope") == "nonprod_evaluation"
         and type(rights.get("retention_expires_at")) is int
         and rights["retention_expires_at"] > now
         and rights.get("source_revision_index_sha256")
         == payload["source_revision_index_sha256"],
         "SOURCE_RIGHTS_SCOPE_OR_VERSION_MISSING")
    budget = payload.get("budget")
    deny(isinstance(budget, dict) and type(budget.get("max_cost_cents")) is int
         and 0 < budget["max_cost_cents"] <= 1_000_000
         and type(budget.get("max_attempts")) is int
         and budget["max_attempts"] == sum(ROLE_COUNTS[purpose].values())
         and budget.get("provider_price_attestation_sha256")
         and pinned(budget["provider_price_attestation_sha256"]),
         "REAL_APPROVED_BUDGET_OR_PRICE_MISSING")
    deny(payload.get("nonproduction") is True and payload.get("one_shot") is True,
         "NONPROD_ONESHOT_REQUIRED")
    deny(payload.get("unseen_independent") is True if purpose == "phaseb200" else True,
         "BLIND_NONOVERLAP_ATTESTATION_MISSING")
    _check_assignments(purpose, payload.get("assignments"), payload)


def verify_signed_authority(
    packet: dict | None, registry: dict | None, *,
    registry_sha256_from_independent_channel: str | None,
    packet_sha256_from_independent_channel: str | None,
    now: int,
) -> dict:
    """Cryptographic preflight ONLY, never an authority-issuing mechanism.

    The caller must authenticate real out-of-band pins and legal signers.
    """
    result = {
        "schema": "m27.w5.a26.preflight.v1",
        "status": NOT_PROVISIONED, "mechanical_signatures_verified": False,
        "independent_real_world_authority_admitted": False,
        "external_call_permitted": False, "official_e26_pass": False,
        "official_b26_pass": False, "w5_full_complete": False,
    }
    try:
        deny(type(now) is int and now > 0, "UNTRUSTED_TIME")
        deny(isinstance(packet, dict) and isinstance(registry, dict),
             "EXTERNAL_SIGNED_ARTIFACTS_ABSENT")
        deny(pinned(packet_sha256_from_independent_channel)
             and digest(packet) == packet_sha256_from_independent_channel,
             "PACKET_EXTERNAL_PIN_MISSING_OR_MISMATCH")
        roots = _verify_roots(registry, registry_sha256_from_independent_channel or "", now)
        payload = packet.get("payload")
        deny(isinstance(payload, dict), "SIGNED_PAYLOAD_ABSENT")
        _check_payload(payload, now)
        signatures = packet.get("signatures")
        required = set(ROLES)
        if payload["purpose"] == "phaseb200":
            required.add("blind_custodian")
        deny(isinstance(signatures, list) and len(signatures) == len(required),
             "INDEPENDENT_ROLES_MISSING")
        used_roles: set[str] = set()
        used_keys: set[str] = set()
        for sig in signatures:
            deny(isinstance(sig, dict), "SIGNATURE_SHAPE")
            role, key_id = sig.get("role"), sig.get("key_id")
            deny(role in required and role not in used_roles
                 and key_id in roots and key_id not in used_keys,
                 "ROLE_SEPARATION_OR_REPLAY")
            root = roots[key_id]
            deny(root["roles"] == [role], "SIGNER_NOT_ENTITLED_FOR_ROLE")
            deny(isinstance(sig.get("signature_b64"), str)
                 and verify_ed25519(payload, sig["signature_b64"], root["public_key_b64"]),
                 "INVALID_INDEPENDENT_SIGNATURE")
            used_roles.add(role)
            used_keys.add(key_id)
        deny(used_roles == required, "ROLE_COVERAGE_INCOMPLETE")
        result["status"] = "A26_MECHANICAL_SIGNATURE_PREFLIGHT_ONLY"
        result["mechanical_signatures_verified"] = True
        result["run_id"] = payload["run_id"]
        result["purpose"] = payload["purpose"]
        result["nonce_sha256"] = sha256(payload["nonce"].encode())
    except (AuthorityDenied, KeyError, TypeError, ValueError, OverflowError) as exc:
        result["reason"] = str(exc)[:110]
    return result


def claim_nonce(private_dir: Path, run_id: str, nonce: str) -> str:
    """One-use durable local claim; only after separate genuine host authorization."""
    deny(ident(run_id) and ident(nonce), "CLAIM_ID_INVALID")
    root = private_dir.lstat()
    deny(stat.S_ISDIR(root.st_mode) and not (root.st_mode & 0o077)
         and not private_dir.is_symlink(), "PRIVATE_CLAIM_DIRECTORY_REQUIRED")
    name = "a26_nonce_" + sha256((run_id + ":" + nonce).encode())
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(private_dir / name, flags, 0o600)
    except FileExistsError as exc:
        raise AuthorityDenied("REPLAY_NONCE_CONSUMED") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(b"A26 NONCE CLAIMED\n")
        stream.flush()
        os.fsync(stream.fileno())
    dirfd = os.open(private_dir, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    return sha256(name.encode())


def observe_client_chunks(
    case: CasePlan, sources: list[SourcePin], attachment: AppAttachment,
    chunks: Any, *, clock_ns: Any, close_reason: str = "disconnect",
    source_current: Any = None,
) -> dict:
    """Embed in real app recv loop; never opens a network connection.

    Never elevate official qualification even when supplied with synthetic=False.
    """
    trial = NativeTrial(case, sources, attachment, clock_ns=clock_ns,
                        source_current=source_current)
    trial.before_send()
    try:
        for part in chunks:
            trial.on_recv(part)
            if trial.capture.status in ("COMPLETE", "ERROR"):
                break
    except (OSError, ValueError, TypeError) as exc:
        trial.transport_fault = "RECV_FAILURE:" + type(exc).__name__
        receipt = trial.close("rejected")
    else:
        receipt = trial.close(close_reason)
    return {
        "a26_schema": "m27.w5.a26.client_observation.v1",
        "case_id": case.case_id,
        "client_receipt_sha256": digest(receipt),
        "client_receipt": receipt,
        "independent_client_ack": None,
        "official_qualified": False,
    }


def cohort_integrity(assignments: list[dict], receipts: list[dict], purpose: str) -> dict:
    """Do not drop denied, timeout, disconnect, duplicate or missing rows."""
    result = {
        "purpose": purpose, "status": "A26_INCOMPLETE_CLIENT_CUSTODY",
        "all_outcome_p95_ms": None, "cited_expected_p95_ms": None,
        "independent_client_ack_verified": False, "official_qualified": False,
    }
    try:
        deny(purpose in ROLE_COUNTS, "PURPOSE_INVALID")
        plan = {"role_counts": ROLE_COUNTS[purpose],
                "assignment_roster_sha256": digest(assignments)}
        _check_assignments(purpose, assignments, plan)
        deny(isinstance(receipts, list) and len(receipts) == len(assignments),
             "ALL_OUTCOME_DENOMINATOR_MISSING")
        by_id: dict[str, dict] = {}
        expected_ids = {a["case_id"] for a in assignments}
        expected_roles = {a["case_id"]: a["role"] for a in assignments}
        for wrapped in receipts:
            deny(isinstance(wrapped, dict), "RECEIPT_SHAPE")
            r = wrapped.get("client_receipt")
            deny(isinstance(r, dict), "NATIVE_RECEIPT_MISSING")
            cid = r.get("case_id")
            deny(cid in expected_ids and cid not in by_id, "UNASSIGNED_OR_DUPLICATE_RECEIPT")
            deny(wrapped.get("client_receipt_sha256") == digest(r),
                 "CLIENT_RECEIPT_TAMPERED")
            deny(r.get("n25_schema") == "m27.w5.n25.native_client_trial.v1"
                 and r.get("synthetic") is False, "REAL_NATIVE_RECEIPT_REQUIRED")
            latency = r.get("outcome_latency_ms")
            deny(type(latency) in (float, int) and math.isfinite(latency)
                 and latency >= 0, "UNKNOWN_OUTCOME_LATENCY")
            deny(type(r.get("request_admitted_ns")) is int
                 and type(r.get("client_closed_ns")) is int
                 and abs(latency - (r["client_closed_ns"]
                                    - r["request_admitted_ns"]) / 1e6) < 1e-6
                 or r.get("status") == "COMPLETE" and type(r.get("terminal_ns")) is int
                 and abs(latency - (r["terminal_ns"]
                                    - r["request_admitted_ns"]) / 1e6) < 1e-6,
                 "CLIENT_CLOCK_INCONSISTENT")
            if expected_roles[cid] == "live_cited":
                first, terminal = (
                    r.get("first_substantive_text_ns"), r.get("terminal_ns")
                )
                deny(r.get("status") == "COMPLETE"
                     and type(first) is int and type(terminal) is int
                     and r["request_admitted_ns"] <= first < terminal,
                     "CITED_FIRST_TEXT_MUST_PRECEDE_TERMINAL")
                citations = r.get("source_native_citations")
                deny(isinstance(citations, list) and bool(citations),
                     "SOURCE_NATIVE_CITATION_MISSING")
                for citation in citations:
                    deny(isinstance(citation, dict)
                         and pinned(citation.get("source_sha256"))
                         and pinned(citation.get("quote_sha256"))
                         and ident(citation.get("revision"))
                         and type(citation.get("source_start")) is int
                         and type(citation.get("source_end")) is int
                         and 0 <= citation["source_start"] < citation["source_end"],
                         "SOURCE_VERSION_OR_NATIVE_SPAN_INVALID")
            by_id[cid] = r
        deny(set(by_id) == expected_ids, "CLIENT_CASES_MISSING")
        if purpose == "current523":
            live = [by_id[a["case_id"]]["outcome_latency_ms"] for a in assignments
                    if a["role"].startswith("live_")]
            cited = [by_id[a["case_id"]]["outcome_latency_ms"] for a in assignments
                     if a["role"] == "live_cited"]
            _, result["all_outcome_p95_ms"] = nearest_rank(live)
            _, result["cited_expected_p95_ms"] = nearest_rank(cited)
            result["all_outcome_nearest_rank"] = 324
            result["cited_expected_nearest_rank"] = 226
        result["status"] = "A26_LOCAL_CLIENT_RECEIPTS_STRUCTURALLY_COMPLETE_ONLY"
    except (AuthorityDenied, KeyError, TypeError, ValueError) as exc:
        result["reason"] = str(exc)[:110]
    return result


def verify_independent_client_ack(
    wrapped: dict, ack_packet: dict | None, *,
    trusted_observer_public_b64: str | None,
    trusted_observer_public_sha256: str | None,
    expected_observer_key_id: str,
    now: int,
) -> dict:
    """Mechanically verify a separately signed ACK, without self-issuing authority.

    The expected observer key SHA must be obtained OUT OF BAND from the
    independent controller, not derived from an ACK furnished by the app.
    """
    result = {
        "status": "A26_CLIENT_ACK_NOT_PROVISIONED",
        "mechanical_ack_signature_verified": False,
        "independent_real_world_ack_admitted": False,
        "official_qualified": False,
    }
    try:
        deny(type(now) is int and ident(expected_observer_key_id), "ACK_TRUST_CONTEXT_MISSING")
        deny(isinstance(wrapped, dict) and isinstance(ack_packet, dict),
             "CLIENT_ACK_OR_RECEIPT_MISSING")
        receipt = wrapped.get("client_receipt")
        deny(isinstance(receipt, dict)
             and wrapped.get("client_receipt_sha256") == digest(receipt),
             "CLIENT_RECEIPT_DIGEST_MISMATCH")
        deny(isinstance(trusted_observer_public_b64, str)
             and pinned(trusted_observer_public_sha256), "EXTERNAL_OBSERVER_PIN_MISSING")
        try:
            pub = base64.b64decode(trusted_observer_public_b64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise AuthorityDenied("OBSERVER_PUBLIC_KEY_MALFORMED") from exc
        deny(len(pub) == 32 and sha256(pub) == trusted_observer_public_sha256,
             "OBSERVER_PUBLIC_KEY_PIN_MISMATCH")
        payload = ack_packet.get("payload")
        deny(isinstance(payload, dict), "ACK_PAYLOAD_MISSING")
        deny(payload.get("schema") == "m27.w5.a26.independent_client_ack.v1"
             and payload.get("observer_role") == "native_observer"
             and payload.get("observer_key_id") == expected_observer_key_id,
             "ACK_OBSERVER_IDENTITY_INVALID")
        for key in ("case_id", "request_id", "nonce", "status"):
            deny(payload.get(key) == receipt.get(key), "ACK_CASE_OR_OUTCOME_MISMATCH")
        deny(payload.get("client_receipt_sha256") == wrapped["client_receipt_sha256"]
             and payload.get("source_native_citations_sha256")
             == digest(receipt.get("source_native_citations")),
             "ACK_DIGEST_BINDING_MISSING")
        deny(payload.get("client_closed_ns") == receipt.get("client_closed_ns")
             and payload.get("terminal_ns") == receipt.get("terminal_ns"),
             "ACK_CLIENT_CLOCK_TAMPERED")
        deny(type(payload.get("issued_at")) is int
             and type(payload.get("expires_at")) is int
             and payload["issued_at"] <= now < payload["expires_at"]
             and payload.get("revoked") is False,
             "ACK_EXPIRED_OR_REVOKED")
        deny(isinstance(ack_packet.get("signature_b64"), str)
             and verify_ed25519(payload, ack_packet["signature_b64"],
                                trusted_observer_public_b64),
             "ACK_INDEPENDENT_SIGNATURE_INVALID")
        result["status"] = "A26_ACK_CRYPTO_VERIFIED_EXTERNAL_ADMISSION_REQUIRED"
        result["mechanical_ack_signature_verified"] = True
    except (AuthorityDenied, TypeError, KeyError, ValueError) as exc:
        result["reason"] = str(exc)[:110]
    return result


def _read_private_json(path: str) -> dict:
    """Read an already-provisioned private regular file without symlink traversal."""
    p = Path(path)
    parent = p.parent.lstat()
    deny(stat.S_ISDIR(parent.st_mode) and not (parent.st_mode & 0o077)
         and not p.parent.is_symlink(), "PRIVATE_SIGNED_INPUT_PARENT_REQUIRED")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags)
    try:
        meta = os.fstat(fd)
        deny(stat.S_ISREG(meta.st_mode) and not (meta.st_mode & 0o077)
             and meta.st_size <= 2_000_000, "PRIVATE_SIGNED_INPUT_FILE_REQUIRED")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            data = fh.read(2_000_001)
        obj = loads_strict(data)
        deny(isinstance(obj, dict), "SIGNED_ROOT_DOCUMENT_NOT_OBJECT")
        return obj
    finally:
        os.close(fd)


def main() -> int:
    """Safe authorization preflight, NOT an external runner or permission issuer."""
    import argparse
    import time

    parser = argparse.ArgumentParser(description="A26 redacted signed authority preflight only")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--packet-sha256-from-independent-channel", required=True)
    parser.add_argument("--registry-sha256-from-independent-channel", required=True)
    args = parser.parse_args()
    try:
        packet = _read_private_json(args.packet)
        registry = _read_private_json(args.registry)
        result = verify_signed_authority(
            packet, registry,
            packet_sha256_from_independent_channel=args.packet_sha256_from_independent_channel,
            registry_sha256_from_independent_channel=args.registry_sha256_from_independent_channel,
            now=int(time.time()),
        )
    except (AuthorityDenied, OSError, ValueError, TypeError) as exc:
        result = {
            "schema": "m27.w5.a26.preflight.v1", "status": NOT_PROVISIONED,
            "reason": type(exc).__name__, "external_call_permitted": False,
            "independent_real_world_authority_admitted": False,
            "w5_full_complete": False,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    # Even cryptographic PASS is not sufficient to authorize a real trial.
    return 20


if __name__ == "__main__":
    raise SystemExit(main())
