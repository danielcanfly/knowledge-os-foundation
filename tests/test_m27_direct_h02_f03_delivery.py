"""Direct Master H02 + F03 bounded first-party provenance regression.

These are LOCAL nonprod source-candidate tests, not Product rights or model QA.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_h02_native_nonprod_consumer as h02


class H02F03DeliveryBoundary(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="m27-direct-h02-f03-")
        self.addCleanup(temp.cleanup)
        self.fence = Path(temp.name) / "fence.json"
        self.fence.write_text(json.dumps({
            "release_id": h02.f03.A05_RELEASE_ID, "minimum_epoch": 1
        }))
        self.fence.chmod(0o600)
        self.consumer = h02.Consumer(
            repo=ROOT, fence=self.fence,
            journal=Path(temp.name) / "journal.jsonl",
        )

    def test_local_source_candidate_is_bound_but_never_product(self):
        response = self.consumer.start("PolicyEngine")
        entry = self.consumer.entries[response["session_id"]]
        actual = self.consumer._delivery_guard(
            self.consumer._source("PolicyEngine"),
            context=entry["local_context"],
            issued_at=entry["local_issued_at"],
            epoch_floor=entry["epoch"],
        )
        self.assertEqual(
            actual["decision"],
            "LOCAL_DELIVERY_CONTEXT_BOUND_SOURCE_CANDIDATE_ONLY",
        )
        self.assertFalse(actual["product_admitted"])
        self.assertFalse(actual["verified_final"])
        self.assertFalse(actual["answer_cache_write"])
        self.assertEqual(response["provider"], "NOT_RUN")
        self.assertFalse(response["model_generated"])

    def test_expired_source_lease_refuses_ack_before_delivery(self):
        response = self.consumer.start("PolicyEngine")
        entry = self.consumer.entries[response["session_id"]]
        entry["local_issued_at"] -= dt.timedelta(seconds=121)
        first = response["claims"][0]
        with self.assertRaisesRegex(
            h02.Denied, "F03_LOCAL_DELIVERY_BOUNDARY_DENIED"
        ):
            self.consumer.ack(
                response["session_id"], first["claim_id"],
                first["challenge"], first["text_sha256"],
            )

    def test_changed_local_principal_refuses_terminal(self):
        response = self.consumer.start("PolicyEngine")
        entry = self.consumer.entries[response["session_id"]]
        entry["local_context"]["principal"] = "os-uid:not-the-owner"
        with self.assertRaisesRegex(
            h02.Denied, "F03_LOCAL_DELIVERY_BOUNDARY_DENIED"
        ):
            self.consumer.terminal(response["session_id"])

    def test_explicit_f03_deny_fails_closed_at_source_dispatch(self):
        with patch.object(
            h02.delivery, "check_local_candidate_delivery",
            return_value={"decision": "DENY_INVALID_LOCAL_AUTH"},
        ):
            with self.assertRaisesRegex(
                h02.Denied, "F03_LOCAL_DELIVERY_BOUNDARY_DENIED"
            ):
                self.consumer.start("PolicyEngine")


if __name__ == "__main__":
    unittest.main()
