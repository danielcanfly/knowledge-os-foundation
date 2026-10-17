"""B0-01 semantic ANSWER cache ABI. Pure contract, no activated store or public route.

This code does NOT authenticate callers, grant source rights, run a semantic
verifier, or admit a real HIT. H01/H02 must supply qualified, independent
enforcers before any product wiring. No answer cache is enabled here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

SCHEMA_VERSION = "m27.semantic-answer-cache/v1"
DEFAULT_NONPROD_CACHE_ENABLED = False
CACHE_MODES = frozenset({"AUTO", "BYPASS", "REFRESH"})
DECISIONS = frozenset({
    "DISABLED", "BYPASSED", "REFUSED_NON_QA", "LOOKUP_REQUIRED",
    "REGENERATE_NO_LOOKUP", "DENY_CANDIDATE", "PROVER_REQUIRED",
    "VERIFIED_FIXTURE_ONLY", "HIT_NOT_ADMITTED", "WRITE_NOT_ADMITTED",
})
MAX_TTL_SECONDS = 3600  # hard local ceiling, not client authority
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_UTC = dt.timezone.utc


class CacheContractError(ValueError):
    """Fail-closed parsing; caller must not silently coerce invalid fields."""


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise CacheContractError(code)


def _shape(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    _require(type(value) is dict, "OBJECT_REQUIRED")
    _require(required <= set(value), "MISSING_FIELD")
    _require(set(value) <= (required | (optional or set())), "UNKNOWN_OR_PRIVILEGED_FIELD")
    return value


def _str(value: Any, name: str, limit: int = 256) -> None:
    _require(type(value) is str and 0 < len(value) <= limit and value.strip() == value, name)


def _sha(value: Any) -> None:
    _require(type(value) is str and _SHA256.fullmatch(value) is not None, "INVALID_SHA256")


def _time(value: Any) -> dt.datetime:
    _str(value, "INVALID_TIMESTAMP", 40)
    _require(value.endswith("Z"), "TIMESTAMP_NOT_UTC")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except (TypeError, ValueError) as exc:
        raise CacheContractError("INVALID_TIMESTAMP") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0), "TIMESTAMP_NOT_UTC")
    return parsed


def _strings(values: Any, *, name: str, limit: int = 24) -> None:
    _require(type(values) is list and len(values) <= limit, name)
    for val in values:
        _str(val, name, 256)
    _require(len(values) == len(set(values)), "DUPLICATE_LIST_MEMBER")


def _version(value: dict) -> None:
    _require(value["schema_version"] == SCHEMA_VERSION, "SCHEMA_VERSION_MISMATCH")


def _parse_identity(identity: Any) -> None:
    o = _shape(identity, {"tenant_id", "principal_id", "auth_context_sha256", "authenticated"})
    for k in ("tenant_id", "principal_id"):
        _str(o[k], "BAD_IDENTITY", 128)
    _sha(o["auth_context_sha256"])
    _require(o["authenticated"] is True, "NOT_AUTHENTICATED")


def _parse_question(question: Any) -> None:
    o = _shape(question, {
        "text", "language", "task_kind", "intent_id", "obligations",
        "negated", "numeric_literals", "temporal_scope", "answer_type",
    })
    _str(o["text"], "BAD_QUESTION", 16000)
    _str(o["language"], "BAD_LANGUAGE", 40)
    _str(o["task_kind"], "BAD_TASK_KIND", 32)
    _str(o["intent_id"], "BAD_INTENT", 256)
    _strings(o["obligations"], name="BAD_OBLIGATIONS")
    _require(type(o["negated"]) is bool, "BAD_NEGATION")
    _strings(o["numeric_literals"], name="BAD_NUMBERS")
    _require(o["temporal_scope"] in ("STATIC", "POINT_IN_TIME", "RELATIVE", "LIVE"),
             "BAD_TEMPORAL_SCOPE")
    _require(o["answer_type"] in ("FACT", "EXPLANATION", "COMPARISON", "OTHER"),
             "BAD_ANSWER_TYPE")


def _parse_source(source: Any) -> None:
    o = _shape(source, {
        "corpus_id", "corpus_revision", "corpus_sha256", "source_manifest_sha256",
        "acl_sha256", "rights_sha256", "source_ids",
    })
    for k in ("corpus_id", "corpus_revision"):
        _str(o[k], "BAD_SOURCE", 256)
    for k in ("corpus_sha256", "source_manifest_sha256", "acl_sha256", "rights_sha256"):
        _sha(o[k])
    _strings(o["source_ids"], name="BAD_SOURCE_IDS", limit=256)
    _require(len(o["source_ids"]) > 0, "SOURCE_REQUIRED")


def _parse_policy(policy: Any) -> None:
    o = _shape(policy, {
        "policy_version", "policy_sha256", "verifier_version",
        "embedding_version", "admission_version", "revocation_epoch",
    })
    for k in ("policy_version", "verifier_version", "embedding_version", "admission_version"):
        _str(o[k], "BAD_POLICY_VERSION", 128)
    _sha(o["policy_sha256"])
    _require(type(o["revocation_epoch"]) is int and o["revocation_epoch"] >= 0,
             "BAD_REVOCATION_EPOCH")


def _parse_cache_window(window: Any) -> None:
    o = _shape(window, {"requested_at", "ttl_seconds"})
    _time(o["requested_at"])
    _require(type(o["ttl_seconds"]) is int and 1 <= o["ttl_seconds"] <= MAX_TTL_SECONDS,
             "BAD_TTL")


def parse_public_cache_choice(value: Any) -> str:
    """Untrusted public UI extension ONLY; never accepts ACL/policy/tenant from caller."""
    body = _shape(value, {"cache_mode"})
    _require(type(body["cache_mode"]) is str and body["cache_mode"] in CACHE_MODES,
             "INVALID_CACHE_MODE")
    return body["cache_mode"]


def parse_internal_request(value: Any) -> dict:
    """Only an authenticated native server may construct this envelope."""
    o = _shape(value, {
        "schema_version", "request_id", "cache_mode", "identity",
        "question", "source", "policy", "cache_window",
    })
    _version(o)
    _str(o["request_id"], "BAD_REQUEST_ID", 128)
    parse_public_cache_choice({"cache_mode": o["cache_mode"]})
    _parse_identity(o["identity"])
    _parse_question(o["question"])
    _parse_source(o["source"])
    _parse_policy(o["policy"])
    _parse_cache_window(o["cache_window"])
    return o


def plan_cache_request(request: dict, *, feature_enabled: bool = DEFAULT_NONPROD_CACHE_ENABLED) -> str:
    """The only executable routing preflight. Does not call a store."""
    o = parse_internal_request(request)
    _require(type(feature_enabled) is bool, "FEATURE_FLAG_MUST_BE_BOOLEAN")
    if o["cache_mode"] == "BYPASS":
        return "BYPASSED"
    if not feature_enabled:
        return "DISABLED"
    if o["question"]["task_kind"] != "QA":
        return "REFUSED_NON_QA"
    if o["question"]["temporal_scope"] in ("RELATIVE", "LIVE"):
        return "REFUSED_NON_QA"  # dynamic query is intentionally not reusable
    if o["cache_mode"] == "REFRESH":
        return "REGENERATE_NO_LOOKUP"
    return "LOOKUP_REQUIRED"


@dataclass(frozen=True, slots=True)
class CacheOperationPolicy:
    """Non-authorizing plan for H02/CACHE02/03/05.

    True candidate flags describe required future gating; these are not I/O
    permissions or evidence that authentication, rights and verifier ran.
    """
    decision: str
    cache_mode: str
    feature_enabled: bool
    candidate_lookup_after_authority: bool
    candidate_write_after_qualified_final: bool
    candidate_atomic_replace_after_qualified_final: bool
    requires_current_auth_source_acl: bool = True
    actual_store_io_authorized: bool = False


def describe_cache_operations(
    request: dict, *, feature_enabled: bool = DEFAULT_NONPROD_CACHE_ENABLED
) -> CacheOperationPolicy:
    """Distinguish possible downstream operations without granting I/O.

    An integrator must never call a store from this plan alone. A fresh,
    independently qualified authorization and source/rights snapshot is
    mandatory before every lookup or write, in addition to final verification.
    """
    decision = plan_cache_request(request, feature_enabled=feature_enabled)
    mode = request["cache_mode"]
    return CacheOperationPolicy(
        decision=decision,
        cache_mode=mode,
        feature_enabled=feature_enabled,
        candidate_lookup_after_authority=decision == "LOOKUP_REQUIRED",
        candidate_write_after_qualified_final=decision in (
            "LOOKUP_REQUIRED", "REGENERATE_NO_LOOKUP"
        ),
        candidate_atomic_replace_after_qualified_final=(
            decision == "REGENERATE_NO_LOOKUP"
        ),
    )


def parse_candidate(value: Any) -> dict:
    """A cache record is UNTRUSTED, including when fetched from a local store."""
    o = _shape(value, {
        "schema_version", "identity", "question", "source", "policy",
        "lifecycle", "answer", "citations", "provenance",
    })
    _version(o)
    _parse_identity(o["identity"])
    _parse_question(o["question"])
    _parse_source(o["source"])
    _parse_policy(o["policy"])
    life = _shape(o["lifecycle"], {
        "created_at", "expires_at", "ttl_seconds", "revocation_epoch", "state",
    })
    created, expires = _time(life["created_at"]), _time(life["expires_at"])
    _require(type(life["ttl_seconds"]) is int and 1 <= life["ttl_seconds"] <= MAX_TTL_SECONDS,
             "BAD_CANDIDATE_TTL")
    _require(dt.timedelta(0) < expires - created <= dt.timedelta(seconds=life["ttl_seconds"]),
             "BAD_EXPIRY_BOUND")
    _require(type(life["revocation_epoch"]) is int and life["revocation_epoch"] >= 0,
             "BAD_CANDIDATE_EPOCH")
    _require(life["state"] in ("ACTIVE", "REVOKED"), "BAD_CANDIDATE_STATE")
    _str(o["answer"], "BAD_CACHED_ANSWER", 64000)
    _require(type(o["citations"]) is list and 0 < len(o["citations"]) <= 64, "CITATIONS_REQUIRED")
    for item in o["citations"]:
        binding = _shape(item, {"source_id", "source_sha256", "revision", "citation_sha256"})
        for key in ("source_id", "revision"):
            _str(binding[key], "BAD_CITATION")
        for key in ("source_sha256", "citation_sha256"):
            _sha(binding[key])
        _require(binding["source_id"] in o["source"]["source_ids"], "UNBOUND_CITATION")
    prov = _shape(o["provenance"], {
        "answer_sha256", "final_verifier_receipt_sha256",
        "source_verifier_receipt_sha256", "rights_receipt_sha256",
        "qualification_class",
    })
    for k in ("answer_sha256", "final_verifier_receipt_sha256",
              "source_verifier_receipt_sha256", "rights_receipt_sha256"):
        _sha(prov[k])
    _require(prov["qualification_class"] in ("PROVIDER_QUALIFIED", "FIXTURE_ONLY"),
             "BAD_QUALIFICATION")
    _require(hashlib.sha256(o["answer"].encode("utf-8")).hexdigest()
             == prov["answer_sha256"], "ANSWER_HASH_MISMATCH")
    return o


def screen_candidate(request: dict, candidate: Any, *, now: dt.datetime | None = None) -> str:
    """Deterministic prefilter only. A pass is NEVER proof of a semantic HIT."""
    r = parse_internal_request(request)
    try:
        c = parse_candidate(candidate)
    except CacheContractError:
        return "DENY_CANDIDATE"
    if plan_cache_request(r, feature_enabled=True) != "LOOKUP_REQUIRED":
        return "DENY_CANDIDATE"
    for key in ("identity", "source", "policy"):
        if c[key] != r[key]:
            return "DENY_CANDIDATE"
    q, cq = r["question"], c["question"]
    for key in ("language", "task_kind", "intent_id", "obligations", "negated",
                "numeric_literals", "temporal_scope", "answer_type"):
        if q[key] != cq[key]:
            return "DENY_CANDIDATE"
    if q["temporal_scope"] in ("RELATIVE", "LIVE"):
        return "DENY_CANDIDATE"
    life = c["lifecycle"]
    if life["state"] != "ACTIVE" or life["revocation_epoch"] != r["policy"]["revocation_epoch"]:
        return "DENY_CANDIDATE"
    instant = now if now is not None else dt.datetime.now(_UTC)
    _require(isinstance(instant, dt.datetime) and instant.tzinfo is not None
             and instant.utcoffset() == dt.timedelta(0), "TRUSTED_UTC_TIME_REQUIRED")
    if not (_time(life["created_at"]) <= instant < _time(life["expires_at"])):
        return "DENY_CANDIDATE"
    # Similar embeddings, lexical differences, or matching intent IDs are NOT an HIT.
    return "PROVER_REQUIRED"


def parse_qualified_proof(value: Any, request: dict, *, kind: str) -> dict:
    """Evidence envelope only. H01/H02 must still authenticate its issuer/signature."""
    r = parse_internal_request(request)
    p = _shape(value, {
        "schema_version", "kind", "request_id", "qualification_class", "qualified",
        "semantic_equivalent", "rights_current", "acl_current", "source_current",
        "citations_current", "policy_current", "verifier_receipt_sha256",
        "source_manifest_sha256", "checked_at",
    })
    _version(p)
    _require(p["kind"] == kind and kind in ("HIT_REVALIDATION", "FINAL_WRITE"),
             "PROOF_KIND_MISMATCH")
    _require(p["request_id"] == r["request_id"], "PROOF_REQUEST_MISMATCH")
    _require(p["qualification_class"] in ("FORMAL_PRODUCT", "FIXTURE_ONLY"),
             "BAD_PROOF_CLASS")
    _sha(p["verifier_receipt_sha256"])
    _sha(p["source_manifest_sha256"])
    _require(p["source_manifest_sha256"] == r["source"]["source_manifest_sha256"],
             "PROOF_SOURCE_MISMATCH")
    _time(p["checked_at"])
    for flag in ("qualified", "semantic_equivalent", "rights_current", "acl_current",
                 "source_current", "citations_current", "policy_current"):
        _require(p[flag] is True, "UNVERIFIED_PROOF_" + flag.upper())
    return p


def verify_hit_contract(
    request: dict, candidate: Any, proof: Any,
    *, trusted_issuer_check: Callable[[Mapping[str, Any]], bool] | None = None,
    now: dt.datetime | None = None,
) -> str:
    """Fail shut until H01 installs an independently authenticated verifier."""
    if screen_candidate(request, candidate, now=now) != "PROVER_REQUIRED":
        return "DENY_CANDIDATE"
    try:
        p = parse_qualified_proof(proof, request, kind="HIT_REVALIDATION")
    except CacheContractError:
        return "HIT_NOT_ADMITTED"
    if p["qualification_class"] != "FORMAL_PRODUCT":
        return "VERIFIED_FIXTURE_ONLY"
    if trusted_issuer_check is None or trusted_issuer_check(p) is not True:
        return "HIT_NOT_ADMITTED"
    # Even authenticated proof is not publishable until H01/02 independently
    # bind complete source/citation/answer semantics. This module never returns HIT.
    return "HIT_NOT_ADMITTED"


def qualify_final_write(
    request: dict, proof: Any, *, trusted_issuer_check: Callable[[Mapping[str, Any]], bool] | None = None,
) -> str:
    """REFRESH replacement and AUTO-miss insertion are held at external verifier gate."""
    r = parse_internal_request(request)
    if plan_cache_request(r, feature_enabled=True) not in ("LOOKUP_REQUIRED", "REGENERATE_NO_LOOKUP"):
        return "WRITE_NOT_ADMITTED"
    try:
        p = parse_qualified_proof(proof, r, kind="FINAL_WRITE")
    except CacheContractError:
        return "WRITE_NOT_ADMITTED"
    if p["qualification_class"] != "FORMAL_PRODUCT":
        return "VERIFIED_FIXTURE_ONLY"
    if trusted_issuer_check is None or trusted_issuer_check(p) is not True:
        return "WRITE_NOT_ADMITTED"
    # Validation of signed issuer, final citations, revocation, atomic CAS and
    # generation result belongs to CACHE05; no real write is authorized here.
    return "WRITE_NOT_ADMITTED"


class CacheStoreV1(Protocol):
    """CACHE02: durable tenant partition, no raw cross-tenant read."""
    def lookup_candidates(self, request: Mapping[str, Any], *, limit: int) -> list[Mapping[str, Any]]: ...
    def compare_and_swap_verified(self, request: Mapping[str, Any], record: Mapping[str, Any],
                                  *, previous_revision: str | None) -> bool: ...
    def invalidate_reachability(self, *, tenant_id: str, principal_id: str,
                                source_manifest_sha256: str, revocation_epoch: int) -> int: ...


class CacheGateV1(Protocol):
    """CACHE03 + CACHE05: genuine registered issuers, not booleans from clients."""
    def authorize_and_snapshot(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def reverify_hit(self, request: Mapping[str, Any], record: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def verify_final_write(self, request: Mapping[str, Any], final: Mapping[str, Any]) -> Mapping[str, Any]: ...


def build_response_contract(
    request: dict, *, status: str, answer: str | None = None,
    citations: list[dict] | None = None, verifier_receipt_sha256: str | None = None,
) -> dict:
    r = parse_internal_request(request)
    _require(status in DECISIONS, "UNADMITTED_STATUS")
    _require(answer is None and citations is None and verifier_receipt_sha256 is None,
             "NO_CACHE_ANSWER_RELEASE_FROM_CONTRACT_ONLY")
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": r["request_id"],
        "cache_mode": r["cache_mode"],
        "cache_status": status,
        "answer": None,
        "citations": [],
        "verifier_receipt_sha256": None,
        "internal_answer_cache_enabled": False,
        "cache_io_performed": False,
    }
