# W3 M06I | AR06 local durable exclusion adapter receipts (v1)

**Bounded claim:** `AR06_LOCAL_DURABLE_EXCLUSION_PASS` only after real pinned scoped tests, Ruff, and exact allowlist Git commit. The adapter is **feature-off**, *not* a user-memory backend or Production policy authorizer.

## Composition, not duplication

- Invokes accepted `GovernanceBoundary` for explicit reviewed registration, in-process read checks, descendant registration, revocation propagation, snapshot restore and consumption checks.
- Calls accepted `DurableWriterV1.recover/read_head/update_authority` against the *same disposable SQLite file*. Run identity is bound to tenant, run, task, version, principal. The writer's verified AR02 chain and source/consent/exclusion generations fence admission. Its local revoke mirror is best-effort **after durable M06 exclusion**. A failure or crash between both commits cannot resurrect a locally tombstoned item because M06 always denies first.
- Accepts `AuthorizedReadPlan` only as an already-verified synthetic K03V plan; `authorize_fixture_read` invokes the actual accepted `VerifiedRightsConsumer.authorize_read` method after durable exclusion preflight, then performs a use-time revalidation. An old AR03 plan becomes ineligible after revocation. Neither the plan nor this adapter grants real publication rights.
- The current original I01 protected Q&A route is untouched. I01/K02D scoped regression demonstrates unchanged accepted test-only vertical. **No live integration into Production route**.

## Storage and crash/restart ordering

The new SQLite `m06_control` and `m06_receipts` tables are a separate metadata-only control plane. Each `REGISTER`, `DESCENDANT`, `REVOKE` is appended with SHA256 hash-chain predecessor and seq. SQLite `BEGIN IMMEDIATE`, WAL and FULL synchronous commit linearize local admits and revocations. Append-only UPDATE/DELETE triggers reject local ordinary receipt edits. Every admission reconstructs and compares sequence, payload chain, metadata pins, generation and tombstone state against the control row. An external SQLite administrator with full DB privileges could drop triggers or rewrite both chain and head, so this is **not an independently signed tamper-evident remote ledger**.

- Metadata: tenant + memory key, subject, purpose, source revision/digest and pin, consent version/generation, independent reviewer reference, review/retention expiration, exclusion generation and optional legal hold reference; **no memory body, embedding, user-secret bytes, memory value text or live provider token**.
- `register_reviewed` requires the exact accepted reviewer-approved object already held by the accepted `GovernanceBoundary`, fresh scoped read fixture, and matching verified AR02 run state. Agent-generated suggestions are never silently persisted.
- `admit` provides only a `MemoryTicket` containing a *synthetic* pointer to the already-reviewed in-process mock, not a live grant. `consume(operation=read|use|checkpoint|replay|cite)` rechecks the current ledger hash/generation, AR02 authority, and the original boundary, compares the whole ticket and denies before another local fixture consumption. Only a caller that genuinely gates actual use on `consume` gains the revocation fence; no distributed atomicity or external reader fence is asserted.
- `revoke` commits durable `REVOKE` first and increments exclusion generation once. Exact repeat of the same revocation ID/reason/hold returns unchanged seq/digest (idempotent), distinct repeated revocations are denied. A restart with no independent in-process reviewer fixture denies; restart with prior boundary also cannot resurrect a tombstone. Snapshot generation 0 is rejected after generation 1 tombstone.
- Descendants are recorded as linked metadata receipt events; any descendant use flows through the parent deny. Legal hold is `EXCEPTION_HELD` in original AR06 boundary and never an erasure receipt; reviewer expiry never becomes an erasure receipt.
- `actual_physical_purge(...)` is always denied until a separately designed and attested external deletion/observer protocol exists. Stored revocation payload sets `actual_physical_purge=false` and `external_erase_receipt=null`, unconditionally.

## Negative / fault matrix

Adversarial tests explicitly cover: consent rollback; stale exclusion generation; invalid fixture identity, tenant, subject, reason; repeat and conflicting revocations; expired reviewer; source/policy/ACL/consent/residency drift; no ledger; low budget; untracked descendants; old ticket invalidation; all read/use/checkpoint/replay/cite operations; held backup; snapshot resurrection after SQLite reconnect; AR02 source drift; injected AR02 mirror failure *after* durable exclusion; independent AR03 consumer and post-grant revoke; ordinary SQLite receipt UPDATE/DELETE forbidden; metadata/control state drift; concurrent revocation-before-consume barrier. A fixture-authorized plan is **not** evidence of actual Provider or IdP authority.

## Exact test/receipt commands

```sh
cd /Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/06_WORKSITES/W3_M06I_AR06_MEMORY_DURABLE
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_m27_w3_ar06_durable_governance_v1_experimental.py \
  tests/test_m27_ar06_governed_memory_experimental.py \
  tests/test_m27_i01_core_local_vertical_v1_experimental.py \
  tests/test_m27_ar02_durable_writer_v1_experimental.py \
  tests/test_m27_ar03_verified_rights_v1_experimental.py \
  tests/test_m27_ar03_context_broker_experimental.py \
  tests/test_m27_ar02_reconciliation_v2_experimental.py
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m ruff check --no-cache \
  src/knowledge_engine/m27_w3_ar06_durable_governance_v1_experimental.py \
  tests/test_m27_w3_ar06_durable_governance_v1_experimental.py
```

## Mandatory missing external gates

**OPEN**: authentic identity/consent via IdP, legal hold and custodian attestations, external independently verified physical purge receipts for original/vector/graph/cache/backup/provider children, real AR03 Provider rights and citation, live source ACL, actual physical erasure, true text-stream ACK, external billing, real research/coding TaskOutcome, REL01 523-case quality+latency native-Q&A holdout, REL02 release and Production. Local green tests do not waive any gate. Owner/Master must independently re-run and inspect three file hashes and Git scope before W4 I02/E09.
