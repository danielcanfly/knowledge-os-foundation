"""F04 C1 repair03 frozen-Git source closure and unsigned deny-path tests.

UNSIGNED, offline, no private signer, no provider, no Product admission.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src" / "knowledge_engine"))
import m27_c1_f04_unsigned_dual_source_request as request
import m27_c1_f04_external_authority_consumer as c
import m27_c1_gitless_source_proof as gitless


class FrozenSourceClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="repair03-unsigned-only-")
        cls.output = Path(cls.temp.name) / "new-byte-inventory"
        cls.receipt = request.generate(ROOT, cls.output)
        cls.head = cls.receipt["head"]
        cls.tree = cls.receipt["tree"]
        cls.c1 = json.loads(
            (cls.output / "UNSIGNED_C1_15_SOURCE_CONTROLLER_REQUEST.json").read_text())
        cls.f03 = json.loads(
            (cls.output / "UNSIGNED_F03_14_SOURCE_CONTROLLER_REQUEST.json").read_text())
        cls.c1_dir = cls.output / "c1_exact_unsigned_bytes"
        cls.f03_dir = cls.output / "f03_exact_unsigned_bytes"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, source=None, payload=None, *, head=None):
        return gitless.inspect_exact_bundle(
            source or self.c1_dir, payload or self.c1,
            expected_head=head or self.head, expected_tree=self.tree)

    def test_01_exact_15_plus_14_and_no_signing(self):
        self.assertEqual(len(self.c1["files"]), 15)
        self.assertEqual(len(self.f03["files"]), 14)
        self.assertEqual(self.receipt["file_count"], 29)
        self.assertEqual(self.receipt["c1_code_files"], 15)
        self.assertEqual(self.receipt["f03_corpus_files"], 14)
        self.assertEqual(self.receipt["c1_git_import_closure"]["missing"], [])
        self.assertFalse(self.receipt["signed"])
        self.assertFalse(self.receipt["formal_product_pass"])
        self.assertEqual(self.check()["files_verified"], 15)
        self.assertEqual(gitless.inspect_exact_bundle(
            self.f03_dir, self.f03,
            expected_head=self.head, expected_tree=self.tree)["files_verified"], 14)

    def test_02_new_consumer_in_signed_candidate_inventory(self):
        self.assertIn("knowledge_engine/m27_c1_f04_external_authority_consumer.py",
                      {row["path"] for row in self.c1["files"]})

    def test_03_old14_frozen_import_closure_denied(self):
        old = frozenset(x for x in c.C1_MODULES
                        if not x.endswith("/m27_c1_f04_external_authority_consumer.py"))
        with self.assertRaisesRegex(ValueError, "IMPORT_CLOSURE_MISSING"):
            request.validate_frozen_git_import_closure(ROOT, self.head, old)

    def test_04_tampered_sha_denied(self):
        obj = copy.deepcopy(self.c1)
        obj["files"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(gitless.GitlessDenied, "SHA256_MISMATCH"):
            self.check(payload=obj)

    def test_05_tampered_oid_denied(self):
        obj = copy.deepcopy(self.c1)
        obj["files"][0]["git_blob_oid"] = "f" * 40
        with self.assertRaisesRegex(gitless.GitlessDenied, "GIT_BLOB_OID_MISMATCH"):
            self.check(payload=obj)

    def test_06_protected_path_denied(self):
        obj = copy.deepcopy(self.c1)
        obj["files"][0]["path"] = "knowledge_engine/.env"
        with self.assertRaisesRegex(gitless.GitlessDenied, "FORBIDDEN_SOURCE_PATH"):
            self.check(payload=obj)

    def test_07_expired_ttl_denied(self):
        obj = copy.deepcopy(self.c1)
        obj["expires_at"] = int(time.time()) - 1
        with self.assertRaisesRegex(gitless.GitlessDenied, "EXPIRED"):
            self.check(payload=obj)

    def test_08_extra_file_denied(self):
        with tempfile.TemporaryDirectory(prefix="repair03-extra-") as folder:
            dest = Path(folder) / "c1"
            shutil.copytree(self.c1_dir, dest)
            (dest / "extraneous.py").write_text("pass\n")
            with self.assertRaisesRegex(gitless.GitlessDenied, "EXTRA_OR_MISSING"):
                self.check(source=dest)

    def test_09_symlink_denied(self):
        with tempfile.TemporaryDirectory(prefix="repair03-symlink-") as folder:
            dest = Path(folder) / "c1"
            shutil.copytree(self.c1_dir, dest)
            (dest / "knowledge_engine" / "danger.py").symlink_to(
                dest / "knowledge_engine" / "m27_c1_f04_external_authority_consumer.py")
            with self.assertRaisesRegex(gitless.GitlessDenied, "UNAUTHORIZED_SYMLINK"):
                self.check(source=dest)

    def test_10_wrong_head_denied(self):
        with self.assertRaisesRegex(gitless.GitlessDenied, "GIT_IDENTITY_MISMATCH"):
            self.check(head="f" * 40)

    def test_11_invalid_git_mode_denied(self):
        obj = copy.deepcopy(self.c1)
        obj["files"][0]["git_mode"] = "120000"
        with self.assertRaisesRegex(gitless.GitlessDenied, "DUPLICATE_OR_INVALID"):
            self.check(payload=obj)

    def test_12_four_root_pins_remain_unapproved(self):
        import m27_c1_genuine_native_generation_seam as live
        import m27_f03_source_rights_admission as f03
        self.assertIsNone(c.RELEASE_CONTROLLER_ROOT_SHA256)
        self.assertIsNone(gitless.C1_GITLESS_TRUST_ROOT_SHA256)
        self.assertIsNone(f03.F03_EXTERNAL_SOURCE_ROOT_SHA256)
        self.assertIsNone(live.TRUST_ROOT_MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
