# W5 E24 | Signed original-523 evidence scorer (EXPERIMENTAL)

**No official evaluation is authorized by this component.** This is a read-only redacted evidence checker, not access to hidden questions, oracle-vm, real Provider, release, OCI or Production. No automatic canonical M16 or W5 state updates.

## Historical facts and frozen denominators

G18 previously matched 523/523 original Stage30O case IDs and outcome IDs, comprising **341 live** and **182 replay**. Only **20 normalized lexical strings** exist among those 523 historical cases. These are NOT 523 fresh unseen independent QA questions. Corrected F20 A19 V2 has `contract_status=DRAFT_NOT_APPROVED`, no authenticated lawful grant or independent grader. Stored Stage30O 237/237 citation flags and about 4.93-second historical server-side timing are **not** current W5 independent scores.

| Frozen mode / expectation | Assigned | Qualified evidence |
|---|---:|---|
| live / verified_cited_answer | 237 | source SHA + revision + native span/permission, signed independent grader >=85, no critical error, real client ACK / preterminal substantive text / complete final |
| live / safe_abstention | 52 | signed separate safe abstention, client ACK, no rights/answer leak |
| live / rejected_before_provider | 52 | separately signed policy reject; authority trace, independently observed zero actual provider dispatch |
| replay / budget_terminal | 26 | separately signed replay-control pass |
| replay / m26_invariant | 26 | separately signed replay-control pass |
| replay / governance_contract | 130 | separately signed replay-control pass |
| **341 live + 182 replay** | **523** | Immutable assignments; failures never removed, replay never counted as answer |

**Draft proposal only:** cited finals >=226/237 (>=95%); all safe 52/52, preprovider 52/52 and replay 182/182. Independent client-complete latency p95 <=15000ms at nearest rank **324/341** and **226/237**. Unverifiable or missing duration blocks latency score, not silently imputed. Timeout, wrong reject/abstention, missing signed grader/source span, incorrect case mode all fail qualification. Cited-success requires source-native independently signed assessment; no subjective word-presence scoring.

## CLI: supply externally permissioned, redacted material

Source: `src/knowledge_engine/m27_w5_e24_original523_evidence_scorer_v1_experimental.py`. Syntax:

`PYTHONPATH=src python -m knowledge_engine.m27_w5_e24_original523_evidence_scorer_v1_experimental --manifest /secure/current-approved-manifest.json --roster /secure/roster.json --outcomes /secure/signed-current-outcomes.json --trusted-registry /independent/roots.json --trusted-registry-sha256 EXTERNALLY_VERIFIED_SHA256 --output /private/new-result.json`

Input is limited to 10 MiB each, regular non-symlink files, duplicate JSON keys and NaN rejected; no network, Provider or corpus access. Output is newly created with `0600` and O_EXCL (no overwrites), SHA256 calculated on actual bytes and reported on stdout. All per-case denial reasons are retained with pseudonymous fingerprints, no raw case IDs/answers. Fingerprints are pseudonyms only and output must remain access-controlled.

**Status/exit distinctions:** exit 20 is a failed or denied admission, 21 output write failure, and 22 is a successful synthetic-only calibration with NO official admission. A synthetic calibration is `SYNTHETIC_CALIBRATION_ONLY`, NOT official. A live signed packet that mechanically passes returns `SIGNED_EVIDENCE_ELIGIBLE_FOR_INDEPENDENT_ACCEPTANCE`, **not** release approval. All five release booleans remain false by code. If approved material is unavailable, record `OFFICIAL_523_NOT_RUN_EVALUATOR_RIGHTS_NOT_ESTABLISHED`, never claim official 523 or Phase B200 scores.

## Minimal evaluator handoff schema

**Roster.** `{"schema":"m27.w5.e24.immutable_roster.v1","cases":[{"case_id":"opaque","mode":"live","expectation":"verified_cited_answer"}, ...]}`. Exactly 523 unique opaque assigned IDs and six immutable buckets. Only the independent custodian may disclose these metadata; hidden text must remain in its controlled evaluator environment.

**Outcomes.** `{"schema":"m27.w5.e24.current_outcomes.v1","signed":{"payload":{"run_id":"one-shot-current-run","candidate_image_sha256":"64hex","roster_sha256":"64hex","receipts":[...]}, "signature":{"key_id":"observer-key-id","signature_hex":"128hex"}}}`. All receipts are signed together by an independent observer. Each receipt has only opaque assigned ID/mode/expectation, terminal status, source-native assertion, signed independent grade, monotonic client timestamps, signed-observer client ACK SHA, answer SHA (not text), provider dispatch count/telemetry, authority SHA and boolean protected leak observation. Original failures and missing IDs remain denied in fixed denominator.

**Source assertion.** Independent source verifier Ed25519-signs `case_id,run_id,answer_sha256,source_sha256,revision,span_start,span_end,source_index_sha256,permission_grant_sha256,valid`. Source SHA/revision/span and matching permission grant required; missing proof means UNKNOWN/FAIL. The signer must actually have permission to inspect the *native* source, not merely keyword-match synthetic text.

**Grader assertion.** Independent grader Ed25519-signs `case_id,run_id,answer_sha256,source_claim_sha256,score,critical_error,pass,category`. Cited finals require score >=85/100 and zero critical failure and SHA match to signed source assertion. Controls get independent pass/fail adjudications, never count toward cited numerator. Human rubric should separately define accuracy/entailment/citation/completeness/temporal weights and blinded double review/arbiter.

**Approved manifest.** Outer shape `{"schema":"m27.w5.e24.signed_original523.v1","contract_status":"APPROVED","payload":{...},"signatures":{"rights_issuer":{...},"evaluator":{...}}}`. Two **distinct** roles Ed25519-sign the identical canonical payload. Required payload:

- `source_corpus_sha256` pinned to historical source native SHA `e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137`; `roster_sha256` and `outcomes_sha256` bind current immutable data.
- `official_run_id` and `purpose=ORIGINAL523_CURRENT_EVALUATION_ONE_SHOT`, six fixed `mode_counts`; historical Stage30O flags are not accepted as current outcomes.
- `rights_grant_sha256`, `license_scope=EVALUATION_ONLY`, `issued_at_utc`, `expires_at_utc`; externally verified lawful case/source controller license, consent/ACL, retention and revocation.
- `rubric_sha256`, `source_index_sha256`, `independent_grader=true` for approved source-native independent QA.
- `candidate_git40`, `candidate_tree40`, `image_sha256`, `build_sha256`, `runner_sha256`, `client_instrumentation_sha256`, `independent_native_client=true` to bind genuinely current signed candidate and client observer.

**Trust roots** supplied in a separate SHA-pinned evaluator registry with version `m27.w5.e24.external_trust_registry.v1` and exactly five independent key IDs/principals for `rights_issuer`, `evaluator`, `observer`, `source_verifier` and `grader`. Each entry has `role,key_id,principal,tier,public_key_hex`, with tier `SYNTHETIC_FIXTURE` or `AUTHENTICATED_EXTERNAL`. Actual root fingerprint must be pinned independently **out of band**. A self-pinned or locally authored registry or the word AUTHENTICATED_EXTERNAL is not independently established authority. No private signing keys or hidden content in the Git branch.

## Actual human/organizational admission checklist

1. **Legal owner/controller + separate custodian:** establish original case and underlying native source ownership/license, consent if needed, ACL, retention/revocation, signed grant scope, source corpus SHA, full 523 mode-roster digest, independent issuer public root and access audit.
2. **Independent rubric approver, grader and source verifier:** freeze 237 answerable assignments and complete 523 roster before outcome access; define and sign 85/100 plus critical veto rubric; source-native span/revision/permission truth inspected by separately authorized verifier. Do not lower strict Phase B holdout requirements to accommodate historical 20 lexical strings.
3. **Signed candidate builder/runner plus independent client/observer:** verify exact current git/tree/image/runner/instrumentation IDs and actually authorized one-shot execution, capture all 341 client receipts including missing/errors/rejects and all 182 replay outcomes separately. No self-scoring or replacement of failed rows.
4. **Score + preserve receipts:** provide only authentic independently authorized redacted signed outcomes and anchored trusted public roots. Retain raw current run, source-verification evidence, immutable grade assertions and result output SHA; ask separate independent Master evaluator to accept/reject official outcome.
5. **Separate original P16/B13/M16, blind AR09 Phase B200, Provider pricing/invoice, signed OCI and rollback, release Owner** remain independent gates. Local E24 code/test SHA cannot supply those rights. Keep `W5_FULL_COMPLETE=false`, `W6_AUTHORIZED=false`, `REL01_CERTIFIED=false`, `REL02_AUTHORIZED=false`, `PRODUCTION_AUTHORIZED=false`.

**Synthetic fixtures used for test coverage have fabricated metadata and keys generated only by tests.** No official original source/hidden case bodies, native client, Provider or controlled benchmark are touched.
