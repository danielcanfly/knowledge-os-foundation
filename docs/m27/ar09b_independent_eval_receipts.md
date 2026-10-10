# AR09B / E01 | Independent Offline Outcome Evaluator Receipts

**Capability:** T0/T1 synthetic, deterministic, isolated. **Release:** HOLD. This is a runnable evaluator with separated synthetic oracle inputs, not a trusted blind independent scorer, real cryptographic signer, or real evidence authority. No production call, real Provider, network, invoice, live rights, tool execution, native Q&A integration or release gate.

## Typed contracts

- OutcomeEvidence binds case/tenant/task/version/run/revision, journal head (seq/hash), terminal status/durability, alleged evaluator/oracle, result digest, rights, remote unknown effect, timestamps, client-received segments, invoice charges and mock resource version.
- TrustedObservation is a **separate input** from executor evidence. It pins the exact identity/revision/head, independently supplied outcome/digest, oracle identity, mock remote version, rights, verified-segment hashes and known refusal expectation. It is **not authenticated by this offline harness**. Real integration must never construct it from executor claims.
- EvaluationContext is a separate mock allowlist and optionally a frozen assigned-case manifest; an allowlisted string does **not** constitute signed oracle authority or permission.
- CaseDecision separates task_success, terminal_correct, denied, refusal_correct, evidence_valid and stream_ok. Quality score is always None and quality_status is BLOCKED_EXTERNAL_ORACLE.
- BatchMetrics reports accepted / assigned, known-denominator refusal accuracy, evidence invalidity, latency nearest-rank p50/p95/p99 and declared buckets, verified *client* first-text time, costs of all attempts incl failed/cancelled and reconciled late fees, cost/success, unknown effects, security violations and completion by workload.
- Missing or unknown evidence fails closed. Correct ABSTAIN, CANCELLED or FAILED terminal is not a successful task. No purported fixture score can become an independent grade of 85.

## Explicit execution ledger (T0/T1)

| Scenario | Executed scope |
|---|---|
| ANSWER result/head/digest, verified client text before terminal | IMPLEMENTED in new tests |
| ARTIFACT/ACTION digest; mock remote revision comparison | IMPLEMENTED in new tests |
| ABSTAIN/CANCELLED/FAILED and refusal accuracy | IMPLEMENTED in new tests |
| Unknown/forged/withdrawn oracle; self-evaluator; mismatched tenant/task/run/revision/journal head | IMPLEMENTED in new tests |
| Rights withheld, UNKNOWN_EFFECT, duplicate fee, unreconciled late billing | IMPLEMENTED in new tests |
| Terminal-only/progress/unverified/undelivered text | IMPLEMENTED in new tests |
| Missing cost, no success, absent assigned cases, inclusive failure denominator | IMPLEMENTED in new tests |
| Legacy AR09A offline oracle regression | SCOPED TEST EXECUTED, see local evidence receipts |
| D01–D18 / N01–N28 exhaustive one-to-one coverage | NOT_RUN, only selected behavioural scenarios |
| Real independent signer/trust, source/read grants, signed approval | BLOCKED_EXTERNAL_ORACLE |
| Real remote-state, provider bills, native Q&A bytes and transport, recovery | NOT_RUN |
| Independent blind holdout, calibrated semantic rubric, real >=85 scorer | BLOCKED_EXTERNAL_ORACLE |
| Genuine Q&A/research/coding/action E2E, build/image lineage, owner release gate | NOT_RUN |

## Boundary and known gaps

1. Caller-supplied synthetic observations can demonstrate rejection of mismatches, not real independence, authentication, source authorization or correctness. SHA-256 binds bytes but is not a signature.
2. Mock verified_claim requires non-whitespace bytes, payload digest, oracle-catalog matching, citation IDs, client receipt flag and strict preterminal timestamps. It does not prove actual client delivery, claim semantics, legitimate citations or release SSE streaming.
3. Fixture invoices do not prove completeness of real billing. Duplicate charge IDs are rejected, but legitimate remote invoice reconciliation and budget caps remain unimplemented.
4. Workload percentiles are descriptive, with no sample size sufficiency, confidence intervals or economic ceiling approval. Final AR09 needs independent holdout and custodian, real quality scorer, attested source/image, cost/recovery and security E2E. REL01 remains separate and NOT CERTIFIED.
5. Only three NEW tracked paths belong to this packet. Prior AR09A, X10, Master state, C01 and M26 Production are untouched; no attempted platform-refused operations.

Final raw test/ruff/commit/hash receipts live outside the Git tree in 05_EVIDENCE_INDEX/AR09B_INDEPENDENT_OUTCOME_EVAL_TEST_RECEIPTS.md. Master alone adjudicates acceptance.
