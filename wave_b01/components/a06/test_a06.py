#!/usr/bin/env python3
"""A06 regression: independent OS death, rollback, UNKNOWN effect, ACL and exact-source negatives."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import runner

HERE = Path(__file__).resolve().parent
PY = sys.executable

def contract(run, **updates):
    c = {
        "run_id": run, "tenant": "tenant-a", "actor": "owner-researcher",
        "goal": "What is the I37 task-native mission and current AR08 coding gate?",
        "deadline": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "budget": {"max_source_reads": 3, "max_action_attempts": 1},
        "sources": list(runner.ALLOWED),
        "rights": ["read-firstparty", "write-own-observation"],
        "outcome": "verified-research-and-reversible-observation", "version": "a06-v1"
    }
    c.update(updates)
    return c

def verify_external(db, run):
    return subprocess.run([PY, str(HERE / "verifier.py"), "--db", str(db), "--run-id", run],
                          capture_output=True, text=True)

class A06Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (HERE / "evidence" / "raw").mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="a06-tests-")
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "run.sqlite3"
        self.con = runner.connection(self.db)
        self.addCleanup(self.con.close)
        self.run = "a06-" + uuid.uuid4().hex[:20]
        self.c = contract(self.run)

    def admit(self):
        runner.admission(self.con, self.c)

    def complete(self):
        self.admit()
        self.assertEqual(runner.run_loop(self.con, self.run), "VERIFIED")

    def test_01_complete_real_persisted_research_and_effect(self):
        self.complete()
        r = verify_external(self.db, self.run)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["source_count"], 3)
        self.assertIn("Coding", runner.artifact_path(self.run).read_text("utf-8"))
        events = self.con.execute("SELECT event FROM journal ORDER BY seq").fetchall()
        self.assertGreaterEqual(len(events), 10)
        self.assertEqual(self.con.execute("SELECT attempts FROM actions").fetchone()[0], 1)
        self.assertEqual(runner.read_observation(self.run)["revision"], 1)

    def test_02_real_os_sigkill_resume_same_runid(self):
        self.admit()
        cmd = [PY, "-u", str(HERE / "runner.py"), "run", "--db", str(self.db),
               "--run-id", self.run, "--hold-at", "GATHERED_2"]
        child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        out = []
        try:
            for _ in range(8):
                line = child.stdout.readline()
                if not line:
                    break
                out.append(line)
                if "HOLD_POINT GATHERED_2" in line:
                    break
            self.assertTrue(any("HOLD_POINT" in x for x in out), "".join(out))
            os.kill(child.pid, signal.SIGKILL)
            child.wait(timeout=10)
            self.assertEqual(child.returncode, -signal.SIGKILL)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            if child.stdout:
                child.stdout.close()
            if child.stderr:
                child.stderr.close()
        trace = HERE / "evidence" / "raw" / "os_sigkill_real.txt"
        trace.write_text(f"child_pid={child.pid} returncode={child.returncode}\n" + "".join(out),
                         encoding="utf-8")
        res = subprocess.run([PY, str(HERE / "runner.py"), "run", "--db", str(self.db),
                              "--run-id", self.run], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("RESULT VERIFIED", res.stdout)
        self.assertEqual(verify_external(self.db, self.run).returncode, 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM journal WHERE event='ADMITTED'").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT attempts FROM actions").fetchone()[0], 1)

    def test_03_timeout_unknown_reconcile_never_reissues_effect(self):
        self.admit()
        cmd = [PY, str(HERE / "runner.py"), "run", "--db", str(self.db),
               "--run-id", self.run, "--inject-unknown"]
        crashed = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(crashed.returncode, 73, crashed.stdout + crashed.stderr)
        self.assertEqual(runner.get_run(self.con, self.run)[1], "ACTION_PREPARED")
        self.assertEqual(self.con.execute("SELECT attempts,status FROM actions").fetchone(), (1, "UNKNOWN"))
        self.assertEqual(runner.read_observation(self.run)["revision"], 1)
        resumed = subprocess.run([PY, str(HERE / "runner.py"), "run", "--db", str(self.db),
                                  "--run-id", self.run], capture_output=True, text=True)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(runner.get_run(self.con, self.run)[1], "VERIFIED")
        self.assertEqual(self.con.execute("SELECT attempts,status FROM actions").fetchone(),
                         (1, "RECONCILED"))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM journal WHERE event='RECONCILED_BY_OBSERVATION'").fetchone()[0], 1)
        self.assertEqual(verify_external(self.db, self.run).returncode, 0)
        (HERE / "evidence" / "raw" / "unknown_effect_real.txt").write_text(
            f"crash_rc={crashed.returncode}; prepared_with_1_attempt; resume_rc={resumed.returncode}\n"
            + crashed.stdout + "\n---RESUME---\n" + resumed.stdout, encoding="utf-8")

    def test_04_unknown_effect_without_observed_result_must_hold(self):
        self.admit()
        while runner.get_run(self.con, self.run)[1] != "ACTION_PREPARED":
            runner.step(self.con, self.run)
        self.con.execute("UPDATE actions SET attempts=1,status='UNKNOWN' WHERE run_id=?", (self.run,))
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_EFFECT_NOT_REPLAYED"):
            runner.step(self.con, self.run)
        self.assertEqual(self.con.execute("SELECT attempts FROM actions").fetchone()[0], 1)
        self.assertEqual(runner.read_observation(self.run)["revision"], 0)
        self.assertEqual(runner.get_run(self.con, self.run)[1], "ACTION_PREPARED")

    def test_05_cancel_is_terminal_without_effect(self):
        self.admit()
        runner.step(self.con, self.run)
        runner.stage(self.con, self.run, "CANCELED", "CANCELLED_NO_FURTHER_EFFECT")
        self.assertEqual(runner.run_loop(self.con, self.run), "CANCELED")
        self.assertIsNone(self.con.execute("SELECT status FROM actions").fetchone())
        self.assertNotEqual(verify_external(self.db, self.run).returncode, 0)

    def test_06_revoke_mid_execution_fails_closed(self):
        self.admit()
        runner.step(self.con, self.run)
        self.con.execute("INSERT INTO revoked VALUES(?,?)", ("CHARTER", runner.now()))
        self.assertEqual(runner.run_loop(self.con, self.run), "ABSTAINED")
        self.assertIsNone(self.con.execute("SELECT status FROM actions").fetchone())
        self.assertNotEqual(verify_external(self.db, self.run).returncode, 0)

    def test_07_cross_tenant_denied_before_admission(self):
        self.c["tenant"] = "tenant-b"
        with self.assertRaisesRegex(PermissionError, "TENANT"):
            self.admit()
        self.assertEqual(self.con.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_08_ambiguous_firstparty_source_abstain(self):
        docdir = Path(self.temp.name) / "sources"
        docdir.mkdir()
        old_root, old_manifest = runner.SOURCE_ROOT, runner.MANIFEST
        manifest = copy.deepcopy(runner.manifest())
        for sid in runner.ALLOWED:
            original = (old_root / (sid + ".md")).read_bytes()
            if sid == "DELIVERY":
                extra = "\n" + runner.NEEDLES["DELIVERY"] + "\n"
                original += extra.encode("utf-8")
            (docdir / (sid + ".md")).write_bytes(original)
            manifest[sid]["sha256"] = hashlib.sha256(original).hexdigest()
        mf = Path(self.temp.name) / "manifest.json"
        mf.write_text(json.dumps(manifest))
        runner.SOURCE_ROOT, runner.MANIFEST = docdir, mf
        try:
            self.admit()
            self.assertEqual(runner.run_loop(self.con, self.run), "ABSTAINED")
            self.assertIn("SOURCE_AMBIGUOUS", self.con.execute(
                "SELECT body FROM journal WHERE event='SAFE_ABSTAIN'").fetchone()[0])
        finally:
            runner.SOURCE_ROOT, runner.MANIFEST = old_root, old_manifest

    def test_09_source_byte_tamper_fails_sha(self):
        docdir = Path(self.temp.name) / "sources"
        docdir.mkdir()
        for sid in runner.ALLOWED:
            data = (runner.SOURCE_ROOT / (sid + ".md")).read_bytes()
            (docdir / (sid + ".md")).write_bytes(data + (b"tampered" if sid == "DELIVERY" else b""))
        old_root = runner.SOURCE_ROOT
        runner.SOURCE_ROOT = docdir
        try:
            self.admit()
            self.assertEqual(runner.run_loop(self.con, self.run), "ABSTAINED")
            self.assertIn("SOURCE_HASH_MISMATCH", self.con.execute(
                "SELECT body FROM journal WHERE event='SAFE_ABSTAIN'").fetchone()[0])
        finally:
            runner.SOURCE_ROOT = old_root

    def test_10_independent_verifier_rejects_artifact_tamper(self):
        self.complete()
        p = runner.artifact_path(self.run)
        obj = json.loads(p.read_text("utf-8"))
        obj["evidence"][0]["quote"] = "UNSUPPORTED INVENTED FACT"
        p.write_text(json.dumps(obj))
        r = verify_external(self.db, self.run)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["verdict"], "FAIL")

    def test_11_precondition_drift_does_not_perform_write(self):
        self.admit()
        while runner.get_run(self.con, self.run)[1] != "RESEARCH_ACCEPTED":
            runner.step(self.con, self.run)
        runner.atomic(runner.observation_path(self.run), runner.encode({"observation":"other","revision":99}))
        self.assertEqual(runner.step(self.con, self.run), "ABSTAINED")
        self.assertIsNone(self.con.execute("SELECT status FROM actions").fetchone())
        self.assertEqual(runner.read_observation(self.run)["revision"], 99)

    def test_12_true_reversible_action_rollback_observed(self):
        self.complete()
        self.assertEqual(verify_external(self.db, self.run).returncode, 0)
        runner.rollback(self.con, self.run)
        self.assertEqual(runner.read_observation(self.run), {"observation": "idle", "revision": 0})
        self.assertNotEqual(verify_external(self.db, self.run).returncode, 0)
        self.assertEqual(self.con.execute("SELECT status FROM actions").fetchone()[0], "ROLLED_BACK")

    def test_13_expired_deadline_reject(self):
        self.c["deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        with self.assertRaisesRegex(ValueError, "DEADLINE_EXPIRED"):
            self.admit()

    def test_14_over_budget_reject(self):
        self.c["budget"]["max_action_attempts"] = 2
        with self.assertRaisesRegex(ValueError, "BUDGET"):
            self.admit()

    def test_15_unauthorized_scope_reject(self):
        self.c["rights"].append("modify-source")
        with self.assertRaisesRegex(PermissionError, "SCOPES"):
            self.admit()

    def test_16_terminal_replay_does_not_repeat_effect(self):
        self.complete()
        event_count = self.con.execute("SELECT count(*) FROM journal").fetchone()[0]
        self.assertEqual(runner.run_loop(self.con, self.run), "VERIFIED")
        self.assertEqual(event_count, self.con.execute("SELECT count(*) FROM journal").fetchone()[0])
        self.assertEqual(self.con.execute("SELECT attempts FROM actions").fetchone()[0], 1)

    def test_17_unknown_run_denied(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_RUN"):
            runner.run_loop(self.con, self.run)

    def test_18_acl_metadata_reject(self):
        mf = Path(self.temp.name) / "m.json"
        d = copy.deepcopy(runner.manifest())
        d["CHARTER"]["role"] = "admin"
        mf.write_text(json.dumps(d))
        old = runner.MANIFEST
        runner.MANIFEST = mf
        try:
            self.admit()
            self.assertEqual(runner.run_loop(self.con, self.run), "ABSTAINED")
            self.assertIn("SOURCE_ACL_DENIED", self.con.execute(
                "SELECT body FROM journal WHERE event='SAFE_ABSTAIN'").fetchone()[0])
        finally:
            runner.MANIFEST = old

    def test_19_revocation_after_verification_invalidates_current_publishability(self):
        self.complete()
        self.con.execute("INSERT INTO revoked VALUES(?,?)", ("CHARTER", runner.now()))
        self.assertNotEqual(verify_external(self.db, self.run).returncode, 0)

    def test_20_observation_tamper_independent_verifier_rejects(self):
        self.complete()
        runner.atomic(runner.observation_path(self.run), runner.encode({"observation":"reviewed","revision":999}))
        self.assertNotEqual(verify_external(self.db, self.run).returncode, 0)

    def test_21_action_requires_exact_owner(self):
        self.c["actor"] = "other"
        with self.assertRaises(PermissionError):
            self.admit()

    def test_22_cancel_api_not_able_to_reissue_action(self):
        self.admit()
        runner.stage(self.con, self.run, "CANCELED", "CANCELLED_NO_FURTHER_EFFECT")
        self.assertEqual(runner.run_loop(self.con, self.run), "CANCELED")
        self.assertFalse(runner.observation_path(self.run).exists())

    def test_23_revocation_after_action_automatically_rolls_back_before_abstain(self):
        self.admit()
        while runner.get_run(self.con, self.run)[1] != "ACTION_DONE":
            runner.step(self.con, self.run)
        self.con.execute("INSERT INTO revoked VALUES(?,?)", ("DELIVERY", runner.now()))
        self.assertEqual(runner.step(self.con, self.run), "ABSTAINED")
        self.assertEqual(runner.read_observation(self.run), {"observation":"idle","revision":0})
        self.assertEqual(self.con.execute("SELECT status FROM actions").fetchone()[0], "ROLLED_BACK")

    def test_24_cancel_after_unknown_effect_reconciles_then_reverts(self):
        self.admit()
        crashed = subprocess.run([PY, str(HERE / "runner.py"), "run", "--db", str(self.db),
                                  "--run-id", self.run, "--inject-unknown"], capture_output=True, text=True)
        self.assertEqual(crashed.returncode, 73)
        self.assertEqual(runner.read_observation(self.run)["revision"], 1)
        cancel = subprocess.run([PY, str(HERE / "runner.py"), "cancel", "--db", str(self.db),
                                 "--run-id", self.run], capture_output=True, text=True)
        self.assertEqual(cancel.returncode, 0, cancel.stderr)
        self.assertEqual(runner.get_run(self.con, self.run)[1], "CANCELED")
        self.assertEqual(runner.read_observation(self.run), {"observation":"idle","revision":0})
        self.assertEqual(self.con.execute("SELECT attempts,status FROM actions").fetchone(), (1,"ROLLED_BACK"))

    def test_25_cancel_unobserved_unknown_effect_holds_and_does_not_repeat(self):
        self.admit()
        while runner.get_run(self.con, self.run)[1] != "ACTION_PREPARED":
            runner.step(self.con, self.run)
        self.con.execute("UPDATE actions SET attempts=1,status='UNKNOWN' WHERE run_id=?", (self.run,))
        canceled = subprocess.run([PY, str(HERE / "runner.py"), "cancel", "--db", str(self.db),
                                   "--run-id", self.run], capture_output=True, text=True)
        self.assertNotEqual(canceled.returncode, 0)
        self.assertEqual(runner.get_run(self.con, self.run)[1], "ACTION_PREPARED")
        self.assertEqual(self.con.execute("SELECT attempts FROM actions").fetchone()[0], 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
