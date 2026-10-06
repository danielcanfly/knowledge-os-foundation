# Observability to Runtime Handoff

## Accepted state

`M27_OBSERVABILITY_CONTRACT_READY`

Base runtime composition:

`8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

Observability branch:

`m27/runtime-observability-contract`

Worktree:

`/home/ubuntu/LLM_Wiki-m27-runtime-observability`

## Runtime contract now available

Every isolated executable M27 request returns:

`M27RuntimeHarnessResult.runtime_telemetry`

and writes:

`runtime/telemetry.json`

using:

`schema_version = m27-runtime-telemetry/v1`

Downstream smoke/runtime diagnostics should consume this telemetry instead of inferring stage latency from total request time.

## Required downstream fields

For each request:

- request/task IDs
- route and task kind
- compute tier and budget class
- called tool count
- final evidence count
- compiler aggregate latency
- provider/model call count and latency
- verifier aggregate exclusive latency
- actual continuation round count
- final terminal reason
- feature flags
- sanitized reason codes
- total runtime latency
- explicit cost state

For each round:

- `tool_ms`
- `evidence_binding_ms`
- `compiler_ms`
- `provider_ms`
- `verifier_ms`
- `round_total_ms`
- compiler/verifier statuses
- provider call records
- evidence count/delta
- continuation allowed/decision
- round terminal reason

## Interpretation rules

1. `provider_ms` is the sum of measured provider/model calls for that round.
2. `verifier_ms` is verifier-local elapsed time with provider time subtracted.
3. `round_total_ms` is wall elapsed time for the full round and may be larger than the sum of named stages because orchestration bookkeeping is intentionally not hidden inside another stage.
4. `estimated_cost_usd = null` with `COST_UNAVAILABLE` means no authoritative provider pricing/token source was present. Do not replace this with guessed cost.
5. A zero-round telemetry document is valid for pre-execution budget/capability safe terminals.

## Privacy contract

Do not add arbitrary payload fields to this schema.

The telemetry boundary must remain free of:

- raw query/question
- raw prompt
- raw evidence or passage text
- raw answer text
- provider/model response body
- credentials/secrets

If later runtime work needs richer debugging, add sanitized typed fields or reason codes rather than attaching raw request/response objects.

## Compatibility

The existing sanitized `DecisionTraceEvent` remains unchanged and valid. `M27RuntimeTelemetry` is additive execution-grade observability for the finalized isolated runtime.

No production runtime, production service, R2, Qdrant, SQLite, release pointer, or production container was changed by this session.

## Verification receipt

```text
ruff check: PASS
git diff --check: PASS
targeted + M27 runtime regression: 71 passed
```

## Next-session constraint

This handoff does not authorize Stage13/14 legacy admission, full523, production deployment, or latency optimization.

The next runtime/smoke session may use the telemetry for diagnosis only after its own prerequisite gates, especially the production-grade compiler/evidence bundle bridge, are satisfied.
