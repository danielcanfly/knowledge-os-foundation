# W4 P09 | Independent authority, source-rights and FinOps intake (T0 offline)

Date: 2026-10-10. **No actual external evidence admitted.** Component output for all local fixture records: \`P09_AUTHORITY_EVIDENCE_NOT_ADMITTED\`. This is bounded audit/intake engineering, not E09 Phase B or REL01 release qualification.

## Independently inspected, authorized nonsecret evidence

- \`07_MASTER_REBASE_20261010/MASTER_STATE_V2.json\` and \`TOOL_ROUTING_POLICY_V5.md\`: approved local W4 I02/E09H and per-command engineering limits.
- \`07_MASTER_REBASE_20261010/02_ACCEPTANCE/W4_I02_E09H_MASTER_ACCEPTANCE_20261010.md\`: two **separate** local acceptance lanes; 1,202 I02 and 182 E09H scoped test passes cannot certify real provider, signer, scorer, product/client ACK, billing or blinded holdout.
- \`02_REPORTS/W4_I02_AR02_AR08_RUNTIME_INTEGRATION_REPORT.md\` and \`02_REPORTS/W4_E09H_AR09_INDEPENDENT_EVALUATION_REPORT.md\`: I02 local SQLite reserve/charge and callback flush are fixture level; E09H has HMAC test keys, not independently approved real custodial issuers.
- \`05_EVIDENCE_INDEX/REL01A_PROVENANCE_CHAIN.md\`: reported historical Stage30O run attribution, Stage30P image/host discrepancy; an OCI tag/short revision is not immutable executed source. Historical source \`395968f3c101499e3ecb33a54e3dd4092c06b372\`, reported image \`sha256:7fd8941b1119cf49545d458d91e8787c65ba6e4bd2ea1b4362cfa87fa22bd748\`, and Stage30P dataset identifiers do **not** bind actual current I02 executable build.
- \`05_EVIDENCE_INDEX/REL01C_STREAM_QUALITY_COST_RECEIPTS.md\`: design contract only, no actual verified model usage or invoices. Every invocation, including failed, retried and timed-out, needs independently reconciled price and billing; no inference of \$0.
- \`05_EVIDENCE_INDEX/REL01E_GATE_EVIDENCE_MATRIX.md\`: R01 has 19 release evidence debts; true source-use rights, original corpus, external billing and real client ACK unproved/restricted.
- \`05_EVIDENCE_INDEX/AR09P_EVAL_HARNESS_CONTRACT.md\`: eligible denominator includes missing/partial/abstain/unknown and all attempted charges, zero verified outcome makes cost-per-outcome undefined. T0–T2 never claim T4.
- \`git -C 06_WORKSITES/W4_I02_AR02_AR08_RUNTIME_INTEGRATION log -1\` read-only: **I02 accepted commit \`0cd2b74baa2c892b163ffe5138de2df863417889\`**, parent \`d14abc74759a3c2dcb53105be9516008ad07a1a6\`, Git tree \`4c352e7ae1e25ecbb023151e7e95722193d2c7a9\`. I02 sibling status read as clean and source path verified through \`ls-tree\`. This is a source-code anchor only, not a built, tested OCI image binding.
- The P09 worktree itself started clean at accepted E09H commit \`bbcd019a787114bbde327b2b3eafb0d73935e963\`, on \`m27/w4-p09-source-cost-authority-v1\`. E09H source can be inspected in P09's own branch without exposing hidden holdout labels or I02 fixtures.

No source bytes, private corpus examples, model prompt payloads, API credentials, upstream endpoint probes, real billable calls, or active owner/prod routes were accessed.

## Evaluated evidence categories: exact debt

| Admission requirement | Actual local observations | P09 classification |
|---|---|---|
| Frozen I02 Git source + tree | Read-only local Git confirmed full commit/tree | PRESENT_VERIFIED *as local Git metadata only* |
| Exact executable I02 image, immutable manifest, build attestation, package module hashes and instrumented native route | No I02 build/runtime receipt bound to that commit or direct package measurement | MISSING |
| Original external source native SHA, ACL tenant, license, revision, freshness | Only historic reports/design; protected corpus data outside consent scope | ACCESS_RESTRICTED for original; MISSING for independently attested rights |
| Source consent and retention issuer, current authorization | No independently verified real issuer record | MISSING |
| Reviewer, verifier, CI, observer, source/license and outcome signer trust roots | E09H test HMAC roles are synthetic, not external public-key roots | NOT_VERIFIED |
| Exact real Provider/model/version/request and all request retry/failure usage | I02 local SQLite reservation/charge, not provider-boundary invoices | MISSING |
| Real provider price schedule + currency + effective interval + per-call independently signed invoice | No independently verified current provider price/usage/invoices; historical estimates are not bills | MISSING, cost UNKNOWN |
| Authenticated client-received text / exact native publication path | Local server-side flush and fixture acknowledgment, not real client receipt | MISSING |
| E09H custodian-blinded Phase B accepted verified outcomes | Offline Phase A alone accepted, unseen original holdout not executed | MISSING |
| Original 523 real quality, p95 and substantive first-byte release gates | Historical reported data do not bind current I02 image/holdout | NOT_VERIFIED |

The current actual economics must be \`UNKNOWN\`, **not USD 0 or local reservation total**. Original sensitive corpus evidence remains under separate independent custody; this worksite did not extract it.

## Executable policy and read-only API

\`EvidenceIntake.inspect(AdmissionPacket)\` uses an externally injected frozen Git+tree and optional full OCI digest/build digest. It accepts a source-agnostic append-only sequence of SHA256-canonical JSON role records: source, consent, retention, reviewer, verifier, CI, observer, price, usage, invoice, client, route, build and outcome. Each signer/digest/issuer/revision/time/tenant/run/request/attempt is bound to a role and a single clock domain, with monotonic/relative order checked inside this offline synthetic envelope. Duplicate roles, reused issuer across roles, forged/expired/uncanonical records and chain gaps fail closed.

\`Anchor\` objects must be independently provisioned OUTSIDE records, with key ID, issuer, role, signer, cryptographic algorithm and tier. Ed25519 authorization is only possible for an externally provisioned \`AUTHORIZED_EXTERNAL\` anchor and explicit outside-packet custodial authorization; any fixture-HMAC can validate **test integrity only** and remains \`NOT_VERIFIED\` for external authority regardless of caller claims. No real keys were supplied in this dispatch. There is no authority derived from claimed strings such as \`verified=true\`, executor-signed results, synthetic self-rating or a mutable tag.

Source contract binds opaque source ID, original-byte SHA256 (not source content), revision, tenant ACL, expiry, license, revocation, consent generation and retention. It never opens a source URL, runs retrieval or stores case text.

Pricing requires exact provider/model/version, ISO 4217-like three-letter currency, bounded effective interval, independently rooted provider price and usage and billing ledgers. Each usage row requires provider request ID, attempted identity, status, clock, tokens (input/output/reasoning/cached), and retry linkage. Invoice lines join by each call ID and include independent original invoice ID, currency, model and issue time within close cutoff; no missing failed attempt, duplicate usage, unsigned or after-close bill is treated as 0. Decimal pricing is exact in integer micro-units; noninteger micros, NaN and negative numbers fail. Unknown ledger cost remains \`None\` even when a synthetic reservation appears numeric.

\`reconcile_economics\` uses the independent eligible attempt catalog, including failures and retry charges. Its numerator is all actual admissible spend; denominator is independently verified outcomes. Without complete invoices, currency or positive true outcomes the cost-per-verified-outcome is **undefined/UNKNOWN**, not 0. Mixed synthetic/real trust is never promoted to actual product economics.

## Negative and fault-injection test groups

- Source wrong tenant, expired ACL, revoked native revision, missing license, stale consent, retention revocation, bogus source digest.
- Authority: missing each of 14 roles, forged signature, incomplete hash chain, digest conflict, self-issuer/executor role, unknown root, role duplication, false \`phase_b_independent_outcome\`.
- FinOps: wrong currency, model/version/effective price, negative/NaN rates, token count/price mismatches, missing empty invoices, duplicated call/invoice, unknown request ID, failed/late invoice, retry mismatch, incomplete telemetry, unmetered attempted failure, zero/unknown cost.
- Provenance/route: wrong immutable I02 commit, mutable OCI tag, missing build, wrong native route, unconfirmed client ACK and cross-clock references.
- Economic arithmetic: failed-attempt cost included in numerator; known cost with zero outcomes returns undefined quotient; missing assigned cases cannot shrink eligible denominator.

All fixture signers and all prices/tokens are **synthetic** and not externally admissible. Full exact test counts and SHA manifests are in the external standalone REPORT.md after scoped execution.
