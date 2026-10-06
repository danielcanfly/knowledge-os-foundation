# M27 Runtime Composition Master Report

Status: `M27_RUNTIME_COMPOSITION_COMPLETE`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-runtime-composition`
Branch: `m27/runtime-composition`
Base: `06681024634b2590ce6115498a5c87ed887b9aea`

## Finalization correction (2026-10-06)

The initial upstream `M27_RUNTIME_COMPOSITION_COMPLETE` claim was premature: the original harness normalized caller-supplied compiler and verifier outputs and only calculated a continuation recommendation. It did not run the M26 answer/model seam or execute a verifier-driven second round. The new, independently audited finalization in `m27/runtime-composition-finalization` adds actual executable isolated composition, 13 acceptance guards, M26 compiler and verifier calls, budget-enforced repeated execution and an explicit fresh-smoke readiness decision. See `docs/m27/research/43_runtime_composition_finalization_report.md` and the updated handoff.

The original 28-test receipt remains valid **for the upstream normalization-only composition mode**, not proof of end-to-end execution. The current isolated synthetic proof and 554-test safety gate supersede the upstream completion interpretation. It does **not** establish production-compiler authority; admission readiness is NO.

## Scope receipt

This session executed only the runtime-composition subsession scope. It did not run or modify Stage13/14 admission mainline, did not start Chunk002, did not run full523, did not restart production, did not stop production, and did not change production configuration.

The worktree started clean on the requested base:

- Branch: `m27/runtime-composition`
- Starting HEAD: `06681024634b2590ce6115498a5c87ed887b9aea`
- Starting subject: `docs(m27): complete stage12 master integration gate`

## Commits created

1. `abc55175 docs(m27): inventory runtime composition primitives`
2. `cfb33527 feat(m27): compose isolated runtime primitives`

A final documentation/handoff commit follows this report.

## Inventory delivered

Artifact: `docs/m27/research/runtime_composition_inventory.md`

Inventory conclusion: Stage1-12 primitives were present but mostly independent. The missing production-independent layer was an isolated runtime harness that composes the primitives in one executable flow without granting new authority.

The inventory maps:

- Stage1 contracts and legacy adapters
- Stage1 decision trace
- Stage2 replay/equivalence
- Stage3 evidence boundary
- Stage4 compute policy
- Stage5 read-only tool registry and provider views
- Stage6 bounded retrieval as a bounded continuation reference
- Stage7 descriptor-only ops skills
- Stage8 isolated workspace
- Stage9 MCP descriptor exposure
- Stage10 candidate-only memory
- Stage11 proposal-only learning
- Stage12 offline meta-harness candidates

## Implementation delivered

### `src/knowledge_engine/m27_tool_executor.py`

Adds the Stage5 execution boundary that was missing behind the descriptor-only tool registry.

Properties:

- Requires injected providers.
- Requires deterministic authorization token and explicit capability allow-list.
- Allows only registered Stage5 read-only descriptors.
- Blocks mutation, raw infrastructure exposure, network-capable descriptors, and authorization bypass.
- Emits sanitized `ToolExecutionRecord` metadata only.
- Supports the existing read-only capability surface:
  - `knowledge.search`
  - `knowledge.expand`
  - `evidence.inspect`
  - `evidence.verify`
  - `runtime.get_trace`
  - `runtime.get_budget`
  - `runtime.get_health`

### `src/knowledge_engine/m27_context_orchestrator.py`

Adds deterministic task-level composition planning.

Properties:

- `NO_CONTEXT` selects no unnecessary context resources.
- `KNOWLEDGE` selects Knowledge and `knowledge.search` only.
- `TOOL` selects the explicitly requested read-only tool capability only.
- `OPS` selects a descriptor-only Stage7 skill and uses its read-only required capabilities.
- Memory candidate context is selected only by explicit policy.
- Verifier gaps may receive at most bounded continuation according to max rounds, tool budget, deadline budget, and provider-attempt budget.

### `src/knowledge_engine/m27_runtime_harness.py`

Adds the first executable composition harness across Stage1-12 primitives.

Properties:

- Feature-off mode returns `M26_BASELINE_UNCHANGED` without workspace, trace, tool, memory, learning, or meta-harness work.
- Feature-on mode creates an isolated Stage8 workspace.
- Existing M26 routing, budget, compiler, verifier, and evidence signals are normalized through existing Stage1/3 adapters.
- Stage4 compute policy remains observational and bounded.
- Stage5 tools execute only through the read-only executor and injected providers.
- Stage7 ops skills remain descriptor-only and do not receive execution authority.
- Stage10 memory remains candidate-only and non-authoritative.
- Stage11 learning remains proposal-only.
- Stage12 meta-harness remains offline/review-only.
- No production write, release, rollback, R2, Qdrant, SQLite, shell, or MCP exposure authority is introduced.

Important boundary fix: Stage10/11/12 optional candidate runtimes are loaded through delayed composition helpers, so existing Stage10/11/12 guard tests still prove they are not statically wired into earlier M27 runtime modules.

## Tests added

### `tests/test_m27_tool_executor.py`

Covers:

- Authorized read-only execution.
- Unauthorized capability block.
- Authorization-token mismatch block.
- Missing provider fail-closed behavior.
- Evidence/runtime provider view invocation.

### `tests/test_m27_context_orchestrator.py`

Covers:

- No-context resource minimization.
- Knowledge source selection.
- Explicit tool source selection.
- Descriptor-only ops skill selection.
- Explicit-only memory candidate selection.
- Bounded verifier continuation.
- Round budget and provider budget blocks.

### `tests/test_m27_runtime_composition_eval.py`

Covers the required 15 synthetic architecture cases:

1. No-context task chooses no unnecessary resources.
2. Knowledge task selects Knowledge and invokes search.
3. Tool task invokes only requested read-only tool.
4. Ops task selects a descriptor-only skill and read-only skill capabilities.
5. Workspace is isolated per task.
6. Memory candidate is explicit and non-authoritative.
7. Verifier gap gets at most one bounded continuation.
8. Budget exhaustion blocks continuation.
9. Unauthorized tool capability fails closed.
10. Mutation-style tool is not executable.
11. Trace summary does not store raw query, answer, or evidence body.
12. Learning candidate is proposal-only.
13. Meta-harness candidate is review-only.
14. Feature-off mode leaves M26 baseline unchanged.
15. Runtime composition does not expose production authority.

## Gate results

### New composition gate

Command:

```bash
PYTHONPATH=src /home/ubuntu/.venvs/m27-runtime-composition/bin/python -m pytest -q \
  tests/test_m27_tool_executor.py \
  tests/test_m27_context_orchestrator.py \
  tests/test_m27_runtime_composition_eval.py
```

Result:

```text
28 passed in 1.13s
```

### Lint and compile gate

Command:

```bash
/home/ubuntu/.venvs/m27-runtime-composition/bin/ruff check \
  src/knowledge_engine/m27_tool_executor.py \
  src/knowledge_engine/m27_context_orchestrator.py \
  src/knowledge_engine/m27_runtime_harness.py \
  tests/test_m27_tool_executor.py \
  tests/test_m27_context_orchestrator.py \
  tests/test_m27_runtime_composition_eval.py

/home/ubuntu/.venvs/m27-runtime-composition/bin/python -m compileall -q src/knowledge_engine tests
```

Result:

```text
All checks passed!
compileall PASS
```

### Stage1-12 plus M26 safety gate

Command:

```bash
PYTHONPATH=src /home/ubuntu/.venvs/m27-runtime-composition/bin/python -m pytest -q \
  tests/test_m26_aq_surface_guard.py \
  tests/test_m26_canonical_runtime_reachability.py \
  tests/test_m26_deadline_aware_semantic_routing.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_public_api.py \
  tests/test_m27_*.py
```

Result:

```text
541 passed, 1 warning in 12.96s
```

Warning only:

- `StarletteDeprecationWarning` from FastAPI testclient/httpx package wiring.

No M26 baseline regression, no M27 Stage1-12 regression, and no composition regression were observed.

## Production proof

Read-only checks only. No production restart, stop, deploy, or config mutation was performed.

Docker process:

```text
llm_wiki-knowledge-engine-1|knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z|Up 43 hours (healthy)|127.0.0.1:8080->8080/tcp
```

Production health:

```text
HTTP/1.1 200 OK
status: ok
answer_bundle_preloaded: true
answer_bundle_preload_error: ""
```

No isolated endpoint was started by this session. `127.0.0.1:18080` was not listening, which is expected for this scope.

## Post-Stage12 commit classification

The runtime-composition branch was intentionally based at Stage12 and did not cherry-pick or depend on the later Stage13/14 admission chain.

Observed commits in `06681024..3592b22b` were classified as out-of-scope for this subsession:

- `c8f8f678` / `6e147d23`: Stage13 admission integration/evaluation.
- `8b567264`, `34f7b808`, `8799d774`, `649908f2`: Stage14 admission repair and provider/endpoint proofs.
- `8dfeb516`, `5889fcbd`, `ab597e2a`: Stage13 smoke blocker/retry reports.
- `a946933f`, `bac017cd`, `fe8ed9b5`, `6db19db8`: Stage13 quota lease repair/proof.
- `09aa3a1e`, `3d1dcae0`: Stage13R2 smoke retry integration/proof.
- `3592b22b`: single-VM production stability guard.

These were read only for classification and were not imported into this composition work.

## Final assessment

`M27_RUNTIME_COMPOSITION_COMPLETE`

M27 now has a minimal executable runtime composition layer that can run an isolated task through planning, read-only tools, workspace state, sanitized trace, bounded continuation decision, candidate-only memory, proposal-only learning, and review-only meta-harness output while preserving M26 baseline behavior when disabled.
