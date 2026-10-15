from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wave_b02.authority import (
    B01_HEAD,
    B01_TREE,
    REPO,
    ReplayGuard,
    build_authority_ledger,
    enforce_provider_budget,
    evaluate_release_gates,
    receipt_is_valid,
    validate_local_model_runtime,
)
from wave_b02.candidate import build_candidate, validate_architecture


class AuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = build_authority_ledger()

    def test_local_preflight_is_authorized_but_formal_release_is_not(self):
        gates = evaluate_release_gates(self.ledger)
        self.assertIs(gates["nonprod_preflight_engineering_pass"], True)
        self.assertIs(gates["formal_product_go"], False)
        self.assertIs(gates["c28_live_trial"], False)
        self.assertIs(gates["deployment_permitted"], False)

    def test_missing_receipt_fails_closed(self):
        row = copy.deepcopy(self.ledger["entries"]["b02_local_engineering"])
        row["evidence"] = []
        self.assertIs(receipt_is_valid(row), False)

    def test_forged_receipt_digest_fails_closed(self):
        row = copy.deepcopy(self.ledger["entries"]["b01_accepted_source"])
        row["evidence"][0]["sha256"] = "0" * 64
        self.assertIs(receipt_is_valid(row), False)

    def test_expired_receipt_fails_closed(self):
        row = copy.deepcopy(self.ledger["entries"]["b02_local_engineering"])
        row["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.assertIs(receipt_is_valid(row), False)

    def test_explicit_refusals_remain_denied(self):
        for name in ("ci_signing_staging", "q34_native_streaming",
                     "product_qdrant", "a08_coding_source_edit"):
            self.assertEqual(self.ledger["entries"][name]["status"], "EXPLICITLY_REFUSED")
            self.assertIs(receipt_is_valid(self.ledger["entries"][name]), False)

    def test_wrong_issuer_bad_certificate_and_replay_are_denied(self):
        guard = ReplayGuard()
        with self.assertRaisesRegex(PermissionError, "WRONG_ISSUER"):
            guard.admit({"issuer": "evil", "certificate_sha256": "b" * 64, "nonce": "1"})
        with self.assertRaisesRegex(PermissionError, "CERTIFICATE_MISMATCH"):
            guard.admit({"issuer": "b02-local-witness", "certificate_sha256": "c" * 64,
                         "nonce": "2"})
        envelope = {"issuer": "b02-local-witness", "certificate_sha256": "b" * 64,
                    "nonce": "3"}
        guard.admit(envelope)
        with self.assertRaisesRegex(PermissionError, "MALICIOUS_REPLAY"):
            guard.admit(envelope)

    def test_provider_runaway_and_external_call_are_denied(self):
        with self.assertRaisesRegex(RuntimeError, "PROVIDER_RUNAWAY_DENIED"):
            enforce_provider_budget([{"duration_ms": 9}, {"duration_ms": 9}],
                                    max_attempts=1, max_total_ms=100)
        with self.assertRaisesRegex(RuntimeError, "EXTERNAL_PROVIDER_CALL_DENIED"):
            enforce_provider_budget([{"duration_ms": 1, "billable_provider_calls": 1}],
                                    max_attempts=1, max_total_ms=100)

    def test_model_not_loaded_fails_closed(self):
        manifest = REPO / "wave_b01/components/a04/MODEL_RUNTIME_MANIFEST.json"
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "MODEL_NOT_LOADED"):
                validate_local_model_runtime(Path(folder), manifest)


class CandidateTests(unittest.TestCase):
    def test_source_identity_is_exact_accepted_b01(self):
        head = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", B01_HEAD], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", f"{B01_HEAD}^{{tree}}"], text=True).strip()
        self.assertEqual(head, B01_HEAD)
        self.assertEqual(tree, B01_TREE)

    def test_candidate_build_is_deterministic_and_unsigned(self):
        with tempfile.TemporaryDirectory() as folder:
            one = build_candidate(Path(folder) / "one")
            two = build_candidate(Path(folder) / "two")
        self.assertEqual(one["oci_content"]["layer_sha256"], two["oci_content"]["layer_sha256"])
        self.assertEqual(one["oci_content"]["manifest_sha256"], two["oci_content"]["manifest_sha256"])
        self.assertEqual(one["classification"], "UNSIGNED_NONPROD_CONTENT_ONLY")
        self.assertIs(one["signed_runnable_product"], False)
        self.assertGreaterEqual(one["source_file_count"], 70)

    def test_oci_architecture_mismatch_is_denied(self):
        with self.assertRaisesRegex(ValueError, "OCI_ARCH_MISMATCH"):
            validate_architecture("definitely-wrong", expected_arch="arm64")


if __name__ == "__main__":
    unittest.main(verbosity=2)
