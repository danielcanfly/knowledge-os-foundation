# 69 M27 2027 Agent Product Gate Repair Report

Final state: `M27_2027_AGENT_PRODUCT_GATE_READY_FOR_CANARY_CONSIDERATION`

## Scope

This session repaired the Stage 23 root causes with an M27-native product answer layer, not an M26 mature composer wrapper. It did not deploy production, activate canary, mutate release pointers, change public routing, restart/rebuild production M26, write production datastores, rerun admission/full523, or run Stage13/14/Chunk002.

## Architecture repair

Implemented / wired:

- M27-native product answer state machine and gap taxonomy in `src/knowledge_engine/m27_agent_product_runtime.py`.
- Runtime-native claim graph before final DTO.
- Live `verified_claim_ready` / `cited_segment_ready` stream publication.
- Structured verifier gaps including insufficient breadth, locator gaps, unsupported span, citation drift, multilingual mismatch, true no evidence, unsafe/private prompt, underspecified query, thin surface, and SLO budget exhaustion.
- Product answer planner with source-breadth gate and broad homepage question rules.
- SLO-aware product path with provider calls avoided in the hot path.
- Multilingual canonicalization before retrieval/support matching.
- Redacted micro-timeline fields in receipts.

The direct Stage25 product path uses the pinned read-only test-page production snapshot and M27 claim-native planner after retrieval. It does not call `synthesize_and_verify` or import/delegate to the M26 mature answer composer.

## Same-run bounded 20-case result

M26 baseline metrics:

```json
{
  "cases": 20,
  "cited_answer_rate": 88.24,
  "http_success_rate": 85.0,
  "p50_final_latency_ms": 2031.543,
  "p50_first_material_ms": 2030.45,
  "p95_final_latency_ms": 11495.034,
  "p95_first_material_ms": 10421.557,
  "rate_429": 0.0,
  "safe_terminal_rate": 5.88,
  "timeout_or_error_rate": 15.0
}
```

M27 repaired candidate metrics:

```json
{
  "cases": 20,
  "cited_answer_rate": 90.0,
  "http_success_rate": 100.0,
  "p50_final_latency_ms": 181.094,
  "p50_first_material_ms": 179.957,
  "p95_final_latency_ms": 9136.395,
  "p95_first_material_ms": 9124.25,
  "rate_429": 0.0,
  "safe_terminal_rate": 10.0,
  "timeout_or_error_rate": 0.0
}
```

Strict product metrics:

```json
{
  "answerable_cases": 18,
  "answerable_final_answer_success_rate": 100.0,
  "answerable_success": 18,
  "browser_use_warning_case_cleared": true,
  "c15_status": {
    "answer_len": 1571,
    "case_id": "C15",
    "citation_count": 4,
    "cited_answer": true,
    "event_names": [
      "request_started",
      "retrieval_started",
      "retrieval_ready",
      "evidence_ready",
      "answer_plan_ready",
      "claim_graph_ready",
      "claim_verification_started",
      "verified_claim_ready",
      "citation_bound",
      "cited_segment_ready",
      "stream_publishable",
      "final_answer_done"
    ],
    "expected_safe_terminal": false,
    "final_latency_ms": 320.408,
    "first_material_latency_ms": 318.532,
    "gap_taxonomy": [],
    "justified_safe_terminal": false,
    "m27_http_ok": true,
    "m27_http_status": 200,
    "micro_timeline": {
      "answer_planning_end_ms": null,
      "answer_planning_start_ms": null,
      "claim_graph_end_ms": null,
      "claim_graph_start_ms": null,
      "evidence_admission_end_ms": null,
      "evidence_admission_start_ms": null,
      "final_emitted_ms": 320.408,
      "first_citation_bound_ms": 318.532,
      "first_cited_segment_ready_ms": 318.532,
      "first_claim_verification_end_ms": null,
      "first_claim_verification_start_ms": null,
      "first_material_emitted_ms": 318.532,
      "first_verified_claim_ready_ms": 318.532,
      "provider_call_count": 0,
      "provider_total_duration_ms": 0.0,
      "retrieval_end_ms": null,
      "retrieval_start_ms": 0.0,
      "verifier_exclusive_duration_ms": 0.0
    },
    "owner_hard_fail_codes": [],
    "owner_rubric_score": 94,
    "safe_terminal": false,
    "slice": "multilingual",
    "source_breadth_status": "sufficient",
    "strict_product_success": true
  },
  "c16_status": {
    "answer_len": 1262,
    "case_id": "C16",
    "citation_count": 4,
    "cited_answer": true,
    "event_names": [
      "request_started",
      "retrieval_started",
      "retrieval_ready",
      "evidence_ready",
      "answer_plan_ready",
      "claim_graph_ready",
      "claim_verification_started",
      "verified_claim_ready",
      "citation_bound",
      "cited_segment_ready",
      "stream_publishable",
      "final_answer_done"
    ],
    "expected_safe_terminal": false,
    "final_latency_ms": 206.754,
    "first_material_latency_ms": 205.379,
    "gap_taxonomy": [],
    "justified_safe_terminal": false,
    "m27_http_ok": true,
    "m27_http_status": 200,
    "micro_timeline": {
      "answer_planning_end_ms": null,
      "answer_planning_start_ms": null,
      "claim_graph_end_ms": null,
      "claim_graph_start_ms": null,
      "evidence_admission_end_ms": null,
      "evidence_admission_start_ms": null,
      "final_emitted_ms": 206.754,
      "first_citation_bound_ms": 205.379,
      "first_cited_segment_ready_ms": 205.379,
      "first_claim_verification_end_ms": null,
      "first_claim_verification_start_ms": null,
      "first_material_emitted_ms": 205.379,
      "first_verified_claim_ready_ms": 205.379,
      "provider_call_count": 0,
      "provider_total_duration_ms": 0.0,
      "retrieval_end_ms": null,
      "retrieval_start_ms": 0.0,
      "verifier_exclusive_duration_ms": 0.0
    },
    "owner_hard_fail_codes": [],
    "owner_rubric_score": 94,
    "safe_terminal": false,
    "slice": "multilingual",
    "source_breadth_status": "sufficient",
    "strict_product_success": true
  },
  "empty_nonterminal_count": 0,
  "false_safe_terminal_count": 0,
  "justified_safe_terminal_cases": 2,
  "median_successful_owner_rubric_score": 93.0,
  "min_successful_owner_rubric_score": 87,
  "thin_cited_answer_count": 0
}
```

## Gate decision

- p95 final latency `<15s`: PASS (`9136.395` ms).
- p95 first-material latency `<15s`: PASS (`9124.25` ms).
- Answerable final-answer success `>95%`: PASS (`18/18` = `100.0%`).
- Successful final answers Owner-rubric proxy `>=85`: PASS (min `87`).
- False safe-terminal rate: PASS (`0`).
- Empty nonterminal: PASS (`0`).
- Thin cited answer counted as success: PASS (`0`).
- Browser Use warning case: PASS (C01 cited answer).
- C15/C16 multilingual cases: PASS (both cited answers).
- Same-run no-worse-than M26 baseline: PASS.

## Validation

- compileall changed files: `0`.
- compileall src/scripts/tests: `0`.
- git diff --check: `0`.
- pytest unavailable on host; live container dependency/runtime validation came from the same bounded 20-case rerun.
- ruff unavailable on host.

## Artifacts

- `docs/m27/research/m27_2027_agent_product_gate_repair_receipts.json`
- `docs/m27/research/69_case_micro_timeline.csv`
- `docs/m27/research/69_m27_2027_agent_product_gate_repair_report.md`
- `docs/m27/handoffs/M27_2027_AGENT_PRODUCT_GATE_REPAIR_HANDOFF.md`
