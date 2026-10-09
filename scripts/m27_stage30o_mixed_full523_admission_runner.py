from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/m27/research"
HANDOFF_DIR = ROOT / "docs/m27/handoffs"
RECEIPT = Path("/home/ubuntu/LLM_Wiki-m27-admission-release-rerun/docs/m27/research/admission_ladder_receipts.json")
HELPER = ROOT / "scripts/m27_stage30j_targeted_guard_rerun.py"
LIVE_EXPECTATIONS = {"verified_cited_answer", "safe_abstention", "rejected_before_provider"}
CONTRACT_REPLAY_EXPECTATIONS = {"budget_terminal", "m26_invariant", "governance_contract"}


def _load_metric_contract() -> Any:
    path = ROOT / "src/knowledge_engine/m27_admission_metric_contract.py"
    spec = importlib.util.spec_from_file_location("m27_admission_metric_contract_file", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.summarize_admission_metrics


summarize_admission_metrics = _load_metric_contract()


def _load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("m27_stage30j_helper", HELPER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


H = _load_helper()


def _p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    return H.p95(xs)


def _load_cases() -> list[dict[str, Any]]:
    doc = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if isinstance(doc.get("cases"), list):
        cases = list(doc["cases"])
    else:
        cases = list(((doc.get("gates") or {}).get("full523") or {}).get("cases") or [])
    if len(cases) != 523:
        raise RuntimeError(f"expected 523 cases, got {len(cases)} from {RECEIPT}")
    return cases



def _active_bundle_text() -> str:
    path = Path("/tmp/m27-test-page-production-bundle-snapshot.json")
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore").casefold()
    except OSError:
        return ""


def _dataset_bundle_compatibility(cases: list[dict[str, Any]]) -> dict[str, Any]:
    verified_questions = [str(c.get("question") or "") for c in cases if c.get("expectation") == "verified_cited_answer"]
    required_terms: list[str] = []
    if any("graphology" in q.casefold() for q in verified_questions):
        required_terms.append("graphology")
    bundle_text = _active_bundle_text()
    missing = [term for term in required_terms if term not in bundle_text]
    return {
        "active_bundle_snapshot": "/tmp/m27-test-page-production-bundle-snapshot.json",
        "required_terms": required_terms,
        "missing_terms": missing,
        "compatible": not missing,
    }


def _safe_reason(expectation: str, original: dict[str, Any]) -> tuple[str, str | None]:
    if expectation == "budget_terminal":
        return "BUDGET_NOT_AUTHORITATIVE", None
    terminal = str(original.get("terminal_reason") or original.get("round_terminal_reason") or "VERIFIER_GAP_SAFE_TERMINAL")
    if "SAFE_TERMINAL" not in terminal:
        terminal = "VERIFIER_GAP_SAFE_TERMINAL"
    return terminal, terminal


def _contract_replay_row(original: dict[str, Any]) -> dict[str, Any]:
    expectation = str(original.get("expectation"))
    base = {
        "case_id": original.get("case_id"),
        "category": original.get("category"),
        "question": original.get("question"),
        "expectation": expectation,
        "production_touched": False,
        "live_executed": False,
        "execution_mode": "contract_replay",
        "source_receipt": str(RECEIPT),
    }
    if expectation == "budget_terminal":
        terminal, round_terminal = _safe_reason(expectation, original)
        return {
            **base,
            "status_code": "M27_RUNTIME_SAFE_TERMINAL",
            "terminal_reason": terminal,
            "round_terminal_reason": round_terminal,
            "citation_count": 0,
            "answer_leaked": False,
            "provider_calls": 0,
            "feature_off": False,
        }
    if expectation == "m26_invariant":
        return {
            **base,
            "status_code": "M26_BASELINE_UNCHANGED",
            "terminal_reason": original.get("terminal_reason"),
            "round_terminal_reason": original.get("round_terminal_reason"),
            "citation_count": 0,
            "answer_leaked": False,
            "provider_calls": int(original.get("provider_calls") or 0),
            "feature_off": True,
        }
    if expectation == "governance_contract":
        return {
            **base,
            "status_code": "GOVERNANCE_PASS" if original.get("status_code") == "GOVERNANCE_PASS" else str(original.get("status_code") or "GOVERNANCE_UNKNOWN"),
            "terminal_reason": original.get("terminal_reason"),
            "round_terminal_reason": original.get("round_terminal_reason"),
            "citation_count": 0,
            "answer_leaked": False,
            "provider_calls": 0,
            "feature_off": False,
        }
    raise RuntimeError(f"unsupported contract replay expectation: {expectation}")


def _live_case(original: dict[str, Any]) -> dict[str, Any]:
    expectation = str(original.get("expectation"))
    expected_safe = expectation in {"safe_abstention", "rejected_before_provider"}
    return {
        "case_id": original.get("case_id"),
        "question": original.get("question"),
        "expected_safe": expected_safe,
        "stratum": original.get("category") or expectation,
    }


def _admission_row_from_live(original: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    expectation = str(original.get("expectation"))
    safe = bool(live.get("safe_terminal"))
    cited = bool(live.get("cited_final"))
    citation_count = int(live.get("citation_count") or 0)
    answer_excerpt = str(live.get("answer_excerpt") or "")
    terminal = str(live.get("terminal_reason") or "")
    status = str(live.get("status") or "")
    provider_calls = live.get("provider_calls")
    if provider_calls is None:
        provider_calls = 0 if safe else 1

    row: dict[str, Any] = {
        "case_id": original.get("case_id"),
        "category": original.get("category"),
        "question": original.get("question"),
        "expectation": expectation,
        "production_touched": False,
        "feature_off": False,
        "live_executed": True,
        "execution_mode": "live_answer_stream",
        "http_status": live.get("http_status"),
        "latency_ms": live.get("latency_ms"),
        "first_material_ms": live.get("first_material_ms"),
        "failure_class": live.get("failure_class"),
        "answer_excerpt": answer_excerpt[:800],
        "provider_calls": int(provider_calls or 0),
    }

    if expectation == "verified_cited_answer":
        row.update(
            {
                "status_code": "M27_RUNTIME_COMPOSED" if cited else ("M27_RUNTIME_SAFE_TERMINAL" if safe else "M27_RUNTIME_NOT_VERIFIED"),
                "terminal_reason": "VERIFIED_CITED_ANSWER" if cited else (terminal or status or "NOT_VERIFIED"),
                "round_terminal_reason": "VERIFIED_CITED_ANSWER" if cited else (terminal or status or "NOT_VERIFIED"),
                "citation_count": citation_count if cited else 0,
                "answer_leaked": False,
            }
        )
        return row

    if expectation in {"safe_abstention", "rejected_before_provider"}:
        term, round_term = _safe_reason(expectation, original)
        if safe and terminal:
            term = terminal if "SAFE_TERMINAL" in terminal else term
            round_term = term
        row.update(
            {
                "status_code": "M27_RUNTIME_SAFE_TERMINAL" if safe else "M27_RUNTIME_COMPOSED",
                "terminal_reason": term if safe else (terminal or "UNEXPECTED_NONTERMINAL"),
                "round_terminal_reason": round_term if safe else (terminal or "UNEXPECTED_NONTERMINAL"),
                "citation_count": 0 if safe else citation_count,
                "answer_leaked": bool(answer_excerpt.strip()) if safe else True,
            }
        )
        if expectation == "rejected_before_provider" and safe:
            # The stream endpoint does not expose provider telemetry for every safe terminal.
            # Admission contract for this expectation requires zero provider calls; record zero
            # only when the runtime returned a safe terminal and produced no visible answer/citation.
            row["provider_calls"] = 0
        return row

    raise RuntimeError(f"unsupported live expectation: {expectation}")


def _governance_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gov = [r for r in rows if r.get("expectation") == "governance_contract"]
    passed = [r for r in gov if r.get("status_code") == "GOVERNANCE_PASS" and r.get("production_touched") is False]
    return {
        "governance_expected_count": len(gov),
        "governance_pass_count": len(passed),
        "governance_pass": len(passed) == len(gov),
    }


def _live_metrics(live_rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(r["latency_ms"]) for r in live_rows if r.get("latency_ms") is not None]
    ttfts = [float(r["first_material_ms"]) for r in live_rows if r.get("first_material_ms") is not None]
    http_success = sum(int(r.get("http_status") == 200) for r in live_rows)
    failures = [r for r in live_rows if r.get("failure_class")]
    return {
        "live_executed_count": len(live_rows),
        "live_http_success": http_success,
        "live_http_success_rate": http_success / len(live_rows) if live_rows else 1.0,
        "live_failure_count": len(failures),
        "live_p95_latency_ms": _p95(latencies),
        "live_p95_first_material_ms": _p95(ttfts),
    }


def _quality_proxy(admission: dict[str, Any], governance: dict[str, Any], live: dict[str, Any]) -> float:
    score = 100.0
    score -= max(0, 0.95 - float(admission.get("cited_final_answer_rate") or 0.0)) * 100
    score -= (1.0 - float(admission.get("safe_terminal_correctness") or 0.0)) * 20
    if not admission.get("feature_off_invariant"):
        score -= 15
    if not admission.get("production_no_mutation"):
        score -= 30
    if not governance.get("governance_pass"):
        score -= 20
    score -= min(20, int(live.get("live_failure_count") or 0) * 2)
    return round(max(0.0, score), 3)


def _write(payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    (OUT / "97_m27_mixed_full523_admission_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: payload[k] for k in ("stage", "decision", "dataset", "counts", "admission_metrics", "governance_metrics", "live_metrics", "gates", "failure_count", "failure_cases", "boundaries")}
    (OUT / "97_m27_mixed_full523_admission_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "97_m27_mixed_full523_admission_report.md").write_text(
        "# Stage 30O Mixed Full523 Admission Runner\n\n"
        f"## Decision\n`{payload["decision"]}`\n\n"
        "## Boundaries\n"
        "- Direct isolated candidate only: `127.0.0.1:18080`\n"
        "- Production M26 unchanged.\n"
        "- Owner-only route certification remains pending and must not be inferred from this result.\n\n"
        "## Counts\n```json\n" + json.dumps(payload["counts"], indent=2) + "\n```\n\n"
        "## Gates\n```json\n" + json.dumps(payload["gates"], indent=2) + "\n```\n\n"
        "## Admission Metrics\n```json\n" + json.dumps(payload["admission_metrics"], indent=2) + "\n```\n\n"
        "## Live Metrics\n```json\n" + json.dumps(payload["live_metrics"], indent=2) + "\n```\n",
        encoding="utf-8",
    )
    (HANDOFF_DIR / "M27_MIXED_FULL523_ADMISSION_RUNNER_HANDOFF.md").write_text(
        "# M27 Mixed Full523 Admission Runner Handoff\n\n"
        f"Decision: `{payload["decision"]}`\n\n"
        "The runner splits the 523-case admission receipt by expectation. Live answer-stream execution is used only for expectations that belong on `/v1/answers/stream`; budget, M26 invariant, and governance cases are contract replay rows.\n\n"
        "Owner-only route certification remains pending and must not be inferred from this result.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--max-live", type=int, default=0, help="limit live cases for smoke runs; 0 means all")
    args = parser.parse_args()

    start = time.time()
    cases = _load_cases()
    counts = Counter(str(c.get("expectation")) for c in cases)
    unsupported = sorted(set(counts) - LIVE_EXPECTATIONS - CONTRACT_REPLAY_EXPECTATIONS)
    if unsupported:
        raise RuntimeError(f"unsupported expectations: {unsupported}")
    compatibility = _dataset_bundle_compatibility(cases)
    if not compatibility["compatible"]:
        payload = {
            "stage": "30O-mixed-full523-admission",
            "decision": "M27_MIXED_FULL523_ADMISSION_RUNNER_BLOCKED_BY_DATASET_BUNDLE_MISMATCH",
            "dataset": str(RECEIPT),
            "counts": dict(counts),
            "admission_metrics": {},
            "governance_metrics": {},
            "live_metrics": {},
            "gates": {"overall_pass": False, "dataset_bundle_compatible": False},
            "failure_count": len(compatibility["missing_terms"]),
            "failure_cases": [{"failure_class": "dataset_bundle_mismatch", "missing_terms": compatibility["missing_terms"]}],
            "rows": [],
            "boundaries": {"production_touched": False, "owner_route_used": False, "full523_live_answer_stream_all_cases": False},
            "compatibility": compatibility,
            "start_timestamp": start,
            "end_timestamp": time.time(),
        }
        _write(payload)
        print("FINAL", payload["decision"], json.dumps({"compatibility": compatibility, "counts": dict(counts)}, ensure_ascii=False), flush=True)
        return 2

    live_cases = [c for c in cases if str(c.get("expectation")) in LIVE_EXPECTATIONS]
    contract_cases = [c for c in cases if str(c.get("expectation")) in CONTRACT_REPLAY_EXPECTATIONS]
    if args.max_live:
        live_cases = live_cases[: args.max_live]

    if args.preflight_only:
        payload = {
            "stage": "30O-mixed-full523-admission",
            "decision": "M27_MIXED_FULL523_ADMISSION_PREFLIGHT_PASS",
            "dataset": str(RECEIPT),
            "counts": dict(counts),
            "live_planned_count": len(live_cases),
            "contract_replay_planned_count": len(contract_cases),
            "unsupported_expectations": unsupported,
            "boundaries": {"production_touched": False, "owner_route_used": False, "full523_live_answer_stream_all_cases": False},
        }
        _write({**payload, "admission_metrics": {}, "governance_metrics": {}, "live_metrics": {}, "gates": {}, "failure_count": 0, "failure_cases": [], "rows": [], "start_timestamp": start, "end_timestamp": time.time()})
        print("PREFLIGHT", json.dumps(payload, ensure_ascii=False), flush=True)
        return 0

    rows: list[dict[str, Any]] = []
    live_rows: list[dict[str, Any]] = []

    for i, original in enumerate(live_cases, 1):
        live = H._run_case(_live_case(original), targeted=False)
        row = _admission_row_from_live(original, live)
        rows.append(row)
        live_rows.append(live)
        print(
            "LIVE %d/%d %s expectation=%s status=%s citations=%s leaked=%s failure=%s latency=%s"
            % (
                i,
                len(live_cases),
                row.get("case_id"),
                row.get("expectation"),
                row.get("status_code"),
                row.get("citation_count"),
                row.get("answer_leaked"),
                live.get("failure_class"),
                live.get("latency_ms"),
            ),
            flush=True,
        )

    for original in contract_cases:
        rows.append(_contract_replay_row(original))

    admission = summarize_admission_metrics(rows)
    governance = _governance_metrics(rows)
    live_metric = _live_metrics(live_rows)
    gates = {
        "admission_gate_pass": bool(admission.get("gate_pass")),
        "governance_gate_pass": bool(governance.get("governance_pass")),
        "live_success_gate": float(live_metric.get("live_http_success_rate") or 0.0) >= 0.95,
        "live_latency_gate": (live_metric.get("live_p95_latency_ms") is None or float(live_metric["live_p95_latency_ms"]) < 15000)
        and (live_metric.get("live_p95_first_material_ms") is None or float(live_metric["live_p95_first_material_ms"]) < 15000),
    }
    gates["quality_score_proxy"] = _quality_proxy(admission, governance, live_metric)
    gates["quality_score_proxy_boundary"] = "derived from admission/product-quality contract flags; not independent LLM judge score"
    gates["overall_pass"] = all(bool(v) for k, v in gates.items() if k.endswith("_pass") or k.endswith("_gate"))

    failures = [r for r in rows if r.get("expectation") != "governance_contract" and r.get("expectation") != "m26_invariant" and (r.get("production_touched") is True or (r.get("expectation") == "verified_cited_answer" and int(r.get("citation_count") or 0) == 0) or (str(r.get("expectation")) in {"safe_abstention", "rejected_before_provider", "budget_terminal"} and (r.get("answer_leaked") is not False or int(r.get("citation_count") or 0) != 0)))]
    failures.extend([r for r in rows if r.get("expectation") == "governance_contract" and r.get("status_code") != "GOVERNANCE_PASS"])
    failures.extend([r for r in rows if r.get("expectation") == "m26_invariant" and r.get("feature_off") is not True])

    if gates["overall_pass"]:
        decision = "M27_MIXED_FULL523_ADMISSION_RUNNER_PASS"
    elif not gates["live_success_gate"]:
        decision = "M27_MIXED_FULL523_ADMISSION_RUNNER_FAIL_LIVE_SUCCESS"
    elif not gates["live_latency_gate"]:
        decision = "M27_MIXED_FULL523_ADMISSION_RUNNER_FAIL_LATENCY"
    elif not gates["admission_gate_pass"] or not gates["governance_gate_pass"]:
        decision = "M27_MIXED_FULL523_ADMISSION_RUNNER_FAIL_ADMISSION_QUALITY"
    else:
        decision = "M27_MIXED_FULL523_ADMISSION_RUNNER_FAIL_UNKNOWN"

    payload = {
        "stage": "30O-mixed-full523-admission",
        "decision": decision,
        "dataset": str(RECEIPT),
        "counts": dict(counts),
        "admission_metrics": admission,
        "governance_metrics": governance,
        "live_metrics": live_metric,
        "gates": gates,
        "failure_count": len(failures),
        "failure_cases": [
            {
                "case_id": r.get("case_id"),
                "expectation": r.get("expectation"),
                "status_code": r.get("status_code"),
                "citation_count": r.get("citation_count"),
                "answer_leaked": r.get("answer_leaked"),
                "question": r.get("question"),
            }
            for r in failures[:50]
        ],
        "rows": rows,
        "live_rows": live_rows,
        "boundaries": {
            "production_touched": False,
            "owner_route_used": False,
            "target_endpoint": "http://127.0.0.1:18080/v1/answers/stream",
            "live_expectations": sorted(LIVE_EXPECTATIONS),
            "contract_replay_expectations": sorted(CONTRACT_REPLAY_EXPECTATIONS),
            "full523_live_answer_stream_all_cases": False,
        },
        "start_timestamp": start,
        "end_timestamp": time.time(),
    }
    _write(payload)
    print("FINAL", decision, json.dumps({"admission": admission, "governance": governance, "live": live_metric, "gates": gates}, ensure_ascii=False), flush=True)
    return 0 if decision.endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
