# M27 Stage 6 Master Integration Report

Date: 2026-10-03
Master branch: `m27/context-native-runtime-spec`
Stage 6 base: `38d8cbf1`

## Integrated commits

```text
1a473cc7 feat(m27): add stage6 bounded agentic retrieval candidate
22fab9af fix(m27): harden stage6 bounded retrieval gate
cd67a8b3 docs(m27): complete stage6 bounded retrieval report
```

## Stage 6 scope

Stage 6 adds bounded, evidence-gap-driven retrieval expansion as a default-off isolated capability.

It does not enable production behavior by default.

## Effective runtime gate

Stage 6 only runs when:

```text
M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED=true
M27_ISOLATED_RUNTIME=true
```

If either condition is false, the canonical entrypoint skips the Stage 6 helper entirely.

## Behavior summary

Stage 6 preserves:

```text
existing M26 first retrieval
existing selector
existing evidence strengthener
existing ContextCompiler
existing verifier
existing citation binding
existing safe-abstention behavior
```

It permits at most one additional deterministic retrieval round when material semantic requirements remain unsupported after existing M26 strengthening.

Second-round evidence is adopted only when the missing material requirement set strictly shrinks.

## Master test gate

Canonical master gate:

```text
compileall: PASS
pytest: 192 passed, 1 warning
ruff M27 files: PASS
ruff patched M26 file with known pre-existing F841 ignored: PASS
```

The known F841 is pre-existing in `m26_aq_semantic_contract.py` and was not introduced by Stage 6.

## Full523 retrieval-only evaluation

Artifact path:

```text
/home/ubuntu/m27-stage6-eval/retrieval-full523-v1
```

Summary:

```text
population: 523
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

The eval was completed in chunks due SSH transport limits. Duplicate rows caused by an earlier overlapping runner were backed up and de-duplicated before final summary generation.

## Live final-answer sanity check

Only the two retrieval-adopted cases were run live with a timeout.

OFF:

```text
PASS024: safe abstention
PASS186: safe abstention
unsupported_claims: 0
```

ON:

```text
PASS024: safe abstention
PASS186: cited answer
unsupported_claims: 0
```

This is a small sanity check, not a full production release gate.

## Runtime safety

Production container observed after integration:

```text
llm_wiki-knowledge-engine-1
knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z
healthy
127.0.0.1:8080->8080/tcp
```

M27 isolated runtime observed after integration:

```text
llm_wiki-m27-context-runtime-1
knowledge-engine:m27-context-runtime-stage0c
healthy
127.0.0.1:18080->8080/tcp
GET /v1/health -> HTTP 200
```

No deployment, production restart, production pointer write, Qdrant alias write, production sqlite write, or release promotion was performed.

## Verdict

```text
STAGE6_MASTER_INTEGRATION: PASS
PRODUCTION_ENABLEMENT: NOT_READY
```

Stage 6 is integrated into canonical master as a default-off isolated capability. It is not enabled for production and must not be promoted until a stable full live final-answer 523 gate is available and passes.
