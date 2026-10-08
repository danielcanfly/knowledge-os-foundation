from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/m27/research"
HANDOFF = ROOT / "docs/m27/handoffs/M27_DIRECT100_TARGETED_GUARD_RERUN_HANDOFF.md"
URL = "http://127.0.0.1:18080/v1/answers/stream"
TARGET = ROOT / "scripts/m27_stage30g_direct20.py"
STAGE30H = Path("/home/ubuntu/LLM_Wiki-m27-direct100-scale-30h")
STAGE30I = ROOT
CASES_100_CSV = STAGE30H / "docs/m27/research/88_m27_direct_candidate_100_scale_eval_cases.csv"
TRIAGE_MATRIX = STAGE30I / "docs/m27/research/89_m27_direct100_failure_adjudication_matrix.csv"
SOURCE = ROOT / "pilot/m26/m26-pa-5-frozen-population.json"

DECISION_PASS = "M27_DIRECT100_TARGETED_GUARD_RERUN_PASS"


def _load_helpers() -> tuple[Any, Any]:
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name in {"parse_sse", "post", "p95"}
    ]
    namespace: dict[str, Any] = {"__name__": "m27_stage30j_helpers", "__file__": str(TARGET)}
    import json as _json
    import time as _time
    import urllib as _urllib
    import urllib.error as _urllib_error
    import urllib.request as _urllib_request
    namespace.update({"URL": URL, "json": _json, "time": _time, "urllib": _urllib})
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(TARGET), "exec"), namespace)
    return namespace["post"], namespace["p95"]


post, p95 = _load_helpers()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0].keys()) if rows else ["case_id"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _p95(xs: list[float]) -> float | None:
    return p95(xs) if xs else None


def _has_precise_traffic_answer(question: str, answer: str) -> bool:
    import re
    q = question.casefold()
    a = answer.casefold()
    release_ids = re.findall(r"\b20\d{6}t\d{6}z-[a-f0-9]{8,}\b", q)
    has_release = (not release_ids) or any(x in a for x in release_ids)
    has_metric = bool(re.search(r"\b(?:[0-9][0-9,.]*|zero)\s*(?:requests?|visits?|sessions?|queries|calls|users|events|rps|qps)\b", a))
    return has_release and has_metric


def _has_harness_provenance_answer(answer: str) -> bool:
    a = answer.casefold()
    return all(k in a for k in ("retrieved-at", "source-commit", "release"))


def _topic_contamination(question: str, answer: str) -> bool:
    q = question.casefold()
    a = answer.casefold()
    triad = ("kubernetes", "x402", "hotel")
    if any(word in a and word not in q for word in triad):
        return True
    if "retrieved-at" in q and "source-commit" in q and "harness" in q:
        if any(x in a for x in ("iras", "tax", "corporate income", "shareholder test")):
            return True
    return False


def _expected_safe(row: dict[str, Any]) -> bool:
    val = row.get("expected_safe")
    if isinstance(val, bool):
        return val
    return str(val).casefold() in {"true", "1", "yes"}


def _source_fingerprint() -> dict[str, str]:
    out = {}
    for name, path in {
        "stage30h_cases_csv": CASES_100_CSV,
        "stage30i_triage_matrix_csv": TRIAGE_MATRIX,
        "frozen_population_json": SOURCE,
    }.items():
        out[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "MISSING"
    return out


def _token(*parts: str) -> str:
    return "_".join(parts)


def _static_no_m26_mature_composer() -> bool:
    source = (ROOT / "src/knowledge_engine/m27_agent_product_runtime.py").read_text(encoding="utf-8")
    forbidden = (_token("run", "owner", "arbitrary", "query"), _token("synthesize", "and", "verify"), "_" + _token("synthesize", "and", "verify"))
    return not any(token in source for token in forbidden)


def _run_case(case: dict[str, Any], *, targeted: bool) -> dict[str, Any]:
    q = str(case["question"])
    x = post(q, timeout=75)
    answer = str(x.get("answer_excerpt") or "")
    safe = bool(x.get("safe_terminal"))
    traffic_obligation = "exact" in q.casefold() and "production traffic volume" in q.casefold()
    provenance_obligation = "retrieved-at" in q.casefold() and "source-commit" in q.casefold() and "release" in q.casefold()
    cited_final = bool(x.get("cited_final"))
    thin_cited = bool((not safe) and x.get("citation_count") and x.get("thin_cited_answer"))
    contamination = _topic_contamination(q, answer)
    obligation_satisfied = False
    evidence_sufficient = False
    failure_class = ""
    if traffic_obligation:
        if safe:
            obligation_satisfied = True
            evidence_sufficient = False
        elif cited_final and _has_precise_traffic_answer(q, answer):
            obligation_satisfied = True
            evidence_sufficient = True
        else:
            failure_class = "safe_miss"
    elif provenance_obligation:
        if safe:
            obligation_satisfied = True
            evidence_sufficient = False
        elif cited_final and _has_harness_provenance_answer(answer) and not contamination:
            obligation_satisfied = True
            evidence_sufficient = True
        else:
            failure_class = "thin_cited" if (thin_cited or contamination or x.get("citation_count")) else "product_quality"
    else:
        expected = _expected_safe(case)
        if expected:
            obligation_satisfied = safe
            if not safe:
                failure_class = "safe_miss"
        else:
            obligation_satisfied = cited_final and not thin_cited and not contamination
            evidence_sufficient = cited_final
            if safe:
                failure_class = "false_safe"
            elif not cited_final:
                failure_class = "not_cited"
            elif thin_cited:
                failure_class = "thin_cited"
            elif contamination:
                failure_class = "topic_contamination"
    if (not targeted) and safe and not _expected_safe(case):
        failure_class = failure_class or "false_safe"
    semantic_bad_publish = bool((not safe) and x.get("answer_len") and not x.get("semantic_gate_ok"))
    if semantic_bad_publish and not failure_class:
        failure_class = "semantic_bad_publish"
    if thin_cited and not failure_class:
        failure_class = "thin_cited"
    if contamination and not failure_class:
        failure_class = "topic_contamination"
    row = {
        "case_id": case.get("case_id") or case.get("question_id"),
        "question": q,
        "stratum": case.get("stratum", ""),
        "expected_safe": _expected_safe(case),
        "targeted_source_failure_type": case.get("failure_type_candidate", ""),
        "http_status": x.get("http_status"),
        "ok": x.get("ok"),
        "latency_ms": x.get("latency_ms"),
        "ttfb_ms": x.get("ttfb_ms"),
        "first_material_ms": x.get("first_material_ms"),
        "answer_len": x.get("answer_len"),
        "word_count": x.get("word_count"),
        "citation_count": x.get("citation_count"),
        "safe_terminal": safe,
        "terminal_reason": x.get("terminal_reason", ""),
        "status": x.get("status", ""),
        "cited_final": cited_final,
        "semantic_gate_ok": x.get("semantic_gate_ok"),
        "thin_cited_answer": thin_cited,
        "topic_contamination": contamination,
        "semantic_bad_publish": semantic_bad_publish,
        "traffic_obligation": traffic_obligation,
        "provenance_obligation": provenance_obligation,
        "obligation_satisfied": obligation_satisfied,
        "evidence_sufficient": evidence_sufficient,
        "failure_class": failure_class,
        "answer_excerpt": answer[:800],
    }
    if targeted:
        print(
            f"TARGETED {row['case_id']} HTTP={row['http_status']} safe={safe} cited={cited_final} "
            f"obligation={obligation_satisfied} failure={failure_class} latency={row['latency_ms']}",
            flush=True,
        )
    return row


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    okrows = [r for r in rows if r.get("ok") and r.get("http_status") == 200]
    answerable = [r for r in rows if not r.get("expected_safe")]
    expected_safe = [r for r in rows if r.get("expected_safe")]
    lat = [float(r["latency_ms"]) for r in okrows if r.get("latency_ms") is not None]
    fm = [float(r["first_material_ms"]) for r in okrows if r.get("first_material_ms") is not None]
    return {
        "cases": len(rows),
        "http_success": len(okrows),
        "answerable_cases": len(answerable),
        "answerable_cited_final": sum(bool(r.get("cited_final")) for r in answerable),
        "expected_safe_cases": len(expected_safe),
        "expected_safe_correct": sum(bool(r.get("safe_terminal")) for r in expected_safe),
        "missed_safe_terminal": sum(bool(r.get("expected_safe") and not r.get("safe_terminal")) for r in rows),
        "false_safe_terminal": sum(bool((not r.get("expected_safe")) and r.get("safe_terminal")) for r in rows),
        "empty_nonterminal": sum(bool(r.get("http_status") == 200 and not r.get("safe_terminal") and not r.get("answer_len")) for r in rows),
        "thin_cited_answer": sum(bool(r.get("thin_cited_answer")) for r in rows),
        "topic_contamination": sum(bool(r.get("topic_contamination")) for r in rows),
        "semantic_bad_publish": sum(bool(r.get("semantic_bad_publish")) for r in rows),
        "obligation_satisfied": sum(bool(r.get("obligation_satisfied")) for r in rows),
        "p50_final_latency_ms": round(statistics.median(lat), 3) if lat else None,
        "p95_final_latency_ms": round(_p95(lat), 3) if lat else None,
        "p50_first_material_ms": round(statistics.median(fm), 3) if fm else None,
        "p95_first_material_ms": round(_p95(fm), 3) if fm else None,
        "first_material_count": len(fm),
        "no_m26_mature_composer_delegation": _static_no_m26_mature_composer(),
    }


def _targeted_decision(metrics: dict[str, Any], rows: list[dict[str, Any]]) -> str | None:
    if metrics["http_success"] != metrics["cases"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_BLOCKED_BY_RUNTIME"
    if any(r.get("failure_class") == "safe_miss" for r in rows):
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_TARGETED9_SAFE_MISS"
    if any(r.get("failure_class") == "thin_cited" or r.get("thin_cited_answer") for r in rows):
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_TARGETED9_THIN_CITED"
    if any(r.get("failure_class") for r in rows):
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY"
    if metrics["obligation_satisfied"] != metrics["cases"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY"
    if metrics["topic_contamination"] or metrics["semantic_bad_publish"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY"
    if (metrics.get("p95_final_latency_ms") or 999999) >= 15000 or (metrics.get("p95_first_material_ms") or 999999) >= 15000:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_LATENCY"
    return None


def _direct100_decision(metrics: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if metrics["http_success"] < 98:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_BLOCKED_BY_RUNTIME"
    answerable_required = math.ceil(metrics["answerable_cases"] * 0.95)
    if metrics["missed_safe_terminal"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_DIRECT100_SAFE_MISS"
    if metrics["thin_cited_answer"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_DIRECT100_THIN_CITED"
    if metrics["answerable_cited_final"] < answerable_required:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY"
    if metrics["expected_safe_correct"] != metrics["expected_safe_cases"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_DIRECT100_SAFE_MISS"
    if any(metrics[k] for k in ("false_safe_terminal", "empty_nonterminal", "topic_contamination", "semantic_bad_publish")):
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY"
    if not metrics["no_m26_mature_composer_delegation"]:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY"
    if (metrics.get("p95_final_latency_ms") or 999999) >= 15000 or (metrics.get("p95_first_material_ms") or 999999) >= 15000:
        return "M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_LATENCY"
    return DECISION_PASS


def _write_artifacts(
    *, decision: str, targeted_rows: list[dict[str, Any]], targeted_metrics: dict[str, Any],
    direct_rows: list[dict[str, Any]] | None, direct_metrics: dict[str, Any] | None,
    start: float, end: float,
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id", "question", "stratum", "expected_safe", "targeted_source_failure_type",
        "http_status", "ok", "latency_ms", "ttfb_ms", "first_material_ms", "answer_len", "word_count",
        "citation_count", "safe_terminal", "terminal_reason", "status", "cited_final", "semantic_gate_ok",
        "thin_cited_answer", "topic_contamination", "semantic_bad_publish", "traffic_obligation",
        "provenance_obligation", "obligation_satisfied", "evidence_sufficient", "failure_class", "answer_excerpt",
    ]
    _write_csv(OUT / "90_m27_direct100_targeted_9case_results.csv", targeted_rows, fields)
    if direct_rows is not None:
        _write_csv(OUT / "90_m27_direct100_targeted_100case_results.csv", direct_rows, fields)
    failures = [r for r in targeted_rows + (direct_rows or []) if r.get("failure_class")]
    if failures:
        _write_csv(OUT / "90_m27_direct100_targeted_guard_failures.csv", failures, fields)
    receipt = {
        "stage": "30J",
        "decision": decision,
        "target_url": URL,
        "start_timestamp": start,
        "end_timestamp": end,
        "image": "knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e",
        "code_head": "2dc7990efcd9a7d80d24bac740349d47e99dc689",
        "source_fingerprint": _source_fingerprint(),
        "targeted_metrics": targeted_metrics,
        "direct100_metrics": direct_metrics,
        "targeted_rows": targeted_rows,
        "direct100_rows": direct_rows or [],
        "owner_only_route_certification_inferred": False,
        "full523_executed": False,
        "nginx_modified": False,
        "production_m26_restarted_or_rebuilt": False,
        "test_backend_restarted_or_rebuilt": False,
    }
    (OUT / "m27_direct100_targeted_guard_rerun_receipts.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = [
        "# Stage 30J Direct100 Targeted Guard Rerun",
        "",
        "## Final decision",
        f"`{decision}`",
        "",
        "## Scope",
        f"- Direct isolated candidate endpoint: `{URL}`",
        "- Replaced only `m27-owner-canary-28` on `127.0.0.1:18080`.",
        "- No owner-only route certification, public rollout, release pointer mutation, Nginx modification, production M26 restart/rebuild, test backend restart/rebuild, admission/full523, Stage13/14, or Chunk002.",
        "- Owner-only route certification remains pending and must not be inferred from this result.",
        "",
        "## Build/runtime identity",
        "- Image: `knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e`",
        "- Code HEAD: `2dc7990efcd9a7d80d24bac740349d47e99dc689`",
        "- Previous rollback image: `knowledge-engine:m27-semantic-publication-gate-30g-67ca9928`",
        "",
        "## Dataset provenance",
        "```json",
        json.dumps(_source_fingerprint(), indent=2),
        "```",
        "",
        "## Targeted 9 metrics",
        "```json",
        json.dumps(targeted_metrics, indent=2),
        "```",
    ]
    if direct_metrics is not None:
        report += ["", "## Direct100 metrics", "```json", json.dumps(direct_metrics, indent=2), "```"]
    report += [
        "",
        "## Artifacts",
        "- `docs/m27/research/90_m27_direct100_targeted_9case_results.csv`",
        "- `docs/m27/research/m27_direct100_targeted_guard_rerun_receipts.json`",
        "- `docs/m27/research/90_m27_direct100_targeted_100case_results.csv` if Direct100 executed",
        "- `docs/m27/research/90_m27_direct100_targeted_guard_failures.csv` if failures remained",
        "- `docs/m27/handoffs/M27_DIRECT100_TARGETED_GUARD_RERUN_HANDOFF.md`",
        "",
    ]
    (OUT / "90_m27_direct100_targeted_guard_rerun_report.md").write_text("\n".join(report), encoding="utf-8")
    HANDOFF.write_text(
        "# Stage 30J handoff\n\n"
        f"Decision: `{decision}`\n\n"
        "Direct isolated candidate guard rerun completed. See `docs/m27/research/90_m27_direct100_targeted_guard_rerun_report.md` and receipts.\n\n"
        "Owner-only route certification remains pending and must not be inferred from this result.\n",
        encoding="utf-8",
    )


def main() -> int:
    start = time.time()
    if not TRIAGE_MATRIX.exists() or not CASES_100_CSV.exists() or not SOURCE.exists():
        decision = "M27_DIRECT100_TARGETED_GUARD_RERUN_BLOCKED_BY_DATASET_PROVENANCE"
        _write_artifacts(decision=decision, targeted_rows=[], targeted_metrics={}, direct_rows=None, direct_metrics=None, start=start, end=time.time())
        print("FINAL", decision, flush=True)
        return 2
    matrix = _read_csv(TRIAGE_MATRIX)
    if len(matrix) != 9:
        decision = "M27_DIRECT100_TARGETED_GUARD_RERUN_BLOCKED_BY_DATASET_PROVENANCE"
        _write_artifacts(decision=decision, targeted_rows=[], targeted_metrics={"matrix_rows": len(matrix)}, direct_rows=None, direct_metrics=None, start=start, end=time.time())
        print("FINAL", decision, flush=True)
        return 2
    targeted_cases = [{"case_id": r["case_id"], "question": r["query"], "expected_safe": r["old_expected_label"] == "SAFE_TERMINAL", "failure_type_candidate": r["failure_type_candidate"]} for r in matrix]
    targeted_rows = [_run_case(c, targeted=True) for c in targeted_cases]
    targeted_metrics = _metrics(targeted_rows)
    targeted_failure = _targeted_decision(targeted_metrics, targeted_rows)
    if targeted_failure:
        _write_artifacts(decision=targeted_failure, targeted_rows=targeted_rows, targeted_metrics=targeted_metrics, direct_rows=None, direct_metrics=None, start=start, end=time.time())
        print("FINAL", targeted_failure, json.dumps(targeted_metrics, ensure_ascii=False), flush=True)
        return 1
    direct_cases = _read_csv(CASES_100_CSV)
    if len(direct_cases) != 100:
        decision = "M27_DIRECT100_TARGETED_GUARD_RERUN_BLOCKED_BY_DATASET_PROVENANCE"
        _write_artifacts(decision=decision, targeted_rows=targeted_rows, targeted_metrics=targeted_metrics, direct_rows=None, direct_metrics=None, start=start, end=time.time())
        print("FINAL", decision, flush=True)
        return 2
    direct_rows = []
    for i, c in enumerate(direct_cases, 1):
        row = _run_case(c, targeted=False)
        direct_rows.append(row)
        print(f"DIRECT100 {i}/100 {row['case_id']} HTTP={row['http_status']} safe={row['safe_terminal']} cited={row['cited_final']} failure={row['failure_class']} latency={row['latency_ms']}", flush=True)
        # Progressive receipts in case long run is interrupted.
        _write_artifacts(decision="RUNNING_DIRECT100", targeted_rows=targeted_rows, targeted_metrics=targeted_metrics, direct_rows=direct_rows, direct_metrics=_metrics(direct_rows), start=start, end=time.time())
    direct_metrics = _metrics(direct_rows)
    decision = _direct100_decision(direct_metrics, direct_rows)
    _write_artifacts(decision=decision, targeted_rows=targeted_rows, targeted_metrics=targeted_metrics, direct_rows=direct_rows, direct_metrics=direct_metrics, start=start, end=time.time())
    print("FINAL", decision, json.dumps({"targeted": targeted_metrics, "direct100": direct_metrics}, ensure_ascii=False), flush=True)
    return 0 if decision == DECISION_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
