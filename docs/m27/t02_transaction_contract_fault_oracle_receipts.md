# T02 | AR02 Single-Writer Transaction Contract & Crash Fault Oracle

**Classification:** fresh independent *inert protocol validation* from accepted AR09C HEAD `144ff8694b2a8a7b01b0349a1c8e99d524193e71`. This is NOT an implementation of the previously refused AR02B-R SQLite edit. No SQLite, database backend, Provider, IdP, durable journal, outbox dispatcher, authorizing API, source or Production mutation.

## What the accepted baseline proves and cannot prove

- The original accepted `Kernel` (`m27_ar02_kernel_experimental.py`) exposes `create`, `reserve`, `charge`, `intent`, `claim`, `possible_send`, `terminal`, `cas`, and `takeover` for a single-process dictionary. In the accepted C02 sequence, `possible_send` returns an **unknown effect** at original head5 and `terminal` explicitly refuses success while unknown.
- The accepted `ReconciliationKernelV2` has public `record_verified_reconciliation`, `current_snapshot`, `terminal_cas`, and `append_postterminal_notice`. Fake signed T4 produces an isolated in-memory head6; the fake verifier and ACK support a separate in-memory head7 terminal. The original Kernel remains head5 UNKNOWN, nonterminal.
- `ReconciliationKernelV2` uses `threading.RLock` only inside a process. A lock, fake HMAC, returned fixture ACK, and an event hash are **not** ACID, remotely authenticated evidence, or a crash-persistent writer.
- Accepted AR09C judged the synthetic successful loop as `MOCK_ONLY_FUNCTIONAL_SUCCESS`, with `no_durable=True`, `no_provider=True`, `no_real_tool=True`, `authorized_task_success=False`. The current T02 adds no genuine authority.

## Immutable input/output types

`TransactionIntentContract`: exact tenant/run/task/version/attempt, T1 action digest and approval, CAS head and lease epoch, reservation and charge identity/microunits, outbox claim and idempotency key, consent/exclusion generation, source revision, expiry. These are **required bindings**, not a permit.

`WriterSnapshotFixture`: one synthetic immutable observation of the proposed sole writer's RunEvent head/hash/epoch, budget and charge ledger, T1 committed intent, T2 committed claim, unknown T3, T4 phase, source policy state and terminal bit. It cannot authenticate its own ledger or survive process loss.

`OutboxClaimContract`: fixture markers for intent-commit ACK, claim-commit ACK, single physical-attempt marker and epoch/idempotency binding. Assertions that these fields are true DO NOT prove a disk flush, an fsync, real signed receipt, permission to dispatch or exactly-once effects. `assess_contract` NEVER authorizes dispatch.

`ReconciliationObligation`: independently observed T4 should bind tenant/run/task/version, original T1 digest, action identity, current head hash/lease and unexpired independent evidence. For a *successful* terminal the proof must report CONFIRMED_APPLIED, not CONFIRMED_NOT_APPLIED or UNKNOWN. This pure fixture validator validates consistency, not signatures or observer authorization.

`DurabilityObligation`: mandatory one AR02 writer and serializable transaction requirements; **true flags mean REQUIRED, never verified**. `ContractDecision` has `mock_policy_contract_pass` plus constants `durable_verified=False`, `backend_writer_present=False`, `provider_dispatch_authorized=False`, `AR02_STAGE_DONE=False`. No real outcome inference is possible.

## Minimum atomic, sole-writer real storage boundary (future separately authorized work)

1. `begin_serializable_run_transaction`: choose an approved durable backend and immutable per-tenant/run fencing key; enforce lease epoch and writer uniqueness. No other agent/module mutates these records.
2. `compare_and_append_event_head`: original RunEvent head/epoch/hash, canonical event bytes and authority provenance must be read and CAS-appended together. Conflicts abort all accompanying ledger/outbox changes. Hash matching is NOT signer authentication.
3. `atomic_reserve_charge_intent_claim`: reserve microunits with budget invariant; one charge identity and exact settlement; bind immutable T1 digest, approval, single-use outbox claim and physical-attempt marker in **the same serializable transaction**. No implicit zero price, negative amount, duplicate reservation, replay or epoch-swapped permit.
4. `verify_durable_commit_ack_before_dispatch`: require a verifiable durable commit acknowledgment for T1 and fenced attempt claim before any AR04 attempt; missing or ambiguous ACK is **DENY**, not optimistic retry. The API must expose whether ACK is an authentic store commit confirmation; a fixture boolean is insufficient.
5. `recover_pending_outbox_without_blind_redispatch`: on crash/restart, reconstruct authoritative head/reservation/charge/claimed attempts; distinguish uncommitted work, claim-but-no-effect, and possibly applied effects. A remote provider without true deduplication CANNOT guarantee exactly once. UNKNOWN requires independent observer reconciliation, never blind physical retry.
6. `commit_t4_and_terminal_with_head_cas`: persist independently verified T4 observation/effect, observer signer+authorized-read proof, original T1 and current head binding, AR05 signed post-reconcile verifier result, hard-gate freshness, and irreversible terminal under a single writer transaction. Repeat verification after head/epoch/source/consent/exclusion changes.
7. `query_revocation_consent_and_source_revision`: read current monotonic exclusion/revocation generation and provider rights on each authorize/replay/publication path; deny stale checkpoints and invalid source. The future backend must specify clock, immutable hashes, retention/erasure and trust-grade design independently.
8. `seal_immutable_terminal_and_sidecar_notice`: no terminal reopening; correction/retraction must be linked append-only sidecar with immutable cursor/provenance and independent publication policy.

The real implementing package must select a transactional backend and write/restore API, specify authoritative ACLs/identity and exact canonical wire schema, perform real crash injection and independent tests, and receive separate authorization. **T02 implements none of the above methods**, only enumerates their required names.

## Fault model expectations (synthetic, zero provider effects)

| Crash boundary | Correct fail-closed resumption |
|---|---|
| Before intent transaction commit | `DENY_UNCOMMITTED_INTENT_AND_ROLL_BACK`. Cannot see durable intent or dispatch. |
| After intent commit, before claim | `RELOAD_HEAD_AND_REEVALUATE_CLAIM`. Only recheck a new fenced claim; no auto-send. |
| After claim, before physical send | `REVALIDATE_ACK_LEASE_AND_ATTEMPT_NO_AUTO_SEND`. Reconcile the commit/attempt marker and expiration first. |
| Lost commit ACK before dispatch | `DENY_AND_REVALIDATE_DURABLE_COMMIT`. Uncertain ACK is not authority to send. |
| Remote effect may have happened, observer missing | `INDEPENDENT_T4_RECONCILIATION_NO_RETRY`; remains `T3_UNKNOWN_EFFECT`, no blind duplicate. |
| Observer recorded, terminal not committed | `REVERIFY_T4_CURRENT_HEAD_THEN_TERMINAL_CAS`; stale/forged/expired/revoked proof denies success. |

All fault-model results have `may_dispatch=False` and `double_charge_allowed=False`. This is a normative recovery decision table, **not an executable recovery engine**.

## Negative oracle and replay implications

The new test suite runs dozens of adversarial fixture checks and five direct accepted original Kernel public-API checks: overlapping CAS, concurrent reserve overcommit, epoch takeover, charge replay idempotency, conflicting charge replay. It also exercises C02's actual public positive mock loop and deterministic *recreation* from the same T3 original fixture. Original Kernel remains head5 UNKNOWN even after successor head7; a newly constructed identical in-memory successor begins at T3 head5, terminal absent. This identifies a critical persistent-completion GAP but is **not a real OS-kill/fsync crash test**. The honest real crash-injection acceptance remains outstanding.

The fixture intentionally does NOT claim to verify cryptographic signer identity, a real authoritative head, storage isolation, provider idempotency, reversible actions, actual client receipt, live billing, or real durable state. The accepted C02/AR09C public APIs, intact in the parent branch, separately verify only mock HMAC and locally consistent event hashes. A malicious actor able to forge both the supplied fixture head and proof is **outside the trust model** and must be blocked by the future original-writer plus independent verifier authority, not by this fixture model.

## Safety, scope and release meaning

Only 3 additive files within `src/`, `tests/`, and `docs/m27/` belong to T02; no accepted files edited. Historical AR02B-R denied patch/environment operation remains frozen. No alternate tool routing for explicit safety denials, no VM/Production, no provider, no credentials, no network. No push/merge/cherry-pick.

Worker success classification: **TRANSACTION_CONTRACT_ORACLE_OFFLINE_PASS ONLY**. C02 and AR09C are accepted **mock components**; T02 is **WORKER_REPORTED pending Master independent acceptance**. AR02 true authorized integration, durable writer and actual Production remain **OPEN / NOT IMPLEMENTED**. AR02_STAGE_DONE = false.
