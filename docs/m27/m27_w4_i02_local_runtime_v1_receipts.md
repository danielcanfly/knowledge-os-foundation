# W4 I02 | AR02–AR08 Local Runtime v1 | Feature-off receipts

Scope: **local verified fixture experiment only**. Zero real Provider/IdP calls, no authenticated client ACK, no M26 Production, no physical purge, no economic billing certification. Composes accepted AR02–AR08 modules in a separate worktree.

## Entry point and boundaries

- I02LocalRuntimeV1(writer) requires DurableWriterV1(sqlite_path, fixture_approval_mode=True).
- TaskContract binds tenant, run, task version, actor, delegation, workload, pinned original source hash/revision, consent and exclusion generations, lease epoch, AR02 journal head, deadline and ACL.
- Admission recovers the AR02 hash chain and denies cross-identity, stale journal, stale source, expiry, revocation and unresolved possible-send effects. Caller-provided fixture booleans do not establish real IdP rights.
- Optional (DurableMemoryExclusion, MemoryTicket, ReadFixture) consumes a durable AR06 ticket on read, citation enqueue/flush, checkpoint, replay, artifact and before action. SQLite tombstones survive reopen and override cached state.
- Re-entry per process per run is refused. A fresh instance still refuses unresolved AR02 outbox. No unknown remote effect is automatically retried or terminalized.

## Real local component compositions

QA: runtime.qa first uses LocalComputeBudget.reserve_and_fence on AR02 SQLite CAS, then NativeQATransportAdapter on original exact NativeSourceBytes and CitationByteSpan, with external injectable independent *fixture* AR03/AR05 port checks. Runtime wraps each enqueue and flush with AR02/AR06 authority and original source-byte pin rechecks. Verified substantive first text is flushed before terminal, without any real Client ACK. Explicit InvoiceFixture allows a real local AR02 settlement; unknown invoice/price never silently costs zero. AR02 POSSIBLY_SENT is a fence, not proof of remote execution.

Research: runtime.research_workflow calls ResearchRecoveryV1 with same writer; admits frozen plan, reserves research cost once through AR02, saves original SQLite source BLOBs, independent fixture reviews, support/counterevidence, ordered milestone checkpoints. Reopens the writer and research module and validates the checkpoint digest chain before storing and re-reading actual Markdown artifact bytes. Research's internal AR02 reserve must **not** also be charged a duplicate AR07 model reservation. UNKNOWN_REMOTE job claims are not replayed. Monetary external qualification remains open.

Coding: runtime.coding uses CodingActionRunnerV1, the fixed ephemeral local answer.py and test_fixture.py fixture, a genuine single subprocess execution, AR04 PermitSandboxV1, AR02 T1/T2/T3/T4, local in-process observer, and independently provisioned AR05 fixture verifier. Validates exit code, stdout/stderr, SHA256, fixture path containment, terminal head and local charge. Nonzero exit or uncertain effects leave OPEN/UNKNOWN_EFFECT. No arbitrary file or remote command is enabled.

## Durability and limits

SQLite AR02 CAS and journal chain are authoritative locally, but reserve/approval/claim/possible-send/settle are separate durable transactions, not a globally atomic distributed unit. Crash may leave an unresolved reserve or unknown effect. Research checkpoint and BLOB journal update commit transactionally. AR06 revocation is written before propagation and replay is refused. QA stream callback failure may occur after the sink has seen bytes; quarantine and no blind retry are mandatory. Coding uses only a disposable fixture, not an OS-enforced generalized sandbox.

## Executable negative/fault matrix (unique pytest cases)

1. wrong actor; 2. self delegation; 3. missing contract ID; 4. source revision drift; 5. invalid source SHA; 6. wrong consent generation; 7. wrong exclusion generation; 8. lease mismatch; 9. missing purpose; 10. negative time; 11. deadline expiry; 12. ACL expiry; 13. revoked ACL; 14. non-fixture execution; 15. unknown workload; 16. wrong run; 17. wrong principal; 18. cross tenant; 19. wrong task version; 20. changed AR02 revision; 21. changed AR02 consent; 22. changed AR02 exclusion; 23. memory revocation between QA enqueue and flush; 24. wrong original citation bytes; 25. ambiguous flush; 26. expired research pin; 27. research wrong ACL; 28. research wrong purpose; 29. source tainted; 30. source wrong consent; 31. source wrong exclusion; 32. corrupt checkpoint after reopen; 33. absent counterevidence review; 34. UNKNOWN_REMOTE marker; 35. coding traversal path; 36. coding idempotency path escape; 37. disallowed program; 38. disallowed command; 39. mismatched source script SHA; 40. forged verifier; 41. lease takeover; 42. double permit/terminal; 43. nonzero coding exit; 44. multiworker CAS budget contention; 45. double/conflicting charge; 46. unknown pricing; 47. crash/reopen research reserve idempotency; 48. stale terminal CAS; 49. post-QA unknown outbox reopen; 50. missing client ACK remains unproven.

The QA, Research and Coding happy paths each exercise real local cross-module integrations and on-disk journal evidence, not isolated demos.

## Reproduction

Pinned interpreter: /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python.
Environment: PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.
Test command: python -B -m pytest -q -p no:cacheprovider tests/test_m27_w4_i02_local_runtime_v1_experimental.py.
Ruff command: python -B -m ruff check --no-cache src/knowledge_engine/m27_w4_i02_local_runtime_v1_experimental.py tests/test_m27_w4_i02_local_runtime_v1_experimental.py.
Actual 24-suite integration/regression commands and raw stdout/stderr/exit receipts retained in external 05_EVIDENCE_INDEX/W4_I02_AR02_AR08_RUNTIME_INTEGRATION_SCRATCH. REPORT.md records final exact Git parent/commit, SHA256 and clean state.

## Explicit nonclaims

Real IdP/Provider and source grants, authenticated consent, physical erasure, real provider billing, remote observers, genuine Client ACK, protected native M26 Q&A, independent AR09 hidden holdout, 523-item cited final answer at >=95%, p95<=15s and real first-answer-text TTFT, REL01, REL02 and Production readiness are unproven. The only possible PASS is local feature-off integration, subject to actual green scoped tests, lint, Git checks and independently checked receipt.
