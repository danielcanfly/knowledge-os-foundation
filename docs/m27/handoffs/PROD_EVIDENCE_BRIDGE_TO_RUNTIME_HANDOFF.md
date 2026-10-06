# Production Evidence Bridge to Runtime Handoff

Status: PROD_EVIDENCE_BRIDGE_READY
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-prod-evidence-bridge`
Branch: `m27/prod-evidence-bridge`
Base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`
Final HEAD: final commit of this branch; see final execution response.

## What changed

M27 executable runtime now has a formal production-equivalent evidence bridge. The bridge is deliberately narrow: it does not make M26.3 context compilation a production authority, and it does not read or mutate production state. It admits only evidence that is already pinned to an M26 production-equivalent bundle and then lets the existing M26 semantic verifier remain authoritative for answer publication.

Primary code:

- `src/knowledge_engine/m27_production_evidence_bridge.py`
- `src/knowledge_engine/m27_runtime_execution.py`
- `src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py`
- `tests/test_m27_production_evidence_bridge.py`

## Runtime authority boundary

The exact boundary is:

1. `ProductionEvidenceAuthority` is the only production-equivalent evidence authority accepted by M27 runtime execution.
2. The authority pins a read-only `ProductionAnswerBundle`, release id, manifest digest, allowed ACL audiences, and per-evidence M26 runtime binding digests.
3. Evidence ids must be M26 PA7 runtime-owned (`m26pa7ev_*`), locators must be runtime-owned (`m26pa7loc_*`, `m26pa7edge_*`, or `m26pa7prov_*`), and the immutable binding digest must match.
4. Source identity, locator identity, release id, artifact key, artifact digest, passage digest, and provenance digest must remain unchanged.
5. Passage/provenance/graph evidence must pass ACL checks against release-backed documents.
6. Published citations must preserve the admitted evidence binding and runtime-owned locator.
7. M26.3 context compiler remains a selector/manifest builder and is recorded as `m26_3_synthetic_selector_non_authoritative` when production-equivalent evidence is used.
8. Existing M26 semantic synthesis/verification remains authoritative. M27 may only narrow to safe terminal, never override an M26 rejection.
9. Candidate memory cannot create, replace, or upgrade production evidence authority.

## Test evidence

Passed:

- `tests/test_m27_production_evidence_bridge.py tests/test_m27_runtime_finalization.py`: `19 passed in 1.11s`
- M26 targeted production/citation/compiler suite: `35 passed in 11.46s`
- Full M27 suite: `511 passed in 10.86s`
- Combined core rerun: `54 passed in 13.61s`
- `compileall -q src/knowledge_engine tests`: PASS
- `git diff --check`: PASS
- Ruff on scoped M27 bridge/runtime/test files: PASS

Ruff over `m26_pa7_arbitrary_query_runtime.py` was not used as a scoped gate because the file has pre-existing unrelated lint debt; this session changed only three explicit audience fields in that legacy runtime file. The changes are covered by compileall and the targeted M26/M27 tests above.

## Forbidden actions not performed

- No production mutation.
- No production stop/restart/rebuild/deploy.
- No production R2/Qdrant/SQLite/release pointer writes.
- No fresh small smoke.
- No admission run.
- No Stage13/14 legacy admission chain.
- No Chunk002, 100-case, or full523.
- No dirty import from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.

## Handoff decision

Session 04 can start after this commit, scoped to its own prompt.

This handoff does not authorize admission, fresh smoke, Stage13/14 legacy admission, production deploy, or production mutation by itself.
