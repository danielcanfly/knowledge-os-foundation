# M27 W4 E09B | AdmissionGateV1, independent blinded Phase B

**Classification:** OFFLINE ADMISSION ENGINEERING, not a genuine unseen holdout run, not a product score, not a release permit. The required verdict when independently accepted D09/T09/P09 reports or external evaluator authority is absent is `E09B_PHASE_B_BLOCKED_EVIDENCE_DEBT`.

## Freeze and independence requirements

- Input worktree branch `m27/w4-e09b-phase-b-admission-v1`, required immutable E09H Phase A parent `bbcd019a787114bbde327b2b3eafb0d73935e963`.
- Candidate *comparison identifier* is I02 full commit `0cd2b74baa2c892b163ffe5138de2df863417889`, plus independently checked tree/build/image/runner digests. I02 source, implementation tests and exposed answer strings are intentionally not read by this module.
- Freeze dataset only with independently custodied, signed manifest hash, separate frozen opaque case ID manifest, sampling protocol, reviewer and rubric/scorer versions, calibration digest, source-rights and snapshot hashes, external client/CI/billing/observer permissions and evaluator-only access log. These fields are claims until a separately trusted verifier with nondeveloper trust roots attests them. Fixture HMAC, model self-score, developer-written signature SHA, any supplied boolean, and this Python module **cannot** establish real independent authority.
- The default constructor has no verifier and no authorized run interface. It **cannot** run external evaluation, extract hidden questions, sign evidence, open a production route or certify a release. A test-only injected verifier permits *offline preflight testing* and still does not run Phase B. Official execution requires separately dispatched evaluator custody and an approved independent run interface; this package provides neither.

## Separate denominators and holdout controls

1. Proposed REL01B holdout is **200 unseen cases minimum**, with >=140 independent intents, >=100 source records, >=20 documents, >=5 independent families, >=40 long-tail, >=60 paraphrases (not separately counted as independent intents), >=30 negative controls and >=20 supported-positive anti-false-safe items. No more than 10% single document, 20% family, 15% Graphology, 20% historical benchmark topic. 0 Direct100, 30O/30P reused, old 9 exposed scored cases or repeated semantic intents. A 200-case protocol is not evidence that an eligible holdout exists.
2. Historical Stage30O **523 rows = 341 live + 182 contract replays**, and live rows are not 523 distinct independent questions. They are not an independently frozen original 523-question product benchmark. The original benchmark requires its *own* versioned immutable manifest, 523 verified distinct questions, independent grades and separate release adjudication. Neither historical row flags nor E09H fixture success certify it.
3. Every assigned case including abstain, unsafe, failed, missing, timeout, partial, UNKNOWN and all retries is retained. Only independently labeled eligibility may exclude a case. A duplicate or unassigned result is a hard failure, not selective deletion. No retry of official failed cases, label changes or threshold adjustment.
4. Every supported answer requires original native citation-byte integrity, factual entailment and independently issued per-answer score >=85, with 0 unsupported publication and 0 false-safe on supported positives. Score mean never substitutes for individual score; safe abstentions require independent legitimacy review.
5. True product p95 is from actual request arrival at trusted client to terminal received in the **same client monotonic clock domain**. Nearest-rank p95 over all assigned cases, timeout/missing penalty >=15s, no missing latency receipts; for REL01B blind strict limit **<15s**; separate Owner release original benchmark target <=15s. First substantive verified answer text must arrive at a trusted client before terminal with a cited segment, not merely progress SSE/event name, server flush, verified_claim_ready with no content, or terminal-only bytes. Cross-machine monotonic subtraction is forbidden.
6. Billing ledger must cover **every provider attempt**, including retry, safe result, cache and failures, with independent billed usage, rate snapshot, invoice receipt, provider pricing and preapproved caps. An absent/delayed/missing invoice is **UNKNOWN** cost, never 0.
7. The offline `audit_opaque_offline` helper checks a deliberately redacted metadata DTO, counts denominator and failures, per-answer minimum score, true-client receipt shape and cost nonzero/unknown. It always returns `OFFLINE_DIAGNOSTIC_NOT_PRODUCT_SCORE`; booleans and synthetic timestamps are **not** real client/billing/scorer proof. A genuine verified run must be separately authorized, independently executed and scored without developer access to prompts or gold labels.

## One-shot and privacy controls

`TestOnceLedger` requires an existing evaluator-only private directory. It creates an exclusively reserved opaque `run_id_sha256.jsonl` (mode 0600) with O_EXCL and fsync. Collision or prior reservation (including an interrupted/failing test) refuses retry. Only opaque run-hash and candidate/corpus digests appear in the record. This is an **offline local primitive**, not a remotely WORM-sealed signed ledger; real official runs require independent append-only retention, verified signing and access auditing. Never copy raw prompt, expected answer, decrypted source, private key or protected signer material to the shared tree, worker report or developer-visible log.

## Readiness gate and actual evidence

- Source policy: `REL01B_BLIND_HOLDOUT_PROTOCOL.md`, `REL01B_SCORING_RUBRIC_AND_RECEIPTS.md`, `REL01C_STREAM_QUALITY_COST_RECEIPTS.md`, `REL01C_VERIFICATION_TEST_PLAN.md`, REL01D/REL01E and W4 I02/E09H Master-accepted local component receipts.
- **D09 corpus**, **T09 transport**, **P09 authority+cost** are separate independent W4 assignments. As of initial worker read, no corresponding delivered report was present in the canonical `02_REPORTS` directory. This is a snapshot of available authorized evidence, not a claim that other parallel workers will never finish.
- Independently accepted scorer, external signer, source ACL/license/consent, true client, invoices, sealed hidden source, and explicit external live interface approval are **not present** in this worker's authorized material. Thus Phase B is **blocked**, no real candidate, provider, scorer, evaluator, corpus or release action was invoked.
- Test-only preflight may create synthetic structured metadata to validate negative gates. It must never assert a genuine frozen 200 or original distinct 523 dataset. The `PRECONDITIONS_SATISFIED_NOT_EXECUTED` unit fixture is not externally attested and has both `official_evaluation_ran=False` and `release_certified=False`.

## Source/test/doc allowlist and verification

Only these NEW tracked paths are authorized:
- `src/knowledge_engine/m27_w4_e09b_blind_gate_v1_experimental.py`
- `tests/test_m27_w4_e09b_blind_gate_v1_experimental.py`
- `docs/m27/m27_w4_e09b_blind_gate_v1_receipts.md`

Raw stdout/stderr, Git/hash receipts and final report live under the specified Master `05_EVIDENCE_INDEX/W4_E09B_BLIND_HOLDOUT_SCRATCH` and `02_REPORTS/W4_E09B_BLIND_HOLDOUT_REPORT.md` outside this Git tree. Negative tests use mock/opaque values only. No source of unpublished hidden labels or I02 worker code is referenced. Parent, exact three additions, scoped pytest, regression, Ruff, sha256 and clean Git must be supported by raw terminal outputs in the separate report.

**Disposition:** New Phase B admission/readiness component only, `E09B_PHASE_B_BLOCKED_EVIDENCE_DEBT`; E09H Phase A accepted separately, genuine Phase B and REL01/REL02 remain NOT EXECUTED / NOT CERTIFIED.
