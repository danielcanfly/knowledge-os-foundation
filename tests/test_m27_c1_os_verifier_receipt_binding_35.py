"""Strict evidence binding for separate OS A05 semantic verifier receipts."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as dev
import m27_c1_genuine_native_generation_seam as live

TEXT="Verification is in the Execution & Governance Plane."
SRC="1"*64
CLAIM=live.OBLIGATIONS[0]

class OSVerifierBinding(unittest.TestCase):
    def child(self,**overrides):
        result={"accepted":True,"signed_semantic_issuer":False,
                "claim_id":CLAIM,"source_proof_sha256":SRC,
                "model_text_sha256":dev.digest(TEXT.encode()),
                "pid":os.getpid()+100000,
                "source_excerpt_sha256":"1"*64,
                "citation":"A05 source pin"}
        result.update(overrides)
        class FakeChild:
            pid=os.getpid()+100000
            returncode=0
            def communicate(self,input=None,timeout=None):
                return json.dumps(result),""
        return FakeChild()
    def run_child(self,**overrides):
        with patch.object(dev.subprocess,"Popen",return_value=self.child(**overrides)):
            return dev.real_os_semantic_verify(ROOT,ROOT/"fence",CLAIM,TEXT,SRC)
    def test_exact_digest_and_child_os_identity_accepted(self):
        record=self.run_child()
        self.assertEqual(record["model_text_sha256"],dev.digest(TEXT.encode()))
    def test_mismatched_generated_text_digest_denied(self):
        with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
            self.run_child(model_text_sha256="0"*64)
    def test_missing_generated_text_digest_denied(self):
        with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
            self.run_child(model_text_sha256=None)
    def test_same_pid_does_not_impersonate_independent_os(self):
        with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
            self.run_child(pid=os.getpid())
    def test_spoofed_pid_type_denied(self):
        with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
            self.run_child(pid="child-os-pid")
    def test_wrong_claim_and_source_still_fail_closed(self):
        for override in ({"claim_id":"wrong-claim"},{"source_proof_sha256":"0"*64}):
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
                    self.run_child(**override)

if __name__=="__main__":
    unittest.main()
