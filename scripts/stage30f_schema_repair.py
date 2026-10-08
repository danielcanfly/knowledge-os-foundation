from pathlib import Path
import csv,json,subprocess
w=Path("/home/ubuntu/LLM_Wiki-m27-semantic-entailment-30f")
d=w/"docs/m27/research"
raw=json.loads((d/"m27_stage30f_raw_judge_outputs.json").read_text())
cases={r["case_id"]:r for r in csv.DictReader((d/"86_m27_semantic_entailment_calibration_cases.csv").open())}
allowed={"DIRECT_SUPPORT","PARAPHRASE_SUPPORT","CLUSTER_SUPPORT","TOPICAL_ONLY","UNSUPPORTED","CONTRADICTED","INSUFFICIENT_PROVIDER_CAPABILITY"}
def valid(x):
 return isinstance(x,dict) and set(x)=={"support_class","confidence","reason","evidence_references"} and x["support_class"] in allowed and type(x["confidence"]) in (int,float) and 0<=x["confidence"]<=1 and isinstance(x["reason"],str) and bool(x["reason"].strip()) and isinstance(x["evidence_references"],list) and all(p=="p1" for p in x["evidence_references"])
invalid=[r for r in raw if not valid(r.get("verdict"))]
print("INVALID",len(invalid),flush=True)
judge='''import json,sys,os
from decimal import Decimal
from knowledge_engine.m26_pa5_v8_live import MiniMaxClient
client=MiniMaxClient(os.environ.get("MINIMAX_API_KEY",""),max_calls=8,max_cost=Decimal("2"))
system="Strict NLI classification ONLY. Return a JSON object with exactly support_class, confidence, reason, evidence_references. support_class MUST be an exact UPPERCASE enum: DIRECT_SUPPORT, PARAPHRASE_SUPPORT, CLUSTER_SUPPORT, TOPICAL_ONLY, UNSUPPORTED, CONTRADICTED, INSUFFICIENT_PROVIDER_CAPABILITY. Lowercase enum values are forbidden. Do not generate any answers. Contradiction, topical overlap, citation-only and cross-topic contamination must be rejected. confidence numeric 0-1, reason nonempty string, evidence_references [p1] if supported else []. JSON only."
for line in sys.stdin:
 r=json.loads(line)
 try:
  payload={"model":"MiniMax-M3","max_tokens":320,"temperature":0,"stream":False,"system":system,"messages":[{"role":"user","content":json.dumps({"claim":r["claim"],"evidence":[{"id":"p1","text":r["evidence_text"]}],"language":r["language"]},ensure_ascii=False)}]}
  ans=client.call(payload,"aq_claim_semantic_entailment")
  print(json.dumps({"case_id":r["case_id"],"verdict":json.loads(ans["text"].strip()),"latency_ms":ans["latency_ms"]}),flush=True)
 except Exception as e: print(json.dumps({"case_id":r["case_id"],"error":type(e).__name__}),flush=True)
'''
with subprocess.Popen(["docker","exec","-i","m27-owner-canary-28","python","-c",judge],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True) as p:
 out,_=p.communicate("".join(json.dumps(cases[x["case_id"]],ensure_ascii=False)+"\n" for x in invalid),timeout=180)
retry=[json.loads(line) for line in out.splitlines()]
replaced={x["case_id"]:x for x in retry if valid(x.get("verdict"))}
final=[replaced.get(x["case_id"],x) for x in raw]
(d/"m27_stage30f_schema_retry_audit.json").write_text(json.dumps({"initial_invalid":len(invalid),"raw_retry":retry,"accepted":list(replaced),"policy":"one_generic_schema_retry;no_normalization"},indent=2,ensure_ascii=False))
results=[]
for item in final:
 r=cases[item["case_id"]];v=item.get("verdict");ok=valid(v)
 support=ok and v["support_class"] in {"DIRECT_SUPPORT","PARAPHRASE_SUPPORT","CLUSTER_SUPPORT"} and v["confidence"]>=.85 and bool(v["evidence_references"])
 results.append({"case_id":item["case_id"],"expected_support_class":r["expected_support_class"],"expected_binary_supported":r["expected_binary_supported"],"predicted_support_class":v.get("support_class","") if isinstance(v,dict) else "","predicted_binary_supported":str(bool(support)).lower(),"confidence":v.get("confidence","") if isinstance(v,dict) else "","schema_valid":str(ok).lower(),"latency_ms":item.get("latency_ms",""),"error":item.get("error","")})
with (d/"86_m27_semantic_entailment_calibration_results.csv").open("w",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
cats={}
for kind in sorted(set(x["expected_support_class"] for x in results)):
 items=[x for x in results if x["expected_support_class"]==kind];supported=sum(x["predicted_binary_supported"]=="true" for x in items)
 cats[kind]={"count":len(items),"supported":supported,"support_rate":round(supported/len(items),4),"schema_valid":sum(x["schema_valid"]=="true" for x in items)}
fp=sum(x["predicted_binary_supported"]=="true" for x in results if x["expected_support_class"] in {"TOPICAL_ONLY","UNSUPPORTED","CONTRADICTED","THIN_CITED_NEGATIVE"})
bad=sum(x["schema_valid"]!="true" for x in results)
decision=("M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_SCHEMA" if bad else "M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_FALSE_POSITIVE" if fp else "M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_RECALL" if any(cats[k]["support_rate"]<v for k,v in {"DIRECT_SUPPORT":.9,"PARAPHRASE_SUPPORT":.7,"CROSS_LANGUAGE_SUPPORT":.6,"CLUSTER_SUPPORT":.6}.items()) else "M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_PASS")
receipt=json.loads((d/"m27_semantic_entailment_provider_selection_receipts.json").read_text())
receipt.update(final_decision=decision,schema_invalid=bad,false_positives=fp,by_category=cats,initial_schema_invalid=len(invalid),schema_retries_accepted=len(replaced),calibration_method="47 original provider responses + generic bounded schema-invalid retry",integrated=False,candidate_rebuilt=False)
(d/"m27_semantic_entailment_provider_selection_receipts.json").write_text(json.dumps(receipt,indent=2))
print("DECISION",decision,"SCHEMA_INVALID",bad,"FP",fp,"RETRIES_ACCEPTED",len(replaced),flush=True)
