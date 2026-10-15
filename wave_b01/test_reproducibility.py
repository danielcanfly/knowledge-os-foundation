from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from wave_b01 import seal_candidate_manifest_v2 as candidate
from wave_b01 import seal_receipt_linkage_v2 as linkage


ROOT = Path(__file__).resolve().parents[1]
WAVE = ROOT / "wave_b01"
A04 = WAVE / "components" / "a04"
BUNDLE = WAVE / "evidence" / "a04_repro_v2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReproducibilityV2Tests(unittest.TestCase):
    def test_all_ten_receipt_log_pairs_have_honest_v2_links(self):
        expected = linkage.build()
        actual = json.loads(linkage.OUTPUT.read_text())
        self.assertEqual(actual, expected)
        self.assertEqual(actual["pair_count"], 10)
        self.assertEqual(actual["verified_pair_count"], 10)
        self.assertEqual(len(actual["known_v1_pointer_mismatches"]), 3)
        for item in actual["records"].values():
            self.assertTrue(item["v2_archive_matches_declared"])

    def test_external_runtime_manifest_and_licenses_are_pinned(self):
        manifest_path = A04 / "MODEL_RUNTIME_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["schema"], "m27.a04.external-model-runtime/v2")
        self.assertTrue(manifest["staging_policy"]["runtime_must_be_outside_git_checkout"])
        self.assertFalse(manifest["staging_policy"]["large_assets_committed_to_git"])
        license_path = A04 / manifest["model"]["license_file"]
        self.assertEqual(sha256(license_path), manifest["model"]["license_sha256"])
        self.assertEqual(manifest["model"]["license"], "Apache-2.0")
        self.assertEqual(manifest["llama_cpp"]["license"], "MIT")

    def test_bad_runtime_assets_fail_closed_and_leave_no_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = root / "assets"
            assets.mkdir()
            (assets / "qwen2.5-0.5b-instruct-q4_k_m.gguf").write_bytes(b"wrong")
            (assets / "llama-b11425-bin-macos-arm64.tar.gz").write_bytes(b"wrong")
            destination = root / "runtime"
            completed = subprocess.run(
                [os.environ.get("A04_PYTHON", "/opt/homebrew/bin/python3.11"),
                 "-B", str(A04 / "stage_model_runtime.py"),
                 "--asset-dir", str(assets), "--destination", str(destination)],
                text=True, capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(destination.exists())

    def test_a04_bundle_is_complete_safe_and_content_addressed(self):
        manifest = json.loads((BUNDLE / "BUNDLE_MANIFEST.json").read_text())
        self.assertEqual(manifest["secret_scan"], "PASS_NO_REDACTION_REQUIRED")
        self.assertFalse(manifest["contains_tokens_or_credentials"])
        self.assertFalse(manifest["contains_protected_gold"])
        self.assertGreaterEqual(manifest["file_count"], 40)
        for name, item in manifest["files"].items():
            self.assertEqual(sha256(BUNDLE / name), item["sha256"])
        portable = json.loads((BUNDLE / "PORTABLE_CLIENT_RECEIPTS_V2.json").read_text())
        replay = json.loads((BUNDLE / "REPRO_RUN_RECEIPT_V2.json").read_text())
        self.assertEqual(replay["status"], "PASS")
        self.assertFalse(replay["runtime_warmup"]["timed_out"])
        self.assertEqual(replay["runtime_warmup"]["exit_code"], 0)
        self.assertTrue(replay["runtime_warmup"]["cache_home_outside_checkout"])
        self.assertTrue(replay["runtime_warmup"]["cache_tmp_outside_checkout"])
        for name in ("runtime_warmup.stdout.log", "runtime_warmup.stderr.log"):
            self.assertIn(name, manifest["files"])
        self.assertEqual(portable["stub"]["counts"], {"total": 21, "pass": 21, "fail": 0})
        self.assertEqual(portable["real_model"]["counts"], {"pass": 8, "fail": 0, "total": 8})
        self.assertEqual(len(portable["stub"]["cases"]), 21)
        self.assertEqual(len(portable["real_model"]["cases"]), 8)
        for group in (portable["stub"]["cases"], portable["real_model"]["cases"]):
            for item in group:
                self.assertFalse(Path(item["receipt"]).is_absolute())
                self.assertEqual(sha256(BUNDLE / item["receipt"]), item["receipt_sha256"])

    def test_candidate_v2_full_pins_and_negative_authority(self):
        manifest = json.loads(candidate.OUTPUT.read_text())
        candidate.verify(manifest)
        self.assertEqual(manifest["imported_file_count"], len(manifest["imported_files"]))
        for identity in manifest["accepted_inputs"].values():
            self.assertEqual(len(identity["head"]), 40)
            self.assertEqual(len(identity["tree"]), 40)
        tampered = json.loads(json.dumps(manifest))
        tampered["negative_authority_assertions"]["production_authority"] = True
        with self.assertRaisesRegex(ValueError, "AUTHORITY_ESCALATION"):
            candidate.verify(tampered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
