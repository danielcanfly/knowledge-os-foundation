# Admission Infrastructure to Small Smoke Handoff

State: `ADMISSION_INFRA_REUSE_PLAN_READY`
Source audit: `docs/m27/research/44b_admission_infra_reuse_audit_report.md`
Base audited: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## What Session 04 may reuse

Reuse ideas and contracts, not old commits wholesale:

- SSE row/summary collection pattern from `6e147d23`;
- immutable case + baseline/final receipt structure from `3d1dcae0`;
- quota lease lifecycle invariants from `6db19db8` / `fe8ed9b5` / `bac017cd`;
- single-VM production-first guard rules from `3592b22b`.

## What Session 04/05 must not import

- `649908f2` runtime changes;
- `34f7b808` runtime changes;
- `fe8ed9b5` M26 public-runtime changes as a cherry-pick or copy;
- dirty changes from `/home/ubuntu/LLM_Wiki-m27-context-runtime`;
- Stage13/14 historical PASS decisions as current authority.

## Session 04 required output

Build a new isolated admission harness with all of these fail-closed properties:

- refuses production targets and defaults to loopback isolated endpoint only;
- verifies expected isolated build SHA before requests;
- captures production health/identity read-only before and after;
- enforces single-eval-container and host resource guard;
- verifies quota/active-request lifecycle without production quota mutation;
- captures generic SSE terminal/citation/latency/TTFT/provider telemetry;
- stops on 429 + zero provider calls, malformed terminal stream, build drift, production health failure, or resource danger;
- cleans up the isolated eval container;
- has unit tests for the above;
- **does not run admission smoke**.

## Session 05 admission prerequisites

Do not start the fresh small smoke until:

1. Session 01 has positively proven the production-grade compiler/evidence bridge and provided its pinned identity/digest contract.
2. Session 04 harness is green and produces a safety receipt.
3. The authorized isolated build commit is explicit.
4. Production health is HTTP 200 and identity captured.
5. No other M27 eval container/build/test workload is active.
6. Host memory/swap/load are inside the Session 04 guard.
7. Isolated quota active state is clean.

If any prerequisite is false, stop before sending the first question.

## Session 05 bounded execution

- exactly one isolated endpoint/container;
- fixed small smoke only, no Stage13/14 legacy chain, no 100-case, no full523;
- explicit resource limits;
- read-only evidence inputs authorized by Session 01;
- verify target build and evidence/compiler binding before first request;
- evaluate hard-stop rules continuously at case/micro-batch boundaries;
- preserve partial evidence if stopped;
- postflight production health/identity, host resources, quota active state, and isolated cleanup are mandatory.

## Hard stop conditions

Stop the smoke immediately if any occurs:

- production `/v1/health` != HTTP 200;
- production identity changes;
- request target is not the verified isolated endpoint;
- isolated build identity changes/mismatches;
- compiler/evidence bridge binding mismatches;
- HTTP 429 with `provider_calls=0` or equivalent quota poison;
- active-request count does not return to expected state;
- malformed/missing terminal SSE event;
- available memory guard trips or swap grows beyond the configured bound;
- another eval/build/test workload violates exclusivity.

Do not convert infrastructure-poisoned rows into quality evidence.

## Minimum output receipt for Session 05

- authorized source commit and image/container identity;
- compiler/evidence bridge digest/identity;
- production pre/post health + identity;
- host pre/post resource snapshot;
- quota pre/post active state;
- per-case JSONL and summary JSON;
- cited/abstained/transport/provider/latency facts;
- explicit unknown-vs-measured unsupported-claim status;
- cleanup confirmation;
- final decision scoped only to the fresh small smoke.

## Canonical handoff

Session 04 can proceed to implement and unit-test the clean isolated harness. Session 05 remains gated on both Session 01 evidence-bridge proof and Session 04 harness readiness.

`ADMISSION_INFRA_REUSE_PLAN_READY`
