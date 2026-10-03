# M27 Stage 4 + Stage 5 Master Integration Report

Date: 2026-10-03
Master branch: `m27/context-native-runtime-spec`
Base: `5a0c6cc7`

## 1. Integrated parallel stages

Stage 4 source:

```text
branch: m27/stage4-compute-policy
source commit: f4061645
master cherry-pick: 96f580c9
```

Stage 5 source:

```text
branch: m27/stage5-readonly-tools
source commit: d1882a76
master cherry-pick: 8797eead
```

The two branches were intentionally file-disjoint.

Neither branch modified:

```text
src/knowledge_engine/m27_context_runtime_contracts.py
any m26_* core source
any test_m26_* baseline test
```

## 2. Stage 4 review

Accepted Stage 4 architecture:

```text
already-produced M26 SemanticRoutingDecision
        “
LegacyM26DeadlineBudgetAdapter
        “
RuleBasedComputePolicy
        “
non-authoritative ComputePolicyObservation
```

The policy is an observer/classifier only.

It preserves existing raw signals:

```text
route
reason
deadline_remaining_ms
minimum_budget_ms
provider_attempts_remaining
affordable
```

and derives only descriptive metadata:

```text
budget_headroom_ms
deadline_budget_class
provider_budget_class
provider_attempt_class
shadow_compute_tier
shadow_reason_code
deadline_pressure_allowed
```

Every observation remains:

```text
shadow_only = true
authoritative = false
```

Master independently checked representative paths:

```text
FAST_RETRY_ONCE -> FAST
SEMANTIC_CLOSURE affordable -> STANDARD
SEMANTIC_CLOSURE deadline_pressure_allowed -> STANDARD
SAFE_ABSTENTION budget blocked -> FAIL_CLOSED
unknown future route -> LEGACY_M26
```

No representative path emitted DEEP.

This is correct because current M26 has no independent authoritative signal for a DEEP compute allocation.

Stage 4 does not allocate provider attempts, retrieval rounds, repair allowance, verification depth, context budget, deadline extension, or route authority.

## 3. Stage 4 shadow flag

```text
M27_COMPUTE_POLICY_SHADOW_ENABLED
default: false
effective only when requested=true and isolated_runtime=true
runtime wiring: none
production authority: none
public authority: none
```

The canonical Stage 1 `ComputeDecision.compute_tier` is not backfilled or mutated by Stage 4.

## 4. Stage 5 review

Accepted native capability registry contains exactly:

```text
knowledge.search
knowledge.expand
evidence.inspect
evidence.verify
runtime.get_trace
runtime.get_budget
runtime.get_health
```

The registry is descriptor-only.

It exposes:

```text
register
resolve
list
describe
```

It has no:

```text
invoke
execute
network caller
credential acquisition
authorization grant
database/storage access
```

Master independently instantiated the canonical registry and confirmed all seven descriptors are:

```text
read_only = true
supports_mutation = false
exposes_raw_infra = false
requires_authorization = true
```

## 5. Stage 5 forbidden boundary

The registry rejects write/admin/release/raw-infrastructure capability names and aliases.

The first native tool layer does not expose:

```text
Qdrant raw APIs
R2 raw APIs
SQLite/raw SQL
release promotion/rollback
ingestion mutation
admin mutation
filesystem/process/Docker control
```

Stage 5 contains no MCP dependency and no agentic retrieval loop.

Knowledge capabilities stop at an injected `KnowledgeProvider` protocol boundary.

Evidence tools inspect already-produced Stage 3 / verifier objects.

Runtime tools expose sanitized metadata views only.

## 6. Parallel integration compatibility

Stage 4 and Stage 5 do not require each other to function.

Stage 5 `runtime.get_budget` deliberately reads the stable sanitized Stage 1 trace budget representation rather than importing the parallel Stage 4 implementation.

Stage 4 does not import or modify the tool registry.

Therefore parallel integration introduces no cyclic dependency and no shared-contract conflict.

A later Master-controlled stage may expose a Stage 4 shadow observation through a sanitized runtime capability, but that is not part of Stage 4 or Stage 5.

## 7. Combined test gate

Compile:

```text
PASS
```

Combined M26 safe baseline + all M27 Stage 1 through Stage 5 tests:

```text
169 passed, 1 warning
```

Composition:

```text
49 M26 safe baseline tests
120 M27 Stage 1-5 tests
```

Ruff:

```text
All checks passed!
```

Diff audit from `5a0c6cc7`:

```text
M26 core source diff: none
M26 baseline test diff: none
shared m27_context_runtime_contracts.py diff: none
```

## 8. Independent sanity checks

Stage 4 representative classification:

```text
FAST_RETRY_ONCE FAST FAST_RETRY_ROUTE authoritative=false shadow_only=true
SEMANTIC_CLOSURE STANDARD BOUNDED_SEMANTIC_RECOVERY_ROUTE authoritative=false shadow_only=true
SEMANTIC_CLOSURE STANDARD DEADLINE_PRESSURE_PRESERVED authoritative=false shadow_only=true
SAFE_ABSTENTION FAIL_CLOSED EXISTING_BUDGET_BLOCK authoritative=false shadow_only=true
FUTURE_ROUTE LEGACY_M26 UNKNOWN_LEGACY_ROUTE authoritative=false shadow_only=true
```

Stage 5 canonical registry:

```text
evidence.inspect
evidence.verify
knowledge.expand
knowledge.search
runtime.get_budget
runtime.get_health
runtime.get_trace
```

Registry invocation surface:

```text
invoke: absent
execute: absent
```

## 9. Runtime and production safety

M27 isolated runtime:

```text
container id:
4cc8d95787f0d7f9461564ce12cec9bbbf1ed068ca07d69a669f7ab8d39b697b

image:
knowledge-engine:m27-context-runtime-stage0c

StartedAt:
2026-10-03T09:34:29.303793202Z

state:
running / healthy

GET http://127.0.0.1:18080/v1/health:
HTTP 200
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

Production identity and start time remain unchanged.

The permanent generic extractive fallback guard remains present:

```python
# Guard: do not emit generic extractive evidence fallback as user-facing answer.
return None
```

## 10. Behavior impact

```text
answer behavior change: none
retrieval behavior change: none
verification behavior change: none
publication behavior change: none
provider call change: none
deadline change: none
provider budget change: none
safe-abstention boundary change: none
production mutation: none
MCP introduced: no
agentic retrieval introduced: no
```

## 11. Remaining limitations

Stage 4:

```text
DEEP remains intentionally unclassified
shadow policy remains unwired
reason-prefix compatibility must remain conservative
```

Stage 5:

```text
knowledge.search / knowledge.expand have no live provider implementation
authorization remains external
runtime health live wiring remains future work
MCP remains future Stage 9 work
```

These limitations are intentional and do not block the next architecture stage.

## 12. Verdict

```text
STAGE4_GATE: PASS
STAGE5_GATE: PASS
PARALLEL_INTEGRATION_GATE: PASS

combined tests: 169 passed
M26 behavior change: none
production invariant weakening: none
production safety: pass
```

Stage 6 Bounded Agentic Retrieval may now enter Master-controlled construction.

Because Stage 6 can change retrieval behavior, its core implementation must remain single-threaded and Master-controlled. Evaluation/failure-analysis helpers may be delegated, but not competing core retrieval implementations.
