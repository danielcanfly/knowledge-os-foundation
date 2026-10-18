"""Offline H02 receipt intake positive and adversarial negative tests."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SRC=Path(__file__).resolve().parents[1]
MASTER=SRC.parents[3]
G01_SOURCE=SRC.parent/"G01_GENUINE_QA_20261018"
EVID=MASTER/"02_REPORTS/PARALLEL_VNEXT_20261014/REPLAN_EK_20261017"
G01_EVID=EVID/"G01_GENUINE_QA_NONPROD_EVIDENCE_20261018"
F01_EVID=EVID/"F01_17_NEW_REAL_DIAGNOSTIC_EVIDENCE_20261018"
RUN=G01_EVID/"G01_REAL_A05_ATTEMPT_01"
spec=importlib.util.spec_from_file_location("intake",SRC/"tools/m27_h02_g01_evidence_intake.py")
intake=importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)

class AdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=json.loads((G01_EVID/"G01_RAW_EVIDENCE_INDEX_V2.json").read_bytes())
        cls.pre=json.loads((RUN/"G01_FROZEN_PRECASE.json").read_bytes())
        cls.wire=[json.loads(x) for x in (RUN/"server_vm_wire.jsonl").read_text().splitlines() if x]
        cls.client=json.loads((RUN/"independent_client_receipts.json").read_bytes())
        cls.native=(SRC/"src/knowledge_engine/m27_h02_native_nonprod_consumer.py").read_text()
        cls.doc=(SRC/"docs/m27/h02_native_nonprod_consumer_abi.md").read_text()
        cls.f01=json.loads((F01_EVID/"f01_17_raw_model_receipts_manifest.json").read_bytes())

    def test_all_physical_files_and_source_rights(self):
        self.assertEqual(intake.verify_index(self.index,G01_EVID,G01_SOURCE),[21,8])
        self.assertTrue(intake.verify_task(self.pre,SRC))
    def test_original_generated_claims_and_two_client_acks(self):
        self.assertTrue(intake.verify_wire(self.wire,self.client))
    def test_h02_source_only_and_f01_no_online_model(self):
        self.assertTrue(intake.verify_native_boundary(self.native,self.doc,self.f01))
    def test_full_offline_verdict_with_formal_hold(self):
        x=intake.audit(G01_EVID,G01_SOURCE,SRC,F01_EVID)
        self.assertEqual(x["verdict"],"SCOPED_EVIDENCE_ACCEPTED")
        self.assertEqual(x["formal"],"FORMAL_H02_PRODUCT_HOLD")
        self.assertEqual(x["new_provider_calls"],0)
    def deny(self,method,*args):
        with self.assertRaises(intake.Refused):
            method(*args)
    def test_denies_incomplete_inventory(self):
        x=copy.deepcopy(self.index)
        x["receipts"].pop()
        self.deny(intake.verify_index,x,G01_EVID,G01_SOURCE)
    def test_denies_inventory_sha_mismatch(self):
        x=copy.deepcopy(self.index)
        x["receipts"][0]["sha256"]="0"*64
        self.deny(intake.verify_index,x,G01_EVID,G01_SOURCE)
    def test_denies_parent_traversal(self):
        x=copy.deepcopy(self.index)
        x["receipts"][0]["path"]="../secret"
        self.deny(intake.verify_index,x,G01_EVID,G01_SOURCE)
    def test_denies_forged_cloudflare_primary(self):
        x=copy.deepcopy(self.pre)
        x["provider_route"]="CLOUDFLARE_PRIMARY"
        self.deny(intake.verify_task,x,SRC)
    def test_denies_new_source_rights(self):
        x=copy.deepcopy(self.pre)
        x["source_bindings"][0]["rights"]="PRODUCT_SIGNED"
        self.deny(intake.verify_task,x,SRC)
    def test_denies_missing_answer_obligation(self):
        x=copy.deepcopy(self.pre)
        x["obligations"].pop()
        self.deny(intake.verify_task,x,SRC)
    def test_denies_client_ack_after_terminal(self):
        x=copy.deepcopy(self.client)
        x["receipts"][1]["ack_monotonic_ns"]=x["receipts"][-1]["received_monotonic_ns"]+1
        self.deny(intake.verify_wire,self.wire,x)
    def test_denies_unverified_claim(self):
        x=copy.deepcopy(self.client)
        x["receipts"][1]["body"]["verified"]=False
        self.deny(intake.verify_wire,self.wire,x)
    def test_denies_mutated_model_text(self):
        x=copy.deepcopy(self.client)
        x["receipts"][1]["body"]["text"]="fake answer"
        self.deny(intake.verify_wire,self.wire,x)
    def test_denies_missing_provider_delta(self):
        x=copy.deepcopy(self.wire)
        x=[r for r in x if not (r["event"]=="vm_wire" and r["provider_event"]["event"]=="delta" and r["provider_event"]["chunk_index"]==4)]
        self.deny(intake.verify_wire,x,self.client)
    def test_denies_publish_before_verify(self):
        x=copy.deepcopy(self.wire)
        vi=next(i for i,v in enumerate(x) if v["event"]=="verify")
        pi=next(i for i,v in enumerate(x) if v["event"]=="publish_answer_text")
        x[vi],x[pi]=x[pi],x[vi]
        self.deny(intake.verify_wire,x,self.client)
    def test_denies_missing_second_ack(self):
        x=copy.deepcopy(self.wire)
        i=[i for i,v in enumerate(x) if v["event"]=="ack"][-1]
        x.pop(i)
        self.deny(intake.verify_wire,x,self.client)
    def test_denies_model_stream_in_native(self):
        self.deny(intake.verify_native_boundary,self.native+"\npublish_answer_text",self.doc,self.f01)
    def test_denies_f01_false_issuer(self):
        x=copy.deepcopy(self.f01)
        x["provider_calls"]=17
        self.deny(intake.verify_native_boundary,self.native,self.doc,x)
    def test_denies_f01_forged_raw_receipt(self):
        x=copy.deepcopy(self.f01)
        x["provider_raw_receipts"]=[{"fake":True}]
        self.deny(intake.verify_native_boundary,self.native,self.doc,x)

if __name__=="__main__":
    unittest.main()
