# M27 Isolated Admission Infrastructure Reuse Audit (44b)

Status: `ADMISSION_INFRA_REUSE_PLAN_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-admission-infra-audit`
Branch: `m27/admission-infra-audit`
Base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## Scope and non-actions

This session audited post-Stage12 evaluation, quota, smoke, and single-VM stability material in `06681024..3592b22b` plus the classification table in report 43. It did not run admission, did not run Stage13/14, did not execute smoke cases, did not build/start/stop/restart any production service, and did not modify runtime behavior. Dirty artifacts in `/home/ubuntu/LLM_Wiki-m27-context-runtime` were treated as forensic only.

No code extraction was performed. That is intentional: the reusable value is split across benchmark-specific runners and runtime-mutating quota fixes. Copying either wholesale would violate the clean-base requirement. The safest output of this audit is a bounded implementation plan for Sessions 04 and 05.

## Source classification

| Commit | Audit disposition | Reuse decision |
|---|---|---|
| `06681024` | Stage12 integration history | forensic only |
| `6e147d23` | Stage13 endpoint smoke/eval tooling plus benchmark artifacts | reuse selected runner concepts only; do not cherry-pick |
| `c8f8f678` | integration report | forensic only |
| `649908f2` | benchmark-facing M26 PA7 runtime edits | exclude |
| `8799d774` | Stage14b endpoint proof artifacts | reuse evidence-shape lessons only |
| `34f7b808` | canonical/legacy M26 runtime provider-contract edits | exclude |
| `8b567264` | integration report | forensic only |
| `ab597e2a` | blocked smoke evidence | forensic failure-mode input |
| `5889fcbd` | quota-blocked retry evidence | forensic failure-mode input |
| `8dfeb516` | integration report | forensic only |
| `6db19db8` | quota lease root-cause report | reuse lifecycle requirements, not code |
| `fe8ed9b5` | quota lease fix in public runtime plus tests | **do not import runtime patch**; re-express lifecycle as isolated harness checks |
| `bac017cd` | quota probe and proof artifacts | reuse probe invariants and evidence fields |
| `a946933f` | integration report | forensic only |
| `3d1dcae0` | repaired smoke evidence and cases | reuse case organization and safety receipts; do not reuse stale benchmark result as admission proof |
| `09aa3a1e` | integration report | forensic only |
| `3592b22b` | single-VM production-stability policy/report | reuse policy requirements, with wording correction from report 43 |

Report 43 already classifies `649908f2` and `34f7b808` as category C and explicitly excludes them. This audit confirms that boundary. It also tightens the treatment of `fe8ed9b5`: although its intent is reusable quota support, the implementation changes `src/knowledge_engine/m26_public_api.py` and `m26_multilingual_public_api.py`; therefore the commit is not a clean infrastructure import.

## Reusable admission infrastructure

### 1. Endpoint evidence collector concepts from `6e147d23`

Reusable mechanics:

- one case at a time against a caller-supplied isolated endpoint;
- capture HTTP status, terminal SSE event, cited-final-answer presence, safe abstention, citation count, answer length/hash, latency, first SSE, first answer text, provider-call observations, surfaced generic/bad-template markers, and transport errors;
- JSONL per-case rows plus machine-readable summary;
- percentile calculation from completed HTTP-200 rows;
- preserve unknown unsupported-claim count as unknown rather than manufacturing zero.

Required redesign before Session 05:

- deny production URLs/ports by default and require an explicit loopback isolated endpoint;
- pin expected build identity and fail closed on mismatch;
- separate collector schema from Stage13 naming and benchmark-specific generic-prefix heuristics;
- record compiler/evidence bridge identity needed by the new M27 admission chain;
- record pre/post quota state and host guard receipts;
- do not infer provider calls solely from a legacy `model.started` event if the new runtime exposes a stronger counter;
- enforce a hard maximum case count for small smoke.

### 2. Case/evidence organization from `3d1dcae0`

Reusable pattern:

- immutable input case file;
- separate output directories for each configuration;
- baseline identity and health receipts before execution;
- final isolated and production health/identity receipts;
- explicit aggregate receipt with HTTP, citation, abstention, provider, quota, and latency facts.

Not reusable as authority:

- the old Stage13R2 pass/fail thresholds;
- prior smoke results;
- the old Stage6 ON/OFF benchmark semantics;
- filesystem snapshot identity from that historical run.

### 3. Quota lifecycle invariants from `6db19db8`, `fe8ed9b5`, `bac017cd`

The old failure mode was a leaked active-request lease. The useful invariant is lifecycle correctness, not the runtime patch itself.

The isolated harness must prove:

1. preflight active count is zero (or a documented clean expected value);
2. one admitted request acquires at most one active lease;
3. normal terminal completion releases it;
4. safe abstention/failure releases it;
5. client cancellation/timeout path releases it when exercised by a dedicated harness test;
6. post-batch active count returns to the preflight value;
7. HTTP 429 with `provider_calls=0` is infrastructure poison, not quality evidence, and stops the smoke;
8. owner bypass and public quota semantics are not silently conflated.

Session 04 should implement these as isolated tooling/probes around the isolated endpoint or test-owned quota store. It must not modify M26 public runtime just to make the smoke pass.

### 4. Production-stability guard from `3592b22b`

Reuse these hard rules:

- production health before and after every eval batch;
- only one non-production M27 container at a time;
- no concurrent docker build, pytest, and endpoint evaluation;
- no full523 continuous run on the 1 GiB production VM;
- stop immediately if production health is not HTTP 200;
- stop on low available memory or aggressive swap growth;
- stop and preserve evidence on HTTP 429/provider_calls=0;
- explicit container resource limits;
- stop the eval container after the session.

For the next small smoke, use an even narrower rule: one isolated endpoint, one small bounded batch, no 100-case/full523.

Wording must follow report 43 semantics. Host-level evaluation means production host impact was monitored; it is inaccurate to claim the host was completely untouched merely because production containers were not mutated.

## Runtime behavior modifications that are excluded

The following are not admission infrastructure and must not enter Sessions 04/05 by cherry-pick, copy, or accidental merge:

- `649908f2` changes to `m26_pa7_arbitrary_query_runtime.py`;
- `34f7b808` changes to `m26_aq_semantic_contract.py` and `m26_pa7_arbitrary_query_runtime.py`;
- `fe8ed9b5` changes to M26 public API runtime, even though their lifecycle lesson is retained;
- any dirty/uncommitted repair from `/home/ubuntu/LLM_Wiki-m27-context-runtime`;
- benchmark-specific Stage13/14 admission thresholds or historical PASS claims.

A future need for a runtime change must be independently justified and authorized. It cannot be smuggled in as "harness reuse."

## Clean plan for Session 04: isolated admission harness

Session 04 should start from the accepted post-bridge base chosen by the master, not from Stage13/14 branches. Its deliverable should be architecture-neutral tooling only.

Required components:

1. **Target guard**: loopback-only default, explicit isolated port allowlist/config, production hostname/IP deny rules, expected build-SHA check.
2. **Host preflight**: production `/v1/health` read-only check, production container/image identity capture, memory/swap/load capture, and assertion that no other M27 eval container is running.
3. **Quota preflight/probe**: read-only or test-owned inspection that establishes active-request state without altering production quota data.
4. **Generic SSE collector**: new schema name, bounded timeout, terminal-event validation, citation/abstention/latency/TTFT fields, and bridge identity fields.
5. **Safety stop rules**: fail closed on production health degradation, identity drift, target mismatch, quota poison, memory/swap guard, or malformed terminal stream.
6. **Postflight**: quota active count restored, isolated endpoint identity unchanged, production health and identity unchanged, eval container cleaned up.
7. **Unit tests**: target rejection, build mismatch, malformed SSE, 429 poison, quota lifecycle assertions, percentile/summary correctness, and no-network pure parser tests.

Session 04 must not run admission smoke. It prepares tooling and proves the tooling with unit/fixture tests only.

## Clean plan for Session 05: fresh small smoke

Session 05 may run only after both prerequisites are true:

- production-grade compiler/evidence bridge has a positive handoff from Session 01;
- Session 04 isolated admission harness is complete and its safety gates pass.

Execution order:

1. establish production read-only health/identity baseline;
2. establish host resource baseline and exclusivity;
3. build/start exactly one isolated image/container from the authorized clean commit, with explicit memory/CPU limits and read-only production-equivalent evidence inputs as authorized by Session 01;
4. verify isolated build identity and evidence/compiler binding before sending a question;
5. verify quota preflight clean state;
6. run a deliberately small fixed smoke set only;
7. after each case (or smallest practical micro-batch), evaluate hard stop conditions;
8. stop immediately on production degradation, identity drift, quota poison, target mismatch, malformed terminal transport, or host resource danger;
9. capture postflight quota/host/production receipts;
10. stop/remove the isolated eval container;
11. report observations without upgrading them to 100-case/full523 readiness unless a separate owner-authorized gate says so.

## Small-smoke evidence contract

Every case row should minimally include:

- case ID and question SHA-256;
- isolated endpoint and verified build identity;
- evidence/compiler bridge identity or digest;
- HTTP status and terminal event/code;
- cited final answer / safe abstention;
- citation count and citation-binding status;
- unsupported-claim metric with explicit measured/unknown state;
- provider-call count from authoritative telemetry when available;
- total latency, first SSE, first answer-text latency;
- quota pre/post active state;
- stop-reason field if the session terminates early.

The session summary should include production pre/post health and identity, host-resource receipts, isolated container identity, case-count bound, and whether any hard-stop condition fired.

## Why no code was extracted in this audit

The prompt permits a small extraction only when safe. The old runner is tightly named and shaped around Stage13, and the quota fix is coupled to public runtime. A clean generic harness needs new fail-closed target/identity/quota/stability contracts. Implementing that belongs in Session 04, where it can receive dedicated tests. Creating a partial helper here would increase cross-session ambiguity without reducing risk.

## Completion

`ADMISSION_INFRA_REUSE_PLAN_READY`

The audit found enough reusable design/evidence patterns to proceed, while excluding benchmark-specific runtime modifications. No admission was run and no production mutation occurred.
