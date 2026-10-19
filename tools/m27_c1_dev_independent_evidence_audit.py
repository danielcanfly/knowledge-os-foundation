"""Independent after-the-fact raw MiniMax-M3/A05/Unix Client audit.

Does not sign an external Product claim or turn a dev result into release PASS.
Consumes genuine raw provider delta bytes from the owner-private 0600 journal,
actual separate OS Client HTTP ACK receipts, and exact current A05 source bytes.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sys,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/knowledge_engine"))
import m27_g01_current_native_consumer as g01
import m27_c1_genuine_native_generation_seam as c1live
import m27_f03_source_rights_admission as f03

def sha(b):return hashlib.sha256(b).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def demand(x,msg):
    if not x:raise ValueError(msg)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True)
    p.add_argument("--repo",required=True)
    args=p.parse_args()
    evidence=Path(args.evidence).resolve(strict=True)
    repo=Path(args.repo).resolve(strict=True)
    run=json.loads((evidence/"C1_REAL_MINIMAX_DEV_RUN_RESULT.json").read_text())
    client=json.loads((evidence/"C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json").read_text())
    journal=[json.loads(x) for x in
      (evidence/"C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl").read_text().splitlines()]
    entries=client["receipts"]
    rid=run["source_prepared"]["request_id"]
    task_sha=run["source_prepared"]["task_contract_sha256"]
    proof_sha=run["source_prepared"]["source_proof_sha256"]
    demand(run["actual_real_provider_call_count"]==1,"NOT_ONE_ACTUAL_NEW_MODEL_CALL")
    demand(run["real_provider_done_observed"] is True,"ACTUAL_PROVIDER_DONE_NOT_OBSERVED")
    demand(run["local_native_ack_count"]==2 and run["client_process_exit"]==0,
           "NOT_TWO_PHYSICAL_NATIVE_ACKS")
    demand(run["formal_product_pass"] is False,"INVALID_FORMAL_PRODUCT_CLAIM")
    kinds=[x["event"] for x in entries]
    demand(kinds==["request_start","answer_text","answer_text","terminal"],
           "INDEPENDENT_NATIVE_RECEIPT_ORDER_DENIED")
    demand(all(x["request_id"]==rid for x in entries),
           "INDEPENDENT_CLIENT_TASK_REQUEST_DIFFERENT")
    answers=entries[1:3]
    demand([a.get("ack_http_status") for a in answers]==[200,200] and
           [a.get("ack_receipt") for a in answers]==
            ["SOURCE_VERIFIED_DEV_NATIVE_ACK"]*2,
           "NATIVE_ACK_DENIED")
    demand(answers[0]["observed_before_provider_done"] is True,
           "SUBSTANTIVE_FIRST_MODEL_TEXT_NOT_PRETERMINAL")
    os_pids=[run["parent_native_server_pid"],client["client_pid"]]+[
        a.get("source_verifier_os_pid") for a in answers]
    demand(all(type(pid) is int and pid>0 for pid in os_pids) and
           len(set(os_pids))==len(os_pids),
           "REAL_OS_SERVER_CLIENT_AND_SEMANTIC_READER_NOT_DISTINCT")
    demand(all(a["citation_count"]==1 for a in answers) and
           entries[-1]["citation_count"]==2 and
           entries[-1].get("full_cited_final") is True and
           entries[-1]["scope_product_pass"] is False,
           "CITED_FINAL_OR_DEV_PRODUCT_STATUS_MISMATCH")
    starts=[x for x in journal if x["event"]=="actual_provider_started"]
    ids=[x for x in journal if x["event"]=="real_provider_identity"]
    heads=[x for x in journal if x["event"]=="provider_response_headers"]
    done=[x for x in journal if x["event"]=="actual_provider_done"]
    end_seen=[x for x in journal if x["event"]=="actual_provider_done_observed"]
    deltas=[x for x in journal if x["event"]=="actual_provider_raw_delta"]
    native=[x for x in journal if x["event"]=="native_delivery_answer_text"]
    acknowledged=[x for x in journal if x["event"]=="native_client_local_ack"]
    demand(len(starts)==len(ids)==len(heads)==len(done)==len(end_seen)==1,
           "PROVIDER_IDENTITY_START_DONE_NOT_UNIQUE")
    demand(ids[0]["model"]=="MiniMax-M3" and heads[0]["status"]==200,
           "REAL_MINIMAX_MODEL_HTTP_IDENTITY_MISMATCH")
    demand(len(deltas)>0 and len(deltas)<=350 and
           [d["sequence"] for d in deltas]==list(range(1,len(deltas)+1)),
           "RAW_PROVIDER_DELTA_SEQUENCE_GAP_OR_REPLAY")
    demand(all(type(d.get("text")) is str and d["text"] and
               sha(d["text"].encode())==d["sha256"] for d in deltas),
           "RAW_PROVIDER_BYTES_SHA_DRIFT")
    raw="".join(d["text"] for d in deltas)
    lines=[v.strip() for v in raw.splitlines() if v.strip()]
    demand(len(lines)==2,"RAW_REAL_PROVIDER_NOT_EXACTLY_TWO_SENTENCES")
    demand(all(a.get("model_text_sha256")==sha(text.encode())
               for a,text in zip(answers,lines)),
           "PUBLISHED_MODEL_CLAIM_NOT_RAW_PROVIDER_SUBSTRING")
    demand(sha(" ".join(lines).encode())==entries[-1].get("answer_sha256"),
           "FINAL_CITED_ANSWER_NOT_REAL_MODEL")
    demand(len(native)==len(acknowledged)==2,"PHYSICAL_DELIVERY_ACK_COUNT_DRIFT")
    demand(native[0]["at_ns"]<acknowledged[0]["at_ns"]<
           end_seen[0]["at_ns"] and
           native[1]["at_ns"]<acknowledged[1]["at_ns"]<
           done[0]["at_ns"],
           "C1_VERIFIED_FIRST_CLIENT_DELIVERY_NOT_PRE_PROVIDER_DONE")
    demand(done[0]["first_client_ack_before_done"] is True,
           "MODEL_CLIENT_TIMING_NOT_VERIFIED")
    demand(entries[-1]["at_ns"]>answers[0]["at_ns"],
           "CLIENT_FINAL_BEFORE_MODEL_ANSWER")
    with tempfile.TemporaryDirectory(prefix="c1-independent-replay-") as td:
        fence=Path(td)/"fence.json"
        fence.write_text(json.dumps({"release_id":f03.A05_RELEASE_ID,
                                     "minimum_epoch":1}))
        fence.chmod(0o600)
        consumer=g01.Consumer(repo=repo,fence=fence,
                 journal=Path(td)/"source.jsonl")
        proofs=consumer._source()
    demand(sha(canon(proofs))==proof_sha,"F03_A05_REAL_CURRENT_SOURCE_PROOF_DRIFT")
    demand(len(proofs)==2 and
           [proof["obligation_id"] for proof in proofs]==list(c1live.OBLIGATIONS) and
           f03.A05_SOURCE_PIN==
             run["source_prepared"]["source_manifest_sha256"],
           "A05_SOURCE_RELEASE_OR_OBLIGATION_DRIFT")
    for claim,p in zip(answers,proofs):
        demand(claim["citation"]==p["citation"],
               "C1_ORIGIN_CITATION_NOT_CURRENT_F03_A05_BYTES")
    demand(entries[-1]["citations"]==
           {p["obligation_id"]:p["citation"] for p in proofs},
           "C1_FINAL_CITATIONS_NOT_F03_REAL_SOURCE")
    s0=acknowledged[0]["at_ns"]
    d0=end_seen[0]["at_ns"]
    result={
      "verdict":"C1_FIRSTPARTY_DEV_REAL_MINIMAX_A05_UNIX_E2E_SCOPED_PASS",
      "formal_C1_product_qualified":False,
      "source_scope":"OWNER_FIRSTPARTY_A05_NONPROD_OS_LOCAL_ONLY",
      "real_model":"MiniMax-M3",
      "new_genuine_model_calls":1,
      "actual_raw_delta_events":len(deltas),
      "raw_provider_concat_sha256":sha(raw.encode()),
      "same_one_fresh_task_request_id":rid,
      "same_fresh_task_contract_sha256":task_sha,
      "source_proof_sha256":proof_sha,
      "source_manifest_sha256":f03.A05_SOURCE_PIN,
      "origin_document_count":11,
      "origin_citation_span_count":21,
      "verified_new_model_substantive_client_claims":2,
      "actual_local_native_client_http_200_acks":2,
      "first_model_text_received_before_provider_done":True,
      "first_client_ack_before_actual_provider_done_observed":True,
      "first_client_ack_lead_to_provider_done_observed_ms":round((d0-s0)/1e6,3),
      "fully_generated_cited_final_sha256":entries[-1]["answer_sha256"],
      "fully_generated_cited_final_source_count":2,
      "actual_model_usage":"NOT_OBSERVED",
      "real_provider_billed_cost":"UNKNOWN",
      "cache":"OFF",
      "f04_h01_h03_production_approval":False,
      "independent_signed_semantic_issuer_receipts":0,
      "independent_external_client_idp_signed_receipts":0,
      "signed_full_product_status":"HOLD",
      "independent_audit_pid":os.getpid(),
      "raw_journal_sha256":sha((evidence/"C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl").read_bytes()),
      "client_receipt_sha256":sha((evidence/"C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json").read_bytes())}
    out=evidence/"C1_INDEPENDENT_RAW_PROVIDER_A05_CLIENT_REPLAY_AUDIT.json"
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    os.chmod(out,0o600)
    print(json.dumps({"verdict":result["verdict"],
      "model_calls":1,"first_client_ack_lead_ms":
         result["first_client_ack_lead_to_provider_done_observed_ms"],
      "client_acks":2,"source_cited_answer":True,
      "formal_product_pass":False,"audit_file":str(out)}))
if __name__=="__main__":main()
