# M06 | Governed Memory: Isolated Deny-First Offline Receipts

**Claim:** `AR06_OFFLINE_GOVERNANCE_PROOF` and `ISOLATED_MOCK_COMPONENT_PASS` only if the attached tests, lint and Git evidence are green. This code is a **synthetic, in-process, metadata-only test fixture**. It never retains human/private memory bytes, does not contact a provider, has no durable state or real IdP/consent/reviewer signature, and never physically deletes external objects.

## Threat boundary

- All proposed content is an opaque `synthetic://` ref plus SHA256 metadata. `Candidate`, `ReviewerDecisionFixture`, `AcceptedMemory`, `Revocation`, `Tombstone`, `ReadDecision`, `DeletionCascade` and `AuditReceipt` are frozen typed objects.
- Candidate producer and reviewer must be distinct. Test-only reviewer fixture binds exact tenant, subject, purpose, candidate ID, source revision/digest, proposed digest, policy, consent/lawful basis, zone and expiry. Fixture flags and test receipts **cannot confer real rights**. Candidate strings/taint labels are inert data; model output cannot approve its own write.
- Each read is mediated by an *in-process authoritative simulation* checking current tombstone ledger, revision/ACL, principal test fixture, current consent/basis, policy, purpose, residency, deadline, conflict and budget. Missing ledger denies. `ReadDecision` is `mock_only`, `authorized_real=False`, and `native_citation_eligible=False`.
- Revocation raises a strictly increasing exclusion generation and creates a permanent tombstone. A cached preapproval, read consumer or restored snapshot cannot use a stale generation; legal hold release **never re-enables serving**. Concurrent real-system linearizability is NOT proven by this single-process simulator.
- Every synthetic descendant is tracked by kind, zone and generation. Revocation emits pending/held obligations; verified status needs correctly scoped, independent **simulated** read-after-delete observation, not tool text. Missing graph, backup or index evidence remains PENDING/PARTIAL/EXCEPTION_HELD. A simulated verified cascade cannot be equated to physical erasure.
- The public AR03A `select` adapter is exercised with a memory metadata candidate and **no grant**, and is expected to omit it. Native Q&A original EvidenceBundleRef/citation must not be replaced by a memory ref. No native cited answer, source bytes or external authentication is claimed.
- All deletion requests, including pending, partial and exception-held, remain in the outcome denominator. Report `actual_deletions_verified=0` and `no_real_deletion_guarantee=True`.

## M01–M18 test coverage (synthetic, not production)

| ID | Executable negative requirement |
|---|---|
| M01 | Consent withdrawn while checkpoint/preapproval is stale: consumer and replay deny |
| M02 | Cross-tenant pooled cache references fail at tenant boundary |
| M03 | Competing versions quarantine, not last-write-wins |
| M04 | Expired approval cannot promote |
| M05 | Injected approval/permission text cannot confer review or capability |
| M06 | Cached memory expires before consumption |
| M07 | Disposed checkpoint cannot reconstruct tombstoned memory |
| M08 | Legal hold quarantines backup; held bytes never serve, release remains tombstoned |
| M09 | Purpose/policy expansions require fresh review |
| M10 | Source revision/digest drift denies |
| M11 | Vector receipt alone does not complete missing graph receipt |
| M12 | Pre-withdrawal backup restored after tombstone cannot serve |
| M13 | Provider self-attestation or forged/partial independent receipt fails closed |
| M14 | Cross-region descendant/receipt rejected |
| M15 | Zero token or cost budget denies |
| M16 | Memory metadata cannot replace a native cited source; AR03A denies without grant |
| M17 | Model cannot repromote a revoked candidate |
| M18 | Old read approval is invalid at next authoritative consumption |

Additional fixture checks cover 12 approval binding mutations, current source ACL/consent/ledger, denied identity, duplicate generation/old receipt, immutable dataclasses, no silent successful physical deletions.

## Gate and open dependencies

This package does **not** implement the architecturally gated production M06 milestone. Owner/privacy decisions on retention, lawful basis, legal holds, backup maximum, cross-region data movement, identity and reviewer roles remain unresolved. **AR02 journal, AR04 store/index tool effects, IdP, real authenticated consent, AR05 outcome verification, external cache and physical erasure, real Q&A transport and production admission remain OPEN**. No work on Production, VM, real memory, provider, or previously denied tool paths is authorized. Test logs, exact diff, status, SHA256 and one isolated commit are referenced in the external task-specific receipt and worker report.
