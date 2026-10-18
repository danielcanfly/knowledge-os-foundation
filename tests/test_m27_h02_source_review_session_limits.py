"""Real bounded lifecycle tests for Owner-firstparty Nonprod Source Review.

These do not represent Provider calls, final answers, C28, or official eval.
"""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_h02_multitopic_local_source_review as review


class BoundedLifecycle(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="m27-h02-review-lifecycle-")
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        fence = d / "fence.json"
        fence.write_text(json.dumps({
            "release_id": review.h02.f03.A05_RELEASE_ID,
            "minimum_epoch": 1,
        }))
        fence.chmod(0o600)
        self.obj = review.SourceReview(repo=ROOT, fence=fence,
                                     journal=d / "journal.jsonl")

    def _start(self):
        return self.obj.start("Context Planner")

    def _ack_all(self, response):
        for c in response["claims"]:
            self.obj.ack(response["session_id"], c["claim_id"],
                         c["challenge"], c["text_sha256"])

    def _no_secrets(self, sid):
        entry = self.obj.entries[sid]
        self.assertEqual(set(entry), {"state", "task_sha"})
        self.assertTrue(isinstance(entry["task_sha"], str))

    def test_real_eighth_permitted_and_ninth_fails_before_retrieval(self):
        accepted = [self._start() for _ in range(8)]
        self.assertEqual(len(self.obj.entries), 8)
        with self.assertRaisesRegex(review.h02.Denied, "MAX_ACTIVE_SOURCE_REVIEWS"):
            self._start()
        self.assertEqual(len(self.obj.entries), 8)
        self.obj.cancel(accepted[0]["session_id"])
        self._no_secrets(accepted[0]["session_id"])
        another = self._start()
        self.assertEqual(another["status"],
                         "LOCAL_MULTITOPIC_SOURCE_REVIEW_AWAITING_ACK")
        self.assertEqual(sum(x["state"] == "AWAITING_ACK"
                             for x in self.obj.entries.values()), 8)

    def test_cancel_wipes_source_and_nonce_but_denies_replay(self):
        response = self._start()
        sid = response["session_id"]
        self.assertGreater(len(self.obj.entries[sid]["excerpts"]), 0)
        self.obj.cancel(sid)
        self._no_secrets(sid)
        c = response["claims"][0]
        with self.assertRaisesRegex(review.h02.Denied, "ACK_AFTER_TERMINAL"):
            self.obj.ack(sid, c["claim_id"], c["challenge"], c["text_sha256"])

    def test_valid_terminal_wipes_sensitive_and_denies_duplicate(self):
        response = self._start()
        self._ack_all(response)
        terminal = self.obj.terminal(response["session_id"])
        self.assertFalse(terminal["product_pass"])
        self._no_secrets(response["session_id"])
        with self.assertRaisesRegex(review.h02.Denied, "DUPLICATE_TERMINAL"):
            self.obj.terminal(response["session_id"])

    def test_expiry_is_failclosed_and_releases_pending_slot(self):
        responses = [self._start() for _ in range(8)]
        sid = responses[0]["session_id"]
        self.obj.entries[sid]["issued_at"] -= dt.timedelta(seconds=121)
        new = self._start()
        self.assertNotEqual(new["session_id"], sid)
        self._no_secrets(sid)
        self.assertEqual(self.obj.entries[sid]["state"], "EXPIRED_NO_REPLAY")
        self.assertEqual(sum(x["state"] == "AWAITING_ACK"
                             for x in self.obj.entries.values()), 8)
        old = responses[0]["claims"][0]
        with self.assertRaisesRegex(review.h02.Denied, "ACK_AFTER_TERMINAL"):
            self.obj.ack(sid, old["claim_id"], old["challenge"], old["text_sha256"])

    def test_expired_ack_immediately_wipes_source(self):
        response = self._start()
        sid = response["session_id"]
        self.obj.entries[sid]["issued_at"] -= dt.timedelta(seconds=121)
        claim = response["claims"][0]
        with self.assertRaisesRegex(review.h02.Denied, "F03_LOCAL_DELIVERY_BOUNDARY_DENIED"):
            self.obj.ack(sid, claim["claim_id"], claim["challenge"], claim["text_sha256"])
        self._no_secrets(sid)

    def test_tombstone_limit_does_not_evict_active_sessions(self):
        active = self._start()
        for i in range(review.MAX_REPLAY_TOMBSTONES + 12):
            self.obj.entries["old-tombstone-" + str(i)] = {
                "state": "TERMINATED", "task_sha": "dummy-nonsecret",
            }
        self.obj._prune_tombstones()
        self.assertEqual(sum(x["state"] != "AWAITING_ACK"
                             for x in self.obj.entries.values()),
                         review.MAX_REPLAY_TOMBSTONES)
        self.assertIn(active["session_id"], self.obj.entries)
        self.assertLessEqual(len(self.obj.entries),
                             review.MAX_REPLAY_TOMBSTONES + review.MAX_PENDING_SOURCE_REVIEWS)


if __name__ == "__main__":
    unittest.main()
