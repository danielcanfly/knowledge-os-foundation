"""Strict *proposed* C1-subset Python byte oracle; feature-off and unauthorizing.

Independent Node counterpart: tests/m27_wire_oracle.mjs.
NOT RFC8785/JCS and NOT a production ABI or signature implementation.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

MAGIC = b"M27-C1-LP-V1\x00"
MAX_SAFE = (1 << 53) - 1
MAX_BODY_BYTES = 65536
SCHEMAS = frozenset({"m27.c1.envelope", "m27.c1.sidecar"})
DOMAINS = {
    "m27.c1.envelope": "m27.envelope.binding.c1",
    "m27.c1.sidecar": "m27.sidecar.binding.c1",
}
REQUIRED = frozenset({
    "schema_id", "tenant_id", "run_id", "task_id", "attempt",
    "issued_at", "expires_at", "consent_ref", "payload", "sidecars",
})
OPTIONAL = frozenset({"memo"})
KEY = re.compile(r"[a-z][a-z0-9_]*\Z", re.ASCII)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z", re.ASCII)
SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
# These authority identifiers may appear ONLY as the typed top-level fields.
UNSIGNED_FIELDS = frozenset({
    "amount_microunits", "price_microunits", "cost_microunits",
    "usage_microunits", "byte_count", "token_count",
})
RESERVED_NESTED = frozenset({
    "tenant_id", "run_id", "task_id", "attempt", "schema_id",
    "consent_ref", "auth_ref", "effective_auth", "signature", "signer_domain",
    "policy_generation", "revocation_generation", "allow_read", "allow_write",
    "approval_id", "privilege", "capability_id", "required_sidecars",
})


class C1Denied(ValueError):
    """Strict C1 candidate rejection; never an authorization result."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, value in items:
        if key in found:
            raise C1Denied("DUPLICATE_JSON_KEY")
        if not KEY.fullmatch(key):
            raise C1Denied("UNSUPPORTED_KEY_OR_NORMALIZATION")
        found[key] = value
    return found


def _int(token: str) -> int:
    if token == "-0":
        raise C1Denied("NEGATIVE_ZERO_UNSUPPORTED")
    value = int(token)
    if value < 0 or value > MAX_SAFE:
        raise C1Denied("UNSAFE_OR_NEGATIVE_INTEGER")
    return value


def _float(_: str) -> None:
    raise C1Denied("FLOAT_OR_EXPONENT_UNSUPPORTED")


def _constant(_: str) -> None:
    raise C1Denied("NONFINITE_NUMBER")


def _validate_tree(value: Any, depth: int = 0, nested: bool = False) -> None:
    if depth > 20:
        raise C1Denied("DEPTH_UNSUPPORTED")
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise C1Denied("UNPAIRED_SURROGATE")
        if unicodedata.normalize("NFC", value) != value:
            raise C1Denied("NON_NFC_VALUE")
    elif type(value) is int:
        if value < 0 or value > MAX_SAFE:
            raise C1Denied("UNSAFE_OR_NEGATIVE_INTEGER")
    elif isinstance(value, dict):
        for key, child in value.items():
            if not KEY.fullmatch(key):
                raise C1Denied("UNSUPPORTED_KEY_OR_NORMALIZATION")
            if nested and key in RESERVED_NESTED:
                raise C1Denied("NESTED_AUTHORITY_SHADOW")
            if key in UNSIGNED_FIELDS and type(child) is not int:
                raise C1Denied("UNSIGNED_FIELD_NOT_INT")
            _validate_tree(child, depth + 1, nested=True)
    elif isinstance(value, list):
        for item in value:
            _validate_tree(item, depth + 1, nested=nested)
    elif value is None or type(value) is bool:
        return
    else:
        raise C1Denied("UNSUPPORTED_VALUE_TYPE")


def _date(value: str) -> datetime:
    if not TIMESTAMP.fullmatch(value):
        raise C1Denied("AMBIGUOUS_TIMESTAMP")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise C1Denied("INVALID_CALENDAR_TIMESTAMP") from exc
    # Eliminate platform-specific early-year representation/roundtrip behavior.
    if parsed.year < 100 or (
        parsed.replace(tzinfo=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
        != value
    ):
        raise C1Denied("INVALID_CALENDAR_TIMESTAMP")
    return parsed


def parse_c1(raw: bytes) -> dict[str, Any]:
    """Decode canonical-candidate *input* without accepting JSON parser coercions."""

    if type(raw) is not bytes or len(raw) > MAX_BODY_BYTES:
        raise C1Denied("WIRE_SIZE_OR_TYPE_UNSUPPORTED")
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise C1Denied("INVALID_UTF8") from exc
    if decoded.startswith("\ufeff"):
        raise C1Denied("UTF8_BOM_UNSUPPORTED")
    try:
        value = json.loads(
            decoded, object_pairs_hook=_pairs, parse_int=_int,
            parse_float=_float, parse_constant=_constant,
        )
    except C1Denied:
        raise
    except (ValueError, UnicodeError) as exc:
        raise C1Denied("INVALID_JSON") from exc
    if type(value) is not dict:
        raise C1Denied("BODY_NOT_OBJECT")
    _validate_tree(value)
    missing = REQUIRED - value.keys()
    extra = value.keys() - (REQUIRED | OPTIONAL)
    if missing:
        raise C1Denied("MISSING_REQUIRED_FIELD")
    if extra:
        raise C1Denied("UNKNOWN_AUTHORITY_OR_BODY_FIELD")
    if value["schema_id"] not in SCHEMAS:
        raise C1Denied("UNRATIFIED_SCHEMA_UNSUPPORTED")
    for field in ("tenant_id", "run_id", "task_id"):
        if type(value[field]) is not str or not value[field]:
            raise C1Denied("SCOPE_OR_NULL_UNBOUND")
    if type(value["attempt"]) is not int:
        raise C1Denied("ATTEMPT_NOT_UNSIGNED_INT")
    if not isinstance(value["issued_at"], str) or not isinstance(value["expires_at"], str):
        raise C1Denied("TIMESTAMP_NOT_STRING")
    if _date(value["issued_at"]) >= _date(value["expires_at"]):
        raise C1Denied("TIMESTAMP_ORDER_INVALID")
    if value["consent_ref"] is not None and (
        type(value["consent_ref"]) is not str or not value["consent_ref"]
    ):
        raise C1Denied("CONSENT_REF_INVALID")
    if type(value["payload"]) is not dict:
        raise C1Denied("PAYLOAD_NOT_OBJECT")
    if type(value["sidecars"]) is not list or not value["sidecars"]:
        raise C1Denied("REQUIRED_SIDECARS_MISSING")
    if any(type(item) is not str or not item for item in value["sidecars"]):
        raise C1Denied("INVALID_SIDECAR_ID")
    if len(set(value["sidecars"])) != len(value["sidecars"]):
        raise C1Denied("DUPLICATE_SIDECAR_ID")
    if "memo" in value and value["memo"] is not None and type(value["memo"]) is not str:
        raise C1Denied("MEMO_TYPE_INVALID")
    return value


def canonical_new_body(raw: bytes) -> bytes:
    """Deterministic tiny ASCII-key, NFC-only, integer-only candidate, not JCS."""

    return json.dumps(
        parse_c1(raw), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def legacy_wire_ref(original_bytes: bytes) -> tuple[bytes, str, int]:
    """Read-only: no parse/rewrite/normalization of historical v1 raw bytes."""

    if type(original_bytes) is not bytes:
        raise C1Denied("LEGACY_BYTES_REQUIRED")
    return original_bytes, hashlib.sha256(original_bytes).hexdigest(), len(original_bytes)


def inspect_legacy_json(original_bytes: bytes) -> None:
    """Optional read-only structural check; historical NFC/order is untouched."""

    if type(original_bytes) is not bytes:
        raise C1Denied("LEGACY_BYTES_REQUIRED")
    try:
        wire = original_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise C1Denied("LEGACY_INVALID_UTF8") from exc

    def duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise C1Denied("LEGACY_DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        json.loads(wire, object_pairs_hook=duplicates, parse_constant=_constant)
    except C1Denied:
        raise
    except ValueError as exc:
        raise C1Denied("LEGACY_INVALID_JSON") from exc
    # Legacy strings and whitespace are deliberately NOT normalized or rewritten.


def _field(data: bytes) -> bytes:
    if len(data) > 0xFFFFFFFF:
        raise C1Denied("LENGTH_OVERFLOW")
    return struct.pack(">I", len(data)) + data


@dataclass(frozen=True, slots=True)
class CandidateDigest:
    status: str
    canonical_hex: str
    canonical_sha256: str
    legacy_raw_sha256: str
    binding_hex: str
    binding_sha256: str


def bind_candidate(
    raw: bytes,
    legacy_raw: bytes,
    *,
    domain: str,
    tenant_id: str,
    run_id: str,
    task_id: str,
    attempt: int,
    expected_legacy_sha256: str | None = None,
) -> CandidateDigest:
    body = parse_c1(raw)
    if domain != DOMAINS[body["schema_id"]]:
        raise C1Denied("DOMAIN_SCHEMA_MISMATCH")
    if (tenant_id, run_id, task_id, attempt) != (
        body["tenant_id"], body["run_id"], body["task_id"], body["attempt"],
    ) or type(attempt) is not int:
        raise C1Denied("IDENTITY_TUPLE_MISMATCH")
    _, legacy_sha, _ = legacy_wire_ref(legacy_raw)
    if expected_legacy_sha256 is not None and (
        not SHA.fullmatch(expected_legacy_sha256)
        or expected_legacy_sha256 != legacy_sha
    ):
        raise C1Denied("LEGACY_DIGEST_MISMATCH")
    canonical = canonical_new_body(raw)
    fields = (
        domain.encode("ascii"), body["schema_id"].encode("ascii"), canonical,
        bytes.fromhex(legacy_sha), tenant_id.encode("utf-8"),
        run_id.encode("utf-8"), task_id.encode("utf-8"),
        str(attempt).encode("ascii"),
    )
    wire = MAGIC + b"".join(_field(item) for item in fields)
    return CandidateDigest(
        status="CANDIDATE_DIGEST_UNRATIFIED",
        canonical_hex=canonical.hex(),
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        legacy_raw_sha256=legacy_sha,
        binding_hex=wire.hex(),
        binding_sha256=hashlib.sha256(wire).hexdigest(),
    )
