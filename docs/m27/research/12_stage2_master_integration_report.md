# M27 Stage 2 Master Integration Report

Date: 2026-10-03
Master branch: `m27/context-native-runtime-spec`
Stage 2 base: `30488a8d`

## 1. Integrated Stage 2 sub-session

Source branch:

```text
m27/stage2-replay-equivalence
source commit: 8cbab3f7
master cherry-pick commit: 8408a485
```

Reviewed report:

```text
docs/m27/research/stage2_replay_equivalence_report.md
```

The Stage 2 commit changed only:

```text
src/knowledge_engine/m27_replay_harness.py
src/knowledge_engine/m27_equivalence_report.py
tests/test_m27_replay_harness.py
tests/test_m27_equivalence_report.py
docs/m27/research/stage2_replay_equivalence_report.md
```

No M26 runtime or M26 baseline test file changed.

## 2. Master code-review findings

The replay harness is provider-free and behavior-inert.

It accepts already-produced M26-compatible signals, sanitizes them, then normalizes them through the Stage 1 LegacyM26 adapters.

It does not:

```text
call a provider
run retrieval
compile context
run verification
change routing
change answer output
change publication
write production state
```

The classification model preserves distinctions between:

```text
EQUIVALENT
EXPECTED_UNAVAILABLE_STAGE1
LEGACY_EXPECTATION_DRIFT
NORMALIZATION_DRIFT
MISSING_SIGNAL
UNSAFE_DRIFT
```

Missing or intentionally unavailable fields are not falsely classified as equivalent.

Safety-critical mismatches are classified as `UNSAFE_DRIFT`.

## 3. Privacy review

Replay capture structurally discards raw bodies.

The safe replay representation does not retain:

```text
raw query
raw answer
full evidence text
full source text
provider prompt
secret
API key
credential
environment value
private payload
```

Citation handling retains only count and allowlisted schema-field names.

Report serialization omits replay values and renders only sanitized case IDs, field names, classifications, and counts.

No raw-query or raw-answer hash was introduced.

## 4. Independent aggregate reproduction

Master independently reconstructed the documented four deterministic representative cases and reran the report aggregation.

Result:

```text
case_count: 4

EQUIVALENT: 51
EXPECTED_UNAVAILABLE_STAGE1: 7
LEGACY_EXPECTATION_DRIFT: 1
MISSING_SIGNAL: 38
NORMALIZATION_DRIFT: 0
UNSAFE_DRIFT: 0

available_signals_equivalent: true
threatens_production_invariants: false
ready_for_next_stage_review: true
```

Therefore the aggregate findings in the Stage 2 report are reproducible and not merely manually asserted.

## 5. Legacy expectation drift

Known deferred drift remains:

```text
tests/test_m26_pa_7_arbitrary_query_runtime.py
```

The older expectation can require repair into a cited answer, while the current production-reconciled M26 path can conservatively return safe abstention.

Stage 2 correctly classifies this as:

```text
LEGACY_EXPECTATION_DRIFT
```

not:

```text
NORMALIZATION_DRIFT
```

No runtime or verifier was weakened.

## 6. Master integration gate

Compile:

```bash
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

Master Stage 1 + Stage 2 pytest gate:

```text
99 passed, 1 warning
```

This includes:

```text
49 existing safe M26 baseline tests
34 Stage 1 M27 tests
16 Stage 2 replay/equivalence tests
```

Ruff:

```text
All checks passed!
```

M26 diff since Stage 2 base:

```text
none
```

## 7. Runtime and production safety

M27 isolated runtime:

```text
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
status: healthy
port: 127.0.0.1:18080->8080/tcp
GET /v1/health: HTTP 200
```

Production:

```text
container id:
c15ab792db7b630d3be57cf11347f61b72e7a7d30548c16f5a9b79ee262b857e

image:
knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z

StartedAt:
2026-10-03T06:17:04.427972123Z

state:
running / healthy
```

The production identity and start time remain unchanged.

Therefore:

```text
production restart: NO
production replacement: NO
production route change: NO
production data mutation: NO
answer behavior change: NO
retrieval behavior change: NO
verification behavior change: NO
```

## 8. Remaining Stage 2 limitations

Stage 1 does not yet normalize:

```text
citation shape
adapter-populated guard outcomes
formal compute tier
formal provider budget class
```

These remain explicit missing/unavailable signals rather than guessed values.

Replay coverage is deterministic and representative, not full 523.

That is acceptable for Stage 2 because Stage 2 is an equivalence harness construction stage, not a behavior-changing release gate.

The replay harness must be expanded before Stage 6 behavior-changing retrieval work.

## 9. Stage 2 verdict

```text
STAGE2_GATE: PASS

normalization drift: 0
unsafe drift: 0
available signals equivalent: true
production invariant threat: false
production safety: PASS
privacy: PASS
M27 isolated health: PASS
```

Stage 3 Context / Evidence Boundary Extraction is unblocked.

## 10. Stage 3 boundary

Stage 3 must separate responsibilities without changing retrieval or answer behavior:

```text
Knowledge / retrieval machinery
  -> EvidencePlanner boundary
       -> selected evidence + evidence gap/sufficiency metadata
            -> ContextCompiler boundary
                 -> deterministic context package / manifest / citations
```

Stage 3 must preserve:

```text
context manifest behavior
citation binding
mandatory evidence preservation
token budget behavior
prompt-injection quarantine
safe fail-closed compilation
deterministic evidence/source IDs
```

Stage 3 is extraction/normalization, not new agentic retrieval.
