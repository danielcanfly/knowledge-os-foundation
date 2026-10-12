# M27 W5 P24 | Original P16/B13 existing-witness verifier (experimental)

## Precise disposition

This standalone module is **not** the original P16 seven-scope pytest execution, P16 standalone AST run, original B13 on-disk-versus-20 Git blobs parity, or B13 original successful ZIP/import/function execution. P24 never executes those four historical actions, accesses the original protected case bodies, or invokes a Provider. It accepts only externally delivered, *already-existing* witness receipts and their native stdout/stderr/test-log bytes.

Any omitted, unsigned, stale, expired, revoked, unauthorized, tampered, wrong-origin or nonterminal witness is returned as \`ORIGINAL_EVIDENCE_UNVERIFIED\`. Cryptographically self-consistent signed *synthetic* witnesses can return \`WITNESS_CHAIN_VERIFIED_ADMISSION_PENDING\`, but even that always retains:

- \`original_p16_pass=false\` and \`original_b13_pass=false\`
- \`external_authority_admitted=false\` and \`release_authorized=false\`

A temporary test-generated Ed25519 key cannot establish a real external custodian, native execution, independently graded hidden set, or any release rights. Only an independently controlled authority can make external grants; the registry MUST arrive through a separately authorized trust channel and MUST NOT be parsed from an untrusted witness.

## Exact four historical evidence debts

| Scope ID | Required separately existing signed native witness |
|---|---|
| \`P16_SEVEN_SUITE\` | Original seven suites, at least 60 executed negatives, native pytest log, test revision, runner/source code origin and actual observed child zero exit |
| \`P16_STANDALONE_AST\` | Independent original Python AST parser run, parsed original source paths, diagnostic-free native log and observed zero exit |
| \`B13_BLOB20_PARITY\` | Twenty distinct original source paths, exact filesystem SHA256 equals observed Git-blob *content* SHA256, original blob Git IDs, native run log and zero child exit |
| \`B13_ORIGINAL_POSITIVE\` | Same SHA256 on two reproducible ZIPs plus observed native steps: two ZIP builds, isolated module import, lazy functional path, and expected denial of optional missing cryptography; real native zero-exit overall receipt |

P17 exit 20 means **receipt-producing DENIAL**; 21 means invalid/unsafe input; 22 means denied receipt integrity or output. None may count as original test success, even if a shell wrapper returned 0 or wrote JSON. Historical P17's 133 executed cases and G23's 271 accepted local tests are intentionally separate.

## Intake contract

Use \`parse_json_bytes(data)\` for bounded strict duplicate-rejecting JSON and \`read_existing_regular(root, "receipt.json")\` for existing, bounded, no-follow, single-link, non-symlink regular files. There are **no mutation, execution, network, ZIP-building, Git-blob-disclosure, or hidden-corpus operations** in this module.

Call:

\`\`\`python
verify_existing_witness(
    preexisting_candidate_doc,
    independent_custodian_registry,
    stdout=preexisting_native_stdout_bytes,
    stderr=preexisting_native_stderr_bytes,
    test_log=preexisting_native_test_log_bytes,
    now=trusted_utc_time,
    seen_witness_ids=frozenset(prior_ids),
)
\`\`\`

Top-level receipt fields must be exactly: \`schema, witness_id, scope, origin, authorization, native, detail, signature\`. Schema is \`m27.w5.p24.original-evidence-witness/v1\`. Body signature is Ed25519 over sorted compact ASCII canonical JSON of all fields **excluding** \`signature\`. Signer identifier and public verification key are injected via the *independent* registry. Python cryptography is used only for Ed25519 **verification**; an unavailable crypto library results in DENIED, not a weaker HMAC substitute.

The trusted registry stores independent signer keys, \`allowed_scopes\`, exact \`approved_grants\` (subject, scope, purpose, original source commit, runner SHA256 and expiry), and \`revoked_grants\`. Purpose must equal \`readonly-existing-original-evidence-verification\`; it never authorizes original test execution. Each receipt must bind 40-hex source commit/tree/test revision and 64-hex runner digest, with the native run signed under the same scope, source and runner, UTC issued/started/ended/expires ordering, separately observed child exit code 0, wrapper exit code 0, kind-specific count/shape, and exact SHA256 of separately supplied native stdout, stderr and log bytes.

A verified signature over a fabricated fixture only shows that a local key signed a fabricated fixture. Receipt chain classification is deliberately **not** a legal or independence grant. External evidence must additionally be received from a separately nominated lawful custodian with permission, audited by a truly independent evaluator and matched to the exact canonical code and current candidate/runner. The P24 module does not and cannot confer those third-party facts by parsing first-party metadata.

## Synthetic validation and test isolation

Tests construct temporary Ed25519 keypairs and entirely invented, clearly labeled synthetic observations in memory. They include adversarial signature tampering, missing/wrong issuers, grants and revocation, duplicate/replayed IDs, consent expiry, wrong Git/runner SHA, 20-blob divergence, bad AST shape, incomplete seven suites, non-observed child exit, conflicting wrapper/child exits, and P17 OS denial code 20/21/22. Their one positive family is **schema/cryptographic ingestion only**, not original B13 positive.

Test command, scoped to P24 only, from P24 isolated worktree:

\`\`\`sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q \
-p no:cacheprovider tests/test_m27_w5_p24_p16_b13_witness_gate_v1_experimental.py
\`\`\`

Ruff only applies to the two newly authored P24 Python paths. Exact stdout, OS child exit, test count, Git commit and SHA256 must be reported from real execution, never inferred from test definitions.

## Security and deployment

This experimental source is a **read-only admission candidate**. It does not produce external signoff, an official 523 or blind Phase B score, a true native client ACK, OCI signature, independent license/custody verification or Provider bill, and cannot update canonical M16 or Production. Keep \`W5_FULL_COMPLETE=false\`, \`W6_AUTHORIZED=false\`, \`REL01_CERTIFIED=false\`, \`REL02_AUTHORIZED=false\`, \`PRODUCTION_AUTHORIZED=false\`. Historical J20/V17 NO-GO remains in force.

Safety-refused original P16/B13 operations shall not be reissued through this verifier, subprocesses, wrappers or alternate executors. A legitimate original scope may only be admitted later with independently authorized, genuine already-existing proof and a separate reviewing authority.
