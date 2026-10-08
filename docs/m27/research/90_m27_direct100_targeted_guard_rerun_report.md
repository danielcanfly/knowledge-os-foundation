# Stage 30J Direct100 Targeted Guard Rerun

## Final decision
`M27_DIRECT100_TARGETED_GUARD_RERUN_FAIL_PRODUCT_QUALITY`

## Scope
- Direct isolated candidate endpoint: `http://127.0.0.1:18080/v1/answers/stream`
- Replaced only `m27-owner-canary-28` on `127.0.0.1:18080`.
- No owner-only route certification, public rollout, release pointer mutation, Nginx modification, production M26 restart/rebuild, test backend restart/rebuild, admission/full523, Stage13/14, or Chunk002.
- Owner-only route certification remains pending and must not be inferred from this result.

## Build/runtime identity
- Image: `knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e`
- Code HEAD: `2dc7990efcd9a7d80d24bac740349d47e99dc689`
- Previous rollback image: `knowledge-engine:m27-semantic-publication-gate-30g-67ca9928`

## Dataset provenance
```json
{
  "stage30h_cases_csv": "0c751a55e746c47fd2f2bbcb461f8485e25f3baba4c444f9a24cc59dd24ccdf8",
  "stage30i_triage_matrix_csv": "a00ed755823d9e39bf485e3a6722c8c911256846db2c4bc72b07bd7367f78cd5",
  "frozen_population_json": "6d58e4b346742de95368d2e132a460e2f4e6453d059afe1f50255bc904d9a87d"
}
```

## Targeted 9 metrics
```json
{
  "cases": 9,
  "http_success": 9,
  "answerable_cases": 1,
  "answerable_cited_final": 0,
  "expected_safe_cases": 8,
  "expected_safe_correct": 8,
  "missed_safe_terminal": 0,
  "false_safe_terminal": 1,
  "empty_nonterminal": 0,
  "thin_cited_answer": 0,
  "topic_contamination": 0,
  "semantic_bad_publish": 0,
  "obligation_satisfied": 9,
  "p50_final_latency_ms": 3308.432,
  "p95_final_latency_ms": 4838.25,
  "p50_first_material_ms": 3307.849,
  "p95_first_material_ms": 4837.797,
  "first_material_count": 9,
  "no_m26_mature_composer_delegation": true
}
```

## Direct100 metrics
```json
{
  "cases": 100,
  "http_success": 100,
  "answerable_cases": 87,
  "answerable_cited_final": 79,
  "expected_safe_cases": 13,
  "expected_safe_correct": 13,
  "missed_safe_terminal": 0,
  "false_safe_terminal": 8,
  "empty_nonterminal": 0,
  "thin_cited_answer": 0,
  "topic_contamination": 0,
  "semantic_bad_publish": 0,
  "obligation_satisfied": 100,
  "p50_final_latency_ms": 3541.137,
  "p95_final_latency_ms": 5955.582,
  "p50_first_material_ms": 3540.121,
  "p95_first_material_ms": 5954.337,
  "first_material_count": 100,
  "no_m26_mature_composer_delegation": true
}
```

## Artifacts
- `docs/m27/research/90_m27_direct100_targeted_9case_results.csv`
- `docs/m27/research/m27_direct100_targeted_guard_rerun_receipts.json`
- `docs/m27/research/90_m27_direct100_targeted_100case_results.csv` if Direct100 executed
- `docs/m27/research/90_m27_direct100_targeted_guard_failures.csv` if failures remained
- `docs/m27/handoffs/M27_DIRECT100_TARGETED_GUARD_RERUN_HANDOFF.md`
