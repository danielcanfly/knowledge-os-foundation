# M27 Stage 7 + Stage 8 Master Integration Report

## Result

```text
STAGE7_STAGE8_MASTER_INTEGRATION: PASS
PRODUCTION_ENABLEMENT: NOT_APPLICABLE
NEXT_STAGE_ALLOWED: STAGE9_MCP_EXPOSURE_ONLY
```

## Master state

```text
branch: m27/context-native-runtime-spec
base before integration: bbb29ed7
stage7 source commit: 60ba735d
stage8 source commit: 8117b16f
master cherry-pick commits:
  f6484970 feat(m27): add stage7 ops skills runtime
  bcb48052 feat(m27): add stage8 isolated workspace boundary
```

## Stage 7 scope integrated

Stage 7 added an ops-only skill runtime boundary:

```text
src/knowledge_engine/m27_skill_contracts.py
tests/test_m27_skill_contracts.py
docs/m27/research/stage7_ops_skills_runtime_report.md
```

The Stage 7 runtime is descriptor/plan only. It intentionally has no tool execution surface, no runner, no persistence, no MCP exposure, no memory runtime, and no production write authority.

Registered Stage 7 skills:

```text
investigate-answer-failure
investigate-retrieval-failure
diagnose-latency
run-quality-gate
```

Deferred Stage 7 skills:

```text
answer-from-knowledge
deep-research
ingest-and-update-knowledge
promote-knowledge-release
```

## Stage 8 scope integrated

Stage 8 added an isolated workspace boundary:

```text
src/knowledge_engine/m27_workspace_contracts.py
src/knowledge_engine/m27_workspace_store.py
tests/test_m27_workspace_contracts.py
tests/test_m27_workspace_store.py
docs/m27/research/stage8_isolated_workspace_report.md
```

The Stage 8 workspace is an injected-root, isolated filesystem store for sanitized task state, artifacts, checkpoints, reports, and candidates only. It does not wire into the answer path, skill execution, MCP, memory, production storage, release promotion, R2, Qdrant, or production sqlite.

Allowed artifact kinds:

```text
REPORT
EVAL_SUMMARY
CANDIDATE_PATCH
CHECKPOINT
HANDOFF
DIAGNOSTIC
```

Blocked artifact kinds:

```text
PRODUCTION_RELEASE
R2_OBJECT
QDRANT_COLLECTION
SQLITE_DB
SECRET
ENV_DUMP
RAW_EVIDENCE
RAW_ANSWER
RAW_QUERY
```

## Boundary checks

```text
production writes added: NO
R2 writes added: NO
Qdrant writes added: NO
production sqlite writes added: NO
release promote/rollback added: NO
MCP exposure added: NO
Memory runtime added: NO
Skill execution authority added: NO
answer path behavior changed: NO
public runtime behavior changed: NO
Stage 7 depends on Stage 8: NO
Stage 8 depends on Stage 7: NO
```

Stage 7 remains procedure/plan only. Stage 8 remains isolated state/artifact boundary only. They are intentionally not connected in this integration.

## Gate commands

```bash
python3 -m compileall -q src/knowledge_engine tests

env -u M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED -u M27_ISOLATED_RUNTIME PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_m26_canonical_runtime_reachability.py \
  tests/test_m26_deadline_aware_semantic_routing.py \
  tests/test_m26_public_api.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_aq_surface_guard.py \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py \
  tests/test_m27_decision_trace.py \
  tests/test_m27_replay_harness.py \
  tests/test_m27_equivalence_report.py \
  tests/test_m27_evidence_planner.py \
  tests/test_m27_context_evidence_boundary.py \
  tests/test_m27_compute_policy.py \
  tests/test_m27_compute_policy_shadow.py \
  tests/test_m27_tool_contracts.py \
  tests/test_m27_tool_registry.py \
  tests/test_m27_readonly_tools.py \
  tests/test_m27_bounded_agentic_retrieval.py \
  tests/test_m27_bounded_agentic_retrieval_runtime.py \
  tests/test_m27_bounded_agentic_retrieval_wiring.py \
  tests/test_m27_skill_contracts.py \
  tests/test_m27_workspace_contracts.py \
  tests/test_m27_workspace_store.py

.venv/bin/ruff check src/knowledge_engine/m27_*.py tests/test_m27_*.py
.venv/bin/ruff check src/knowledge_engine/m26_aq_semantic_contract.py --ignore F841
```

## Gate results

```text
compileall: PASS
pytest: 233 passed, 1 warning in 10.60s
ruff M27: PASS
ruff patched M26 file with known pre-existing F841 ignored: PASS
```

The warning is the pre-existing Starlette/httpx deprecation warning in the FastAPI test client path.

## Production status

No production deployment, docker image rebuild, container restart, R2 pointer update, Qdrant alias update, or production sqlite mutation was performed during Stage 7/8 integration.

## Remaining risks

```text
Stage 7 plans do not execute tools; a later runner must preserve policy and authorization boundaries.
Stage 8 syntactic sanitization cannot prove arbitrary prose is semantically non-sensitive.
Stage 8 is designed for isolated single-task/single-writer use; cross-process transaction locking is intentionally out of scope.
Stage 7 and Stage 8 are not connected yet; future integration must remain policy-gated.
```

## Recommendation

```text
READY_FOR_STAGE9_MCP_EXPOSURE_PREVIEW
```

Stage 9 may expose selected already-stable read-only native capabilities through MCP, but must remain default-off, read-only, policy-gated, and independent of production behavior.
