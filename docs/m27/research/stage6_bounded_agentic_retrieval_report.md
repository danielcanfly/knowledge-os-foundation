# M27 Stage 6 Bounded Agentic Retrieval Report

Date: 2026-10-03
Branch: `m27/stage6-bounded-agentic-retrieval`
Base: `38d8cbf1`
Candidate baseline commit: `d16cadcd`

## Scope

Stage 6 introduces bounded, evidence-gap-driven retrieval expansion for the isolated M27 runtime only.

It is not an open-ended agent loop. It keeps the existing M26 retrieval/selection/strengthening/compiler/verifier/publication path authoritative.

## Files changed

```text
src/knowledge_engine/m27_bounded_agentic_retrieval.py
src/knowledge_engine/m27_bounded_agentic_retrieval_runtime.py
src/knowledge_engine/m26_aq_semantic_contract.py
tests/test_m27_bounded_agentic_retrieval.py
tests/test_m27_bounded_agentic_retrieval_runtime.py
tests/test_m27_bounded_agentic_retrieval_wiring.py
docker-compose.m27-isolated.yml
docs/m27/research/stage6_bounded_agentic_retrieval_report.md
```

## Runtime boundary

Stage 6 runs only when both flags are true:

```text
M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED=true
M27_ISOLATED_RUNTIME=true
```

If the feature flag is off, the canonical M26 entrypoint does not call the Stage 6 helper at all.

If the feature flag is requested but the isolated marker is absent, the canonical M26 entrypoint also does not call the Stage 6 helper.

The isolated compose file sets:

```text
M27_ISOLATED_RUNTIME=true
M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED=false
```

so Stage 6 remains default-off even in the isolated runtime.

## Retrieval flow

Canonical flow:

```text
M26 retrieval
  -> M26 _select_evidence
  -> M26 _strengthen_evidence
  -> existing facet support classification
  -> if material gap remains and budgets allow:
       one deterministic gap query
       one additional M26 lexical/dense retrieval
       merge candidate pools
       M26 _select_evidence again
       M26 _strengthen_evidence again
       adopt only if material missing set strictly shrinks
  -> existing ContextCompiler / verifier / publication
```

Maximum retrieval rounds: 2.

No LLM query rewrite is used. The gap query is built deterministically from already-derived semantic requirement evidence terms.

## Adoption rule

Second-round evidence is adopted only if:

```text
missing_after is a strict subset of missing_before
```

If second-round retrieval does not improve the material gap set, the runtime returns the original Round 1 evidence and endpoint proof.

This prevents citation churn and prevents trading one material gap for another.

## Budget rule

The second round requires:

```text
deadline_remaining_ms >= post_retrieval_reserve_ms + 1500ms
```

The canonical wiring passes:

```text
FAST_RETRY_MIN_BUDGET_MS
+ SEMANTIC_CLOSURE_MIN_BUDGET_MS
+ FINAL_VALIDATION_MIN_BUDGET_MS
= 7000ms
```

So the second retrieval round requires at least 8500ms remaining.

## Identity and merge rule

Stable identity dedupe uses, in order:

```text
section_id
passage_id
evidence_id
edge_id
id
source_id/source_identity + locator_id/uri
```

If an item has no stable identity, Stage 6 preserves both items instead of fabricating an opaque identity or deduping by shape/text.

## Privacy

The Stage 6 audit is body-free and query-free. It contains:

```text
rounds_executed
second_round_executed
second_round_adopted
decision_code
missing_before requirement ids
missing_after requirement ids
```

It does not contain raw query, raw answer, evidence body, source body, provider prompt, credentials, secrets, or environment values.

## Tests

Focused Stage 6 tests after identity fix:

```text
23 passed
Ruff: All checks passed
```

Combined safe gate:

```text
192 passed, 1 warning
Ruff M27: All checks passed
Ruff patched M26 file with known pre-existing F841 ignored: All checks passed
```

The ignored F841 is pre-existing in `m26_aq_semantic_contract.py` and not introduced by Stage 6.

## Retrieval-only full523 evaluation

Path:

```text
/home/ubuntu/m27-stage6-eval/retrieval-full523-v1
```

Question population SHA:

```text
8ebae1ae155433535e4bf461e954b809b81828459b4711765aab554554d63219
```

Summary:

```text
population: 523
retrieval_eligible: 523
collector_failures: 0
round2_executed: 35
round2_adopted: 2
round2_adoption_rate_of_executed: 0.057143
round1_p50_ms: 2003.0
round1_p95_ms: 5109.0
total_retrieval_p50_ms: 2094.0
total_retrieval_p95_ms: 5893.9
max_total_retrieval_ms: 22982
```

Decision codes:

```text
NO_MATERIAL_GAP: 486
NO_GAP_IMPROVEMENT: 33
GAP_IMPROVED: 2
DEADLINE_BUDGET_BLOCKED: 2
```

Adopted cases:

```text
PASS024
PASS186
```

The full523 retrieval-only run was completed in chunks because the SSH transport consistently terminated foreground child processes at approximately 217 seconds. The artifact was de-duplicated after an earlier duplicate-run overlap; the original duplicate-contaminated rows were preserved at:

```text
/home/ubuntu/m27-stage6-eval/retrieval-full523-v1/rows.sanitized.jsonl.duplicate-backup
```

The final rows file is 523 unique contiguous cases.

## Live final-answer sanity check

Path:

```text
/home/ubuntu/m27-stage6-eval/adopted2-off
/home/ubuntu/m27-stage6-eval/adopted2-on
```

Cases:

```text
PASS024
PASS186
```

OFF:

```text
cited_final_answers: 0 / 2
safe_abstentions: 2
unsupported_claims: 0
provider_calls_total: 3
```

ON:

```text
cited_final_answers: 1 / 2
safe_abstentions: 1
unsupported_claims: 0
provider_calls_total: 4
```

PASS186 improved from safe abstention to cited answer. PASS024 remained safe abstention.

A separate 19-case live subset was marked invalid because live provider execution hung before completion. That invalid run was stopped and preserved separately as an external provider/harness issue, not used as a gate result.

## Behavior impact

Stage 6 OFF:

```text
no Stage 6 helper call
no retrieval behavior change
no answer behavior change
no verifier behavior change
no publication behavior change
```

Stage 6 ON and isolated:

```text
at most one extra retrieval round
no provider call added by retrieval itself
same selector
same strengthener
same ContextCompiler
same verifier
same citation gate
same safe abstention path
```

## Production safety

No production pointer, Qdrant alias, production sqlite, release promotion, or production container update was performed by Stage 6 work.

## Remaining risks

1. Full live final-answer 523 gate was not completed because the live provider path showed hang behavior in the subset runner.
2. Retrieval-only full523 shows narrow gains: 2 adopted improvements out of 523, so Stage 6 should remain isolated/default-off until a stable live final-answer harness validates end-to-end benefit.
3. The audit is present in the canonical endpoint proof when Stage 6 runs, but the external sanitized subset runner did not reliably collect audit rows from all response shapes.
4. The max retrieval-only case was 22982ms. This is a retrieval-only outlier and should be studied before any production-facing enablement.

## Verdict

```text
STAGE6_IMPLEMENTATION: READY_FOR_MASTER_REVIEW
PRODUCTION_ENABLEMENT: NOT_READY
```

Stage 6 is suitable for Master integration as default-off isolated capability. It is not suitable for production enablement or release promotion without a future stable full live final-answer 523 gate.
