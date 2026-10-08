
from __future__ import annotations
import importlib.util, json, math, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/m27/research'
POP=ROOT/'pilot/m26/m26-pa-5-frozen-population.json'
HELPER=ROOT/'scripts/m27_stage30j_targeted_guard_rerun.py'
spec=importlib.util.spec_from_file_location('h', HELPER); h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
def case(q):
    return {'case_id':q['question_id'],'question':q['question'],'stratum':q.get('stratum',''),'expected_safe':bool(q.get('abstention_class') or q.get('stratum')=='abstention_no_answer')}
def gates(m):
    need=math.ceil(m['answerable_cases']*.95)
    qflags=('missed_safe_terminal','false_safe_terminal','empty_nonterminal','thin_cited_answer','topic_contamination','semantic_bad_publish')
    okq=m['answerable_cited_final']>=need and m['expected_safe_correct']==m['expected_safe_cases'] and all(m[x]==0 for x in qflags) and m['obligation_satisfied']==m['cases'] and m['no_m26_mature_composer_delegation'] is True
    penalties=max(0,need-m['answerable_cited_final'])*40/max(1,m['answerable_cases'])+max(0,m['expected_safe_cases']-m['expected_safe_correct'])*20/max(1,m['expected_safe_cases'])+sum(m[x] for x in qflags)*5+max(0,m['cases']-m['obligation_satisfied'])*20/max(1,m['cases'])
    if not m['no_m26_mature_composer_delegation']: penalties+=25
    return {'success_rate':round(m['http_success']/m['cases'],4),'success_gate':m['http_success']/m['cases']>=.95,'latency_gate':(m.get('p95_final_latency_ms') or 999999)<15000 and (m.get('p95_first_material_ms') or 999999)<15000,'quality_gate':okq,'quality_score_proxy':round(max(0,100-penalties),3),'quality_score_proxy_boundary':'derived from product-quality harness flags; not independent semantic judge score','answerable_required_for_95pct':need}
def write(rows,decision,start):
    m=h._metrics(rows); g=gates(m); fails=[r for r in rows if r.get('failure_class')]
    OUT.mkdir(parents=True,exist_ok=True)
    payload={'stage':'30N-full200','dataset':'pilot/m26/m26-pa-5-frozen-population.json','dataset_count':200,'decision':decision,'metrics':m,'gates':g,'failure_count':len(fails),'failure_cases':[{'case_id':r.get('case_id'),'failure_class':r.get('failure_class'),'question':r.get('question'),'answer_excerpt':r.get('answer_excerpt','')[:300]} for r in fails],'rows':rows,'start_timestamp':start,'end_timestamp':time.time(),'full523_executed':False}
    (OUT/'95_hotpatch_full200_results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    summary={k:payload[k] for k in ('stage','dataset','dataset_count','decision','metrics','gates','failure_count','failure_cases','start_timestamp','end_timestamp','full523_executed')}
    (OUT/'95_hotpatch_full200_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (OUT/'95_m27_hotpatch_full200_eval_report.md').write_text('# Stage 30N Hotpatch Full Frozen 200 Eval\n\n## Decision\n`%s`\n\n## Gates\n```json\n%s\n```\n\n## Metrics\n```json\n%s\n```\n' % (decision,json.dumps(g,indent=2),json.dumps(m,indent=2)))
def main():
    start=time.time(); doc=json.loads(POP.read_text()); qs=sorted(doc['questions'],key=lambda x:(x.get('stratum',''),x.get('question_id','')))
    rows=[]
    for i,q in enumerate(qs,1):
        r=h._run_case(case(q),targeted=False); rows.append(r); print('FULL200 %d/200 %s safe=%s cited=%s failure=%s latency=%s'%(i,r['case_id'],r['safe_terminal'],r['cited_final'],r['failure_class'],r['latency_ms']),flush=True); write(rows,'RUNNING_FULL200',start)
    m=h._metrics(rows); g=gates(m)
    decision='M27_HOTPATCH_FULL200_PASS' if g['success_gate'] and g['latency_gate'] and g['quality_gate'] else ('M27_HOTPATCH_FULL200_FAIL_SUCCESS_RATE' if not g['success_gate'] else 'M27_HOTPATCH_FULL200_FAIL_LATENCY' if not g['latency_gate'] else 'M27_HOTPATCH_FULL200_FAIL_QUALITY')
    write(rows,decision,start); print('FINAL',decision,json.dumps({'metrics':m,'gates':g},ensure_ascii=False),flush=True); return 0 if decision.endswith('_PASS') else 1
if __name__=='__main__': raise SystemExit(main())
