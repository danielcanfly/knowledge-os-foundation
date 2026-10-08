# Stage 30H Direct Candidate 100-case Scale Evaluation

## Final decision
`M27_DIRECT_CANDIDATE_100_SCALE_EVAL_FAIL_PRODUCT_QUALITY`

## Scope and provenance
- Direct-candidate only: `http://127.0.0.1:18080/v1/answers/stream`
- Source: `pilot/m26/m26-pa-5-frozen-population.json` (200-case frozen M26 population; deterministic every-second-question by sorted question_id per stratum)
- Source SHA256: `6d58e4b346742de95368d2e132a460e2f4e6453d059afe1f50255bc904d9a87d`
- The source references an earlier accepted local release and may not exactly match the current M27 indexed corpus. This is a transfer diagnostic, not an M26 admission run.
- No owner route, Nginx or production path requested.
- Image: `knowledge-engine:m27-semantic-publication-gate-30g-67ca9928`
- Code commit: `67ca9928b54feb7cd81083313f845c264c565b37`
- Start/end unix seconds: 1791455435.7145395 / 1791455813.3591173

## Metrics
```json
{
  "cases": 100,
  "http_success": 100,
  "answerable_cases": 87,
  "answerable_cited_final": 86,
  "expected_safe_cases": 13,
  "expected_safe_correct": 5,
  "false_safe_terminal": 0,
  "missed_safe_terminal": 8,
  "empty_nonterminal": 0,
  "thin_cited_answer": 1,
  "topic_contamination_heuristic": 0,
  "semantic_bad_publish": 0,
  "p95_final_ms": 6305.318,
  "p95_first_material_ms": 6304.548
}
```

## Verification boundary
- Receipt-backed semantic publication checks are verified by the M27 provider. This script cannot independently judge all answer/topic correctness; keyword contamination is a risk detector, not semantic proof. If all numeric gates are green, decision remains BLOCKED_BY_HARNESS pending independent quality adjudication.
- No M26 mature composer delegation: True
- Owner-only route certification remains pending and must not be inferred from this result.
