# Admission Infrastructure to Small Smoke Handoff

Status: `ADMISSION_INFRA_REUSE_PLAN_READY`
Date: 2026-10-06
Source workspace: `/home/ubuntu/LLM_Wiki-m27-admission-infra-audit`
Base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## Decision

Post-Stage12 history contains reusable admission infrastructure patterns, but no historical commit should be wholesale imported into the accepted M27 runtime.

Proceed by rebuilding a neutral isolated admission collector and safety wrapper on the accepted base. Keep Stage13/14 benchmark runtime patches excluded.

## Reuse these patterns

- Incremental SSE collector from `6e147d23` as a design reference: terminal type, HTTP status, total latency, first SSE, first answer text, provider-call count, citation count, safe abstention and transport error.
- Quota lifecycle invariants from `fe8ed9b5` tests and `6db19db8` diagnosis: no stale active lease after terminal paths; release is effectively idempotent; failed acquire/owner bypass cannot require release; sequential requests cannot poison the next request.
- Stage13R2 operational pattern from `3d1dcae0`: fresh isolated image, localhost endpoint, read-only evidence mount, explicit identity receipts, before/after production checks, preservation of quota failures as non-quality evidence.
- Single-VM constraints from `3592b22b`: one isolated endpoint, bounded resources, no overlapping build/test/eval, chunked execution, stop on host or production instability.

## Do not reuse

- M26 runtime patches from `649908f2`, `34f7b808`, or `fe8ed9b5` by cherry-pick.
- Stage13/14 benchmark-specific answer/retrieval/provider repairs.
- Old benchmark artifacts as fresh evidence.
- Dirty `/home/ubuntu/LLM_Wiki-m27-context-runtime` state.
- Historical production restart-policy mutation from report 30.

## Session 04 contract

Build neutral isolated tooling, preferably `tools/m27_isolated_admission_smoke.py`, with unit tests. It should:

- accept only explicit inputs;
- default to loopback endpoints;
- parse SSE and write deterministic JSONL + summary + run manifest;
- preserve unknown metrics as unknown;
- classify 429/provider_calls=0 as invalid quality evidence;
- contain no benchmark gate thresholds and no runtime behavior changes.

Session 04 should remain tooling-only unless separately authorized to execute a smoke.

## Session 05 preflight gate

A small smoke may start only when all are true:

1. Production-grade compiler/evidence bundle bridge is proven and pinned.
2. Session 04 harness tests pass.
3. Production health is HTTP 200 and production identity is recorded.
4. Host memory/swap/load are acceptable.
5. No other non-production M27 endpoint/container is running.
6. The isolated image commit, localhost port, feature/config snapshot and read-only bundle identity are recorded.

During the run, stop on production health degradation, host pressure, bundle mismatch, provider-backed 429 with zero provider calls, or other evidence-invalidating infrastructure failure.

After the run, remove only the session-owned isolated container and verify production health/identity again.

## Wording discipline

Because evaluation shares the production host, use:

`production deploy/restart/image mutation: NO`

`production host impact: monitored`

`production health checked before/after each batch`

Do not claim `production untouched` merely because no deployment occurred.

## Current authorization

- Fresh small admission smoke: **not executed here**.
- Stage13/14 legacy admission chain: **not authorized**.
- 100-case/full523: **not authorized**.
- Runtime behavior changes: **none**.

Next owner should use report `44b_admission_infra_reuse_audit_report.md` as the authoritative reuse map.
