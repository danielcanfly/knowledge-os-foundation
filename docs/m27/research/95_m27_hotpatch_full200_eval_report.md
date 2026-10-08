# Stage 30N Hotpatch Full Frozen 200 Eval

## Decision
`M27_HOTPATCH_FULL200_FAIL_QUALITY`

## Gates
```json
{
  "success_rate": 1.0,
  "success_gate": true,
  "latency_gate": true,
  "quality_gate": false,
  "quality_score_proxy": 89.8,
  "quality_score_proxy_boundary": "derived from product-quality harness flags; not independent semantic judge score",
  "answerable_required_for_95pct": 167
}
```

## Metrics
```json
{
  "cases": 200,
  "http_success": 200,
  "answerable_cases": 175,
  "answerable_cited_final": 175,
  "expected_safe_cases": 25,
  "expected_safe_correct": 25,
  "missed_safe_terminal": 0,
  "false_safe_terminal": 0,
  "empty_nonterminal": 0,
  "thin_cited_answer": 0,
  "topic_contamination": 2,
  "semantic_bad_publish": 0,
  "obligation_satisfied": 198,
  "p50_final_latency_ms": 3440.433,
  "p95_final_latency_ms": 6238.586,
  "p50_first_material_ms": 3439.117,
  "p95_first_material_ms": 6237.497,
  "first_material_count": 200,
  "no_m26_mature_composer_delegation": true
}
```
