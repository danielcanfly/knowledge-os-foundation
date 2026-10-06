# M27 Production Evidence Bridge Report (44)

Status: PROD_EVIDENCE_BRIDGE_READY
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-prod-evidence-bridge`
Branch: `m27/prod-evidence-bridge`
Base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`
Final HEAD: final commit of this branch; see final execution response.

## Mission result

This session closes the current admission blocker scoped by `01_PRODUCTION_EVIDENCE_BRIDGE_PROMPT.md`: M27 executable runtime can now accept a formal production-equivalent M26 evidence authority without weakening citation, provenance, ACL, release, or rollback governance.

No admission, fresh smoke, Stage13/14 chain, Chunk002, 100-case, full523, production deploy, production restart, production rebuild, production R2/Qdrant/SQLite write, or release pointer write was performed.

## Implementation summary

Added `src/knowledge_engine/m27_production_evidence_bridge.py` with a fail-closed `ProductionEvidenceAuthority` contract. The authority pins:

- a read-only `ProductionAnswerBundle`;
- release id and manifest SHA;
- allowed ACL audiences;
- formal M26 runtime evidence binding digests keyed by evidence id.

The bridge admits only M26 PA7 runtime-owned evidence identities. Evidence must retain runtime-owned evidence ids and locator ids, exact source identity, exact section/concept identity, release-bound artifact key, artifact SHA, passage text SHA, and provenance record SHA. Citation publication is rejected unless the emitted citation preserves the admitted evidence binding.

Updated `M27ExecutableRequest` with optional `production_evidence_authority`. When absent, the path remains synthetic-only and explicitly not production authority. When present, M27 validates the authority before read-only retrieval, admits only formally pinned evidence, then invokes the existing M26.3 compiler and M26 semantic verifier. M27 can narrow to safe terminal but cannot approve a result rejected by M26.

Updated M26 PA7 evidence construction to include explicit `audience` on passage, graph-edge, and provenance evidence items so the bridge can enforce ACL decisions at the boundary without re-running production retrieval.

## Exact evidence authority boundary

Production-equivalent authority is granted only by `ProductionEvidenceAuthority`, not by memory, retrieval output, context compilation, or caller-supplied text. The authority boundary is:

1. M26 production-equivalent bundle authority: `ProductionAnswerBundle` release id, manifest digest, artifact keys, artifact digests, optional pointer identity, and production status.
2. M26 runtime evidence authority: evidence ids must be M26 PA7 runtime-owned (`m26pa7ev_*`), locators must be runtime-owned, and the precomputed binding digest must match the exact immutable fields.
3. Source and locator authority: `source_identity`, `source_id`, `section_id`, `concept_id`, `locator_id`, `artifact_key`, `artifact_sha256`, `release_id`, `passage_text_sha256`, and `provenance_record_sha256` cannot drift.
4. ACL authority: passage and related provenance/graph evidence must be backed by release documents whose audience is inside the pinned allowed audience set.
5. Citation authority: published citations must preserve evidence id, locator id, source id, section id, concept id, release id, source identity, provenance digest, source artifact SHA, support text SHA, source locator, and `runtime_owned_locator=true`.
6. Compiler boundary: M26.3 context compiler remains a synthetic selector/manifest builder and is recorded as `m26_3_synthetic_selector_non_authoritative` when production-equivalent evidence is used. It does not mint production authority.
7. Verifier boundary: existing M26 semantic synthesis and verification remains authoritative. M27 fails closed on verifier gap, provider budget exhaustion, binding drift, missing provenance, source/locator/release mismatch, and unauthorized capability.

## Production-equivalent artifacts inventoried

The bridge reuses existing production-equivalent M26 shapes:

- `ProductionAnswerBundle` from `m26_production_answer_bundle.py` for manifest/artifact/release identity.
- M26 PA7 evidence items from `m26_pa7_arbitrary_query_runtime.py` for passage, graph-edge, and provenance evidence.
- M26 PA7 public citation fields for locator/source/release/provenance/artifact binding.
- M26.3 `compile_context_package` for selected-passage context construction.
- M26 semantic `synthesize_and_verify` for answer and citation verification.

## Tests added

Added `tests/test_m27_production_evidence_bridge.py` covering:

- valid production-equivalent evidence compiles and verifies through M27 runtime;
- source mismatch is rejected before provider publication;
- locator mismatch is rejected before provider publication;
- release mismatch is rejected fail-closed;
- missing provenance digest is rejected;
- memory cannot supply production evidence authority;
- synthetic-only path remains explicitly not production authority.

## Test results

Commands run:

```bash
PATH=/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin:$PATH PYTHONPATH=src:. \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest \
  tests/test_m27_production_evidence_bridge.py tests/test_m27_runtime_finalization.py -q
```

Result: `19 passed in 1.11s`.

```bash
PATH=/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin:$PATH PYTHONPATH=src:. \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_3_context_compiler.py \
  tests/test_m26_pa_4_verified_answer_citation_gate.py \
  tests/test_m26_11_production_authority.py \
  tests/test_m26_aq_production_entrypoint.py -q
```

Result: `35 passed in 11.46s`.

```bash
PATH=/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin:$PATH PYTHONPATH=src:. \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest tests/test_m27_*.py -q
```

Result: `511 passed in 10.86s`.

```bash
PATH=/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin:$PATH PYTHONPATH=src:. \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest \
  tests/test_m27_production_evidence_bridge.py \
  tests/test_m27_runtime_finalization.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_3_context_compiler.py \
  tests/test_m26_pa_4_verified_answer_citation_gate.py \
  tests/test_m26_11_production_authority.py \
  tests/test_m26_aq_production_entrypoint.py -q
```

Result: `54 passed in 13.61s`.

```bash
PATH=/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin:$PATH PYTHONPATH=src:. \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m compileall -q src/knowledge_engine tests

git diff --check
```

Result: PASS.

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m ruff check \
  src/knowledge_engine/m27_runtime_execution.py \
  src/knowledge_engine/m27_production_evidence_bridge.py \
  tests/test_m27_production_evidence_bridge.py
```

Result: PASS.

Note: full-file Ruff over `src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py` is not a scoped gate here because that pre-existing large runtime file has unrelated legacy lint debt. This session changed only three audience-field additions in that file; coverage is by compileall and the M26/M27 tests above.

## Forbidden actions check

Confirmed by scope and commands:

- No production mutation.
- No production restart/stop/rebuild/deploy.
- No production R2/Qdrant/SQLite/release pointer write.
- No admission or fresh smoke.
- No Stage13/14 legacy chain.
- No Chunk002, 100-case, or full523.
- No dirty import from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.

## Decision

`PROD_EVIDENCE_BRIDGE_READY`

Production-equivalent evidence can safely enter M27 runtime execution when, and only when, it is backed by a pinned `ProductionEvidenceAuthority` and survives the release/source/locator/passage/provenance/ACL/citation binding checks above.

## Whether 04 can start

YES. Session 04 can start from this branch after the final commit, scoped to its own prompt. This does not authorize admission, fresh smoke, Stage13/14 legacy admission, production deployment, or production mutation by itself.
