# 05｜Stage 0C Source Reconciliation Handoff

This is intentionally **not** `05_no_blocker_handoff.md`.

Stage 0B found unresolved source-of-truth blockers. The next session must complete Stage 0C before any M27 runtime implementation.

## Objective

Create a clean M27 source base that matches the current production image source truth, without changing production behavior.

## Current facts

```text
production image:
knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z

freeze tag:
knowledge-engine:m26-production-freeze-generic-fallback-guard-20261003T063245Z

production entrypoint:
uvicorn knowledge_engine.m26_console_api:app --host 0.0.0.0 --port 8080

M27 workspace:
/home/ubuntu/LLM_Wiki-m27-context-runtime
branch: m27/context-native-runtime-spec
HEAD: e5aeee42

production-matching source evidence:
/home/ubuntu/LLM_Wiki-f746-quality-gate-20260930
```

The dirty worktree source matches production image Python files exactly, but it is dirty/untracked and must not become the development base as-is.

## Stage 0C required work

1. Create a clean reconciliation plan.
2. Copy/import production-only modules and production-different modules into M27 source branch, or create a new clean branch from production image source.
3. Preserve docs/m27 prework.
4. Do not modify production container.
5. Do not alter runtime behavior.
6. Commit only source reconciliation and tests explicitly needed to make M27 branch equal production source plus M27 docs.

## Files missing from M27 clean branch but present in production

```text
src/knowledge_engine/m26_active_production_release.py
src/knowledge_engine/m26_active_release_dense.py
src/knowledge_engine/m26_admin_audit.py
src/knowledge_engine/m26_admin_auth.py
src/knowledge_engine/m26_admin_contract.py
src/knowledge_engine/m26_admin_control_plane.py
src/knowledge_engine/m26_admin_corpus.py
src/knowledge_engine/m26_admin_health.py
src/knowledge_engine/m26_admin_ingestion.py
src/knowledge_engine/m26_admin_ingestion_core.py
src/knowledge_engine/m26_admin_ingestion_sync.py
src/knowledge_engine/m26_admin_overview.py
src/knowledge_engine/m26_admin_production.py
src/knowledge_engine/m26_admin_qa.py
src/knowledge_engine/m26_admin_settings.py
src/knowledge_engine/m26_admin_usage.py
src/knowledge_engine/m26_console_api.py
src/knowledge_engine/m26_console_health_runtime.py
src/knowledge_engine/m26_console_p05_ask_playground.py
src/knowledge_engine/m26_daily_ip_rate_limit.py
src/knowledge_engine/m26_golden_production_provider.py
src/knowledge_engine/m26_golden_questions_admin.py
src/knowledge_engine/m26_ingestion_candidate_qdrant.py
src/knowledge_engine/m26_ingestion_candidate_writer.py
src/knowledge_engine/m26_ingestion_finalization.py
src/knowledge_engine/m26_ingestion_health_read.py
src/knowledge_engine/m26_ingestion_operator_health.py
src/knowledge_engine/m26_ingestion_qdrant_qualification.py
src/knowledge_engine/m26_ingestion_read_runtime.py
src/knowledge_engine/m26_ingestion_runtime.py
src/knowledge_engine/m26_jobs_rollback_api.py
src/knowledge_engine/m26_production_promotion.py
src/knowledge_engine/m26_qa_inbox_integration.py
src/knowledge_engine/m26_runtime_read_cache.py
src/knowledge_engine/m26_runtime_read_worker.py
src/knowledge_engine/m26_sqlite_ingestion.py
src/knowledge_engine/m26_suggested_questions_admin.py
```

## Files present but different from production

```text
src/knowledge_engine/m26_aq_semantic_contract.py
src/knowledge_engine/m26_ask_api.py
src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py
src/knowledge_engine/m26_pa7_semantic_closure_runtime.py
src/knowledge_engine/m26_production_answer_bundle.py
src/knowledge_engine/m26_public_api.py
```

These are high-risk because they include answer path, public API, bundle binding, and fallback/QA changes.

## Mandatory production invariants to preserve

```text
INV-001 production entrypoint remains console API unless intentionally changed later.
INV-002 public answer path still uses existing admission/origin/quota/provider guards.
INV-003 generic extractive evidence fallback cannot be user-facing.
INV-004 material answer text is emitted only in terminal verified public SSE event.
INV-005 existing verified answer/citation gates remain authoritative.
INV-006 QA inbox capture does not collect raw sensitive material outside existing policy.
INV-007 admin/release/ingestion/write surfaces remain behind existing deterministic capability gates.
INV-008 no M27 tool/agent can bypass ACL, release CAS, audit, rollback, or idempotency checks.
```

## Validation commands after source reconciliation

Run from clean M27 workspace after applying source reconciliation:

```bash
git status --short
python3 -m compileall -q src/knowledge_engine
python3 - <<PY
import importlib.util
for mod in [
    knowledge_engine.m26_console_api,
    knowledge_engine.m26_public_api,
    knowledge_engine.m26_aq_semantic_contract,
    knowledge_engine.m26_qa_inbox_integration,
    knowledge_engine.m26_admin_control_plane,
]:
    spec = importlib.util.find_spec(mod)
    assert spec, mod
    print(mod, spec.origin)
PY
```

Then run the existing production regression commands identified by the controlling session. At minimum, include public API tests and the bad-template / quality gates before any M27 Stage 1 code.

## Stage 0C completion criteria

```text
1. M27 branch contains production entrypoint source.
2. M27 branch contains production-only admin/QA/ingestion/release modules or explicitly excludes them with a documented replacement branch strategy.
3. The six differing M26 files are reconciled to production source or intentionally diffed with reason.
4. Generic fallback guard is present in reconciled source.
5. Production image and M27 source delta is known and documented.
6. No production container/release behavior was modified.
7. New commit contains source reconciliation and docs only, no M27 behavior implementation.
```

## Recommended next step after Stage 0C

Only after Stage 0C is clean:

```text
M27 Stage 1A:
Add adapter-only ContextPlan / ComputeDecision normalization around existing M26 route/budget logic.
Feature flags default off.
Trace only.
No answer output change.
```
