# M27 W5 P16 | Genuine external evidence intake and custody receipt v1

**Scope:** offline metadata reconciliation and read-only SHA256 inspection of locally presented evidence files only. Neither a licensed source acquisition process nor an external grading run, and not a declaration of custodian consent. No signed data, original evaluation bodies, source-origin credentials or paid Provider calls are generated here.

## Invocation

```bash
TMPDIR=/tmp PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B \
-m knowledge_engine.m27_w5_p16_external_evidence_ingress_v1_experimental \
inspect --ingress-root /authorized/local/ingress \
--manifest manifest.json \
--scratch /private/independent/outside-worktree
```

The manifest is **relative** to the authorized ingress root, and must not be a symlink. No automatic searches of a home directory, mount points, external data systems, browser profiles, IdP, Provider service, historical fixtures, or official evaluator. The CLI has **no** option to import external signing roots from the untrusted ingress. Its JSON status is a read-only *candidate classification*, not evaluation authorization. It writes one 0600 receipt in a private 0700 scratch directory. The interface never prints raw case bodies, protected answers, bearer credentials or signed keys.

## Exact on-disk manifest contract

JSON object with exactly `schema`, `subject`, `run_id`, `grant_id`, `host_id`, `candidate_commit`, `candidate_image_sha256`, and `artifacts`:

```json
{
  "schema": "m27-p16-external-evidence-v1",
  "subject": "candidate01",
  "run_id": "run01",
  "grant_id": "grant01",
  "host_id": "host01",
  "candidate_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "candidate_image_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "artifacts": [
    {
      "kind": "rights_custody",
      "path": "rights.json",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "subject": "candidate01",
      "issuer_id": "independentCustodian01",
      "scope": "EVALUATION_ONLY",
      "revision": "rev01",
      "source_id": "source01",
      "grant_id": "grant01",
      "license_id": "license01",
      "run_id": "run01",
      "host_id": "host01",
      "candidate_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "candidate_image_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "issued_ms": 1790000000000,
      "consent_until_ms": 1810000000000,
      "acl_until_ms": 1810000000000,
      "retention_until_ms": 1810000000000,
      "revoked": false
    }
  ]
}
```

This example is a **schema sketch, not a genuine license or custody attestation**, and its listed hash must be replaced with the actual SHA256 of the provided file. An independent custodian must supply and verify the source rights, license/ACL/consent/retention/revocation/version and exact intended scope. No value in this JSON proves the named issuer was authorized.

Required artifact kinds (one file each): \`rights_custody\`, \`original_index\`, \`phase_b_index\`, \`native_sources\`, \`citation_spans\`, \`grading_rubric\`, \`graded_original\`, \`graded_phase_b\`, \`image_attestation\`, \`build_attestation\`, \`runner_attestation\`, \`instrumentation_attestation\`, \`client_delivery\`, \`provider_usage\`, \`provider_prices\`, \`provider_invoice\`, \`issuer_roots\`. Optional: \`rollback_rehearsal\`, \`release_authorization\`. Metadata must be bound to candidate subject, run/host identity, Git/image SHA, issuer, grant/license, distinct file digest, revision, scope, consent/ACL/retention validity window and current revocation state. Sealed index files have the E15 \`SealedManifest\` JSON schema; graded packet files have the E15 \`RunPacket\` JSON schema; protected question/answer bodies must not be placed in developer-accessible ingress. The origin and Phase B population must remain separately sealed: original 523 distinct independently reviewed questions, and 200 genuinely unseen separately reviewed Phase B cases. Historical 523 stored rows are **341 live + 182 replay with only 20 lexical unique questions**: do not relabel those or synthetic case IDs as official original benchmarks.

## File-read and authority boundaries

File references are strict restricted relative names: no absolute, tilde, dot traversal, encoded escape, control, backslash, Unicode spoof or symlinks in components. Open relative to a pinned directory descriptor with \`O_NOFOLLOW\`; reject nonregular/hardlinked files, >8 MiB per file, >1 MiB manifest, altered inode/size/mtime/ctime or nonmatching expected SHA256. Read all bytes from actual descriptors; no download. ZIPs are validated without extraction with a 128-entry, 16 MiB uncompressed and 50:1 expansion ceiling and no encrypted/symlink/traversal members. Maximum 64 manifest entries. Atomic SHA receipt does not include raw content or private signing material.

The **manifest-supplied issuer** is not an issuer grant. An independent authorized evaluator application may inject \`TrustedAuthorityRegistry\` through a separately authenticated integration which binds externally provisioned SHA256 for each artifact, actual issuer nominations, subject and grant. The E15 independent context and its 8 separately rooted Ed25519 roles (\`custodian\`, \`rights_issuer\`, \`source_verifier\`, \`builder\`, \`runner\`, \`grader\`, \`client\`, \`observer\`) remain authoritative for deeper signed scoring metadata. \`E15.inspect(SealedManifest, RunPacket, IndependentContext)\` is called for both separately typed cohorts when provided, including a complete denominator, source native span and revision, candidate immutable commit/tree/image/build/runner/instrumentation, grader rubric, client first substantive cited DATA before terminal, authentic Provider costs and signatures. No external process authorization is constructed from a caller boolean or fixture root. Even with successfully inspected metadata, this worker **always** returns \`P16_EXTERNAL_AUTHORITY_NOT_ADMITTED\` as its ingress classification and retains \`ORIGINAL523_EVIDENCE_NOT_ADMITTED\`, \`AR09_PHASE_B_BLOCKED\`, \`may_execute_official_evaluation=false\`, \`official_cited_gate_pass=false\`. Independent reviewers must separately decide actual eligibility and actual execution.

## Exportable source / independent authority request

\`P16_REQUEST_RECEIPT.json\` has each required evidence file class, who must independently produce and authenticate it, its actual file-level SHA256 where present, proof-of-absence/denial reason, required signer role and permitted evaluation-only scope. It deliberately omits raw questions, answers, source documents, keys, client transcripts, invoice content and other private material. Missing real consent or trusted root means \`EXTERNAL_ARTIFACTS_ABSENT\` or \`P16_EXTERNAL_AUTHORITY_NOT_ADMITTED\`. Required authority is per-party and must not be supplied by the software implementer or inferred from a Git SHA/locally generated test key. Retention and revocation require current independent evidence, not passive historical timestamps. The separately authorized release operator owns any rollback rehearsal and release identity verification. This receipt is evidence debt and not a release certificate.

## Explicit gates

P16 does not execute the genuine original 523 grader or real Phase B, and cannot authorize B13 20-source executable packaging, W5_FULL_COMPLETE, W6, REL01/REL02, CI, IdP, authentic native product Client ACK, real Provider spend, credential operations or Production. B13's earlier explicitly platform-safety-refused operations are not repeated by this package. A successful synthetic test verifies only local mechanical denial/ingress behavior. All genuine real-world source rights and independently provisioned roots remain **unproven until separately supplied and inspected**.
