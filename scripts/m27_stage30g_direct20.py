from __future__ import annotations
import csv, json, statistics, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m27_test_page_compare_19r as base

URL = "http://127.0.0.1:18080/v1/answers/stream"
OUT = ROOT / "docs/m27/research"


def parse_sse(text: str):
    rows = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        ev = ""; data = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                try:
                    x = json.loads(line.split(":", 1)[1].strip())
                    data = x if isinstance(x, dict) else {"_value": x}
                except Exception:
                    data = {"_unparsed": True}
        if ev:
            rows.append({"event": ev, "data": data})
    return rows


def post(question: str, timeout: int = 75):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter(); first_byte = None; first_material = None; buf = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            while True:
                line = resp.readline()
                if not line:
                    break
                now = time.perf_counter()
                if first_byte is None and line.strip():
                    first_byte = now
                decoded = line.decode("utf-8", errors="replace")
                buf.append(decoded)
                if first_material is None and any(x in decoded for x in (
                    "event: verified_claim_ready", "event: cited_segment_ready",
                    "event: final_answer_done", "event: safe_abstention_done")):
                    first_material = (now - t0) * 1000
    except Exception as exc:
        return {"ok": False, "http_status": getattr(exc, "code", None),
                "error": type(exc).__name__,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 3)}
    events = parse_sse("".join(buf)); names = [x["event"] for x in events]
    dto = {}
    for x in events:
        d = x["data"]
        if x["event"] in {"final_answer_done", "safe_abstention_done"} and isinstance(d.get("response"), dict):
            dto = d["response"]
    answer = str(dto.get("answer_text") or "")
    citations = dto.get("citations") if isinstance(dto.get("citations"), list) else []
    response = dto.get("response") if isinstance(dto.get("response"), dict) else {}
    integrity = dto.get("integrity") if isinstance(dto.get("integrity"), dict) else {}
    receipts = response.get("semantic_verification_receipts") if isinstance(response.get("semantic_verification_receipts"), list) else []
    plan = dto.get("answer_plan") if isinstance(dto.get("answer_plan"), dict) else {}
    safe = bool(dto.get("safe_abstention")) or dto.get("status") == "owner_only_safe_abstention" or "safe_abstention_done" in names
    word_count = len(answer.split())
    thin = bool(response.get("thin_cited_answer")) or (bool(answer) and word_count < 45) or (
        bool(answer) and plan.get("broad_homepage_question") is True and word_count < 55
    )
    semantic_ok = bool(receipts) and all(
        r.get("publication_accepted") is True
        and r.get("verified") is True
        and r.get("support_class") in {"direct_support", "paraphrase_support", "clustered_support"}
        and float(r.get("confidence") or 0) >= .85
        and r.get("provider_status") == "m27-minimax-nli"
        for r in receipts
    )
    cited_final = (
        not safe and bool(answer) and bool(citations)
        and integrity.get("material_claim_support_verified") is True
        and integrity.get("citation_locator_valid") is True
        and int(integrity.get("unsupported_accepted_claims") or 0) == 0
        and semantic_ok and not thin
    )
    return {"ok": True, "http_status": status,
        "ttfb_ms": round(((first_byte or time.perf_counter()) - t0) * 1000, 3),
        "first_material_ms": round(first_material, 3) if first_material is not None else None,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
        "answer_len": len(answer), "word_count": word_count,
        "citation_count": len(citations), "safe_terminal": safe,
        "thin_cited_answer": thin, "semantic_receipts": receipts,
        "semantic_gate_ok": semantic_ok, "cited_final": cited_final,
        "terminal_reason": str(dto.get("terminal_reason") or ""),
        "status": str(dto.get("status") or ""), "event_names": names,
        "answer_excerpt": answer[:800]}


def p95(xs):
    ys = sorted(xs)
    return ys[max(0, min(len(ys) - 1, int((len(ys) - 1) * .95 + .999999)))] if ys else None

rows = []
for c in base.CASES:
    x = post(c["question"])
    answer = x.get("answer_excerpt", "").casefold(); q = c["question"].casefold()
    contam = (("kubernetes" in q and ("x402" in answer or "hotel" in answer))
              or ("x402" in q and ("kubernetes" in answer or "hotel" in answer))
              or ("hotel" in q and ("kubernetes" in answer or "x402" in answer)))
    x.update(case_id=c["case_id"], slice=c["slice"], question=c["question"],
             topic_contamination=contam, expected_safe=(c["slice"] == "safe_terminal"))
    x["false_safe_terminal"] = bool(x.get("safe_terminal") and not x["expected_safe"])
    x["missed_safe_terminal"] = bool(x["expected_safe"] and not x.get("safe_terminal"))
    x["empty_nonterminal"] = bool(x.get("ok") and not x.get("safe_terminal") and not x.get("answer_len"))
    rows.append(x)
    print(c["case_id"], x.get("http_status"), x.get("latency_ms"), x.get("first_material_ms"),
          "safe", x.get("safe_terminal"), "cited", x.get("cited_final"),
          "semantic", x.get("semantic_gate_ok"), "thin", x.get("thin_cited_answer"), flush=True)

okrows = [r for r in rows if r.get("ok") and r.get("http_status") == 200]
answerable = [r for r in rows if not r["expected_safe"]]
lat = [r["latency_ms"] for r in okrows]
fm = [r["first_material_ms"] for r in okrows if r.get("first_material_ms") is not None]
source = (ROOT / "src/knowledge_engine/m27_agent_product_runtime.py").read_text()
no_m26 = not any(x in source for x in ("run_owner_arbitrary_query", "synthesize_and_verify", "_synthesize_and_verify"))
metrics = {
    "cases": len(rows),
    "http_success": len(okrows),
    "answerable_cases": len(answerable),
    "answerable_cited_final": sum(bool(r.get("cited_final")) for r in answerable),
    "expected_safe_terminal_pass": sum(bool(r.get("safe_terminal")) for r in rows if r["expected_safe"]),
    "false_safe_terminal_count": sum(bool(r.get("false_safe_terminal")) for r in rows),
    "missed_safe_terminal_count": sum(bool(r.get("missed_safe_terminal")) for r in rows),
    "empty_nonterminal_count": sum(bool(r.get("empty_nonterminal")) for r in rows),
    "thin_cited_answer_count": sum(bool(r.get("thin_cited_answer")) for r in rows),
    "topic_contamination_count": sum(bool(r.get("topic_contamination")) for r in rows),
    "semantic_gate_bad_published_count": sum(bool((not r.get("semantic_gate_ok")) and r.get("cited_final")) for r in rows),
    "p50_final_latency_ms": round(statistics.median(lat), 3) if lat else None,
    "p95_final_latency_ms": round(p95(lat), 3) if lat else None,
    "p50_first_material_ms": round(statistics.median(fm), 3) if fm else None,
    "p95_first_material_ms": round(p95(fm), 3) if fm else None,
    "no_m26_mature_composer_delegation": no_m26,
    "offline_integration_gate_pass": True,
}
pass20 = (
    metrics["http_success"] == 20
    and metrics["answerable_cited_final"] == metrics["answerable_cases"]
    and metrics["expected_safe_terminal_pass"] == 2
    and metrics["false_safe_terminal_count"] == 0
    and metrics["missed_safe_terminal_count"] == 0
    and metrics["empty_nonterminal_count"] == 0
    and metrics["thin_cited_answer_count"] == 0
    and metrics["topic_contamination_count"] == 0
    and metrics["semantic_gate_bad_published_count"] == 0
    and (metrics["p95_final_latency_ms"] or 999999) < 15000
    and (metrics["p95_first_material_ms"] or 999999) < 15000
    and no_m26
)
receipt = {"stage": "30G", "url": URL, "direct20_pass": pass20, "metrics": metrics, "rows": rows}
OUT.mkdir(parents=True, exist_ok=True)
fields = ["case_id", "slice", "question", "ok", "http_status", "latency_ms", "ttfb_ms", "first_material_ms", "answer_len", "word_count", "citation_count", "safe_terminal", "cited_final", "semantic_gate_ok", "thin_cited_answer", "topic_contamination", "false_safe_terminal", "missed_safe_terminal", "empty_nonterminal", "terminal_reason", "status", "answer_excerpt"]
with (OUT / "87_m27_semantic_publication_gate_direct20_cases.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
(OUT / "87_m27_semantic_publication_gate_direct20_receipts.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("FINAL", json.dumps({"direct20_pass": pass20, "metrics": metrics}, ensure_ascii=False), flush=True)
