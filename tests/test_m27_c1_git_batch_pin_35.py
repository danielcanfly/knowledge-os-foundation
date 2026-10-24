"""C1-35: immutable Git batch pin optimization without rights caching."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "knowledge_engine"))
import m27_f03_source_rights_admission as f03

class FrozenGitBatchSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c1-git-batch-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fence = self.root / "fence.json"
        self.fence.write_text(json.dumps(
            {"release_id": f03.A05_RELEASE_ID, "minimum_epoch": 1}))
        self.fence.chmod(0o600)
        self.reader = f03.A05OwnerCorpusAdmission(ROOT, fence=self.fence)
    def query(self, reader=None):
        return (reader or self.reader).source_retrieval(
            "PolicyEngine", tenant="owner-internal",
            principal="os-uid:" + str(os.geteuid()),
            obligations=["PolicyEngine decides."], ttl_seconds=120)
    def test_cold_exact_batch_14_pins_one_git_process(self):
        commands = []
        original = subprocess.run
        def spy(command, *args, **kwargs):
            if isinstance(command, list) and command[:3] == [
                "git", "-C", str(ROOT)]:
                commands.append(command)
            return original(command, *args, **kwargs)
        with patch.object(f03.subprocess, "run", side_effect=spy):
            first = self.query()
            second = self.query()
        self.assertEqual(first["decision"], "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        self.assertEqual(second["decision"], first["decision"])
        self.assertEqual(len(self.reader._pinned_blob_cache), 14)
        self.assertEqual(sum(x[-1] == "--batch" for x in commands), 1)
        self.assertFalse(any(x[-2:] == ["cat-file", "blob"] for x in commands))
    def test_corrupt_batch_blob_fails_closed_and_cannot_partially_cache(self):
        original = subprocess.run
        def corrupt(command, *args, **kwargs):
            result = original(command, *args, **kwargs)
            if command[-2:] == ["cat-file", "--batch"]:
                binary = bytearray(result.stdout)
                begin = binary.index(b"\\n") + 1
                binary[begin] ^= 1
                return subprocess.CompletedProcess(
                    command, result.returncode, bytes(binary), result.stderr)
            return result
        with patch.object(f03.subprocess, "run", side_effect=corrupt):
            with self.assertRaisesRegex(f03.Rejected, "MISMATCHED_PINNED_GIT_OBJECT"):
                self.reader._pinned(f03.A05_SOURCE + "/corpus.json")
        self.assertEqual(self.reader._pinned_blob_cache, {})
    def test_cached_pin_still_detects_mutated_disk_document(self):
        copied = self.root / "isolated_a05_corpus"
        shutil.copytree(ROOT / f03.A05_SOURCE, copied)
        reader = f03.A05OwnerCorpusAdmission(
            ROOT, source_root=copied, fence=self.fence,
            isolated_test_copy=True)
        self.assertEqual(self.query(reader)["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        with (copied / "01_contracts.md").open("ab") as out:
            out.write(b"\nTamper must not be accepted\n")
        self.assertNotEqual(self.query(reader)["decision"],
                            "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
    def test_cached_pin_still_observes_rights_revocation(self):
        copied = self.root / "isolated_a05_corpus"
        shutil.copytree(ROOT / f03.A05_SOURCE, copied)
        reader = f03.A05OwnerCorpusAdmission(
            ROOT, source_root=copied, fence=self.fence,
            isolated_test_copy=True)
        self.assertEqual(self.query(reader)["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        source_sha = f03.sha((copied / "01_contracts.md").read_bytes())
        path = copied / "revocations.json"
        rev = json.loads(path.read_text())
        rev["revoked_document_sha256"].append(source_sha)
        rev["epoch"] = 2
        path.write_text(json.dumps(rev))
        self.fence.write_text(json.dumps(
            {"release_id": f03.A05_RELEASE_ID, "minimum_epoch": 2}))
        self.assertNotEqual(self.query(reader)["decision"],
                            "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")

if __name__ == "__main__":
    unittest.main()
