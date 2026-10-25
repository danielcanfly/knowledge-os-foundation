"""F04-C1-02 isolated synthetic Ed25519 fixtures, NEVER external issuers.

These signatures test the PUBLIC verifier only. No fixture private key, PIN,
receipt, source-rights grant, or generated text is admitted as Product proof.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "knowledge_engine"))
import m27_c1_f04_external_authority_consumer as f04
import m27_c1_genuine_native_generation_seam as live
import m27_c1_gitless_source_proof as gitless


class PublicConsumerFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="F04_TEST_FIXTURE_NOT_ISSUER_")
        cls.tmp = Path(cls.folder.name)
        cls.keys = {}
        for role in ("release_controller", *f04.ROLES):
            priv, pub = cls.tmp / (role + ".private.pem"), cls.tmp / (role + ".public.pem")
            subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519",
                            "-out", str(priv)], check=True, capture_output=True)
            subprocess.run(["openssl", "pkey", "-in", str(priv),
                            "-pubout", "-out", str(pub)], check=True, capture_output=True)
            cls.keys[role] = (priv, pub.read_text())
        cls.source = cls.tmp / "14-source"
        for path in sorted(f04.f03.F03_GITLESS_ALLOWED_A05):
            destination = cls.source / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, destination)
        cls.c1_source = cls.tmp / "complete-c1-modules"
        for name in sorted(f04.C1_MODULES):
            target = cls.c1_source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "src" / name, target)
        cls.now = int(time.time())
        cls.head = "a"*40
        cls.tree = "b"*40
        cls.task = {
            "task_sha256": "c"*64, "request_id": "r"*48,
            "nonce": "e"*48, "source_proof_sha256": "d"*64,
            "rights_epoch": 2}
        cls.task["request_id"] = "1"*48
        role_keys = {
            role: {"principal": "principal-" + role,
                   "custodian": "custody-" + role,
                   "public_key_pem": cls.keys[role][1],
                   "scope": "NONPROD_EXACT_C1_TASK_ONLY"}
            for role in f04.ROLES}
        release = {
            "schema": "m27.external-independent-trust/v1",
            "head": cls.head, "tree": cls.tree,
            "source_manifest_sha256": f04.CORPUS,
            "source_release_id": f04.f03.A05_RELEASE_ID,
            "tenant": "owner-internal",
            "roles": role_keys, "release_principal": "principal-release-controller",
            "release_custodian": "custody-release-controller",
            "revocation_epoch": 2,
            "issued_at": cls.now - 1, "expires_at": cls.now + 240}
        files = []
        for name in sorted(f04.f03.F03_GITLESS_ALLOWED_A05):
            raw = (cls.source / name).read_bytes()
            files.append({
                "path": name, "sha256": f04.digest(raw),
                "git_blob_oid": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                "git_mode": "100644"})
        manifest = {
            "schema": gitless.ABI, "head": cls.head, "tree": cls.tree,
            "source_controller": role_keys["source_controller"]["principal"],
            "expires_at": cls.now + 1800, "files": files,
            "tenant": "owner-internal", "source_release_id": f04.f03.A05_RELEASE_ID}
        c1_files = []
        for name in sorted(f04.C1_MODULES):
            raw = (cls.c1_source / name).read_bytes()
            c1_files.append({
                "path": name, "sha256": f04.digest(raw),
                "git_blob_oid": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                "git_mode": "100644"})
        c1_manifest = {
            "schema": gitless.ABI, "head": cls.head, "tree": cls.tree,
            "source_controller": role_keys["source_controller"]["principal"],
            "expires_at": cls.now + 1800, "files": c1_files,
            "tenant": "owner-internal", "source_release_id": f04.f03.A05_RELEASE_ID}
        rights = {
            "task_sha256": cls.task["task_sha256"],
            "request_id": cls.task["request_id"], "source_sha256": f04.CORPUS,
            "source_proof_sha256": cls.task["source_proof_sha256"],
            "tenant": "owner-internal", "source_release_id": f04.f03.A05_RELEASE_ID,
            "head": cls.head, "tree": cls.tree, "documents": f04.A05_DOCS,
            "role": "source_controller", "issuer": role_keys["source_controller"]["principal"],
            "nonce": cls.task["nonce"], "issued_at": cls.now - 1,
            "expires_at": cls.now + 240, "region": "test-region",
            "retention_seconds": 0, "serving_ttl_seconds": 120,
            "revocation_uri": "https://invalid.example/revocations",
            "acl": {"tenant": "owner-internal", "read": ["internal"]},
            "gitless_manifest_sha256": f04.digest(f04.canonical(manifest)),
            "c1_gitless_manifest_sha256": f04.digest(f04.canonical(c1_manifest)),
            "source_rights_epoch": cls.task["rights_epoch"]}
        revocation = {
            "schema": "m27.external-trust-revocations/v1",
            "release_sha256": f04.digest(f04.canonical(release)),
            "epoch": 2, "revoked_principals": [],
            "issued_at": cls.now - 1, "expires_at": cls.now + 240}
        cls.fixture = {
            "release_root_pem": cls.keys["release_controller"][1],
            "release_signed": cls.sign("release_controller", release),
            "revocations_signed": cls.sign("release_controller", revocation),
            "rights_signed": cls.sign("source_controller", rights),
            "gitless_signed": cls.sign("source_controller", manifest),
            "gitless_source_directory": str(cls.source),
            "c1_gitless_signed": cls.sign("source_controller", c1_manifest),
            "c1_gitless_source_directory": str(cls.c1_source)}
        cls.root_pin = f04.digest(cls.keys["release_controller"][1].encode())
        cls.receipts = []
        expectations = [
            ("provider_controller", "start", "", "", 0, 0),
            ("source_controller", "rights", "", "", 0, 0),
            ("semantic_issuer", "claim", f04.CLAIMS[0],
             "00_m27_architecture_overview.md", 0, 0),
            ("client_idp", "ack", f04.CLAIMS[0],
             "00_m27_architecture_overview.md", 100, 120),
            ("semantic_issuer", "claim", f04.CLAIMS[1],
             "01_contracts.md", 0, 0),
            ("client_idp", "ack", f04.CLAIMS[1],
             "01_contracts.md", 200, 230),
            ("client_idp", "terminal", "", "", 0, 0)]
        for role, event, claim, document, delivered, ack in expectations:
            row = {
                "role": role, "issuer": role_keys[role]["principal"],
                "event": event, "claim_id": claim,
                "task_sha256": cls.task["task_sha256"],
                "request_id": cls.task["request_id"],
                "nonce": cls.task["nonce"],
                "source_sha256": f04.CORPUS,
                "source_proof_sha256": cls.task["source_proof_sha256"],
                "issued_at": cls.now-1, "expires_at": cls.now+240,
                "text_sha256": (("f"*64) if claim == f04.CLAIMS[0] else
                                ("0"*64) if claim == f04.CLAIMS[1] else ""),
                "citation_document": document,
                "challenge_sha256": "a"*64 if event == "ack" else "",
                "server_pid": 123 if event == "ack" else 0,
                "client_pid": 456 if event == "ack" else 0,
                "delivered_ns": delivered, "ack_ns": ack,
                "provider_done_ns": 300 if event == "ack" else 0}
            cls.receipts.append(cls.sign(role, row))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    @classmethod
    def sign(cls, role, payload):
        private = cls.keys[role][0]
        with tempfile.TemporaryDirectory(prefix="f04-signature-fixture-") as tmp:
            message, signature = Path(tmp) / "payload", Path(tmp) / "sig"
            message.write_bytes(f04.canonical(payload))
            subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(private),
                            "-rawin", "-in", str(message), "-out", str(signature)],
                           capture_output=True, check=True)
            return {"payload": copy.deepcopy(payload),
                    "signature_b64": base64.b64encode(signature.read_bytes()).decode()}

    def inspect(self, evidence=None, *, now=None, head=None, pin=None):
        return f04.verify_release_structure(
            evidence if evidence is not None else self.fixture,
            pinned_root_sha256=pin if pin is not None else self.root_pin,
            expected_head=head if head is not None else self.head,
            expected_tree=self.tree,
            now=now if now is not None else self.now)

    def resign_release_and_revocations(self, evidence):
        p = evidence["release_signed"]["payload"]
        evidence["release_signed"] = self.sign("release_controller", p)
        r = evidence["revocations_signed"]["payload"]
        r["release_sha256"] = f04.digest(f04.canonical(p))
        evidence["revocations_signed"] = self.sign("release_controller", r)

    def test_01_no_real_release_pin_closes_runtime(self):
        self.assertIsNone(f04.RELEASE_CONTROLLER_ROOT_SHA256)
        self.assertIsNone(gitless.C1_GITLESS_TRUST_ROOT_SHA256)
        self.assertIsNone(f04.f03.F03_EXTERNAL_SOURCE_ROOT_SHA256)
        with self.assertRaisesRegex(f04.Denied, "ROOT_NOT_APPROVED"):
            f04.require_live_launch(None, task=self.task, expected_head=self.head,
                                    expected_tree=self.tree)

    def test_02_valid_crypto_fixture_is_not_product_pass(self):
        x = self.inspect()
        self.assertTrue(x["public_signature_valid"])
        self.assertFalse(x["formal_product_pass"])
        self.assertIn("NOT_REAL_AUTHORITY", x["qualification"])

    def test_03_fixture_signed_rights_and_complete_real_bytes(self):
        x = f04.verify_source_rights(self.fixture, self.inspect(),
                                      task=self.task, now=self.now)
        self.assertEqual(x["verified_physical_files"], 29)
        self.assertEqual(x["verified_f03_source_files"], 14)
        self.assertEqual(x["verified_c1_module_files"], 15)
        self.assertFalse(x["product_pass"])

    def test_04_fixture_seven_signed_same_task_receipts(self):
        x = f04.verify_task_receipts(self.inspect(), self.receipts,
                                    task=self.task, now=self.now)
        self.assertEqual(x["cryptographically_verified_receipts"], 7)
        self.assertFalse(x["actual_os_delivery_independently_observed"])

    def test_05_nonfixture_product_entry_rejects_fixture_pin(self):
        with self.assertRaisesRegex(f04.Denied, "ROOT_NOT_APPROVED"):
            f04.require_live_launch(Path(self.tmp / "anything"),
                                    task=self.task,
                                    expected_head=self.head, expected_tree=self.tree)

    def test_06_missing_root_rejected(self):
        with self.assertRaisesRegex(f04.Denied, "NO_APPROVED_RELEASE_ROOT"):
            self.inspect(pin="invalid")

    def test_07_wrong_root_pin_rejected(self):
        with self.assertRaisesRegex(f04.Denied, "PIN_MISMATCH"):
            self.inspect(pin="0"*64)

    def test_08_tampered_signature_rejected(self):
        evidence = copy.deepcopy(self.fixture)
        evidence["release_signed"]["payload"]["tree"] = "c"*40
        with self.assertRaisesRegex(f04.Denied, "PUBLIC_SIGNATURE_MISMATCH"):
            self.inspect(evidence)

    def test_09_role_swap_denied(self):
        evidence = copy.deepcopy(self.fixture)
        p = evidence["release_signed"]["payload"]
        p["roles"]["client_idp"] = p["roles"]["source_controller"].copy()
        self.resign_release_and_revocations(evidence)
        with self.assertRaisesRegex(f04.Denied, "FIVE_ROLE_SEPARATION"):
            self.inspect(evidence)

    def test_10_release_controller_must_be_fifth_distinct(self):
        evidence = copy.deepcopy(self.fixture)
        p = evidence["release_signed"]["payload"]
        p["release_custodian"] = p["roles"]["provider_controller"]["custodian"]
        self.resign_release_and_revocations(evidence)
        with self.assertRaisesRegex(f04.Denied, "FIVE_ROLE_SEPARATION"):
            self.inspect(evidence)

    def test_11_wrong_source_head_fails(self):
        with self.assertRaisesRegex(f04.Denied, "SOURCE_OR_ROOT_SCOPE"):
            self.inspect(head="f"*40)

    def test_12_time_expired_fails(self):
        with self.assertRaisesRegex(f04.Denied, "TIME_WINDOW"):
            self.inspect(now=self.now+301)

    def test_13_future_dated_release_fails(self):
        with self.assertRaisesRegex(f04.Denied, "TIME_WINDOW"):
            self.inspect(now=self.now-300)

    def test_14_revoked_source_controller_fails(self):
        evidence = copy.deepcopy(self.fixture)
        r = evidence["revocations_signed"]["payload"]
        r["revoked_principals"] = ["principal-source_controller"]
        evidence["revocations_signed"] = self.sign("release_controller", r)
        with self.assertRaisesRegex(f04.Denied, "REVOKED"):
            self.inspect(evidence)

    def test_15_revocation_epoch_drift_denied(self):
        evidence = copy.deepcopy(self.fixture)
        r = evidence["revocations_signed"]["payload"]
        r["epoch"] = 1
        evidence["revocations_signed"] = self.sign("release_controller", r)
        with self.assertRaisesRegex(f04.Denied, "REVOKED_OR_DRIFTED"):
            self.inspect(evidence)

    def test_16_a05_other_region_or_acl_denied(self):
        e = copy.deepcopy(self.fixture)
        p = e["rights_signed"]["payload"]
        p["acl"] = {"tenant": "foreign", "read": ["public"]}
        e["rights_signed"] = self.sign("source_controller", p)
        with self.assertRaisesRegex(f04.Denied, "ONLINE_SERVING_RIGHTS"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_17_rights_ttl_too_long_denied(self):
        e = copy.deepcopy(self.fixture)
        p = e["rights_signed"]["payload"]
        p["serving_ttl_seconds"] = 301
        e["rights_signed"] = self.sign("source_controller", p)
        with self.assertRaisesRegex(f04.Denied, "ONLINE_SERVING_RIGHTS"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_18_rights_exact_two_docs_drift_denied(self):
        e = copy.deepcopy(self.fixture)
        p = e["rights_signed"]["payload"]
        p["documents"]["01_contracts.md"] = "1"*64
        e["rights_signed"] = self.sign("source_controller", p)
        with self.assertRaisesRegex(f04.Denied, "ONLINE_SERVING_RIGHTS|SCHEMA|MISMATCH"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_19_unsigned_gitless_substitution_denied(self):
        e = copy.deepcopy(self.fixture)
        e["gitless_signed"]["payload"]["source_controller"] = "fake"
        with self.assertRaisesRegex(f04.Denied, "PUBLIC_SIGNATURE_MISMATCH"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_20_wrong_git_blob_sha_denied(self):
        e = copy.deepcopy(self.fixture)
        git = e["gitless_signed"]["payload"]
        git["files"][0]["sha256"] = "1"*64
        e["gitless_signed"] = self.sign("source_controller", git)
        rights = e["rights_signed"]["payload"]
        rights["gitless_manifest_sha256"] = f04.digest(f04.canonical(git))
        e["rights_signed"] = self.sign("source_controller", rights)
        with self.assertRaisesRegex(gitless.GitlessDenied, "SHA256_MISMATCH"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_21_same_task_nonce_swap_denied(self):
        e = copy.deepcopy(self.receipts)
        p = e[3]["payload"]
        p["nonce"] = "f"*48
        e[3] = self.sign("client_idp", p)
        with self.assertRaisesRegex(f04.Denied, "RECEIPT_TASK_ROLE"):
            f04.verify_task_receipts(self.inspect(), e, task=self.task, now=self.now)

    def test_22_client_ack_after_provider_done_denied(self):
        e = copy.deepcopy(self.receipts)
        p = e[3]["payload"]
        p["ack_ns"] = p["provider_done_ns"] + 1
        e[3] = self.sign("client_idp", p)
        with self.assertRaisesRegex(f04.Denied, "ACK_NOT_PRETERMINAL"):
            f04.verify_task_receipts(self.inspect(), e, task=self.task, now=self.now)

    def test_23_client_same_pid_denied(self):
        e = copy.deepcopy(self.receipts)
        p = e[3]["payload"]
        p["client_pid"] = p["server_pid"]
        e[3] = self.sign("client_idp", p)
        with self.assertRaisesRegex(f04.Denied, "ACK_NOT_PRETERMINAL"):
            f04.verify_task_receipts(self.inspect(), e, task=self.task, now=self.now)

    def test_24_semantic_text_tamper_denied(self):
        e = copy.deepcopy(self.receipts)
        p = e[2]["payload"]
        p["text_sha256"] = "7"*64
        e[2] = self.sign("semantic_issuer", p)
        with self.assertRaisesRegex(f04.Denied, "SEMANTIC_AND_CLIENT_TEXT"):
            f04.verify_task_receipts(self.inspect(), e, task=self.task, now=self.now)

    def test_25_missing_seventh_terminal_denied(self):
        with self.assertRaisesRegex(f04.Denied, "SEVEN_RECEIPTS"):
            f04.verify_task_receipts(self.inspect(), self.receipts[:-1],
                                     task=self.task, now=self.now)

    def test_26_source_drift_task_denied(self):
        altered = {**self.task, "source_proof_sha256": "1"*64}
        with self.assertRaisesRegex(f04.Denied, "RECEIPT_TASK_ROLE"):
            f04.verify_task_receipts(self.inspect(), self.receipts,
                                     task=altered, now=self.now)

    def test_27_role_receipt_swap_denied(self):
        e = copy.deepcopy(self.receipts)
        e[0], e[1] = e[1], e[0]
        with self.assertRaisesRegex(f04.Denied, "PUBLIC_SIGNATURE_MISMATCH|RECEIPT_TASK_ROLE"):
            f04.verify_task_receipts(self.inspect(), e, task=self.task, now=self.now)

    def test_28_all_native_fail_closed_limits_unchanged(self):
        self.assertIsNone(live.TRUST_ROOT_MANIFEST_SHA256)
        with tempfile.TemporaryDirectory(prefix="f04-live-deny-") as temp:
            candidate = live.NativeLiveProduct(
                repo=ROOT, fence=Path(temp) / "fence",
                journal=Path(temp) / "journal")
            with self.assertRaisesRegex(live.NotQualified, "ROOT_NOT_ADMITTED"):
                candidate.start({"request_id": self.task["request_id"]})
            self.assertEqual(candidate.provider_invocations, 0)
            self.assertEqual(candidate.sessions, {})

    def test_29_c1_signed_complete_modules_blob_tamper_denied(self):
        e = copy.deepcopy(self.fixture)
        source = e["c1_gitless_signed"]["payload"]
        source["files"][0]["git_blob_oid"] = "1"*40
        e["c1_gitless_signed"] = self.sign("source_controller", source)
        rights = e["rights_signed"]["payload"]
        rights["c1_gitless_manifest_sha256"] = f04.digest(f04.canonical(source))
        e["rights_signed"] = self.sign("source_controller", rights)
        with self.assertRaisesRegex(gitless.GitlessDenied, "GIT_BLOB_OID_MISMATCH"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_30_c1_signed_missing_module_denied(self):
        e = copy.deepcopy(self.fixture)
        source = e["c1_gitless_signed"]["payload"]
        source["files"].pop()
        e["c1_gitless_signed"] = self.sign("source_controller", source)
        rights = e["rights_signed"]["payload"]
        rights["c1_gitless_manifest_sha256"] = f04.digest(f04.canonical(source))
        e["rights_signed"] = self.sign("source_controller", rights)
        with self.assertRaisesRegex(f04.Denied, "C1_COMPLETE_MODULES"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_31_c1_gitless_rights_manifest_unbound_denied(self):
        e = copy.deepcopy(self.fixture)
        rights = e["rights_signed"]["payload"]
        rights["c1_gitless_manifest_sha256"] = "f"*64
        e["rights_signed"] = self.sign("source_controller", rights)
        with self.assertRaisesRegex(f04.Denied, "C1_COMPLETE_MODULES"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_31a_missing_new_runtime_consumer_denied(self):
        e = copy.deepcopy(self.fixture)
        source = e["c1_gitless_signed"]["payload"]
        source["files"] = [row for row in source["files"]
                           if row["path"] !=
                           "knowledge_engine/m27_c1_f04_external_authority_consumer.py"]
        e["c1_gitless_signed"] = self.sign("source_controller", source)
        rights = e["rights_signed"]["payload"]
        rights["c1_gitless_manifest_sha256"] = f04.digest(f04.canonical(source))
        e["rights_signed"] = self.sign("source_controller", rights)
        with self.assertRaisesRegex(f04.Denied, "C1_COMPLETE_MODULES"):
            f04.verify_source_rights(e, self.inspect(), task=self.task, now=self.now)

    def test_31b_runtime_static_import_not_in_complete_source_denied(self):
        with tempfile.TemporaryDirectory(prefix="repair03-missing-import-") as td:
            root = Path(td)
            for name in sorted(f04.C1_MODULES):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / "src" / name, p)
            target = root / "knowledge_engine/m27_c1_genuine_native_generation_seam.py"
            with target.open("ab") as handle:
                handle.write(b"\nimport m27_unlisted_local_runtime_dependency\n")
            with self.assertRaisesRegex(f04.Denied, "LOCAL_IMPORT_NOT_IN_SOURCE_MANIFEST"):
                f04._require_c1_staged_import_closure(root, f04.C1_MODULES)

    def test_32_native_f04_cli_new_argument_present(self):
        import inspect
        import m27_c1_current_native_product_nonprod as app
        self.assertIn("release_evidence_file", inspect.signature(app.serve).parameters)
        self.assertIn("release_evidence_file", inspect.signature(app.Candidate).parameters)
        self.assertIn("release_evidence", inspect.signature(live.NativeLiveProduct).parameters)


if __name__ == "__main__":
    unittest.main()