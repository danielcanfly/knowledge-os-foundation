"""Fresh H02 Native Nonprod tests. No protected gold, no live provider."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_h02_native_nonprod_consumer as n


class H02Native(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="h02-native-scope-")
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.fence = self.dir / "fence.json"
        self.fence_write(1)
        self.journal = self.dir / "events.jsonl"
        self.c = n.Consumer(repo=ROOT, fence=self.fence, journal=self.journal)

    def fence_write(self, epoch):
        self.fence.write_text(json.dumps({
            "release_id": n.f03.A05_RELEASE_ID, "minimum_epoch": epoch}))
        self.fence.chmod(0o600)

    def source(self):
        return self.c.start("PolicyEngine")

    def validate(self, entry):
        for claim in entry["claims"]:
            self.c.ack(entry["session_id"], claim["claim_id"],
                       claim["challenge"], claim["text_sha256"])
        return self.c.terminal(entry["session_id"])

    def test_01_contract_validation_local_os_scope(self):
        contract = n.local_task("PolicyEngine", self.c.principal)
        self.assertEqual(n.tc.task_contract(contract), contract)
        self.assertEqual(contract["tenant_id"], "owner-internal")
        self.assertEqual(contract["actor"]["auth_context_ref"], "OS-LOCAL-UNSIGNED-NOT-IDP")
        self.assertEqual(contract["privacy"]["allow_memory_promotion"], False)

    def test_02_real_firstparty_two_source_clauses(self):
        entry = self.source()
        self.assertEqual(entry["source_mode"], "REAL_GIT_SOURCE")
        self.assertEqual(entry["source_manifest_sha256"], n.f03.A05_SOURCE_PIN)
        self.assertEqual(len(entry["claims"]), 2)
        self.assertNotEqual(entry["claims"][0]["text_sha256"], entry["claims"][1]["text_sha256"])
        self.assertTrue(all(x["citation"]["document_sha256"]
                            and x["kind"] == "source_candidate_not_answer"
                            and x["model_generated"] is False for x in entry["claims"]))
        self.assertFalse(entry["complete_answer"])
        self.assertEqual(entry["provider"], "NOT_RUN")
        self.assertEqual(entry["cache"], "OFF")

    def test_03_preterminal_ack_and_terminal(self):
        entry = self.source()
        final = self.validate(entry)
        self.assertEqual(final["status"], "LOCAL_SOURCE_TWO_CLAUSES_ACKED_NOT_PRODUCT")
        self.assertFalse(final["product_pass"])
        events = [json.loads(x) for x in self.journal.read_text().splitlines()]
        self.assertEqual([x["event"] for x in events],
                         ["source_candidate_sent", "client_ack", "client_ack", "terminal"])

    def test_04_unknown_issuer_denied(self):
        with self.assertRaisesRegex(n.Denied, "UNKNOWN_ISSUER"):
            self.c.start("PolicyEngine", issuer="unsigned-self-attested-issuer")

    def test_05_tenant_and_principal_denied(self):
        with self.assertRaisesRegex(n.Denied, "TENANT_OR_PRINCIPAL"):
            self.c.start("PolicyEngine", tenant="another-tenant")
        with self.assertRaisesRegex(n.Denied, "TENANT_OR_PRINCIPAL"):
            self.c.start("PolicyEngine", principal="other-os-user")

    def test_06_bounded_query_and_no_progress_only_answer(self):
        with self.assertRaisesRegex(n.Denied, "BOUNDED_QUERY_ONLY"):
            self.c.start("Can you answer an arbitrary user question?")
        with self.assertRaisesRegex(n.Denied, "BOUNDED_QUERY_ONLY"):
            self.c.start("PolicyEngine says production is ready")
        self.assertEqual(n.PROVIDER, "NOT_RUN")
        self.assertNotIn("answer_text", n.fail("PROGRESS_ONLY"))

    def test_07_wrong_client_ack_nonce(self):
        entry = self.source()
        claim = entry["claims"][0]
        with self.assertRaisesRegex(n.Denied, "CLIENT_ACK_WRONG_NONCE"):
            self.c.ack(entry["session_id"], claim["claim_id"],
                       "injected-wrong-nonce", claim["text_sha256"])
        with self.assertRaisesRegex(n.Denied, "CLIENT_ACK_WRONG_NONCE"):
            self.c.ack(entry["session_id"], claim["claim_id"],
                       claim["challenge"], "0" * 64)

    def test_08_second_claim_missing_blocks_terminal(self):
        entry = self.source()
        claim = entry["claims"][0]
        self.c.ack(entry["session_id"], claim["claim_id"],
                   claim["challenge"], claim["text_sha256"])
        with self.assertRaisesRegex(n.Denied, "SECOND_CLAIM"):
            self.c.terminal(entry["session_id"])

    def test_09_terminal_race_and_no_duplicates(self):
        entry = self.source()
        with self.assertRaisesRegex(n.Denied, "SECOND_CLAIM"):
            self.c.terminal(entry["session_id"])
        self.validate(entry)
        with self.assertRaisesRegex(n.Denied, "DUPLICATE_TERMINAL"):
            self.c.terminal(entry["session_id"])
        with self.assertRaisesRegex(n.Denied, "ACK_AFTER_TERMINAL"):
            c = entry["claims"][0]
            self.c.ack(entry["session_id"], c["claim_id"], c["challenge"], c["text_sha256"])

    def test_10_cancel_blocks_ack_terminal(self):
        entry = self.source()
        result = self.c.cancel(entry["session_id"])
        self.assertEqual(result["status"], "CANCELLED_NO_REPLAY")
        with self.assertRaisesRegex(n.Denied, "SECOND_CLAIM|DUPLICATE_TERMINAL"):
            self.c.terminal(entry["session_id"])
        with self.assertRaisesRegex(n.Denied, "ACK_AFTER_TERMINAL_OR_CANCEL"):
            c = entry["claims"][0]
            self.c.ack(entry["session_id"], c["claim_id"], c["challenge"], c["text_sha256"])

    def test_11_local_revocation_fence_stale_restore(self):
        entry = self.source()
        self.fence_write(2)   # independent fence changes; original immutable corpus remains intact
        claim = entry["claims"][0]
        with self.assertRaisesRegex(n.Denied, "DENY_STALE_RESTORED"):
            self.c.ack(entry["session_id"], claim["claim_id"],
                       claim["challenge"], claim["text_sha256"])
        with self.assertRaisesRegex(n.Denied, "DENY_STALE_RESTORED"):
            self.c.terminal(entry["session_id"])
        self.fence_write(1)   # test-only restore should not imply remote governance authorization
        self.assertFalse(n.f03.PRODUCT_ADMITTED)

    def test_12_real_doc_revocation_in_isolated_copy(self):
        root = self.dir / "a05_copy"
        shutil.copytree(ROOT / n.f03.A05_SOURCE, root)
        recfile = root / "revocations.json"
        rec = json.loads(recfile.read_text())
        corpus = json.loads((root / "corpus.json").read_text())
        rec["revoked_document_sha256"] = [doc["sha256"] for doc in corpus["docs"]]
        recfile.write_text(json.dumps(rec))
        other = n.Consumer(repo=ROOT, source_root=root, isolated_test_copy=True,
                           fence=self.fence, journal=self.dir / "copy_journal.jsonl")
        with self.assertRaises(n.Denied):
            other.start("PolicyEngine")
        self.assertFalse(any((ROOT / n.f03.A05_SOURCE / "revocations.json").read_bytes()
                             == recfile.read_bytes() for _ in range(1)))

    def test_13_wrong_citation_independent_os_rejected(self):
        entry = self.source()
        citation = dict(entry["claims"][0]["citation"])
        citation["excerpt_sha256"] = "0" * 64
        request = {"source_root": str(self.c.reader.source_root), "citation": citation,
                   "text": entry["claims"][0]["text"],
                   "manifest_sha256": n.f03.A05_SOURCE_PIN}
        proc = subprocess.run([sys.executable, str(self.c.verifier)],
                              input=json.dumps(request), text=True, capture_output=True,
                              timeout=10)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(proc.stdout)["code"], "EXCERPT_SHA")

    def test_14_independent_verifier_unavailable_fails_closed(self):
        self.c.verifier = self.dir / "unavailable.py"
        with self.assertRaisesRegex(n.Denied, "INDEPENDENT_OS_VERIFIER_DENIED"):
            self.source()

    def test_15_crash_resume_no_replay_or_effect(self):
        entry = self.source()
        restarted = n.Consumer(repo=ROOT, fence=self.fence, journal=self.journal)
        self.assertEqual(restarted.recovery, "INCOMPLETE_NO_REPLAY")
        with self.assertRaisesRegex(n.Denied, "UNKNOWN_SESSION_NO_REPLAY"):
            restarted.terminal(entry["session_id"])
        self.assertEqual(len([x for x in self.journal.read_text().splitlines()
                              if '"event": "terminal"' in x]), 0)

    def test_16_no_fallback_on_auth_acl_timeout_without_primary(self):
        for failure in ("AUTH", "ACL", "TIMEOUT", None):
            self.assertEqual(n.g01.decide_provider(
                primary_provenance=False, first_failure=failure,
                fallback_consent=True, published_claims=0), "PRIMARY_LIVE_HOLD")
        for failure in ("AUTH", "ACL"):
            self.assertEqual(n.g01.decide_provider(
                primary_provenance=True, first_failure=failure,
                fallback_consent=True, published_claims=0), "NO_FALLBACK")
        self.assertEqual(n.g01.decide_provider(
            primary_provenance=True, first_failure="TIMEOUT",
            fallback_consent=True, published_claims=1), "NO_FALLBACK")

    def test_17_cost_action_memory_and_cache_guards(self):
        info = n.fail("EXTERNAL_HOLD")
        self.assertEqual(info["provider"], "NOT_RUN")
        self.assertFalse(info["fallback_allowed"])
        self.assertFalse(info["g03_action_allowed"])
        self.assertFalse(info["g05_invoice_verified"])
        self.assertFalse(info["actual_savings_verified"])
        self.assertEqual(info["cache"], "OFF")

    def test_18_direct_unknown_session_no_effect(self):
        with self.assertRaisesRegex(n.Denied, "UNKNOWN_SESSION_NO_REPLAY"):
            self.c.cancel("old-session-id")

    def http_app(self):
        ready = self.dir / "ready.json"
        cli = [sys.executable, str(ROOT / "src/knowledge_engine/m27_h02_native_nonprod_consumer.py"),
               "--repo", str(ROOT), "--fence", str(self.fence),
               "--journal", str(self.journal), "--ready-file", str(ready)]
        proc = subprocess.Popen(cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.end_proc, proc)
        for _ in range(100):
            if proc.poll() is not None:
                raise AssertionError("SERVER_DIED:" + str(proc.communicate()))
            if ready.is_file():
                break
            time.sleep(0.05)
        self.assertTrue(ready.is_file())
        port = json.loads(ready.read_text())["port"]
        return "http://127.0.0.1:" + str(port)

    @staticmethod
    def end_proc(proc):
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=3)

    def post(self, base, path, data):
        request = Request(base + path, data=json.dumps(data).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=30) as r:
                return r.status, json.loads(r.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_19_true_os_http_independent_client_positive(self):
        base = self.http_app()
        code, answer = self.post(base, n.ROUTE, {"question": "PolicyEngine"})
        self.assertEqual(code, 200, answer)
        self.assertEqual(answer["status"], "LOCAL_FIRSTPARTY_SOURCE_CANDIDATE")
        self.assertFalse(answer["complete_answer"])
        for c in answer["claims"]:
            code, reply = self.post(base, n.ACK, {
                "session_id": answer["session_id"], "claim_id": c["claim_id"],
                "challenge": c["challenge"], "text_sha256": c["text_sha256"]})
            self.assertEqual(code, 200, reply)
        code, done = self.post(base, n.TERMINAL, {"session_id": answer["session_id"]})
        self.assertEqual(code, 200, done)
        self.assertEqual(done["status"], "LOCAL_SOURCE_TWO_CLAUSES_ACKED_NOT_PRODUCT")

    def test_20_true_os_http_wrong_nonce_and_cancel(self):
        base = self.http_app()
        code, entry = self.post(base, n.ROUTE, {"question": "PolicyEngine"})
        self.assertEqual(code, 200)
        claim = entry["claims"][0]
        code, bad = self.post(base, n.ACK, {
            "session_id": entry["session_id"], "claim_id": claim["claim_id"],
            "challenge": "forged", "text_sha256": claim["text_sha256"]})
        self.assertEqual(code, 403)
        self.assertEqual(bad["status"], "CLIENT_ACK_WRONG_NONCE_OR_DIGEST")
        code, cancelled = self.post(base, n.CANCEL, {"session_id": entry["session_id"]})
        self.assertEqual(code, 200)
        self.assertEqual(cancelled["status"], "CANCELLED_NO_REPLAY")
        code, terminal = self.post(base, n.TERMINAL, {"session_id": entry["session_id"]})
        self.assertEqual(code, 403)
        self.assertEqual(terminal["status"], "DUPLICATE_TERMINAL")
        code, injected = self.post(base, n.ROUTE,
                                   {"question": "PolicyEngine", "issuer": "forge"})
        self.assertEqual(code, 403)
        self.assertEqual(injected["status"], "UNEXPECTED_REQUEST_FIELDS")


if __name__ == "__main__":
    unittest.main()
