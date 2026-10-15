"""A07 true SQLite/file and separate OS-process security acceptance."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from a07_memory import ABI, Denied, MemoryStore

FUTURE = 2_000_000_000


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="a07_nonprod_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = MemoryStore(self.root)
        self.store.grant_source(tenant="A", principal="alice", source="s1",
                                purpose="research", payload=b"FIRST_SOURCE_FIXTURE", expires=FUTURE,consent=True)
        self.store.grant_source(tenant="A", principal="alice", source="s2",
                                purpose="research", payload=b"SECOND_SOURCE_FIXTURE", expires=FUTURE,consent=True)
        self.store.grant_source(tenant="B", principal="bob", source="s1",
                                purpose="research", payload=b"OTHER_TENANT_FIXTURE", expires=FUTURE,consent=True)

    def make(self, memid="m1", sources=("s1","s2"), expires=FUTURE):
        self.store.write_memory(tenant="A", principal="alice", memid=memid,
                                summary="Sanitized research candidate", sources=sources,
                                expires=expires)
        return self.store.candidate(tenant="A", principal="alice", memid=memid)

    def cache(self, key="c1", memid="m1"):
        self.store.put_cache(tenant="A", principal="alice", memid=memid,
                             key=key, payload=b"DERIVED_FIXTURE", expires=FUTURE)

    def denied(self, fn):
        with self.assertRaises(Denied):
            fn()

    def test_01_multi_source_durable_positive(self):
        candidate=self.make()
        self.assertEqual(candidate["abi"],ABI)
        self.assertEqual(len(candidate["source_lineage"]),2)
        self.assertFalse(candidate["citation_eligible"])
        self.assertFalse(candidate["knowledge_authority"])
        self.assertFalse(candidate["answer_context_enabled"])
        self.cache()
        again=MemoryStore(self.root)
        self.assertEqual(again.query_cache(tenant="A", principal="alice", key="c1"),
                         b"DERIVED_FIXTURE")
        self.assertEqual(again.read_source(tenant="A",principal="alice",source="s2"),
                         b"SECOND_SOURCE_FIXTURE")
        self.assertEqual(again.candidate(tenant="A",principal="alice",memid="m1"),
                         candidate)

    def test_02_consent_required(self):
        self.denied(lambda:self.store.grant_source(
            tenant="A",principal="alice",source="s3",purpose="research",
            payload=b"X",expires=FUTURE,consent=False))
        self.denied(lambda:self.store.write_memory(tenant="A",principal="alice",
            memid="new",summary="X",sources=("s3",),expires=FUTURE))

    def test_03_cross_tenant_and_principal_denials(self):
        self.make()
        self.cache()
        self.denied(lambda:self.store.read_source(tenant="B",principal="bob",source="s2"))
        self.denied(lambda:self.store.read_source(tenant="A",principal="bob",source="s1"))
        self.denied(lambda:self.store.candidate(tenant="B",principal="bob",memid="m1"))
        self.denied(lambda:self.store.candidate(tenant="A",principal="bob",memid="m1"))
        self.denied(lambda:self.store.query_cache(tenant="B",principal="bob",key="c1"))
        self.denied(lambda:self.store.query_cache(tenant="A",principal="bob",key="c1"))

    def test_04_source_revoke_cascades_cache_and_memory(self):
        self.make()
        self.cache()
        receipt=self.store.revoke_source(tenant="A",principal="alice",source="s1")
        self.assertTrue(receipt["tombstone_durable"])
        self.assertFalse(receipt["external_backups_erased"])
        self.assertFalse(receipt["physical_sqlite_erasure_proven"])
        self.denied(lambda:self.store.read_source(tenant="A",principal="alice",source="s1"))
        self.denied(lambda:self.store.candidate(tenant="A",principal="alice",memid="m1"))
        self.denied(lambda:self.store.query_cache(tenant="A",principal="alice",key="c1"))
        self.assertFalse((self.root/"blobs"/"A"/"s1.bin").exists())
        self.assertEqual(self.store.read_source(tenant="B",principal="bob",source="s1"),
                         b"OTHER_TENANT_FIXTURE")
        self.assertEqual(MemoryStore(self.root).recover_cleanup(tenant="A")["local_unlinked"],0)

    def test_05_revoking_one_source_invalidates_multi_source_derived(self):
        self.make()
        self.cache()
        self.store.write_memory(tenant="A",principal="alice",memid="m2",
                                summary="Independent",sources=("s2",),expires=FUTURE)
        self.store.revoke_source(tenant="A",principal="alice",source="s1")
        self.denied(lambda:self.store.candidate(tenant="A",principal="alice",memid="m1"))
        self.assertEqual(self.store.candidate(tenant="A",principal="alice",memid="m2")["summary"],
                         "Independent")

    def test_06_memory_delete_and_stale_replay(self):
        self.make()
        self.cache()
        self.store.delete_memory(tenant="A",principal="alice",memid="m1")
        reopened=MemoryStore(self.root)
        self.denied(lambda:reopened.candidate(tenant="A",principal="alice",memid="m1"))
        self.denied(lambda:reopened.query_cache(tenant="A",principal="alice",key="c1"))
        self.denied(lambda:reopened.write_memory(tenant="A",principal="alice",memid="m1",
                         summary="Recreated",sources=("s2",),expires=FUTURE))
        self.assertEqual(reopened.read_source(tenant="A",principal="alice",source="s2"),
                         b"SECOND_SOURCE_FIXTURE")

    def test_07_consent_source_id_not_reused_after_revoke(self):
        self.store.revoke_source(tenant="A",principal="alice",source="s1")
        self.denied(lambda:self.store.grant_source(tenant="A",principal="alice",source="s1",
                         purpose="research",payload=b"old bytes",expires=FUTURE,consent=True))

    def test_08_expired_memory_negative(self):
        self.make(expires=int(time.time())+1)
        time.sleep(1.15)
        self.denied(lambda:MemoryStore(self.root).candidate(
            tenant="A",principal="alice",memid="m1"))

    def test_09_expired_source_negative(self):
        self.store.grant_source(tenant="A",principal="alice",source="short",
                                purpose="research",payload=b"T",expires=int(time.time())+1,
                                consent=True)
        self.store.write_memory(tenant="A",principal="alice",memid="temporary",
                                summary="Temporary",sources=("short",),expires=FUTURE)
        time.sleep(1.15)
        self.denied(lambda:MemoryStore(self.root).candidate(
            tenant="A",principal="alice",memid="temporary"))
        self.denied(lambda:MemoryStore(self.root).read_source(
            tenant="A",principal="alice",source="short"))

    def test_10_restorable_positive_snapshot(self):
        self.make()
        self.cache()
        self.store.snapshot(snap="cp1")
        self.store.restore(snap="cp1")
        self.assertEqual(self.store.query_cache(tenant="A",principal="alice",key="c1"),
                         b"DERIVED_FIXTURE")

    def test_11_revoked_snapshot_cannot_restore(self):
        self.make()
        self.cache()
        self.store.snapshot(snap="cp1")
        self.store.revoke_source(tenant="A",principal="alice",source="s1")
        self.denied(lambda:MemoryStore(self.root).restore(snap="cp1"))
        self.assertFalse((self.root/"snapshots"/"cp1.memory.sqlite").exists())
        self.assertFalse((self.root/"snapshots"/"cp1.cache.sqlite").exists())

    def test_12_forced_old_data_rollback_does_not_override_guard(self):
        self.make()
        self.cache()
        prior=self.root/"manual_old_memory.sqlite"
        oldcache=self.root/"manual_old_cache.sqlite"
        shutil.copy2(self.store.data,prior)
        shutil.copy2(self.store.cache,oldcache)
        self.store.revoke_source(tenant="A",principal="alice",source="s1")
        # Simulate a hostile/buggy file-level rollback, not a supported restore.
        shutil.copy2(prior,self.store.data)
        shutil.copy2(oldcache,self.store.cache)
        reopened=MemoryStore(self.root)
        self.denied(lambda:reopened.candidate(tenant="A",principal="alice",memid="m1"))
        self.denied(lambda:reopened.query_cache(tenant="A",principal="alice",key="c1"))

    def test_13_deleted_memory_rollback_denied(self):
        self.make()
        old=self.root/"old_memory.sqlite"
        shutil.copy2(self.store.data,old)
        self.store.delete_memory(tenant="A",principal="alice",memid="m1")
        shutil.copy2(old,self.store.data)
        self.denied(lambda:MemoryStore(self.root).candidate(
            tenant="A",principal="alice",memid="m1"))

    def test_14_no_promotion_even_when_valid(self):
        self.make()
        self.assertFalse(self.store.candidate(tenant="A",principal="alice",memid="m1")
                         ["can_promote_to_knowledge"])
        self.denied(lambda:self.store.to_evidence(
            tenant="A",principal="alice",memid="m1"))
        self.store.revoke_source(tenant="A",principal="alice",source="s1")
        self.denied(lambda:self.store.to_evidence(
            tenant="A",principal="alice",memid="m1"))

    def test_15_integrity_tampering_fail_closed(self):
        path=self.root/"blobs"/"A"/"s1.bin"
        path.write_bytes(b"MALICIOUS_TAMPER")
        self.denied(lambda:self.store.read_source(tenant="A",principal="alice",source="s1"))

    def test_16_os_process_pause_revoke_resume(self):
        self.make()
        self.cache()
        ready=self.root/"ready"
        resume=self.root/"resume"
        child=Path(__file__).with_name("a07_child.py")
        proc=subprocess.Popen([sys.executable,"-B",str(child),str(self.root),
                               str(ready),str(resume)],stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,text=True,env={**os.environ,
                               "PYTHONDONTWRITEBYTECODE":"1"})
        try:
            limit=time.monotonic()+10
            while not ready.exists() and proc.poll() is None and time.monotonic()<limit:
                time.sleep(.025)
            self.assertTrue(ready.exists(),f"child exited {proc.poll()}")
            self.store.revoke_source(tenant="A",principal="alice",source="s1")
            resume.touch()
            out,err=proc.communicate(timeout=10)
            self.assertEqual(proc.returncode,0, (out,err))
            self.assertIn("CHILD_RESTART_REVOKED_DENIED=3",out)
            print(f"OS_REVOCATION_WITNESS pid={proc.pid} child_exit={proc.returncode} "
                  "cross_process_denials=3")
            self.assertNotIn("FIRST_SOURCE_FIXTURE",out+err)
            self.assertNotIn("DERIVED_FIXTURE",out+err)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)

    def test_17_negative_input_and_class(self):
        self.denied(lambda:self.store.write_memory(tenant="A",principal="alice",
                    memid="forbidden",summary="X",sources=("s1",),expires=FUTURE,
                    memory_class="EVIDENCE"))
        self.denied(lambda:self.store.read_source(tenant="A",principal="alice",source="../s1"))
        self.denied(lambda:self.store.grant_source(tenant="A",principal="alice",source="bad",
                         purpose="research",payload=b"Z",expires=0,consent=True))

    def test_18_audit_and_no_external_remote_claim(self):
        self.make()
        self.cache()
        self.store.delete_memory(tenant="A",principal="alice",memid="m1")
        self.assertEqual(self.store.audit()["deleted_memories"],1)
        receipt=self.store.recover_cleanup(tenant="A")
        self.assertFalse(receipt["external_backups_erased"])
        self.assertFalse(receipt["physical_sqlite_erasure_proven"])

    def test_19_snapshot_bytes_tamper_denied(self):
        self.make()
        self.cache()
        self.store.snapshot(snap="cp1")
        snap=self.root/"snapshots"/"cp1.cache.sqlite"
        with snap.open("ab") as handle:
            handle.write(b"tamper")
        self.denied(lambda:self.store.restore(snap="cp1"))
        self.assertEqual(self.store.query_cache(tenant="A",principal="alice",key="c1"),
                         b"DERIVED_FIXTURE")

    def test_20_crash_during_cleanup_no_regrant(self):
        from unittest.mock import patch
        self.make()
        self.cache()
        with patch.object(self.store, "_blob", side_effect=OSError("SIMULATED_UNLINK_FAIL")):
            with self.assertRaises(OSError):
                self.store.revoke_source(tenant="A",principal="alice",source="s1")
        reopened=MemoryStore(self.root)
        self.denied(lambda:reopened.read_source(tenant="A",principal="alice",source="s1"))
        self.denied(lambda:reopened.query_cache(tenant="A",principal="alice",key="c1"))
        self.assertTrue((self.root/"blobs"/"A"/"s1.bin").exists())
        receipt=reopened.recover_cleanup(tenant="A")
        self.assertEqual(receipt["local_unlinked"],1)
        self.assertFalse((self.root/"blobs"/"A"/"s1.bin").exists())

    def test_21_forged_lineage_generation_fail_closed(self):
        import sqlite3
        self.make()
        with sqlite3.connect(self.store.data) as db:
            db.execute("UPDATE lineage SET version=0 WHERE tenant='A' AND memid='m1'")
        self.denied(lambda:MemoryStore(self.root).candidate(
            tenant="A",principal="alice",memid="m1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
