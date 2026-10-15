# A07 Governed Memory and Revocation (Nonprod-only)

This independent, first-party local-only component implements the **A07** bounded acceptance scope. Nothing was written to frozen Q34, I37, other workers, shared run state, remote R2/provider/IdP, Production, or protected test material.

## Storage and authority

- **authority.sqlite**: durable source consent, tenant/principal binding, source generation, expiry, source tombstones, erased-memory tombstones, event journal, snapshot manifests/invalidations. **Not included in snapshots.**
- **memories.sqlite**: typed `PROJECT/EPISODIC` candidate summaries plus many-to-many source/version lineage.
- **derived.sqlite**: cache bytes and exact per-source/version lineage; every read revalidates memory and all sources against authority.
- **blobs/**: source bytes, SHA-256 checked and restricted to an owned local path.
- **snapshots/**: versioned SQLite-local memory/cache checkpoints with SHA-256 integrity; invalidated snapshots are removed during local cleanup.
- Revoke commits the authoritative tombstone first. Missing/broken cleanup never reinstates authority. `recover_cleanup(tenant=...)` is idempotent and retries local deletions.

**Failure model:** lease/actor identity is a claimed value here, not a real IdP claim. An upstream identity adapter must attest it. This module is not an authorization service for a real remote client. Corruption or reversal of the separate authority database itself is outside this local fixture's trust model and would require protected immutable authority/recovery infrastructure.

## Safe ABI

`candidate(tenant, principal, memid)` returns `a07.governed-memory/v1` with source IDs, consent/version lineage, and an immutable **candidate-only** status. The four fields `knowledge_authority`, `citation_eligible`, `answer_context_enabled`, `can_promote_to_knowledge` are **always false**. `to_evidence()` fails closed even for an active candidate. Do not treat a memory summary as a valid citation, external fact, or verified answer.

When binding this to A05/A06, re-evaluate the authoritative source permissions immediately before every downstream context/publish action. A previously acquired string or stale buffer is **not** a revocable external transport. Native A05/A06 integration is reserved for the sole Master-approved integrator.

## Reproduce

From this folder:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B before_m28_probe.py
# Intentional exit 1: old M28 run-wide revoke cannot preserve independent source s2.
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.11 -B -m unittest -v test_a07_memory
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest -v test_a07_memory
```

A07 has independent **real OS subprocess**, SQLite file writes/read-after-restart, multi-source lineage, per-tenant principal rejection, TTL, atomic source-level revoke, per-memory erasure, corrupt blob, snapshot tamper, snapshot restore, post-revoke forced-file-rollback, forged source version, cleanup interruption and recovery tests. No tests use skip/xfail/mock network claims.

## Explicit limits

- This component does **not** prove external provider/R2/cloud-backup physical erasure or SQLite device-level secure overwrite. Deleting owned local files is not forensic storage erasure; SQLite pages, storage snapshots and journal remnants may remain.
- It does **not** establish a source-rights/licensing judgment, valid remote consent instrument, actual verified principal, A05 publication gate, A06 true task execution, Q34 release, signed OCI, official evaluator result, or Production readiness.
- The old M28 code is only **read** by `before_m28_probe.py`, never edited. Original Q34, Q33, I37 and other workers remain untouched.
- Recovering after local tombstone protects **authorized reads**; it cannot revoke bytes already materialized in the hands of an untrusted external consumer before revocation. The downstream integration must enforce a fresh gate before publication.
