"""Non-billable strict C1 DEV adapter contracts; never impersonates Provider."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import unittest
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

if __name__=="__main__":unittest.main()
