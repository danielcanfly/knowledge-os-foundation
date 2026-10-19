"""C1 new real OS native generation admission, source and trust negative tests.

This suite explicitly does NOT create fake semantic issuer/IdP credentials,
mock live provider bytes, or call any unadmitted provider.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_c1_current_native_product_nonprod as c1
import m27_c1_genuine_native_generation_seam as s


class LiveSeamNegative(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c1-new-live-admission-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.token_file = self.root / "bearer"
        self.secret = os.urandom(32).hex()
        self.token_file.write_text(self.secret)
        self.token_file.chmod(0o600)
        self.fence = self.root / "fence.json"
        self.fence.write_text(json.dumps({"release_id": c1.h02.f03.A05_RELEASE_ID,
                                          "minimum_epoch": 1}))
        self.fence.chmod(0o600)
        self.head = c1.git_field(ROOT, "HEAD")
        self.tree = c1.git_field(ROOT, "HEAD^{tree}")

    @staticmethod
    def permitted_request():
        return {"question": c1.g01.QUESTION, "tenant": "owner-internal",
                "cache_mode": "OFF", "max_tokens": 64,
                "deadline_seconds": 10, "fallback_consent": False}

    def test_01_missing_genuine_authority_returns_explicit_denial(self):
        seam = s.NativeLiveProduct(repo=ROOT, fence=self.fence,
                                   journal=self.root / "live.jsonl")
        with self.assertRaisesRegex(s.NotQualified, "INDEPENDENT_TRUST_ROOT_NOT_ADMITTED"):
            seam.start({"request_id": "not_prepared"})
        self.assertEqual(seam.provider_invocations, 0)
        self.assertFalse((self.root / "live.jsonl").exists())
        self.assertIsNone(s.TRUST_ROOT_MANIFEST_SHA256)
        self.assertFalse(seam.admission_status()["product_pass"])
        self.assertEqual(seam.admission_status()["cache"], "OFF")

    def test_02_unknown_untrusted_body_and_fallback_denied_before_model(self):
        seam = s.NativeLiveProduct(repo=ROOT, fence=self.fence,
                                   journal=self.root / "live.jsonl")
        for change, expected in [
            ({"tenant": "foreign-tenant"}, "LIVE_TASK_RIGHTS_BUDGET"),
            ({"cache_mode": "HIT"}, "LIVE_TASK_RIGHTS_BUDGET"),
            ({"max_tokens": 193}, "LIVE_TASK_RIGHTS_BUDGET"),
            ({"deadline_seconds": 120}, "LIVE_TASK_RIGHTS_BUDGET"),
            ({"fallback_consent": True}, "LIVE_TASK_RIGHTS_BUDGET"),
            ({"question": "invent answer"}, "LIVE_TASK_RIGHTS_BUDGET")]:
            with self.subTest(change=change):
                with self.assertRaisesRegex(s.NotQualified, expected):
                    seam.prepare({**self.permitted_request(), **change})
        with self.assertRaisesRegex(s.NotQualified, "LIVE_TASKCONTRACT_SHAPE"):
            seam.prepare({**self.permitted_request(), "signed_issuer": "self"})
        self.assertEqual(seam.provider_invocations, 0)

    def test_03_external_signature_is_not_self_declared_or_bypassable(self):
        with self.assertRaisesRegex(s.NotQualified, "INDEPENDENT_TRUST_ROOT_NOT_ADMITTED"):
            s.IndependentAuthority(root_path=self.root / "missing")
        with self.assertRaisesRegex(s.NotQualified, "INVALID_EXTERNAL_SIGNATURE_OR_ROOT"):
            s.verify_ed25519(b"-----BEGIN PUBLIC KEY-----\n", {"a": 1}, "")
        with self.assertRaisesRegex(s.NotQualified, "INVALID_EXTERNAL_SIGNATURE_OR_ROOT"):
            s.verify_ed25519(b"NOT A PUBLIC KEY", {"a": 1},
                             __import__("base64").b64encode(b"0" * 64).decode())
        with self.assertRaisesRegex(s.NotQualified, "INDEPENDENT_ISSUER_OR_SOURCE_RECHECK"):
            s.GeneratedSession(task_sha="0" * 64, request_id="no-trust",
                               pins={"source_proof_sha256": "1" * 64},
                               source_recheck=lambda: "1" * 64,
                               journal=s.h02.FsyncJournal(self.root / "none.jsonl"),
                               authority=object(), model="unqualified")

    def test_04_provider_route_tls_budget_and_exact_model_preflight(self):
        for url, model, allowed in [
            ("http://example.invalid/models", "m", "http://example.invalid/models"),
            ("https://example.invalid/models", "m", "https://other.invalid/models"),
            ("https://example.invalid/models?token=secret", "m",
             "https://example.invalid/models?token=secret"),
        ]:
            with self.subTest(url=url):
                with self.assertRaises(s.NotQualified):
                    s.BoundedProviderWire(url=url, model=model,
                                          token_path=self.token_file,
                                          approved_origin=allowed, approved_model=model)
        valid = s.BoundedProviderWire(
            url="https://example.invalid/custom-worker",
            model="exact-model", token_path=self.token_file,
            approved_origin="https://example.invalid/custom-worker",
            approved_model="exact-model")
        with self.assertRaisesRegex(s.NotQualified, "MODEL_BUDGET_OR_TASK"):
            list(valid.one_bounded_stream(prompt="hello", task_sha="bad",
                                          request_id="req", max_tokens=64))
        with self.assertRaisesRegex(s.NotQualified, "MODEL_BUDGET_OR_TASK"):
            list(valid.one_bounded_stream(prompt="hello", task_sha="0" * 64,
                                          request_id="req", max_tokens=999))
        # No HTTPS connection was initiated; checks happened before URL open.

    def server(self):
        ready = self.root / "ready.json"
        command = [sys.executable,
                   str(ROOT / "src/knowledge_engine/m27_c1_current_native_product_nonprod.py"),
                   "--repo", str(ROOT), "--fence", str(self.fence),
                   "--journal", str(self.root / "source.jsonl"),
                   "--token-file", str(self.token_file),
                   "--expected-head", self.head, "--expected-tree", self.tree,
                   "--ready-file", str(ready)]
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        def finish():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            proc.stderr.close()
        self.addCleanup(finish)
        for _ in range(100):
            if ready.is_file():
                break
            self.assertIsNone(proc.poll(), "C1_NATIVE_SERVER_FAILED_EARLY")
            time.sleep(.05)
        self.assertTrue(ready.is_file())
        return "http://127.0.0.1:" + str(json.loads(ready.read_text())["port"])

    def call(self, url, body=None, *, bearer=True):
        headers = {"Host": "127.0.0.1", "X-C1-Local-Capability":
                   self.secret if bearer else "invalid"}
        raw = json.dumps(body).encode() if body is not None else None
        request = Request(url, method="POST" if raw is not None else "GET",
                          data=raw, headers=headers)
        client = build_opener(ProxyHandler({}))
        try:
            with client.open(request, timeout=10) as res:
                return res.status, json.loads(res.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_05_real_os_native_generation_route_is_explicitly_gated(self):
        base = self.server()
        code, data = self.call(base + c1.STATUS_PATH)
        self.assertEqual(code, 200)
        self.assertEqual(data["native_live"]["native_generation_abi"], s.ABI)
        self.assertEqual(data["native_live"]["provider_called"], False)
        self.assertIsNone(data["native_live"]["trust_root_sha256"])
        code, prepared = self.call(base + c1.LIVE_PREPARE, self.permitted_request())
        self.assertEqual(code, 200)
        self.assertEqual(prepared["status"],
                         "CURRENT_TASK_SOURCE_PREPARED_AWAIT_EXTERNAL_GRANTS")
        self.assertEqual(prepared["prepared_source_count"], 2)
        self.assertEqual(len(prepared["task_contract_sha256"]), 64)
        self.assertEqual(len(prepared["source_proof_sha256"]), 64)
        self.assertTrue(prepared["source_byte_verified_local"])
        self.assertFalse(prepared["provider_called"])
        self.assertFalse(prepared["product_pass"])
        self.assertIsNone(prepared["answer_text"])
        code, response = self.call(base + c1.MODEL_PATH,
                                   {"request_id": prepared["request_id"]})
        self.assertEqual(code, 403)
        self.assertEqual(response["status"], "INDEPENDENT_TRUST_ROOT_NOT_ADMITTED")
        self.assertFalse(response["provider_called"])
        self.assertFalse(response["product_pass"])
        self.assertEqual(response["cache"], "OFF")
        audit = self.root / "source.jsonl.native-live.jsonl"
        self.assertTrue(audit.exists())
        events = [json.loads(line) for line in audit.read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"],
                         "real_a05_source_and_task_prepared_NOT_PROVIDER")
        self.assertFalse(events[0]["provider_called"])
        self.assertFalse(events[0]["product_qualified"])
        code, response = self.call(base + c1.MODEL_PATH, self.permitted_request(),
                                   bearer=False)
        self.assertEqual(code, 403)
        self.assertEqual(response["status"], "CLIENT_AUTH_DENIED")

    def test_06_real_os_source_read_permissions_are_not_escalated(self):
        base = self.server()
        code, bad = self.call(base + c1.SOURCE_PATH, {"question": "PolicyEngine",
                                                       "tenant": "another"})
        self.assertEqual(code, 403)
        self.assertFalse(bad["product_pass"])
        code, bad = self.call(base + c1.LIVE_PREPARE,
                              {**self.permitted_request(), "cache_mode": "HIT"})
        self.assertEqual(code, 403)
        self.assertEqual(bad["status"], "LIVE_TASK_RIGHTS_BUDGET_OR_FALLBACK_DENIED")


    def test_07_revoked_a05_epoch_rejects_real_two_source_preflight(self):
        # Mutate ONLY the isolated nonprod OS fence, not the approved A05 corpus.
        self.fence.write_text(json.dumps({
            "release_id": c1.h02.f03.A05_RELEASE_ID, "minimum_epoch": 2}))
        self.fence.chmod(0o600)
        seam = s.NativeLiveProduct(
            repo=ROOT, fence=self.fence,
            journal=self.root / "revoked-not-a-provider.jsonl")
        with self.assertRaisesRegex(ValueError, "A05_SOURCE_RIGHTS_OR_RETRIEVAL_DENIED"):
            seam.prepare(self.permitted_request())
        self.assertEqual(seam.provider_invocations, 0)
        self.assertFalse((self.root / "revoked-not-a-provider.jsonl").exists())

    def test_08_unsigned_semantic_and_ack_no_session_no_publish(self):
        base = self.server()
        code, unissued = self.call(base + c1.LIVE_VERIFY, {
            "request_id": "not-issued", "obligation": s.OBLIGATIONS[0],
            "text": "fake answer is not independently verified",
            "signed_semantic_receipt": {"payload": {}, "signature_b64": "fake"}})
        self.assertEqual(code, 403)
        self.assertEqual(unissued["status"], "UNKNOWN_OR_REPLAYED_LIVE_TASK")
        code, unissued = self.call(base + c1.LIVE_ACK, {
            "request_id": "not-issued", "claim_id": s.OBLIGATIONS[0],
            "challenge": "not-issued", "text_sha256": "0" * 64,
            "signed_client_ack": {"payload": {}, "signature_b64": "fake"}})
        self.assertEqual(code, 403)
        code, unissued = self.call(base + c1.LIVE_TERMINAL, {
            "request_id": "not-issued"})
        self.assertEqual(code, 403)
        self.assertEqual(unissued["status"], "UNKNOWN_OR_REPLAYED_LIVE_TASK")
        self.assertFalse(unissued["product_pass"])


    def test_09_preterminal_substantive_verified_model_text_and_ack_required(self):
        """No fake signer or provider data: only validate temporal safety proof."""
        with self.assertRaisesRegex(s.NotQualified, "NOT_PRETERMINAL"):
            s.assert_preterminal_verified_client_text(None, None, None)
        with self.assertRaisesRegex(s.NotQualified, "NOT_PRETERMINAL"):
            s.assert_preterminal_verified_client_text(20, 30, 25)
        with self.assertRaisesRegex(s.NotQualified, "NOT_PRETERMINAL"):
            s.assert_preterminal_verified_client_text(20, 35, 30)
        with self.assertRaisesRegex(s.NotQualified, "NOT_PRETERMINAL"):
            s.assert_preterminal_verified_client_text(40, 40, 70)
        # This is only a pure timing invariant, NEVER evidence that an external
        # model, verifier or client did anything or signed a real receipt.
        self.assertIsNone(s.assert_preterminal_verified_client_text(10, 20, 30))


if __name__ == "__main__":
    unittest.main()
