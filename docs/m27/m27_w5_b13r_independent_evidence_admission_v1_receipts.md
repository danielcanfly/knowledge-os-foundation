# M27 W5 B13R | Independent evidence admission and bounded recovery

2026-10-11. **Status: new independent evidence-gap validator candidate only.**
This document is not a B13 positive closure certificate.

## Owned component

- New module: `B13IndependentEvidenceAdmissionV1`
- Receipt schema: `m27.w5.b13r.independent.evidence.debt/v1`
- Proposal schema: `m27.w5.b13r.independent.evidence.proposal/v1`
- Candidate B13 commit: `c8bcc4f7f2fe124556f9f60768b8ea1cd248000c`.
- F13 v3 manifest pin: `0781bb17f1dd405e5140accc1071d019742643902849bb75cd512af9be2f0cde`.
- Profile: `CORE_OFFLINE_FEATURE_OFF`.

The standalone implementation uses Python stdlib only; it does not call or import
the previous B13 positive builder or attempt a batch original-source Git blob
readback. It accepts an in-memory, typed, metadata-only proposal and optionally
the pre-existing B13 and Master report texts, marked untrusted. Reports are
fingerprinted for diagnosis but cannot grant an attestation.

## Machine-checkable evidence obligations

`OBLIGATIONS` contains 13 versioned entries with explicit required proofs,
expected independent trust domains, outstanding-status reasons, and safety-denied
original operation IDs where applicable. It covers original 20 file SHA vs Git
blobs; two independently built canonical 21-entry ZIPs; full 20 isolated modules,
origins and I02 import order; real AR06→AR03 deferred path; real P09 missing
cryptography rejection; source/package binding; historic committed tests; actual
externally executed/signed OCI, real signer trust; client text ACK and actual
cost/p95/eligible-original-523; qualified AR09 Phase B; REL01 and REL02.

The validator's **only** positive status is
`EVIDENCE_GAP_VALIDATOR_LOCAL_PASS`. This represents metadata schema
validation and local negative tests, not genuine source bytes, image, rights,
Ed25519, module-import or product proof.

Regardless of a syntactically credible self-reported SHA, matching synthetic
witness, unknown signer, green tests or fixture-HMAC, output stays:

- `B13_POSITIVE_RUN_NOT_VERIFIED`
- `B13_20_FILE_ZIP_NOT_VERIFIED`
- `B13_I02_20_MODULE_IMPORT_NOT_VERIFIED`
- `B13_AR03_LAZY_FUNCTION_NOT_VERIFIED`
- `B13_P09_ABSENT_CRYPTO_NOT_VERIFIED`
- `OPTIONAL_ED25519_DENIAL_UNVERIFIED`
- `REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED`

`B13_ALL_FEATURES_DEPENDENCY_CLOSED = false`; `REL01 = NOT_CERTIFIED`;
`REL02 = NOT_AUTHORIZED`. The independent proposer schema denies any
`production_authorized`, owner grant, phase-B or release self-promotion.
It also rejects forged artifact/witness trust domains and any asserted original
independent-byte proof, because this module has no approved trust root capable
of validating such a claim.

## Binding platform-safety denials

Two distinct prior operations remain
`DENIED_NO_EQUIVALENT_RETRY`:

1. Original B13 `OfflineCoreDependencyClosureV1.run` positive build and proof.
2. Master original frozen F13 20-source/Git-blob batch readback.

No Plan B RDC, Plan C Codex App, source slicing, import-from-host replay,
pytest wrapper or equivalent variant may be used to sidestep either denial.
Independent schema/contract review, local negative fixtures, receipt validation
and unrelated scoped bug fixes are allowed. The B13R worker owns only its new
source, tests and docs in the B13R worktree.

## Provenance boundaries

The F13 manifest and historical B13 worker/Master reports are trusted
**only for their existence as historical metadata**. The worker's three B13
commit SHA and previously green 1,101 tests were independently accepted in
prior Master review, but none prove unexecuted full F13 20-source closure.
The B13R negative-suite tests produce no real Ed25519 signature authority,
original-source grant, external evaluator, client ACK, signed OCI, Provider
calls, billed model, canary, or Production mutation.

See `02_REPORTS/W5_B13R_INDEPENDENT_EVIDENCE_RECOVERY_REPORT.md` for actual
committed B13R test/Ruff/Git receipts. Only the independent Master can accept
this **bounded local evidence-gap validator**, not the original B13 core.
