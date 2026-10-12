import collections
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

w=Path("/home/ubuntu/LLM_Wiki-m27-semantic-entailment-30f")
path=w/"docs/m27/research/86_m27_semantic_entailment_calibration_cases.csv"
cases=list(csv.DictReader(path.open()))
judge=r'''
import sys,json,os
from decimal import Decimal
from knowledge_engine.m26_pa5_v8_live import MiniMaxClient
try:
 client=MiniMaxClient(os.environ.get("MINIMAX_API_KEY",""),max_calls=85,max_cost=Decimal("8"))
except Exception as exc:
 print(json.dumps({"fatal":"provider_configuration_unavailable"}),flush=True); sys.exit(3)
prompt="""You are an independent strict semantic NLI verifier. Do not generate answers. Assess whether every element of the claim is ENTAILED by the supplied evidence. Do not infer unsupported details. Reject broad generalizations, contradictions, mere topical overlap, misleading citations, and cross-topic (Kubernetes, x402, hotel) mixtures. Translate Chinese/English faithfully. Evidence passages separated by || jointly support a claim only if all parts are explicitly established. Respond ONLY one JSON object with EXACTLY keys support_class, confidence, reason, evidence_references. support_class must be DIRECT_SUPPORT, PARAPHRASE_SUPPORT, CLUSTER_SUPPORT, TOPICAL_ONLY, UNSUPPORTED, CONTRADICTED, or INSUFFICIENT_PROVIDER_CAPABILITY. confidence is a real number between 0 and 1. reason max 500 characters. evidence_references is ["p1"] if entailed, otherwise []. Never cite evidence for an unsupported case; when uncertain choose UNSUPPORTED."""
for line in sys.stdin:
 try:
  row=json.loads(line)
  payload={"model":"MiniMax-M3","max_tokens":400,"temperature":0,"stream":False,"system":prompt,"messages":[{"role":"user","content":json.dumps({"claim":row["claim"],"evidence":[{"id":"p1","text":row["evidence_text"]}],"language":row["language"]},ensure_ascii=False)}]}
  result=client.call(payload,"aq_claim_semantic_entailment")
  value=result["text"].strip()
  if value.startswith(chr(96)*3): value=value.split("\n",1)[-1].rsplit(chr(96)*3,1)[0].strip()
  print(json.dumps({"case_id":row["case_id"],"verdict":json.loads(value),"latency_ms":result["latency_ms"]}),flush=True)
 except Exception as exc:
  print(json.dumps({"case_id":row.get("case_id","?"),"error":type(exc).__name__}),flush=True)
'''
cmd=["docker","exec","-i","m27-owner-canary-28","python","-c",judge]
with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1) as p:
 payload="".join(json.dumps(row,ensure_ascii=False)+"\n" for row in cases)
 out,_=p.communicate(payload,timeout=780)
outrows=[]
for line in out.splitlines():
 try: outrows.append(json.loads(line))
 except: pass
(w/"docs/m27/research/m27_stage30f_raw_judge_outputs.json").write_text(json.dumps(outrows,ensure_ascii=False,indent=2))
# importing adapter without installed repo path; use source-based schema checks in isolated PYTHONPATH
import os
from importlib.util import module_from_spec, spec_from_file_location

sys.path.insert(0,str(w/"src"))
def parse_verdict(raw,allowed):
 if isinstance(raw,str): raw=json.loads(raw)
 if not isinstance(raw,dict) or set(raw)!={"support_class","confidence","reason","evidence_references"}: raise ValueError("schema_keys")
 k=raw["support_class"]; c=raw["confidence"]; refs=raw["evidence_references"]; reason=raw["reason"]
 kinds={"DIRECT_SUPPORT","PARAPHRASE_SUPPORT","CLUSTER_SUPPORT","TOPICAL_ONLY","UNSUPPORTED","THIN_CITED_NEGATIVE","CONTRADICTED","INSUFFICIENT_PROVIDER_CAPABILITY"}
 if k not in kinds or type(c) not in (int,float) or not 0<=c<=1 or not isinstance(reason,str) or not reason.strip() or len(reason)>500 or not isinstance(refs,list) or len(refs)!=len(set(refs)) or any(x not in allowed for x in refs): raise ValueError("schema_fields")
 return raw
byid={r["case_id"]:r for r in outrows}
results=[]
positive={"DIRECT_SUPPORT","PARAPHRASE_SUPPORT","CROSS_LANGUAGE_SUPPORT","CLUSTER_SUPPORT"}
negative={"TOPICAL_ONLY","UNSUPPORTED","CONTRADICTED","THIN_CITED_NEGATIVE"}
for row in cases:
 v=byid.get(row["case_id"],{})
 raw=v.get("verdict")
 try:
  x=parse_verdict(raw,["p1"])
  supported=x["support_class"] in {"DIRECT_SUPPORT","PARAPHRASE_SUPPORT","CLUSTER_SUPPORT"} and x["confidence"]>=0.85 and bool(x["evidence_references"])
  schema_ok=True
 except Exception:
  supported=False;schema_ok=False
 results.append(dict(case_id=row["case_id"],expected_support_class=row["expected_support_class"],expected_binary_supported=row["expected_binary_supported"],predicted_support_class=raw.get("support_class","") if isinstance(raw,dict) else "",predicted_binary_supported=str(supported).lower(),confidence=raw.get("confidence","") if isinstance(raw,dict) else "",schema_valid=str(schema_ok).lower(),latency_ms=v.get("latency_ms",""),error=v.get("error","")))
with (w/"docs/m27/research/86_m27_semantic_entailment_calibration_results.csv").open("w",newline="") as f:
 outcsv=csv.DictWriter(f,fieldnames=list(results[0]));outcsv.writeheader();outcsv.writerows(results)
cats={}
for k in sorted(set(x["expected_support_class"] for x in cases)):
 subset=[r for r in results if r["expected_support_class"]==k]
 cats[k]={"count":len(subset),"supported":sum(r["predicted_binary_supported"]=="true" for r in subset),"schema_valid":sum(r["schema_valid"]=="true" for r in subset)}
 cats[k]["support_rate"]=round(cats[k]["supported"]/cats[k]["count"],4)
false_positive=sum(x["predicted_binary_supported"]=="true" for x in results if x["expected_support_class"] in negative)
schema_invalid=sum(x["schema_valid"]=="false" for x in results)
error_count=sum(bool(x["error"]) for x in results)
gate=(len(outrows)==len(cases) and not false_positive and not schema_invalid and cats["DIRECT_SUPPORT"]["support_rate"]>=.9 and cats["PARAPHRASE_SUPPORT"]["support_rate"]>=.7 and cats["CROSS_LANGUAGE_SUPPORT"]["support_rate"]>=.6 and cats["CLUSTER_SUPPORT"]["support_rate"]>=.6)
if len(outrows)!=len(cases): decision="M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_BLOCKED_BY_RUNTIME"
elif schema_invalid: decision="M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_SCHEMA"
elif false_positive: decision="M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_FALSE_POSITIVE"
elif any(cats[k]["support_rate"]<v for k,v in {"DIRECT_SUPPORT":.9,"PARAPHRASE_SUPPORT":.7,"CROSS_LANGUAGE_SUPPORT":.6,"CLUSTER_SUPPORT":.6}.items()): decision="M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_RECALL"
else: decision="M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_PASS"
receipt={"final_decision":decision,"calibration_count":len(cases),"result_count":len(outrows),"provider":"MiniMax-M3 via existing generic client, narrow NLI only","by_category":cats,"false_positives":false_positive,"schema_invalid":schema_invalid,"provider_errors":error_count,"integrated":False,"candidate_rebuilt":False,"owner_only_route_certification":"pending"}
(d:=w/"docs/m27/research").joinpath("m27_semantic_entailment_provider_selection_receipts.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False))
print(json.dumps(receipt,ensure_ascii=False),flush=True)