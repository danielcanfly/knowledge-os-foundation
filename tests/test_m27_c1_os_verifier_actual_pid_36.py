"""Verify that a semantic receipt's PID is the actual launched OS child PID.

The previous reader accepted any positive nonparent PID printed by the
verifier. These tests require checking the PID supplied independently by
the local operating system subprocess API, not trusting JSON alone.
No Provider requests, no privileged operations.
"""
import json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as dev
import m27_c1_genuine_native_generation_seam as live

CLAIM=live.OBLIGATIONS[0]
TEXT="Verification is in the Execution & Governance Plane."
SOURCE="1"*64

class Child:
    def __init__(self,reported_pid=None,actual_pid=None,returncode=0):
        self.pid=actual_pid or os.getpid()+4012
        self.returncode=returncode
        receipt={"accepted":True,"signed_semantic_issuer":False,
                 "claim_id":CLAIM,"source_proof_sha256":SOURCE,
                 "model_text_sha256":dev.digest(TEXT.encode()),
                 "pid":reported_pid if reported_pid is not None else self.pid,
                 "source_excerpt_sha256":"2"*64,"citation":"A05 source pin"}
        self.stdout=json.dumps(receipt)
        self.stderr=""
        self.killed=False
    def communicate(self,input=None,timeout=None):
        return self.stdout,self.stderr
    def kill(self):self.killed=True
    def wait(self):return self.returncode

class OSChildIdentity(unittest.TestCase):
    def invoke(self,child):
        # Before this repair, the code uses run(), which doesn't expose the
        # OS-verified pid. Simulate successful but forged JSON from that path.
        old=subprocess.CompletedProcess([],0,child.stdout,child.stderr)
        with patch.object(dev.subprocess,"run",return_value=old),\
             patch.object(dev.subprocess,"Popen",return_value=child):
            return dev.real_os_semantic_verify(ROOT,ROOT/"fence",CLAIM,TEXT,SOURCE)
    def test_exact_os_child_pid_is_accepted(self):
        c=Child()
        self.assertEqual(self.invoke(c)["pid"],c.pid)
    def test_different_positive_pid_is_not_os_verified(self):
        c=Child(reported_pid=os.getpid()+88888)
        with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
            self.invoke(c)
    def test_same_parent_pid_does_not_count_as_child(self):
        c=Child(reported_pid=os.getpid())
        with self.assertRaisesRegex(ValueError,"LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED"):
            self.invoke(c)
    def test_nonzero_real_child_exit_cannot_admit_signed_proof(self):
        c=Child(returncode=13)
        with self.assertRaisesRegex(ValueError,"SEPARATE_OS_SEMANTIC_SOURCE_VERIFIER_DENIED"):
            self.invoke(c)
    def test_timed_out_real_child_is_killed_and_denied(self):
        c=Child()
        previous_communicate=c.communicate
        attempts=[0]
        def communicate(input=None,timeout=None):
            attempts[0]+=1
            if attempts[0]==1:
                raise subprocess.TimeoutExpired(cmd=["verifier"],timeout=timeout)
            return previous_communicate(input=input,timeout=timeout)
        c.communicate=communicate
        with self.assertRaisesRegex(ValueError,"SEPARATE_OS_SEMANTIC_SOURCE_VERIFIER_TIMEOUT"):
            self.invoke(c)
        self.assertTrue(c.killed)
        self.assertEqual(attempts[0],2)

if __name__=="__main__":unittest.main()
