# B0-06 | G03 scope disposition and G04 bounded interface

Date: 2026-10-17. Worker-only scope decision; no Owner/custodian/Provider grant is asserted.

## G03 boundary matrix

| Candidate operation | Evidence / required boundary | Disposition |
|---|---|---|
| Read original D01 AR08, AR04, AR06, M28, TaskContract and context boundary | Audit and shared B0 rules permit read-only evaluation | READ ONLY; inspected, no modifications |
| Change original M27 \`m27_w3_ar08_coding_action_v1_experimental.py\`, including same-dispatch persisted coding patch | Earlier explicit equivalent AR08 source edit refusal recorded by Master/audit; changing host, branch, filename or session does not change scope | **HOLD / DO NOT RETRY** |
| Duplicate original AR08 same-dispatch source edit through renamed local harness, toy file, alternate repository or host | Cosmetic relabeling of refused behavior is equivalent to refused operation | **DENIED; NOT ATTEMPTED** |
| Execute AR04 real external Action, deploy, paid provider or Production mutation | AR04 experimental boundary is inert: provider_calls=0; no independent authorized endpoint, issuer/permit and reconciliation grant | **HOLD; NOT ATTEMPTED** |
| Merely run existing AR08 arithmetic fixture and call it real persistent Coding | AR08 local fixed-arithmetic fixture and in-process verifier are insufficient for full F35 Coding outcome | **NOT QUALIFIED; NO PROMOTION** |
| Truly new owner-authorized, non-equivalent Coding sandbox | Would need precise authorized source owner, source tree, action, target, allowlist, signed actor grant, independent reviewer and proof of separation from the refused AR08 edit | **PROPOSED_ONLY; no new permission identified** |
| Add independent fixture-only G04 revocation ABI and local tests in worker-exclusive filenames | Separate from refused coding patch; shared D01 and all Product handlers untouched | **AUTHORIZED SCOPED NONPROD WORK** |

A future G03 approval must identify the exact permitted code location and workload, prove it is substantively distinct from the previously refused AR08 same-dispatch edit, bind the authorized actor and source owner, specify available OS/sandbox permissions, idempotent execution and independently observed output, and define exact stop/abort and negative tests. The issuer must grant that authority separately. An Owner wish to complete F35 is not itself an override of a platform refusal.

## Existing contracts inspected, without edits

- \`m27_w3_ar08_coding_action_v1_experimental.py\`: fixed add/multiply fixture, predeclared source digest, isolated local temporary directory, in-process fixture verifier. This is not a general real Coding patch.
- \`m27_ar04_safe_action_experimental.py\`: explicitly inert Action send boundary with no provider adapter, no external effect.
- \`m27_ar06_governed_memory_experimental.py\`: in-memory generation/tombstone/cascade fixtures; simulated deletion evidence cannot prove external erasure.
- \`m27_m28_local_rights_memory_fence.py\`: local durable right/consent fence, tombstone-before-cleanup with quarantine, no external provider rights.
- \`m27_task_contracts_v1.py\`: existing versioned Task/Outcome contract, unchanged.
- \`m27_context_evidence_boundary.py\`: existing context evidence boundary, unchanged.

## G04 interface, explicitly fixture-only

Code: \`src/knowledge_engine/m27_b0_revocation_contract.py\`.

1. Authority is a dedicated SQLite database, separate from the replaceable artifact SQLite DB. All mutations are SQLite \`ATTACH\` transactions in DELETE journal mode. An independent real trust provider **does not** exist here.
2. \`SourceLease\` binds tenant, principal, source, source revision, right version, consent expiry and revocation epoch. Every local read or write reacquires authoritative scope in a transaction and fails closed on revocation, ACL downgrade, consent expiry, or stale version/epoch.
3. \`revoke()\` first atomically invalidates authority and local descendants (\`source\`, \`answer_cache\`, \`derived_cache\`, \`citation\`, \`memory\`), then commits a digest-bearing **local audit witness**. A repeated event is idempotent; repeated different event IDs are denied after revocation.
4. Local \`audit_witness()\` is not cryptographically signed by an independent custodian. \`deleted_entries\` counts only local rows, not remote/vector/index replicas, external backup or physical media. \`external_erasure_verified=False\` is permanent in this interface.
5. Restoring a stale *artifact-only* snapshot cannot resurrect source rights because the separate authority retains its epoch/tombstone. \`recover_restored_artifacts_fixture()\` removes local restored descendants after denial.
6. \`downgrade_acl_fixture()\` and \`advance_right_version_fixture()\` make old leases and derived entries unusable. No silent same-scope regrant after revocation.

### Test boundaries and explicit risk exceptions

- A caller-supplied \`authorized_fixture=True\` is only a simulation. The fixture caller is not a trusted real IdP, principal proof or custody grant. CACHE-03/H02 must bind actual authenticated principal and non-forgeable grants before integration.
- The protected authority DB itself must resist rollback. Restoring **both** authority DB and artifact DB, deleting authority records, or bypassing the API to read raw files is **not** prevented by this prototype. Admission needs external immutable/monotonic authority custody and tested backup policy.
- Physical deletion from WAL, drive snapshots, caches beyond this DB, Qdrant, external providers and all replicated descendants is **not** established. No legal hold handling, independent remote deletion receipts, or real erasure SLA is claimed.
- A source-wide revocation across multiple authorized principals currently requires the integrator to enumerate/atomically invalidate **all** affected principal scopes; this prototype intentionally models principal-scoped source rights and cannot be the sole source-wide registry.
- The separate databases must live on one filesystem for SQLite multi-file atomicity guarantees. The design uses DELETE journal mode, not WAL, and does not claim distributed transaction safety.
- The source-right versions here are numeric fixture versions; policy/consent document signatures and real lineage proofs must be introduced and evaluated at integration.
- The persisted audit witness is SHA-256 integrity metadata, not independent nonrepudiation.

## CACHE-03 / F03 / H02 obligations

- CACHE-01 must first freeze its versioned schema; *do not* modify/cache-hook its pending contract now.
- CACHE-03 must map cache record tenant/principal/source-right version/source revision/revocation epoch to authenticated immutable source catalog and live ACL/consent checks; invalidate primary, vector/embedding index, citation, answer cache, checkpoint and backup descendants.
- F03 must pass immutable verified source identifiers and verifier/source bindings; similarity retrieval is merely a candidate, never an authorized HIT.
- H02 sole Integrator must arrange read/write serialization with real transactional source-right registry and cache store, dynamic cache OFF default, cross-source dependency graph, source-wide revocation fan-out, backup replay fences and reliable deletion receipts. Do not replay side effects from cached Coding or Actions.
- Neither this patch nor its test subset activates cache ON, completes F35, changes Production, or admits full G03 Coding/Action.
