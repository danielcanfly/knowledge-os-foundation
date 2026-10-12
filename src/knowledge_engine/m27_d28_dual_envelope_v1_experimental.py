"""D28 local-only AR01 canonical dual-envelope golden adapter.

A candidate hash/reader contract, NOT a ratified ABI, signature verifier, IdP
grant, permission issuer, remote observer or production publication adapter.
It has no effectful transport. The historical legacy byte string is immutable.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import unicodedata
from collections.abc import Mapping
from typing import Any

LEGACY_NS = "ar01v.envelope"
NEW_NS = "ar01z.new-record"
VERSION = "1.0.0"
DOMAIN = b"M27-D28-AR01-ABI-CANDIDATE\x00"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NAMES = re.compile(r"[a-z][a-z0-9_.-]*\Z")
MAX_WIRE = 65536
MAX_INT = (1 << 53) - 1
COMMON = frozenset({
    "namespace", "schema_version", "record_type", "record_id", "tenant_id",
    "run_id", "policy_generation", "revocation_generation", "checkpoint",
    "field_hashes", "envelope_digest",
})
LEGACY_ONLY = frozenset({"legacy_ref", "required_sidecars"})
NEW_ONLY = frozenset({"new_record_kind", "new_record_namespace", "body", "body_sha256"})
KINDS = frozenset({"revocation", "billing", "postterminal"})
KIND_NS = {
    "revocation": "ar06.revocation-control",
    "billing": "ar02.billing-ledger",
    "postterminal": "ar05r.notice",
}
KIND_REQUIRED = {
    "revocation": frozenset({"exclusion_generation", "subject_ref", "reason_code"}),
    "billing": frozenset({"charge_id", "billing_status", "usage_ref"}),
    "postterminal": frozenset({
        "original_terminal_head_hash", "notice_seq", "notice_prev_hash",
        "client_cursor", "supersedes_segment_id", "kind",
    }),
}
LEGACY_REF_FIELDS = frozenset({"raw_sha256", "raw_byte_length", "original_event_hash"})
CHECKPOINT_FIELDS = frozenset({"seq", "head_hash"})


class D28Denied(ValueError):
    """Local negative golden: hard reject, never fall back to raw-legacy authority."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_canonical(value))


def _canonical(value: Any) -> bytes:
    def check(obj: Any, depth: int = 0) -> None:
        if depth > 20:
            raise D28Denied("DEPTH_UNSUPPORTED")
        if isinstance(obj, Mapping):
            for key, child in obj.items():
                if not isinstance(key, str) or not NAMES.fullmatch(key):
                    raise D28Denied("UNSUPPORTED_FIELD_NAME")
                check(child, depth + 1)
        elif isinstance(obj, (list, tuple)):
            for child in obj:
                check(child, depth + 1)
        elif isinstance(obj, str):
            if any(0xD800 <= ord(ch) <= 0xDFFF for ch in obj):
                raise D28Denied("SURROGATE_NOT_ALLOWED")
            if unicodedata.normalize("NFC", obj) != obj:
                raise D28Denied("NON_NFC_NEW_WIRE")
        elif type(obj) is int:
            if not 0 <= obj <= MAX_INT:
                raise D28Denied("INTEGER_OUT_OF_RANGE")
        elif obj is not None and type(obj) is not bool:
            raise D28Denied("UNSUPPORTED_VALUE_TYPE")
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in items:
        if key in output:
            raise D28Denied("DUPLICATE_FIELD")
        output[key] = value
    return output


def _bad_number(_: str) -> None:
    raise D28Denied("FLOAT_DISALLOWED")


def _int(value: str) -> int:
    if value.startswith("-") or int(value) > MAX_INT:
        raise D28Denied("INTEGER_OUT_OF_RANGE")
    return int(value)


def load_wire(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or len(raw) > MAX_WIRE:
        raise D28Denied("WIRE_LENGTH")
    try:
        item = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
                          parse_int=_int, parse_float=_bad_number,
                          parse_constant=_bad_number)
    except D28Denied:
        raise
    except (UnicodeError, ValueError) as exc:
        raise D28Denied("INVALID_JSON_UTF8") from exc
    if type(item) is not dict:
        raise D28Denied("WIRE_NOT_OBJECT")
    if _canonical(item) != raw:
        raise D28Denied("NONCANONICAL_NEW_WIRE")
    return item


def _require_sha(value: Any, code: str = "DIGEST_SHAPE") -> None:
    if type(value) is not str or not HEX64.fullmatch(value):
        raise D28Denied(code)


def _checkpoint(seq: int, head_hash: str) -> dict[str, Any]:
    if type(seq) is not int or seq < 0:
        raise D28Denied("CHECKPOINT_SEQ")
    _require_sha(head_hash, "CHECKPOINT_HEAD")
    return {"seq": seq, "head_hash": head_hash}


def _digest_tuple(envelope: dict[str, Any]) -> str:
    core = {k: v for k, v in envelope.items() if k != "envelope_digest"}
    raw = _canonical(core)
    if len(raw) > MAX_WIRE:
        raise D28Denied("WIRE_LENGTH")
    # Frame prevents concatenation ambiguity, scoped separately from old event SHA.
    payload = DOMAIN + struct.pack(">I", len(raw)) + raw
    return _sha(payload)


def _seal(envelope: dict[str, Any]) -> bytes:
    envelope["envelope_digest"] = _digest_tuple(envelope)
    result = _canonical(envelope)
    if len(result) > MAX_WIRE:
        raise D28Denied("WIRE_LENGTH")
    return result


def _common(record_type: str, ns: str, record_id: str, tenant_id: str,
            run_id: str, policy_generation: int, revocation_generation: int,
            checkpoint_seq: int, checkpoint_head: str) -> dict[str, Any]:
    for field in (record_id, tenant_id, run_id):
        if type(field) is not str or not field:
            raise D28Denied("UNBOUND_IDENTITY")
    if any(type(v) is not int or v < 0 for v in
           (policy_generation, revocation_generation)):
        raise D28Denied("GENERATION_UNBOUND")
    return {
        "namespace": ns, "schema_version": VERSION, "record_type": record_type,
        "record_id": record_id, "tenant_id": tenant_id, "run_id": run_id,
        "policy_generation": policy_generation,
        "revocation_generation": revocation_generation,
        "checkpoint": _checkpoint(checkpoint_seq, checkpoint_head),
    }


def make_legacy(*, raw_legacy: bytes, original_event_hash: str,
                required_sidecars: list[dict[str, str]], record_id: str,
                tenant_id: str, run_id: str, policy_generation: int,
                revocation_generation: int, checkpoint_seq: int,
                checkpoint_head: str) -> bytes:
    if type(raw_legacy) is not bytes:
        raise D28Denied("LEGACY_RAW_BYTES_REQUIRED")
    _require_sha(original_event_hash, "LEGACY_EVENT_HASH")
    envelope = _common("legacy-bound", LEGACY_NS, record_id, tenant_id, run_id,
                       policy_generation, revocation_generation, checkpoint_seq,
                       checkpoint_head)
    envelope["legacy_ref"] = {
        "raw_sha256": _sha(raw_legacy), "raw_byte_length": len(raw_legacy),
        "original_event_hash": original_event_hash,
    }
    envelope["required_sidecars"] = required_sidecars
    envelope["field_hashes"] = {
        "legacy_ref": _digest(envelope["legacy_ref"]),
        "required_sidecars": _digest(required_sidecars),
        "checkpoint": _digest(envelope["checkpoint"]),
    }
    result = _seal(envelope)
    validate_wire(result, raw_legacy=raw_legacy)
    return result


def make_new(*, new_record_kind: str, new_record_namespace: str,
             body: dict[str, Any], record_id: str, tenant_id: str, run_id: str,
             policy_generation: int, revocation_generation: int,
             checkpoint_seq: int, checkpoint_head: str) -> bytes:
    envelope = _common("new-record", NEW_NS, record_id, tenant_id, run_id,
                       policy_generation, revocation_generation, checkpoint_seq,
                       checkpoint_head)
    envelope["new_record_kind"] = new_record_kind
    envelope["new_record_namespace"] = new_record_namespace
    envelope["body"] = body
    envelope["body_sha256"] = _digest(body)
    envelope["field_hashes"] = {
        "body": _digest(body), "checkpoint": _digest(envelope["checkpoint"]),
    }
    result = _seal(envelope)
    validate_wire(result)
    return result


def validate_wire(raw: bytes, *, raw_legacy: bytes | None = None) -> dict[str, Any]:
    item = load_wire(raw)
    mode = item.get("record_type")
    wanted = COMMON | (LEGACY_ONLY if mode == "legacy-bound" else NEW_ONLY)
    if type(mode) is not str or mode not in {"legacy-bound", "new-record"} or item.keys() != wanted:
        raise D28Denied("ENVELOPE_FIELDS_OR_KIND")
    namespace = LEGACY_NS if mode == "legacy-bound" else NEW_NS
    if item["namespace"] != namespace or item["schema_version"] != VERSION:
        raise D28Denied("UNSUPPORTED_VERSION_NO_DOWNGRADE")
    if type(item["checkpoint"]) is not dict or item["checkpoint"].keys() != CHECKPOINT_FIELDS:
        raise D28Denied("CHECKPOINT_FIELD_SET")
    _common(mode, namespace, item["record_id"], item["tenant_id"], item["run_id"],
            item["policy_generation"], item["revocation_generation"],
            item["checkpoint"]["seq"], item["checkpoint"]["head_hash"])
    if mode == "legacy-bound":
        ref = item["legacy_ref"]
        if type(ref) is not dict or ref.keys() != LEGACY_REF_FIELDS:
            raise D28Denied("LEGACY_REF_FIELDS")
        _require_sha(ref["raw_sha256"])
        _require_sha(ref["original_event_hash"])
        if type(ref["raw_byte_length"]) is not int:
            raise D28Denied("LEGACY_LENGTH_SHAPE")
        if type(raw_legacy) is not bytes:
            raise D28Denied("LEGACY_BYTES_ABSENT")
        if ref["raw_byte_length"] != len(raw_legacy):
            raise D28Denied("LEGACY_LENGTH_MISMATCH")
        if ref["raw_sha256"] != _sha(raw_legacy):
            raise D28Denied("LEGACY_RAW_HASH_MISMATCH")
        sidecars = item["required_sidecars"]
        if type(sidecars) is not list or not sidecars:
            raise D28Denied("REQUIRED_SIDECARS_MISSING")
        seen: set[tuple[str, str]] = set()
        for sidecar in sidecars:
            if type(sidecar) is not dict or sidecar.keys() != {
                "namespace", "schema_version", "body_sha256",
            }:
                raise D28Denied("SIDECAR_FIELDS")
            if sidecar["schema_version"] != VERSION or type(sidecar["namespace"]) is not str:
                raise D28Denied("SIDECAR_VERSION_UNSUPPORTED")
            _require_sha(sidecar["body_sha256"])
            identity = (sidecar["namespace"], sidecar["schema_version"])
            if not NAMES.fullmatch(sidecar["namespace"]) or identity in seen:
                raise D28Denied("SIDECAR_DUPLICATE_OR_INVALID")
            seen.add(identity)
        expected_hashes = {
            "legacy_ref": _digest(ref), "required_sidecars": _digest(sidecars),
            "checkpoint": _digest(item["checkpoint"]),
        }
    else:
        if raw_legacy is not None:
            raise D28Denied("NEW_RECORD_CANNOT_BIND_LEGACY")
        kind = item["new_record_kind"]
        ns = item["new_record_namespace"]
        if type(kind) is not str or kind not in KINDS or type(ns) is not str or ns != KIND_NS[kind]:
            raise D28Denied("NEW_RECORD_KIND_OR_NAMESPACE")
        body = item["body"]
        if type(body) is not dict or body.keys() != KIND_REQUIRED[kind]:
            raise D28Denied("NEW_BODY_FIELDS")
        if kind == "revocation" and (
            type(body["exclusion_generation"]) is not int
            or body["exclusion_generation"] <= 0
        ):
            raise D28Denied("REVOCATION_GENERATION")
        if kind == "billing" and body["billing_status"] not in {
            "PENDING", "FINAL", "UNKNOWN", "OVERRUN",
        }:
            raise D28Denied("BILLING_STATUS")
        if kind == "postterminal":
            for f in ("original_terminal_head_hash", "notice_prev_hash"):
                _require_sha(body[f])
            if type(body["notice_seq"]) is not int or body["notice_seq"] < 1:
                raise D28Denied("NOTICE_SEQ")
            if (
                type(body["client_cursor"]) is not int
                or body["client_cursor"] != body["notice_seq"]
            ):
                raise D28Denied("NOTICE_CURSOR")
            if body["kind"] not in {"correction", "retraction", "privacy_suppression"}:
                raise D28Denied("NOTICE_KIND")
        for key, val in body.items():
            if key not in {"exclusion_generation", "notice_seq", "client_cursor"} and (
                type(val) is not str or not val
            ):
                raise D28Denied("NEW_BODY_VALUE")
        if item["body_sha256"] != _digest(body):
            raise D28Denied("NEW_BODY_HASH_MISMATCH")
        expected_hashes = {
            "body": _digest(body), "checkpoint": _digest(item["checkpoint"]),
        }
    if item["field_hashes"] != expected_hashes:
        raise D28Denied("FIELD_HASH_MISMATCH")
    if item["envelope_digest"] != _digest_tuple(item):
        raise D28Denied("ENVELOPE_HASH_MISMATCH")
    return item


def negotiate_reader(raw: bytes, *, supported: Mapping[str, set[str]],
                     understood_sidecars: set[str], raw_legacy: bytes | None = None,
                     old_native_reader: bool = False) -> dict[str, Any]:
    """Gateway must evaluate mandatory proofs BEFORE invoking an old reader."""
    if old_native_reader:
        raise D28Denied("OLD_READER_REQUIRES_GATEWAY_NO_FALLBACK")
    item = validate_wire(raw, raw_legacy=raw_legacy)
    if item["schema_version"] not in supported.get(item["namespace"], set()):
        raise D28Denied("READER_UNSUPPORTED_NO_DOWNGRADE")
    if item["record_type"] == "legacy-bound":
        required = {x["namespace"] for x in item["required_sidecars"]}
        if not required.issubset(understood_sidecars):
            raise D28Denied("UNKNOWN_REQUIRED_AUTHORITY_NO_DOWNGRADE")
    return item
