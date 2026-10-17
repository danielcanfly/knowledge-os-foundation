"""B1 CACHE03 isolated, default-OFF cache eligibility and local revocation guard.

The durable SQLite file is a LOCAL FIXTURE AUTHORITY, never Product IAM.
No result grants an HIT, writes a cache record or supplies a user-facing answer.
Independent source/issuer custody must be installed by H01/H02 before release.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from knowledge_engine import m27_b0_cache_contracts as abi

UTC = dt.timezone.utc
PROOF_SCHEMA = "m27.cache03/claim-proof/v1"
_NEG = re.compile(r"\b(?:not|no|never|without|isn't|aren't|doesn't|don't|cannot|can't|未|不|無|没有|沒有|不是)\b", re.I)
_NUMBER = re.compile(r"(?<![\w])(?:[$€¥₫£]\s*)?-?\d+(?:[.,]\d+)*(?:\s*%)?(?![\w])")
_CURRENCY = re.compile(r"\b(?:USD|SGD|TWD|NTD|VND|EUR|JPY|CNY|HKD|GBP|RMB)\b|[$€¥₫£]", re.I)
_DYNAMIC = re.compile(r"\b(?:today|yesterday|tomorrow|current(?:ly)?|latest|now|live|this week|last week|next week)\b|今天|昨天|明天|目前|現在|最新")
_INJECT = re.compile(r"ignore (?:all |any )?(?:previous|prior) instructions|system prompt|developer message|override (?:safety|acl|policy)|忽略(?:之前|上面)(?:的)?指令", re.I)
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def when(s: str) -> dt.datetime:
    if type(s) is not str or not s.endswith("Z"):
        raise ValueError("INVALID_UTC_TIMESTAMP")
    try:
        t = dt.datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("INVALID_UTC_TIMESTAMP") from exc
    if t.utcoffset() != dt.timedelta(0):
        raise ValueError("INVALID_UTC_TIMESTAMP")
    return t


def clock(t: dt.datetime) -> dt.datetime:
    if not isinstance(t, dt.datetime) or t.tzinfo is None or t.utcoffset() != dt.timedelta(0):
        raise ValueError("TRUSTED_UTC_TIME_REQUIRED")
    return t


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    principal_id: str
    actor_id: str
    auth_context_sha256: str
    authenticated: bool
    issuer: str


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    fixture_only: bool = True
    cache_hit_admitted: bool = False
    store_write_admitted: bool = False


def deny(reason: str) -> Decision:
    return Decision("DENY_CANDIDATE", reason)


class FixtureAuthority:
    """Separately persisted monotonic local authority. Only fixture provisioning.

    Restored artifact bytes cannot lower epochs because authority lives in its
    own file. Restoring THIS file too is outside this contract, and must HOLD.
    """

    def __init__(self, authority_file: str | Path, *, fixture_only: bool):
        if fixture_only is not True:
            raise ValueError("EXTERNAL_AUTHORITY_NOT_IMPLEMENTED")
        self.path = Path(authority_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS rights (
                tenant TEXT NOT NULL, principal TEXT NOT NULL, source_id TEXT NOT NULL,
                identity_sha TEXT NOT NULL, source_json TEXT NOT NULL,
                policy_json TEXT NOT NULL, bindings_json TEXT NOT NULL,
                consent_until TEXT NOT NULL, generation INTEGER NOT NULL,
                status TEXT NOT NULL, acl INTEGER NOT NULL, consent INTEGER NOT NULL,
                PRIMARY KEY(tenant, principal, source_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                tenant TEXT NOT NULL, principal TEXT NOT NULL, source_id TEXT NOT NULL,
                event_id TEXT NOT NULL, kind TEXT NOT NULL, generation INTEGER NOT NULL,
                event_sha TEXT NOT NULL,
                PRIMARY KEY(tenant,principal,source_id,event_id))""")

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA journal_mode=DELETE")
        return db

    @staticmethod
    def _actor(request: Mapping[str, Any], actor: Actor) -> None:
        i = request["identity"]
        if (type(actor) is not Actor or actor.authenticated is not True
            or actor.tenant_id != i["tenant_id"]
            or actor.principal_id != i["principal_id"]
            or actor.actor_id != i["principal_id"]
            or actor.auth_context_sha256 != i["auth_context_sha256"]
            or not actor.issuer):
            raise ValueError("ACTOR_NOT_INDEPENDENTLY_AUTHENTICATED")

    @staticmethod
    def _fixture(confirmed: bool) -> None:
        if confirmed is not True:
            raise ValueError("FIXTURE_PROVISION_NOT_AUTHORIZED")

    def provision_fixture(self, request: dict, *, actor: Actor,
                          bindings: list[dict], consent_until: str,
                          authorized_fixture: bool) -> None:
        self._fixture(authorized_fixture)
        r = abi.parse_internal_request(request)
        self._actor(r, actor)
        if when(consent_until) <= when(r["cache_window"]["requested_at"]):
            raise ValueError("CONSENT_EXPIRED")
        required = set(r["source"]["source_ids"])
        by_id: dict[str, dict] = {}
        for b in bindings:
            if type(b) is not dict or set(b) != {"source_id", "source_sha256", "revision", "citation_sha256"}:
                raise ValueError("INVALID_SOURCE_BINDING")
            if b["source_id"] in by_id or b["source_id"] not in required or any(
                type(b[k]) is not str or not _SHA.fullmatch(b[k])
                for k in ("source_sha256", "citation_sha256")
            ) or b["revision"] != r["source"]["corpus_revision"]:
                raise ValueError("INVALID_SOURCE_BINDING")
            by_id[b["source_id"]] = b
        if set(by_id) != required:
            raise ValueError("INCOMPLETE_SOURCE_AUTHORITY")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for source_id, binding in by_id.items():
                    db.execute("""INSERT INTO rights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        r["identity"]["tenant_id"], r["identity"]["principal_id"], source_id,
                        digest(r["identity"]), json.dumps(r["source"], sort_keys=True),
                        json.dumps(r["policy"], sort_keys=True), json.dumps(binding, sort_keys=True),
                        consent_until, r["policy"]["revocation_epoch"], "ACTIVE", 1, 1))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _rows(self, request: dict, actor: Actor, now: dt.datetime) -> list[sqlite3.Row]:
        self._actor(request, actor)
        rows = []
        with self._db() as db:
            db.execute("BEGIN")
            try:
                for source_id in request["source"]["source_ids"]:
                    row = db.execute("""SELECT * FROM rights WHERE tenant=? AND principal=? AND source_id=?""",
                        (actor.tenant_id, actor.principal_id, source_id)).fetchone()
                    if row is None:
                        raise ValueError("SOURCE_AUTHORITY_MISSING")
                    if row["status"] != "ACTIVE" or row["acl"] != 1 or row["consent"] != 1:
                        raise ValueError("SOURCE_REVOKED_DELETED_OR_ACL_DOWN")
                    if not when(row["consent_until"]) > now:
                        raise ValueError("CONSENT_EXPIRED")
                    if row["identity_sha"] != digest(request["identity"]):
                        raise ValueError("AUTH_SCOPE_CHANGED")
                    if json.loads(row["source_json"]) != request["source"]:
                        raise ValueError("SOURCE_REVISION_OR_RIGHTS_CHANGED")
                    if json.loads(row["policy_json"]) != request["policy"]:
                        raise ValueError("POLICY_OR_EPOCH_CHANGED")
                    if row["generation"] != request["policy"]["revocation_epoch"]:
                        raise ValueError("AUTHORITY_EPOCH_CHANGED")
                    rows.append(row)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return rows

    def snapshot(self, request: dict, *, actor: Actor, now: dt.datetime) -> tuple[str, dict[str, dict]]:
        r = abi.parse_internal_request(request)
        rows = self._rows(r, actor, clock(now))
        bindings = {row["source_id"]: json.loads(row["bindings_json"]) for row in rows}
        # Fingerprint every authoritative field, including rights generation/status.
        fingerprint = digest([dict(row) for row in rows])
        return fingerprint, bindings

    def is_unchanged(self, request: dict, *, actor: Actor,
                     now: dt.datetime, fingerprint: str) -> bool:
        try:
            new, _ = self.snapshot(request, actor=actor, now=now)
            return new == fingerprint
        except (ValueError, abi.CacheContractError, sqlite3.Error):
            return False

    def mutate_fixture(self, *, tenant: str, principal: str, source_id: str,
                       event_id: str, kind: str, actor: Actor,
                       authorized_fixture: bool) -> int:
        self._fixture(authorized_fixture)
        if (type(actor) is not Actor or not actor.authenticated or
            actor.tenant_id != tenant or actor.principal_id != principal or
            actor.actor_id != principal or not actor.issuer):
            raise ValueError("INVALID_MUTATION_ACTOR")
        if kind not in {"REVOKE", "DELETE", "ACL_DOWN", "CONSENT_WITHDRAW"}:
            raise ValueError("INVALID_MUTATION_KIND")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 128:
            raise ValueError("INVALID_EVENT_ID")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = db.execute("""SELECT kind,generation FROM events
                    WHERE tenant=? AND principal=? AND source_id=? AND event_id=?""",
                    (tenant, principal, source_id, event_id)).fetchone()
                if previous is not None:
                    if previous["kind"] != kind:
                        raise ValueError("EVENT_REUSE_CONFLICT")
                    db.execute("COMMIT")
                    return previous["generation"]
                row = db.execute("""SELECT * FROM rights WHERE tenant=? AND principal=? AND source_id=?""",
                    (tenant, principal, source_id)).fetchone()
                if row is None:
                    raise ValueError("UNKNOWN_SCOPE")
                gen = row["generation"] + 1
                status = "DELETED" if kind == "DELETE" else ("REVOKED" if kind == "REVOKE" else row["status"])
                consent = 0 if kind == "CONSENT_WITHDRAW" else row["consent"]
                db.execute("""UPDATE rights SET generation=?,status=?,acl=0,consent=?
                    WHERE tenant=? AND principal=? AND source_id=?""",
                    (gen, status, consent, tenant, principal, source_id))
                db.execute("""INSERT INTO events VALUES (?,?,?,?,?,?,?)""", (
                    tenant, principal, source_id, event_id, kind, gen,
                    digest([tenant, principal, source_id, event_id, kind, gen])))
                db.execute("COMMIT")
                return gen
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def update_source_fixture(self, prior_request: dict, new_request: dict, *,
                              actor: Actor, authorized_fixture: bool) -> None:
        """Atomic source/policy revision change, never resurrects revoked sources."""
        self._fixture(authorized_fixture)
        old = abi.parse_internal_request(prior_request)
        new = abi.parse_internal_request(new_request)
        self._actor(old, actor)
        self._actor(new, actor)
        if (old["identity"] != new["identity"] or
            old["source"]["source_ids"] != new["source"]["source_ids"] or
            new["policy"]["revocation_epoch"] != old["policy"]["revocation_epoch"] + 1 or
            old["source"] == new["source"]):
            raise ValueError("INVALID_SOURCE_REVISION_CHANGE")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for source_id in old["source"]["source_ids"]:
                    row = db.execute("""SELECT * FROM rights WHERE
                        tenant=? AND principal=? AND source_id=?""",
                        (actor.tenant_id, actor.principal_id, source_id)).fetchone()
                    if (row is None or row["status"] != "ACTIVE" or row["acl"] != 1
                        or row["consent"] != 1 or row["generation"] != old["policy"]["revocation_epoch"]
                        or json.loads(row["source_json"]) != old["source"]
                        or json.loads(row["policy_json"]) != old["policy"]):
                        raise ValueError("STALE_SOURCE_CAS_OR_REVOKED")
                    # Source bytes/citations require NEW external custody. Never
                    # promote stale binding hashes from the previous revision.
                    db.execute("""UPDATE rights SET generation=?,source_json=?,policy_json=?,
                        status='SOURCE_REFRESH_PENDING',acl=0
                        WHERE tenant=? AND principal=? AND source_id=?""", (
                        new["policy"]["revocation_epoch"], json.dumps(new["source"],sort_keys=True),
                        json.dumps(new["policy"],sort_keys=True), actor.tenant_id,actor.principal_id,source_id))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise


def _semantic_collision(request: dict, candidate: dict) -> str | None:
    q = request["question"]["text"]
    old = candidate["question"]["text"]
    if _DYNAMIC.search(q) or _DYNAMIC.search(old):
        return "DYNAMIC_QUESTION_REQUIRES_LIVE_EVIDENCE"
    if bool(_NEG.search(q)) != bool(_NEG.search(old)):
        return "NEGATION_CONFLICT"
    if sorted(_NUMBER.findall(q)) != sorted(_NUMBER.findall(old)):
        return "NUMBER_CONFLICT"
    if sorted(x.upper() for x in _CURRENCY.findall(q)) != sorted(x.upper() for x in _CURRENCY.findall(old)):
        return "CURRENCY_CONFLICT"
    if _INJECT.search(q) or _INJECT.search(old) or _INJECT.search(candidate["answer"]):
        return "PROMPT_INJECTION_CONTENT"
    return None


def _proof_check(request: dict, candidate: dict, proof: Any, bindings: dict[str, dict],
                 *, now: dt.datetime, trusted_issuer: Callable[[Mapping[str, Any]], bool] | None) -> str:
    if type(proof) is not dict:
        return "MISSING_SEMANTIC_PROOF"
    expected = {"schema_version", "qualification_class", "issuer_id", "verifier_model",
                "generator_model", "request_sha256", "candidate_sha256",
                "question_sha256", "answer_sha256", "source_manifest_sha256",
                "checked_at", "expires_at", "semantic_relation", "claim_coverage",
                "claims", "obligations", "issuer_receipt_sha256"}
    if set(proof) != expected or proof["schema_version"] != PROOF_SCHEMA:
        return "MALFORMED_PROOF_ENVELOPE"
    if proof["qualification_class"] not in ("FIXTURE_ONLY", "EXTERNAL_QUALIFIED"):
        return "UNQUALIFIED_PROOF_CLASS"
    if (not isinstance(proof["issuer_id"], str) or not proof["issuer_id"]
        or not isinstance(proof["verifier_model"], str) or not proof["verifier_model"]
        or proof["verifier_model"] == proof["generator_model"]):
        return "VERIFIER_NOT_DISTINCT"
    if (proof["request_sha256"] != digest(request) or proof["candidate_sha256"] != digest(candidate)
        or proof["question_sha256"] != digest(request["question"])
        or proof["answer_sha256"] != candidate["provenance"]["answer_sha256"]
        or proof["source_manifest_sha256"] != request["source"]["source_manifest_sha256"]):
        return "STALE_OR_CROSS_REQUEST_PROOF"
    if (proof["semantic_relation"] != "EQUIVALENT" or proof["claim_coverage"] is not True):
        return "SEMANTIC_OR_CLAIM_COVERAGE_FAILED"
    try:
        if not (when(proof["checked_at"]) <= now < when(proof["expires_at"])):
            return "PROOF_TIME_INVALID"
    except (ValueError, TypeError):
        return "PROOF_TIME_INVALID"
    if (type(proof["issuer_receipt_sha256"]) is not str
        or not _SHA.fullmatch(proof["issuer_receipt_sha256"])):
        return "MISSING_ISSUER_RECEIPT"
    claims = proof["claims"]
    obligations = proof["obligations"]
    if type(claims) is not list or not claims or len(claims) > 128 or type(obligations) is not list:
        return "CLAIMS_OR_OBLIGATIONS_MISSING"
    seen = set()
    cited = {digest(c): c for c in candidate["citations"]}
    for claim in claims:
        if type(claim) is not dict or set(claim) != {"id", "text", "text_sha256", "verdict", "citation_sha256s"}:
            return "CLAIM_SHAPE_INVALID"
        if (type(claim["id"]) is not str or not claim["id"] or claim["id"] in seen
            or type(claim["text"]) is not str or not claim["text"]
            or claim["text_sha256"] != hashlib.sha256(claim["text"].encode()).hexdigest()
            or claim["verdict"] != "ENTAILED"):
            return "CLAIM_NOT_ENTAILED"
        seen.add(claim["id"])
        cites = claim["citation_sha256s"]
        if type(cites) is not list or not cites or len(set(cites)) != len(cites):
            return "CLAIM_NO_UNIQUE_CITATIONS"
        if any(k not in cited or cited[k] != bindings.get(cited[k]["source_id"]) for k in cites):
            return "CLAIM_UNTRUSTED_CITATION"
    required = request["question"]["obligations"]
    if len(obligations) != len(required) or {o.get("name") for o in obligations if type(o) is dict} != set(required):
        return "ANSWER_OBLIGATION_MISMATCH"
    for obligation in obligations:
        if type(obligation) is not dict or set(obligation) != {"name", "verdict", "claim_ids"}:
            return "OBLIGATION_SHAPE_INVALID"
        if obligation["verdict"] != "SATISFIED" or type(obligation["claim_ids"]) is not list:
            return "OBLIGATION_UNSATISFIED"
        if not obligation["claim_ids"] or not set(obligation["claim_ids"]) <= seen:
            return "OBLIGATION_CLAIMS_UNBOUND"
    # Neither hashes nor synthetic local data are an independent publisher/issuer.
    if trusted_issuer is None:
        return "INDEPENDENT_ISSUER_UNAVAILABLE"
    try:
        if trusted_issuer(proof) is not True:
            return "INDEPENDENT_ISSUER_REJECTED"
    except Exception:
        return "INDEPENDENT_ISSUER_ERROR"
    if proof["qualification_class"] == "FIXTURE_ONLY":
        return "VERIFIED_FIXTURE_ONLY"
    # External issuer signature, registry, source custody and Product authority
    # are not furnished here. Even a callback cannot grant an actual HIT.
    return "FORMAL_ADMISSION_HOLD"


def evaluate_candidate(request: dict, candidate: Any, proof: Any, *,
                       authority: FixtureAuthority, actor: Actor,
                       now: dt.datetime, feature_enabled: bool = False,
                       trusted_issuer: Callable[[Mapping[str, Any]], bool] | None = None,
                       before_final_authority_check: Callable[[], None] | None = None) -> Decision:
    """Gate candidates with current rights and signed-proof hooks; never release."""
    try:
        r = abi.parse_internal_request(request)
        instant = clock(now)
        plan = abi.plan_cache_request(r, feature_enabled=feature_enabled)
        if plan != "LOOKUP_REQUIRED":
            return Decision("NO_CACHE_IO", plan)
        token, bindings = authority.snapshot(r, actor=actor, now=instant)
        if abi.screen_candidate(r, candidate, now=instant) != "PROVER_REQUIRED":
            return deny("CACHE01_ABI_SCREEN_REJECTED")
        c = abi.parse_candidate(candidate)
        for cited in c["citations"]:
            if bindings.get(cited["source_id"]) != cited:
                return deny("CITATION_NOT_CURRENT")
        collision = _semantic_collision(r, c)
        if collision:
            return deny(collision)
        proof_state = _proof_check(r, c, proof, bindings, now=instant, trusted_issuer=trusted_issuer)
        if before_final_authority_check is not None:
            before_final_authority_check()
        # Fresh authority recheck protects revoke/source-update racing verification.
        if not authority.is_unchanged(r, actor=actor, now=instant, fingerprint=token):
            return deny("AUTHORITY_CHANGED_DURING_VERIFICATION")
        if proof_state == "VERIFIED_FIXTURE_ONLY":
            return Decision("VERIFIED_FIXTURE_ONLY", proof_state)
        return Decision("HIT_NOT_ADMITTED", proof_state)
    except (ValueError, TypeError, KeyError, abi.CacheContractError, sqlite3.Error) as exc:
        return deny(type(exc).__name__ + ":" + str(exc)[:100])
