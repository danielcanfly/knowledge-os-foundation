from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "scripts")
import m27_test_page_compare_19r as h

OUT=Path("docs/m27/research")
OUT.mkdir(parents=True,exist_ok=True)
URL="http://127.0.0.1:18080/v1/answers/stream"
rows=[]
for c in h.CASES:
    x=h.post(URL,c["question"],{},timeout=60)
    answer=x.pop("answer_text","")
    x.pop("event_names",None)
    x.update(case_id=c["case_id"],slice=c["slice"],question=c["question"],answer_excerpt=answer[:1100])
    x["suspected_thin"] = bool(x.get("cited_answer") and (len(answer)<180 or "Evidence 1 says:" in answer or "the strongest grounded answer is" in answer))
    x["empty_nonterminal"] = bool(x.get("ok") and not answer and not x.get("safe_terminal"))
    x["false_safe_terminal"] = bool(x.get("safe_terminal") and c["slice"] != "safe_terminal")
    rows.append(x)
    print(c["case_id"],x.get("http_status"),x.get("latency_ms"),x.get("cited_answer"),x["suspected_thin"],flush=True)
names=["case_id","slice","question","ok","http_status","latency_ms","ttfb_ms","first_material_ms","cited_answer","citation_count","answer_len","safe_terminal","terminal_reason","final_status","suspected_thin","empty_nonterminal","false_safe_terminal","answer_excerpt","error_class","error_code"]
with (OUT/"81_m27_direct_candidate_batch_eval_cases.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=names,extrasaction="ignore");w.writeheader();w.writerows(rows)
answerable=[r for r in rows if r["slice"]!="safe_terminal"]
citations=sum(bool(r.get("cited_answer")) for r in answerable)
metrics=h.metric(rows)
metrics.update(answerable_cases=len(answerable),answerable_cited_rate=round(100*citations/len(answerable),2),thin_suspected_count=sum(r["suspected_thin"] for r in rows),empty_nonterminal_count=sum(r["empty_nonterminal"] for r in rows),false_safe_terminal_count=sum(r["false_safe_terminal"] for r in rows),safe_terminal_cases=sum(bool(r.get("safe_terminal")) for r in rows))
failure=any(not r.get("ok") or r.get("http_status")!=200 for r in rows)
if failure: state="M27_DIRECT_CANDIDATE_BATCH_EVAL_FAIL_SUCCESS_RATE"
elif metrics["p95_final_latency_ms"] is not None and metrics["p95_final_latency_ms"]>=15000:state="M27_DIRECT_CANDIDATE_BATCH_EVAL_FAIL_LATENCY"
elif metrics["answerable_cited_rate"]<95:state="M27_DIRECT_CANDIDATE_BATCH_EVAL_FAIL_SUCCESS_RATE"
elif metrics["thin_suspected_count"] or metrics["false_safe_terminal_count"] or metrics["empty_nonterminal_count"]:state="M27_DIRECT_CANDIDATE_BATCH_EVAL_FAIL_PRODUCT_QUALITY"
else:state="M27_DIRECT_CANDIDATE_BATCH_EVAL_BLOCKED_BY_HARNESS"
receipt={"stage":"30A","url":URL,"set_size":len(rows),"metrics":metrics,"state":state,"owner_rubric":"unavailable; heuristic flags are not owner scores","rows":rows}
(OUT/"m27_direct_candidate_batch_eval_receipts.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
print("FINAL",state,json.dumps(metrics,ensure_ascii=False),flush=True)
