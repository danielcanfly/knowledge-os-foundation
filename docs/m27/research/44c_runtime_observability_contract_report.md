# M27 Runtime Observability Contract Report

## Session

- Session: 03 Runtime Observability Contract
- Base accepted runtime-composition HEAD: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`
- Branch: `m27/runtime-observability-contract`
- Worktree: `/home/ubuntu/LLM_Wiki-m27-runtime-observability`
- Production mutation: **none**
- Completion state: **M27_OBSERVABILITY_CONTRACT_READY**

## Mission result

The isolated executable M27 runtime now emits a stable privacy-safe `M27RuntimeTelemetry` document for every executable request, including pre-execution safe terminals. The change is instrumentation-only: no routing, retrieval, compiler, verifier, continuation, provider-budget, answer-quality, or latency policy was optimized or changed.

The telemetry is returned on `M27RuntimeHarnessResult.runtime_telemetry` and persisted inside the isolated task workspace as:

`runtime/telemetry.json`

Schema version:

`m27-runtime-telemetry/v1`

## Architecture reconciliation

The original M27 request-flow contract requires:

- request ID
- task type
- route
- compute tier
- called tools
- retrieval rounds
- compiled-context / compiler observability
- model tier / provider observability
- verification result
- latency by stage
- cost estimate
- reason codes
- feature flags

The finalized executable composition already had bounded rounds and a sanitized Stage-1 `DecisionTraceEvent`, but its per-round execution summary only carried status/counters. It did not provide trustworthy stage timings, provider-call timings, a stable cost field, or a separate privacy-validated runtime telemetry artifact.

This session keeps `DecisionTraceEvent` intact and adds an execution-grade schema rather than overloading the Stage-1 trace.

## Stable telemetry contract

Top-level fields include:

- `schema_version`
- `request_id`
- `task_id`
- `route`
- `task_kind`
- `compute_tier`
- `budget_class`
- `rounds`
- `tool_call_count`
- `retrieval_evidence_count`
- `compiler_latency_ms`
- `provider_call_count`
- `provider_latency_ms`
- `model_call_count`
- `model_latency_ms`
- `verifier_latency_ms`
- `continuation_rounds`
- `terminal_reason`
- `feature_flags`
- `reason_codes`
- `total_latency_ms`
- `estimated_cost_usd`
- `cost_reason_code`

Each execution round includes:

- round index and continuation reason
- selected route / task kind / compute tier / budget class
- called tool names and tool-call count
- retrieval evidence count and evidence delta
- compiler status
- provider/model call records
- provider/model call latency
- verifier status and exclusive verifier latency
- actual continuation allowed/terminal decision
- final round terminal reason
- stage latency map:
  - `tool_ms`
  - `evidence_binding_ms`
  - `compiler_ms`
  - `provider_ms`
  - `verifier_ms`
  - `round_total_ms`

Provider calls are timed inside the existing provider quota wrapper. Verifier latency is reported exclusive of provider time so later smoke diagnosis can distinguish model/provider delay from local verification work.

## Cost contract

No production-equivalent token-price authority is present in this isolated composition. The schema therefore captures cost explicitly without fabricating a number:

- `estimated_cost_usd: null`
- `cost_reason_code: COST_UNAVAILABLE`

A later production-grade provider bridge may populate the estimate only from an authoritative pricing/token source while preserving this schema boundary.

## Privacy and payload boundary

`M27RuntimeTelemetry` has no arbitrary metadata/payload field. Identifiers are restricted to sanitized opaque identifiers; unsafe identifier shapes are hashed.

The telemetry contract does **not** serialize:

- raw question/query text
- prompt text
- evidence/passage text
- answer text
- provider/model response bodies
- credentials/secrets
- arbitrary raw payloads

`assert_privacy_safe_telemetry()` recursively rejects forbidden raw-payload keys before the telemetry artifact is written.

## Instrumentation behavior

Instrumentation uses `time.perf_counter_ns()` around existing execution boundaries. It does not add sleeps, retries, retrieval work, provider calls, verifier calls, or continuation rounds.

The executable path now measures:

1. read-only tool execution
2. evidence identity binding
3. M26.3 context compile
4. each provider/model call
5. verifier-local work exclusive of provider latency
6. complete round elapsed time
7. complete executable request elapsed time

Pre-execution safe terminals still emit a valid zero-round telemetry document with terminal reason and zero call counts.

## Files changed

- `src/knowledge_engine/m27_runtime_telemetry.py`
- `src/knowledge_engine/m27_runtime_execution.py`
- `src/knowledge_engine/m27_runtime_harness.py`
- `tests/test_m27_runtime_observability_contract.py`
- `docs/m27/research/44c_runtime_observability_contract_report.md`
- `docs/m27/handoffs/OBSERVABILITY_TO_RUNTIME_HANDOFF.md`

## Verification

Formatting/lint:

```text
ruff check:
All checks passed!
git diff --check:
PASS
```

Targeted and regression tests:

```text
tests/test_m27_runtime_observability_contract.py
tests/test_m27_runtime_finalization.py
tests/test_m27_runtime_composition_eval.py
tests/test_m27_decision_trace.py
tests/test_m27_compute_policy.py

71 passed in 2.34s
```

The new observability-specific tests prove:

- stable schema and required fields
- per-round stage latency attribution
- provider/model call count and latency attribution
- real continuation round recording
- safe zero-round pre-execution terminal telemetry
- no question/evidence/answer/prompt text leakage
- fail-closed rejection of raw payload keys

## Scope / gates

This session does **not** prove the production-grade compiler/evidence bundle bridge and does **not** authorize a smoke/admission run by itself.

Fresh small admission smoke readiness remains governed by the next-phase dispatch chain. The legal result of this session is limited to observability readiness:

**M27_OBSERVABILITY_CONTRACT_READY**
