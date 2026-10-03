# M27 Stage 3 Context / Evidence Boundary Extraction Report

Date: 2026-10-03
Workspace: `/home/ubuntu/LLM_Wiki-m27-stage3-boundary`
Branch: `m27/stage3-context-evidence-boundary`
Base: `acd68cd1`

## 1. Summary of files changed

Stage 3 changes are M27-only:

- `src/knowledge_engine/m27_context_runtime_contracts.py`
  - backward-compatible Stage 3 contract extension
  - adds `EvidenceIdentity`, `EvidenceGapSummary`, `EvidencePlanningResult`, and `EvidencePlanner`
  - adds explicit `unavailable_in_stage3` marker for signals that cannot be obtained non-invasively
- `src/knowledge_engine/m27_evidence_planner.py`
  - adds `LegacyM26EvidencePlannerAdapter`
  - normalizes already-produced M26 evidence identity and existing gap/sufficiency signals
  - never re-runs retrieval, evidence selection, strengthening, reranking, or support scoring
- `src/knowledge_engine/m27_context_evidence_boundary.py`
  - exposes the EvidencePlanner and existing ContextCompiler normalization as separate responsibilities
  - never compiles context itself
- `tests/test_m27_evidence_planner.py`
  - identity, gap/sufficiency, missing-signal, privacy, adapter-only, and protocol tests
- `tests/test_m27_context_evidence_boundary.py`
  - boundary separation, context-manifest/citation preservation, compiler-budget-subset, privacy, abstention, and Stage 2 replay-lens tests
- `docs/m27/research/stage3_context_evidence_boundary_report.md`
  - this report

No `m26_*.py` file or `test_m26_*.py` file was modified.

## 2. Exact EvidencePlanner boundary

The Stage 3 EvidencePlanner boundary is:

```text
already-produced M26 retrieval/evidence result
+ already-derived requirements when available
+ already-produced support classification when available
+ already-produced endpoint/recovery proof when available
+ already-produced sufficiency/reason codes when available
        |
        v
LegacyM26EvidencePlannerAdapter.normalize(...)
        |
        v
EvidencePlanningResult
  selected evidence identity only
  selected evidence count
  deterministic evidence ids where already present
  passage ids where already present
  source identities using existing M26 identity semantics
  locator ids where already present
  requirement ids
  covered/missing requirement ids only from existing support classification
  existing sufficiency state
  existing bounded-recovery metadata
  sanitized reason codes
```

EvidencePlanner owns the conceptual question **"which evidence was selected / what evidence coverage or gap exists?"**

It does **not** own:

- lexical/dense retrieval execution
- graph traversal execution
- provider calls
- a second `_select_evidence`
- a second `_strengthen_evidence`
- new evidence scoring
- new evidence-quality policy
- new sufficiency policy
- context token budgeting
- context excerpt normalization
- context manifest construction
- citation construction
- verification/publication

The Stage 3 adapter is observation/normalization only. Tests monkeypatch M26 `_select_evidence` and `_dynamic_evidence_budget` to fail if called; normalization still succeeds.

## 3. Exact ContextCompiler boundary

The canonical implementation remains:

```text
src/knowledge_engine/m26_context_compiler.py
```

Stage 3 preserves the existing contract:

```text
already-selected evidence envelope + existing gap + context policy
        |
        v
M26 ContextCompiler
        |
        v
deterministic context package
+ context manifest
+ evidence budget receipt
+ citations
+ safe-for-provider state
+ prompt-injection quarantine state
```

The Stage 3 boundary reads an **already-produced** compiler package through the existing Stage 1 `LegacyM26ContextCompilerAdapter`; it does not call `compile_context_package` again.

The following remain ContextCompiler responsibilities:

- envelope/gap/policy validation
- safe-for-context validation
- mandatory conflicting-evidence preservation
- token budget enforcement
- reserved instruction budget
- optional evidence `budget_precheck` exclusion
- fail closed when mandatory evidence cannot fit
- deterministic whitespace/excerpt normalization
- context manifest construction
- context manifest digest
- evidence budget receipt digest
- citation binding
- prompt-injection quarantine
- `abstain_required` compilation failure

Important boundary clarification: the compiler's token-budget-driven passage subset is a **compilation-time selection**, not a second retrieval/evidence-planning policy. Stage 3 intentionally leaves that behavior in the compiler.

## 4. Mapping from current M26 functions/signals

### Evidence planning side

| M26 function/signal | Stage 3 interpretation |
|---|---|
| `m26_pa7_arbitrary_query_runtime._select_evidence` | canonical existing evidence selection behavior; Stage 3 does not call or reimplement it |
| `_dynamic_evidence_budget` | existing planner-side evidence-count budget; observed indirectly through already-selected evidence, never recalculated |
| `_select_diverse_candidates` | existing source/concept diversity selection policy; not duplicated |
| `_ensure_query_coverage_passages` | existing query-coverage augmentation; output evidence metadata may be normalized, behavior not rerun |
| `_ensure_required_facet_coverage_passages` | existing facet-coverage augmentation; Stage 3 consumes existing requirement/support signals only |
| `_ensure_distinct_passage_sources` | existing source-diversity behavior; Stage 3 reports distinct source identity count from selected evidence |
| `_graph_evidence_bundle` / graph evidence items | existing graph-evidence planning behavior and deterministic identities |
| `_provenance_evidence_bundle` / provenance evidence items | existing provenance-evidence planning behavior and deterministic identities |
| `_temporal_evidence_bundle` / temporal evidence items | existing temporal-evidence planning behavior and deterministic identities |
| `_dedupe_evidence` | existing dedupe behavior; not re-run by Stage 3 |
| `m26_aq_semantic_contract.derive_semantic_requirements` | canonical requirement source; Stage 3 accepts already-derived requirement IDs |
| `m26_pa7_semantic_closure_runtime._facet_support_classification` | existing support state source: `SUPPORTED`, `UNSUPPORTED`, `UNKNOWN`; Stage 3 does not recompute scores |
| `m26_pa7_semantic_closure_runtime._strengthen_evidence` | existing bounded requirement recovery; Stage 3 accepts existing `recovered_facets` and bounded-recovery boolean only |
| runtime `selected_evidence_count` | existing count signal; Stage 3 also preserves exact input selected-evidence count |

### Evidence identity side

Existing M26 evidence records already carry deterministic identity fields such as:

- `evidence_id`
- `locator_id`
- `source_identity`
- `source_id`
- `section_id`
- artifact identity
- passage text digest

Stage 3 preserves existing IDs verbatim. For source identity fallback, Stage 3 reuses the current M26 `_source_identity` semantics only when the required source/artifact fields are already present. It does not generate random IDs or derive identities from raw text.

### Context compilation side

| M26 function/signal | Stage 3 interpretation |
|---|---|
| `_validate_envelope` / `_validate_gap` / `validate_context_policy` | compiler validation |
| `_mandatory_passage_ids` | mandatory conflicting-evidence preservation |
| `build_context_manifest` | compiler deterministic budgeting, excerpts, manifest, budget receipt |
| `compile_context_package` | compiler package, citation binding, safe/provider flag, quarantine, fail-closed abstention |
| `context_manifest_sha256` | preserved verbatim by existing Stage 1 compiler adapter |
| `evidence_budget_sha256` | preserved verbatim |
| `context_manifest.selected_passage_ids` | preserved as compiler-side passage identities |
| `citations` | only citation count is retained by normalized boundary object; raw quote/evidence body is not retained |
| `safe_for_provider_mock` | normalized as existing safe-for-provider state |
| `diagnostics.prompt_injection_quarantined` | preserved boolean |
| `diagnostics.reason_codes` | preserved by existing compiler adapter |

## 5. New contracts/protocols/dataclasses

Added to `m27_context_runtime_contracts.py`:

```text
STAGE3_UNAVAILABLE
Stage3Unavailable
EvidenceIdentity
EvidenceGapSummary
EvidencePlanningResult
EvidencePlanner Protocol
```

Added implementation objects:

```text
LegacyM26EvidencePlannerAdapter
ContextEvidenceBoundaryResult
LegacyM26ContextEvidenceBoundary
```

The Stage 1/2 contract behavior is unchanged. Existing contract tests remain green.

## 6. Evidence identity guarantees

Stage 3 guarantees:

1. Existing `evidence_id` is preserved verbatim.
2. Existing `passage_id` is preserved verbatim when present.
3. Existing `locator_id` is preserved verbatim.
4. Existing `source_identity` is preferred verbatim.
5. If explicit `source_identity` is absent, existing M26 source-identity semantics are reused from already-present source/artifact fields.
6. No random identity is generated.
7. Raw evidence text is never used as identity.
8. No LLM/provider is used to infer source identity.
9. If a complete identity cannot be obtained non-invasively, the aggregate identity field is `unavailable_in_stage3` rather than fabricated.
10. Evidence IDs and compiler passage IDs remain separate fields. Stage 3 does not assume they are interchangeable.

Focused tests intentionally use different values for `evidence_id` and `passage_id` to enforce this separation.

## 7. Gap/sufficiency metadata and source

Normalized fields:

```text
selected_evidence_count
distinct_source_count
requirement_ids
covered_requirement_ids
missing_requirement_ids
coverage_status
sufficiency_status
recovered_requirement_ids
bounded_recovery_used
reason_codes
```

Sources:

- `covered_requirement_ids` and `missing_requirement_ids` come only from an already-produced M26 support classification.
- `coverage_status` is a structural summary of that supplied classification:
  - `covered` when all supplied requirements are already classified `SUPPORTED`
  - `gap_present` when an existing classification reports `UNSUPPORTED` or `UNKNOWN`
  - `not_applicable` when there are no requirements
  - `unavailable_in_stage3` when the required existing classification is absent or incomplete
- `sufficiency_status` is accepted only when it is one of the existing M26 envelope states:
  - `sufficient`
  - `partially_sufficient`
  - `conflicting`
  - `insufficient`
  - `no_match`
- `recovered_requirement_ids` comes from existing `endpoint_proof.recovered_facets`.
- `bounded_recovery_used` comes from existing `endpoint_proof.bounded_authorized_corpus_recovery`.
- `reason_codes` retain only short code-shaped values. Free-form text is not copied into the Stage 3 boundary object.

Stage 3 does not infer sufficiency from evidence count, source count, coverage status, or a new threshold.

## 8. Context manifest/citation preservation

The boundary uses the existing `LegacyM26ContextCompilerAdapter`.

For supplied already-produced compiler output, tests prove preservation of:

- `status`
- `context_manifest_sha256`
- `evidence_budget_sha256`
- `context_manifest.selected_passage_ids`
- citation count
- safe-for-provider state
- prompt-injection quarantine state
- compiler reason codes
- explicit `None` manifest/budget digests on `abstain_required`

The boundary also tests the legitimate case where EvidencePlanner supplies two evidence items but the compiler package contains a one-passage budgeted subset. Stage 3 preserves both sides independently and does not reinterpret compiler budget pruning as planner drift.

Context manifest drift observed: **NONE** in the deterministic Stage 3 tests.
Citation drift observed: **NONE** in the deterministic Stage 3 tests.

## 9. Privacy guarantees

The new Stage 3 contract/boundary objects contain identity/count/status metadata only.

They do not contain fields for:

- raw query
- raw answer
- full evidence text
- full source text
- provider prompt
- instruction block text
- exact citation quote
- secret
- credential
- environment value
- private payload

Tests inject explicit private marker strings into evidence bodies, compiled excerpts, exact quotes, provider context, provider prompts, and raw answers and verify none appear in the normalized result representation.

Recovery action bodies are deliberately not copied. Only allowed requirement IDs and a bounded-recovery boolean are retained.

## 10. Tests run and exact results

Focused Stage 3 compile:

```bash
python3 -m compileall -q   src/knowledge_engine/m27_context_runtime_contracts.py   src/knowledge_engine/m27_evidence_planner.py   src/knowledge_engine/m27_context_evidence_boundary.py   tests/test_m27_evidence_planner.py   tests/test_m27_context_evidence_boundary.py
```

Result:

```text
PASS
exit 0
```

Focused Stage 3 pytest:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage3-boundary/src   /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m27_evidence_planner.py   tests/test_m27_context_evidence_boundary.py
```

Result:

```text
13 passed in 0.50s
```

Required full compile:

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage3-boundary

python3 -m compileall -q   src/knowledge_engine   tests
```

Result:

```text
PASS
exit 0
```

Required Stage 1/2/3 M27 pytest gate:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage3-boundary/src   /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m27_context_runtime_contracts.py   tests/test_m27_legacy_m26_adapters.py   tests/test_m27_decision_trace.py   tests/test_m27_replay_harness.py   tests/test_m27_equivalence_report.py   tests/test_m27_evidence_planner.py   tests/test_m27_context_evidence_boundary.py
```

Result:

```text
63 passed in 1.37s (final pre-commit rerun)
```

Required Ruff gate:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check   src/knowledge_engine/m27_*.py   tests/test_m27_*.py
```

Result:

```text
All checks passed!
```

No full 523 was run.
No Docker build was run.

## 11. Replay/equivalence findings

Stage 2 remains the canonical regression lens.

The Stage 3 boundary test sends the same already-produced compiled package through:

1. `LegacyM26ContextEvidenceBoundary.normalize(...)`
2. the existing Stage 2 `capture_sanitized_replay_input(...)` + `run_replay_equivalence(...)`

For the boundary fixture, Stage 2 classifies all relevant compiler fields as `EQUIVALENT`:

- selected evidence/passages count
- selected evidence/passages identity tuple
- context compiler status
- context compiler citation count

Stage 3 direct assertions additionally prove preservation of compiler fields that Stage 2 does not yet contract-normalize:

- context manifest SHA-256
- evidence budget SHA-256
- safe-for-provider state
- prompt-injection quarantine state

No Stage 2 normalization or safety contract was weakened.

## 12. Missing/unavailable signals

Stage 3 explicitly reports unavailable rather than inventing data when:

- runtime selected evidence does not carry a `passage_id`
- an evidence item has no usable existing source identity fields
- locator identity is absent
- requirement IDs are unavailable
- requirement support classification was not already produced/supplied
- existing support classification is incomplete for supplied requirements
- existing M26 sufficiency state was not supplied
- endpoint/recovery proof was not supplied
- compiler manifest does not exist because compilation failed closed

Additional known Stage 1/2 limitations remain unchanged:

- Stage 2 does not contract-normalize context-manifest digest
- Stage 2 does not contract-normalize safe-for-provider state
- Stage 2 does not contract-normalize prompt-injection quarantine state
- citation shape and some guard outcomes remain unavailable at the Stage 1 adapter layer

Stage 3 does not pretend those fields are equivalent.

## 13. Blockers encountered

No implementation blocker remains.

Tooling-only issues:

- one initial remote write command failed locally due shell quoting
- one alternate large command form was rejected by the LocalBridge safety layer
- worktree remained clean after both failures
- writing continued through the authorized persistent `ssh oracle-vm` LocalBridge session
- no M26 or production state was affected

No blocker required modifying:

- `m26_context_compiler.py`
- `m26_aq_semantic_contract.py`
- `m26_pa7_arbitrary_query_runtime.py`
- `m26_public_api.py`
- `m26_console_api.py`

## 14. Remaining risks

1. Stage 3 is an extraction/normalization layer and is intentionally not wired into the production answer path.
2. Runtime evidence IDs and context-compiler passage IDs are distinct identity domains unless an upstream envelope explicitly provides both. Stage 3 keeps them separate.
3. The canonical runtime evidence-strengthening function currently lives in `m26_pa7_semantic_closure_runtime.py`; Stage 3 maps it but does not move it.
4. Support classification must be supplied as an already-produced signal. Stage 3 intentionally refuses to call the private M26 support scorer itself.
5. ContextCompiler can legitimately select a token-budgeted subset of planner-selected evidence. Equality between planner evidence count and compiler passage count is therefore not a required invariant.
6. Stage 2 replay still lacks normalized manifest-hash/safe-provider/quarantine fields. Stage 3 tests cover those directly, but future replay expansion could add them without changing behavior.
7. Broader Master validation still needs the documented 49 M26 safe baseline + all M27 Stage 1/2/3 tests + isolated health + production invariant check.

## 15. Confirmation M26 core behavior was unchanged

Confirmed.

```text
M26 core source diff: none
M26 baseline test file diff: none
retrieval behavior change: none
evidence selection behavior change: none
evidence strengthening behavior change: none
context compiler behavior change: none
verifier behavior change: none
publication behavior change: none
answer behavior change: none
```

The permanent generic extractive fallback guard was not modified:

```python
# Guard: do not emit generic extractive evidence fallback as user-facing answer.
return None
```

## 16. Confirmation production untouched

Production touched: **NO**.

This Stage 3 sub-session performed only:

- read-only source/document inspection through `ssh oracle-vm`
- writes inside `/home/ubuntu/LLM_Wiki-m27-stage3-boundary`
- Python compile/tests/lint using the existing M27 dependency environment

It did not:

- restart production
- restart the isolated M27 runtime
- modify production routes
- modify nginx/Cloudflare
- write R2
- write Qdrant
- write production SQLite
- call a live provider
- perform a new retrieval round against production
- promote/rollback a release
- build Docker
- run full 523

## 17. Recommendation whether Stage 4/5 can begin

Stage 3 sub-session recommendation:

```text
READY_FOR_MASTER_INTEGRATION
```

Stage 4/5 should begin only after Master:

1. reviews/cherry-picks this Stage 3 commit,
2. reruns the 49 M26 safe baseline,
3. reruns all M27 Stage 1/2/3 tests,
4. confirms isolated health,
5. confirms production invariants.

Stage 3 itself does not start Stage 4 or Stage 5.

## Required boundary questions

### Can EvidencePlanner and ContextCompiler now be reasoned about as separate responsibilities without changing M26 behavior?

**Yes.**

EvidencePlanner is represented as normalization of already-produced evidence identities and existing coverage/gap/sufficiency signals. ContextCompiler remains the existing deterministic evidence-in/context-package-out compiler. Stage 3 does not rerun either behavior.

### Did context manifest or citation behavior drift?

**No drift observed.**

The deterministic Stage 3 tests preserve context manifest identity, compiler-selected passage identities, citation count, safe-for-provider state, and prompt-injection quarantine state from the supplied already-produced compiler package.

### Did selected evidence identity drift?

**No drift observed.**

Existing evidence IDs, passage IDs when present, locator IDs, and source identities are preserved verbatim. Missing identities are marked unavailable instead of regenerated.

### Did any production invariant weaken?

**No.**

No M26 behavior was changed, the generic extractive fallback guard remains untouched, unsupported material claims still remain verifier-controlled, citation binding is unchanged, safe abstention remains conservative, and production was not touched.
