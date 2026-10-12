from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge_engine.m27_agent_product_runtime import build_agent_native_product_answer
from knowledge_engine.m27_native_judge_provider import M27NativeJudgeAdapter
from knowledge_engine.m27_semantic_entailment import (
    EntailmentVerdict,
    EvidencePassage,
    MaterialClaim,
    SupportLabel,
)
from knowledge_engine.m27_semantic_publication_gate import verify_publication_claim

OUT = Path(os.environ.get("M27_STAGE30G_OUT", str(ROOT / "docs/m27/research"))); OUT.mkdir(parents=True, exist_ok=True)
rows: list[dict[str, object]] = []
audits: list[dict[str, object]] = []


def record(case_id: str, category: str, passed: bool, detail: str, audit=None):
    rows.append({"case_id": case_id, "category": category, "passed": bool(passed), "detail": detail})
    if audit:
        a = dict(audit)
        a["case_id"] = case_id
        audits.append(a)
    if not passed:
        raise AssertionError(f"{case_id}: {detail}")


def passage(pid: str, text: str, source: str = "source", loc: str | None = None, lang: str = "en"):
    return EvidencePassage(source, loc or f"loc-{pid}", pid, text, lang)


def claim(cid: str, text: str, ids: tuple[str, ...], lang: str = "en"):
    return MaterialClaim(cid, text, 0, len(text), lang, ids)


class VerdictProvider:
    def __init__(self, label, *, verified=True, confidence=.97, refs=None, reason="offline-verdict"):
        self.label = label
        self.verified = verified
        self.confidence = confidence
        self.refs = refs
        self.reason = reason
        self.calls = 0
    def verify(self, c, evidence):
        self.calls += 1
        refs = tuple(self.refs if self.refs is not None else [x.passage_id for x in evidence])
        return EntailmentVerdict(
            self.label, self.verified, refs if self.verified else (),
            "offline-semantic-provider", self.reason, self.confidence, 1, False,
        )


# 1 direct support
e1 = passage("p1", "Kubernetes schedules inference containers onto eligible compute nodes.")
c1 = claim("direct", "Kubernetes schedules inference containers onto eligible compute nodes.", ("p1",))
ok, a = verify_publication_claim(c1, [e1], VerdictProvider(SupportLabel.DIRECT))
record("O01", "direct_support", ok, "direct semantic support accepted", a)

# 2 paraphrase support
c2 = claim("paraphrase", "Kubernetes assigns inference workloads to suitable nodes.", ("p1",))
ok, a = verify_publication_claim(c2, [e1], VerdictProvider(SupportLabel.PARAPHRASE))
record("O02", "paraphrase_support", ok, "provider-verified semantic paraphrase accepted", a)

# 3 cross-language, only because provider verifies
c3 = claim("cross", "Kubernetes 會把推論工作排程到合適的運算節點。", ("p1",), "zh")
ok, a = verify_publication_claim(c3, [e1], VerdictProvider(SupportLabel.PARAPHRASE))
record("O03", "cross_language_support", ok, "cross-language accepted only by semantic provider", a)

# 4 multi-passage cluster
e2 = passage("p2", "Health probes can detect unhealthy application pods.", "source-b")
e3 = passage("p3", "Kubernetes can restart failed pods after health failures.", "source-c")
c4 = claim("cluster", "Kubernetes can detect unhealthy pods through probes and restart failed pods.", ("p2", "p3"))
ok, a = verify_publication_claim(c4, [e2, e3], VerdictProvider(SupportLabel.CLUSTERED, refs=["p2", "p3"]))
record("O04", "cluster_support", ok, "verified two-passage cluster accepted", a)

# 5 cluster cannot masquerade as one passage
c5 = claim("cluster-one", "A compound claim", ("p2",))
ok, a = verify_publication_claim(c5, [e2], VerdictProvider(SupportLabel.CLUSTERED, refs=["p2"]))
record("O05", "cluster_support", not ok and a["fail_closed_reason"] == "cluster_support_requires_multiple_evidence",
       "single-reference cluster rejected", a)

# 6 topical-only
ok, a = verify_publication_claim(c1, [e1], VerdictProvider(SupportLabel.UNSUPPORTED, verified=False, confidence=.98, refs=[]))
record("O06", "topical_only", not ok, "topical-only evidence rejected", a)

# 7 unsupported
unsupported = claim("unsupported", "Kubernetes guarantees zero downtime.", ("p1",))
ok, a = verify_publication_claim(unsupported, [e1], VerdictProvider(SupportLabel.UNSUPPORTED, verified=False, refs=[]))
record("O07", "unsupported", not ok, "unsupported factual extension rejected", a)

# 8 contradicted
contradicted = claim("contradicted", "Kubernetes never restarts failed pods.", ("p3",))
ok, a = verify_publication_claim(contradicted, [e3], VerdictProvider(SupportLabel.CONTRADICTED, verified=False, refs=[]))
record("O08", "contradicted", not ok, "contradicted claim rejected", a)

# 9 citation existence without semantic provider
ok, a = verify_publication_claim(c1, [e1], None)
record("O09", "citation_without_support", not ok, "citation existence is not semantic support", a)

# 10 low confidence
ok, a = verify_publication_claim(c1, [e1], VerdictProvider(SupportLabel.DIRECT, confidence=.4))
record("O10", "low_confidence", ok, "interface provider can be pre-calibrated; adapter threshold tested separately", a)

# 11 adapter low confidence fail closed
payload_low = {"support_class":"DIRECT_SUPPORT","confidence":.4,"reason":"weak","evidence_references":["p1"]}
adapter = M27NativeJudgeAdapter(lambda c,e: payload_low)
ok, a = verify_publication_claim(c1, [e1], adapter)
record("O11", "low_confidence_adapter", not ok and a["confidence"] == .4, "adapter threshold rejects low confidence", a)

# 12 schema invalid twice -> exactly one retry, no lowercase normalization
calls = {"n": 0}
def bad_schema(c,e):
    calls["n"] += 1
    return {"support_class":"direct_support","confidence":.99,"reason":"wrong enum case","evidence_references":["p1"]}
ok, a = verify_publication_claim(c1, [e1], M27NativeJudgeAdapter(bad_schema))
record("O12", "schema_invalid_after_retry",
       not ok and calls["n"] == 2 and a["schema_retry_used"] and a["fail_closed_reason"] == "schema_invalid_after_retry",
       "invalid enum remains invalid after one retry", a)

# 13 schema retry succeeds exactly once
calls = {"n": 0}
def retry_schema(c,e):
    calls["n"] += 1
    if calls["n"] == 1:
        return {"support_class":"direct_support","confidence":.99,"reason":"invalid first","evidence_references":["p1"]}
    return {"support_class":"DIRECT_SUPPORT","confidence":.96,"reason":"fresh strict schema","evidence_references":["p1"]}
ok, a = verify_publication_claim(c1, [e1], M27NativeJudgeAdapter(retry_schema))
record("O13", "schema_retry", ok and calls["n"] == 2 and a["schema_retry_used"], "one fresh schema retry accepted", a)

# 14 provider unavailable is not schema retried
calls = {"n": 0}
def unavailable(c,e):
    calls["n"] += 1
    raise RuntimeError("provider offline")
ok, a = verify_publication_claim(c1, [e1], M27NativeJudgeAdapter(unavailable))
record("O14", "provider_unavailable",
       not ok and calls["n"] == 1 and a["fail_closed_reason"] == "provider_unavailable",
       "provider unavailable fails closed without schema retry", a)

# 15 hallucinated evidence reference fails schema and retry
calls = {"n": 0}
def bad_ref(c,e):
    calls["n"] += 1
    return {"support_class":"DIRECT_SUPPORT","confidence":.99,"reason":"bad ref","evidence_references":["fake"]}
ok, a = verify_publication_claim(c1, [e1], M27NativeJudgeAdapter(bad_ref))
record("O15", "invalid_evidence_reference", not ok and calls["n"] == 2,
       "hallucinated evidence id rejected after bounded retry", a)

# 16 explicit Kubernetes/x402/hotel contamination rejected
contam_e = passage("contam", "Kubernetes, x402 payment rails, and hotel loyalty programs are all technology topics.")
contam_c = claim("contam", "Kubernetes uses x402 hotel payments to schedule GPU inference.", ("contam",))
ok, a = verify_publication_claim(contam_c, [contam_e], VerdictProvider(SupportLabel.UNSUPPORTED, verified=False, refs=[]))
record("O16", "topic_contamination", not ok, "Kubernetes/x402/hotel contamination rejected", a)

# 17 thin cited answer rejected by runtime despite positive verdict
short_text = "MCP stands for Model Context Protocol and standardizes tool interfaces."
runtime_evidence = [{
    "passage_text": short_text, "section_id":"mcp", "source_id":"mcp-doc",
    "artifact_key":"knowledge/mcp", "evidence_id":"mcp-1",
}]
r = build_agent_native_product_answer(
    question="What does MCP stand for in this blog?", intent_class="factual",
    evidence=runtime_evidence, semantic_provider=VerdictProvider(SupportLabel.DIRECT),
)
record("O17", "thin_cited_answer",
       not r.publishable and "PRODUCT_THIN_SURFACE" in r.gap_taxonomy,
       "thin cited surface rejected")

# 18 runtime positive path proves provider is actually in publication path
long1 = ("Kubernetes schedules inference containers across eligible compute nodes and uses scheduler "
         "constraints and resource requests to place workloads. Operators can combine health probes "
         "with controllers so failed application pods are noticed and restarted. These mechanisms "
         "support reliable inference service operation while remaining dependent on explicit cluster "
         "configuration and workload policy rather than promising automatic zero downtime.")
long2 = ("For production inference, Kubernetes controllers track desired replica state and reconcile "
         "workloads when pods fail. Resource limits, node labels, tolerations, and scheduling policy "
         "shape where model-serving containers can run. Health checks and autoscaling components add "
         "operational control, while observability is still required to understand saturation, errors, "
         "latency, and capacity across the serving fleet.")
ev = [
    {"passage_text":long1,"section_id":"k1","source_id":"s1","artifact_key":"k8s/a","evidence_id":"e1"},
    {"passage_text":long2,"section_id":"k2","source_id":"s2","artifact_key":"k8s/b","evidence_id":"e2"},
]
prov = VerdictProvider(SupportLabel.DIRECT)
r = build_agent_native_product_answer(
    question="How does Kubernetes help AI infrastructure?", intent_class="factual",
    evidence=ev, semantic_provider=prov,
)
record("O18", "runtime_publication_path",
       r.publishable and prov.calls >= 2 and bool(r.answer.get("semantic_verification_receipts")),
       "publication requires semantic provider verdicts")
for receipt in r.answer.get("semantic_verification_receipts", []):
    x = dict(receipt); x["case_id"] = "O18"; audits.append(x)

# 19 forbidden composer delegation static guard
source = (ROOT/"src/knowledge_engine/m27_agent_product_runtime.py").read_text()
forbidden = ("synthesize_and_verify", "_synthesize_and_verify", "run_owner_arbitrary_query")
record("O19", "no_m26_composer_delegation", not any(x in source for x in forbidden),
       "M27 runtime contains no forbidden mature composer delegation")

# 20 receipts sanitized
serialized = json.dumps(audits, ensure_ascii=False)
record("O20", "sanitized_receipts",
       "MINIMAX_API_KEY" not in serialized and "owner_bypass" not in serialized and "secret" not in serialized,
       "verification receipts contain no raw secret or protected owner material")

with (OUT/"87_m27_semantic_publication_gate_eval_cases.csv").open("w", newline="", encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=["case_id","category","passed","detail"])
    w.writeheader(); w.writerows(rows)

fields=["case_id","claim_id","evidence_ids","supporting_evidence_ids","support_class","provider_status",
        "confidence","verified","publication_accepted","provider_attempt_count","schema_retry_used","fail_closed_reason"]
with (OUT/"87_m27_semantic_publication_gate_claim_audit.csv").open("w", newline="", encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for a in audits:
        row=dict(a)
        row["evidence_ids"]="|".join(row.get("evidence_ids") or [])
        row["supporting_evidence_ids"]="|".join(row.get("supporting_evidence_ids") or [])
        w.writerow(row)

receipt={
    "stage":"30G",
    "offline_integration_gate_pass": all(bool(r["passed"]) for r in rows),
    "case_count":len(rows),
    "passed":sum(bool(r["passed"]) for r in rows),
    "failed":sum(not bool(r["passed"]) for r in rows),
    "categories":[r["category"] for r in rows],
    "schema_retry_limit":1,
    "literal_overlap_is_semantic_support":False,
    "citation_existence_is_semantic_support":False,
    "thin_cited_answer_can_publish":False,
    "m26_mature_composer_delegation":False,
}
(OUT/"m27_stage30g_offline_integration_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt,sort_keys=True))
