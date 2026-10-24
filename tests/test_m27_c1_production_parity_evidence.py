"""Strict production-parity validator SECURITY tests with MOCK FILES ONLY.

No fixture, mock, test signature or historical run grants a real E2E PASS.
"""
import copy,hashlib,json,os,stat,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_production_parity_verifier as v
import m27_c1_genuine_native_generation_seam as formal

HEAD="a"*40;TREE="b"*40;TASK="c"*64;SOURCE="d"*64;RID="e"*48
TEXTS=("Verification is in the Execution & Governance Plane.",
       "PolicyEngine decides deterministic enforcement.")
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def ticket(**attrs):return {"at_ns":123456,**attrs}

def fixture():
    run={"current_source_head":HEAD,"current_source_tree":TREE,
      "source_clean_at_e2e_execution":True,
      "parent_native_server_pid":99,"source_prepared":{
        "prepared_source_count":2,"source_byte_verified_local":True,
        "task_contract_sha256":TASK,"source_proof_sha256":SOURCE,
        "request_id":RID},
      "provider_mode":"m26-parity-direct","actual_real_provider_call_count":1,
      "real_provider_done_observed":True,"client_process_exit":0,
      "local_native_ack_count":2,"formal_product_pass":False}
    receipts=[
      {"event":"request_start","request_id":RID},
      {"event":"answer_text","request_id":RID,"task_sha256":TASK,
       "ack_http_status":200,"citation_count":1,"source_verifier_os_pid":202,
       "observed_before_provider_done":True,"model_text_sha256":h(TEXTS[0])},
      {"event":"answer_text","request_id":RID,"task_sha256":TASK,
       "ack_http_status":200,"citation_count":1,"source_verifier_os_pid":203,
       "observed_before_provider_done":False,"model_text_sha256":h(TEXTS[1])},
      {"event":"terminal","request_id":RID,"full_cited_final":True,
       "citation_count":2,"real_model_calls":1,"scope_product_pass":False,
       "answer_sha256":h(" ".join(TEXTS)),
       "citations":{v.CLAIMS[0]:"A05_doc_00",v.CLAIMS[1]:"A05_doc_01"}}]
    c={"client_pid":201,"receipts":receipts}
    journal=[
      ticket(event="actual_provider_started",at_ns=1,request_id=RID,provider=v.CLOUDFLARE),
      ticket(event="provider_response_headers",at_ns=2,status=200,provider=v.CLOUDFLARE),
      ticket(event="real_provider_identity",at_ns=3,model=v.CLOUDFLARE),
      ticket(event="actual_provider_raw_delta",at_ns=4,sequence=1,text=TEXTS[0]+"\n",
             sha256=h(TEXTS[0]+"\n")),
      ticket(event="native_delivery_answer_text",at_ns=5,request_id=RID,
             text_sha256=h(TEXTS[0]),source_cited=True),
      ticket(event="native_client_local_ack",at_ns=6,request_id=RID,
             claim_id=v.CLAIMS[0],text_sha256=h(TEXTS[0])),
      ticket(event="actual_provider_raw_delta",at_ns=7,sequence=2,
             text=TEXTS[1],sha256=h(TEXTS[1])),
      ticket(event="native_delivery_answer_text",at_ns=8,request_id=RID,
             text_sha256=h(TEXTS[1]),source_cited=True),
      ticket(event="native_client_local_ack",at_ns=9,request_id=RID,
             claim_id=v.CLAIMS[1],text_sha256=h(TEXTS[1])),
      ticket(event="actual_provider_done",at_ns=10,delta_count=2,
             first_client_ack_before_done=True)]
    # Synthetic fixture must include the NEW A06/A07 dual-endpoint nonce
    # custody. These are MOCK values, never eligible Product evidence.
    for i,claim in enumerate(v.CLAIMS):
        nonce=str(i+1)*40
        vals={"request_id":RID,"claim_id":claim,"challenge":nonce,
              "text_sha256":h(TEXTS[i])}
        body=json.dumps(vals).encode()
        meta={"challenge_sha256":h(nonce),
              "ack_binding_sha256":h("|".join((
                  RID,TASK,claim,nonce,h(TEXTS[i])))),
              "ack_request_body_sha256":hashlib.sha256(body).hexdigest()}
        receipts[i+1].update({"claim_id":claim,**meta})
        journal[4+i*3].update({"task_sha256":TASK,"claim_id":claim,
             "challenge_sha256":meta["challenge_sha256"],
             "ack_binding_sha256":meta["ack_binding_sha256"]})
        journal[5+i*3].update({"task_sha256":TASK,**meta})
    return run,c,journal

class ParityEvidenceRejectsForgedOutcomes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="c1-synthetic-parity-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.run,self.client,self.events=fixture()
    def write(self):
        payloads={
          "C1_REAL_MINIMAX_DEV_RUN_RESULT.json":
              json.dumps(self.run),
          "C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json":
              json.dumps(self.client),
          "C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl":
              "\n".join(json.dumps(ev) for ev in self.events)+"\n",
          "C1_REAL_TASK_JOURNAL.jsonl":json.dumps({
              "event":"real_a05_source_and_task_prepared_NOT_PROVIDER",
              "request_id":RID,"task_sha256":TASK,
              "source_proof_sha256":SOURCE,
              "provider_called":False,"product_qualified":False})+"\n"}
        for name,data in payloads.items():
            p=self.path/name
            p.write_text(data);p.chmod(0o600)
    def check(self):
        self.write()
        return v.evaluate(self.path,head=HEAD,tree=TREE,real_run=True,
                          allow_synthetic=True)
    def test_01_synthetic_reference_only_tests_logic_not_real_provider(self):
        a=self.check()
        self.assertEqual(a["status"],"TEST_ONLY_SYNTHETIC_EVIDENCE_STRUCTURE_PASS")
        self.assertEqual(a["model"],v.CLOUDFLARE)
        self.assertEqual(a["real_delta_count"],2)
        self.assertTrue(a["first_ack_preterminal"])
        self.assertFalse(a["formal_independently_signed_product_pass"])
        self.assertFalse(a["production_release_qualified"])
        with self.assertRaisesRegex(v.Rejected,"ONLY_ACTIVE_REAL_OS_SERVER"):
            v.evaluate(self.path,head=HEAD,tree=TREE)
    def test_02_reject_version_and_dirty_evidence(self):
        self.run["current_source_head"]="f"*40
        with self.assertRaisesRegex(v.Rejected,"SOURCE_HEAD_TREE"):
            self.check()
        self.run["current_source_head"]=HEAD
        self.run["source_clean_at_e2e_execution"]=False
        with self.assertRaisesRegex(v.Rejected,"SOURCE_HEAD_TREE"):
            self.check()
    def test_03_reject_second_task_receipt(self):
        self.client["receipts"][2]["request_id"]="z"*48
        with self.assertRaisesRegex(v.Rejected,"CLIENT_ACK_INCOMPLETE|CROSS_TASK"):
            self.check()
    def test_04_reject_progress_without_live_model(self):
        self.events=[ev for ev in self.events
                     if ev.get("event")!="actual_provider_raw_delta"]
        with self.assertRaisesRegex(v.Rejected,"JOURNAL"):
            self.check()
    def test_05_reject_forged_ack_sha(self):
        self.client["receipts"][1]["model_text_sha256"]="f"*64
        with self.assertRaisesRegex(v.Rejected,"MODEL_TEXT_CLIENT_PROOF"):
            self.check()
    def test_06_reject_delayed_first_ack(self):
        self.events[5]["at_ns"]=30
        with self.assertRaisesRegex(v.Rejected,"NOT_PRETERMINAL"):
            self.check()
    def test_07_reject_wrong_model_even_having_two_acks(self):
        self.events[0]["provider"]="MiniMax-M3"
        with self.assertRaisesRegex(v.Rejected,"CLOUDFLARE_STREAM"):
            self.check()
    def test_08_reject_hallucinated_or_substituted_model_delta(self):
        self.events[6]["text"]="Agent decides everything."
        self.events[6]["sha256"]=h(self.events[6]["text"])
        with self.assertRaisesRegex(v.Rejected,"MODEL_TEXT_NOT_IN_RAW_DELTAS"):
            self.check()
    def test_09_reject_error_on_same_task(self):
        self.events.append(ticket(event="live_dev_fail_closed",at_ns=11,reason="bad"))
        with self.assertRaisesRegex(v.Rejected,"ERROR_OR_PARTIAL"):
            self.check()
    def test_10_reject_nonowner_evidence_permissions(self):
        self.write()
        (self.path/"C1_REAL_MINIMAX_DEV_RUN_RESULT.json").chmod(0o644)
        with self.assertRaisesRegex(v.Rejected,"OWNER_PRIVATE_FILE"):
            v.evaluate(self.path,head=HEAD,tree=TREE,
                       allow_synthetic=True)
    def test_11_mock_opt_in_cannot_be_used_as_formal_e2e(self):
        self.write()
        with self.assertRaisesRegex(v.Rejected,"FIXTURE_NOT_ELIGIBLE"):
            v.evaluate(self.path,head=HEAD,tree=TREE,real_run=False,
                       allow_synthetic=True)
        self.assertIsNone(formal.TRUST_ROOT_MANIFEST_SHA256)
    def test_12_reject_independent_signoff_pretend(self):
        self.run["formal_product_pass"]=True
        with self.assertRaisesRegex(v.Rejected,"AUTHENTIC_CLOUDFLARE"):
            self.check()
    def test_13_source_journal_is_bound_to_same_task(self):
        self.write()
        source=self.path/"C1_REAL_TASK_JOURNAL.jsonl"
        item=json.loads(source.read_text())
        item["task_sha256"]="0"*64
        source.write_text(json.dumps(item)+"\n")
        with self.assertRaisesRegex(v.Rejected,"SOURCE_TASK_JOURNAL_MISMATCH"):
            v.evaluate(self.path,head=HEAD,tree=TREE)
    def test_14_legacy_ack_without_nonce_hash_must_not_promote(self):
        del self.client["receipts"][1]["challenge_sha256"]
        with self.assertRaisesRegex(v.Rejected,"ACK_CHALLENGE_BINDING_CUSTODY"):
            self.check()
    def test_15_forged_client_ack_http_body_digest_must_not_promote(self):
        self.client["receipts"][1]["ack_request_body_sha256"]="f"*64
        with self.assertRaisesRegex(v.Rejected,"ACK_CHALLENGE_BINDING_CUSTODY"):
            self.check()
    def test_16_server_claim_nonce_binding_must_match_both_client_and_frame(self):
        self.events[5]["ack_binding_sha256"]="0"*64
        with self.assertRaisesRegex(v.Rejected,"ACK_CHALLENGE_BINDING_CUSTODY"):
            self.check()
        self.events[5]["ack_binding_sha256"]=fixture()[2][5]["ack_binding_sha256"]
        self.events[4]["challenge_sha256"]="0"*64
        with self.assertRaisesRegex(v.Rejected,"ACK_CHALLENGE_BINDING_CUSTODY"):
            self.check()
    def test_17_reused_challenge_even_with_consistent_fake_hashes_denied(self):
        ch=self.client["receipts"][1]["challenge_sha256"]
        self.client["receipts"][2]["challenge_sha256"]=ch
        self.events[7]["challenge_sha256"]=ch
        self.events[8]["challenge_sha256"]=ch
        with self.assertRaisesRegex(v.Rejected,"REUSED_ACK_CHALLENGE"):
            self.check()
    def test_18_server_ack_wrong_task_custody_must_not_promote(self):
        self.events[5]["task_sha256"]="f"*64
        with self.assertRaisesRegex(v.Rejected,"ACK_BINDING_TASK_OR_CLAIM"):
            self.check()
if __name__=="__main__":unittest.main()
