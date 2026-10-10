# K02D Durable Writer v1 | Independent experimental receipt

**Status boundary:** A NEW, locally executable, feature-off SQLite transactional component.
No external side effect, IdP/read grant, production source read, genuine provider observer,
authentic approval issuer, independently controlled verifier, transport ACK, or billing
invoice is supplied. `DURABLE_LOCAL_COMPONENT_PASS` applies **only** after real
tests and scoped Ruff complete successfully. `AR02_STAGE_DONE = False`; no I01
or Production acceptance is implied.

## Storage contract

- One file-backed SQLite database using Python 3.11 `sqlite3`; each mutation gets
  `BEGIN IMMEDIATE`, WAL, `synchronous=FULL`, FK and uniqueness constraints,
  and commits before returning. SQLite guarantees atomic local database commits
  according to host filesystem guarantees. Power-loss promises beyond these
  SQLite/filesystem contracts or true remote exactly-once are NOT made.
- `RunIdentity(tenant_id, run_id, task_id, task_version, principal_id)` is
  checked on every read/mutation. `Head(seq, digest, epoch, state, budget, reserved,
  spent)` is an explicit caller-visible CAS fence.
- Domain-separated SHA-256 genesis and canonical JSON event hash chaining. Every
  operation verifies the entire sequential chain and compares its terminal hash
  to the runs table. Append-only event trigger forbids updates/deletes in normal
  SQL. This is tamper-evidence for chain records, **not** a signed audit trail;
  arbitrary SQLite administrators can change tables/triggers and mutable balances
  are not independently cryptographically authenticated.
- `reserve` fences budget and uniqueness. `charge` consumes one reservation,
  records globally unique `charge_id`, atomically releases reserved cap and adds
  known amount to spent. Unknown charges, negative amounts, repeats and overcap
  charges fail closed. **Not** real invoice reconciliation.
- `provision_fixture_approval` works only with
  `fixture_approval_mode=True`. Its records cannot authorize a real effect.
  `commit_intent_and_claim` atomically validates original intent digest,
  principal/tenant/task, lease, expiry, price reservation, source rev and generation;
  consumes single-use fixture approval and inserts immutable intent, unique
  idempotency key, claim and pending outbox in one commit.
- `claim_outbox` allows one durable local claim, returns a commit-token only
  after transaction commit. Lost response **does not** permit re-claim or
  dispatch; `recover` exposes the `CLAIMED` quarantine state. The token is
  neither external authorization nor a remote dispatch permit.
- `mark_possible_send` accepts the original token once and durably sets
  `POSSIBLY_SENT`/`T3_UNKNOWN_EFFECT` before an application *could* reach
  a remote boundary. It performs **zero** external sends. An unknown outcome
  is never auto-retried; recovery never dispatches.
- `record_observer_reconciliation` requires T3, original T1 digest, observer
  identity distinct from executor, exact current head/epoch, evidence SHA-256
  reference, observer outcome, expiry, source revision, consent/exclusion
  generation. Stores a T4 record clearly marked **UNATTESTED**. Caller-supplied
  independent evidence reference is NOT authenticated by this repository.
- `commit_terminal` requires matching T4 outcome, a separately supplied
  verification reference, current head and generation, an explicit local HMAC
  verifier-key proof over canonical run/head/epoch/evidence/outcome bytes, no
  unresolved T3, and three distinct nominal actors. It atomically commits only
  `LOCAL_VERIFIED_APPLIED` or `LOCAL_VERIFIED_NOT_APPLIED`; **not**
  `SUCCEEDED` or real final-answer publication. The fixture HMAC key is
  synthetic and cannot establish independent signer custody.
- `takeover` increments epoch and invalidates earlier approvals and old worker
  CAS. `update_authority` advances monotonic generations and can permanently
  fence revocation, with append-only event. `audit_charge_adjustment` writes a
  uniquely keyed sidecar correction linked to an existing charge; it does not
  reopen terminal or rewrite original spend, and is shown separately via
  `recover().corrected_spent`. Sidecar does not claim externally verified fees.
- `recover` scans/validates the chain, reports outbox and state, never sends,
  and sets `dispatch_authorized=False` and `AR02_STAGE_DONE=False`.
  This module never exposes a `trusted=True` bypass.

## Explicit workflow

```python
writer = DurableWriterV1(db_path, fixture_approval_mode=True,
                         verifier_keys={"verifier-a": synthetic_test_key})
identity = RunIdentity("tenant", "run", "task", 1, "executor")
head = writer.create_run(identity, budget=100, source_revision="rev1",
                         consent_generation=1, exclusion_generation=1)
head = writer.reserve(identity, head, reserve_id="r1", amount=25)
head = writer.provision_fixture_approval(identity, head,
                   approval_id="a1", intent_digest="immutable-digest",
                   expires_at=100)
head = writer.commit_intent_and_claim(identity, head, intent_id="i1",
                   intent_digest="immutable-digest", approval_id="a1",
                   claim_id="c1", reserve_id="r1",
                   idempotency_key="idem1", now=10)
head, local_ack = writer.claim_outbox(identity, head, claim_id="c1")
head = writer.mark_possible_send(identity, head, claim_id="c1",
                                 local_ack_token=local_ack)
# NO provider send occurs; subsequent T4 reference is separately supplied.
# Independently obtained and verified real observer/signer authority is NOT
# implemented and must be a separately authorized integration.
```

## Synthetic tests and failure boundaries

The new tests use real disk files under the named evidence scratch pytest
basetemp and independent SQLite connections/processes. Included: process
`os._exit(29)` pre-commit vs post-commit, two competing independent PIDs
sharing one CAS head and budget, chain tamper rejection, forced transaction
exception rollback, hot restart in an independent Python process, lost commit
ACK, double claim/send/charge, foreign tenant/identity, stale CAS/epoch,
takeover, generation drift/revocation, missing T4, mismatched signatures,
postterminal immutability and late invoice correction sidecar. Exact run
receipts, exit codes and SHA-256 are in the separately written K02D report.

**Follow-on requirements:** independent external approval identity, source
read grant and rights, real provider transport/idempotency semantics, authorized
observer/negative completeness, independent signer custody, genuine client ACK,
invoice reconciliation, benchmark/holdout, and independently accepted I01 ABI
are all OPEN. Prior refused AR02B-R and other blocked operations remain frozen.
