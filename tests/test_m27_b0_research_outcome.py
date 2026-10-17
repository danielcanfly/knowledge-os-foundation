"""Scoped local tests. The sole actual outcome comes from owned live M27 docs.

These are verification/negative tests, not substitutes for OS-kill receipts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "knowledge_engine"))
sys.path.insert(0, str(ROOT / "tools"))

from m27_b0_research_outcome import ResearchDenied, execute
from m27_b0_research_independent_check import verify


class RealSourceResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = os.environ.get("G02_EVIDENCE_ROOT")
        if not raw:
            raise RuntimeError("Set G02_EVIDENCE_ROOT to owner-authorized M27 evidence root")
        cls.golden = Path(raw)
        cls.sources = json.loads((cls.golden / "input" / "sources.json").read_bytes())
        cls.contract = json.loads((cls.golden / "input" / "task_contract.json").read_bytes())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="g02-negative-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "run.sqlite"
        self.out = self.root / "out"
        self.out.mkdir()
        self.contract_data = copy.deepcopy(self.contract)
        self.sources_data = copy.deepcopy(self.sources)
        self._save()

    def _save(self):
        self.contract_path = self.root / "contract.json"
        self.sources_path = self.root / "sources.json"
        self.contract_path.write_text(json.dumps(self.contract_data), encoding="utf-8")
        self.sources_path.write_text(json.dumps(self.sources_data), encoding="utf-8")

    def _execute(self):
        self._save()
        return execute(self.db, self.contract_path, self.sources_path, self.out,
                       "g02-test-same-id")

    def _denied(self, expected):
        with self.assertRaises((ResearchDenied, ValueError)) as cm:
            self._execute()
        self.assertIn(expected, str(cm.exception))

    def test_01_real_owned_document_artifact_and_independent_reader(self):
        result = self._execute()
        receipt = verify(self.db, self.sources_path, self.contract_path,
                         self.out, "g02-test-same-id")
        self.assertEqual(receipt["verified_live_citations"], 4)
        self.assertEqual(receipt["markdown_sha256"], result["markdown_sha256"])
        self.assertEqual(result["events"], 4)

    def test_02_repeated_resume_is_byte_identical_and_side_effect_free(self):
        first = self._execute()
        second = self._execute()
        self.assertEqual(first, second)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM g02_events").fetchone()[0], 4)
        self.assertEqual(len(list(self.out.iterdir())), 2)

    def test_03_deny_other_tenant(self):
        self.contract_data["tenant_id"] = "other-tenant"
        self._denied("SOURCE_ACL_DENIED")

    def test_04_deny_wrong_principal(self):
        self.contract_data["actor"]["principal_id"] = "other-principal"
        self._denied("SOURCE_ACL_DENIED")

    def test_05_deny_revoked_rights(self):
        self.sources_data["sources"]["audit"]["revoked"] = True
        self._denied("SOURCE_REVOKED")

    def test_06_deny_expired_rights(self):
        self.sources_data["sources"]["charter"]["valid_until"] = "2020-01-01T00:00:00Z"
        self._denied("SOURCE_RIGHTS_EXPIRED")

    def test_07_deny_stale_sha(self):
        self.sources_data["sources"]["charter"]["sha256"] = "0" * 64
        self._denied("SOURCE_DIGEST_DRIFT")

    def test_08_deny_out_of_scope_path(self):
        self.sources_data["sources"]["charter"]["path"] = "/etc/passwd"
        self._denied("SOURCE_PATH_OUT_OF_SCOPE")

    def test_09_deny_unqualified_source_rights(self):
        self.sources_data["sources"]["charter"]["rights_basis"] = "UNKNOWN"
        self._denied("SOURCE_RIGHTS_UNPROVEN")

    def test_10_deny_insufficient_tool_quota(self):
        self.contract_data["budget"]["max_tool_calls"] = 1
        self._denied("QUOTA_OR_PROVIDER_DENIED")

    def test_11_deny_unapproved_side_effect(self):
        self.contract_data["authority"]["max_side_effect"] = "irreversible"
        self._denied("RESEARCH_AUTHORITY_DENIED")

    def test_12_deny_malformed_registry_extension(self):
        self.sources_data["secret"] = "untrusted"
        self._denied("UNKNOWN_REGISTRY_FIELD")

    def test_13_deny_partial_source(self):
        sample_root = self.root / "source-copies"
        sample_root.mkdir()
        self.sources_data["root"] = str(sample_root)
        for key, doc in self.sources_data["sources"].items():
            copied = sample_root / (key + ".md")
            copied.write_bytes(Path(doc["path"]).read_bytes())
            doc["path"] = str(copied)
        (sample_root / "audit.md").write_bytes(b"partial")
        self._denied("SOURCE_DIGEST_DRIFT")

    def test_14_deny_source_symlink(self):
        path = self.root / "link.md"
        path.symlink_to(self.sources_data["sources"]["charter"]["path"])
        self.sources_data["sources"]["charter"]["path"] = str(path)
        self._denied("UNSAFE_SOURCE_PATH")

    def test_15_deny_tampered_report(self):
        self._execute()
        (self.out / "g02-test-same-id.md").write_text("malicious report")
        self._denied("OUTCOME_BYTES_CHANGED")
        with self.assertRaises(AssertionError):
            verify(self.db, self.sources_path, self.contract_path,
                   self.out, "g02-test-same-id")

    def test_16_deny_partial_outcome_file(self):
        self._execute()
        (self.out / "g02-test-same-id.json").unlink()
        self._denied("OUTCOME_MISSING_OR_PARTIAL")

    def test_17_deny_immutable_event_mutation(self):
        self._execute()
        with sqlite3.connect(self.db) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE g02_events SET kind='FORGED' WHERE seq=2")
        self.assertEqual(self._execute()["events"], 4)

    def test_18_revoke_after_completion_denies_read_and_checker(self):
        self._execute()
        self.sources_data["sources"]["charter"]["revoked"] = True
        self._save()
        with self.assertRaisesRegex(ResearchDenied, "SOURCE_REVOKED"):
            self._execute()
        with self.assertRaisesRegex(AssertionError, "source not authorized"):
            verify(self.db, self.sources_path, self.contract_path,
                   self.out, "g02-test-same-id")

    def test_19_replay_with_altered_task_identity_fails(self):
        self._execute()
        self.contract_data["task_id"] += "-forged"
        self._denied("TASK_IDENTITY_MISMATCH")

    def test_20_replay_with_altered_source_pins_fails(self):
        self._execute()
        alternate = self.root / "owned"
        alternate.mkdir()
        self.sources_data["root"] = str(alternate)
        for key, doc in self.sources_data["sources"].items():
            copied = alternate / (key + ".md")
            copied.write_bytes(Path(doc["path"]).read_bytes())
            doc["path"] = str(copied)
        # Bytes identical but locator different. Checkpoint pins make it fail closed.
        self._denied("CHECKPOINT_SOURCE_DRIFT")


if __name__ == "__main__":
    unittest.main()
