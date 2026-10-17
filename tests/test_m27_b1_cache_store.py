"""B1-03 durable SQLite candidate tests: real OS files/processes, synthetic data ONLY."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/knowledge_engine"
sys.path.insert(0, str(SOURCE))
import m27_b0_cache_contracts as b0
import m27_b1_cache_store as cache02

A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
Z = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


def request(mode="AUTO", *, text="What does the agreement require?"):
    return {
        "schema_version": b0.SCHEMA_VERSION, "request_id": "fixture_request",
        "cache_mode": mode,
        "identity": {
            "tenant_id": "fixture_tenant_a", "principal_id": "fixture_principal_a",
            "auth_context_sha256": A, "authenticated": True,
        },
        "question": {
            "text": text, "language": "en", "task_kind": "QA",
            "intent_id": "contract-obligation", "obligations": ["citation", "rights"],
            "negated": False, "numeric_literals": [],
            "temporal_scope": "STATIC", "answer_type": "FACT",
        },
        "source": {
            "corpus_id": "fixture_corpus", "corpus_revision": "rev_1",
            "corpus_sha256": A, "source_manifest_sha256": B,
            "acl_sha256": C, "rights_sha256": D, "source_ids": ["source_1"],
        },
        "policy": {
            "policy_version": "v1", "policy_sha256": A,
            "verifier_version": "fixture-v1", "embedding_version": "LEXICAL_ONLY",
            "admission_version": "not-admitted", "revocation_epoch": 7,
        },
        "cache_window": {"requested_at": Z(NOW), "ttl_seconds": 120},
    }


def record(r, *, answer="The agreement requires a signature.", created=None, expiry=None):
    born = created or NOW - dt.timedelta(seconds=5)
    until = expiry or NOW + dt.timedelta(seconds=115)
    return {
        "schema_version": b0.SCHEMA_VERSION,
        "identity": copy.deepcopy(r["identity"]),
        "question": copy.deepcopy(r["question"]),
        "source": copy.deepcopy(r["source"]),
        "policy": copy.deepcopy(r["policy"]),
        "lifecycle": {
            "created_at": Z(born), "expires_at": Z(until),
            "ttl_seconds": 120, "revocation_epoch": r["policy"]["revocation_epoch"],
            "state": "ACTIVE",
        },
        "answer": answer,
        "citations": [{
            "source_id": "source_1", "source_sha256": A,
            "revision": "rev_1", "citation_sha256": C,
        }],
        "provenance": {
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "final_verifier_receipt_sha256": B,
            "source_verifier_receipt_sha256": C,
            "rights_receipt_sha256": D,
            "qualification_class": "FIXTURE_ONLY",
        },
    }


def rev(c):
    return hashlib.sha256(cache02._json(c)).hexdigest()


class DurableStoreTest(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.get("M27_CACHE02_FIXTURE_TEST_MODE")
        os.environ["M27_CACHE02_FIXTURE_TEST_MODE"] = "1"
        self.temp = tempfile.TemporaryDirectory(prefix="m27-b1-cache02-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private" / "candidates.sqlite3"
        self.key = b"synthetic-in-memory-test-key-only--not-a-production-secret!!"
        self.guard_calls = []
        self.guard = lambda r, op: self.guard_calls.append(op) or True
        self.db = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True,
            authority_guard=self.guard, integrity_key=self.key, fixture_only=True,
        )
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self.old_env is None:
            os.environ.pop("M27_CACHE02_FIXTURE_TEST_MODE", None)
        else:
            os.environ["M27_CACHE02_FIXTURE_TEST_MODE"] = self.old_env

    def stage(self, r=None, c=None, previous_revision=None, **kwargs):
        r = r or request()
        c = c or record(r)
        self.assertTrue(self.db._fixture_cas(
            r, c, previous_revision=previous_revision, now=NOW, **kwargs))
        return r, c

    def test_01_default_disabled_zero_io_bypass_zero_io(self):
        absent = self.path.parent / "off.sqlite3"
        disabled = cache02.DurableSemanticAnswerCacheStore(
            absent, integrity_key=self.key, authority_guard=self.guard)
        self.assertEqual(disabled.lookup_candidates(request()), [])
        self.assertFalse(disabled.compare_and_swap_verified(
            request(), record(request()), previous_revision=None))
        self.assertFalse(absent.exists())
        no_io = cache02.DurableSemanticAnswerCacheStore(
            absent, feature_enabled=True, authority_guard=self.guard,
            integrity_key=self.key, fixture_only=True)
        self.assertEqual(no_io.lookup_candidates(request("BYPASS")), [])
        self.assertFalse(no_io._fixture_cas(
            request("BYPASS"), record(request("BYPASS")), previous_revision=None, now=NOW))
        self.assertFalse(absent.exists())
        self.assertEqual(self.guard_calls, [])

    def test_02_untrusted_authority_denied_no_db_creation(self):
        blocked = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=self.key)
        self.assertEqual(blocked.lookup_candidates(request()), [])
        self.assertFalse(blocked.compare_and_swap_verified(
            request(), record(request()), previous_revision=None))
        self.assertFalse(self.path.exists())
        denied = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=self.key,
            authority_guard=lambda _r, _o: False, fixture_only=True)
        self.assertFalse(denied._fixture_cas(
            request(), record(request()), previous_revision=None, now=NOW))
        self.assertFalse(self.path.exists())

    def test_03_disk_restart_and_candidate_not_hit(self):
        r, c = self.stage()
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        restarted = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, authority_guard=lambda r, op: True,
            integrity_key=self.key, fixture_only=True)
        results = restarted.lookup_candidates(r, now=NOW)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["answer"], c["answer"])
        self.assertEqual(b0.screen_candidate(r, results[0], now=NOW), "PROVER_REQUIRED")
        self.assertEqual(b0.verify_hit_contract(r, results[0], None, now=NOW),
                         "HIT_NOT_ADMITTED")
        self.assertFalse(restarted.compare_and_swap_verified(
            r, c, previous_revision=rev(c)))

    def test_04_actual_separate_interpreter_restart(self):
        r, c = self.stage()
        script = '''
import datetime as dt, json, sys
sys.path.insert(0, sys.argv[1])
import m27_b1_cache_store as s
p=sys.argv[2]
k=bytes.fromhex(sys.argv[3])
req=json.loads(sys.argv[4])
at=dt.datetime.fromisoformat(sys.argv[5])
v=s.DurableSemanticAnswerCacheStore(p,feature_enabled=True,authority_guard=lambda r,o: True,integrity_key=k,fixture_only=True)
print(json.dumps([x["answer"] for x in v.lookup_candidates(req,now=at)]))
'''
        env = {**os.environ, "M27_CACHE02_FIXTURE_TEST_MODE": "1"}
        run = subprocess.run(
            [sys.executable, "-c", script, str(SOURCE), str(self.path),
             self.key.hex(), json.dumps(r), NOW.isoformat()],
            capture_output=True, text=True, check=True, timeout=12, env=env)
        self.assertEqual(json.loads(run.stdout), [c["answer"]])

    def test_05_refresh_no_old_read_atomic_replacement(self):
        r, c = self.stage()
        newer = record(r, answer="The agreement requires a countersignature.")
        refresh = request("REFRESH")
        self.assertEqual(self.db.lookup_candidates(refresh, now=NOW), [])
        self.assertFalse(self.db._fixture_cas(
            refresh, newer, previous_revision=A, now=NOW))
        self.assertEqual(self.db.lookup_candidates(r, now=NOW)[0]["answer"], c["answer"])
        self.assertTrue(self.db._fixture_cas(
            refresh, newer, previous_revision=rev(c), now=NOW))
        self.assertEqual(self.db.lookup_candidates(r, now=NOW)[0]["answer"], newer["answer"])
        self.assertTrue(self.db._fixture_cas(
            refresh, newer, previous_revision=rev(c), now=NOW))
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 1)

    def test_06_real_crash_before_commit_rollback(self):
        r, c = self.stage()
        script = '''
import os,sqlite3,signal,sys
db=sys.argv[1]
con=sqlite3.connect(db, isolation_level=None,timeout=4)
con.execute("PRAGMA journal_mode=WAL")
con.execute("BEGIN IMMEDIATE")
con.execute("UPDATE entries SET payload=?",(b"uncommitted-malicious",))
os.kill(os.getpid(),signal.SIGKILL)
'''
        proc = subprocess.run([sys.executable, "-c", script, str(self.path)],
                              capture_output=True, timeout=12)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.db.lookup_candidates(r, now=NOW)[0]["answer"], c["answer"])
        self.assertEqual(sqlite3.connect(self.path).execute(
            "PRAGMA integrity_check").fetchone()[0], "ok")

    def test_07_injected_crash_and_cas_content_preserved(self):
        r, c = self.stage()
        newer = record(r, answer="Replacement after restart.")
        for fault in ("before_write", "after_write_before_commit"):
            with self.subTest(fault=fault), self.assertRaisesRegex(
                RuntimeError, "INJECTED_CRASH"):
                self.db._fixture_cas(r, newer, previous_revision=rev(c),
                                     fail_at=fault, now=NOW)
            self.assertEqual(self.db.lookup_candidates(r, now=NOW)[0]["answer"],
                             c["answer"])
        self.assertFalse(self.db._fixture_cas(
            r, newer, previous_revision=A, now=NOW))

    def test_08_wrong_tenant_principal_authctx_and_source_versions(self):
        r, c = self.stage()
        for section, key, value in (
            ("identity", "tenant_id", "fixture_tenant_b"),
            ("identity", "principal_id", "fixture_principal_b"),
            ("identity", "auth_context_sha256", B),
            ("source", "corpus_sha256", B),
            ("source", "source_manifest_sha256", A),
            ("source", "acl_sha256", A),
            ("source", "rights_sha256", B),
            ("source", "corpus_revision", "rev_2"),
            ("policy", "policy_version", "v2"),
            ("policy", "policy_sha256", B),
            ("policy", "revocation_epoch", 8),
            ("policy", "verifier_version", "other"),
            ("policy", "embedding_version", "other"),
            ("policy", "admission_version", "other"),
        ):
            with self.subTest(section=section, key=key):
                other = copy.deepcopy(r)
                other[section][key] = value
                self.assertEqual(self.db.lookup_candidates(other, now=NOW), [])
        self.assertEqual(len(self.db.lookup_candidates(r, now=NOW)), 1)

    def test_09_wrong_negation_numbers_temporal_task_and_locale(self):
        r, c = self.stage()
        for section, key, value in (
            ("question", "negated", True),
            ("question", "numeric_literals", ["12"]),
            ("question", "temporal_scope", "LIVE"),
            ("question", "temporal_scope", "RELATIVE"),
            ("question", "answer_type", "COMPARISON"),
            ("question", "language", "zh-TW"),
            ("question", "obligations", ["citation"]),
            ("question", "task_kind", "Action"),
            ("question", "intent_id", "other"),
        ):
            with self.subTest(key=key, value=value):
                other = copy.deepcopy(r)
                other[section][key] = value
                self.assertEqual(self.db.lookup_candidates(other, now=NOW), [])

    def test_10_lexical_near_match_is_only_candidate(self):
        r, c = self.stage()
        near = request(text="What does the agreement require for a signature?")
        result = self.db.lookup_candidates(near, now=NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["question"]["text"], c["question"]["text"])
        self.assertEqual(b0.screen_candidate(near, result[0], now=NOW),
                         "PROVER_REQUIRED")
        self.assertEqual(b0.verify_hit_contract(near, result[0], None, now=NOW),
                         "HIT_NOT_ADMITTED")

    def test_11_expiry_stale_and_corruption_failclosed(self):
        r, c = self.stage()
        self.assertEqual(self.db.lookup_candidates(
            r, now=NOW + dt.timedelta(seconds=121)), [])
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE entries SET payload=?", (b"tampered-answer",))
        self.assertEqual(self.db.lookup_candidates(r, now=NOW), [])
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE entries SET integrity_mac=?", ("f"*64,))
        self.assertEqual(self.db.lookup_candidates(r, now=NOW), [])

    def test_12_revocation_durable_and_monotonic(self):
        r, c = self.stage()
        self.assertEqual(self.db.invalidate_reachability(
            tenant_id=r["identity"]["tenant_id"],
            principal_id=r["identity"]["principal_id"],
            source_manifest_sha256=B, revocation_epoch=8), 0)
        self.assertEqual(self.db._fixture_invalidate(
            tenant_id=r["identity"]["tenant_id"],
            principal_id=r["identity"]["principal_id"],
            source_manifest_sha256=B, revocation_epoch=8), 1)
        self.assertEqual(self.db.lookup_candidates(r, now=NOW), [])
        self.assertFalse(self.db._fixture_cas(r, c, previous_revision=None, now=NOW))
        self.assertEqual(self.db._fixture_invalidate(
            tenant_id=r["identity"]["tenant_id"],
            principal_id=r["identity"]["principal_id"],
            source_manifest_sha256=B, revocation_epoch=7), 0)
        again = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=self.key,
            authority_guard=lambda r, op: True, fixture_only=True)
        self.assertEqual(again.lookup_candidates(r, now=NOW), [])

    def test_13_actual_cas_race_multi_process(self):
        r, first = self.stage()
        a = record(r, answer="Concurrent A.")
        b = record(r, answer="Concurrent B.")
        script = '''
import datetime as dt,json,sys
sys.path.insert(0,sys.argv[1])
import m27_b1_cache_store as s
req=json.loads(sys.argv[3]); rec=json.loads(sys.argv[4])
db=s.DurableSemanticAnswerCacheStore(sys.argv[2],feature_enabled=True,
 authority_guard=lambda r,o: True,integrity_key=bytes.fromhex(sys.argv[5]),fixture_only=True)
print(int(db._fixture_cas(req,rec,previous_revision=sys.argv[6],
 now=dt.datetime.fromisoformat(sys.argv[7]))))
'''
        env = {**os.environ, "M27_CACHE02_FIXTURE_TEST_MODE": "1"}
        procs = [
            subprocess.Popen([sys.executable, "-c", script, str(SOURCE),
                str(self.path), json.dumps(r), json.dumps(x), self.key.hex(),
                rev(first), NOW.isoformat()], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, env=env)
            for x in (a, b)
        ]
        outcomes = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=14)
            self.assertEqual(proc.returncode, 0, stderr)
            outcomes.append(int(stdout.strip()))
        self.assertEqual(sorted(outcomes), [0, 1])
        results = self.db.lookup_candidates(r, now=NOW)
        self.assertEqual(len(results), 1)
        self.assertIn(results[0]["answer"], (a["answer"], b["answer"]))

    def test_14_invalid_fixture_and_size_limit(self):
        with self.assertRaises(cache02.StoreInvariantError):
            cache02.DurableSemanticAnswerCacheStore(
                "relative.sqlite3", integrity_key=self.key)
        with self.assertRaises(cache02.StoreInvariantError):
            cache02.DurableSemanticAnswerCacheStore(
                self.path, integrity_key=b"x")
        outside = Path.home() / "never-write-cache02-fixture.sqlite3"
        with self.assertRaises(cache02.StoreInvariantError):
            cache02.DurableSemanticAnswerCacheStore(
                outside, integrity_key=self.key, fixture_only=True)
        with self.assertRaises(cache02.StoreInvariantError):
            self.db.lookup_candidates(request(), limit=100)
        r = request()
        # B0 itself forbids oversized answer bodies before any DB I/O.
        big = record(r, answer="Z" * 64001)
        with self.assertRaises(b0.CacheContractError):
            self.db._fixture_cas(r, big, previous_revision=None, now=NOW)
        self.assertFalse(self.path.exists())
        bounded = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=self.key,
            authority_guard=self.guard, fixture_only=True, max_records=1)
        c = record(r)
        self.assertTrue(bounded._fixture_cas(r, c, previous_revision=None, now=NOW))
        another = request(text="What does an annex require?")
        self.assertFalse(bounded._fixture_cas(
            another, record(another), previous_revision=None, now=NOW))

    def test_15_no_wrong_record_source_or_status_staged(self):
        r = request()
        for corrupt in (
            lambda c: c["identity"].update(tenant_id="wrong"),
            lambda c: c["source"].update(rights_sha256=A),
            lambda c: c["lifecycle"].update(state="REVOKED"),
            lambda c: c["provenance"].update(answer_sha256=D),
        ):
            with self.subTest(corrupt=corrupt):
                c = record(r)
                corrupt(c)
                try:
                    verdict = self.db._fixture_cas(r, c, previous_revision=None, now=NOW)
                    self.assertFalse(verdict)
                except b0.CacheContractError:
                    pass
        self.assertFalse(self.path.exists())

    def test_16_replaceable_ranker_cannot_override_partition(self):
        r, c = self.stage()
        malicious_ranker = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=self.key,
            authority_guard=self.guard, fixture_only=True,
            candidate_ranker=lambda query, stored: 1.0)
        self.assertEqual(len(malicious_ranker.lookup_candidates(r, now=NOW)), 1)
        other = copy.deepcopy(r)
        other["identity"]["tenant_id"] = "another_tenant"
        self.assertEqual(malicious_ranker.lookup_candidates(other, now=NOW), [])
        invalid_ranker = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=self.key,
            authority_guard=self.guard, fixture_only=True,
            candidate_ranker=lambda query, stored: float("nan"))
        self.assertEqual(invalid_ranker.lookup_candidates(r, now=NOW), [])
        wrong_key = cache02.DurableSemanticAnswerCacheStore(
            self.path, feature_enabled=True, integrity_key=b"different-test-secret-012345678901234567890123",
            authority_guard=self.guard, fixture_only=True)
        self.assertEqual(wrong_key.lookup_candidates(r, now=NOW), [])


if __name__ == "__main__":
    unittest.main()
