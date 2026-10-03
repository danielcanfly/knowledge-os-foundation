# M27 Stage 1 Master Integration Report

Date: 2026-10-03
Master branch: `m27/context-native-runtime-spec`
Stage 1 base: `6f51a0b1`

## 1. Integrated sub-sessions

Stage 1A source branch:

```text
m27/stage1-a-contracts
source commit: 7aee74fe
master cherry-pick commit: 7fc54714
```

Stage 1B source branch:

```text
m27/stage1-b-trace
source commit: ee7c0eb5
master cherry-pick commit: 69bcc652
```

Both required sub-session reports were present and reviewed:

```text
docs/m27/research/stage1_subsession_A_report.md
docs/m27/research/stage1_subsession_B_report.md
```

Both sub-sessions confirmed production was untouched.

## 2. Master integration reconciliation

Master found one semantic integration conflict even though Git had no textual conflict:

- Stage 1A defined a placeholder `DecisionTraceEvent` with arbitrary `metadata`.
- Stage 1B defined the privacy-hardened canonical `DecisionTraceEvent` with fixed enums/counts and no arbitrary payload/metadata.

Keeping both would create two trace contracts and would weaken the Stage 1 privacy boundary.

Master resolution:

```text
m27_decision_trace.DecisionTraceEvent
= canonical sanitized trace event

m27_context_runtime_contracts.DecisionTraceEvent
= re-export/import of the canonical sanitized trace event
```

`RuntimeTraceStore.record(...)` now uses the same canonical event type.

The Stage 1A placeholder metadata-bearing trace event was removed.

A contract test now proves:

```text
DecisionTraceEvent is CanonicalDecisionTraceEvent
no metadata field
no payload field
```

This is an integration-only contract reconciliation. No M26 runtime file or answer path was changed.

## 3. Final Stage 1 contract surface

Contracts:

```text
ContextPlan
ComputeDecision
EvidencePlan
ContextCompileResult
VerificationDecision
DecisionTraceEvent
RuntimeTraceStore
PolicyDecision
ContextPlanner
ComputePolicy
ContextCompiler
Verifier
```

Legacy adapters:

```text
LegacyM26SemanticRoutingAdapter
LegacyM26DeadlineBudgetAdapter
LegacyM26ContextCompilerAdapter
LegacyM26VerifierAdapter
```

Feature flag:

```text
M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED
default effective value: false
effective true requires isolated_runtime=True
```

Trace remains observability-only and has no routing, security, publication, promotion, or rollback authority.

## 4. Privacy boundary

Canonical Stage 1 trace does not contain arbitrary payload or metadata fields.

It does not directly represent:

```text
raw query
raw answer
full evidence text
full source text
secret
API key
token
credential
environment value
private payload
production write credential
```

Allowed trace information is restricted to sanitized IDs, fixed enums, counts, budget classes, source classes, status classes, abstention outcomes, and fixed guard outcomes.

## 5. Master test gate

Compile:

```bash
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

M27-only integration tests:

```text
34 passed
```

Ruff:

```text
All checks passed!
```

Full documented Stage 1 gate:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_m26_canonical_runtime_reachability.py \
  tests/test_m26_deadline_aware_semantic_routing.py \
  tests/test_m26_public_api.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_aq_surface_guard.py \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py \
  tests/test_m27_decision_trace.py
```

Result:

```text
83 passed, 1 warning
```

The original safe M26 Stage 1 baseline was 49 tests. The added 34 M27 tests all pass.

## 6. M26 behavior isolation check

Master checked for changes since `6f51a0b1` under:

```text
src/knowledge_engine/m26*
tests/test_m26*
```

Result:

```text
no changed files
```

No Stage 1 integration change modified M26 runtime or its baseline tests.

## 7. Isolated runtime health

M27 isolated runtime:

```text
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
status: healthy
port: 127.0.0.1:18080->8080/tcp
GET /v1/health: HTTP 200
```

The Stage 1 code is intentionally not wired into the runtime answer path in this stage. The health gate verifies that the isolated lab remains independently startable and healthy.

## 8. Production safety verification

Production before M27 isolated start:

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

Production after M27 isolated start and health gate had the same container ID, image, StartedAt, and healthy state.

Therefore:

```text
production restarted: NO
production container replaced: NO
production route changed: NO
production R2/Qdrant/SQLite write: NO
answer behavior changed: NO
```

## 9. Deferred item

The legacy arbitrary semantic expectation drift remains:

```text
tests/test_m26_pa_7_arbitrary_query_runtime.py
```

It remains `DEFERRED_OUTSIDE_STAGE1`.

Do not weaken current safe-abstention behavior to satisfy stale cited-answer expectations.

This must be classified during replay/equivalence work before behavior-changing Stage 6 retrieval work.

## 10. Stage 1 verdict

```text
STAGE1_GATE: PASS
behavior impact: NONE
production safety: PASS
trace privacy: PASS
contract reconciliation: PASS
M27 isolated health: PASS
```

Stage 2 Replay / Equivalence Harness is now unblocked.

Stage 2 must still be non-behavior-changing and must not introduce Jev, MCP, Memory, Agent loop, Learning Plane, Meta-Harness, or production access.
