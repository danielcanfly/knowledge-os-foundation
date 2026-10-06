# M27 Isolated Admission Infrastructure Reuse Audit Report (44b)

Status: `ADMISSION_INFRA_REUSE_PLAN_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-admission-infra-audit`
Branch: `m27/admission-infra-audit`
Base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## Mission and boundary

This session audited post-Stage12 commits `06681024..3592b22b` plus the reconciliation table in report 43. It did not run admission, did not mutate production, did not alter runtime behavior, and did not import dirty state from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.

The objective was to identify reusable evaluation, quota, smoke, and production-stability infrastructure while excluding benchmark-specific runtime changes.

## Audit conclusion

A clean reusable admission infrastructure path exists, but it should be reconstructed as isolated evaluation tooling rather than cherry-picked wholesale from Stage13/14 history.

Reusable concepts and isolated tooling patterns are strong enough to support Sessions 04 and 05. Runtime modifications from Stage13/14 remain excluded.

## Commit classification and reuse decision

| Commit | Existing category | Reuse decision | Rationale |
|---|---|---|---|
| `06681024` | D | reference only | Stage12 integration history; no executable admission infrastructure to import. |
| `6e147d23` | B | selective reimplementation | `tools/m27_stage13_admission_smoke.py` contains useful bounded SSE collection, latency, TTFT, citation, provider-call and abstention measurements. `scripts/m27_stage13_endpoint_quality.py` contains reusable request/evidence aggregation patterns, but its scorer and case wiring are Stage13-specific. Do not cherry-pick artifacts or benchmark decisions. |
| `c8f8f678` | D | reference only | Stage13 integration report. |
| `649908f2` | C | reject from reuse path | Benchmark-facing M26 runtime edits. Runtime authority and answer behavior are outside this audit. |
| `8799d774` | B | evidence-pattern reference only | Large endpoint proof corpus demonstrates isolated endpoint and read-only bundle proof patterns, but consists mainly of Stage14B benchmark artifacts rather than clean reusable code. |
| `34f7b808` | C | reject from reuse path | M26 canonical/legacy runtime modifications for Stage14B provider contract. |
| `8b567264` | D | reference only | Stage14 repair integration report. |
| `ab597e2a`, `5889fcbd`, `8dfeb516` | D | forensic only | Blocked smoke/quota evidence; useful for failure taxonomy, not source import. |
| `6db19db8` | D | design reference | Quota lease root-cause report precisely identifies terminal-state lease semantics. |
| `fe8ed9b5` | B | test semantics reusable; runtime patch excluded | The 10 quota lifecycle tests encode valuable invariants: release before terminal completion, idempotent release, no lease on failed acquire, no sequential poisoning. The source patch modifies M26 public API and therefore must not be imported in this session. |
| `bac017cd` | B | probe pattern reusable | Isolated quota probe and receipts are useful patterns for Session 04/05 validation, not source-of-truth runtime behavior. |
| `a946933f` | D | reference only | Quota integration report. |
| `3d1dcae0` | B | runbook/evidence pattern reusable | Fresh isolated image, read-only bundle mount, before/after production health, active lease zero checks, and smoke artifact receipts are reusable. Stage13R2 case corpus and gate decisions are not. |
| `09aa3a1e` | D | reference only | Stage13R2 integration report. |
| `3592b22b` | D | policy reusable after correction | Single-VM production-first constraints are useful. Historical restart-policy mutation from report 30 must not be repeated. The new plan treats production as read-only and uses health/identity observation only. |

## Reusable isolated admission harness contract

The following elements can be reused or rebuilt without changing runtime behavior:

1. **Bounded endpoint collector**
   - Localhost-only target supplied explicitly by caller.
   - POST question payload to `/v1/answers`.
   - Parse SSE incrementally.
   - Record first SSE time, first answer-text time, terminal event, latency, HTTP status, provider-call count, citation count, safe abstention and transport errors.
   - Hash question and answer for receipts instead of storing unnecessary raw content.

2. **Evidence validity rules**
   - HTTP 429 with `provider_calls=0` is quota/admission evidence, never quality evidence.
   - Missing numeric unsupported-claim telemetry remains `null`; never reinterpret unknown as zero.
   - A cited final answer requires a completed terminal event, non-empty answer text and citation presence. Any stronger claim-support gate must come from the runtime/evidence bridge proven separately.
   - Preserve failed and blocked rows rather than silently filtering them.

3. **Isolated run manifest**
   - Base commit and image/container identity.
   - Explicit localhost port.
   - Read-only evidence bundle identity and manifest digest supplied by Session 01/bridge work.
   - Feature/config snapshot for the isolated endpoint.
   - Start/end production health and identity receipts.
   - Host memory/swap/load receipts.
   - Per-case rows plus aggregate summary.

4. **Quota lifecycle proof**
   - Do not transplant `fe8ed9b5` M26 API changes into the accepted runtime.
   - Reuse its invariants as black-box/isolated validation: sequential requests must not accumulate active leases; terminal completion/abstention/failure/cancel must leave no stale active request; 429 must occur only when the configured concurrency boundary is genuinely exceeded.
   - Any discovered lifecycle defect in the accepted runtime becomes a separate blocker/repair scope rather than an implicit admission-harness patch.

5. **Single-VM safety guard**
   - Production health must be HTTP 200 before and after each isolated batch.
   - Only one non-production M27 endpoint/container may run at a time.
   - No concurrent docker build, test run and endpoint evaluation.
   - Use explicit container resource limits; historical safe example was `--memory 384m --memory-swap 768m --cpus 0.75`.
   - Stop on production health failure, low memory/aggressive swap growth, or quota poison.
   - No production restart-policy change, restart, stop, rebuild, deployment, route mutation or production data-store write is authorized by this policy.

## Rejected imports

The following must not enter Sessions 04/05 through this audit branch:

- Stage14/14B M26 runtime/provider-contract patches from `649908f2` or `34f7b808`.
- Stage13/14 benchmark-specific answer repairs, retrieval tuning, generic-fallback repair, PA7 tuning, or scorer-driven runtime behavior.
- Historical benchmark result artifacts as fresh admission evidence.
- Dirty uncommitted files from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.
- Production quota sqlite resets or production quota-state mutation.
- Historical production restart-policy hardening from report 30.

## Why no code was extracted in this session

The useful code in the audited range is entangled with Stage13 naming, scorer/case assumptions, or M26 public-API runtime changes. A blind cherry-pick would violate the requirement to separate harness infrastructure from runtime behavior.

The safest small extraction is therefore deferred to Session 04, where a new neutral isolated collector can be authored directly against the accepted M27 base and the production-grade evidence bridge from Session 01. This keeps provenance obvious and makes unit tests authoritative for the new harness rather than inherited benchmark code.

## Plan for Session 04: isolated admission harness

Session 04 should implement a neutral tool, suggested location `tools/m27_isolated_admission_smoke.py`, with no import from production runtime internals.

Required behavior:

- Require explicit endpoint, cases file, output directory and timeout.
- Refuse non-loopback endpoint by default unless separately authorized.
- Parse SSE incrementally and emit deterministic JSONL rows + summary JSON.
- Preserve unknown telemetry as unknown.
- Emit run manifest containing git/image/bundle/config identities.
- Add unit tests for SSE parsing, terminal classification, percentile math, 429 invalidation, unknown unsupported-claim telemetry, output collision/refusal, and endpoint loopback guard.
- Do not contain benchmark thresholds or runtime repair logic.

Session 04 completion should establish a testable collector and manifest contract only. It should not run fresh admission unless its own prompt explicitly authorizes the smoke.

## Plan for Session 05: safe small smoke execution

Only after the production-grade compiler/evidence-bundle bridge is proven and Session 04 harness tests pass:

1. Verify production health/identity read-only.
2. Verify host RAM/swap/load and absence of other M27 eval containers.
3. Build/start exactly one isolated endpoint from an explicitly pinned accepted commit, with resource limits and read-only bundle mount.
4. Confirm isolated health, build identity, feature/config snapshot and bundle/manifest binding.
5. Run the smallest authorized smoke population sequentially.
6. Stop immediately on production health degradation, quota poison, provider-call-zero 429, bundle identity mismatch or host pressure.
7. Preserve all rows and receipts.
8. Stop/remove only the session-owned isolated container.
9. Re-check production health/identity and host metrics.
10. Return an evidence-based readiness decision. Do not infer 100-case/full523 readiness unless the Session 05 prompt explicitly defines that gate.

## Production boundary for Sessions 04/05

Allowed:
- read-only `/v1/health` checks;
- read-only container identity inspection;
- host metric inspection;
- one explicitly isolated non-production endpoint;
- isolated output directories and read-only evidence bundle mounts.

Forbidden:
- production restart/stop/rebuild/deploy;
- production route change;
- production R2/Qdrant/SQLite writes;
- production quota reset;
- importing Stage13/14 runtime patches;
- legacy Stage13/14 admission continuation;
- full523 unless separately authorized.

## Completion

`ADMISSION_INFRA_REUSE_PLAN_READY`

No admission was run. No runtime behavior was changed. No production mutation occurred.
