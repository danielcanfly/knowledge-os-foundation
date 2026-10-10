# W4 E09H | AR09 IndependentOutcomeHarnessV1 | Offline Component Receipts

**Verdict boundary:** `E09H_OFFLINE_INDEPENDENT_HARNESS_COMPONENT_PASS` applies only after actual scoped tests, Ruff, commit, SHA and clean tree. This is **Phase A, OFFLINE_FIXTURE_ONLY**. It is not independent unseen holdout, real economic evaluation, I02 readiness, REL01 certification or Production authorization.

## Sources and isolation

- Expected frozen W4 HEAD: `d14abc74759a3c2dcb53105be9516008ad07a1a6`.
- Source baseline: W4 Master five component seed, W3 Master acceptance, newest Master State V2, Tool Routing V5, existing AR09B and AR09C source/contracts and original independent outcomes.
- This module has **no dependency on I02**, no I02 worktree reads and no injection of I02 worker test answer files. It contains no Providers, IdP calls, production writes, network imports, platform remote actions or release activation.
- Exactly three new tracked files: standalone evaluator, standalone test suite, these receipts. Raw local logs/report are stored in existing Master `05_EVIDENCE_INDEX` and `02_REPORTS`, not added to the Git tree.

## Executable semantics

1. **Frozen Task / Outcome contract.** Separately supplied `Assignment` catalog determines eligibility and denominator. Every eligible assigned case counts exactly once, including missing, unknown, rejected, abstained and partial. `NOT_ELIGIBLE` is reserved for evaluator-assigned noneligible cases; executor may not self-exclude. Duplicate case submissions and distinct case IDs pointing to the same Task ID fail closed. Unassigned submissions cannot inflate success rate.
2. **Evidence Authority.** Source and Artifact actual bytes are SHA256-checked, with source ID, source revision, cross-tenant ACL, explicit consent, not-revoked state, issued/expiry timestamps and nonempty literal citation byte spans. Verifier/artifact and quality-grade signatures bind entire recorded payload to distinct externally configured *test* trust keys and role allowlists. Forged/missing/revoked/self-signed fixture evidence fails. These HMAC fixtures are **not genuine real IdP or signer credentials**; no input field can upgrade their authority.
3. **Q&A.** A quality grade is a separate role-attested rubric record with fact correctness, grounding and a score threshold of 85 (fixture gate only); no executor self-grade is trusted. Cited verified substantive UTF-8 text binds artifact bytes and source IDs. `server_flush_ms`, independent role-attested `client_ack_ms` and terminal time are checked in strict order; first client text is calculated from the ACK, not from a server write, SSE progress event or terminal-only receipt. Offline frame/ACK attestation is not a real browser receipt.
4. **Research.** Requires role-attested independently reviewed source list, counterevidence examination, SHA256 checkpoint and zero unfinished tasks. Signed quality rubric and artifact bytes are additionally checked.
5. **Coding / Action.** Requires a separate signed runner identity, observed test count, successful subprocess exit and artifact digest, plus independently signed scoped permit and independently signed effect observation with resolved UNKNOWN_EFFECT. The runner is a fixture record, not an OS security boundary or real CI. Neither the fixture grader nor the model can certify actual physical side effects.
6. **Recovery.** Independently sealed recovery evidence includes restart checks, checkpoint persistence, replay counts, idempotency/duplicate accounting and UNKNOWN_EFFECT. An unknown effect remains `UNKNOWN`, never `ACCEPTED`.
7. **FinOps.** A signed billing-role `Invoice` binds every attempt ID, unique charge ID, usage token counts, price per token and reconciled invoice total. Duplicate, delayed, absent, contradictory or unpriced bills turn cost into `None` (`UNKNOWN`) rather than zero. Cost per verified outcome uses the **entire eligible batch spend**, including failed attempts, over the verified accepted denominator. With zero verified outcomes or no complete authoritative ledger the ratio is `None`.
8. **Latency.** Q&A true first verified client text uses client ACK minus start; long task completion uses terminal minus start and has a separate descriptive percentile. Every Phase A latency is synthetic and explicitly **never** demonstrates product p95.
9. **Receipts.** Immutable `EvidenceManifest` and `EvaluationReceipt` carry case identity, checked source list/citations, artifact byte hash, authority failures and deterministic SHA256. A `DenominatorLedger` contains assigned/eligible/outcome counts, duplicate/unreported/unassigned records, known/unknown costs and timing buckets.

## Negative-first and fault-injection design

Executable parameterized independent suite includes at least 35 (actual count recorded in the report) distinct corruptions:

- Assigned case / task / version / tenant / workload mismatch, forced NOT_ELIGIBLE, worker holdout contamination, duplicate Task ID, duplicate Case ID and surprise submissions
- Actual source-byte and digest drift, forged or out-of-range citation spans, mismatched quotes, stale revision, missing source, duplicate citations
- Source expired, revoked, future issuance, missing consent, wrong tenant ACL, invalid/revoked/self-signed source/verifier/evaluator record and model self-rating
- Grade mismatched, fact incorrect, grounding false, rubric score less than 85
- Client ACK absent, late or after terminal, out-of-order flush, payload not in artifact, no citation, progress-only and forged client signature
- Research missing counterevidence, source list or checkpoint and unfinished tasks
- Coding fake runner, nonzero exit, missing tests or mismatched artifact SHA
- Permit expired/missing/wrong tenant, absent or unknown effect and contradictory observed remote state
- Restart or checkpoint failure, duplicate bookkeeping, replay count corruption, unknown action
- Invoice absent, delayed, unsigned, duplicated, incorrect total, invalid price/usage/attempt and unapproved cost denominator

Parameterized tests actually mutate evidence and invoke public `evaluate` behavior. They do not merely compare hardcoded expected label strings.

## Phase B and actual Release Gates: NOT EXECUTED

**Phase B requires all of:** a separately *Master accepted* immutable I02 commit; quarantined independently sealed held-out evaluation set from a distinct custodian; real source/IdP rights, signed independent verifier/observer and graded outcome authorities; genuine protected Q&A transport and client receipt; real runner/effect observations; complete Price/Usage/Invoice issuer reconciliation. Inputs generated by worker or tester are never called unseen holdout.

**REL01 requires a separate independent certification** of the original 523 question benchmark, cited final answer **≥95%**, original product p95 **≤15 seconds**, Verified First-Answer-Text Streaming (genuine substantive bytes and authenticated client receipt, separate from server flush/progress), independent semantic quality, security/recovery gates and real cost evidence. No fixture timing, local pytest, value of `TrustContext` or record labeled `EXTERNALLY_AUTHENTICATED` can turn `release_certification` into `PASS`. The evaluator will return `NOT_CERTIFIED` or `AWAITING_INDEPENDENT_523_RELEASE_CERTIFICATION` and cannot issue release authorization.

**All signatures, graders, source content, prices, client ACKs and runner/observer evidence in Phase A are synthetic demonstration inputs.** The module is a new isolation-safe harness component, not a substitute for live independent authority or a real hidden holdout.

## Execution references

- Raw logs: `05_EVIDENCE_INDEX/W4_E09H_AR09_INDEPENDENT_EVAL_SCRATCH/`
- Worker report: `02_REPORTS/W4_E09H_AR09_INDEPENDENT_EVALUATION_REPORT.md`
- Actual final pytest / Ruff / Git / SHA256 receipt values are in the worker report, not prefabricated in this document.
