"""K02D independent feature-off SQLite AR02 writer v1: local ACID, NO provider rights.

This is a new experimental ABI. Synthetic approval references and local HMAC
verifier keys cannot establish external authority, independence or dispatch
permission. In particular this module does NOT send, sign, or grant rights.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class FenceError(ValueError):
    """A stale, inconsistent or unauthorized local transition."""


@dataclass(frozen=True)
class RunIdentity:
    tenant_id: str
    run_id: str
    task_id: str
    task_version: int
    principal_id: str


@dataclass(frozen=True)
class Head:
    seq: int
    digest: str
    epoch: int
    state: str
    budget: int
    reserved: int
    spent: int


def _canonical(data: object) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _nonempty(*values: str) -> None:
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise FenceError("MISSING_IDENTITY_OR_EVIDENCE")


class DurableWriterV1:
    """One SQLite single-writer across connections/processes, never an executor.

    Every write uses BEGIN IMMEDIATE and a full-chain verified CAS in the SAME
    transaction. SQLite WAL+FULL synchronizes commit before returning a local
    acknowledgment. No remote-effect/exactly-once guarantees are asserted.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        fixture_approval_mode: bool = False,
        verifier_keys: Mapping[str, bytes] | None = None,
    ) -> None:
        self.path = Path(path)
        if not self.path.parent.is_dir():
            raise ValueError("database parent must exist")
        self.fixture_approval_mode = fixture_approval_mode
        self._verifier_keys = dict(verifier_keys or {})
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                  tenant TEXT NOT NULL, run TEXT NOT NULL, task TEXT NOT NULL,
                  version INTEGER NOT NULL, principal TEXT NOT NULL,
                  budget INTEGER NOT NULL CHECK(budget >= 0),
                  reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
                  spent INTEGER NOT NULL DEFAULT 0 CHECK(spent >= 0),
                  seq INTEGER NOT NULL DEFAULT 0, digest TEXT NOT NULL,
                  epoch INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'OPEN',
                  source_rev TEXT NOT NULL, consent_gen INTEGER NOT NULL,
                  exclusion_gen INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY(tenant,run)
                );
                CREATE TABLE IF NOT EXISTS events (
                  tenant TEXT NOT NULL, run TEXT NOT NULL, seq INTEGER NOT NULL,
                  kind TEXT NOT NULL, payload TEXT NOT NULL, prev TEXT NOT NULL,
                  digest TEXT NOT NULL, PRIMARY KEY(tenant,run,seq),
                  FOREIGN KEY(tenant,run) REFERENCES runs(tenant,run)
                );
                CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events
                  BEGIN SELECT RAISE(ABORT,'immutable event'); END;
                CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events
                  BEGIN SELECT RAISE(ABORT,'immutable event'); END;
                CREATE TABLE IF NOT EXISTS reservations (
                  tenant TEXT NOT NULL, run TEXT NOT NULL, reserve_id TEXT NOT NULL,
                  amount INTEGER NOT NULL CHECK(amount > 0), charged INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY(tenant,run,reserve_id),
                  FOREIGN KEY(tenant,run) REFERENCES runs(tenant,run)
                );
                CREATE TABLE IF NOT EXISTS charges (
                  charge_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, run TEXT NOT NULL,
                  reserve_id TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount >= 0),
                  FOREIGN KEY(tenant,run,reserve_id)
                    REFERENCES reservations(tenant,run,reserve_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                  approval_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, run TEXT NOT NULL,
                  intent_digest TEXT NOT NULL, principal TEXT NOT NULL, epoch INTEGER NOT NULL,
                  expires_at INTEGER NOT NULL, source_rev TEXT NOT NULL,
                  consent_gen INTEGER NOT NULL, exclusion_gen INTEGER NOT NULL,
                  consumed_by TEXT,
                  FOREIGN KEY(tenant,run) REFERENCES runs(tenant,run)
                );
                CREATE TABLE IF NOT EXISTS intents (
                  intent_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, run TEXT NOT NULL,
                  digest TEXT NOT NULL, approval_id TEXT NOT NULL UNIQUE,
                  claim_id TEXT NOT NULL UNIQUE, reserve_id TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL UNIQUE,
                  FOREIGN KEY(tenant,run) REFERENCES runs(tenant,run)
                );
                CREATE TABLE IF NOT EXISTS outbox (
                  claim_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, run TEXT NOT NULL,
                  intent_id TEXT NOT NULL UNIQUE, epoch INTEGER NOT NULL,
                  state TEXT NOT NULL, ack_token TEXT,
                  FOREIGN KEY(intent_id) REFERENCES intents(intent_id)
                );
                CREATE TABLE IF NOT EXISTS observations (
                  evidence_ref TEXT PRIMARY KEY, tenant TEXT NOT NULL, run TEXT NOT NULL,
                  intent_id TEXT NOT NULL UNIQUE, intent_digest TEXT NOT NULL,
                  observer_id TEXT NOT NULL, evidence_sha TEXT NOT NULL,
                  outcome TEXT NOT NULL, expires_at INTEGER NOT NULL,
                  source_rev TEXT NOT NULL, consent_gen INTEGER NOT NULL,
                  exclusion_gen INTEGER NOT NULL,
                  FOREIGN KEY(intent_id) REFERENCES intents(intent_id)
                );
                CREATE TABLE IF NOT EXISTS adjustments (
                  adjustment_id TEXT PRIMARY KEY, charge_id TEXT NOT NULL,
                  delta INTEGER NOT NULL, evidence_ref TEXT NOT NULL,
                  FOREIGN KEY(charge_id) REFERENCES charges(charge_id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=8)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=8000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _load(self, db: sqlite3.Connection, identity: RunIdentity) -> sqlite3.Row:
        row = db.execute("SELECT * FROM runs WHERE tenant=? AND run=?",
                         (identity.tenant_id, identity.run_id)).fetchone()
        if row is None or (row["task"], row["version"], row["principal"]) != (
            identity.task_id, identity.task_version, identity.principal_id
        ):
            raise FenceError("RUN_IDENTITY_MISMATCH")
        self._verify_chain(db, row)
        return row

    def _verify_chain(self, db: sqlite3.Connection, row: sqlite3.Row) -> None:
        prev = _digest(_canonical([
            "K02D-v1", row["tenant"], row["run"], row["task"],
            row["version"], row["principal"],
        ]))
        events = db.execute(
            "SELECT * FROM events WHERE tenant=? AND run=? ORDER BY seq",
            (row["tenant"], row["run"]),
        ).fetchall()
        for idx, event in enumerate(events, start=1):
            body = _canonical({
                "seq": idx, "kind": event["kind"], "payload": json.loads(event["payload"]),
            })
            wanted = _digest(prev + "|" + body)
            if event["seq"] != idx or event["prev"] != prev or event["digest"] != wanted:
                raise FenceError("CORRUPT_EVENT_HEAD")
            prev = wanted
        if row["seq"] != len(events) or row["digest"] != prev:
            raise FenceError("CORRUPT_EVENT_HEAD")

    def _append(self, db: sqlite3.Connection, row: sqlite3.Row,
                kind: str, payload: dict) -> Head:
        seq = row["seq"] + 1
        digest = _digest(row["digest"] + "|" + _canonical({
            "seq": seq, "kind": kind, "payload": payload,
        }))
        db.execute(
            "INSERT INTO events(tenant,run,seq,kind,payload,prev,digest)"
            " VALUES(?,?,?,?,?,?,?)",
            (row["tenant"], row["run"], seq, kind, _canonical(payload),
             row["digest"], digest),
        )
        db.execute("UPDATE runs SET seq=?,digest=? WHERE tenant=? AND run=?",
                   (seq, digest, row["tenant"], row["run"]))
        fresh = db.execute("SELECT * FROM runs WHERE tenant=? AND run=?",
                           (row["tenant"], row["run"])).fetchone()
        return self._head(fresh)

    @staticmethod
    def _head(row: sqlite3.Row) -> Head:
        return Head(row["seq"], row["digest"], row["epoch"], row["state"],
                    row["budget"], row["reserved"], row["spent"])

    @staticmethod
    def _cas(row: sqlite3.Row, head: Head, *, open_only: bool = True) -> None:
        if (row["seq"], row["digest"], row["epoch"]) != (
            head.seq, head.digest, head.epoch
        ):
            raise FenceError("STALE_HEAD_OR_EPOCH")
        if open_only and row["state"] != "OPEN":
            raise FenceError("IMMUTABLE_TERMINAL")
        if open_only and row["revoked"]:
            raise FenceError("SOURCE_REVOKED")

    @staticmethod
    def _scope(identity: RunIdentity) -> None:
        _nonempty(identity.tenant_id, identity.run_id,
                  identity.task_id, identity.principal_id)
        if identity.task_version < 1:
            raise FenceError("INVALID_TASK_VERSION")

    def create_run(
        self, identity: RunIdentity, *, budget: int, source_revision: str,
        consent_generation: int, exclusion_generation: int,
    ) -> Head:
        self._scope(identity)
        _nonempty(source_revision)
        if budget < 0 or min(consent_generation, exclusion_generation) < 0:
            raise FenceError("INVALID_BUDGET_OR_GENERATION")
        genesis = _digest(_canonical([
            "K02D-v1", identity.tenant_id, identity.run_id,
            identity.task_id, identity.task_version, identity.principal_id,
        ]))
        with self._write() as db:
            db.execute(
                "INSERT INTO runs(tenant,run,task,version,principal,budget,digest,"
                "source_rev,consent_gen,exclusion_gen) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (identity.tenant_id, identity.run_id, identity.task_id,
                 identity.task_version, identity.principal_id, budget, genesis,
                 source_revision, consent_generation, exclusion_generation),
            )
            row = self._load(db, identity)
            return self._append(db, row, "RUN_CREATED", {
                "budget": budget, "source_rev": source_revision,
                "consent": consent_generation, "exclusion": exclusion_generation,
            })

    def read_head(self, identity: RunIdentity) -> Head:
        with self._connect() as db:
            return self._head(self._load(db, identity))

    def reserve(self, identity: RunIdentity, head: Head, *,
                reserve_id: str, amount: int) -> Head:
        _nonempty(reserve_id)
        if amount <= 0:
            raise FenceError("INVALID_RESERVATION")
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            if row["spent"] + row["reserved"] + amount > row["budget"]:
                raise FenceError("BUDGET_EXCEEDED")
            db.execute("INSERT INTO reservations VALUES(?,?,?,?,0)",
                       (identity.tenant_id, identity.run_id, reserve_id, amount))
            db.execute("UPDATE runs SET reserved=reserved+? WHERE tenant=? AND run=?",
                       (amount, identity.tenant_id, identity.run_id))
            return self._append(db, row, "RESERVED", {
                "reserve_id": reserve_id, "amount": amount,
            })

    def provision_fixture_approval(
        self, identity: RunIdentity, head: Head, *, approval_id: str,
        intent_digest: str, expires_at: int,
    ) -> Head:
        """Test-only local approval reference, NEVER an external trusted approval."""
        if not self.fixture_approval_mode:
            raise FenceError("NO_AUTHENTIC_APPROVAL_ISSUER")
        _nonempty(approval_id, intent_digest)
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            db.execute(
                "INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                (approval_id, identity.tenant_id, identity.run_id, intent_digest,
                 identity.principal_id, row["epoch"], expires_at,
                 row["source_rev"], row["consent_gen"], row["exclusion_gen"]),
            )
            return self._append(db, row, "FIXTURE_APPROVAL_REFERENCE", {
                "approval_id": approval_id, "digest": intent_digest,
            })

    def commit_intent_and_claim(
        self, identity: RunIdentity, head: Head, *, intent_id: str,
        intent_digest: str, approval_id: str, claim_id: str,
        reserve_id: str, idempotency_key: str, now: int,
    ) -> Head:
        _nonempty(intent_id, intent_digest, approval_id, claim_id,
                  reserve_id, idempotency_key)
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            reserve = db.execute(
                "SELECT * FROM reservations WHERE tenant=? AND run=? AND reserve_id=?",
                (identity.tenant_id, identity.run_id, reserve_id),
            ).fetchone()
            approval = db.execute(
                "SELECT * FROM approvals WHERE approval_id=?", (approval_id,),
            ).fetchone()
            if reserve is None or reserve["charged"] or approval is None:
                raise FenceError("MISSING_RESERVATION_OR_APPROVAL")
            if (approval["tenant"], approval["run"], approval["principal"],
                approval["intent_digest"], approval["epoch"]) != (
                identity.tenant_id, identity.run_id, identity.principal_id,
                intent_digest, row["epoch"]
            ) or approval["consumed_by"] is not None or now > approval["expires_at"]:
                raise FenceError("APPROVAL_EXPIRED_CONSUMED_OR_MISMATCH")
            if (approval["source_rev"], approval["consent_gen"],
                approval["exclusion_gen"]) != (
                row["source_rev"], row["consent_gen"], row["exclusion_gen"]
            ):
                raise FenceError("APPROVAL_AUTHORITY_DRIFT")
            db.execute(
                "INSERT INTO intents VALUES(?,?,?,?,?,?,?,?)",
                (intent_id, identity.tenant_id, identity.run_id, intent_digest,
                 approval_id, claim_id, reserve_id, idempotency_key),
            )
            db.execute("UPDATE approvals SET consumed_by=? WHERE approval_id=?",
                       (intent_id, approval_id))
            db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,?,NULL)",
                       (claim_id, identity.tenant_id, identity.run_id,
                        intent_id, row["epoch"], "PENDING"))
            return self._append(db, row, "T1_T2_INTENT_APPROVAL_CLAIM_OUTBOX", {
                "intent_id": intent_id, "intent_digest": intent_digest,
                "approval_id": approval_id, "claim_id": claim_id,
                "reserve_id": reserve_id, "idempotency_key": idempotency_key,
                "epoch": row["epoch"],
            })

    def claim_outbox(self, identity: RunIdentity, head: Head, *,
                     claim_id: str) -> tuple[Head, str]:
        """Returns local durable-commit token; NOT permission for remote send."""
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            outbox = db.execute(
                "SELECT * FROM outbox WHERE claim_id=? AND tenant=? AND run=?",
                (claim_id, identity.tenant_id, identity.run_id),
            ).fetchone()
            if outbox is None or outbox["state"] != "PENDING" or outbox["epoch"] != row["epoch"]:
                raise FenceError("CLAIM_ALREADY_USED_OR_STALE")
            token = secrets.token_hex(24)
            db.execute("UPDATE outbox SET state='CLAIMED',ack_token=? WHERE claim_id=?",
                       (token, claim_id))
            fresh = self._append(db, row, "LOCAL_CLAIM_ACK", {"claim_id": claim_id})
        return fresh, token

    def mark_possible_send(self, identity: RunIdentity, head: Head, *,
                           claim_id: str, local_ack_token: str) -> Head:
        """Durably record UNKNOWN before any (unsupported) remote effect."""
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            outbox = db.execute("SELECT * FROM outbox WHERE claim_id=? AND tenant=? AND run=?",
                                (claim_id, identity.tenant_id, identity.run_id)).fetchone()
            if (outbox is None or outbox["state"] != "CLAIMED"
                or not local_ack_token
                or not hmac.compare_digest(outbox["ack_token"], local_ack_token)
                or outbox["epoch"] != row["epoch"]):
                raise FenceError("NO_DURABLE_COMMIT_ACK_OR_ALREADY_MARKED")
            db.execute("UPDATE outbox SET state='POSSIBLY_SENT' WHERE claim_id=?",
                       (claim_id,))
            return self._append(db, row, "T3_UNKNOWN_EFFECT", {"claim_id": claim_id})

    def record_observer_reconciliation(
        self, identity: RunIdentity, head: Head, *, intent_id: str,
        original_t1_digest: str, observer_id: str, evidence_ref: str,
        evidence_sha256: str, outcome: str, source_revision: str,
        consent_generation: int, exclusion_generation: int,
        expires_at: int, now: int,
    ) -> Head:
        _nonempty(intent_id, original_t1_digest, observer_id, evidence_ref,
                  evidence_sha256, source_revision)
        if (outcome not in {"CONFIRMED_APPLIED", "CONFIRMED_NOT_APPLIED"}
            or len(evidence_sha256) != 64
            or any(c not in "0123456789abcdef" for c in evidence_sha256)
            or expires_at < now):
            raise FenceError("INVALID_T4_EVIDENCE_REFERENCE")
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            intent = db.execute(
                "SELECT * FROM intents WHERE intent_id=? AND tenant=? AND run=?",
                (intent_id, identity.tenant_id, identity.run_id),
            ).fetchone()
            outbox = None if intent is None else db.execute(
                "SELECT * FROM outbox WHERE intent_id=?", (intent_id,),
            ).fetchone()
            if (intent is None or outbox is None
                or intent["digest"] != original_t1_digest
                or outbox["state"] != "POSSIBLY_SENT"
                or observer_id == identity.principal_id):
                raise FenceError("UNRECONCILED_T3_OR_SELF_OBSERVER")
            if (source_revision, consent_generation, exclusion_generation) != (
                row["source_rev"], row["consent_gen"], row["exclusion_gen"]
            ):
                raise FenceError("STALE_SOURCE_CONSENT_EXCLUSION")
            db.execute(
                "INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (evidence_ref, identity.tenant_id, identity.run_id, intent_id,
                 original_t1_digest, observer_id, evidence_sha256, outcome,
                 expires_at, source_revision, consent_generation,
                 exclusion_generation),
            )
            db.execute("UPDATE outbox SET state='T4_RECORDED' WHERE intent_id=?",
                       (intent_id,))
            return self._append(db, row, "T4_OBSERVER_REFERENCE_UNATTESTED", {
                "evidence_ref": evidence_ref, "observer_id": observer_id,
                "outcome": outcome, "evidence_sha256": evidence_sha256,
                "intent_id": intent_id, "intent_digest": original_t1_digest,
            })

    @staticmethod
    def verification_message(
        identity: RunIdentity, head: Head, *, evidence_ref: str,
        verification_ref: str, status: str,
    ) -> bytes:
        return _canonical({
            "domain": "K02D-LOCAL-EXPERIMENTAL-v1",
            "tenant": identity.tenant_id, "run": identity.run_id,
            "task": identity.task_id, "version": identity.task_version,
            "principal": identity.principal_id, "seq": head.seq,
            "hash": head.digest, "epoch": head.epoch,
            "evidence_ref": evidence_ref, "verification_ref": verification_ref,
            "status": status,
        }).encode("utf-8")

    def commit_terminal(
        self, identity: RunIdentity, head: Head, *, evidence_ref: str,
        verification_ref: str, verifier_id: str, signature_hex: str,
        status: str, now: int,
    ) -> Head:
        """Fixture-key HMAC permits LOCAL terminal only, never real SUCCEEDED."""
        _nonempty(evidence_ref, verification_ref, verifier_id, signature_hex)
        if status not in {"LOCAL_VERIFIED_APPLIED", "LOCAL_VERIFIED_NOT_APPLIED"}:
            raise FenceError("NO_PRODUCTION_SUCCESS_AUTHORITY")
        key = self._verifier_keys.get(verifier_id)
        if key is None:
            raise FenceError("MISSING_INDEPENDENT_VERIFIER_KEY")
        message = self.verification_message(
            identity, head, evidence_ref=evidence_ref,
            verification_ref=verification_ref, status=status,
        )
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise FenceError("INVALID_VERIFIER_SIGNATURE") from exc
        if not hmac.compare_digest(hmac.new(key, message, hashlib.sha256).digest(),
                                   signature):
            raise FenceError("INVALID_VERIFIER_SIGNATURE")
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            obs = db.execute(
                "SELECT * FROM observations WHERE evidence_ref=? AND tenant=? AND run=?",
                (evidence_ref, identity.tenant_id, identity.run_id),
            ).fetchone()
            wanted = ("CONFIRMED_APPLIED" if status == "LOCAL_VERIFIED_APPLIED"
                      else "CONFIRMED_NOT_APPLIED")
            if (obs is None or obs["outcome"] != wanted or now > obs["expires_at"]
                or verifier_id in {identity.principal_id, obs["observer_id"]}
                or (obs["source_rev"], obs["consent_gen"], obs["exclusion_gen"]) != (
                    row["source_rev"], row["consent_gen"], row["exclusion_gen"]
                )):
                raise FenceError("T4_VERIFICATION_CONTEXT_MISMATCH")
            outstanding = db.execute(
                "SELECT COUNT(*) AS n FROM outbox WHERE tenant=? AND run=?"
                " AND state='POSSIBLY_SENT'",
                (identity.tenant_id, identity.run_id),
            ).fetchone()["n"]
            if outstanding:
                raise FenceError("UNRESOLVED_UNKNOWN_EFFECT")
            db.execute("UPDATE runs SET state=? WHERE tenant=? AND run=?",
                       (status, identity.tenant_id, identity.run_id))
            return self._append(db, row, "T5_LOCAL_VERIFIED_TERMINAL", {
                "status": status, "evidence_ref": evidence_ref,
                "verification_ref": verification_ref, "verifier_id": verifier_id,
            })

    def charge(self, identity: RunIdentity, head: Head, *, reserve_id: str,
               charge_id: str, amount: int) -> Head:
        _nonempty(reserve_id, charge_id)
        if amount < 0:
            raise FenceError("UNKNOWN_OR_NEGATIVE_CHARGE")
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            reserve = db.execute(
                "SELECT * FROM reservations WHERE tenant=? AND run=? AND reserve_id=?",
                (identity.tenant_id, identity.run_id, reserve_id),
            ).fetchone()
            if reserve is None or reserve["charged"] or amount > reserve["amount"]:
                raise FenceError("RESERVATION_ALREADY_CHARGED_OR_EXCEEDED")
            db.execute("INSERT INTO charges VALUES(?,?,?,?,?)",
                       (charge_id, identity.tenant_id, identity.run_id,
                        reserve_id, amount))
            db.execute(
                "UPDATE reservations SET charged=1 WHERE tenant=? AND run=? AND reserve_id=?",
                       (identity.tenant_id, identity.run_id, reserve_id))
            db.execute(
                "UPDATE runs SET reserved=reserved-?,spent=spent+?"
                " WHERE tenant=? AND run=?",
                (reserve["amount"], amount, identity.tenant_id, identity.run_id),
            )
            return self._append(db, row, "CHARGE_CAPTURED", {
                "reserve_id": reserve_id, "charge_id": charge_id,
                "amount": amount, "released": reserve["amount"],
            })

    def takeover(self, identity: RunIdentity, head: Head) -> Head:
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            db.execute("UPDATE runs SET epoch=epoch+1 WHERE tenant=? AND run=?",
                       (identity.tenant_id, identity.run_id))
            return self._append(db, row, "LEASE_TAKEOVER", {"epoch": row["epoch"] + 1})

    def update_authority(
        self, identity: RunIdentity, head: Head, *, source_revision: str,
        consent_generation: int, exclusion_generation: int, revoked: bool = False,
    ) -> Head:
        _nonempty(source_revision)
        with self._write() as db:
            row = self._load(db, identity)
            self._cas(row, head)
            if (consent_generation < row["consent_gen"]
                or exclusion_generation < row["exclusion_gen"]):
                raise FenceError("AUTHORITY_GENERATION_ROLLBACK")
            db.execute(
                "UPDATE runs SET source_rev=?,consent_gen=?,exclusion_gen=?,revoked=?"
                " WHERE tenant=? AND run=?",
                (source_revision, consent_generation, exclusion_generation,
                 int(revoked), identity.tenant_id, identity.run_id),
            )
            return self._append(db, row, "AUTHORITY_REVISION", {
                "source": source_revision, "consent": consent_generation,
                "exclusion": exclusion_generation, "revoked": bool(revoked),
            })

    def audit_charge_adjustment(
        self, *, adjustment_id: str, charge_id: str,
        delta: int, evidence_ref: str,
    ) -> None:
        """Sidecar audit: no run head or terminal mutation, no invoice authority."""
        _nonempty(adjustment_id, charge_id, evidence_ref)
        if delta == 0:
            raise FenceError("ZERO_ADJUSTMENT")
        with self._write() as db:
            db.execute("INSERT INTO adjustments VALUES(?,?,?,?)",
                       (adjustment_id, charge_id, delta, evidence_ref))

    def recover(self, identity: RunIdentity) -> dict:
        """Read verified durable state; never automatically re-send outbox."""
        with self._connect() as db:
            row = self._load(db, identity)
            outbox = db.execute(
                "SELECT claim_id,intent_id,epoch,state FROM outbox"
                " WHERE tenant=? AND run=? ORDER BY claim_id",
                (identity.tenant_id, identity.run_id),
            ).fetchall()
            ledger = db.execute(
                "SELECT COALESCE(SUM(a.delta),0) AS net FROM adjustments a"
                " JOIN charges c ON c.charge_id=a.charge_id"
                " WHERE c.tenant=? AND c.run=?",
                (identity.tenant_id, identity.run_id),
            ).fetchone()
            return {
                "head": self._head(row),
                "outbox": [dict(item) for item in outbox],
                "corrected_spent": row["spent"] + ledger["net"],
                "source_revision": row["source_rev"],
                "consent_generation": row["consent_gen"],
                "exclusion_generation": row["exclusion_gen"],
                "revoked": bool(row["revoked"]),
                "dispatch_authorized": False,
                "AR02_STAGE_DONE": False,
            }
