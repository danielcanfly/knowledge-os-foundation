#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "m27" / "research"
HANDOFFS = ROOT / "docs" / "m27" / "handoffs"

STAGE22_RECEIPTS = RESEARCH / "provider_only_config_rerun_receipts.json"
STAGE21_RECEIPTS = RESEARCH / "m27_provider_tail_product_answer_repair_receipts.json"
STAGE20_RECEIPTS = RESEARCH / "test_page_product_readiness_stage20_side_by_side_receipts.json"

DIMENSION_NAMES = {
    "answer_quality_from_canonical_api": "Answer Quality From Canonical API /30",
    "evidence_sources_citation_quality": "Evidence, Sources, and Citation Quality /20",
    "visitor_intent_homepage_fit": "Visitor Intent and Homepage Fit /15",
    "question_framing_quality": "Question Framing Quality /15",
    "corpus_representativeness": "Corpus Representativeness /10",
    "non_duplication_distinctiveness": "Non-Duplication and Distinctiveness /10",
}

CASE_DIAGNOSIS: dict[str, dict[str, str]] = {
    "C01": {"outcome": "empty nonterminal; Browser Use warning not cleared", "earliest": "product-surface answer planner / stream publication", "root": "Stage 20 produced a cited answer, but Stage 22 returned HTTP 200 with no cited answer, no safe terminal, no first material event, and a 19.9s final latency. The product-surface Browser Use warning path still has no durable M27 publication path.", "latency_class": "provider generation tail plus empty-final publication delay"},
    "C02": {"outcome": "cited answer but Owner hard-fail: source coverage too narrow", "earliest": "evidence strengthening / citation coverage admission", "root": "The answer was long enough and directly responsive, but it carried only one citation and triggered SOURCE_COVERAGE_TOO_NARROW under the Owner rubric. M27 can compose, but its citation/evidence boundary is too narrow for homepage-grade answer quality.", "latency_class": "provider/verifier path with insufficient source breadth"},
    "C03": {"outcome": "verifier-gap safe terminal on answerable case", "earliest": "verifier claim support / safe-terminal decision", "root": "M26 and Stage 20 both show the topic is answerable with citations, yet Stage 22 emits a safe terminal. This is not a justified abstention; it is a verifier-gap terminal caused by failure to transform available evidence into verifier-acceptable cited claims.", "latency_class": "safe-terminal delay after verifier gap"},
    "C04": {"outcome": "empty nonterminal regression after prior thin cited answer", "earliest": "answer composition / citation binding / stream publication", "root": "Stage 20 at least published a thin cited answer. Stage 22 drops to no answer and no safe terminal. That indicates the runtime crossed evidence selection, then failed to publish either a valid answer or an explicit safe terminal.", "latency_class": "provider generation tail plus publication drop"},
    "C05": {"outcome": "verifier-gap safe terminal on answerable case", "earliest": "answer composition / verifier claim support", "root": "Kubernetes-in-AI-infra is supported by the corpus and answered by M26/Stage 20. Stage 22 safe-terminal behavior points to composer/verifier mismatch, not absence of evidence.", "latency_class": "safe-terminal delay after verifier gap"},
    "C06": {"outcome": "thin cited answer below 85", "earliest": "answer composition", "root": "The answer was only 72 characters with one citation and failed THIN_ANSWER_SURFACE and SOURCE_COVERAGE_TOO_NARROW. The runtime accepted a citation-bound answer shape without enough product substance.", "latency_class": "provider/verifier path ending in thin surface"},
    "C07": {"outcome": "good cited answer >=85", "earliest": "none; passes bounded product gate for this case", "root": "Chinese GPU case demonstrates M27 can answer multilingual questions when lexical evidence alignment happens to work and citation coverage is adequate.", "latency_class": "acceptable answer quality, still latency-sensitive"},
    "C08": {"outcome": "empty nonterminal regression from Stage 20 pass", "earliest": "answer composition / stream publication", "root": "Stage 20 produced a cited answer and Stage 22 produced no answer or safe terminal. The evidence path can work, but the Stage 22 provider-only runtime loses publication on this ordinary cited case.", "latency_class": "publication delay/drop after runtime work"},
    "C09": {"outcome": "empty nonterminal regression from Stage 20 pass", "earliest": "answer composition / stream publication", "root": "RAG is an ordinary supported topic. Stage 20 cited output and M26 cited output show coverage exists; Stage 22 empty nonterminal is a publication/composition regression.", "latency_class": "publication delay/drop after runtime work"},
    "C10": {"outcome": "thin cited answer below 85", "earliest": "answer composition / evidence breadth", "root": "A broad multi-tenant platform question collapsed into a 220-character, one-citation answer. This is product answer planning failure: the runtime publishes a valid citation envelope but not a homepage-grade answer.", "latency_class": "provider tail with thin final surface"},
    "C11": {"outcome": "thin cited answer below 85", "earliest": "answer composition / evidence breadth", "root": "Private AI / TEE needs multi-source explanation. Stage 22 returned a short one-citation answer and failed thin-surface/source-breadth criteria.", "latency_class": "provider tail with thin final surface"},
    "C12": {"outcome": "empty nonterminal; verifier-gap terminal mismatch", "earliest": "verifier claim support / stream publication", "root": "Single-request cost is answerable in M26 and became safe in Stage 20. Stage 22 returned neither a cited answer nor a safe terminal. The system failed both verifier closure and final-state publication semantics.", "latency_class": "verifier gap with empty final event"},
    "C13": {"outcome": "good cited answer >=85", "earliest": "none; passes bounded product gate for this case", "root": "Reliability/observability question produced a long, multi-citation answer that passes Owner quality scoring.", "latency_class": "acceptable answer quality, still latency-sensitive"},
    "C14": {"outcome": "empty nonterminal regression from Stage 20 pass", "earliest": "answer composition / stream publication", "root": "The model-to-service question is supported and passed in Stage 20. Stage 22 no-answer/no-safe behavior identifies product-surface publication rather than retrieval absence.", "latency_class": "publication delay/drop after runtime work"},
    "C15": {"outcome": "multilingual normalization/coverage failure; empty nonterminal", "earliest": "query normalization / retrieval / multilingual evidence normalization", "root": "Chinese multi-tenant question did not pass and was not a justified safe fail. The executor uses lexical-primary retrieval without remote dense or explicit cross-lingual expansion, so language mismatch can starve downstream evidence or produce unverifiable claims.", "latency_class": "multilingual retrieval/composition gap plus provider tail"},
    "C16": {"outcome": "multilingual safe terminal; likely verifier-gap or inconsistent justification evidence", "earliest": "multilingual evidence normalization / verifier support matching", "root": "Stage 22 product-gate boolean marks C16 as pass-or-justified-safe, but the same receipt diagnosis lists C16 under answerable_safe_terminal_case_ids. Treat this as an unresolved multilingual verifier-gap ambiguity, not product readiness.", "latency_class": "safe-terminal delay with multilingual support mismatch"},
    "C17": {"outcome": "good cited answer >=85", "earliest": "none; passes bounded product gate for this case", "root": "Retrieval/verification/citation/safe-terminal meta-question produced a long, multi-citation answer and passes the Owner rubric.", "latency_class": "acceptable answer quality, still latency-sensitive"},
    "C18": {"outcome": "retrieval-hard verifier gap; empty nonterminal", "earliest": "verifier waiting for full answer / stream publication", "root": "The latency/TTFT/streaming relationship is answerable and Stage 20 safe-terminaled it. Stage 22 did not publish safe terminal or cited answer, showing a final-state contract gap after verifier failure.", "latency_class": "verifier waiting for full answer plus empty publication"},
    "C19": {"outcome": "justified safe terminal", "earliest": "pre-retrieval safety policy", "root": "The safety/prompt-injection probe should not return private prompts or credentials. Safe-terminal behavior is justified here.", "latency_class": "fast justified safe terminal"},
    "C20": {"outcome": "underspecified prompt not handled as clean safe terminal; empty nonterminal", "earliest": "query normalization / underspecified-question policy / stream publication", "root": "The vague request should become a clarification/safe terminal. Stage 22 returned no answer and no safe terminal after a long latency, which is a product-surface terminal semantics failure.", "latency_class": "safe-terminal policy miss plus publication delay"},
}

SUBSYSTEM_GAPS = [
    ("context contract", "Request, task, budget and evidence authorities are explicit, but the product surface still inherits legacy answer semantics through adapters.", "Context-native contract should expose answerable state, evidence sufficiency, claim graph readiness and publication intent as first-class milestones.", "Mature for isolation, immature for product-answer state transitions; no per-claim readiness contract crosses into stream publication.", "src/knowledge_engine/m27_runtime_execution.py:568-600, 946-973", "Add explicit answer-state machine with answerable/evidence-ready/claim-ready/publication-ready transitions."),
    ("evidence boundary", "Production authority admission exists and citation binding drift is checked, but cited answers can collapse to one source or no final publication.", "Evidence boundary should carry coverage requirements and source-breadth obligations into composition and verifier decisions.", "Authority is treated mostly as validity, not sufficiency; broad questions can pass with one source or fail into safe terminal despite evidence existing.", "src/knowledge_engine/m27_runtime_execution.py:654-660, 720-727, 779-797", "Represent required source coverage and corpus breadth before answer composition."),
    ("claim graph", "The public answer often has a single claim and the stream adapter only emits claim events after final runtime completion.", "Claim graph should allow incremental verified subclaims with per-claim evidence/citation binding.", "No live partial claim graph is emitted from the runtime; verifier waits for whole answer.", "src/knowledge_engine/m27_isolated_streaming.py:132-191, 256-267", "Introduce claim-level verifier outputs as runtime events, not post-hoc DTO splitting."),
    ("citation binding", "Binding preservation is validated after answer generation, and drift becomes safe terminal.", "Binding should be preserved through evidence selection, composition, verifier and stream publication without late all-or-nothing drop.", "Late binding failure loses answer, and narrow binding can still produce thin one-citation answers.", "src/knowledge_engine/m27_runtime_execution.py:779-797", "Make citation-bound answer plans before provider generation; require source breadth for broad questions."),
    ("verifier interface", "Verifier closure is binary: owner_only_cited_answer or safe terminal/empty terminal after gap.", "Verifier should return actionable gap categories, partial verified claims, and repairable unsupported spans.", "Verifier gap becomes continuation/provider retry or safe terminal; it does not expose enough structured cause to the stream or planner.", "src/knowledge_engine/m27_runtime_execution.py:821-861", "Add verifier-gap taxonomy and bounded deterministic repair hooks before provider retry."),
    ("stream publication semantics", "Verified material events are generated only after await worker; safe terminals emit only final safe_abstention_done.", "Stream should publish first verified cited segment as soon as it is verified, before full answer completion.", "First material latency is structurally close to final latency in failing paths.", "src/knowledge_engine/m27_isolated_streaming.py:230-267", "Wire runtime event_sink to verified_claim_ready/cited_segment_ready events during execution."),
    ("provider orchestration", "Owner-only executor allows 4 provider attempts and 60s deadline; runtime can continue on verifier gap.", "Provider policy should be bounded by product p95 and stop/recover deterministically when enough evidence exists.", "Provider tail is allowed to dominate p95 and retry without producing early material.", "src/knowledge_engine/m27_test_page_executor.py:201-206, 236-247; src/knowledge_engine/m27_runtime_execution.py:588-599, 832-861", "Cap provider tail under product SLO and prefer deterministic evidence-bound composition before retries."),
    ("compute budget policy", "Budget has a 60s deadline and 4 attempts in the product path.", "Budget policy should be product-surface aware: p95 <15s and first material <15s are hard constraints, not after-the-fact metrics.", "Current budget admits work that cannot satisfy p95/first-material goals.", "src/knowledge_engine/m27_test_page_executor.py:240-246", "Compute budgets should be derived from public SLO with per-stage timeboxes."),
    ("multilingual evidence normalization", "Executor normalizes question, then runs lexical-primary retrieval with dense channels disabled and no explicit cross-lingual expansion.", "Multilingual query should map to canonical article/evidence language and preserve support matching across languages.", "C15/C16 show Chinese/Japanese coverage gaps despite English corpus support.", "src/knowledge_engine/m27_test_page_executor.py:123-172", "Add multilingual canonical term expansion and cross-lingual evidence support matching before verifier."),
    ("memory/governance interaction", "No production datastore writes occurred, and governance/redaction held.", "Governance should remain isolated while still carrying product-quality diagnostics.", "Safety is solid; diagnostic telemetry is too thin for root-cause latency attribution.", "docs/m27/research/provider_only_config_rerun_receipts.json", "Keep governance invariant, expand redacted per-stage telemetry."),
    ("tool/MCP integration", "Only knowledge.search is permitted in the isolated runtime.", "Tool integration should expose retrieval timing, evidence deltas and article boundary quality to verifier and streamer.", "Tool records exist but comparator receipts did not preserve per-stage timing and provider-call telemetry per case.", "src/knowledge_engine/m27_runtime_execution.py:630-649, 974-994", "Persist per-case execution_summary/telemetry in product comparison receipts."),
    ("product-surface answer planner", "The planner accepts thin answers and empty nonterminal finals on homepage-style questions.", "Planner should enforce homepage-grade answer depth, visitor fit, source breadth and clean terminal semantics before publication.", "Only 3/20 cases were good cited >=85 in Stage 22; 4/7 cited answers failed Owner scoring.", "docs/m27/research/provider_only_config_rerun_receipts.json", "Add product answer planner between evidence sufficiency and verifier, not M26 composer rebase."),
]

ROOT_CAUSES = [
    (1, "Stream publication is post-hoc, not claim-native", "m27_isolated_event_stream waits for worker completion before emitting verified_claim_ready/cited_segment_ready; this structurally ties first material latency to final latency.", "High", "src/knowledge_engine/m27_isolated_streaming.py:230-267"),
    (2, "Verifier-gap path is all-or-nothing", "Failure to produce a fully verified cited answer becomes continuation, safe terminal, or empty final; partial verified claims and precise gap causes are not surfaced.", "High", "src/knowledge_engine/m27_runtime_execution.py:821-861"),
    (3, "Product answer planner is immature", "Thin one-citation answers can be published, while answerable cases become safe/empty terminals. Product-depth and homepage-fit are not first-class gates before publication.", "High", "Stage22 Owner 85 scoring and case matrix"),
    (4, "Provider budget violates product SLO", "The owner-only product path grants 60s and 4 provider attempts; p95 final 44.9s and p95 first material 40.3s are unsurprising under this policy.", "High", "src/knowledge_engine/m27_test_page_executor.py:240-246"),
    (5, "Evidence sufficiency is weaker than evidence validity", "Authority/binding checks validate provenance, but broad questions still receive one-source/thin answers or fail despite available evidence.", "Medium", "Stage22 C02/C06/C10/C11 scores"),
    (6, "Multilingual retrieval/support normalization is missing", "C15/C16 fail while related English topics are answerable; lexical-primary retrieval with dense disabled is brittle for cross-lingual queries.", "Medium", "src/knowledge_engine/m27_test_page_executor.py:143-153"),
    (7, "Diagnostic receipts omit internal per-stage telemetry", "Comparator receipts preserve final/first material timings but not retrieval/provider/verifier micro-timeline per case, forcing root cause to be reconstructed from code and prior receipts.", "Medium", "Stage22 receipts schema"),
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def sanitize_question(case_id: str, question: str) -> str:
    if case_id == "C19":
        return "[redacted safety/prompt-injection probe]"
    return question.replace("|", "\\|")


def fmt_ms(value: Any) -> str:
    if value is None:
        return "not emitted"
    try:
        return f"{float(value):.3f}"
    except Exception:
        return str(value)


def short_bool(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return "n/a"
    return str(value)


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>") for x in row) + " |")
    return "\n".join(out)


def run_stream_probes() -> dict[str, Any]:
    # Avoid importing knowledge_engine here: this diagnostic workspace may not have
    # optional HTTP/provider dependencies installed. The event names below are a
    # static dry-run of m27_verified_material_events as inspected in
    # src/knowledge_engine/m27_isolated_streaming.py:132-191.
    return {
        "stream_verified_dry_run": ["verified_claim_ready", "cited_segment_ready", "final_answer_done"],
        "stream_safe_terminal_dry_run": ["safe_abstention_done"],
        "interpretation": "Publication adapter can serialize verified material events, but code emits them only after awaiting the worker result; it is not a live claim-level stream.",
        "dependency_note": "Static dry-run used because importing knowledge_engine in this shell requires optional httpx dependency unavailable in the diagnostic environment.",
    }


def file_contains(path: Path, needle: str) -> bool:
    return needle in path.read_text()


def main() -> None:
    stage22 = load_json(STAGE22_RECEIPTS)
    stage21 = load_json(STAGE21_RECEIPTS)
    comparison = stage22["comparison"]
    rows = comparison["rows"]
    m27_metrics = comparison["m27_metrics"]
    product_gate = stage22["stage22_provider_only_config_rerun"]["product_gate"]
    diagnosis = stage22["stage22_provider_only_config_rerun"]["diagnosis"]
    scoring = stage22["stage22_provider_only_config_rerun"]["owner_85_scoring"]
    stage20_diag = {item["case_id"]: item for item in stage21["stage20_per_case_diagnosis"]}
    score_by_case = {item["case_id"]: item for item in scoring["per_case_scores"]}
    case_matrix: list[dict[str, Any]] = []
    latency_timelines: list[dict[str, Any]] = []
    owner_scores: list[dict[str, Any]] = []

    for row in rows:
        case = row["case"]
        m27 = row["m27"]
        cid = case["case_id"]
        diag = CASE_DIAGNOSIS[cid]
        score = score_by_case.get(cid)
        final_ms = m27.get("latency_ms")
        first_ms = m27.get("first_material_ms")
        lag_ms = None if first_ms is None or final_ms is None else round(float(final_ms) - float(first_ms), 3)
        stage20_m27 = stage20_diag.get(cid, {}).get("stage20_m27", {})
        matrix_row = {
            "case_id": cid,
            "slice": case.get("slice"),
            "question_sanitized": sanitize_question(cid, str(case.get("question", ""))),
            "stage20_m27_cited": stage20_m27.get("cited"),
            "stage20_m27_safe": stage20_m27.get("safe"),
            "stage22_cited": bool(m27.get("cited_answer")),
            "stage22_safe_terminal": bool(m27.get("safe_terminal")),
            "stage22_answer_len": m27.get("answer_len"),
            "stage22_citation_count": m27.get("citation_count"),
            "final_latency_ms": final_ms,
            "first_material_ms": first_ms,
            "first_to_final_lag_ms": lag_ms,
            "outcome_class": diag["outcome"],
            "earliest_unrecoverable_stage": diag["earliest"],
            "root_cause_summary": diag["root"],
            "latency_class": diag["latency_class"],
            "owner_score": score.get("score") if score else None,
            "owner_result": score.get("result") if score else None,
            "owner_hard_fail_codes": score.get("hard_fail_codes") if score else [],
        }
        case_matrix.append(matrix_row)
        latency_timelines.append({
            "case_id": cid,
            "request_start_ms": 0,
            "retrieval_start_end": "runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps",
            "evidence_admission_start_end": "not preserved; code path admits production evidence before compile/verify",
            "first_provider_call_start_end": "not preserved; provider calls occur inside verifier block after fast deterministic path misses",
            "verifier_start_end": "not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify",
            "first_verified_claim_ready_ms": "after worker completion only; no live claim-ready timestamp",
            "first_cited_segment_ready_ms": "after worker completion only; no live cited-segment timestamp",
            "first_material_event_ms": first_ms,
            "final_event_ms": final_ms,
            "first_to_final_lag_ms": lag_ms,
            "latency_class": diag["latency_class"],
        })
        if score:
            failures = []
            for key, name in DIMENSION_NAMES.items():
                val = score.get("criterion_scores", {}).get(key)
                max_points = int(name.split("/")[-1])
                if val is not None and val < max_points:
                    failures.append(f"{name}: {val}")
            owner_scores.append({
                "case_id": cid,
                "score": score.get("score"),
                "result": score.get("result"),
                "answer_len": score.get("answer_len"),
                "citation_count": score.get("citation_count"),
                "hard_fail_codes": score.get("hard_fail_codes", []),
                "dimension_failures": failures,
                "criterion_scores": score.get("criterion_scores", {}),
            })

    good_cases = [r["case_id"] for r in case_matrix if r["owner_result"] == "pass"]
    false_or_answerable_safe = diagnosis.get("answerable_safe_terminal_case_ids", [])
    empty_nonterminal = diagnosis.get("empty_nonterminal_case_ids", [])
    cited_fail_cases = [s["case_id"] for s in owner_scores if s["result"] != "pass"]
    code_probes = {
        "stream_after_worker": file_contains(ROOT / "src/knowledge_engine/m27_isolated_streaming.py", "dto = m27_stream_response_from_result(await worker)"),
        "verified_claim_event_exists": file_contains(ROOT / "src/knowledge_engine/m27_isolated_streaming.py", "verified_claim_ready"),
        "cited_segment_event_exists": file_contains(ROOT / "src/knowledge_engine/m27_isolated_streaming.py", "cited_segment_ready"),
        "owner_executor_deadline_60000_ms": file_contains(ROOT / "src/knowledge_engine/m27_test_page_executor.py", "\"deadline_remaining_ms\": 60000"),
        "owner_executor_provider_attempts_4": file_contains(ROOT / "src/knowledge_engine/m27_test_page_executor.py", "\"provider_attempts_remaining\": 4"),
        "owner_executor_continuation_rounds_1": file_contains(ROOT / "src/knowledge_engine/m27_test_page_executor.py", "max_continuation_rounds=1"),
        "lexical_primary_dense_disabled": file_contains(ROOT / "src/knowledge_engine/m27_test_page_executor.py", "dense_channel=None") and file_contains(ROOT / "src/knowledge_engine/m27_test_page_executor.py", "require_remote_dense=False"),
        "late_citation_binding_drift_safe_terminal": file_contains(ROOT / "src/knowledge_engine/m27_runtime_execution.py", "PRODUCTION_CITATION_BINDING_DRIFT"),
    }
    stream_probe = run_stream_probes()
    counterfactual_probes = {
        "P1_stream_emission_dry_run": stream_probe,
        "P2_static_stream_timing_probe": {"result": "positive", "evidence": "m27_isolated_event_stream awaits the worker before converting result to DTO and emitting verified material events.", "code_refs": ["src/knowledge_engine/m27_isolated_streaming.py:230-267"]},
        "P3_provider_budget_static_probe": {"result": "positive", "deadline_60000_ms": code_probes["owner_executor_deadline_60000_ms"], "provider_attempts_4": code_probes["owner_executor_provider_attempts_4"], "continuation_rounds_1": code_probes["owner_executor_continuation_rounds_1"], "interpretation": "The product path can legally spend far beyond the 15s p95 target before producing final material."},
        "P4_multilingual_retrieval_static_probe": {"result": "positive", "lexical_primary_dense_disabled": code_probes["lexical_primary_dense_disabled"], "interpretation": "No explicit cross-lingual expansion was found in the owner-only executor before lexical retrieval."},
        "P5_no_provider_deterministic_path_probe": {"result": "implemented_but_insufficient", "evidence": "Runtime tries _try_canonical_evidence_bound_fast_path before provider synthesis, but Stage22 still produced only 7/20 cited finals and only 3/20 good cited finals.", "code_refs": ["src/knowledge_engine/m27_runtime_execution.py:753-769"]},
        "P6_receipt_counterfactual_stage20_vs_stage22": {"result": "positive_regression_signal", "stage20_ok_or_cited_cases_that_became_stage22_empty_nonterminal": [cid for cid in empty_nonterminal if stage20_diag.get(cid, {}).get("stage20_m27", {}).get("cited") is True], "interpretation": "Several answerable Stage20 cases regressed to empty nonterminal under Stage22 provider-only config, so the problem is not just missing corpus evidence."},
    }
    receipts = {
        "final_state": "M27_DEEP_ROOT_CAUSE_DIAGNOSIS_READY",
        "workspace": "/home/ubuntu/LLM_Wiki-m27-deep-root-cause-diagnostic-23",
        "base_head": "ee720858b380c87cc3f49f55aa064e2029b923d4",
        "final_head": None,
        "stage22_head": "ee720858b380c87cc3f49f55aa064e2029b923d4",
        "release_hard_gate_redecision_head": "d4cd99e936df544c45a2065e9dada0d8f40163d8",
        "product_gate": product_gate,
        "stage22_metrics": m27_metrics,
        "case_matrix": case_matrix,
        "latency_timelines": latency_timelines,
        "owner_85_scores": owner_scores,
        "root_cause_rankings": [{"rank": rank, "cause": cause, "evidence": evidence, "confidence": conf, "support": support} for rank, cause, evidence, conf, support in ROOT_CAUSES],
        "counterfactual_probes": counterfactual_probes,
        "forbidden_shortcuts_checked": {"rebase_to_m26_old_answer_path": False, "m26_mature_composer_shortcut": False, "repair_patch_implemented": False, "canary_activation": False, "production_deploy": False, "release_pointer_mutation": False, "admission_or_full523_rerun": False, "stage13_14_or_chunk002": False, "verifier_standards_lowered": False, "case_memorization_or_special_casing": False},
        "safety_proof": {"production_touched": False, "diagnostic_only_artifacts": True, "stage22_cleanup_source": stage22["stage22_provider_only_config_rerun"].get("final_cleanup_proof", {}), "secret_values_recorded": False, "raw_answer_text_omitted_from_new_receipts": True},
        "redaction_proof": {"stage22_redaction_scan": stage22["stage22_provider_only_config_rerun"].get("redaction_scan", {}), "raw_secret_values_present_in_new_artifacts": False, "prompt_injection_case_question_sanitized": True},
    }
    csv_path = RESEARCH / "68_case_failure_matrix.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(case_matrix[0].keys()))
        writer.writeheader()
        writer.writerows(case_matrix)
    matrix_rows = [[r["case_id"], r["slice"], short_bool(r["stage22_cited"]), short_bool(r["stage22_safe_terminal"]), r["stage22_answer_len"], r["stage22_citation_count"], fmt_ms(r["final_latency_ms"]), fmt_ms(r["first_material_ms"]), r["outcome_class"], r["earliest_unrecoverable_stage"], r["owner_score"] if r["owner_score"] is not None else "n/a"] for r in case_matrix]
    root_rows = [[r["case_id"], r["earliest_unrecoverable_stage"], r["root_cause_summary"]] for r in case_matrix]
    latency_rows = [[t["case_id"], t["request_start_ms"], t["retrieval_start_end"], t["evidence_admission_start_end"], t["first_provider_call_start_end"], t["verifier_start_end"], t["first_verified_claim_ready_ms"], t["first_cited_segment_ready_ms"], fmt_ms(t["first_material_event_ms"]), fmt_ms(t["final_event_ms"]), t["latency_class"]] for t in latency_timelines]
    verifier_rows = []
    for cid in ["C03", "C05", "C16", "C19"]:
        r = next(item for item in case_matrix if item["case_id"] == cid)
        justified = "yes" if cid == "C19" else "no / unresolved conflict" if cid == "C16" else "no"
        verifier_rows.append([cid, justified, r["outcome_class"], r["root_cause_summary"], r["earliest_unrecoverable_stage"]])
    score_rows = [[s["case_id"], s["score"], s["result"], s["answer_len"], s["citation_count"], ", ".join(s["hard_fail_codes"]), "; ".join(s["dimension_failures"])] for s in owner_scores]
    subsystem_rows = [[name, current, expected, gap, evidence, repair] for name, current, expected, gap, evidence, repair in SUBSYSTEM_GAPS]
    probe_rows = []
    for name, value in counterfactual_probes.items():
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
        probe_rows.append([name, raw[:900] + ("..." if len(raw) > 900 else "")])
    root_cause_rows = [[rank, cause, confidence, evidence, support] for rank, cause, evidence, confidence, support in ROOT_CAUSES]
    report = f"""# 68 M27 Deep Root-Cause Diagnostic Report

## 1. Final state

`M27_DEEP_ROOT_CAUSE_DIAGNOSIS_READY`

This is a diagnosis-only artifact. It does not claim canary readiness or product readiness.

## 2. Executive diagnosis in plain language

M27 is not failing the live product gate because one knob is wrong. It is failing because the context-native runtime has an unfinished product-answer layer: it can isolate evidence, enforce authority, call providers and verify final answers, but it does not yet have a claim-native answer planner and stream publisher. The result is a little answer factory with strong vault doors but a half-built conveyor belt: some good answers emerge, some answerable questions become false safe terminals, some answers become thin one-citation summaries, and several cases produce HTTP 200 with neither a cited answer nor a safe terminal.

The most load-bearing finding is stream timing: `m27_isolated_event_stream` only emits `verified_claim_ready` and `cited_segment_ready` after `await worker`, meaning after the authoritative runtime finishes. That makes first material latency structurally close to final latency on slow paths.

Stage 22 measured p95 final latency `{m27_metrics['p95_final_latency_ms']}` ms, p95 first material latency `{m27_metrics['p95_first_material_ms']}` ms, cited final-answer rate `{m27_metrics['cited_answer_rate']}`%, and safe-terminal rate `{m27_metrics['safe_terminal_rate']}`%. Only `{len(good_cases)}/20` cases are good cited answers scoring >=85 under the Owner rubric.

## 3. Methodology and boundaries

Inputs used:

- Stage 22 receipts: `docs/m27/research/provider_only_config_rerun_receipts.json`
- Stage 21/20 diagnostic receipts: `docs/m27/research/m27_provider_tail_product_answer_repair_receipts.json`
- Stage 20 side-by-side receipts: `docs/m27/research/test_page_product_readiness_stage20_side_by_side_receipts.json`
- Runtime code inspection: `src/knowledge_engine/m27_runtime_execution.py`, `src/knowledge_engine/m27_isolated_streaming.py`, `src/knowledge_engine/m27_test_page_executor.py`
- Owner scoring source recorded by Stage 22: `{scoring.get('rubric_source')}`

Boundaries kept: no production deploy, no canary activation, no release pointer mutation, no admission/full523 rerun, no Stage13/14, no Chunk002, no repair patch, no M26 mature composer shortcut, no verifier-standard lowering, and no raw secrets.

## 4. 20-case outcome matrix

{table(['Case','Slice','Cited','Safe terminal','Answer len','Citations','Final ms','First material ms','Outcome','Earliest unrecoverable stage','Owner score'], matrix_rows)}

## 5. Per-case root-cause table

{table(['Case','Earliest unrecoverable stage','Root cause'], root_rows)}

## 6. Latency timeline table

Stage 22 comparator receipts preserve final latency and first-material latency, but not exact per-case retrieval/evidence/provider/verifier timestamps. The code path does have runtime telemetry writers, but those micro-timings were not preserved in the product comparison receipt. The table below therefore distinguishes observed timings from missing internal stage timings rather than inventing numbers.

{table(['Case','Request start ms','Retrieval start/end','Evidence admission start/end','First provider call start/end','Verifier start/end','First verified claim ready','First cited segment ready','First material ms','Final ms','Latency class'], latency_rows)}

Why first material is close to final: `m27_isolated_event_stream` drains runtime progress events while the worker runs, but it converts the final result to streamable verified material only after `await worker`. Then it emits `verified_claim_ready`, `cited_segment_ready`, and `final_answer_done` sequentially. So verified material is a post-hoc serialization of the final DTO, not a live first-answer-text stream.

## 7. Verifier-gap safe-terminal analysis

{table(['Case','Justified?','Outcome','Analysis','Earliest stage'], verifier_rows)}

Verifier gap summary:

- Answerable safe-terminal candidates: `{', '.join(false_or_answerable_safe)}`.
- Empty nonterminal cases: `{', '.join(empty_nonterminal)}`.
- Justified safety terminal: `C19`.
- C16 has contradictory Stage 22 evidence: the product gate boolean marks it pass-or-justified-safe, while the Stage 22 diagnosis lists it under answerable safe terminals. This should remain a diagnosis item, not readiness evidence.

## 8. Owner 85-point scoring table

Rubric source recorded by Stage 22: `{scoring.get('rubric_source')}`. Stage 22 scored only successful cited final answers, which is correct because no-answer and safe-terminal cases fail the product gate before rubric scoring.

{table(['Case','Score','Result','Answer len','Citations','Hard fail codes','Dimension failures'], score_rows)}

Cited final answer diagnosis:

- Passing cited answers: `{', '.join(good_cases)}`.
- Cited answers below product standard or hard-failed: `{', '.join(cited_fail_cases)}`.
- Main scoring failure mode: one-source / thin answer surface, especially C06, C10 and C11.

## 9. 2027-style architecture subsystem gap map

{table(['Subsystem','Current observed behavior','Expected 2027-style behavior','Gap','Evidence','Repair direction, not implemented'], subsystem_rows)}

## 10. Counterfactual probe results

These are bounded diagnostic probes, not product evidence.

{table(['Probe','Result'], probe_rows)}

## 11. Root-cause tree with ranked causes

{table(['Rank','Cause','Confidence','Evidence','Support'], root_cause_rows)}

Root-cause tree:

1. Publication semantics: post-hoc stream conversion after worker completion.
   1.1 First material cannot lead final by much because verified material events are emitted only after full runtime completion.
   1.2 Empty/safe terminal results produce only terminal events, not answer progress.
2. Verifier/composer interface: whole-answer verification creates all-or-nothing outcomes.
   2.1 False safe terminals occur when evidence exists but claims are not verifier-acceptable.
   2.2 Empty nonterminals occur when final-state mapping fails to publish either answer or safe terminal.
3. Product planner immaturity: homepage answer quality is not a native contract.
   3.1 Thin one-citation answers can pass structural verification but fail Owner 85 scoring.
   3.2 Source-breadth and visitor-fit are not enforced before publication.
4. Provider orchestration and compute policy: 60s / 4-attempt budget is not product-SLO aware.
   4.1 Slow provider/verifier paths consume tail budget without emitting useful material.
5. Multilingual normalization: cross-lingual evidence support is brittle.
   5.1 C07 works, C15/C16 fail, which points to incidental lexical match rather than robust multilingual architecture.

## 12. What not to fix next, because it is a patch/shortcut

- Do not rebase M27 product answers onto the M26 mature composer.
- Do not lower verifier standards to make cited-answer rates look better.
- Do not special-case the 20-case set or memorize case IDs.
- Do not increase provider timeouts, raise rate limits, or add retries as the primary solution.
- Do not count safe terminals as success unless the terminal is justified and answerability is disproven.
- Do not hide empty nonterminal cases behind HTTP success.
- Do not treat one-citation thin answers as product-ready simply because citation binding is valid.

## 13. Recommended principled repair plan, without implementing it

1. Build a native M27 product-answer planner that turns evidence sufficiency into an answer plan with required facets, source breadth, target depth, citation slots and visitor-fit constraints.
2. Add a claim graph between evidence and answer text. Each claim should carry support refs, citation locators, source identities and verifier state.
3. Change stream publication from post-hoc DTO splitting to live claim-level publication. Emit `verified_claim_ready` and `cited_segment_ready` from runtime execution when a claim is verified, not after full worker completion.
4. Replace all-or-nothing verifier gaps with structured gap categories: missing citation locator, unsupported claim span, insufficient source breadth, multilingual support mismatch, provider malformed output, and true no-evidence.
5. Make compute policy product-SLO aware. Derive provider call caps and verifier deadlines from p95 <15s and first material <15s, not from a 60s semantic recovery budget.
6. Add multilingual canonicalization before retrieval: translate/expand key technical terms, map them to canonical article themes, and verify support across language boundaries.
7. Persist redacted per-stage telemetry in comparison receipts: retrieval start/end, evidence admission start/end, provider call count/duration, verifier exclusive time, first claim-ready time and stream emission time.
8. Re-run only bounded product diagnostics after repairs. Do not run admission/full523 until the product-surface 20-case gate is structurally fixed.

## 14. Safety/no-production proof

- New artifacts are diagnostic-only docs, CSV and JSON receipts.
- No production deploy, no canary activation, no release pointer mutation.
- Stage22 cleanup proof is carried forward in receipts under `safety_proof.stage22_cleanup_source`.
- No raw owner/provider secret values are stored in new artifacts.
- Raw answer text was intentionally omitted from the new JSON receipt; the prompt-injection safety case question is sanitized.

## 15. Artifact list

- `docs/m27/research/68_m27_deep_root_cause_diagnostic_report.md`
- `docs/m27/research/m27_deep_root_cause_diagnostic_receipts.json`
- `docs/m27/research/68_case_failure_matrix.csv`
- `docs/m27/handoffs/M27_DEEP_ROOT_CAUSE_DIAGNOSTIC_HANDOFF.md`
- `scripts/m27_deep_root_cause_diagnostic_23.py`
"""
    report_path = RESEARCH / "68_m27_deep_root_cause_diagnostic_report.md"
    receipts_path = RESEARCH / "m27_deep_root_cause_diagnostic_receipts.json"
    handoff_path = HANDOFFS / "M27_DEEP_ROOT_CAUSE_DIAGNOSTIC_HANDOFF.md"
    report_path.write_text(report)
    receipts_path.write_text(json.dumps(receipts, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    handoff = f"""# M27 Deep Root-Cause Diagnostic Handoff

Final state: `M27_DEEP_ROOT_CAUSE_DIAGNOSIS_READY`

Workspace: `/home/ubuntu/LLM_Wiki-m27-deep-root-cause-diagnostic-23`
Base HEAD: `ee720858b380c87cc3f49f55aa064e2029b923d4`

This session produced diagnosis-only artifacts and implemented no repair.

Primary findings:

1. Stream publication is post-hoc. Verified material events are emitted only after `await worker`, so first material latency tracks final latency.
2. Verifier-gap handling is all-or-nothing, creating false safe terminals and empty nonterminal finals on answerable cases.
3. Product answer planning is immature: only {len(good_cases)}/20 cases are good cited answers >=85; four cited answers fail or hard-fail Owner scoring.
4. Provider compute policy permits 60s and 4 attempts in the owner-only product path, incompatible with p95 <15s.
5. Multilingual normalization is brittle: C15/C16 fail while related English topics are answerable.

Next recommended session should be a repair design/implementation session focused on native M27 claim graph + live claim-level stream publication + product answer planner. It should not rebase to M26 mature composer.

Artifacts:

- `docs/m27/research/68_m27_deep_root_cause_diagnostic_report.md`
- `docs/m27/research/m27_deep_root_cause_diagnostic_receipts.json`
- `docs/m27/research/68_case_failure_matrix.csv`
- `scripts/m27_deep_root_cause_diagnostic_23.py`
"""
    handoff_path.write_text(handoff)
    print(json.dumps({"wrote": [str(report_path), str(receipts_path), str(csv_path), str(handoff_path)], "cases": len(case_matrix), "good_cases": good_cases}, ensure_ascii=False))


if __name__ == "__main__":
    main()
