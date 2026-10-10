# W3 C07I | AR07 local compute budget CAS receipts

Component: src/knowledge_engine/m27_w3_ar07_compute_budget_v1_experimental.py
Adversarial suite: tests/test_m27_w3_ar07_compute_budget_v1_experimental.py
Original clean seed: 067dda88d8cbd58fbd6f4c694a382d354eb8fccb
Local acceptance label: AR07_LOCAL_CAS_ROUTING_PASS
Real Provider and economic qualification: OPEN

## Implemented behavior

LocalComputeBudget.reserve_and_fence takes a pinned Attempt. It re-evaluates
the existing accepted C07 propose_compute policy rather than trusting a
caller-supplied approval. It verifies tenant/run/task/version/principal via
RunIdentity and the AR02 journal; binds exact current head, epoch, journal
sequence as budget version, remaining money, source revision, consent and
exclusion generations, authorized revision and current revocation status.

The selected PriceSnapshotFixture is uniquely named, not stale, from an
approved test-only provider, for the exact model revision and MICROUSD
currency. It is not a market price or a live pricing authority.

An AR02 DurableWriterV1 reserve uses the existing WAL+FULL chain-verified
single-writer CAS. A local SQLite sidecar pins route, quote, consent and
request_key; then a synthetic approval, T1/T2 intent/outbox claim, local
ACK and T3 POSSIBLY_SENT fence are durably recorded. Only then does the
method return a local receipt; there is *no* dispatch method or external
Provider call.

An InvoiceFixture for the pinned route/price can settle one AR02 charge.
The usage identity and charge are unique; duplicate/conflicting usage,
repeated attempts and unplanned token usage fail closed. Positive cost
overruns and late bill adjustments are recorded in the AR02 adjustment
ledger, and must remain economically unqualified.

A newly opened SQLite writer and LocalComputeBudget can recover reserved
and spent counters and detect unknown attempts. Further spending remains
blocked on unresolved possible sends or untracked reservations.

## Real SQLite transaction / failure boundaries

AR02 reserve, synthetic approval, claim, local claim ACK and T3 are
individually ACID CAS SQLite transactions, *not* one global transaction.
The sidecar and each AR02 write are separate transactions; crash injection
after reserve, after approval, after claim, after local ACK and after T3
demonstrates fail-closed recovery rather than unsafe automatic retries.
Local recovery is not exactly-once remote invocation.

## Executable coverage

- Interactive QA and long research/coding take distinct policy paths.
- The accepted C07 policy and I01 core, AR02 durable writer are regression
  tested against the same pinned interpreter.
- New adversarial cases cover concurrent attempts exhausting the same cost
  cap, stale head/epoch, identity/tenant/source/consent/exclusion/version,
  revocation, expired/missing/double/unknown quote, currency/model mismatch,
  canceled or timed-out requests, unknown effect and interrupted reservations.
- Separate invoice cases cover duplicate usage, bad invoice dimensions,
  over-reservation and late billing, one immutable usage charge and live
  AR02 spent-vs-reserved counters across fresh SQLite connections.
- Fake StreamFrameFixture never constitutes authenticated client delivery.

Scoped test command, from the isolated W3_C07I_AR07_COMPUTE_BUDGET worktree:
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q
-p no:cacheprovider tests/test_m27_w3_ar07_compute_budget_v1_experimental.py
tests/test_m27_ar07_compute_policy_experimental.py
tests/test_m27_ar02_durable_writer_v1_experimental.py
tests/test_m27_i01_core_local_vertical_v1_experimental.py

Ruff uses python -B -m ruff check --no-cache scoped to the two new Python
paths only. The actual exit-code receipts, file SHA256 and Git evidence
are in the worker REPORT and evidence-index scratch directory.

## Open gates, deliberately NOT established

There is no authentic Provider price, actual call or billing, IdP-issued
consent/read rights, authenticated streamed first-answer/client ACK, real
research/coding external TaskOutcome, measured latency p95 or 523-QA score,
actual physical memory purge, original M26 protected Q&A route, external
tool-effect reconciliation, REL01/REL02 approval, or Production release.
Local worker PASS never automatically unlocks W4.
