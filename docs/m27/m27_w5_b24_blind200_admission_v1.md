# W5 B24 | Independently Sealed Blind Phase B200 Metadata Admission v1

**Engineering status:** synthetic protocol and negative testing only. **Real Phase B: `PHASE_B200_EVALUATION_NOT_EXECUTED`.** Never equate M26 frozen200, Stage30O 523, G23 synthetic wire receipts, a developer-produced trust registry, or a first-party Git SHA with a fresh unseen officially scored 200 cohort.

## Separation of duties and provenance

The authorized source controller/rights issuer owns proof of legal use and allowed immutable source revisions. A genuinely **independent custodian** creates and holds a new 200-case sealed holdout with grader keys, corpus contents, prompt bodies and answers outside the developer environment. The custodian signs a case-ID roster commitment BEFORE the candidate lock. An independent rubric owner signs the precommitted rubric. A real builder attests a signed immutable image/candidate, the independently authorized sealed runner signs read-once intent, and an authenticated client independently signs native ACK evidence.

The developer receives only opaque case IDs, fixed denominator, evidence digests, signature identities, and redacted event summaries. It never receives cases, answer keys, expected outcomes, or grading rubric answer details. Input files for the real evaluation MUST remain on a separately controlled host and must not be copied to this project worktree.

The **developer cannot establish independent trusted authority by signing their own roots.** `trusted_roots` maps six roles to independently enrolled ED25519 public keys. `pinned_root_sha256` is the JSON-canonical SHA256 of that trust registry obtained via a *separate authenticated channel*; caller-supplied matched hex is only a local cryptographic check, **not** a lawfulness certification. Real custodian and rights verification remains an external acceptance obligation. A valid local metadata response is never a live authorization or Phase B PASS.

## Immutable input contract

All envelopes are exactly `{role, key_id, payload, signature}`. Signature is base64 of ED25519 over `b"M27-B24-v1\\x00" + role + b"\\x00" + canonical_json(payload)`. Canonical JSON uses lexically sorted keys, UTF-8, no whitespace, no NaN. Exact role-specific payload allowlists are `ADMISSION_FIELDS` in the source, and **additional fields are rejected** to prevent smuggling hidden case bodies, grading keys or model outputs. Trust roles:

| Role | Responsibility | Required material |
| --- | --- | --- |
| `custodian` | Fresh independently held blind case commitment, distinct 200 opaque IDs | `population=NEW_UNSEEN_PHASE_B200`, `case_count=200`, `roster_sha256`, sealed corpus and exclusion digests, `history_overlap_count=0`, source revision index pin, `sealed_at_ms` strictly before lock, independence and no leak flags |
| `rights_issuer` | Current lawful-source-controller authorization | corpus-roster SHA and source-revision index SHA, scope, approved immutable image, `valid_until_ms` |
| `builder` | Candidate immutability and lock | image/runner/client SHA, signed OCI digest, candidate lock timestamp |
| `runner` | Independent sealed one-shot client execution intent | bound runner SHA, one-time nonce, expiration, `RUN_ONCE_BLINDED`, no developer/answer-key access |
| `client` | Authenticated native client | client digest, true ACK digest, nonce bound to runner, expiration |
| `rubric` | Preapproved independent scoring | frozen rubric digest and threshold, pre-lock freeze time, zero-critical rule, grade-only output, expiration |

The custodian's `rights_grant_sha256` equals the canonical rights payload SHA. All six envelope evaluation IDs must match; signer keys and actor IDs must be distinct. Any missing, expired, malformed, mismatched, contaminated or user-signed-by-unknown-root evidence is **NOT_ADMITTED**. Signed roots are necessary but cannot by themselves demonstrate that the actors are in fact independent.

`admit(manifests, trust, now_ms=..., pinned_root_sha256=...)` returns:
- denied: `NOT_ADMITTED`, `PHASE_B200_EVALUATION_NOT_EXECUTED`, null official score and false release flags;
- syntactically/cryptographically eligible: `EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY`, with fixed 200, nonce and SHA pins, **still not executed**, no provider traffic, no official score.

`reserve_one_shot(eligible_metadata, custodian_controlled_state_dir)` atomically mkdir-reserves a digest of evaluation-ID+nonce; a second reservation fails and a crashed reservation stays spent. Host OS permissions and independently controlled durable storage are mandatory. The module does not launch a runner, read a holdout or call a provider. Execute the eligible interface only under an authenticated independently administered custodian, after external authority validation.

## Sealed runner results / grade-only output

The externally controlled runner emits an ED25519 `runner` envelope containing `evaluation_id`, `nonce`, `roster_sha256`, `image_sha256`, `attempt_ids`, `terminal_ids`. The separate rubric role emits grade-only signed output containing `evaluation_id`, `nonce`, `roster_sha256`, `runner_digest`, and **exactly 200** `results`, each with:

`{id, outcome, grade, critical, source_revision, source_id, citation_start, citation_end, span_verified}`.

Permitted outcomes: `ANSWER|ABSTAIN|ERROR|TIMEOUT|DENIED`; each is in the original 200 denominator. A timeout, missing/false citation span, denial, abstention, critical error or model error is **grade 0**, not omitted or favorable. Any outcome not reaching terminal is **NOT_ADMITTED** until genuine fault-inclusive signed terminal evidence exists. Source spans have numeric start/end offsets, end > start, source/revision identifiers; a source-authority independently inspects underlying permitted native revisions and supplies verified/audited proof. Do not treat a grader's unsigned claim of an approved source as an actual verified source span.

The `custodian` signs an additional **grade-digest-bound** source/span/critical audit envelope without source bodies. The `verify_grade_only` metadata auditor requires all 200 distinct attempt IDs and terminal IDs, exactly 200 graded unique IDs, unchanged roster/image/nonce, signed provenance chain, grade-only allowlisted fields and signed source-span audit. It provides **synthetic/admissible metadata counts only**; even when it counts 200 passing results, it does not produce an official score, Phase B certification or external evaluator acceptance. Official scoring is reserved for a separate lawful independent adjudicator.

## Independent execution handoff

1. Obtain and record legal source controller/allowed revisions and grants, independently enroll six distinct trusted identities/roots and pin roots via a separate authenticated out-of-band channel. Never place private keys in this repository.
2. Independently create a **new** unseen 200-case corpus after historical M26, original 523, and other evaluated/replayed samples are exclusion-checked, freeze the opaque IDs and private contents, and sign the 200 roster digest **before** candidate lock.
3. Freeze source-native citation verification contract and actual rubric. Independently sign approved image/runner/client, lock candidate, preserve byte-level OCI/runner/custodian identities, and acquire authenticated native client ACK. No first-party-only signatures.
4. On external custodian host, check `admit`; reserve one-shot nonce only after all checks and independent external authorization. Runner reads the sealed inputs exactly once and sends the model only through its approved constrained interface; developer receives no bodies/answers. Record start, terminal, failures, event log signatures, all latency and cost outcomes for 200.
5. Independent grader returns grade-only signed results and source verifier/custodian source-span receipts, retaining keys and permitted sources off the developer host. Check `verify_grade_only` without retrieving private cases.
6. Independent evaluator independently verifies authentic custody, rights, signatures, live candidate and source pin, external audit and preregistered criteria, then issues a separate formal score/admission decision. **No phase or release flag is toggled by this component.**

Example deny-only smoke test, guaranteed to avoid external data:

```sh
PYTHONPATH=src python -m knowledge_engine.m27_w5_b24_blind200_admission_v1_experimental
# child exit 20, NOT_ADMITTED, PHASE_B200_EVALUATION_NOT_EXECUTED
```

To perform a **metadata-only** custodian preflight after authenticated out-of-band enrollment:

```sh
PYTHONPATH=src python -m knowledge_engine.m27_w5_b24_blind200_admission_v1_experimental \\
  --manifest /externally-controlled/redacted-sealed-metadata.json \\
  --trust /externally-controlled/independently-enrolled-public-roots.json \\
  --pinned-root-sha256 '<independently authenticated hex digest>'
```

No local sealed evaluation is attempted. A synthetically generated trust root or set of fake signatures is not valid real-world evidence, even if the metadata verifier returns `EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY`.

## Mechanical verification

Owned code, own test suite and own documentation are separate from E24 original523, M24/P24/C24 and canonical M16. The independently generated synthetic 200 fixture and adversarial cases test 199/200, duplicate identities, fraudulent role/key/signer, post-lock swaps, historical reuse, expirations, unexpected data/schema leaks, tampered digests, one-shot replay, faults and late terminals. Raw terminal pytest/Ruff/CLI logs are preserved in `05_EVIDENCE_INDEX/W5_B24_PHASEB200_ADMISSION_20261012/`; all scenarios are synthetic only.

**Hard stop states:** `PHASE_B200_EVALUATION_NOT_EXECUTED`, `J20_M16_NOT_AUTHORIZED`, `W5_FULL_COMPLETE=false`, `W6_AUTHORIZED=false`, `REL01_CERTIFIED=false`, `REL02_AUTHORIZED=false`, `PRODUCTION_AUTHORIZED=false`.
