"""Non-billable strict C1 DEV adapter contracts; never impersonates Provider."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as dev
import m27_c1_genuine_native_generation_seam as live

class MiniMaxDevScopedContracts(unittest.TestCase):
    def test_01_two_distinct_source_entailed_material_obligations(self):
        positives=(
          ("Verification is in the Execution & Governance Plane.",0),
          ("The Execution and Governance Plane includes Verification.",0),
          ("Verification is part of the Execution & Governance Plane.",0),
          ("PolicyEngine decides deterministic enforcement.",1),
          ("The PolicyEngine is responsible for deterministic policy enforcement.",1),
          ("Deterministic policy enforcement is decided by PolicyEngine.",1))
        for text,ob in positives:
            with self.subTest(text=text):
                self.assertIsNotNone(dev.SEMANTIC[ob].fullmatch(text))
                self.assertIsNone(dev.SEMANTIC[1-ob].fullmatch(text))
    def test_02_denies_hallucinated_negations_and_wrong_authority(self):
        invalid=[
          "Verification is NOT in the Execution & Governance Plane.",
          "Verification is in the Intelligence Plane.",
          "The Execution & Governance Plane excludes Verification.",
          "PolicyEngine never decides deterministic enforcement.",
          "Agent decides deterministic enforcement.",
          "PolicyEngine decides production release.",
          "Verification belongs to the Execution & Governance Plane and Agent decides.",
          "PolicyEngine decides deterministic enforcement without ACL.",
          "Verification is in the Execution & Governance Plane. Extra unsupported claim."
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.assertFalse(any(p.fullmatch(value) for p in dev.SEMANTIC))
    def test_03_formal_external_authority_remains_unqualified(self):
        self.assertIsNone(live.TRUST_ROOT_MANIFEST_SHA256)
        self.assertIn("NOT_CLOUDFLARE_PRIMARY",dev.PROVIDER_DEV_SCOPE)
        self.assertEqual(dev.MODEL,"MiniMax-M3")
        self.assertEqual(len(dev.PINNED),3)
        self.assertFalse(dev.ABI.endswith("product-pass"))
    def test_04_missing_old_vendor_root_does_not_fallback_to_other_route(self):
        with self.assertRaises((ValueError,FileNotFoundError)):
            dev.vendor_generator(ROOT/"never-admitted-g01-vendor")

    def test_05_authentic_g01_genuine_provider_adapter_pinned_readonly(self):
        vendor=Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/"
          "07_MASTER_REBASE_20261010/08_MASTER_TAKEOVER_20261012/"
          "09_MASTER_RESET_POST_V34_20261013/06_WORKSITES/"
          "PARALLEL_VNEXT_20261014/REPLAN_EK_20261017/"
          "G01_GENUINE_QA_20261018/tools/g01_vendor")
        stream=dev.vendor_generator(vendor)
        self.assertTrue(callable(stream))
        self.assertIn("'max_tokens':128",stream.__globals__["b1"].VM_PROVIDER_SCRIPT)
        self.assertNotIn("'max_tokens':650",stream.__globals__["b1"].VM_PROVIDER_SCRIPT)

    def test_06_source_recheck_expiring_during_io_denies_after_io(self):
        # This is the historical failure mode: verification starts before
        # the deadline and finishes after it. No late publication is allowed.
        proofs=[{"obligation_id":"real_owner_source_byte_proof"}]
        actual_sha=dev.digest(dev.canon(proofs))
        reads=[]
        def source():
            reads.append(True)
            return proofs
        stub=SimpleNamespace(deadline_ns=150,
             live=SimpleNamespace(_source=source,
                pending={"source_proofs_sha256":actual_sha}))
        with patch.object(dev.time,"monotonic_ns",side_effect=[100,200]):
            with self.assertRaisesRegex(ValueError,"C1_ONE_TASK_30_SECOND_DEADLINE"):
                dev.Server.current(stub)
        self.assertEqual(len(reads),1)

    def test_07_already_expired_request_does_not_even_reopen_sources(self):
        reads=[]
        def no_read():
            reads.append(True)
            raise AssertionError("EXPIRED_SOURCE_IO_CALLED")
        stub=SimpleNamespace(deadline_ns=150,
             live=SimpleNamespace(_source=no_read,
                pending={"source_proofs_sha256":"NOT_USED"}))
        with patch.object(dev.time,"monotonic_ns",return_value=200):
            with self.assertRaisesRegex(ValueError,"C1_ONE_TASK_30_SECOND_DEADLINE"):
                dev.Server.current(stub)
        self.assertEqual(reads,[])

    def test_08_live_rights_are_still_rechecked_within_deadline(self):
        proofs=[{"obligation_id":"source1"},{"obligation_id":"source2"}]
        actual_sha=dev.digest(dev.canon(proofs))
        stub=SimpleNamespace(deadline_ns=150,
             live=SimpleNamespace(_source=lambda:proofs,
                pending={"source_proofs_sha256":actual_sha}))
        with patch.object(dev.time,"monotonic_ns",side_effect=[100,110]):
            self.assertEqual(dev.Server.current(stub),proofs)
        stub.live.pending["source_proofs_sha256"]="wrong-source-hash"
        with patch.object(dev.time,"monotonic_ns",side_effect=[100,110]):
            with self.assertRaisesRegex(ValueError,"F03_A05_RIGHTS_REVOKED"):
                dev.Server.current(stub)

if __name__=="__main__":unittest.main()
