# Runtime to Small Smoke Handoff

State: `M27_PRODUCTION_EQUIV_RUNTIME_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-prod-equiv-runtime`
Branch: `m27/production-equivalent-runtime`
Base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## Integrated runtime identity

This branch integrates:

- Production evidence bridge: `e8bea293a026e12926eb76cdddb615f13c4286d6`
- Admission infrastructure audit: `cda6a06d757e3f2f3b92d2758ba5b2f2c70109f6`
- Runtime observability contract: `f18128138d79c982474afe847de81cc55eaea5de`

It adds a unified production-equivalent isolated runtime and a clean fail-closed isolated admission harness.

## What Session 05 may use

Session 05 may use:

- `src/knowledge_engine/m27_runtime_execution.py` production-equivalent evidence route;
- `src/knowledge_engine/m27_production_evidence_bridge.py` authority and binding checks;
- `src/knowledge_engine/m27_runtime_telemetry.py` telemetry schema `m27-runtime-telemetry/v1`;
- `src/knowledge_engine/m27_isolated_admission_harness.py` for preflight, case transport classification, postflight, and receipt summaries;
- deterministic production-equivalent evidence fixture patterns from `tests/test_m27_production_evidence_bridge.py`.

## Explicit Session 05 decision

`05 MAY RUN: YES, CONDITIONALLY.`

Session 05 may run only the bounded fresh small smoke described by its own prompt after it verifies all live preflight conditions. It must stop before the first question if any preflight condition fails.

Required preflight gates for Session 05:

1. The authorized isolated build commit is this branch final HEAD or another explicitly owner-authorized descendant.
2. The target endpoint is loopback isolated-only and matches the expected isolated endpoint.
3. The isolated build SHA, image/container identity, and endpoint match the expected values.
4. Production health is read-only HTTP 200 and production identity is captured before the smoke.
5. Production identity must remain stable after the smoke.
6. Exactly one isolated eval container is active.
7. No concurrent docker build, pytest, endpoint evaluation, or other M27 eval workload is active.
8. Host memory, swap, and load are inside the configured guard.
9. Isolated quota active-request state is clean before first request and after cleanup.
10. The production-equivalent evidence/compiler binding matches the pinned bridge authority.

## Mandatory hard stops for Session 05

Stop immediately and preserve partial receipts if any occurs:

- request target is not the verified isolated endpoint;
- isolated build identity changes or mismatches;
- production `/v1/health` is not HTTP 200;
- production identity changes;
- compiler/evidence authority binding mismatches;
- HTTP 429 with `provider_calls = 0` or equivalent quota poison;
- quota active-request count fails to return to expected state;
- malformed or missing terminal SSE event;
- citation status, latency, or TTFT is unknown for a case where the smoke requires it;
- available memory guard trips;
- swap grows beyond the configured bound;
- another eval/build/test workload violates exclusivity;
- isolated cleanup cannot be confirmed.

Do not convert infrastructure-poisoned rows into quality evidence.

## What Session 05 must not do

- Do not mutate production.
- Do not restart, stop, rebuild, deploy, or write production.
- Do not write production R2, Qdrant, SQLite, or release pointers.
- Do not run Stage13/14 legacy admission.
- Do not run Chunk002, 100-case, or full523.
- Do not import dirty changes from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.

## Verification receipt from this session

- Production-equivalent runtime + observability + finalization + admission harness: `32 passed in 1.74s`
- Full M27 suite: `524 passed in 12.87s`
- M26 safety-equivalent gate: `35 passed in 12.32s`
- Combined M27 + M26 gate: `67 passed in 11.70s`
- `compileall -q src/knowledge_engine tests`: PASS
- Scoped Ruff: PASS
- `git diff --check`: PASS

## Handoff conclusion

Session 05 is unlocked only for a fresh small-smoke preflight and bounded isolated smoke under its own prompt. This handoff does not authorize admission scoring beyond that scope, production mutation, Stage13/14 legacy admission, 100-case, Chunk002, or full523.

`M27_PRODUCTION_EQUIV_RUNTIME_READY`
