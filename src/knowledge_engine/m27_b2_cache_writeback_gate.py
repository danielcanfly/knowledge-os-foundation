"""CACHE05 scoped final-write gate. NO product issuer; fixture-only physical CAS.

Only B2-04/H02 may integrate, and H01 must independently qualify signer/source
custody before ANY product write. This module cannot manufacture that authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from knowledge_engine import m27_b0_cache_contracts as abi

UTC = dt.timezone.utc
VERSION = "m27.cache05/final-write-proof/v1"
HASH = re.compile(r"[a-f0-9]{64}\Z")
MAX_PROOF_AGE = dt.timedelta(seconds=60)
_INJECT = re.compile(
    r"ignore (?:all |any )?(?:previous|prior) instructions|"
    r"reveal (?:the )?system prompt|override (?:safety|acl|policy)|"
    r"忽略(?:之前|上面)(?:的)?指令|洩露系統提示", re.I)


def canonical(x: Any) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(x: Any) -> str:
    return hashlib.sha256(canonical(x)).hexdigest()


def sha(x: bytes) -> str:
    return hashlib.sha256(x).hexdigest()


def z(t: dt.datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class WriteReceipt:
    status: str
    request_id: str
    states: tuple[str, ...]
    fixture_only: bool = True
    product_write_admitted: bool = False
    product_hit_admitted: bool = False


class FinalWriteGate:
    """Strictly test-only cross-branch CACHE02/CACHE03 physical integration.

    The fixture secret authenticates a TEST verifier's assertion, NOT the truth
    of independent entailment and NOT product signer authorization.
    The private fixture helper in CACHE02 is never exposed as an admitted
    public CacheStoreV1.compare_and_swap_verified implementation.
    """

    def __init__(self, *, store: Any, authority: Any, actor: Any,
                 fixture_verifier_secret: bytes | None = None,
                 fixture_only: bool = False, feature_enabled: bool = False):
        if fixture_only is not True or os.environ.get("M27_CACHE05_FIXTURE_TEST_MODE") != "1":
            raise ValueError("FORMAL_ISSUER_UNAVAILABLE")
        if (type(fixture_verifier_secret) is not bytes or len(fixture_verifier_secret) < 32
                or type(feature_enabled) is not bool):
            raise ValueError("FIXTURE_VERIFIER_KEY_REQUIRED")
        if (not getattr(store, "_fixture_only", False)
                or not getattr(store, "feature_enabled", False)
                or authority.__class__.__name__ != "FixtureAuthority"):
            raise ValueError("NONPROD_STORE_AND_AUTHORITY_REQUIRED")
        self.store = store
        self.authority = authority
        self.actor = actor
        self._test_secret = fixture_verifier_secret
        self.feature_enabled = feature_enabled

    @staticmethod
    def product_write(*_args: Any, **_kwargs: Any) -> WriteReceipt:
        return WriteReceipt("FORMAL_ADMISSION_HOLD", "", ("PRODUCT_GATE_OFF",))

    def _verify(self, request: dict, final: Any, proof: Any, source_bytes: Any,
                bindings: dict, snapshot: str, now: dt.datetime) -> None:
        if type(final) is not dict or set(final) != {"answer", "citations", "claims"}:
            raise ValueError("INVALID_FINAL_SHAPE")
        answer, citations, claims = final["answer"], final["citations"], final["claims"]
        if type(answer) is not str or not answer.strip() or len(answer) > 64000:
            raise ValueError("INVALID_FINAL_ANSWER")
        if type(citations) is not list or not citations or len(citations) > 64:
            raise ValueError("MISSING_CITATIONS")
        if type(claims) is not list or not claims or len(claims) > 128:
            raise ValueError("MISSING_CLAIMS")
        if _INJECT.search(answer) or _INJECT.search(request["question"]["text"]):
            raise ValueError("INJECTION_PATTERN_IN_FINAL")
        if type(source_bytes) is not dict or set(source_bytes) != set(request["source"]["source_ids"]):
            raise ValueError("UNTRUSTED_SOURCE_SNAPSHOT")
        for cid, data in source_bytes.items():
            if type(data) is not bytes or len(data) > 1024 * 1024 or not data:
                raise ValueError("INVALID_SOURCE_BYTES")
            if sha(data) != bindings[cid]["source_sha256"]:
                raise ValueError("IMMUTABLE_SOURCE_SHA_MISMATCH")
            if _INJECT.search(data.decode("utf-8", errors="replace")):
                raise ValueError("INJECTION_PATTERN_IN_SOURCE")
        if len({c["source_id"] for c in citations if type(c) is dict and "source_id" in c}) != len(citations):
            raise ValueError("DUPLICATE_OR_BAD_CITATION")
        if any(type(c) is not dict or c != bindings.get(c.get("source_id")) for c in citations):
            raise ValueError("CITATION_RIGHTS_BINDING_FAILED")
        if type(proof) is not dict or set(proof) != {
            "schema_version", "qualification_class", "issuer_id", "generator_id",
            "verifier_id", "request_id", "request_sha256", "final_sha256",
            "auth_context_sha256", "source_manifest_sha256", "rights_snapshot_sha256",
            "source_bytes_sha256", "checked_at", "expires_at", "claims", "obligations",
            "signature"
        }:
            raise ValueError("PROOF_SHAPE_INVALID")
        if (proof["schema_version"] != VERSION or proof["qualification_class"] != "FIXTURE_ONLY"
                or proof["issuer_id"] != "INDEPENDENT_TEST_FIXTURE_VERIFIER"
                or type(proof["verifier_id"]) is not str or not proof["verifier_id"]
                or type(proof["generator_id"]) is not str or not proof["generator_id"]
                or proof["verifier_id"] == proof["generator_id"]):
            raise ValueError("ISSUER_NOT_QUALIFIED")
        bare = {k: v for k, v in proof.items() if k != "signature"}
        signature = proof["signature"]
        expected = hmac.new(self._test_secret, canonical(bare), hashlib.sha256).hexdigest()
        if type(signature) is not str or not hmac.compare_digest(signature, expected):
            raise ValueError("PROOF_SIGNATURE_INVALID")
        if (proof["request_id"] != request["request_id"]
                or proof["request_sha256"] != digest(request)
                or proof["final_sha256"] != digest(final)
                or proof["auth_context_sha256"] != request["identity"]["auth_context_sha256"]
                or proof["source_manifest_sha256"] != request["source"]["source_manifest_sha256"]
                or proof["rights_snapshot_sha256"] != sha(snapshot.encode())
                or proof["source_bytes_sha256"] != digest({s: sha(b) for s, b in source_bytes.items()})):
            raise ValueError("PROOF_BOUND_CONTEXT_STALE")
        checked, expiry = abi._time(proof["checked_at"]), abi._time(proof["expires_at"])
        if not (checked <= now < expiry and now - checked <= MAX_PROOF_AGE
                and dt.timedelta(0) < expiry - checked <= MAX_PROOF_AGE):
            raise ValueError("PROOF_EXPIRED_OR_FUTURE")
        if proof["claims"] != claims:
            raise ValueError("CLAIM_PROOF_NOT_BOUND")
        if type(proof["obligations"]) is not list:
            raise ValueError("OBLIGATIONS_MISSING")
        required = request["question"]["obligations"]
        claims_by_id: dict[str, dict] = {}
        used_cites = set()
        for claim in claims:
            if type(claim) is not dict or set(claim) != {
                "id", "text", "text_sha256", "verdict", "evidence_spans"
            }:
                raise ValueError("CLAIM_SHAPE_INVALID")
            label, text = claim["id"], claim["text"]
            if (type(label) is not str or not label or label in claims_by_id
                    or type(text) is not str or not text or text not in answer
                    or claim["text_sha256"] != sha(text.encode())
                    or claim["verdict"] != "ENTAILED"):
                raise ValueError("CLAIM_UNSUPPORTED_OR_DUPLICATE")
            spans = claim["evidence_spans"]
            if type(spans) is not list or not spans or len(spans) > 32:
                raise ValueError("CLAIM_MISSING_SOURCE_SPANS")
            for span in spans:
                if type(span) is not dict or set(span) != {
                    "source_id", "start", "end", "excerpt_sha256"
                }:
                    raise ValueError("SPAN_MALFORMED")
                sid, start, end = span["source_id"], span["start"], span["end"]
                if (sid not in source_bytes or type(start) is not int or type(end) is not int
                        or not 0 <= start < end <= len(source_bytes[sid])):
                    raise ValueError("SPAN_OUT_OF_BOUNDS")
                chunk = source_bytes[sid][start:end]
                if (sha(chunk) != span["excerpt_sha256"]
                        or sha(chunk) != bindings[sid]["citation_sha256"]):
                    raise ValueError("SPAN_EVIDENCE_MUTATED")
                used_cites.add(sid)
            claims_by_id[label] = claim
        if used_cites != {c["source_id"] for c in citations}:
            raise ValueError("UNCLAIMED_OR_UNCITED_SOURCE")
        if len(proof["obligations"]) != len(required):
            raise ValueError("OBLIGATION_COUNT")
        found = set()
        for ob in proof["obligations"]:
            if type(ob) is not dict or set(ob) != {"name", "verdict", "claim_ids"}:
                raise ValueError("OBLIGATION_SHAPE")
            if (ob["name"] not in required or ob["name"] in found
                    or ob["verdict"] != "SATISFIED" or type(ob["claim_ids"]) is not list
                    or not ob["claim_ids"] or not set(ob["claim_ids"]) <= claims_by_id.keys()):
                raise ValueError("OBLIGATION_UNSATISFIED")
            found.add(ob["name"])
        if found != set(required):
            raise ValueError("MISSING_QUESTION_OBLIGATION")
        # A signed TEST attestation is no substitute for a real claim verifier.

    def admit_fixture(self, request: dict, final: Any, proof: Any, *,
                      source_bytes: dict[str, bytes], now: dt.datetime,
                      previous_revision: str | None = None,
                      after_verifier: Callable[[], None] | None = None,
                      fail_at: str | None = None) -> WriteReceipt:
        stages = ["CANDIDATE"]
        request_id = request.get("request_id", "") if type(request) is dict else ""
        def receipt(status: str) -> WriteReceipt:
            return WriteReceipt(status, request_id, tuple(stages))
        try:
            r = abi.parse_internal_request(request)
            if not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
                raise ValueError("TRUSTED_UTC_CLOCK_REQUIRED")
            decision = abi.plan_cache_request(r, feature_enabled=self.feature_enabled)
            if decision != "LOOKUP_REQUIRED" and decision != "REGENERATE_NO_LOOKUP":
                stages.append("ZERO_CACHE_IO")
                return receipt(decision)
            if not self.store._fixture_only:
                raise ValueError("STORE_NOT_FIXTURE_SCOPED")
            snapshot, bindings = self.authority.snapshot(r, actor=self.actor, now=now)
            stages.append("CURRENT_SOURCE_ACL_CONSENT")
            self._verify(r, final, proof, source_bytes, bindings, snapshot, now)
            stages.append("INDEPENDENT_TEST_FIXTURE_PROOF")
            if after_verifier is not None:
                after_verifier()
            if not self.authority.is_unchanged(r, actor=self.actor, now=now,
                                               fingerprint=snapshot):
                stages.append("REVOCATION_OR_SOURCE_RACE_DENIED")
                return receipt("RIGHTS_CHANGED")
            stages.append("RIGHTS_RECHECK")
            ttl = r["cache_window"]["ttl_seconds"]
            remaining = int((abi._time(proof["expires_at"]) - now).total_seconds())
            lifetime = min(ttl - 1, remaining - 1)
            if lifetime < 1:
                raise ValueError("TTL_NOT_FRESH")
            record = {
                "schema_version": abi.SCHEMA_VERSION,
                "identity": r["identity"], "question": r["question"], "source": r["source"],
                "policy": r["policy"],
                "lifecycle": {"created_at": z(now), "expires_at": z(now + dt.timedelta(seconds=lifetime)),
                              "ttl_seconds": ttl, "revocation_epoch": r["policy"]["revocation_epoch"],
                              "state": "ACTIVE"},
                "answer": final["answer"], "citations": final["citations"],
                "provenance": {
                    "answer_sha256": sha(final["answer"].encode()),
                    "final_verifier_receipt_sha256": digest(proof),
                    "source_verifier_receipt_sha256": digest({s: sha(b) for s, b in source_bytes.items()}),
                    "rights_receipt_sha256": sha(snapshot.encode()),
                    "qualification_class": "FIXTURE_ONLY",
                },
            }
            abi.parse_candidate(record)
            stages.append("ATOMIC_CAS_ATTEMPT")
            committed = self.store._fixture_cas(
                r, record, previous_revision=previous_revision, now=now, fail_at=fail_at)
            if not committed:
                stages.append("CAS_CONFLICT_OR_REVOKED")
                return receipt("CAS_NOT_COMMITTED")
            stages.append("FIXTURE_CAS_COMMITTED")
            if not self.authority.is_unchanged(r, actor=self.actor, now=now,
                                               fingerprint=snapshot):
                # Separate fixture authorities are not distributed atomic custody.
                self.store._fixture_invalidate(
                    tenant_id=r["identity"]["tenant_id"],
                    principal_id=r["identity"]["principal_id"],
                    source_manifest_sha256=r["source"]["source_manifest_sha256"],
                    revocation_epoch=r["policy"]["revocation_epoch"] + 1)
                stages.append("POST_COMMIT_REVOKE_INVALIDATION")
                return receipt("RIGHTS_CHANGED_POST_COMMIT")
            stages.append("FIXTURE_ONLY_NEVER_HIT")
            return receipt("FIXTURE_WRITE_COMMITTED")
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
            stages.append("FAIL_CLOSED_" + type(exc).__name__)
            return receipt("WRITE_DENIED")
        except Exception:
            stages.append("FAIL_CLOSED_EXCEPTION")
            return receipt("WRITE_DENIED")
