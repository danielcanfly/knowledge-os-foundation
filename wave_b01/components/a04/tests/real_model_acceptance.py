#!/usr/bin/env python3
"""A04 RETURN real-model-only independent TCP acceptance and adversarial probes."""
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from acceptance import stream,post,verified,kinds,statuses,expect_order,check,new_id,reset_revocations,DATA,EV

MODEL_SHA="74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
OUT=EV/"return_model_cases"
OUT.mkdir(exist_ok=True)
results=[]

def read_model_journal(run_id):
 p=EV/"journals"/(run_id+".jsonl")
 records=[json.loads(x) for x in p.read_text().splitlines()]
 spawn=next(r for r in records if r["kind"]=="provider.spawn")
 check(spawn["provider"]=="local_open_weight_qwen2.5_0.5b_instruct","provider metadata")
 adapter=EV/"model_generation"/("child_"+str(spawn["pid"])+".jsonl")
 check(adapter.is_file(),"missing real OS adapter receipt")
 audits=[json.loads(x) for x in adapter.read_text().splitlines()]
 return {"pid":spawn["pid"],"records":audits,"journal_path":str(adapter)}

def common_model_audit(result,min_calls=1):
 audit=read_model_journal(result["run_id"])
 calls=[x for x in audit["records"] if x["kind"]=="real_model_generation"]
 check(len(calls)>=min_calls,"no authentic local model invocation")
 for a in calls:
  check(a["real_local_llm"] is True and a["exit_code"]==0,"real model process absent")
  check(a["model_sha256"]==MODEL_SHA,"model digest mismatch")
  check(a["max_new_tokens"]==52 and a["duration_ms"]>0,"no hard generation budget")
  check(isinstance(a["llama_cli_pid"],int),"no real inference pid")
  check(a["billable_provider_calls"]==0,"unexpected remote provider")
 return audit,calls

def positive_real_model():
 r=stream("real_local",deadline_ms=60000)
 expect_order(r,min_claims=2)
 claims=verified(r)
 check(len(claims)==2,"exact 2 real claims required")
 check([c["source_id"] for c in claims]==["atlas-A","delta-B"],"source identity")
 audit,calls=common_model_audit(r,min_calls=2)
 check(len(calls)==2,"unexpected real model call count")
 check([a["output"] for a in calls]==[c["text"] for c in claims],"uncorrelated or fake model text")
 check([a["output_sha256"] for a in calls]==[hashlib.sha256(c["text"].encode()).hexdigest() for c in claims],"raw model bytes mismatch")
 r["model_audit"]=audit
 return r

def hallucination_failclosed():
 r=stream("real_local_negative",deadline_ms=60000)
 audit,calls=common_model_audit(r,min_calls=1)
 check(not verified(r),"negative model produced published verified assertion")
 check(statuses(r) in (["refused"],["rejected"]),"negative incorrectly marked succeeded")
 r["model_audit"]=audit
 return r

def tamper_between_real_claims():
 p=DATA/"delta.txt";original=p.read_bytes()
 try:
  def tamper(e,run_id):
   if e["event"]=="claim.verified" and e["source_id"]=="atlas-A":
    p.write_bytes(original+b"\nTAMPERED\n")
  r=stream("real_local",deadline_ms=60000,on_event=tamper)
  check(statuses(r)!=["succeeded"],"tampered model task falsely succeeded")
  check(len(verified(r))<=1,"second tampered source published")
  audit,calls=common_model_audit(r,min_calls=1)
  provider_rejected=any(x.get("reason")=="source_tamper_before_model" for x in audit["records"] if x["kind"]=="real_model_adapter.fail_closed")
  verifier_rejected=any(x.get("reason")=="source_bytes_tampered" for x in r["events"] if x["event"]=="claim.rejected")
  check(provider_rejected or verifier_rejected,"tampered source escaped both provider and verifier")
  r["tamper_detection_stage"]="provider" if provider_rejected else "verification_boundary"
  r["model_audit"]=audit
  return r
 finally:
  p.write_bytes(original)

def source_revocation_model():
 reset_revocations()
 try:
  once=[]
  def revoke(e,run_id):
   if e["event"]=="claim.verified" and not once:
    once.append(True)
    reset_revocations(["atlas-A"])
  r=stream("real_local",deadline_ms=60000,on_event=revoke,ack=False)
  check("claim.retracted" in kinds(r),"source retraction missing")
  check(statuses(r)!=["succeeded"],"revoked real output retained as success")
  audit,calls=common_model_audit(r,min_calls=1)
  r["model_audit"]=audit
  return r
 finally:reset_revocations()

def timed_out_real():
 r=stream("real_local",deadline_ms=70)
 check(statuses(r)==["timeout"],"no deadline terminal")
 check(not verified(r),"deadline emitted late real claim")
 p=EV/"journals"/(r["run_id"]+".jsonl")
 items=[json.loads(x) for x in p.read_text().splitlines()]
 check(any(x["kind"]=="worker.finished" for x in items),"worker did not close on timeout")
 return r

def cancelled_real():
 requests=[]
 def cancel(e,run_id):
  if e["event"]=="claim.verified" and not requests:
   status,_=post("/v1/cancel",{"run_id":run_id})
   requests.append(status)
 r=stream("real_local",deadline_ms=60000,on_event=cancel)
 check(requests==[202],"cancel endpoint failed")
 check(statuses(r)==["cancelled"],"model cancel not terminal")
 check(len(verified(r))==1,"claim leaked after cancel")
 audit,calls=common_model_audit(r,min_calls=1)
 r["model_audit"]=audit
 return r

def cross_tenant_real():
 payload={"run_id":new_id("real_acl"),"tenant":"tenant-alpha",
          "source_ids":["atlas-A","cedar-C"],"mode":"real_local","deadline_ms":60000}
 status,obj=post("/v1/stream",payload)
 check(status==403,"other tenant source admitted")
 return {"response_code":status,"body":obj}

def forged_ack_real():
 r=positive_real_model()
 claim=verified(r)[0]
 status,obj=post("/v1/ack",{"run_id":r["run_id"],"seq":claim["seq"],
                             "proof":"0"*64,"client_received_ns":time.monotonic_ns()})
 check(status==409,"forged Client receipt accepted")
 r["forged_ack"]={"status":status,"body":obj}
 return r

def test(name,fn):
 start=time.monotonic_ns()
 try:
  data=fn()
  passed=True;error=None
 except Exception:
  passed=False;error=traceback.format_exc();data=None
 item={"name":name,"pass":passed,"error":error,"duration_ms":round((time.monotonic_ns()-start)/1e6,3),"data":data}
 p=OUT/(name+".json")
 p.write_text(json.dumps(item,indent=2,ensure_ascii=False)+"\n")
 results.append({"name":name,"pass":passed,"receipt_path":str(p),"error":error})
 print(json.dumps({"test":name,"PASS":passed,"error":error[-160:] if error else ""}),flush=True)

if __name__=="__main__":
 reset_revocations()
 for name,fn in [
  ("two_real_model_generated_claims_preterminal",positive_real_model),
  ("real_model_adversarial_safe_refusal",hallucination_failclosed),
  ("real_model_source_tamper_failclosed",tamper_between_real_claims),
  ("real_model_revocation_and_retraction",source_revocation_model),
  ("real_model_hard_timeout",timed_out_real),
  ("real_model_cancel_cleanup",cancelled_real),
  ("real_model_cross_tenant_denied",cross_tenant_real),
  ("real_model_forged_client_ack_denied",forged_ack_real),
 ]:
  test(name,fn)
 counts={"pass":sum(x["pass"] for x in results),"fail":sum(not x["pass"] for x in results),"total":len(results)}
 output={"counts":counts,"tests":results,"model":"Qwen2.5-0.5B-Instruct Q4_K_M","model_sha256":MODEL_SHA,
         "actual_model_inference":True,"native_q34":False,"client_pid":os.getpid(),"no_external_provider_calls":True}
 (EV/"return_model_test_results.json").write_text(json.dumps(output,indent=2)+"\n")
 print(json.dumps({"SUMMARY":counts}),flush=True)
 sys.exit(0 if counts["fail"]==0 else 1)
