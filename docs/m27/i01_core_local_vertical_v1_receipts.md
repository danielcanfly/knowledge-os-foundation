# I01 AR02→AR05 local vertical, v1 | test-fixture receipts

**State**: LOCAL FEATURE-OFF WORKER EVIDENCE ONLY. Exact success label:
`I01_LOCAL_TEST_VERTICAL_PASS`. Real/provider-integrated/release status remains
`EXTERNAL_AUTHORITY_REQUIRED`. This document does not claim external authority,
independent cryptographic key custody, authenticated client ACK, Production,
REL01 or REL02.

## Actual runtime composition

The single `I01CoreVerticalV1` entrypoint composes the four accepted component
APIs without copying their implementations:

1. **K02D / AR02**: `DurableWriterV1.create_run` creates an actual SQLite WAL
   journal with full synchronous commits. Callers use its cryptographic head,
   epoch, CAS, actual budget reservations, fixture approval record, transactional
   T1/T2 intent/claim/outbox, local durable ACK, T3 unknown fence, optional
   T4 reference, charge, and fixture-key local terminal CAS. It is the *sole*
   database writer. Two SQLite connections and crash/reopen are tested.
2. **K03V / AR03**: `VerifiedRightsConsumer.authorize_read` validates the
   independent fixture verifier's opaque signed-context equivalent (sealed token
   table, not real IdP signature), the trust registry, current checkpoint,
   effective actor/delegation, ACL/consent, source generation and original
   native ID/revision/byte spans. No source bytes are admitted to this
   orchestrator prior to read authorization. Fresh source bytes are checked
   again before the local T3/T4 and terminal boundaries.
3. **K04P / AR04**: `PermitSandboxV1` compiles an explicitly feature-OFF
   capability policy; `request → issue_permit → freeze_claim` freezes
   policy/approval/effective actor, head, epoch, consent and cost.
   `_DurableAR02Port` performs the real local SQLite claim transaction and
   returns only a **mock_only** local ACK. `simulate_fixture` runs strictly
   deterministic in-process with an independently identified fixture observer.
   `attempt_external` is never invoked. UNKNOWN_EFFECT is durable and
   *never* terminalized or retried.
4. **V05N / AR05**: `propose_eligibility` is called on an independently
   supplied fixture `EvidenceBundle` and local trust evaluator. I01
   cross-checks same task/run/post-T4+charge journal head and epoch, original
   source IDs, revision and bytes, citation spans, requested/completed claim,
   source revision and local charge. V05N opens the actual pinned artifact
   bytes and checks the separate test-only runner, rights, citation, independent
   observer, cost, fake signed client-ACK receipt, and verifier evidence root.
   Caller label alone cannot set eligibility. Even a passing V05N proposal
   never mutates AR02. Only a separate HMAC fixture signer against AR02's
   configured fixture-verifier key can allow the **local** final CAS.

## Evidence-grade boundaries

No actual IdP/Provider assertion, source ACL API, OS sandbox, live action
dispatch, independent external signer, real CI runner, actual client delivery,
published result, provider invoice, or authenticated production authority
is present. The test fixture's client-ACK proof is a signed *synthetic event*,
not an ACK inferred from server emit and not evidence that a real client
received bytes. The test `ExecutionReceipt` is synthetic and named fixture
data, not an independently run CI service. Local AR02 T4 is explicitly
`UNATTESTED`, local terminal is `LOCAL_VERIFIED_APPLIED`; not any
`AUTHORIZED_PROVIDER_SUCCESS` claim.

Absent independent fixture bundle/signer, the wrapper returns
`EXTERNAL_AUTHORITY_REQUIRED` without creating new claims or outside effects.
Unknown or negative fixture effect leaves the T3 journal durable/open with
no automatic replay. If fresh source/checkpoint, lease/head, observer or
verifier evidence fails, the code denies local terminalization.

## Failure surface and regression suites

New test suite covers 61 scenarios including genuine I01 all-module local
pass, two-connection SQLite visibility, crash/reopen and abrupt process exit,
rollback of uncommitted transaction, duplicate durable reservation/claim/charge,
wrong tenant/actor/task/version, forged issuer/key/audience/assertion, malicious
namespace/resource/command string, budget cap, expired consent, stale head/
lease/takeover, source bytes/revision/ACL/consent drift, missing fake issuer,
synthetic unknown T3, bad artifact hash, absent synthetic ACK, fake observer,
self-verification, role/sign domain mismatch, late invoice, invalid original
citation span, wrong source bytes/head, forged runner, unknown effect,
duplicate terminal and missing billing. It preserves the four source/test/docs
triplets unchanged and adds only the three I01 allowlisted paths.

## Repository/evidence pointers

- Integration source:
  `src/knowledge_engine/m27_i01_core_local_vertical_v1_experimental.py`
- Negative and local-success suite:
  `tests/test_m27_i01_core_local_vertical_v1_experimental.py`
- This contract and receipt:
  `docs/m27/i01_core_local_vertical_v1_receipts.md`
- Raw logs:
  `05_EVIDENCE_INDEX/I01_AR02_AR05_INTEGRATION_SCRATCH/`
- Worker report:
  `02_REPORTS/I01_AR02_AR05_CORE_INTEGRATION_REPORT.md`

**Invariant**: A worker PASS is not Master-independent acceptance. External
I01 authorized integration, AR08 release dependencies, REL01, REL02 and M26
Production remain pending independent external proofs and explicit release.
