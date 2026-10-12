# ADR-I28-001 | Frozen local Task/Outcome ABI composition (2026-10-12)

**Status:** LOCAL NONPROD ENGINEERING CANDIDATE ONLY. **Formal ABI ratification: OPEN.**
This ADR does not issue an IdP, service, rights, consent, evaluator, or production authorization.

## Owned base and source decisions

- Base clean T27 commit `8604752934fb43a3441055d33c01940028cc5938`.
- D28 `e416a1bdbba830687ec77d2845cd2e758a393791`, M28 `16c14823b7d5b7c3990caa30191ce8bd47567a58` imported as actual code.
- K28 `089117ec9242e7bc4efa640f332759ca4c1bc73b` imported as real-SIGKILL fault oracle; P28 `b90ff73399f4ff187c3a5a8a7327ec57e117cbe1` imported only as nonproduction packaging evidence.
- No sibling worktree rebase, reset, branch overwrite or live P28R input. Original W4 I02 and W5 G25R/T27 code bytes inherited from immutable T27 baseline; T27 Chrome client is read directly from its original committed file.

## Chosen engineering contract

The existing M26 SSE, original source citation, W4 I02 RunEvent, and historical client bytes are untouched. The D28 registry supports opt-in-only disjoint envelopes: `(ar01v.envelope,1.0.0)` for sidecar-bound legacy bytes; `(ar01z.new-record,1.0.0)` for new-only revocation/billing/notice records. No silently mutating legacy frames, default reader downgrade, cross-tenant field substitution, or unsupported-version fallback. The unmodified M26 legacy source and D28 byte goldens are the acceptance guard. The I28 localhost Chrome/C24 stream adapter is a test-only client wire, **not** a formally ratified production SSE replacement.

Task/Outcome flow: fixed local request -> I02 TaskContract and AR02 WAL journal/epoch/source revision -> AR03 fixture authority + M28 durable rights/generation gate -> AR07 bounded compute and AR08 QA/Research/Coding -> independently received T27 Chrome/C24 client bytes or hashed Markdown/coding fixture -> AR09 evidence intake with external oracle unavailable -> AR10 offline candidate-only journal, without automatic promotion. In-flight enqueue/flush, replay, and coding subprocess send each consult the M28 generation fence. T27 browser and C24 client are distinct OS processes. A dedicated I28 OS child reopens the revoked original journal/tenant store after a real parent-side tombstone; K28 SIGKILL/restart is separately run against the same frozen imported source. No action grants other than the fixed reversible local coding fixture.

## Authority and external exit gates

These remain FALSE: `FORMAL_ABI_RATIFIED`, `EXTERNAL_SOURCE_RIGHTS_VALIDATED`, `REAL_PROVIDER_IDEMPOTENCY_VERIFIED`, `AUTHENTIC_NATIVE_ACK`, `INDEPENDENT_EVALUATOR_APPROVED`, `ARTIFACT_EXTERNAL_ACCEPTANCE`, `SIGNED_CURRENT_I28_OCI`, `REL01_CERTIFIED`, `REL02_AUTHORIZED`, `PRODUCTION_AUTHORIZED`.

All source/right/consent and all remote side effects are synthetic private local fixtures. Model output never produces authority. Quarantined backup does not mean physically erased. UNKNOWN, revoked, denied and cancelled remain assigned; not converted into successes. C24's signed custody is UNKNOWN. AR09's unavailable oracle yields `ORACLE_UNAVAILABLE`, not an independent quality result. AR10 registers a DRAFT-like candidate-only proposal but never advances or writes a release.

P28's original canonical M26 lifespan boot failed exit3 because a legitimately approved release manifest is missing. Using `--lifespan off` yielded HTTP 200/starting, **not ready**. P28R later patch (if any) remains a distinct branch for V28's independent reviewed integration. Existing unsigned T27 OCI is not repurposed as a signed I28 runtime. I28 code freeze requires immutable clean Git HEAD/tree and separate machine observer. External rollout, 523/200 official blind evidence, signed OCI/rollback and Production are all out of scope.

## Reversal and security

All I28 work confined to a new isolated worktree and V3 local evidence. No Production, public Nginx, paid Provider, external SaaS write, private blind corpus, privileged GitHub workflow, default M26 bundle creation, protected Master State write or old sibling source mutation. This is a frozen **local test candidate**, not a release gate.
