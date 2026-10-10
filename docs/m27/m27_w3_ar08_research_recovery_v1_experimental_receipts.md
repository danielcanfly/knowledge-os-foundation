# W3 S08R | AR08 Research Recovery | Local experimental receipts v1

Protocol: `S08R/1.0/LOCAL_FIXTURE_ONLY`
Worker verdict, conditional on actual local test/artifact/commit evidence: `RESEARCH_LOCAL_RECOVERY_PASS`
**No external research completion, source authenticity, real IdP/Provider rights, external reviewer cryptographic identity, actual charging, publication, or authorized remote dispatch is claimed.**

## Change boundary

This worker adds one research source module, one executable test module, and this receipt document to an independently isolated worktree based on frozen W3 seed `067dda88d8cbd58fbd6f4c694a382d354eb8fccb`. It reads existing K02D `DurableWriterV1` through its real SQLite writer and accepted I01-derived local writer lineage. It does **not** change or execute I01's action path, original native Q&A, sibling worktrees, M26 Production, external providers, remote tools, Qdrant/R2, Git remote, or deployment.

### Executable local protocol

1. Frozen `ResearchPlan`: identity (tenant/run/task/principal/version), purpose, version, SHA256 of immutable research brief, hypotheses, ordered milestones, source pins with immutable original-byte digests, reviewer-independent evidence requirements, time/generation/ACL, budget reservation, and task deadline.
2. `admit()` binds the canonical plan SHA to the existing real K02D SQLite run and appends a K02D event in the *same* SQLite transaction as sidecar admission. Any altered plan/revision/tenant fails closed.
3. `reserve_budget()` invokes K02D's actual public `reserve()`. Its deterministic reservation identifier permits restart recovery if the process crashes **after** the journal commit but before the caller sees the acknowledgement; it never charges real money.
4. `register_source()` takes **actual bytes** supplied by a local fixture, checks the frozen digest/quote span, and stores the original bytes on disk. Model text or a model-generated citation is never an authoritative source. `record_review()` requires a separate reviewer identity and exact original source+revision+digest; these are local reviewer **fixtures**, not independently authenticated external signatures.
5. `checkpoint()` atomically appends a K02D hash-chained journal event and an ordered `milestone + resume cursor + parent digest` sidecar row. Crash-injection before commit rolls both back. Duplicate *identical* checkpoint replay has the same digest and no extra journal entry; a conflicting replay is rejected.
6. `resume()` verifies immutable plan, current live K02D chain, source revision/consent/exclusion/ACL/purpose/expiry, outbox ambiguity and job markers, all checkpoint hash links and corresponding K02D event hashes. Multiple SQLite connections observe the same cursor. Stale or revoked state cannot resume.
7. `claim_job()` commits a unique at-most-once `UNKNOWN_REMOTE` marker ahead of any possible remote side effect; there is **no remote dispatcher**. An ambiguous claim fences subsequent resume/proposal/retry rather than blindly executing a second effect.
8. `propose_artifact()` requires every milestone, pinned original source bytes, a separate accepted reviewer receipt for each source, explicit support **and counterevidence** for every frozen hypothesis, an exact matching K02D budget reservation and live source authority. It stores real Markdown BLOB bytes and journal-linked digest atomically. It neither emits to a client nor declares source conclusions externally verified. The blob is readable and byte/hash-verifiable after process restart; no terminal state is reopened.

### Real local test coverage (T0–T2 fixtures only)

- Deterministic happy path: actual SQLite WAL file, K02D reservation/event lineage, 3 ordered checkpoints, distinct support and counterevidence byte snapshots, two connection handles, restart and exact persisted Markdown artifact read-back.
- Parametric negative fixtures cover malformed identity and plan version, missing hypotheses/milestones, missing counterevidence, hallucinated/incorrect source bytes, source pin range, source disagreement and model-only citation, absent or rejected independent review, forged reviewer identity, stale consent/ACL/expiry/revision/taint, duplicate or out-of-order checkpoint, cost mismatch, missing reservation, unknown remote job claim, changed immutable plan, terminal supersession, corrupted checkpoint digest/cursor and corrupted artifact byte/hash.
- Fault injection: after plan insertion, after source insertion, **between AR02 journal append and checkpoint sidecar insert**, after checkpoint insert but before transaction commit, after fully committed K02D reservation (recover without duplicate reserve), after artifact journal append but before BLOB write, after artifact insert before commit, and after unknown-job marker before commit.
- No external trust is simulated as a real authorization. All statuses are explicitly `LOCAL_FIXTURE_ONLY`; no provider call, no real research claim, no authorization to publish.

### Reproduction / independent verification

From the exact isolated worktree, with the pre-existing pinned Python 3.11.15 and no installs/network:

```sh
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_m27_w3_ar08_research_recovery_v1_experimental.py \
  tests/test_m27_ar02_durable_writer_v1_experimental.py \
  tests/test_m27_i01_core_local_vertical_v1_experimental.py \
  tests/test_m27_ar02_reconciliation_v2_experimental.py \
  tests/test_m27_ar05_independent_verifier_v1_experimental.py \
  tests/test_m27_ar05_verification_experimental.py \
  tests/test_m27_ar02_ar05_reconciled_vertical_experimental.py \
  tests/test_m27_ar02_ar05_core_vertical_experimental.py
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m ruff check --no-cache \
  src/knowledge_engine/m27_w3_ar08_research_recovery_v1_experimental.py \
  tests/test_m27_w3_ar08_research_recovery_v1_experimental.py
```

Observed worker scoped pytest: **405 passed in 66.48 seconds, terminal exit 0** (8 suites including new). Observed new suite before adding two final restart/terminal regression cases: **71 passed**; final 8-suite run includes both additional fixtures. Observed Ruff: **All checks passed**, terminal exit 0. Raw local run transcripts, SQLite demo proof, real 1,031-byte Markdown source-derived artifact, checkpoint lineage and SHA evidence are indexed in the external `05_EVIDENCE_INDEX/W3_S08R_AR08_RESEARCH_RECOVERY_SCRATCH` directory. The final REPORT records exact paths, Git commit, parent and three verified file digests.

### Hard open gates

- Provider/IdP live ACL, consent/tombstone issuer and real source license/identities: **OPEN**.
- Independent externally signed source review and actual source coverage/ground-truth quality: **OPEN**.
- External research TaskOutcome, provider usage/pricing, immutable bills and external publication/receipt: **OPEN**.
- Genuine client-stream ACK, physical memory purge and native protected M26 Q&A benchmark: **OPEN**.
- Independent blinded AR09 holdout; REL01 523 Q&A quality, citation and first-text streaming gates; W4 I02/E09; REL02/public release: **NOT AUTHORIZED / OPEN**.

This document describes only isolated local component proof, never a product-success claim or automatic W4 authorization.