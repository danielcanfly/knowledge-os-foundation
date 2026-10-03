# M27 Stage 4 ComputePolicy / Test-Time Compute Optimization Report

Date: 2026-10-03
Branch: `m27/stage4-compute-policy`
Base: `5a0c6cc7`

## 1. Files changed

Stage 4 changed only the Stage 4-owned surfaces:

```text
src/knowledge_engine/m27_compute_policy.py
src/knowledge_engine/m27_compute_policy_shadow.py
tests/test_m27_compute_policy.py
tests/test_m27_compute_policy_shadow.py
docs/m27/research/stage4_compute_policy_report.md
```

Not modified:

```text
src/knowledge_engine/m27_context_runtime_contracts.py
src/knowledge_engine/m26_aq_semantic_contract.py
src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py
src/knowledge_engine/m26_context_compiler.py
src/knowledge_engine/m26_public_api.py
src/knowledge_engine/m26_console_api.py
Stage 5 tool/read-only files
```

## 2. Existing M26 compute signals mapped

Stage 4 studied and preserves the existing `SemanticRoutingDecision` shape:

```text
route
reason
deadline_remaining_ms
minimum_budget_ms
provider_attempts_remaining
affordable
```

The source semantics remain M26-authoritative:

```text
affordable =
  deadline_remaining_ms >= minimum_budget_ms
  AND provider_attempts_remaining > 0
```

Existing M26 route budget constants observed:

```text
SOFT_DEADLINE_MS = 14500
FAST_RETRY_MIN_BUDGET_MS = 2500
SEMANTIC_CLOSURE_MIN_BUDGET_MS = 3500
CLAIM_WEAKENING_MIN_BUDGET_MS = 2000
FINAL_VALIDATION_MIN_BUDGET_MS = 1000
```

Existing M26 route minimum budgets observed:

```text
FAST_RETRY_ONCE:
  2500 + 3500 + 1000 = 7000 ms

SEMANTIC_CLOSURE / EVIDENCE_SLOT_REALIGNMENT:
  3500 + 1000 = 4500 ms

CLAIM_WEAKENING / CONTRADICTION_TRIAGE:
  2000 + 1000 = 3000 ms

other/default final validation:
  1000 ms
```

Stage 4 does not recompute or replace those M26 decisions. It first uses
`LegacyM26DeadlineBudgetAdapter`, then classifies the already-produced decision.

## 3. Exact RuleBasedComputePolicy semantics

`RuleBasedComputePolicy` is an observer/classifier, not a controller.

Flow:

```text
already-produced M26 SemanticRoutingDecision
  -> LegacyM26DeadlineBudgetAdapter
  -> canonical ComputeDecision raw legacy fields
  -> RuleBasedComputePolicy.classify()
  -> ComputePolicyObservation
```

The observation preserves:

```text
legacy route
legacy reason
deadline_remaining_ms
minimum_budget_ms
budget_headroom_ms
provider_attempts_remaining
affordable
shadow compute tier
shadow reason code
deadline budget class
provider budget class
provider attempt class
deadline pressure observed
shadow_only = true
authoritative = false
```

`budget_headroom_ms` is exactly:

```text
deadline_remaining_ms - minimum_budget_ms
```

when both existing raw signals are available. Otherwise it remains
`unavailable_in_stage1`.

Deadline budget class uses only the existing M26 route minimum:

```text
remaining <= 0                  -> EXHAUSTED
0 < remaining < minimum_budget -> CONSTRAINED
remaining >= minimum_budget    -> HEALTHY
missing signal                 -> UNAVAILABLE_IN_STAGE1
```

Provider budget class reuses the already-canonical
`ProviderAttemptClass` boundary rather than inventing a new call threshold:

```text
0 attempts       -> EXHAUSTED / NONE
1 attempt        -> CONSTRAINED / ONE
2+ attempts      -> HEALTHY / MULTIPLE
missing signal   -> UNAVAILABLE_IN_STAGE1
```

No provider attempt is allocated by this classification.

## 4. FAST / STANDARD / DEEP / FAIL_CLOSED classification rules

### FAST

```text
route == FAST_RETRY_ONCE
AND all core legacy budget signals are available
AND affordable == true
AND reason is not deadline_pressure_allowed
-> FAST
```

This label reflects the existing M26 route identity only. It does not grant a
new fast path or alter the 7000 ms legacy minimum budget.

### STANDARD

```text
route in:
  SEMANTIC_CLOSURE
  EVIDENCE_SLOT_REALIGNMENT
  CLAIM_WEAKENING
  CONTRADICTION_TRIAGE

AND either:
  affordable == true
OR
  existing reason starts deadline_pressure_allowed:
  AND provider_attempts_remaining > 0
  AND affordable == false
-> STANDARD
```

These are all existing bounded M26 semantic recovery paths. Stage 4 does not
change their provider-call or retry allowance.

### DEEP

```text
not emitted in Stage 4
```

M26 currently exposes no independent, authoritative compute-depth signal that
can distinguish a DEEP allocation from its bounded semantic recovery routes.
Classifying a route as DEEP would therefore be a new policy guess.

Specialized semantic routes such as `CLAIM_WEAKENING` and
`CONTRADICTION_TRIAGE` remain STANDARD shadow classifications in this stage.
`deadline_pressure_allowed` also remains STANDARD and never becomes DEEP.

### FAIL_CLOSED

```text
existing route == SAFE_ABSTENTION
-> FAIL_CLOSED
```

If the existing reason begins
`deadline_or_provider_budget_blocked:`, the reason code records that existing
M26 budget block. Otherwise it records existing safe abstention.

Stage 4 never causes an M26 answer to fail. It only labels an already-produced
fail-closed/safe-abstention state.

### LEGACY_M26

Used instead of guessing when:

```text
required raw budget signal is missing
unknown/future legacy route is observed
FAST_RETRY_ONCE is internally inconsistent with affordability
semantic recovery route is inconsistent with existing M26 pressure semantics
```

## 5. Cases left unavailable instead of guessed

Stage 4 deliberately does not invent:

```text
DEEP tier authority
missing deadline_remaining_ms
missing minimum_budget_ms
missing provider_attempts_remaining
missing affordable
unknown route semantics
new repair allowance
new retrieval round budget
new verification depth
new context budget
new safe-abstention threshold
```

Missing raw fields remain the existing `unavailable_in_stage1` sentinel.
Tier classification falls back to `LEGACY_M26` when a reliable tier cannot be
derived from existing signals.

## 6. Deadline-pressure handling

M26 permits one late verified semantic attempt for non-fast routes when:

```text
preferred wall-clock minimum is no longer affordable
provider_attempts_remaining > 0
route is one of:
  SEMANTIC_CLOSURE
  EVIDENCE_SLOT_REALIGNMENT
  CLAIM_WEAKENING
  CONTRADICTION_TRIAGE
```

M26 marks this by prefixing the reason with:

```text
deadline_pressure_allowed:
```

Stage 4 preserves this as:

```text
deadline_pressure_allowed = true
deadline budget class = CONSTRAINED or EXHAUSTED from raw remaining time
shadow tier = STANDARD
shadow reason = DEADLINE_PRESSURE_PRESERVED
```

It does not reinterpret deadline pressure as M27 DEEP authority.

`FAST_RETRY_ONCE` does not receive this exception in M26. An inconsistent
FAST signal is therefore left `LEGACY_M26`, not force-classified.

## 7. Feature flag / shadow-only semantics

Stage 4 adds an isolated, default-off flag constant in the Stage 4 shadow module:

```text
M27_COMPUTE_POLICY_SHADOW_ENABLED=false
```

Effective enablement requires both:

```text
requested == true
isolated_runtime == true
```

The flag is not wired into the public runtime, production runtime, route
selection, provider layer, retrieval layer, verifier, or answer path.

The pure `classify_shadow_compute()` API is side-effect free.
`observe_shadow_compute_if_enabled()` returns no observation while disabled.

Future enablement boundary, if Master chooses to wire it later:

```text
M27 isolated internal trace/comparison only
no public SSE
no production authority
no route authority
```

## 8. Privacy guarantees

The Stage 4 observation schema can contain only:

```text
route/reason codes
integer budget values
integer attempt counts
booleans
fixed enums/classes
shadow metadata
```

It has no fields for:

```text
raw query
raw answer
evidence body
source body
provider prompt
secret
credential
environment value
private payload
```

Extra private fields supplied in a mapping are ignored by
`LegacyM26DeadlineBudgetAdapter` and do not appear in
`ComputePolicyObservation.as_dict()`.

The feature-flag loader stores only resolved booleans and does not retain the
raw environment value.

## 9. Exact tests/results

Focused Stage 4 tests:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage4-compute/src \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_compute_policy.py \
  tests/test_m27_compute_policy_shadow.py
```

Result:

```text
23 passed in 0.85s
```

Required compile gate:

```bash
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

Required Stage 1-4 regression command:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage4-compute/src \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py \
  tests/test_m27_decision_trace.py \
  tests/test_m27_replay_harness.py \
  tests/test_m27_equivalence_report.py \
  tests/test_m27_evidence_planner.py \
  tests/test_m27_context_evidence_boundary.py \
  tests/test_m27_compute_policy.py \
  tests/test_m27_compute_policy_shadow.py
```

Result:

```text
86 passed in 2.18s
```

Relevant existing M26 deadline-routing regression:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage4-compute/src \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m26_deadline_aware_semantic_routing.py
```

Result:

```text
11 passed in 0.34s
```

Required ruff gate:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m27_compute_policy*.py \
  tests/test_m27_compute_policy*.py
```

Result:

```text
All checks passed!
```

No full 523, Docker build, production mutation, or production test deployment was run.

## 10. Replay/equivalence findings

Stage 2 remains the canonical regression lens.

Stage 4 tests feed the same real M26 `SemanticRoutingDecision` into:

```text
Stage 2 capture_sanitized_replay_input/run_replay_equivalence
and
Stage 4 RuleBasedComputePolicy
```

Findings:

```text
route: EQUIVALENT
route_reason: EQUIVALENT
deadline_remaining_ms: EQUIVALENT
minimum_budget_ms: EQUIVALENT
provider_attempts_remaining: EQUIVALENT
deadline_affordable: EQUIVALENT
```

The Stage 4 policy adds a separate non-authoritative shadow tier. It does not
backfill or mutate the canonical Stage 1 `ComputeDecision.compute_tier`.
When the Stage 4 tier is supplied to the Stage 2 replay fixture, the Stage 2
adapter correctly still reports its historical
`EXPECTED_UNAVAILABLE_STAGE1` classification rather than pretending the
Stage 1 adapter produced the new tier.

This keeps chronology and ownership explicit.

## 11. Behavior impact

```text
M26 route changes: NO
provider calls added: NO
retrieval rounds added: NO
repair attempts added: NO
verification depth changed: NO
context budget changed: NO
deadline changed: NO
provider budget changed: NO
answer changed: NO
citation behavior changed: NO
safe-abstention boundary changed: NO
public SSE changed: NO
production wiring added: NO
```

Stage 4 is observer/classifier only.

## 12. Blockers

```text
NONE
```

No shared-contract change was required.

## 13. Remaining risks

1. M26 exposes no independent DEEP compute signal today. DEEP remains intentionally
   unclassified rather than guessed.
2. Deadline-pressure and budget-block reason recognition depends on existing M26
   reason prefixes. Raw reason remains preserved, and unknown/inconsistent forms
   fall back to `LEGACY_M26`.
3. Stage 4 is not runtime-wired. Master integration must preserve the same
   shadow-only/default-off boundary if internal tracing is wired later.
4. The provider budget class is descriptive only. ONE versus MULTIPLE reuses the
   existing canonical `ProviderAttemptClass`; it must not become an allocation
   rule without a later behavior-changing stage and eval gate.
5. Full 523 is intentionally not run in this sub-session.

## 14. Production untouched confirmation

Git ownership audit before report creation showed only Stage 4-owned new files.
No M26, shared contract, Stage 5, tool, or read-only registry file was modified.

Read-only runtime status check:

```text
production:
llm_wiki-knowledge-engine-1
knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z
healthy
127.0.0.1:8080->8080/tcp

M27 isolated:
llm_wiki-m27-context-runtime-1
knowledge-engine:m27-context-runtime-stage0c
healthy
127.0.0.1:18080->8080/tcp
```

Production was not restarted, replaced, routed, built, or mutated by Stage 4.

## 15. Recommendation for Master integration

```text
READY_FOR_MASTER_INTEGRATION
```

Recommended Master review points:

```text
1. Keep ComputePolicyObservation separate from authoritative ComputeDecision.
2. Preserve LEGACY_M26 fallback for missing/unknown/inconsistent signals.
3. Accept that DEEP is intentionally unavailable in Stage 4.
4. If shadow tracing is wired later, keep the default-off + isolated-runtime gate.
5. Do not wire this policy to route/provider/retrieval/repair/verifier authority.
```

Required answers:

```yaml
Does shadow ComputePolicy preserve every existing M26 budget signal?: YES

Can it ever change an M26 route or provider call count?: NO

Is tier classification authoritative?: NO

Did any safety/abstention boundary weaken?: NO
```
