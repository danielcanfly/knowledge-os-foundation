"""Actual firstparty A05 multi-topic source review positive/negative acceptance.

All tests are local/nonprod and must never be counted as model-answer quality.
"""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_h02_multitopic_local_source_review as mt


class BoundedMultitopicSourceReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m27-multitopic-a05-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.fence = self.dir / "fence.json"
        self.fence.write_text(json.dumps({
            "release_id": mt.h02.f03.A05_RELEASE_ID,
            "minimum_epoch": 1,
        }))
        self.fence.chmod(0o600)
        self.reader = mt.SourceReview(
            repo=ROOT, fence=self.fence,
            journal=self.dir / "journal.jsonl",
        )

    def _begin(self, topic="PolicyEngine"):
        return self.reader.start(topic)

    def _acked(self, obj):
        for claim in obj["claims"]:
            self.reader.ack(
                obj["session_id"], claim["claim_id"],
                claim["challenge"], claim["text_sha256"],
            )

    def test_all_five_live_firstparty_topics_claim_ack_terminal(self):
        for topic in mt.TOPIC_OBLIGATIONS:
            with self.subTest(topic=topic):
                obj = self._begin(topic)
                self.assertTrue(1 <= len(obj["claims"]) <= 2)
                self.assertFalse(obj["complete_answer"])
                self.assertFalse(obj["model_generated"])
                self.assertFalse(obj["product_qualified"])
                self.assertEqual(obj["provider"], "NOT_RUN")
                for c in obj["claims"]:
                    self.assertFalse(c["model_generated"])
                    self.assertEqual(c["kind"], "exact_source_candidate_not_answer")
                    self.assertIn(mt.TOPIC_OBLIGATIONS[topic].casefold(), c["text"].casefold())
                self._acked(obj)
                result = self.reader.terminal(obj["session_id"])
                self.assertEqual(result["status"], "LOCAL_SOURCE_REVIEW_ACKED_NOT_PRODUCT")
                self.assertFalse(result["product_pass"])
                self.assertFalse(result["model_generated_answer"])

    def test_unsupported_query_is_not_general_qa(self):
        for q in ["", "Explain quantum acceleration", "Tool Registry",
                  "PolicyEngine not?", "PolicyEngine 523", "help"]:
            with self.subTest(q=q):
                with self.assertRaisesRegex(mt.h02.Denied, "TOPIC_NOT_IN_BOUNDED"):
                    self._begin(q)

    def test_wrong_tenant_and_principal_and_issuer(self):
        for kw in [{"tenant": "another"}, {"principal": "os-uid:999999"},
                   {"issuer": "fake-signer"}]:
            with self.subTest(kw=kw):
                with self.assertRaisesRegex(mt.h02.Denied, "REMOTE_IDP_NOT_ADMITTED"):
                    self.reader.start("PolicyEngine", **kw)

    def test_wrong_ack_digest_and_nonce_denied(self):
        obj = self._begin()
        c = obj["claims"][0]
        with self.assertRaisesRegex(mt.h02.Denied, "INVALID_CLIENT_ACK"):
            self.reader.ack(obj["session_id"], c["claim_id"], "a" * 48, c["text_sha256"])
        with self.assertRaisesRegex(mt.h02.Denied, "INVALID_CLIENT_ACK"):
            self.reader.ack(obj["session_id"], c["claim_id"], c["challenge"], "0" * 64)

    def test_terminal_requires_all_client_acks(self):
        obj = self._begin()
        with self.assertRaisesRegex(mt.h02.Denied, "UNACKNOWLEDGED_SOURCE_CANDIDATES"):
            self.reader.terminal(obj["session_id"])
        self._acked(obj)
        self.reader.terminal(obj["session_id"])
        with self.assertRaisesRegex(mt.h02.Denied, "DUPLICATE_TERMINAL"):
            self.reader.terminal(obj["session_id"])

    def test_repeat_ack_and_cancel_are_failclosed(self):
        obj = self._begin()
        c = obj["claims"][0]
        self.reader.ack(obj["session_id"], c["claim_id"], c["challenge"], c["text_sha256"])
        with self.assertRaisesRegex(mt.h02.Denied, "UNKNOWN_OR_DUPLICATE_CLAIM"):
            self.reader.ack(obj["session_id"], c["claim_id"], c["challenge"], c["text_sha256"])
        self.reader.cancel(obj["session_id"])
        with self.assertRaisesRegex(mt.h02.Denied, "ACK_AFTER_TERMINAL"):
            self.reader.ack(obj["session_id"], c["claim_id"], c["challenge"], c["text_sha256"])

    def test_epoch_fence_revocation_denies_ack_after_start(self):
        obj = self._begin()
        self.fence.write_text(json.dumps({
            "release_id": mt.h02.f03.A05_RELEASE_ID, "minimum_epoch": 2,
        }))
        self.fence.chmod(0o600)
        c = obj["claims"][0]
        with self.assertRaises(mt.h02.Denied):
            self.reader.ack(obj["session_id"], c["claim_id"],
                            c["challenge"], c["text_sha256"])

    def test_expired_local_delivery_lease_fails_closed(self):
        obj = self._begin()
        self.reader.entries[obj["session_id"]]["issued_at"] -= dt.timedelta(seconds=121)
        c = obj["claims"][0]
        with self.assertRaisesRegex(mt.h02.Denied, "F03_LOCAL_DELIVERY_BOUNDARY_DENIED"):
            self.reader.ack(obj["session_id"], c["claim_id"],
                            c["challenge"], c["text_sha256"])

    def test_wrong_source_root_cannot_get_product_rights(self):
        obj = self._begin()
        self.reader.entries[obj["session_id"]]["context"]["principal"] = "os-uid:invalid"
        with self.assertRaisesRegex(mt.h02.Denied, "F03_LOCAL_DELIVERY_BOUNDARY_DENIED"):
            self.reader.terminal(obj["session_id"])

    def test_independent_os_verifier_deny_rejects_source(self):
        with patch.object(self.reader.inner, "_verify", side_effect=mt.h02.Denied("OS_DENIED")):
            with self.assertRaisesRegex(mt.h02.Denied, "OS_DENIED"):
                self._begin()

    def test_journal_resume_does_not_restore_publishable_sessions(self):
        obj = self._begin()
        self.assertNotIn(obj["session_id"], {})
        another = mt.SourceReview(
            repo=ROOT, fence=self.fence, journal=self.dir / "journal.jsonl"
        )
        self.assertEqual(another.entries, {})
        with self.assertRaisesRegex(mt.h02.Denied, "UNKNOWN_SESSION_NO_REPLAY"):
            another.terminal(obj["session_id"])

    def test_source_bytes_tampered_after_start_are_denied(self):
        clone = self.dir / "source-clone"
        shutil.copytree(ROOT / mt.h02.f03.A05_SOURCE, clone)
        reader = mt.SourceReview(
            repo=ROOT, fence=self.fence,
            journal=self.dir / "journal-copy.jsonl",
            source_root=clone, isolated_test_copy=True
        )
        obj = reader.start("Context Planner")
        d = clone / "03_context_planner.md"
        d.write_bytes(d.read_bytes() + b"\nchanged after sending\n")
        c = obj["claims"][0]
        with self.assertRaises(mt.h02.Denied):
            reader.ack(obj["session_id"], c["claim_id"],
                       c["challenge"], c["text_sha256"])


if __name__ == "__main__":
    unittest.main()
