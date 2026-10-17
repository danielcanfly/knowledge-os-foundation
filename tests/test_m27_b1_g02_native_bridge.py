"""Bounded first-party Nonprod H02 research: live owner sources and a real loopback client."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "knowledge_engine"))
from m27_b1_g02_native_bridge import (
    AdmissionDenied, REQUEST_SCHEMA, ResearchBridge,
)
from m27_b0_research_outcome import ResearchDenied, canonical
from m27_task_contracts_v1 import sha256 as task_sha

EVIDENCE = Path(os.environ["G02_EVIDENCE_ROOT"])
CHECKER = ROOT / "tools" / "m27_b0_research_independent_check.py"


class NativeResearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="h02-g02-native-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "artifact").mkdir()
        self.contract_path = self.root / "contract.json"
        self.registry_path = self.root / "registry.json"
        self.contract = json.loads((EVIDENCE / "input/task_contract.json").read_bytes())
        self.registry = json.loads((EVIDENCE / "input/sources.json").read_bytes())
        self.save_input()
        self.db = self.root / "research.sqlite"
        self.bridge = self.make_bridge()
        self.request = self.make_request("run-1", "req-1")

    def save_input(self):
        self.contract_path.write_bytes(canonical(self.contract))
        self.registry_path.write_bytes(canonical(self.registry))

    def make_bridge(self):
        return ResearchBridge(
            contract_path=self.contract_path, registry_path=self.registry_path,
            db_path=self.db, outcome_dir=self.root / "artifact",
            independent_checker=CHECKER,
            tenant_id="owner-m27-nonprod", principal_id="owner-delegated-b0-02",
        )

    def make_request(self, run_id, request_id):
        return {
            "schema": REQUEST_SCHEMA, "request_id": request_id, "run_id": run_id,
            "task_id": self.contract["task_id"],
            "task_version": self.contract["task_version"],
            "tenant_id": "owner-m27-nonprod", "principal_id": "owner-delegated-b0-02",
            "contract_sha256": task_sha(self.contract),
            "registry_sha256": hashlib.sha256(canonical(self.registry)).hexdigest(),
            "outcome_id": self.contract["output_specs"][0]["outcome_id"],
        }

    def assert_denied(self, request, phrase):
        with self.assertRaisesRegex((AdmissionDenied, ResearchDenied, ValueError), phrase):
            self.bridge.dispatch(request)

    def test_01_real_source_two_step_native_outcome_and_independent_bytes(self):
        result = self.bridge.dispatch(self.request)
        self.assertEqual(result["admission"], "NATIVE_TASK_V1_ACCEPTED")
        self.assertEqual(result["state"], "DURABLE_SOURCE_BACKED_RESEARCH_READBACK_PASS")
        self.assertEqual(result["citations"], 4)
        self.assertFalse(result["formal_product_qualified"])
        md = Path(result["markdown_path"]).read_bytes()
        self.assertIn(b"## Synthesis and bounded recommendation", md)
        self.assertEqual(hashlib.sha256(md).hexdigest(), result["markdown_sha256"])
        structured = json.loads(Path(result["json_path"]).read_bytes())
        self.assertEqual([c["source_id"] for c in structured["citations"]],
                         ["charter", "charter", "audit", "audit"])
        self.assertEqual(len(list((self.root / "artifact").glob("*.json"))), 2)
        with sqlite3.connect(self.db) as db:
            events = db.execute("SELECT kind FROM g02_events WHERE run_id=? ORDER BY seq",
                                ("run-1",)).fetchall()
        self.assertEqual([x[0] for x in events],
                         ["PLANNED", "CHARTER_EXTRACTED",
                          "AUDIT_COMPARED", "OUTCOME_COMMITTED"])

    def test_02_native_resume_byte_identical_and_one_binding(self):
        before = self.bridge.dispatch(self.request)
        after = self.make_bridge().dispatch(self.request)
        self.assertEqual(before, after)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM g02_events").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM h02_request_bindings").fetchone()[0], 1)

    def test_03_cross_tenant_denied(self):
        request = dict(self.request, tenant_id="other-tenant")
        self.assert_denied(request, "CLIENT_IDENTITY")

    def test_04_wrong_principal_denied(self):
        request = dict(self.request, principal_id="unauthorized-actor")
        self.assert_denied(request, "CLIENT_IDENTITY")

    def test_05_revoked_doc_denied(self):
        self.registry["sources"]["audit"]["revoked"] = True
        self.save_input()
        request = self.make_request("revoked", "revoked")
        self.assert_denied(request, "SOURCE_REVOKED")

    def test_06_expired_doc_denied(self):
        self.registry["sources"]["charter"]["valid_until"] = "2020-01-01T00:00:00Z"
        self.save_input()
        self.assert_denied(self.make_request("expired", "expired"), "SOURCE_RIGHTS_EXPIRED")

    def test_07_stale_source_sha_denied(self):
        self.registry["sources"]["charter"]["sha256"] = "0" * 64
        self.save_input()
        self.assert_denied(self.make_request("drift", "drift"), "SOURCE_DIGEST_DRIFT")

    def test_08_contract_abi_bypass_denied(self):
        req = dict(self.request, task_version=99)
        self.assert_denied(req, "TASK_ABI")

    def test_09_registry_pin_mismatch_denied(self):
        req = dict(self.request, registry_sha256="0" * 64)
        self.assert_denied(req, "REGISTRY_PIN")

    def test_10_duplicate_request_id_new_run_denied(self):
        self.bridge.dispatch(self.request)
        req = self.make_request("run-2", "req-1")
        self.assert_denied(req, "REPLAY_OR_DUPLICATE")

    def test_11_same_run_forged_new_request_denied(self):
        self.bridge.dispatch(self.request)
        req = self.make_request("run-1", "req-2")
        self.assert_denied(req, "REPLAY_OR_DUPLICATE")

    def test_12_post_commit_revocation_denied(self):
        self.bridge.dispatch(self.request)
        self.registry["sources"]["charter"]["revoked"] = True
        self.save_input()
        self.assert_denied(self.request, "REGISTRY_PIN")
        req = self.make_request("run-1", "req-1")
        self.assert_denied(req, "REPLAY_OR_DUPLICATE")

    def test_13_corrupt_journal_hash_denied(self):
        self.bridge.dispatch(self.request)
        with sqlite3.connect(self.db) as db:
            db.execute("DROP TRIGGER g02_no_update")
            db.execute("UPDATE g02_events SET digest=? WHERE seq=2", ("0"*64,))
        self.assert_denied(self.request, "JOURNAL_CHAIN_CORRUPT")

    def test_14_partial_artifact_denied(self):
        self.bridge.dispatch(self.request)
        (self.root / "artifact" / "run-1.json").unlink()
        self.assert_denied(self.request, "OUTCOME_MISSING_OR_PARTIAL")

    def test_15_receipt_tamper_denied(self):
        result = self.bridge.dispatch(self.request)
        p = Path(result["receipt_path"])
        body = json.loads(p.read_bytes())
        body["markdown_sha256"] = "f"*64
        p.write_bytes(canonical(body))
        self.assert_denied(self.request, "RECEIPT_REPLAY_DRIFT")

    def test_16_unsafe_run_id_denied(self):
        self.assert_denied(dict(self.request, run_id="../escape"), "UNSAFE_OR_MISSING")

    def test_17_request_fields_not_extensible_denied(self):
        self.assert_denied(dict(self.request, secret="no"), "REQUEST_ABI")

    def test_18_public_product_claim_denied_by_absence(self):
        out = self.bridge.dispatch(self.request)
        self.assertNotIn("publish", out)
        self.assertFalse(out["formal_product_qualified"])
        self.assertEqual(out["scope"], "NONPROD_OWNER_FIRST_PARTY_LOCAL_RESEARCH_ONLY")

    def test_19_real_independent_local_http_client(self):
        cmd = [sys.executable,
               str(ROOT / "src" / "knowledge_engine" / "m27_b1_g02_native_bridge.py"),
               "--contract", str(self.contract_path), "--sources", str(self.registry_path),
               "--db", str(self.db), "--out", str(self.root / "artifact"),
               "--checker", str(CHECKER), "--tenant", "owner-m27-nonprod",
               "--principal", "owner-delegated-b0-02", "--once", "--port", "0"]
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env)
        try:
            ready = json.loads(p.stdout.readline())
            self.assertEqual(ready["listen"], "127.0.0.1")
            url = f"http://127.0.0.1:{ready['port']}/nonprod/h02/research"
            raw_request = urllib.request.Request(
                url, data=canonical(self.request),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(raw_request, timeout=10) as resp:
                body = json.loads(resp.read())
            self.assertEqual(body["state"], "DURABLE_SOURCE_BACKED_RESEARCH_READBACK_PASS")
            self.assertEqual(body["admission"], "NATIVE_TASK_V1_ACCEPTED")
            self.assertEqual(body["citations"], 4)
            self.assertEqual(hashlib.sha256(Path(body["markdown_path"]).read_bytes()).hexdigest(),
                             body["markdown_sha256"])
            self.assertEqual(p.wait(timeout=10), 0)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
            p.stdout.close()
            p.stderr.close()

    def test_20_contract_without_independent_verifier_denied(self):
        self.contract["definition_of_done"]["independent_verification_required"] = False
        self.save_input()
        self.assert_denied(self.make_request("noverify", "noverify"),
                           "INDEPENDENT_VERIFICATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
