from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "m27-b03-r01-public-acceptance-receipt/v1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ReceiptRejected(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthorizedIssuer:
    issuer_id: str
    role: str
    public_key_b64: str
    authorization_receipt_sha256: str
    authorization_status: str
    candidate_commit: str
    valid_from_ms: int
    valid_until_ms: int
    revoked: bool = False


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode("ascii")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ReceiptRejected(code)


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def verify_public_acceptance_receipt(
    envelope: Mapping[str, Any],
    *,
    issuer: AuthorizedIssuer | None,
    expected_candidate: str,
    expected_tree: str,
    expected_claims: Mapping[str, int],
    now_ms: int,
    maximum_age_ms: int,
    consumed_receipt_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Verify a non-secret, externally issued receipt without reading source artifacts."""
    _require(set(envelope) == {"payload", "signature_b64", "algorithm"}, "ENVELOPE_SCHEMA")
    _require(envelope["algorithm"] == "Ed25519", "UNSUPPORTED_OR_SELF_SIGNATURE")
    _require(issuer is not None, "ISSUER_NOT_AUTHORIZED")
    assert issuer is not None
    _require(issuer.authorization_status == "DONE_WITH_RECEIPT", "ISSUER_AUTHORIZATION_MISSING")
    _require(issuer.role == "INDEPENDENT_MASTER_EVIDENCE_WITNESS", "ISSUER_ROLE_INVALID")
    _require(_valid_sha(issuer.authorization_receipt_sha256), "ISSUER_AUTHORIZATION_DIGEST_INVALID")
    _require(not issuer.revoked, "ISSUER_REVOKED")
    _require(
        issuer.valid_from_ms <= now_ms <= issuer.valid_until_ms,
        "ISSUER_EXPIRED_OR_NOT_YET_VALID",
    )
    _require(issuer.candidate_commit == expected_candidate, "ISSUER_CANDIDATE_MISMATCH")

    payload = envelope["payload"]
    _require(isinstance(payload, dict), "PAYLOAD_SCHEMA")
    required = {
        "schema",
        "receipt_id",
        "issuer_id",
        "subject",
        "candidate_commit",
        "candidate_tree",
        "observed_at_ms",
        "command_id",
        "pid",
        "pid_command_id",
        "claims",
        "artifact_digests",
        "physical_bytes_observed",
        "custody_independent",
        "production_touched",
    }
    _require(set(payload) == required, "PAYLOAD_SCHEMA")
    _require(payload["schema"] == SCHEMA, "PAYLOAD_VERSION")
    _require(
        isinstance(payload["receipt_id"], str) and payload["receipt_id"],
        "RECEIPT_ID_INVALID",
    )
    _require(
        payload["receipt_id"] not in consumed_receipt_ids,
        "REPLAYED_OR_COPIED_RECEIPT",
    )
    _require(payload["issuer_id"] == issuer.issuer_id, "FORGED_ISSUER")
    _require(payload["subject"] == "B03_MASTER_PHYSICAL_EVIDENCE", "WRONG_SUBJECT")
    _require(payload["candidate_commit"] == expected_candidate, "WRONG_CANDIDATE")
    _require(payload["candidate_tree"] == expected_tree, "INCONSISTENT_TREE")
    _require(payload["claims"] == dict(expected_claims), "COUNT_MISMATCH")
    _require(payload["physical_bytes_observed"] is True, "PHYSICAL_OBSERVATION_MISSING")
    _require(payload["custody_independent"] is True, "CUSTODY_NOT_INDEPENDENT")
    _require(payload["production_touched"] is False, "PRODUCTION_TOUCH_FORBIDDEN")
    _require(isinstance(payload["command_id"], str) and payload["command_id"], "COMMAND_ID_MISSING")
    _require(isinstance(payload["pid"], int) and payload["pid"] > 0, "PID_COMMAND_MISMATCH")
    _require(payload["pid_command_id"] == payload["command_id"], "PID_COMMAND_MISMATCH")
    observed_at_ms = payload["observed_at_ms"]
    _require(isinstance(observed_at_ms, int), "TIMESTAMP_INVALID")
    _require(0 <= now_ms - observed_at_ms <= maximum_age_ms, "STALE_TIMESTAMP")
    digests = payload["artifact_digests"]
    _require(isinstance(digests, dict) and digests, "ARTIFACT_DIGEST_MISSING")
    _require(all(_valid_sha(value) for value in digests.values()), "ARTIFACT_DIGEST_INVALID")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(issuer.public_key_b64))
        signature = base64.b64decode(envelope["signature_b64"], validate=True)
        public_key.verify(signature, canonical_json(payload))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ReceiptRejected("SIGNATURE_INVALID") from exc
    return {
        "schema": "m27-b03-r01-public-receipt-verification/v1",
        "accepted": True,
        "receipt_id": payload["receipt_id"],
        "issuer_id": issuer.issuer_id,
        "candidate_commit": expected_candidate,
        "candidate_tree": expected_tree,
        "payload_sha256": sha256_bytes(canonical_json(payload)),
        "independent_master_proof": True,
    }
