# Stage 30O Mixed Full523 Admission Runner

## Decision
`M27_MIXED_FULL523_ADMISSION_RUNNER_PASS`

## Boundaries
- Direct isolated candidate only: `127.0.0.1:18080`
- Production M26 unchanged.
- Owner-only route certification remains pending and must not be inferred from this result.

## Counts
```json
{
  "verified_cited_answer": 237,
  "safe_abstention": 52,
  "rejected_before_provider": 52,
  "budget_terminal": 26,
  "m26_invariant": 26,
  "governance_contract": 130
}
```

## Gates
```json
{
  "admission_gate_pass": true,
  "governance_gate_pass": true,
  "live_success_gate": true,
  "live_latency_gate": true,
  "quality_score_proxy": 100.0,
  "quality_score_proxy_boundary": "derived from admission/product-quality contract flags; not independent LLM judge score",
  "overall_pass": true
}
```

## Admission Metrics
```json
{
  "verified_answer_expected_count": 237,
  "verified_answer_cited_count": 237,
  "cited_final_answer_rate": 1.0,
  "safe_terminal_expected_count": 130,
  "safe_terminal_correct_count": 130,
  "safe_terminal_correctness": 1.0,
  "safe_abstention_correctness": 1.0,
  "drift_rejection_correctness": 1.0,
  "budget_terminal_correctness": 1.0,
  "unexpected_answer_on_safe_terminal_count": 0,
  "safe_terminal_missing_leakage_signal_count": 0,
  "feature_off_invariant": true,
  "production_no_mutation": true,
  "gate_pass": true
}
```

## Live Metrics
```json
{
  "live_executed_count": 341,
  "live_http_success": 341,
  "live_http_success_rate": 1.0,
  "live_failure_count": 0,
  "live_p95_latency_ms": 4933.967,
  "live_p95_first_material_ms": 4932.788
}
```
