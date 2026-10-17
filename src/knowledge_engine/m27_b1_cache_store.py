"""B1-03 F03-CACHE-02: durable, fail-closed *candidate* store, NOT a cache HIT.

Default OFF. Production write admission is deliberately unavailable pending
CACHE03/CACHE05/H01: the B0 ABI has no authenticated final-write proof parameter.
A fixture-only staging seam exercises the actual SQLite transaction machinery.
No local embedding model, Qdrant, network, or public endpoint is used.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata
from typing import Any, Callable, Mapping

if __package__:
    from . import m27_b0_cache_contracts as base
else:
    import m27_b0_cache_contracts as base

MAX_CANDIDATES = 16
MAX_STORE_RECORDS = 256
MAX_PAYLOAD_BYTES = 128 * 1024
MAX_DB_BYTES = 64 * 1024 * 1024
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


class StoreInvariantError(ValueError):
    """Configuration or unsafe fixture misuse; not a HIT admission."""


def _json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _tokens(text: str) -> frozenset[str]:
    # Local deterministic LEXICAL candidate ranking only; no semantic inference.
    norm = unicodedata.normalize("NFKC", text).casefold()
    return frozenset(_WORDS.findall(norm)[:128])


def _partition(r: dict) -> str:
    q = {k: v for k, v in r["question"].items() if k != "text"}
    return _sha(_json({"identity": r["identity"], "source": r["source"],
                       "policy": r["policy"], "question_constraints": q}))


def _identity_key(r: dict) -> str:
    # Blinded key for revocation; does NOT store user/tenant plaintext as SQL key.
    return _sha(_json([r["identity"]["tenant_id"], r["identity"]["principal_id"],
                       r["source"]["source_manifest_sha256"]]))


def _record_key(r: dict) -> str:
    return _sha(_json([_partition(r), r["question"]["text"]]))


def _effective_now(now: dt.datetime | None) -> dt.datetime:
    value = _utc_now() if now is None else now
    if (not isinstance(value, dt.datetime) or value.tzinfo is None
            or value.utcoffset() != dt.timedelta(0)):
        raise StoreInvariantError("UTC_CLOCK_REQUIRED")
    return value


class DurableSemanticAnswerCacheStore:
    """CAS-backed SQLite candidate index. All outputs require later CACHE03 proof.

    The authority_guard is a *future* upstream, independently authenticated
    source/ACL snapshot check. It is not a signature or a cache HIT. Absence of
    this guard => no I/O. No method grants external source rights.
    """

    def __init__(
        self, db_path: str | Path, *,
        feature_enabled: bool = base.DEFAULT_NONPROD_CACHE_ENABLED,
        authority_guard: Callable[[Mapping[str, Any], str], bool] | None = None,
        integrity_key: bytes | None = None,
        fixture_only: bool = False,
        max_records: int = MAX_STORE_RECORDS,
        candidate_ranker: Callable[[str, str], float] | None = None,
    ) -> None:
        path = Path(db_path)
        if not path.is_absolute() or path.suffix != ".sqlite3":
            raise StoreInvariantError("ABSOLUTE_SQLITE3_PATH_REQUIRED")
        if type(feature_enabled) is not bool or type(fixture_only) is not bool:
            raise StoreInvariantError("BOOLEAN_FLAGS_REQUIRED")
        if type(max_records) is not int or not (1 <= max_records <= MAX_STORE_RECORDS):
            raise StoreInvariantError("BAD_MAX_RECORDS")
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 32:
            raise StoreInvariantError("IN_MEMORY_INTEGRITY_KEY_REQUIRED")
        if fixture_only:
            if os.environ.get("M27_CACHE02_FIXTURE_TEST_MODE") != "1":
                raise StoreInvariantError("FIXTURE_TEST_ENV_REQUIRED")
            # Fixture staging is permitted ONLY in system temp; never customer data.
            if not path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
                raise StoreInvariantError("FIXTURE_DISK_MUST_BE_TEMP")
        self.path = path
        self.feature_enabled = feature_enabled
        self.authority_guard = authority_guard
        self._key = integrity_key
        self._fixture_only = fixture_only
        self.max_records = max_records
        # Swappable lexical/vector candidate scorer; neither scorer nor ranking
        # grants HIT or bypasses hard SQL partition and B0 screen_candidate.
        self.candidate_ranker = candidate_ranker or self._lexical_score

    @staticmethod
    def _lexical_score(query: str, stored: str) -> float:
        if query == stored:
            return 1.0
        q, c = _tokens(query), _tokens(stored)
        return len(q & c) / len(q | c) if q and c else 0.0

    def _preflight(self, request: Mapping[str, Any], operation: str) -> dict | None:
        # Parse/route with NO filesystem access. BYPASS and disabled are zero I/O.
        r = base.parse_internal_request(dict(request))
        decision = base.plan_cache_request(r, feature_enabled=self.feature_enabled)
        expected = ("LOOKUP_REQUIRED" if operation == "read" else
                    ("LOOKUP_REQUIRED", "REGENERATE_NO_LOOKUP"))
        if (decision != expected if operation == "read" else decision not in expected):
            return None
        if self.authority_guard is None:
            return None
        # A guard is a required external authority dependency, not issuer proof.
        try:
            if self.authority_guard(r, operation) is not True:
                return None
        except Exception:
            return None
        return r

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Never grant group/world read to newly created local cache data.
        os.chmod(self.path.parent, 0o700)
        con = sqlite3.connect(str(self.path), timeout=8, isolation_level=None)
        if self.path.exists():
            os.chmod(self.path, 0o600)
        con.execute("PRAGMA busy_timeout=8000")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA secure_delete=ON")
        con.execute("PRAGMA journal_size_limit=1048576")
        con.execute("PRAGMA max_page_count=16384")  # nominal 64 MiB DB bound
        con.execute("""
            CREATE TABLE IF NOT EXISTS entries(
              key_sha TEXT PRIMARY KEY,
              partition_sha TEXT NOT NULL,
              identity_sha TEXT NOT NULL,
              revision_sha TEXT NOT NULL,
              payload BLOB NOT NULL,
              integrity_mac TEXT NOT NULL,
              expiry_utc TEXT NOT NULL,
              revocation_epoch INTEGER NOT NULL
            )""")
        con.execute("CREATE INDEX IF NOT EXISTS entries_partition ON entries(partition_sha)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS revocation(
              identity_sha TEXT PRIMARY KEY,
              epoch INTEGER NOT NULL CHECK(epoch >= 0)
            )""")
        return con

    def _mac(self, *, key: str, partition: str, revision: str, body: bytes) -> str:
        return hmac.new(self._key,
                        _json([key, partition, revision]) + body,
                        hashlib.sha256).hexdigest()

    def _check_row(self, request: dict, row: tuple, now: dt.datetime) -> dict | None:
        key, partition, rev, body, mac, epoch = row
        if len(body) > MAX_PAYLOAD_BYTES:
            return None
        if not hmac.compare_digest(self._mac(key=key, partition=partition,
                                             revision=rev, body=body), mac):
            return None
        try:
            record = json.loads(body)
            if (base.screen_candidate(request, record, now=now) != "PROVER_REQUIRED"
                    or _partition(request) != partition
                    or _record_key({**request, "question": record["question"]}) != key
                    or _sha(body) != rev
                    or record["policy"]["revocation_epoch"] != epoch):
                return None
            return record
        except (ValueError, TypeError, KeyError, base.CacheContractError):
            return None

    def lookup_candidates(
        self, request: Mapping[str, Any], *, limit: int = MAX_CANDIDATES,
        now: dt.datetime | None = None,
    ) -> list[Mapping[str, Any]]:
        """Bounded lexical discovery; every result is a CANDIDATE, NEVER HIT."""
        if type(limit) is not int or not (1 <= limit <= MAX_CANDIDATES):
            raise StoreInvariantError("CANDIDATE_LIMIT_BOUNDS")
        r = self._preflight(request, "read")
        if r is None or not self.path.exists():
            return []
        instant = _effective_now(now)
        partition = _partition(r)
        try:
            con = self._connect()
            try:
                rows = con.execute("""
                    SELECT key_sha,partition_sha,revision_sha,payload,integrity_mac,
                           revocation_epoch FROM entries
                    WHERE partition_sha=? ORDER BY key_sha LIMIT ?
                """, (partition, self.max_records)).fetchall()
                watermark_row = con.execute(
                    "SELECT epoch FROM revocation WHERE identity_sha=?",
                    (_identity_key(r),)).fetchone()
            finally:
                con.close()
        except (sqlite3.DatabaseError, OSError):
            return []
        watermark = watermark_row[0] if watermark_row else -1
        scored = []
        for row in rows:
            if row[5] < watermark:
                continue
            record = self._check_row(r, row, instant)
            if record is None:
                continue
            # No unqualified ranking can change the hard partition or ACL bound.
            try:
                score = self.candidate_ranker(
                    r["question"]["text"], record["question"]["text"])
                if (type(score) not in (int, float) or
                    not 0.0 <= score <= 1.0):
                    continue
            except Exception:
                continue
            if score >= 0.25:
                scored.append((score, row[0], record))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [item[2] for item in scored[:limit]]

    def compare_and_swap_verified(
        self, request: Mapping[str, Any], record: Mapping[str, Any],
        *, previous_revision: str | None,
    ) -> bool:
        """FAIL CLOSED: CACHE05 must supply a real qualified final-write authority.

        CacheStoreV1 currently accepts no authenticated final-write proof.
        It cannot truthfully treat SHA strings, fixture flags or caller booleans
        as credentials. Until CACHE05/H01 extend admission, always no I/O.
        """
        _ = (request, record, previous_revision)
        return False

    def _fixture_cas(self, request: Mapping[str, Any],
                     record: Mapping[str, Any], *,
                     previous_revision: str | None,
                     fail_at: str | None = None,
                     now: dt.datetime | None = None) -> bool:
        """Nonprod fixture ONLY; same durable CAS primitive future CACHE05 uses."""
        if not self._fixture_only:
            raise StoreInvariantError("FIXTURE_ONLY")
        r = self._preflight(request, "write")
        if r is None:
            return False
        c = base.parse_candidate(dict(record))
        instant = _effective_now(now)
        if (c["identity"] != r["identity"] or c["source"] != r["source"]
                or c["policy"] != r["policy"] or c["question"] != r["question"]
                or c["lifecycle"]["state"] != "ACTIVE"
                or c["lifecycle"]["revocation_epoch"] != r["policy"]["revocation_epoch"]
                or not (base._time(c["lifecycle"]["created_at"]) <= instant
                        < base._time(c["lifecycle"]["expires_at"]))):
            return False
        if previous_revision is not None and not re.fullmatch("[a-f0-9]{64}", previous_revision):
            raise StoreInvariantError("BAD_PREVIOUS_REVISION")
        body = _json(c)
        if len(body) > MAX_PAYLOAD_BYTES:
            return False
        partition, key = _partition(r), _record_key(r)
        revision = _sha(body)
        mac = self._mac(key=key, partition=partition, revision=revision, body=body)
        identity = _identity_key(r)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            if fail_at == "before_write":
                raise RuntimeError("INJECTED_CRASH_BEFORE_WRITE")
            watermark = con.execute(
                "SELECT epoch FROM revocation WHERE identity_sha=?", (identity,)
            ).fetchone()
            if watermark and c["policy"]["revocation_epoch"] < watermark[0]:
                con.rollback()
                return False
            existing = con.execute(
                "SELECT revision_sha FROM entries WHERE key_sha=?", (key,)
            ).fetchone()
            if existing and existing[0] == revision:
                con.commit()  # strictly identical idempotent replay
                return True
            if ((existing is None and previous_revision is not None) or
                (existing is not None and existing[0] != previous_revision)):
                con.rollback()
                return False
            if existing is None:
                count = con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                if count >= self.max_records:
                    con.rollback()
                    return False
            con.execute("""
                INSERT INTO entries(key_sha,partition_sha,identity_sha,revision_sha,
                                    payload,integrity_mac,expiry_utc,revocation_epoch)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(key_sha) DO UPDATE SET
                  revision_sha=excluded.revision_sha,
                  payload=excluded.payload,
                  integrity_mac=excluded.integrity_mac,
                  expiry_utc=excluded.expiry_utc,
                  revocation_epoch=excluded.revocation_epoch
            """, (key, partition, identity, revision, body, mac,
                  c["lifecycle"]["expires_at"], c["policy"]["revocation_epoch"]))
            if fail_at == "after_write_before_commit":
                raise RuntimeError("INJECTED_CRASH_BEFORE_COMMIT")
            con.commit()
            return True
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def invalidate_reachability(
        self, *, tenant_id: str, principal_id: str,
        source_manifest_sha256: str, revocation_epoch: int
    ) -> int:
        """Fail closed unless a *real external* authority requests invalidation.

        No caller-controlled tenant/epoch can become a trusted revocation.
        Actual fixture invalidation uses _fixture_invalidate below.
        """
        _ = (tenant_id, principal_id, source_manifest_sha256, revocation_epoch)
        return 0

    def _fixture_invalidate(
        self, *, tenant_id: str, principal_id: str,
        source_manifest_sha256: str, revocation_epoch: int,
    ) -> int:
        if not self._fixture_only or not self.feature_enabled:
            raise StoreInvariantError("FIXTURE_ONLY")
        if (not tenant_id or not principal_id or
                not re.fullmatch("[a-f0-9]{64}", source_manifest_sha256) or
                type(revocation_epoch) is not int or revocation_epoch < 0):
            raise StoreInvariantError("BAD_REVOCATION")
        identity = _sha(_json([tenant_id, principal_id, source_manifest_sha256]))
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute("SELECT epoch FROM revocation WHERE identity_sha=?",
                              (identity,)).fetchone()
            if old and revocation_epoch < old[0]:
                con.rollback()
                return 0
            con.execute("""
                INSERT INTO revocation(identity_sha,epoch) VALUES(?,?)
                ON CONFLICT(identity_sha) DO UPDATE SET
                epoch=MAX(revocation.epoch,excluded.epoch)
            """, (identity, revocation_epoch))
            cur = con.execute(
                "DELETE FROM entries WHERE identity_sha=? AND revocation_epoch < ?",
                (identity, revocation_epoch))
            con.commit()
            return cur.rowcount
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()
