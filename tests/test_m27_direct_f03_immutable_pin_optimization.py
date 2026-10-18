"""Immutable Git baseline reuse, never source/rights or answer caching."""
from __future__ import annotations

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
import m27_f03_source_rights_admission as f03


class ImmutableGitPinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m27-direct-f03-pin-")
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.corpus = self.dir / "source"
        shutil.copytree(ROOT / f03.A05_SOURCE, self.corpus)
        self.fence = self.dir / "epoch.json"
        self.fence.write_text(json.dumps({
            "release_id": f03.A05_RELEASE_ID, "minimum_epoch": 1}))
        self.fence.chmod(0o600)
        self.reader = f03.A05OwnerCorpusAdmission(
            ROOT, source_root=self.corpus, fence=self.fence,
            isolated_test_copy=True)

    def fetch(self):
        return self.reader.source_retrieval(
            "PolicyEngine", tenant="owner-internal",
            principal="os-uid:" + str(os.geteuid()),
            obligations=["PolicyEngine decides."], ttl_seconds=120)

    def test_exact_immutable_blob_is_not_spawned_repeatedly(self):
        with patch.object(f03.subprocess, "run",
                          wraps=f03.subprocess.run) as run:
            first = self.fetch()
            before = run.call_count
            second = self.fetch()
            self.assertEqual(run.call_count, before)
        self.assertGreater(before, 0)
        self.assertEqual(first["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        self.assertEqual(second["decision"], first["decision"])
        self.assertTrue(second["candidate_only"])
        self.assertFalse(second["product_admitted"])
        self.assertFalse(second["answer_cache_enabled"])

    def test_changed_local_source_denied_after_pin_warm(self):
        self.assertEqual(self.fetch()["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        doc = self.corpus / json.loads(
            (self.corpus / "corpus.json").read_text())["docs"][0]["filename"]
        doc.write_bytes(doc.read_bytes() + b"\nunauthorized extra content\n")
        result = self.fetch()
        self.assertNotEqual(
            result["decision"], "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        self.assertFalse(result["product_admitted"])

    def test_epoch_revocation_fence_denies_after_warm(self):
        self.assertEqual(self.fetch()["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        # A higher local floor without matching revocation change is unsafe.
        self.fence.write_text(json.dumps({
            "release_id": f03.A05_RELEASE_ID, "minimum_epoch": 2}))
        self.fence.chmod(0o600)
        result = self.fetch()
        self.assertNotEqual(
            result["decision"], "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        self.assertFalse(result["answer_cache_hit"])

    def test_path_validation_remains_failclosed_even_if_warmed(self):
        self.reader._pinned(f03.A05_SOURCE + "/corpus.json")
        with self.assertRaises(f03.Rejected):
            self.reader._pinned("../corpus.json")


if __name__ == "__main__":
    unittest.main()
