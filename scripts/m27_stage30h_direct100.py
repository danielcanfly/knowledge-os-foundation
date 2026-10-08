from __future__ import annotations
import ast,csv,hashlib,json,math,statistics,sys,time
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/m27/research"
URL="http://127.0.0.1:18080/v1/answers/stream"
SOURCE=ROOT/"pilot/m26/m26-pa-5-frozen-population.json"
TARGET=ROOT/"scripts/m27_stage30g_direct20.py"
source=TARGET.read_text()
tree=ast.parse(source)
selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("parse_sse","post","p95")]
namespace={"__name__":"m27_stage30h_helpers","__file__":str(TARGET)}
import urllib.request,urllib.error
namespace.update({"URL":URL,"json":json,"time":time,"urllib":urllib})
exec(compile(ast.Module(body=selected,type_ignores=[]),str(TARGET),"exec"),namespace)
post=namespace["post"]; p95=namespace["p95"]
population=json.loads(SOURCE.read_text())
assert len(population["questions"])==200
groups=defaultdict(list)
for q in population["questions"]:groups[q["stratum"]].append(q)
# Deterministic proportional stratified half sample, sorted by stable question_id.
cases=[]
for stratum,group in sorted(groups.items()):
    ordered=sorted(group,key=lambda q:q["question_id"])
    cases.extend(ordered[::2])
cases=sorted(cases,key=lambda q:(q["stratum"],q["question_id"]))[:100]
assert len(cases)==100 and len({q["question_id"] for q in cases})==100
assert URL=="http://127.0.0.1:18080/v1/answers/stream"
case_rows=[{"case_id":q["question_id"],"question":q["question"],"stratum":q["stratum"],"abstention_class":q.get("abstention_class") or "", "expected_safe":bool(q.get("abstention_class") or q["stratum"]=="abstention_no_answer"),"question_digest":q["question_digest"],"source_path":(q.get("construction_source_identity") or {}).get("source_path",""),"source_artifact_sha256":(q.get("construction_source_identity") or {}).get("artifact_sha256","")} for q in cases]
OUT.mkdir(parents=True,exist_ok=True)
def write_csv(path,rows):
    keys=list(rows[0]) if rows else ["case_id"]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction="ignore");w.writeheader();w.writerows(rows)
write_csv(OUT/"88_m27_direct_candidate_100_scale_eval_cases.csv",case_rows)
report_path=OUT/"88_m27_direct_candidate_100_scale_eval_report.md"
receipt_path=OUT/"m27_direct_candidate_100_scale_eval_receipts.json"
start=time.time()
rows=[]
for i,c in enumerate(case_rows,1):
    x=post(c["question"],timeout=75)
    answer=x.get("answer_excerpt","").lower()
    query=c["question"].lower()
    # Conservative risk flags only. Do not treat absence of keyword collision as semantic proof.
    topics=("kubernetes","x402","hotel")
    contam=any(word in answer and word not in query for word in topics)
    row={**c,**x,"topic_contamination":contam,"topic_contamination_heuristic_only":True}
    row["false_safe_terminal"]=bool(row.get("safe_terminal") and not row["expected_safe"])
    row["missed_safe_terminal"]=bool(row["expected_safe"] and not row.get("safe_terminal"))
    row["empty_nonterminal"]=bool(row.get("http_status")==200 and not row.get("safe_terminal") and not row.get("answer_len"))
    row["semantic_bad_publish"]=bool(not row.get("safe_terminal") and row.get("answer_len") and not row.get("semantic_gate_ok"))
    # Citation metadata is insufficient to independently certify semantic truth; keep explicit boundary.
    row["semantic_truth_independently_adjudicated"]=False
    rows.append(row)
    print(f"{i}/100 {c['case_id']} HTTP={row.get('http_status')} cited={row.get('cited_final')} safe={row.get('safe_terminal')} latency={row.get('latency_ms')}",flush=True)
    receipt_path.write_text(json.dumps({"stage":"30H","target_url":URL,"dataset":str(SOURCE.relative_to(ROOT)),"dataset_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),"image":"knowledge-engine:m27-semantic-publication-gate-30g-67ca9928","start_timestamp":start,"updated_timestamp":time.time(),"completed":len(rows),"rows":rows},ensure_ascii=False,indent=2)+"\n")
end=time.time()
http=sum(r.get("http_status")==200 and r.get("ok") for r in rows)
answerable=[r for r in rows if not r["expected_safe"]]
safe=[r for r in rows if r["expected_safe"]]
lat=[r["latency_ms"] for r in rows if r.get("http_status")==200 and r.get("latency_ms") is not None]
first=[r["first_material_ms"] for r in rows if r.get("http_status")==200 and r.get("first_material_ms") is not None]
metrics={"cases":len(rows),"http_success":http,"answerable_cases":len(answerable),"answerable_cited_final":sum(bool(r.get("cited_final")) for r in answerable),"expected_safe_cases":len(safe),"expected_safe_correct":sum(bool(r.get("safe_terminal")) for r in safe),"false_safe_terminal":sum(r["false_safe_terminal"] for r in rows),"missed_safe_terminal":sum(r["missed_safe_terminal"] for r in rows),"empty_nonterminal":sum(r["empty_nonterminal"] for r in rows),"thin_cited_answer":sum(bool(r.get("thin_cited_answer")) for r in rows),"topic_contamination_heuristic":sum(r["topic_contamination"] for r in rows),"semantic_bad_publish":sum(r["semantic_bad_publish"] for r in rows),"p95_final_ms":p95(lat),"p95_first_material_ms":p95(first)}
sourcecode=(ROOT/"src/knowledge_engine/m27_agent_product_runtime.py").read_text()
no_m26=not any(t in sourcecode for t in ("run_owner_arbitrary_query","synthesize_and_verify","_synthesize_and_verify"))
quality=metrics["answerable_cited_final"]>=math.ceil(.95*len(answerable)) and metrics["expected_safe_correct"]==len(safe) and all(metrics[k]==0 for k in ("false_safe_terminal","missed_safe_terminal","empty_nonterminal","thin_cited_answer","topic_contamination_heuristic","semantic_bad_publish")) and no_m26
latency=metrics["p95_final_ms"] is not None and metrics["p95_first_material_ms"] is not None and metrics["p95_final_ms"]<15000 and metrics["p95_first_material_ms"]<15000 and len(first)==len(rows)
decision=("M27_DIRECT_CANDIDATE_100_SCALE_EVAL_FAIL_SUCCESS_RATE" if http<98 else "M27_DIRECT_CANDIDATE_100_SCALE_EVAL_FAIL_PRODUCT_QUALITY" if not quality else "M27_DIRECT_CANDIDATE_100_SCALE_EVAL_FAIL_LATENCY" if not latency else "M27_DIRECT_CANDIDATE_100_SCALE_EVAL_BLOCKED_BY_HARNESS")
# Even if all machine checks pass, the harness cannot call this PASS without independent semantic adjudication.
write_csv(OUT/"88_m27_direct_candidate_100_scale_eval_failures.csv",[{"case_id":r["case_id"],"reason":",".join(k for k in ("false_safe_terminal","missed_safe_terminal","empty_nonterminal","thin_cited_answer","topic_contamination","semantic_bad_publish") if r.get(k)) or ("HTTP" if r.get("http_status")!=200 else "NOT_CITED" if not r.get("cited_final") and not r["expected_safe"] else "FLAGGED"),"excerpt":r.get("answer_excerpt","")[:250]} for r in rows if r.get("http_status")!=200 or (not r["expected_safe"] and not r.get("cited_final")) or any(r.get(k) for k in ("false_safe_terminal","missed_safe_terminal","empty_nonterminal","thin_cited_answer","topic_contamination","semantic_bad_publish"))] or [{"case_id":"none","reason":"none","excerpt":""}])
receipt=json.loads(receipt_path.read_text());receipt.update(end_timestamp=end,metrics=metrics,decision=decision,no_m26_mature_composer_delegation=no_m26,semantic_quality_boundary="Runtime receipts checked; independent human semantic truth adjudication not performed; machine flags are conservative heuristics")
receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
report_path.write_text("# Stage 30H Direct Candidate 100-case Scale Evaluation\n\n## Final decision\n\x60"+decision+"\x60\n\n## Scope and provenance\n- Direct-candidate only: \x60"+URL+"\x60\n- Source: \x60"+str(SOURCE.relative_to(ROOT))+"\x60 (200-case frozen M26 population; deterministic every-second-question by sorted question_id per stratum)\n- Source SHA256: \x60"+hashlib.sha256(SOURCE.read_bytes()).hexdigest()+"\x60\n- The source references an earlier accepted local release and may not exactly match the current M27 indexed corpus. This is a transfer diagnostic, not an M26 admission run.\n- No owner route, Nginx or production path requested.\n- Image: \x60knowledge-engine:m27-semantic-publication-gate-30g-67ca9928\x60\n- Code commit: \x6067ca9928b54feb7cd81083313f845c264c565b37\x60\n- Start/end unix seconds: "+str(start)+" / "+str(end)+"\n\n## Metrics\n\x60\x60\x60json\n"+json.dumps(metrics,indent=2)+"\n\x60\x60\x60\n\n## Verification boundary\n- Receipt-backed semantic publication checks are verified by the M27 provider. This script cannot independently judge all answer/topic correctness; keyword contamination is a risk detector, not semantic proof. If all numeric gates are green, decision remains BLOCKED_BY_HARNESS pending independent quality adjudication.\n- No M26 mature composer delegation: "+str(no_m26)+"\n- Owner-only route certification remains pending and must not be inferred from this result.\n")
(ROOT/"docs/m27/handoffs/M27_DIRECT_CANDIDATE_100_SCALE_EVAL_HANDOFF.md").write_text("# Stage 30H handoff\n\nDecision: \x60"+decision+"\x60\n\nDirect-only 100-case run completed against 127.0.0.1:18080. See docs/m27/research/88_m27_direct_candidate_100_scale_eval_report.md and receipts. No full523 or production changes.\n")
print("FINAL",decision,json.dumps(metrics),flush=True)
