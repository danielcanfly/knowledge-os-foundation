"""Failclosed HTTP Client authority for owner-local A05 firstparty review only.

A live HTTP success needs one per-process bootstrap token explicitly supplied
out-of-band. Token/authorization is never an external Product IdP or signer.
"""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_h02_multitopic_local_source_review as review


class LocalTokenBoundary(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="m27-p0-h02-http-auth-")
        self.addCleanup(temp.cleanup)
        d = Path(temp.name)
        fence = d / "epoch.json"
        fence.write_text(json.dumps({
            "release_id": review.h02.f03.A05_RELEASE_ID, "minimum_epoch": 1,
        }))
        fence.chmod(0o600)
        self.inner = review.SourceReview(
            repo=ROOT, fence=fence, journal=d / "journal.jsonl")
        self.server = review.LocalSourceReviewServer(self.inner)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.url = ("http://127.0.0.1:"
                    + str(self.server.server_address[1])
                    + "/nonprod/source-review/start")

    def call(self, *, authorization=None, origin=None, host=None):
        headers = {"Content-Type": "application/json"}
        if authorization is not None:
            headers["Authorization"] = authorization
        if origin is not None:
            headers["Origin"] = origin
        if host is not None:
            headers["Host"] = host
        req = urllib.request.Request(
            self.url, json.dumps({"topic": "PolicyEngine"}).encode("utf-8"),
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_no_token_denied_before_firstparty_source_read(self):
        code, payload = self.call()
        self.assertEqual(code, 403)
        self.assertEqual(payload["status"], "DENY_LOCAL_CLIENT_AUTH")
        self.assertNotIn("claims", payload)

    def test_wrong_token_denied(self):
        code, payload = self.call(authorization="Bearer never-a-real-token")
        self.assertEqual(code, 403)
        self.assertEqual(payload["status"], "DENY_LOCAL_CLIENT_AUTH")

    def test_cross_origin_refused_even_if_token_correct(self):
        code, payload = self.call(
            authorization="Bearer " + self.server.client_auth_token,
            origin="https://untrusted.example")
        self.assertEqual(code, 403)
        self.assertEqual(payload["status"], "DENY_CROSS_ORIGIN")

    def test_host_header_mismatch_refused_even_if_token_correct(self):
        code, payload = self.call(
            authorization="Bearer " + self.server.client_auth_token,
            host="localhost:invalid")
        self.assertEqual(code, 403)
        self.assertEqual(payload["status"], "DENY_HOST")

    def test_auth_token_is_random_not_persisted_in_source(self):
        with tempfile.TemporaryDirectory(prefix="m27-h02-token-") as d:
            fence = Path(d) / "fence.json"
            fence.write_text(json.dumps({
                "release_id": review.h02.f03.A05_RELEASE_ID,
                "minimum_epoch": 1,
            }))
            fence.chmod(0o600)
            obj = review.SourceReview(
                repo=ROOT, fence=fence, journal=Path(d) / "journal.jsonl")
            another = review.LocalSourceReviewServer(obj)
            try:
                self.assertNotEqual(
                    another.client_auth_token, self.server.client_auth_token)
                self.assertGreaterEqual(len(another.client_auth_token), 48)
            finally:
                another.server_close()

    def test_valid_local_token_allows_source_only_not_product(self):
        code, payload = self.call(
            authorization="Bearer " + self.server.client_auth_token)
        self.assertEqual(code, 200)
        self.assertTrue(payload["claims"])
        self.assertFalse(payload["complete_answer"])
        self.assertFalse(payload["model_generated"])
        self.assertFalse(payload["product_qualified"])
        self.assertEqual(payload["provider"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
