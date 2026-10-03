# M27 Stage 3 Master Integration Report

Date: 2026-10-03
Master branch: `m27/context-native-runtime-spec`
Stage 3 base: `acd68cd1`

## 1. Integrated Stage 3 sub-session

Source branch:

```text
m27/stage3-context-evidence-boundary
source commit: db67483a
master cherry-pick commit: 411368b4
```

Reviewed report:

```text
docs/m27/research/stage3_context_evidence_boundary_report.md
```

Changed files are M27-only plus the Stage 3 report. No M26 source or M26 baseline test file changed.

## 2. Master boundary review

Accepted canonical separation:

```text
existing retrieval / evidence behavior
        “
EvidencePlanner normalization
        “
selected evidence identities
+ existing coverage/gap/sufficiency metadata
        “
existing M26 ContextCompiler
        “
deterministic context package / manifest / citations
```

EvidencePlanner remains observation/normalization only.

It does not rerun:

```text
retrieval
_select_evidence
_strengthen_evidence
reranking
support scoring
new evidence-quality policy
new sufficiency policy
```

ContextCompiler remains the existing implementation:

```text
src/knowledge_engine/m26_context_compiler.py
```

Stage 3 does not compile context a second time.

## 3. Contract additions

Stage 3 extends the M27 contract layer with:

```text
STAGE3_UNAVAILABLE
Stage3Unavailable
EvidenceIdentity
EvidenceGapSummary
EvidencePlanningResult
EvidencePlanner
```

Implementation surfaces:

```text
LegacyM26EvidencePlannerAdapter
ContextEvidenceBoundaryResult
LegacyM26ContextEvidenceBoundary
```

Stage 1 and Stage 2 contracts remain compatible and all prior tests stay green.

## 4. Evidence identity review

Master independently checked source-identity behavior.

Observed:

```text
explicit source_identity -> preserved exactly
source_id -> preserved exactly
artifact_key + section_id -> same M26 artifact#section identity
section_id only -> unavailable_in_stage3
no source fields -> unavailable_in_stage3
```

Current M26 private helper would produce fallback strings such as:

```text
artifact#section
artifact#
```

when artifact fields are absent.

Stage 3 intentionally refuses to claim those default-generated fallback strings as reliable Stage 3 identity unless sufficient artifact/source signal already exists.

This is accepted because the Stage 3 rule is:

```text
preserve existing meaningful identity
otherwise mark unavailable
never fabricate identity merely for completeness
```

No random ID, raw-text-derived ID, or model-inferred source identity is introduced.

Evidence ID and compiler passage ID remain separate identity domains.

## 5. Gap and sufficiency review

Normalized fields are sourced only from already-produced M26 signals:

```text
selected_evidence_count
distinct_source_count
requirement_ids
covered_requirement_ids
missing_requirement_ids
coverage_status
sufficiency_status
recovered_requirement_ids
bounded_recovery_used
reason_codes
```

Stage 3 does not infer evidence sufficiency from count, source diversity, or a new threshold.

Missing/incomplete support classifications remain explicit unavailable values.

## 6. ContextCompiler preservation

Stage 3 preserves the normalized form of already-produced compiler outputs:

```text
compiler status
context_manifest_sha256
evidence_budget_sha256
selected passage identities
citation count
safe-for-provider state
prompt-injection quarantine state
reason codes
```

The planner-selected evidence set and compiler-selected passage set are not required to be identical.

A compiler token-budget subset is legitimate compiler behavior, not planner drift.

## 7. Production invariant review

The permanent generic extractive fallback guard remains present:

```python
# Guard: do not emit generic extractive evidence fallback as user-facing answer.
return None
```

No M26 core file changed.

Therefore Stage 3 does not change:

```text
retrieval behavior
evidence selection
evidence strengthening
context compiler behavior
verification
publication
answer behavior
safe abstention
citation binding
```

## 8. Master integration gate

Compile:

```text
PASS
```

Stage 1 + Stage 2 + Stage 3 + M26 safe baseline:

```text
112 passed, 1 warning
```

Composition:

```text
49 existing safe M26 baseline tests
34 Stage 1 M27 tests
16 Stage 2 M27 tests
13 Stage 3 M27 tests
```

Ruff:

```text
All checks passed!
```

M26 diff from Stage 3 base:

```text
none
```

## 9. Runtime safety

M27 isolated runtime:

```text
llm_wiki-m27-context-runtime-1
knowledge-engine:m27-context-runtime-stage0c
healthy
127.0.0.1:18080
GET /v1/health -> HTTP 200
```

Production remains:

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

The production container identity and start time are unchanged.

Production was not restarted or replaced.

## 10. Stage 3 verdict

```text
STAGE3_GATE: PASS

EvidencePlanner / ContextCompiler separation: PASS
selected evidence identity drift: NONE observed
context manifest drift: NONE observed
citation drift: NONE observed
M26 behavior change: NONE
production invariant weakening: NONE
production safety: PASS
isolated runtime health: PASS
```

Stage 4 ComputePolicy / Test-Time Compute Optimization and Stage 5 Read-only Tool / Capability Registry may now be evaluated for parallel execution.

Neither is permitted to change production behavior without a later Master-controlled gate.
