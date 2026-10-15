"""A07 standalone NONPROD governed memory journal and revocation adapter.

Never connect this module to a production database, R2, Qdrant, IdP or client.
The authority DB deliberately lives outside restorable data/cache snapshots.
No memory is admissible as knowledge or citation evidence, even if retained.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Iterator

TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
CLASSES = frozenset({"EPISODIC", "PROJECT"})
ABI = "a07.governed-memory/v1"


class Denied(ValueError):
    """No data, secret, or attacker-provided identifier is included in errors."""


def _id(value: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise Denied("INVALID_IDENTIFIER")
    return value


def _expiry(expires: int) -> int:
    if type(expires) is not int or expires <= 0:
        raise Denied("INVALID_EXPIRY")
    return expires


class MemoryStore:
    def __init__(self, root: str | Path):
        root = Path(root)
        if root.is_symlink():
            raise Denied("UNSAFE_ROOT")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.joinpath("blobs").mkdir(exist_ok=True)
        self.root.joinpath("snapshots").mkdir(exist_ok=True)
        if any(self.root.joinpath(name).is_symlink() for name in ("blobs", "snapshots")):
            raise Denied("UNSAFE_ROOT")
        self.auth = self.root / "authority.sqlite"
        self.data = self.root / "memories.sqlite"
        self.cache = self.root / "derived.sqlite"
        with self._db(self.auth) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources(
                  tenant TEXT NOT NULL, source TEXT NOT NULL, principal TEXT NOT NULL,
                  purpose TEXT NOT NULL, version INTEGER NOT NULL, consent INTEGER NOT NULL,
                  expires INTEGER NOT NULL, status TEXT NOT NULL, digest TEXT NOT NULL,
                  PRIMARY KEY(tenant,source));
                CREATE TABLE IF NOT EXISTS erased_memories(
                  tenant TEXT NOT NULL, memid TEXT NOT NULL, revoked_at INTEGER NOT NULL,
                  PRIMARY KEY(tenant,memid));
                CREATE TABLE IF NOT EXISTS events(
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
                  target TEXT NOT NULL, event TEXT NOT NULL, generation INTEGER NOT NULL,
                  timestamp INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots(
                  snap TEXT PRIMARY KEY, manifest TEXT NOT NULL, state TEXT NOT NULL);
            """)
        with self._db(self.data) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memories(
                  tenant TEXT NOT NULL, memid TEXT NOT NULL, principal TEXT NOT NULL,
                  class TEXT NOT NULL, summary TEXT NOT NULL, expires INTEGER NOT NULL,
                  PRIMARY KEY(tenant,memid));
                CREATE TABLE IF NOT EXISTS lineage(
                  tenant TEXT NOT NULL, memid TEXT NOT NULL, source TEXT NOT NULL,
                  version INTEGER NOT NULL, PRIMARY KEY(tenant,memid,source));
            """)
        with self._db(self.cache) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cache(
                  tenant TEXT NOT NULL, key TEXT NOT NULL, memid TEXT NOT NULL,
                  value BLOB NOT NULL, expires INTEGER NOT NULL,
                  PRIMARY KEY(tenant,key));
                CREATE TABLE IF NOT EXISTS cache_lineage(
                  tenant TEXT NOT NULL, key TEXT NOT NULL, source TEXT NOT NULL,
                  version INTEGER NOT NULL, PRIMARY KEY(tenant,key,source));
            """)

    @contextmanager
    def _db(self, path: Path) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _authority(self) -> Iterator[sqlite3.Connection]:
        with self._db(self.auth) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _blob(self, tenant: str, source: str) -> Path:
        folder = self.root / "blobs" / _id(tenant)
        if folder.is_symlink():
            raise Denied("UNSAFE_BLOB_PATH")
        folder.mkdir(exist_ok=True)
        if folder.is_symlink() or folder.resolve() != folder:
            raise Denied("UNSAFE_BLOB_PATH")
        path = folder / (_id(source) + ".bin")
        if path.is_symlink():
            raise Denied("UNSAFE_BLOB_PATH")
        return path

    @staticmethod
    def _source_ok(db: sqlite3.Connection, tenant: str, principal: str,
                   source: str, version: int | None = None) -> sqlite3.Row:
        row = db.execute("SELECT * FROM sources WHERE tenant=? AND source=?",
                         (tenant, source)).fetchone()
        if (row is None or row["principal"] != principal or row["status"] != "ACTIVE"
                or row["consent"] != 1 or row["expires"] <= int(time.time())
                or (version is not None and row["version"] != version)):
            raise Denied("SOURCE_REVOKED_EXPIRED_OR_SCOPE")
        return row

    @staticmethod
    def _not_erased(db: sqlite3.Connection, tenant: str, memid: str) -> None:
        if db.execute("SELECT 1 FROM erased_memories WHERE tenant=? AND memid=?",
                      (tenant, memid)).fetchone():
            raise Denied("MEMORY_ERASED")

    def grant_source(self, *, tenant: str, principal: str, source: str,
                     purpose: str, payload: bytes, expires: int, consent: bool) -> int:
        for token in (tenant, principal, source, purpose):
            _id(token)
        _expiry(expires)
        if consent is not True or not isinstance(payload, bytes):
            raise Denied("CONSENT_REQUIRED")
        if expires <= int(time.time()):
            raise Denied("EXPIRED_AT_WRITE")
        path = self._blob(tenant, source)
        digest = hashlib.sha256(payload).hexdigest()
        with self._authority() as db:
            if db.execute("SELECT 1 FROM sources WHERE tenant=? AND source=?",
                          (tenant, source)).fetchone():
                raise Denied("SOURCE_ID_REUSE_OR_REVOKED")
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?)",
                           (tenant, source, principal, purpose, 1, 1, expires,
                            "ACTIVE", digest))
                db.execute("INSERT INTO events(tenant,target,event,generation,timestamp) "
                           "VALUES(?,?,?,?,?)",
                           (tenant, source, "CONSENT_GRANTED", 1, int(time.time())))
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        return 1

    def read_source(self, *, tenant: str, principal: str, source: str) -> bytes:
        for token in (tenant, principal, source):
            _id(token)
        with self._authority() as db:
            row = self._source_ok(db, tenant, principal, source)
            path = self._blob(tenant, source)
            if not path.is_file() or path.is_symlink():
                raise Denied("SOURCE_BLOB_MISSING")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != row["digest"]:
                raise Denied("SOURCE_INTEGRITY")
            return payload

    def _lineage(self, db: sqlite3.Connection, tenant: str, principal: str,
                 memid: str) -> list[tuple[str,int]]:
        self._not_erased(db, tenant, memid)
        with self._db(self.data) as data:
            memory = data.execute("SELECT principal,expires FROM memories "
                                  "WHERE tenant=? AND memid=?", (tenant, memid)).fetchone()
            if memory is None or memory["principal"] != principal:
                raise Denied("MEMORY_SCOPE")
            if memory["expires"] <= int(time.time()):
                raise Denied("MEMORY_EXPIRED")
            rows = data.execute("SELECT source,version FROM lineage WHERE tenant=? "
                                "AND memid=? ORDER BY source", (tenant, memid)).fetchall()
        if not rows:
            raise Denied("NO_VALID_LINEAGE")
        for row in rows:
            self._source_ok(db, tenant, principal, row["source"], row["version"])
        return [(row["source"], row["version"]) for row in rows]

    def write_memory(self, *, tenant: str, principal: str, memid: str,
                     summary: str, sources: tuple[str,...], expires: int,
                     memory_class: str = "PROJECT") -> None:
        for token in (tenant, principal, memid):
            _id(token)
        _expiry(expires)
        if (memory_class not in CLASSES or not isinstance(summary, str)
                or not 0 < len(summary) <= 4096 or not sources
                or len(sources) != len(set(sources)) or expires <= int(time.time())):
            raise Denied("INVALID_MEMORY_CANDIDATE")
        for source in sources:
            _id(source)
        with self._authority() as auth:
            lineage = [(source, self._source_ok(auth, tenant, principal, source)["version"])
                       for source in sources]
            with self._db(self.data) as data:
                try:
                    data.execute("BEGIN IMMEDIATE")
                    self._not_erased(auth, tenant, memid)
                    data.execute("INSERT INTO memories VALUES(?,?,?,?,?,?)",
                                 (tenant, memid, principal, memory_class, summary, expires))
                    data.executemany("INSERT INTO lineage VALUES(?,?,?,?)",
                                     [(tenant, memid, src, ver) for src, ver in lineage])
                    data.commit()
                except BaseException:
                    data.rollback()
                    raise

    def candidate(self, *, tenant: str, principal: str, memid: str) -> dict:
        for token in (tenant, principal, memid):
            _id(token)
        with self._authority() as auth:
            lineage = self._lineage(auth, tenant, principal, memid)
            with self._db(self.data) as data:
                row = data.execute("SELECT class,summary FROM memories "
                                   "WHERE tenant=? AND memid=?", (tenant, memid)).fetchone()
            return {"abi": ABI, "status": "UNVERIFIED_MEMORY_CANDIDATE",
                    "tenant_id": tenant, "memory_id": memid, "memory_class": row["class"],
                    "summary": row["summary"],
                    "source_lineage": [{"source_id": s, "generation": v} for s,v in lineage],
                    "knowledge_authority": False, "citation_eligible": False,
                    "answer_context_enabled": False, "can_promote_to_knowledge": False}

    def put_cache(self, *, tenant: str, principal: str, memid: str,
                  key: str, payload: bytes, expires: int) -> None:
        _id(key)
        _expiry(expires)
        if type(payload) is not bytes or expires <= int(time.time()):
            raise Denied("INVALID_CACHE")
        with self._authority() as auth:
            lineage = self._lineage(auth, _id(tenant), _id(principal), _id(memid))
            with self._db(self.cache) as cache:
                try:
                    cache.execute("BEGIN IMMEDIATE")
                    cache.execute("INSERT INTO cache VALUES(?,?,?,?,?)",
                                  (tenant, key, memid, payload, expires))
                    cache.executemany("INSERT INTO cache_lineage VALUES(?,?,?,?)",
                                      [(tenant,key,s,v) for s,v in lineage])
                    cache.commit()
                except BaseException:
                    cache.rollback()
                    raise

    def query_cache(self, *, tenant: str, principal: str, key: str) -> bytes:
        for token in (tenant, principal, key):
            _id(token)
        with self._authority() as auth:
            with self._db(self.cache) as cache:
                row = cache.execute("SELECT memid,value,expires FROM cache WHERE "
                                    "tenant=? AND key=?", (tenant, key)).fetchone()
                if row is None or row["expires"] <= int(time.time()):
                    raise Denied("CACHE_MISSING_EXPIRED")
                lineage = self._lineage(auth, tenant, principal, row["memid"])
                cache_rows = cache.execute("SELECT source,version FROM cache_lineage "
                                           "WHERE tenant=? AND key=? ORDER BY source",
                                           (tenant,key)).fetchall()
                if [(r["source"],r["version"]) for r in cache_rows] != lineage:
                    raise Denied("CACHE_LINEAGE_STALE")
                return bytes(row["value"])

    def to_evidence(self, *args, **kwargs):
        raise Denied("MEMORY_NOT_EVIDENCE_OR_CITATION")

    def revoke_source(self, *, tenant: str, principal: str, source: str) -> dict:
        for token in (tenant, principal, source):
            _id(token)
        with self._authority() as auth:
            row = self._source_ok(auth, tenant, principal, source)
            auth.execute("UPDATE sources SET status='REVOKED',consent=0,version=version+1 "
                         "WHERE tenant=? AND source=?", (tenant, source))
            auth.execute("INSERT INTO events(tenant,target,event,generation,timestamp) "
                         "VALUES(?,?,?,?,?)",
                         (tenant, source, "REVOKED", row["version"]+1, int(time.time())))
            self._invalidate_snapshots(auth, tenant, source=source)
        return self.recover_cleanup(tenant=tenant)

    def delete_memory(self, *, tenant: str, principal: str, memid: str) -> dict:
        for token in (tenant, principal, memid):
            _id(token)
        with self._authority() as auth:
            self._lineage(auth, tenant, principal, memid)
            auth.execute("INSERT INTO erased_memories VALUES(?,?,?)",
                         (tenant, memid, int(time.time())))
            auth.execute("INSERT INTO events(tenant,target,event,generation,timestamp) "
                         "VALUES(?,?,?,?,?)",
                         (tenant, memid, "MEMORY_DELETED", 1, int(time.time())))
            self._invalidate_snapshots(auth, tenant, memid=memid)
        return self.recover_cleanup(tenant=tenant)

    def _invalidate_snapshots(self, db: sqlite3.Connection, tenant: str,
                              source: str | None = None, memid: str | None = None) -> None:
        for row in db.execute("SELECT snap,manifest FROM snapshots WHERE state='ACTIVE'"):
            manifest = json.loads(row["manifest"])
            if ((source is not None and [tenant,source] in manifest["sources"])
                    or (memid is not None and [tenant,memid] in manifest["memories"])):
                db.execute("UPDATE snapshots SET state='INVALIDATED' WHERE snap=?",
                           (row["snap"],))

    def recover_cleanup(self, *, tenant: str) -> dict:
        """Only reduces availability. Repeat after an interrupted unlink."""
        _id(tenant)
        removed = 0
        with self._authority() as auth:
            revoked = [r["source"] for r in auth.execute(
                "SELECT source FROM sources WHERE tenant=? AND status='REVOKED'", (tenant,))]
            deleted = [r["memid"] for r in auth.execute(
                "SELECT memid FROM erased_memories WHERE tenant=?", (tenant,))]
            with self._db(self.data) as data, self._db(self.cache) as cache:
                affected = set(deleted)
                for source in revoked:
                    affected.update(r["memid"] for r in data.execute(
                        "SELECT memid FROM lineage WHERE tenant=? AND source=?",
                        (tenant,source)))
                for memid in affected:
                    cache.execute("DELETE FROM cache_lineage WHERE tenant=? AND key IN "
                                  "(SELECT key FROM cache WHERE tenant=? AND memid=?)",
                                  (tenant,tenant,memid))
                    cache.execute("DELETE FROM cache WHERE tenant=? AND memid=?", (tenant,memid))
                    data.execute("DELETE FROM lineage WHERE tenant=? AND memid=?", (tenant,memid))
                    data.execute("DELETE FROM memories WHERE tenant=? AND memid=?", (tenant,memid))
                for source in revoked:
                    path = self._blob(tenant,source)
                    if path.exists():
                        path.unlink()
                        removed += 1
            invalid = [r["snap"] for r in auth.execute(
                "SELECT snap FROM snapshots WHERE state='INVALIDATED'")]
            for snap in invalid:
                # Excluded by registered manifest; never arbitrary caller paths.
                for ext in (".memory.sqlite", ".cache.sqlite"):
                    path = self.root / "snapshots" / (snap + ext)
                    if path.is_symlink():
                        raise Denied("UNSAFE_SNAPSHOT_FILE")
                    if path.exists():
                        path.unlink()
                        removed += 1
        return {"tombstone_durable": True, "local_unlinked": removed,
                "external_backups_erased": False, "physical_sqlite_erasure_proven": False}

    def snapshot(self, *, snap: str) -> None:
        _id(snap)
        with self._authority() as auth:
            if auth.execute("SELECT 1 FROM snapshots WHERE snap=?", (snap,)).fetchone():
                raise Denied("SNAPSHOT_REUSE")
            with self._db(self.data) as data:
                memories = data.execute("SELECT tenant,memid,principal FROM memories").fetchall()
                lineage = data.execute("SELECT tenant,memid,source,version FROM lineage").fetchall()
            for row in lineage:
                principal = next((m["principal"] for m in memories
                                  if m["tenant"] == row["tenant"] and m["memid"] == row["memid"]), None)
                self._source_ok(auth,row["tenant"],principal,row["source"],row["version"])
            manifest = {"memories": sorted([m["tenant"],m["memid"]] for m in memories),
                        "sources": sorted(set((r["tenant"],r["source"]) for r in lineage)),
                        "versions": sorted([r["tenant"],r["source"],r["version"]] for r in lineage),
                        "sha256": {}}
            for dbpath,ext in ((self.data,".memory.sqlite"),(self.cache,".cache.sqlite")):
                path = self.root / "snapshots" / (snap+ext)
                if path.exists() or path.is_symlink():
                    raise Denied("SNAPSHOT_PATH_REUSE")
                with self._db(dbpath) as live, self._db(path) as dest:
                    live.backup(dest)
                manifest["sha256"][ext] = hashlib.sha256(path.read_bytes()).hexdigest()
            auth.execute("INSERT INTO snapshots VALUES(?,?,?)",
                         (snap,json.dumps(manifest,sort_keys=True),"ACTIVE"))

    def restore(self, *, snap: str) -> None:
        """Controlled local snapshot restore; never restore the authority database."""
        _id(snap)
        with self._authority() as auth:
            row = auth.execute("SELECT manifest,state FROM snapshots WHERE snap=?",
                               (snap,)).fetchone()
            if row is None or row["state"] != "ACTIVE":
                raise Denied("SNAPSHOT_REVOKED_OR_UNKNOWN")
            manifest = json.loads(row["manifest"])
            for tenant,memid in manifest["memories"]:
                self._not_erased(auth,tenant,memid)
            for tenant,source,version in manifest["versions"]:
                row_source = auth.execute("SELECT * FROM sources WHERE tenant=? AND source=?",
                                          (tenant,source)).fetchone()
                if row_source is None:
                    raise Denied("RESTORE_MISSING_SOURCE")
                self._source_ok(auth,tenant,row_source["principal"],source,version)
            # Verify every input BEFORE modifying any live database.
            for ext in (".memory.sqlite",".cache.sqlite"):
                src = self.root / "snapshots" / (snap+ext)
                if not src.is_file() or src.is_symlink():
                    raise Denied("RESTORE_MISSING_SNAPSHOT")
                if hashlib.sha256(src.read_bytes()).hexdigest() != manifest["sha256"][ext]:
                    raise Denied("RESTORE_TAMPERED_SNAPSHOT")
            for dbpath,ext in ((self.data,".memory.sqlite"),(self.cache,".cache.sqlite")):
                src = self.root / "snapshots" / (snap+ext)
                # Controlled SQLite backup; guardian is intentionally NOT restored.
                with self._db(src) as backup, self._db(dbpath) as live:
                    backup.backup(live)

    def audit(self) -> dict:
        with self._db(self.auth) as db:
            return {"events": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                    "revoked_sources": db.execute("SELECT COUNT(*) FROM sources "
                                                   "WHERE status='REVOKED'").fetchone()[0],
                    "deleted_memories": db.execute(
                        "SELECT COUNT(*) FROM erased_memories").fetchone()[0]}
