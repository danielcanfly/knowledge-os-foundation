"""G04 isolated Nonprod revocation ABI.

A fixture-only, local SQLite two-file contract. The *authority* DB is kept
separate from the replaceable *artifact* DB: restoring a stale artifact snapshot
cannot restore rights. Neither database is an IdP, production deletion receipt,
nor proof of external backup/WAL/media erasure. No network, tools, or Actions.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_KINDS = frozenset({"source", "answer_cache", "derived_cache", "citation", "memory"})
_REASONS = frozenset({"CONSENT_WITHDRAWN", "SUBJECT_ERASURE", "SOURCE_RIGHTS_REVOKED"})


class RevocationDenied(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceLease:
    tenant: str
    principal: str
    source_id: str
    source_revision: str
    right_version: int
    revocation_epoch: int
    consent_expires_at: int


@dataclass(frozen=True, slots=True)
class RevocationWitness:
    tenant: str
    principal: str
    source_id: str
    event_id: str
    revocation_epoch: int
    reason: str
    deleted_entries: int
    deleted_kinds: tuple[tuple[str, int], ...]
    evidence_sha256: str
    local_only: bool = True
    external_erasure_verified: bool = False


class LocalRevocationContract:
    """Fail-closed test-only interface. Both DB files must remain on one filesystem.

    SQLite ATTACH + DELETE journals make scope mutation, local invalidation and
    witness insertion one transactional unit. No service-level issuer is implied.
    A higher trust system must protect the separate authority DB from rollback.
    """

    def __init__(self, data_path: str | Path, authority_path: str | Path,
                 *, fixture_only: bool):
        if fixture_only is not True:
            raise RevocationDenied("EXTERNAL_AUTHORITY_NOT_IMPLEMENTED")
        self.data_path = Path(data_path).resolve()
        self.authority_path = Path(authority_path).resolve()
        if self.data_path == self.authority_path:
            raise RevocationDenied("AUTHORITY_MUST_BE_SEPARATE")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.authority_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connected() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS scope (
                tenant TEXT NOT NULL, principal TEXT NOT NULL, source_id TEXT NOT NULL,
                source_revision TEXT NOT NULL, right_version INTEGER NOT NULL,
                epoch INTEGER NOT NULL, consent_expires_at INTEGER NOT NULL,
                acl INTEGER NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY(tenant, principal, source_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS audit (
                tenant TEXT NOT NULL, principal TEXT NOT NULL, source_id TEXT NOT NULL,
                event_id TEXT NOT NULL, witness_json TEXT NOT NULL,
                PRIMARY KEY(tenant, principal, source_id, event_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS data.entries (
                tenant TEXT NOT NULL, principal TEXT NOT NULL, source_id TEXT NOT NULL,
                entry_id TEXT NOT NULL, kind TEXT NOT NULL,
                right_version INTEGER NOT NULL, epoch INTEGER NOT NULL,
                payload BLOB NOT NULL, payload_sha256 TEXT NOT NULL,
                PRIMARY KEY(tenant, principal, source_id, entry_id))""")

    @contextmanager
    def _connected(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.authority_path), timeout=15, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("ATTACH DATABASE ? AS data", (str(self.data_path),))
            db.execute("PRAGMA data.journal_mode=DELETE")
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connected() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _ids(*values: str) -> None:
        if not all(isinstance(v, str) and _ID.fullmatch(v) for v in values):
            raise RevocationDenied("INVALID_SCOPE_ID")

    @staticmethod
    def _fixture_actor(actor: str, principal: str, authorized: bool) -> None:
        if actor != principal or authorized is not True:
            raise RevocationDenied("MISSING_INDEPENDENT_AUTHORITY")

    @staticmethod
    def _row(db: sqlite3.Connection, tenant: str, principal: str,
             source_id: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM scope WHERE tenant=? AND principal=? AND source_id=?",
            (tenant, principal, source_id),
        ).fetchone()
        if row is None:
            raise RevocationDenied("UNKNOWN_SOURCE_RIGHTS")
        return row

    @staticmethod
    def _lease(row: sqlite3.Row) -> SourceLease:
        return SourceLease(row["tenant"], row["principal"], row["source_id"],
                           row["source_revision"], row["right_version"],
                           row["epoch"], row["consent_expires_at"])

    @staticmethod
    def _require(row: sqlite3.Row, lease: SourceLease, *, now: int) -> None:
        if type(now) is not int or now < 0:
            raise RevocationDenied("INVALID_TIME")
        if (row["source_revision"], row["right_version"], row["epoch"]) != (
                lease.source_revision, lease.right_version, lease.revocation_epoch):
            raise RevocationDenied("STALE_RIGHTS_OR_EPOCH")
        if row["status"] != "ACTIVE" or not row["acl"]:
            raise RevocationDenied("REVOKED_OR_ACL_DOWNGRADE")
        if now >= row["consent_expires_at"] or now >= lease.consent_expires_at:
            raise RevocationDenied("CONSENT_EXPIRED")
        if lease.consent_expires_at != row["consent_expires_at"]:
            raise RevocationDenied("STALE_CONSENT")

    def provision_fixture(self, *, tenant: str, principal: str, source_id: str,
                          source_revision: str, right_version: int,
                          consent_expires_at: int, actor: str,
                          authorized_fixture: bool) -> SourceLease:
        self._ids(tenant, principal, source_id, source_revision)
        self._fixture_actor(actor, principal, authorized_fixture)
        if (type(right_version) is not int or right_version < 1 or
                type(consent_expires_at) is not int or consent_expires_at < 1):
            raise RevocationDenied("INVALID_RIGHTS_VERSION_OR_EXPIRY")
        with self._transaction() as db:
            try:
                db.execute("""INSERT INTO scope VALUES(?,?,?,?,?,?,?,?,?)""", (
                    tenant, principal, source_id, source_revision, right_version,
                    0, consent_expires_at, 1, "ACTIVE"))
            except sqlite3.IntegrityError as exc:
                raise RevocationDenied("SCOPE_ALREADY_ISSUED_NO_REGRANT") from exc
            return self._lease(self._row(db, tenant, principal, source_id))

    def current_lease_fixture(self, *, tenant: str, principal: str, source_id: str,
                              actor: str, authorized_fixture: bool,
                              now: int) -> SourceLease:
        self._ids(tenant, principal, source_id)
        self._fixture_actor(actor, principal, authorized_fixture)
        with self._transaction() as db:
            row = self._row(db, tenant, principal, source_id)
            lease = self._lease(row)
            self._require(row, lease, now=now)
            return lease

    def put(self, lease: SourceLease, *, entry_id: str, kind: str,
            payload: bytes, now: int, inject_failure: bool = False) -> str:
        self._ids(lease.tenant, lease.principal, lease.source_id, entry_id)
        if kind not in _KINDS or not isinstance(payload, bytes):
            raise RevocationDenied("INVALID_ENTRY")
        digest = hashlib.sha256(payload).hexdigest()
        with self._transaction() as db:
            row = self._row(db, lease.tenant, lease.principal, lease.source_id)
            self._require(row, lease, now=now)
            db.execute("""INSERT INTO data.entries VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant,principal,source_id,entry_id) DO UPDATE SET
                kind=excluded.kind, right_version=excluded.right_version,
                epoch=excluded.epoch, payload=excluded.payload,
                payload_sha256=excluded.payload_sha256""", (
                    lease.tenant, lease.principal, lease.source_id, entry_id, kind,
                    lease.right_version, lease.revocation_epoch, payload, digest))
            if inject_failure:
                raise RuntimeError("INJECTED_BEFORE_ATOMIC_COMMIT")
        return digest

    def get(self, lease: SourceLease, *, entry_id: str, now: int) -> bytes:
        self._ids(lease.tenant, lease.principal, lease.source_id, entry_id)
        with self._transaction() as db:
            row = self._row(db, lease.tenant, lease.principal, lease.source_id)
            self._require(row, lease, now=now)
            item = db.execute("""SELECT * FROM data.entries
                WHERE tenant=? AND principal=? AND source_id=? AND entry_id=?""",
                (lease.tenant, lease.principal, lease.source_id, entry_id)).fetchone()
            if item is None:
                raise RevocationDenied("ENTRY_NOT_FOUND")
            if (item["right_version"], item["epoch"]) != (
                    row["right_version"], row["epoch"]):
                raise RevocationDenied("STALE_DERIVED_ENTRY")
            content = bytes(item["payload"])
            if hashlib.sha256(content).hexdigest() != item["payload_sha256"]:
                raise RevocationDenied("CORRUPT_ENTRY")
            return content

    @staticmethod
    def _delete_descendants(db: sqlite3.Connection, tenant: str,
                            principal: str, source_id: str) -> tuple[tuple[str, int], ...]:
        rows = db.execute("""SELECT kind, COUNT(*) AS n FROM data.entries
            WHERE tenant=? AND principal=? AND source_id=? GROUP BY kind ORDER BY kind""",
            (tenant, principal, source_id)).fetchall()
        db.execute("""DELETE FROM data.entries
            WHERE tenant=? AND principal=? AND source_id=?""",
            (tenant, principal, source_id))
        return tuple((row["kind"], row["n"]) for row in rows)

    @staticmethod
    def _witness(tenant: str, principal: str, source_id: str, event_id: str,
                 epoch: int, reason: str,
                 kinds: tuple[tuple[str, int], ...]) -> RevocationWitness:
        total = sum(n for _, n in kinds)
        fields = (tenant, principal, source_id, event_id, epoch, reason, total, kinds)
        digest = hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return RevocationWitness(tenant, principal, source_id, event_id, epoch,
                                 reason, total, kinds, digest)

    @staticmethod
    def _receipt(db: sqlite3.Connection, witness: RevocationWitness) -> None:
        payload = json.dumps({
            "tenant": witness.tenant, "principal": witness.principal,
            "source_id": witness.source_id, "event_id": witness.event_id,
            "revocation_epoch": witness.revocation_epoch, "reason": witness.reason,
            "deleted_entries": witness.deleted_entries,
            "deleted_kinds": witness.deleted_kinds,
            "evidence_sha256": witness.evidence_sha256,
        }, sort_keys=True)
        db.execute("INSERT INTO audit VALUES(?,?,?,?,?)", (
            witness.tenant, witness.principal, witness.source_id,
            witness.event_id, payload))

    @staticmethod
    def _existing_receipt(db: sqlite3.Connection, tenant: str,
                          principal: str, source_id: str,
                          event_id: str) -> RevocationWitness | None:
        row = db.execute("""SELECT witness_json FROM audit
            WHERE tenant=? AND principal=? AND source_id=? AND event_id=?""",
            (tenant, principal, source_id, event_id)).fetchone()
        if row is None:
            return None
        try:
            obj = json.loads(row["witness_json"])
            obj["deleted_kinds"] = tuple((k, n) for k, n in obj["deleted_kinds"])
            witness = RevocationWitness(**obj)
            expected = LocalRevocationContract._witness(
                witness.tenant, witness.principal, witness.source_id,
                witness.event_id, witness.revocation_epoch,
                witness.reason, witness.deleted_kinds)
            if (expected.evidence_sha256 != witness.evidence_sha256
                    or expected.deleted_entries != witness.deleted_entries
                    or (witness.tenant, witness.principal, witness.source_id,
                        witness.event_id) != (tenant, principal, source_id, event_id)):
                raise ValueError("integrity mismatch")
            return witness
        except (ValueError, TypeError, KeyError) as exc:
            raise RevocationDenied("CORRUPT_AUDIT_WITNESS") from exc

    def revoke(self, *, tenant: str, principal: str, source_id: str,
               event_id: str, reason: str, actor: str,
               authorized_fixture: bool,
               inject_failure: bool = False) -> RevocationWitness:
        self._ids(tenant, principal, source_id, event_id)
        self._fixture_actor(actor, principal, authorized_fixture)
        if reason not in _REASONS:
            raise RevocationDenied("INVALID_REASON")
        with self._transaction() as db:
            prev = self._existing_receipt(db, tenant, principal, source_id, event_id)
            if prev is not None:
                if prev.reason != reason:
                    raise RevocationDenied("EVENT_ID_REUSED_WITH_DIFFERENT_REASON")
                return prev
            row = self._row(db, tenant, principal, source_id)
            if row["status"] == "REVOKED":
                raise RevocationDenied("ALREADY_REVOKED_OTHER_EVENT")
            db.execute("""UPDATE scope SET status='REVOKED', acl=0, epoch=epoch+1
                WHERE tenant=? AND principal=? AND source_id=?""",
                (tenant, principal, source_id))
            kinds = self._delete_descendants(db, tenant, principal, source_id)
            witness = self._witness(tenant, principal, source_id, event_id,
                                    row["epoch"] + 1, reason, kinds)
            self._receipt(db, witness)
            if inject_failure:
                raise RuntimeError("INJECTED_BEFORE_ATOMIC_COMMIT")
            return witness

    def downgrade_acl_fixture(self, *, tenant: str, principal: str,
                              source_id: str, actor: str,
                              authorized_fixture: bool) -> int:
        self._ids(tenant, principal, source_id)
        self._fixture_actor(actor, principal, authorized_fixture)
        with self._transaction() as db:
            row = self._row(db, tenant, principal, source_id)
            if row["status"] != "ACTIVE" or not row["acl"]:
                return row["epoch"]
            db.execute("""UPDATE scope SET acl=0, epoch=epoch+1
                WHERE tenant=? AND principal=? AND source_id=?""",
                (tenant, principal, source_id))
            self._delete_descendants(db, tenant, principal, source_id)
            return row["epoch"] + 1

    def advance_right_version_fixture(self, *, tenant: str, principal: str,
                                      source_id: str, new_version: int,
                                      actor: str, authorized_fixture: bool) -> SourceLease:
        self._ids(tenant, principal, source_id)
        self._fixture_actor(actor, principal, authorized_fixture)
        with self._transaction() as db:
            row = self._row(db, tenant, principal, source_id)
            if (row["status"] != "ACTIVE" or not row["acl"] or
                    type(new_version) is not int or new_version <= row["right_version"]):
                raise RevocationDenied("INVALID_RIGHTS_ADVANCE")
            db.execute("""UPDATE scope SET right_version=?, epoch=epoch+1
                WHERE tenant=? AND principal=? AND source_id=?""",
                (new_version, tenant, principal, source_id))
            self._delete_descendants(db, tenant, principal, source_id)
            return self._lease(self._row(db, tenant, principal, source_id))

    def recover_restored_artifacts_fixture(self, *, tenant: str,
                                           principal: str, source_id: str,
                                           actor: str, authorized_fixture: bool) -> int:
        """Delete stale restored local descendants. Never restore authority."""
        self._ids(tenant, principal, source_id)
        self._fixture_actor(actor, principal, authorized_fixture)
        with self._transaction() as db:
            row = self._row(db, tenant, principal, source_id)
            if row["status"] != "REVOKED" and row["acl"]:
                raise RevocationDenied("RECOVERY_REQUIRES_REVOKED_SCOPE")
            kinds = self._delete_descendants(db, tenant, principal, source_id)
            return sum(n for _, n in kinds)

    def audit_witness(self, *, tenant: str, principal: str, source_id: str,
                      event_id: str, actor: str,
                      authorized_fixture: bool) -> RevocationWitness:
        self._ids(tenant, principal, source_id, event_id)
        self._fixture_actor(actor, principal, authorized_fixture)
        with self._transaction() as db:
            witness = self._existing_receipt(db, tenant, principal, source_id, event_id)
            if witness is None:
                raise RevocationDenied("WITNESS_NOT_FOUND")
            return witness
