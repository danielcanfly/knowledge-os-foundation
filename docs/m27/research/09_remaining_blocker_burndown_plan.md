# M27 Remaining Blocker Burn-down Plan

## Cleared blockers

| ID | Previous category | Resolution |
|---|---|---|
| B001 | SOURCE_MISMATCH | M27 `src/knowledge_engine` now matches production image 382/382 Python files. |
| B002 | PRODUCTION_ENTRYPOINT_MISSING | `m26_console_api.py` now exists in M27 source. |
| B003 | DIRTY_WORKTREE_SOURCE_OF_TRUTH | Dirty worktree verified as exact source match to production image; M27 branch reconciled from it. |
| B004 | GENERIC_FALLBACK_GUARD_MISSING | Guard present in reconciled M27 source. |
| B009 | QA_EVAL_MODULES_MISSING | QA modules copied into M27 source. |
| B010 | PROMOTION_ROLLBACK_MODULES_MISSING | Production promotion/rollback modules copied into M27 source. |

## Remaining blockers before behavior-changing M27 work

| ID | Category | Description | Status | Required mitigation |
|---|---|---|---|---|
| B011 | TEST_ENV_GAP | Host VM lacks pytest, so selected pytest suites were not run. | Open | Use isolated dev image/venv with dev deps; do not mutate production. |
| B012 | ISOLATED_READINESS_CONFIG | M27 isolated container starts but returns `SERVICE_NOT_READY` because staging config is absent. | Open | Create non-production/read-only M27 env or fixture-backed readiness config. |
| B013 | BEHAVIOR_EQUIVALENCE_GAP | M27 image has not yet proven same answer behavior as M26 production on selected suites. | Open | Run equivalence tests against isolated M27 once readiness config exists. |
| B014 | DOCKERFILE_ENTRYPOINT_DRIFT | Dockerfile CMD is `m26_production_api`, while production container and isolated compose use `m26_console_api`. | Accepted with mitigation | Keep Dockerfile unchanged for now; isolated compose overrides command. Decide later whether to update Dockerfile after source/equivalence gates. |
| B015 | NO_PRODUCTION_CREDENTIAL_RULE | M27 must not use production write credentials. | Active rule | Any env used for M27 must be read-only, cloned, fixture-backed, or explicitly approved. |

## Next safe step

Next session should do **Stage 0D/0E test environment completion**, not M27 feature implementation.

1. Build a dev/test image with pytest or create isolated venv.
2. Create a non-production M27 env/read-only fixture configuration.
3. Run selected tests:

```text
tests/test_m26_canonical_runtime_reachability.py
tests/test_m26_deadline_aware_semantic_routing.py
tests/test_m26_pa_7_arbitrary_query_runtime.py
tests/test_m26_public_api.py
```

4. Run bad-template/quality gate selfcheck.
5. Run isolated health and behavior-equivalence smoke.
6. Only after these pass, begin adapter-only contract extraction.

## Not allowed yet

```text
new planner implementation
new agent loop
Jev provider
MCP adapter
memory runtime
learning plane
meta-harness optimizer
production route changes
production credential use
production DB/R2/Qdrant writes
```
