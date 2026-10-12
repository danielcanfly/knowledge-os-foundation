"""M28 feature-off local fixture rights + derived Memory lifecycle fence.

Durable SQLite is the authority for this strictly local simulation. It is NOT an
IdP/provider authority, external deletion receipt, or physical SQLite/WAL erase.
No live external dispatch occurs; a fresh OS process must recheck the same DB.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_KINDS = frozenset({"source", "cache", "citation", "trace", "memory", "checkpoint", "backup"})
_OPS = frozenset({"read", "cite", "publish", "tool", "checkpoint", "replay", "write", "query", "use"})
_FIXTURE = "M28_LOCAL_ONLY_NO_EXTERNAL_AUTHORITY"


class LifecycleDenied(ValueError):
    """Fail-closed; never include payload in an error."""


def _valid(*values: str) -> bool:
    return all(isinstance(x, str) and bool(_ID.fullmatch(x)) for x in values)


@dataclass(frozen=True, slots=True)
class LocalLease:
    tenant_id: str
    run_id: str
    principal_id: str
    purpose: str
    source_revision: str
    consent_generation: int
    policy_generation: int
    lease_id: str
    fixture_marker: str = _FIXTURE


class LocalRightsMemoryFence:
    """Tenant/run-scoped committed generations, local files, outbox and quarantine.

    Every read, citation publication, cached query, tool dispatch and checkpoint
    replay tests the durable policy inside BEGIN IMMEDIATE. An offline/restarted
    process cannot treat a pre-revocation lease as live. The configured root is
    restricted to owned local fixture files, not arbitrary caller paths.
    """

    def __init__(self, db_path: str | Path, blob_root: str | Path, *, fixture_only: bool):
        if not fixture_only:
            raise LifecycleDenied("EXTERNAL_AUTHORITY_NOT_SUPPORTED")
        self.db_path = Path(db_path)
        self.blob_root = Path(blob_root).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_root.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS m28_scope(
                    tenant TEXT NOT NULL, run TEXT NOT NULL,
                    principal TEXT NOT NULL, purpose TEXT NOT NULL,
                    revision TEXT NOT NULL, consent INTEGER NOT NULL,
                    policy INTEGER NOT NULL, lease TEXT NOT NULL,
                    status TEXT NOT NULL, PRIMARY KEY(tenant,run));
                CREATE TABLE IF NOT EXISTS m28_blob(
                    tenant TEXT NOT NULL, run TEXT NOT NULL, item TEXT NOT NULL,
                    kind TEXT NOT NULL, sha TEXT NOT NULL, state TEXT NOT NULL,
                    PRIMARY KEY(tenant,run,item));
                CREATE TABLE IF NOT EXISTS m28_permit(
                    tenant TEXT NOT NULL, run TEXT NOT NULL, permit TEXT NOT NULL,
                    generation INTEGER NOT NULL, state TEXT NOT NULL,
                    PRIMARY KEY(tenant,run,permit));
                CREATE TABLE IF NOT EXISTS m28_event(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
                    run TEXT NOT NULL, kind TEXT NOT NULL, generation INTEGER NOT NULL);
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=8, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=8000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Connection]:
        with self._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def grant(self, *, tenant: str, run: str, principal: str, purpose: str,
              revision: str, lease_id: str, consent_generation: int = 1,
              policy_generation: int = 1) -> LocalLease:
        if (not _valid(tenant, run, principal, purpose, revision, lease_id)
                or type(consent_generation) is not int or consent_generation < 1
                or type(policy_generation) is not int or policy_generation < 1):
            raise LifecycleDenied("INVALID_LOCAL_GRANT")
        lease = LocalLease(tenant, run, principal, purpose, revision,
                           consent_generation, policy_generation, lease_id)
        with self._txn() as db:
            try:
                db.execute(
                    "INSERT INTO m28_scope VALUES(?,?,?,?,?,?,?,?,?)",
                    (tenant, run, principal, purpose, revision, consent_generation,
                     policy_generation, lease_id, "ACTIVE"),
                )
            except sqlite3.IntegrityError as exc:
                raise LifecycleDenied("DUPLICATE_OR_REVOKED_SCOPE") from exc
            db.execute("INSERT INTO m28_event(tenant,run,kind,generation) VALUES(?,?,?,?)",
                       (tenant, run, "LOCAL_FIXTURE_GRANT", policy_generation))
        return lease

    def _require(self, db: sqlite3.Connection, lease: LocalLease, op: str) -> None:
        if (not isinstance(lease, LocalLease) or lease.fixture_marker != _FIXTURE
                or op not in _OPS):
            raise LifecycleDenied("UNTRUSTED_LEASE_OR_OPERATION")
        row = db.execute("SELECT * FROM m28_scope WHERE tenant=? AND run=?",
                         (lease.tenant_id, lease.run_id)).fetchone()
        if (row is None or row["status"] != "ACTIVE"
                or (row["principal"], row["purpose"], row["revision"],
                    row["consent"], row["policy"], row["lease"]) != (
                    lease.principal_id, lease.purpose, lease.source_revision,
                    lease.consent_generation, lease.policy_generation,
                    lease.lease_id)):
            raise LifecycleDenied("REVOKED_STALE_OR_TENANT_SCOPE")

    def require(self, lease: LocalLease, operation: str) -> None:
        with self._txn() as db:
            self._require(db, lease, operation)

    def _file(self, lease: LocalLease, item: str, *, quarantine: bool = False) -> Path:
        if not _valid(lease.tenant_id, lease.run_id, item):
            raise LifecycleDenied("INVALID_ITEM_ID")
        scope = "quarantine" if quarantine else "derived"
        folder = self.blob_root / scope / lease.tenant_id / lease.run_id
        folder.mkdir(parents=True, exist_ok=True)
        if folder.is_symlink() or folder.resolve() != folder:
            raise LifecycleDenied("UNSAFE_LOCAL_BLOB_DIRECTORY")
        return folder / (item + ".bin")

    def put(self, lease: LocalLease, item: str, kind: str, payload: bytes) -> str:
        if kind not in _KINDS or not _valid(item) or not isinstance(payload, bytes):
            raise LifecycleDenied("INVALID_DERIVED_RECORD")
        with self._txn() as db:
            self._require(db, lease, "write")
            if db.execute("SELECT 1 FROM m28_blob WHERE tenant=? AND run=? AND item=?",
                          (lease.tenant_id, lease.run_id, item)).fetchone():
                raise LifecycleDenied("DUPLICATE_DERIVED_RECORD")
            path = self._file(lease, item)
            digest = hashlib.sha256(payload).hexdigest()
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                db.execute("INSERT INTO m28_blob VALUES(?,?,?,?,?,?)",
                           (lease.tenant_id, lease.run_id, item, kind, digest, "ACTIVE"))
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            return digest

    def _get(self, db: sqlite3.Connection, lease: LocalLease,
             item: str, kind: str, operation: str) -> bytes:
        self._require(db, lease, operation)
        row = db.execute(
            "SELECT kind,sha,state FROM m28_blob WHERE tenant=? AND run=? AND item=?",
            (lease.tenant_id, lease.run_id, item),
        ).fetchone()
        if row is None or row["state"] != "ACTIVE" or row["kind"] != kind:
            raise LifecycleDenied("DERIVED_NOT_READABLE")
        path = self._file(lease, item)
        if path.is_symlink() or not path.is_file():
            raise LifecycleDenied("UNSAFE_OR_MISSING_DERIVED_FILE")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["sha"]:
            raise LifecycleDenied("DERIVED_DIGEST_MISMATCH")
        return payload

    def read(self, lease: LocalLease, item: str, *, kind: str = "source") -> bytes:
        with self._txn() as db:
            return self._get(db, lease, item, kind, "read")

    def query_cache(self, lease: LocalLease, item: str) -> bytes:
        with self._txn() as db:
            return self._get(db, lease, item, "cache", "query")

    def replay(self, lease: LocalLease, item: str) -> bytes:
        with self._txn() as db:
            return self._get(db, lease, item, "checkpoint", "replay")

    def publish_queued(self, lease: LocalLease, item: str) -> bytes:
        with self._txn() as db:
            payload = self._get(db, lease, item, "citation", "publish")
            db.execute("UPDATE m28_blob SET state='PUBLISHED_LOCAL' WHERE tenant=? AND run=? AND item=?",
                       (lease.tenant_id, lease.run_id, item))
            db.execute("INSERT INTO m28_event(tenant,run,kind,generation) VALUES(?,?,?,?)",
                       (lease.tenant_id, lease.run_id, "LOCAL_CITATION_PUBLICATION", lease.policy_generation))
            return payload

    def issue_tool_permit(self, lease: LocalLease, permit: str) -> None:
        if not _valid(permit):
            raise LifecycleDenied("INVALID_LOCAL_PERMIT")
        with self._txn() as db:
            self._require(db, lease, "tool")
            try:
                db.execute("INSERT INTO m28_permit VALUES(?,?,?,?,?)",
                           (lease.tenant_id, lease.run_id, permit, lease.policy_generation, "ISSUED"))
            except sqlite3.IntegrityError as exc:
                raise LifecycleDenied("DUPLICATE_TOOL_PERMIT") from exc

    def dispatch_local_tool(self, lease: LocalLease, permit: str) -> str:
        """No external tool or network effect. Model the final local T3 fence."""
        with self._txn() as db:
            self._require(db, lease, "tool")
            result = db.execute(
                "UPDATE m28_permit SET state='LOCAL_DISPATCHED' WHERE tenant=? AND run=? "
                "AND permit=? AND generation=? AND state='ISSUED'",
                (lease.tenant_id, lease.run_id, permit, lease.policy_generation),
            )
            if result.rowcount != 1:
                raise LifecycleDenied("STALE_OR_DUPLICATED_PERMIT")
            db.execute("INSERT INTO m28_event(tenant,run,kind,generation) VALUES(?,?,?,?)",
                       (lease.tenant_id, lease.run_id, "LOCAL_TOOL_ONLY", lease.policy_generation))
        return "LOCAL_TOOL_ONLY_NO_EXTERNAL_EFFECT"

    def revoke(self, lease: LocalLease, *, reason: str = "CONSENT_WITHDRAWN") -> dict:
        if reason not in {"CONSENT_WITHDRAWN", "POLICY_CHANGE", "SUBJECT_ERASURE"}:
            raise LifecycleDenied("INVALID_REVOCATION_REASON")
        # Commit tombstone FIRST; failed cleanup cannot restore authority.
        with self._txn() as db:
            self._require(db, lease, "use")
            db.execute("UPDATE m28_scope SET status='TOMBSTONED',policy=policy+1 "
                       "WHERE tenant=? AND run=?", (lease.tenant_id, lease.run_id))
            db.execute("UPDATE m28_blob SET state='DENIED_AFTER_REVOCATION' WHERE tenant=? AND run=?",
                       (lease.tenant_id, lease.run_id))
            db.execute("UPDATE m28_permit SET state='REVOKED' WHERE tenant=? AND run=?",
                       (lease.tenant_id, lease.run_id))
            db.execute("INSERT INTO m28_event(tenant,run,kind,generation) VALUES(?,?,?,?)",
                       (lease.tenant_id, lease.run_id, "LOCAL_TOMBSTONE_" + reason, lease.policy_generation + 1))
        return self.recover_local_cleanup(lease)

    def recover_local_cleanup(self, lease: LocalLease) -> dict:
        """Idempotent cleanup after a crash between tombstone fsync and unlink.

        This privileged local fixture function can only decrease availability.
        It NEVER reactivates a lease, reads bytes, or attests remote deletion.
        """
        with self._txn() as db:
            row = db.execute("SELECT * FROM m28_scope WHERE tenant=? AND run=?",
                             (lease.tenant_id, lease.run_id)).fetchone()
            if (row is None or row["status"] != "TOMBSTONED"
                    or (row["principal"], row["purpose"], row["revision"],
                        row["consent"], row["policy"], row["lease"]) != (
                        lease.principal_id, lease.purpose, lease.source_revision,
                        lease.consent_generation, lease.policy_generation + 1,
                        lease.lease_id)):
                raise LifecycleDenied("UNAUTHORIZED_OR_ACTIVE_CLEANUP_SCOPE")
            rows = db.execute("SELECT item,kind FROM m28_blob WHERE tenant=? AND run=? "
                              "AND state='DENIED_AFTER_REVOCATION'",
                              (lease.tenant_id, lease.run_id)).fetchall()
        removed, quarantined, cleanup_pending = 0, 0, []
        for record in rows:
            try:
                source = self._file(lease, record["item"])
                if record["kind"] == "backup":
                    target = self._file(lease, record["item"], quarantine=True)
                    if source.exists():
                        os.replace(source, target)
                    if target.exists():
                        quarantined += 1
                else:
                    if source.exists():
                        source.unlink()
                        removed += 1
            except OSError:
                cleanup_pending.append(record["item"])
        return {"tombstoned": True, "local_unlinked": removed,
                "backup_quarantined": quarantined, "cleanup_pending": tuple(cleanup_pending),
                "external_backup_erased": False, "sqlite_physical_erasure_proven": False}

    def restore_quarantined(self, lease: LocalLease, item: str) -> bytes:
        # Even holding an old backup file never bypasses the authoritative tombstone.
        self.require(lease, "replay")
        raise LifecycleDenied("BACKUP_RESTORE_REQUIRES_NEW_AUTHORITY_AND_REVIEW")
