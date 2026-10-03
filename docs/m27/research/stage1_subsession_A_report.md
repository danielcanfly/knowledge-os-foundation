# M27 Stage 1A Sub-session Report

## 1. Summary of files changed

Created only the Stage 1A files assigned to this sub-session:

- `src/knowledge_engine/m27_context_runtime_contracts.py`
- `src/knowledge_engine/m27_legacy_m26_adapters.py`
- `tests/test_m27_context_runtime_contracts.py`
- `tests/test_m27_legacy_m26_adapters.py`
- `docs/m27/research/stage1_subsession_A_report.md`

No existing M26 runtime file was modified.

## 2. Exact behavior impact

**NONE.**

The implementation is adapter-only. It accepts M26 signals or outputs that have already
been produced and normalizes them into M27 typed contracts.

It does not:

- invoke a model/provider,
- perform retrieval,
- compile context,
- run verification,
- alter routing,
- alter deadline/provider budgets,
- alter evidence selection,
- alter citations,
- alter answers,
- wire itself into the public or production runtime.

The adapters have no imports from M26 runtime modules. Compatibility with the real
`SemanticRoutingDecision` object is tested structurally.

## 3. Feature flags added or used

None.

Stage 1A did not add or wire `M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED`. That flag and
trace implementation belong to Stage 1B. Stage 1A only defines the trace contract surface
(`DecisionTraceEvent` and `RuntimeTraceStore`) required for integration.

## 4. New contracts / dataclasses / protocols

Dataclasses:

- `ContextPlan`
- `ComputeDecision`
- `EvidencePlan`
- `ContextCompileResult`
- `VerificationDecision`
- `DecisionTraceEvent`
- `PolicyDecision`

Protocols:

- `RuntimeTraceStore`
- `ContextPlanner`
- `ComputePolicy`
- `ContextCompiler`
- `Verifier`

Stage 1 unavailable marker:

- `STAGE1_UNAVAILABLE = "unavailable_in_stage1"`

Fields that cannot be obtained non-invasively from the supplied Stage 1 signal are left as
`unavailable_in_stage1`. No provider/model/retrieval signal is synthesized.

## 5. Adapter-to-M26 signal mapping

### LegacyM26SemanticRoutingAdapter

Input: existing `SemanticRoutingDecision`-shaped object or mapping.

Mapping:

- `route` -> `ContextPlan.route`
- `reason` -> `ContextPlan.reason`
- evidence-planning details -> `unavailable_in_stage1`
- planning mode -> `unavailable_in_stage1`

It does not call `_routing_decision`, `_fast_failure_route`, or
`_semantic_failure_route`.

### LegacyM26DeadlineBudgetAdapter

Input: existing `SemanticRoutingDecision`-shaped object or public mapping.

Mapping:

- `route` -> `ComputeDecision.route`
- `reason` -> `ComputeDecision.reason`
- `deadline_remaining_ms` -> same
- `minimum_budget_ms` -> same
- `provider_attempts_remaining` -> same
- existing `affordable` property/value -> same
- compute tier -> `unavailable_in_stage1`

It does not re-run M26 routing or call a provider. If `affordable` itself is absent, the
adapter does not reimplement the M26 affordability policy; it marks the field unavailable.

### LegacyM26ContextCompilerAdapter

Input: an already-produced `m26_context_compiler.compile_context_package` mapping.

Mapping:

- `status` -> `ContextCompileResult.status`
- `context_manifest_sha256` -> same
- `evidence_budget_sha256` -> same
- manifest/budget `token_budget` -> `token_budget`
- manifest/budget `measured_token_estimate` -> `measured_token_estimate`
- manifest `selected_passage_ids` -> `selected_passage_ids`
- citation list length -> `citation_count`
- `safe_for_provider_mock` -> `safe_for_provider`
- diagnostics `prompt_injection_quarantined` -> same
- diagnostics `reason_codes` -> `reason_codes`

It intentionally does not copy context text, instruction blocks, derived excerpt text, or
full citation/evidence bodies.

### LegacyM26VerifierAdapter

Input: existing M26 verification/final-response mapping.

Mapping:

- `status`
- `terminal_status`
- `safe_abstention`
- `reason_codes`
- `provider_call_count`
- `material_claim_support_verified`
- `citation_locator_valid`
- `unsupported_accepted_claims`
- `repair_attempted`
- citation list length -> `citation_count`
- `answer_source`

The adapter intentionally excludes `answer_text`, answer claims, citation bodies, full
evidence text, and support-proof bodies.

## 6. Tests run with exact command and output

Required compile command:

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage1-a

python3 -m compileall -q \
  src/knowledge_engine/m27_context_runtime_contracts.py \
  src/knowledge_engine/m27_legacy_m26_adapters.py \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py
```

Result:

```text
exit 0
(no output)
```

The exact requested pytest command was also executed:

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage1-a

/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py
```

Initial result:

```text
2 errors during collection
ModuleNotFoundError: No module named 'knowledge_engine.m27_context_runtime_contracts'
```

This is a worktree interpreter-path issue, not a code failure. The specified master
interpreter resolves `knowledge_engine` from:

```text
/home/ubuntu/LLM_Wiki-m27-context-runtime/src/knowledge_engine
```

instead of the Stage 1A worktree. The same specified interpreter was therefore run with the
Stage 1A source path explicitly selected:

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage1-a

PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py
```

Result:

```text
............                                                             [100%]
12 passed in 0.41s
```

Additional lint gate:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m27_context_runtime_contracts.py \
  src/knowledge_engine/m27_legacy_m26_adapters.py \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py
```

Result:

```text
All checks passed!
```

## 7. Blockers encountered and status

### Resolved / non-code blocker: master venv editable-source path

The requested master workspace interpreter imports the package from the master workspace,
not the Stage 1A worktree. The exact requested pytest command therefore cannot see unmerged
Stage 1A modules.

Status: **resolved for sub-session testing** with `PYTHONPATH=src` while retaining the exact
same interpreter and dependency environment.

This should disappear naturally after Master integrates/cherry-picks Stage 1A into the
master workspace. No virtualenv, package install, or shared environment was modified.

No runtime/code blocker required modifying:

- `src/knowledge_engine/m26_aq_semantic_contract.py`
- `src/knowledge_engine/m26_public_api.py`
- `src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py`

## 8. Remaining risks

1. Stage 1A normalizes only signals already present at the adapter call site. It does not
   wire collection points into the runtime. That is intentional for zero behavior impact.
2. Evidence planning details such as retrieval round count/source count are not universally
   available from the four assigned legacy surfaces and remain
   `unavailable_in_stage1`.
3. Compute tier does not exist in the current M26 budget signal and remains
   `unavailable_in_stage1`; Stage 4 can layer shadow classification later.
4. Context compiler and verifier adapters deliberately expose only normalized metadata,
   not raw context/answer/evidence bodies. Stage 2 replay should compare these normalized
   fields rather than depending on hidden raw payloads.
5. Master must run the full Stage 1 A+B integration gate after integration; this
   sub-session intentionally did not run full 523, build Docker, or start/restart any
   runtime.

## 9. Suggested next step

Master should inspect this report and the five Stage 1A files, integrate Stage 1A together
with Stage 1B, then run the documented Stage 1 integration gate. If A+B are green, freeze
the contract shapes before issuing Stage 2 replay/equivalence work.

## 10. Confirmation production was untouched

**YES: production was untouched.**

This sub-session performed only:

- read-only source/document inspection over SSH,
- writes inside `/home/ubuntu/LLM_Wiki-m27-stage1-a`,
- compile/unit/lint tests against the worktree.

It did not restart or modify production, did not change nginx/Cloudflare/routes, did not
write R2/Qdrant/SQLite, did not use production write credentials, and did not perform
release promotion/rollback.

Read-only final production health check:

```text
llm_wiki-knowledge-engine-1|knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z|Up 3 hours (healthy)|127.0.0.1:8080->8080/tcp
```
