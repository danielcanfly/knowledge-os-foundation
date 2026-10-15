# A06: Durable research plus reversible local observation

Owned standalone Nonprod adapter derived from clean I37 `216f912994d20d134b1c8af50f7b2dd1a1c89a15`. No changes to I37, Q34, Production, or other workers. Does **not** implement the historically refused same-dispatch persisted coding-source patch.

## Actual E2E

`python3.11 experiment.py` executed four first-party research-and-action flows using one immutable TaskContract per run:

- normal (terminal verified)
- actual child OS SIGKILL at checkpoint GATHERED_2 then new OS process resume same RunID (terminal verified)
- crash exit 73 after one physical effect but before SQLite receipt, then observe/reconcile with the same idempotency key and **no repeat effect** (terminal verified)
- reversible observation: actual file before/after then rollback, post-rollback independent verifier correctly rejects the formerly verified outcome

Physical state is only `a06/state/<run_id>/observation.json`. This is an approved Owner-owned reversible local observation, **not** a production or third-party API effect. Experiment log and receipt: `a06/evidence/experiment_results.json`, `a06/evidence/raw/`.

## Source grounding

Three copied exact-byte **owner-firstparty** project documents with individual source IDs `CHARTER`, `DELIVERY`, `I37_ACCEPTANCE`, manifest SHA-256, tenant/role claims, exact line and UTF-8 byte positions. Independent verifier opens raw source snapshots itself. This proves exact-byte provenance against the checked-in manifest, **not** cryptographic origin attestation of upstream owner documents and not semantic LLM quality. SOURCE ambiguity, SHA mismatch, ACL mismatch, cross-tenant, revocation all fail closed.

## Operational semantics

Runner provides SQLite WAL FULL-synchronous durable journal with RunID, checkpointed plan/source/tool/event chain, one-per-run idempotency ledger, max reads 3, action attempt budget 1, cancel, source revocation, unknown-effect observation/reconcile, rollback and an external read-only OS verifier `verifier.py`. Revoke/cancel after physical effect automatically compensates; if UNKNOWN cannot be observed, it is held and **cannot** terminal cancel or replay.

**Reproduce**: `/opt/homebrew/bin/python3.11 -m unittest -v a06.test_a06` from clone root (or cd `a06` and run `python3.11 -m unittest -v test_a06`). 25 tests including true child SIGKILL. Re-running `experiment.py` intentionally refuses to overwrite its durable primary run evidence. Run only in a fresh independent copy for a new experiment.

## Integration boundary

No private ABI merges. `INTEGRATION_CONTRACT_REQUEST.json` is a separate request for future Integrator. Provider, qualified IdP, real remote API, official sealed evaluation, original Q34 coding-source patch remain out of scope.