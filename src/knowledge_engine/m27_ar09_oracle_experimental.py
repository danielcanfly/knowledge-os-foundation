"""Independent synthetic AR01V raw-byte and negative-behaviour oracle.

The module is stdlib-only, has no provider hooks, and does not import candidate
AR04/AR05 implementations.  Labels are test-only and are not runtime enums.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

EXPECTED_DENY = "EXPECTED_DENY"
EXPECTED_UNKNOWN_PROOF = "EXPECTED_UNKNOWN_PROOF"
EXPECTED_UNKNOWN_EFFECT = "EXPECTED_UNKNOWN_EFFECT"
EXPECTED_STREAM_FAIL = "EXPECTED_STREAM_FAIL"
EXPECTED_ACCEPT_FIXTURE_ONLY = "EXPECTED_ACCEPT_FIXTURE_ONLY"
NOT_RUN = "NOT_RUN"

OracleLabel = Literal[
    "EXPECTED_DENY",
    "EXPECTED_UNKNOWN_PROOF",
    "EXPECTED_UNKNOWN_EFFECT",
    "EXPECTED_STREAM_FAIL",
    "EXPECTED_ACCEPT_FIXTURE_ONLY",
]

SAFE_JSON_UINT_MAX = 2**53 - 1
REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "tenant_id",
        "task_id",
        "task_version",
        "run_id",
        "attempt",
        "audience",
        "issued_at",
        "expires_at",
        "signer_key_id",
        "signer_domain",
        "policy_generation",
        "delegated_by",
        "delegation_expires_at",
        "consent_required",
        "consent_ref",
        "source",
        "journal_head_seq",
        "journal_head_hash",
        "proof_head_seq",
        "proof_head_hash",
        "lease_epoch",
        "proof_lease_epoch",
        "price_microunits",
        "usage_microunits",
        "metadata",
    }
)
ALLOWED_RECORD_TYPES = frozenset({"verification_proposal", "native_evidence_view"})
AUTHORITY_SHADOW_NAMES = frozenset(
    {"allow_read", "verified", "signer_domain", "tenant_id", "effective_auth_ref"}
)


class _DuplicateKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OracleConfig:
    now: str
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    attempt: int
    audience: str
    lease_epoch: int
    journal_head_seq: int
    journal_head_hash: str
    policy_generation: int
    trusted_keys: frozenset[str]
    revoked_keys: frozenset[str]
    forbidden_signers: frozenset[str]
    expected_raw_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class OracleResult:
    label: OracleLabel
    reason: str
    raw_bytes_sha256: str
    canonical_json_sha256: str | None


@dataclass(frozen=True, slots=True)
class NativeCitation:
    citation_id: str
    source_id: str
    source_revision: str
    source_digest: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class NativeSourceFixture:
    kind: Literal["native", "synthetic"]
    tenant_id: str
    snapshot_id: str
    source_bytes: bytes
    source_digest: str
    citations: tuple[NativeCitation, ...]
    attested: bool = True


@dataclass(frozen=True, slots=True)
class StreamFrame:
    kind: Literal["progress", "verified_text", "terminal", "safe_abstention"]
    payload: bytes
    citation_ids: tuple[str, ...] = ()
    client_ack: bool = False
    answer_timestamp_present: bool = False


@dataclass(frozen=True, slots=True)
class ScheduleOracle:
    label: OracleLabel
    winner: str | None
    loser: str | None
    commit_count: int
    send_count: int
    reason: str


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return _sha(encoded)


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return parsed


def _result(
    label: OracleLabel,
    reason: str,
    raw: bytes,
    parsed: object | None = None,
) -> OracleResult:
    canonical = None if parsed is None else _canonical_sha(parsed)
    return OracleResult(label, reason, _sha(raw), canonical)


def base_envelope() -> dict[str, object]:
    """Return a deterministic, entirely synthetic positive fixture."""

    return {
        "schema_version": "1.0.0",
        "record_type": "verification_proposal",
        "tenant_id": "tenant-a",
        "task_id": "task-a",
        "task_version": 1,
        "run_id": "run-a",
        "attempt": 1,
        "audience": "ar05.verifier",
        "issued_at": "2026-10-09T00:00:00Z",
        "expires_at": "2026-10-10T00:00:00Z",
        "signer_key_id": "trusted-key",
        "signer_domain": "independent-oracle",
        "policy_generation": 7,
        "delegated_by": "owner-a",
        "delegation_expires_at": "2026-10-10T00:00:00Z",
        "consent_required": True,
        "consent_ref": "consent-a",
        "source": {
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "source_revision": "revision-a",
            "source_digest": "a" * 64,
        },
        "journal_head_seq": 11,
        "journal_head_hash": "b" * 64,
        "proof_head_seq": 11,
        "proof_head_hash": "b" * 64,
        "lease_epoch": 3,
        "proof_lease_epoch": 3,
        "price_microunits": 5,
        "usage_microunits": 5,
        "metadata": {},
    }


def default_config() -> OracleConfig:
    return OracleConfig(
        now="2026-10-09T12:00:00Z",
        tenant_id="tenant-a",
        task_id="task-a",
        task_version=1,
        run_id="run-a",
        attempt=1,
        audience="ar05.verifier",
        lease_epoch=3,
        journal_head_seq=11,
        journal_head_hash="b" * 64,
        policy_generation=7,
        trusted_keys=frozenset({"trusted-key"}),
        revoked_keys=frozenset(),
        forbidden_signers=frozenset({"answer-generator"}),
    )


def encode_envelope(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def classify_wire(raw: bytes, config: OracleConfig | None = None) -> OracleResult:
    """Independently classify a strict synthetic envelope without side effects."""

    config = config or default_config()
    if config.expected_raw_sha256 is not None and _sha(raw) != config.expected_raw_sha256:
        return _result(EXPECTED_DENY, "ORIGINAL_RAW_BYTES_MISMATCH", raw)
    try:
        parsed = json.loads(raw, object_pairs_hook=_pairs_no_duplicates)
    except _DuplicateKey:
        return _result(EXPECTED_DENY, "DUPLICATE_JSON_KEY", raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _result(EXPECTED_DENY, "INVALID_UTF8_OR_JSON", raw)
    if not isinstance(parsed, dict):
        return _result(EXPECTED_DENY, "TOP_LEVEL_NOT_OBJECT", raw, parsed)
    missing = REQUIRED_FIELDS - parsed.keys()
    if missing:
        return _result(EXPECTED_DENY, "MISSING_REQUIRED_FIELD", raw, parsed)
    if set(parsed) - REQUIRED_FIELDS:
        return _result(EXPECTED_DENY, "UNKNOWN_AUTHORITY_FIELD", raw, parsed)
    if parsed["schema_version"] != "1.0.0":
        return _result(EXPECTED_DENY, "UNSUPPORTED_VERSION", raw, parsed)
    if parsed["record_type"] not in ALLOWED_RECORD_TYPES:
        return _result(EXPECTED_DENY, "UNSUPPORTED_RECORD_TYPE", raw, parsed)
    for name in (
        "task_version",
        "attempt",
        "policy_generation",
        "journal_head_seq",
        "proof_head_seq",
        "lease_epoch",
        "proof_lease_epoch",
    ):
        value = parsed[name]
        if type(value) is not int or value < 0 or value > SAFE_JSON_UINT_MAX:
            return _result(EXPECTED_DENY, "BOOL_OR_UNSAFE_UINT", raw, parsed)
    issued = _time(parsed["issued_at"])
    expires = _time(parsed["expires_at"])
    delegated_until = _time(parsed["delegation_expires_at"])
    now = _time(config.now)
    if None in {issued, expires, delegated_until, now}:
        return _result(EXPECTED_DENY, "TIMESTAMP_UNCERTAIN", raw, parsed)
    assert issued is not None and expires is not None and delegated_until is not None and now
    if issued > now or expires <= now or delegated_until <= now:
        return _result(EXPECTED_DENY, "PROOF_OR_DELEGATION_EXPIRED", raw, parsed)
    key = parsed["signer_key_id"]
    signer = parsed["signer_domain"]
    if key in config.revoked_keys or key not in config.trusted_keys:
        return _result(EXPECTED_DENY, "UNKNOWN_OR_REVOKED_TRUST_ROOT", raw, parsed)
    if signer in config.forbidden_signers:
        return _result(EXPECTED_UNKNOWN_PROOF, "SELF_VERIFIER", raw, parsed)
    identity = (
        parsed["tenant_id"],
        parsed["task_id"],
        parsed["task_version"],
        parsed["run_id"],
        parsed["attempt"],
        parsed["audience"],
    )
    expected_identity = (
        config.tenant_id,
        config.task_id,
        config.task_version,
        config.run_id,
        config.attempt,
        config.audience,
    )
    if identity != expected_identity:
        return _result(EXPECTED_DENY, "IDENTITY_OR_AUDIENCE_MISMATCH", raw, parsed)
    if parsed["policy_generation"] != config.policy_generation:
        return _result(EXPECTED_UNKNOWN_PROOF, "STALE_POLICY_GENERATION", raw, parsed)
    if (
        parsed["lease_epoch"] != config.lease_epoch
        or parsed["proof_lease_epoch"] != config.lease_epoch
    ):
        return _result(EXPECTED_DENY, "STALE_LEASE_BINDING", raw, parsed)
    if (
        parsed["journal_head_seq"] != config.journal_head_seq
        or parsed["proof_head_seq"] != config.journal_head_seq
        or parsed["journal_head_hash"] != config.journal_head_hash
        or parsed["proof_head_hash"] != config.journal_head_hash
    ):
        return _result(EXPECTED_DENY, "STALE_JOURNAL_PROOF", raw, parsed)
    if parsed["delegated_by"] is None:
        return _result(EXPECTED_DENY, "DELEGATION_MISSING", raw, parsed)
    if parsed["consent_required"] is True and not parsed["consent_ref"]:
        return _result(EXPECTED_DENY, "CONSENT_MISSING", raw, parsed)
    source = parsed["source"]
    if not isinstance(source, dict):
        return _result(EXPECTED_DENY, "SOURCE_BINDING_INVALID", raw, parsed)
    if set(source) != {"tenant_id", "source_id", "source_revision", "source_digest"}:
        return _result(EXPECTED_DENY, "SOURCE_AUTHORITY_FIELD_OR_SHAPE_INVALID", raw, parsed)
    if source["tenant_id"] != config.tenant_id:
        return _result(EXPECTED_DENY, "TENANT_OR_SOURCE_MISMATCH", raw, parsed)
    if not source["source_revision"] or not source["source_digest"]:
        return _result(EXPECTED_DENY, "SOURCE_PIN_MISSING", raw, parsed)
    metadata = parsed["metadata"]
    if not isinstance(metadata, dict) or _contains_authority_shadow(metadata):
        return _result(EXPECTED_DENY, "AUTHORITY_SHADOWING", raw, parsed)
    price = parsed["price_microunits"]
    usage = parsed["usage_microunits"]
    if price is None or usage is None:
        return _result(EXPECTED_UNKNOWN_PROOF, "PRICE_OR_USAGE_MISSING", raw, parsed)
    if type(price) is not int or type(usage) is not int or price < 0 or usage < 0:
        return _result(EXPECTED_DENY, "PRICE_OR_USAGE_INVALID", raw, parsed)
    return _result(EXPECTED_ACCEPT_FIXTURE_ONLY, "SYNTHETIC_FIXTURE_ACCEPT", raw, parsed)


def _contains_authority_shadow(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in AUTHORITY_SHADOW_NAMES or _contains_authority_shadow(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_authority_shadow(item) for item in value)
    return False


def compare_native_source(
    original: NativeSourceFixture, observed: NativeSourceFixture
) -> OracleResult:
    """Judge native bytes/citation identity without exposing cross-tenant details."""

    raw = original.source_bytes
    if original.tenant_id != observed.tenant_id:
        return _result(EXPECTED_DENY, "TENANT_OR_SOURCE_MISMATCH", raw)
    if not original.attested or not observed.attested:
        return _result(EXPECTED_UNKNOWN_PROOF, "SOURCE_ATTESTATION_MISSING", raw)
    if original.kind != "native" or observed.kind != "native":
        return _result(EXPECTED_DENY, "NATIVE_SYNTHETIC_SUBSTITUTION", raw)
    if _sha(original.source_bytes) != original.source_digest:
        return _result(EXPECTED_DENY, "ORIGINAL_BYTES_DIGEST_MISMATCH", raw)
    if (
        original.snapshot_id != observed.snapshot_id
        or original.source_bytes != observed.source_bytes
        or original.source_digest != observed.source_digest
        or original.citations != observed.citations
    ):
        return _result(EXPECTED_DENY, "SOURCE_BYTES_OR_CITATION_ORDER_CHANGED", raw)
    for citation in original.citations:
        if (
            citation.source_digest != original.source_digest
            or not citation.source_revision
            or citation.start < 0
            or citation.end <= citation.start
            or citation.end > len(original.source_bytes)
        ):
            return _result(EXPECTED_DENY, "CITATION_SPAN_OR_PIN_INVALID", raw)
    return _result(EXPECTED_ACCEPT_FIXTURE_ONLY, "NATIVE_FIXTURE_IDENTICAL", raw)


def classify_stream(frames: tuple[StreamFrame, ...]) -> OracleLabel:
    """Judge progress/text/citation/delivery boundaries without live streaming."""

    terminal = next((index for index, item in enumerate(frames) if item.kind == "terminal"), None)
    verified = [
        (index, item)
        for index, item in enumerate(frames)
        if item.kind == "verified_text" and item.payload.strip()
    ]
    abstention = next((item for item in frames if item.kind == "safe_abstention"), None)
    if abstention is not None:
        return (
            EXPECTED_STREAM_FAIL
            if abstention.answer_timestamp_present
            else EXPECTED_ACCEPT_FIXTURE_ONLY
        )
    if not verified or terminal is not None and verified[0][0] >= terminal:
        return EXPECTED_STREAM_FAIL
    first = verified[0][1]
    if not first.citation_ids:
        return EXPECTED_STREAM_FAIL
    if not first.client_ack:
        return EXPECTED_UNKNOWN_PROOF
    return EXPECTED_ACCEPT_FIXTURE_ONLY


def two_writer_cas_oracle(seed: int) -> ScheduleOracle:
    """Select one deterministic winner; the other must conflict with zero sends."""

    actors = ["writer-a", "writer-b"]
    random.Random(seed).shuffle(actors)
    return ScheduleOracle(
        EXPECTED_ACCEPT_FIXTURE_ONLY,
        actors[0],
        actors[1],
        commit_count=1,
        send_count=0,
        reason="ONE_CAS_WINNER",
    )


def remote_unknown_oracle(*, t3_crossed: bool, ack_lost: bool) -> ScheduleOracle:
    """Model a remote uncertainty schedule; it never performs the send."""

    if t3_crossed and ack_lost:
        return ScheduleOracle(
            EXPECTED_UNKNOWN_EFFECT,
            None,
            None,
            commit_count=1,
            send_count=0,
            reason="POSSIBLY_SENT_NO_BLIND_RETRY",
        )
    return ScheduleOracle(
        EXPECTED_ACCEPT_FIXTURE_ONLY,
        None,
        None,
        commit_count=int(t3_crossed),
        send_count=0,
        reason="NO_REMOTE_EFFECT_EXECUTED",
    )


def generate_case(case_id: str, seed: int = 0) -> tuple[bytes, OracleLabel]:
    """Generate selected deterministic AR01V cases from an independent seed."""

    value = base_envelope()
    if case_id == "V01":
        raw = encode_envelope(value) + b" "
        return raw, EXPECTED_DENY
    if case_id == "V06":
        return b'{"tenant_id":"a","tenant_id":"b"}', EXPECTED_DENY
    if case_id == "V02":
        value["record_type"] = "unknown_authority_record"
    elif case_id == "V07":
        value["task_version"] = True
    elif case_id == "V08":
        value["attempt"] = SAFE_JSON_UINT_MAX + 1
    elif case_id == "V09":
        value["expires_at"] = "2026-10-10 00:00:00"
    elif case_id == "V11":
        value["signer_key_id"] = "unknown-key"
    elif case_id == "V16":
        value["source"] = {**value["source"], "tenant_id": "tenant-b"}  # type: ignore[dict-item]
    elif case_id == "V17":
        value["consent_ref"] = None
    elif case_id == "V20":
        value["audience"] = "wrong-audience"
    elif case_id == "V21":
        value["source"] = {**value["source"], "source_revision": ""}  # type: ignore[dict-item]
    elif case_id in {"V32", "V33"}:
        value["price_microunits" if case_id == "V32" else "usage_microunits"] = None
        return encode_envelope(value), EXPECTED_UNKNOWN_PROOF
    elif case_id == "V35":
        value["task_version"] = 2
    elif case_id == "V40":
        value["allow_read"] = True
    elif case_id == "V41":
        value.pop("run_id")
    elif case_id == "V42":
        value["policy_generation"] = 6
        return encode_envelope(value), EXPECTED_UNKNOWN_PROOF
    elif case_id == "V43":
        value["signer_domain"] = "answer-generator"
        return encode_envelope(value), EXPECTED_UNKNOWN_PROOF
    elif case_id == "V44":
        value["proof_head_seq"] = 10
    elif case_id == "V45":
        value["proof_lease_epoch"] = 2
    elif case_id == "V50":
        value["metadata"] = {"nested": {"signer_domain": "shadow"}}
    else:
        random.Random(seed).random()
        return encode_envelope(value), EXPECTED_ACCEPT_FIXTURE_ONLY
    return encode_envelope(value), EXPECTED_DENY


IMPLEMENTED_VECTORS = frozenset(
    {
        "V01",
        "V02",
        "V06",
        "V07",
        "V08",
        "V09",
        "V11",
        "V14",
        "V16",
        "V17",
        "V20",
        "V21",
        "V22",
        "V26",
        "V27",
        "V29",
        "V30",
        "V31",
        "V32",
        "V33",
        "V35",
        "V39",
        "V40",
        "V41",
        "V42",
        "V43",
        "V44",
        "V45",
        "V48",
        "V49",
        "V50",
    }
)
VECTOR_COVERAGE = {
    f"V{index:02d}": "IMPLEMENTED" if f"V{index:02d}" in IMPLEMENTED_VECTORS else NOT_RUN
    for index in range(1, 51)
}


def mutate_source(fixture: NativeSourceFixture, **changes: object) -> NativeSourceFixture:
    """Convenience for tests; mutation never changes the frozen original."""

    return replace(fixture, **changes)
