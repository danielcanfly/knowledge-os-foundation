# M27 Stage 0C Source Reconciliation Report

## Status

Stage 0C source reconciliation completed for `src/knowledge_engine` in the M27 workspace.

Workspace:

```text
/home/ubuntu/LLM_Wiki-m27-context-runtime
```

Branch:

```text
m27/context-native-runtime-spec
```

Production image used as source-of-truth reference:

```text
knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z
```

Production-equivalent source tree used for reconciliation:

```text
/home/ubuntu/LLM_Wiki-f746-quality-gate-20260930
```

This dirty worktree was verified before reconciliation to match the running production image Python package source:

```text
production image Python files: 382
production image vs dirty worktree: 382 / 382 match
```

## Reconciliation result

After copying the production-equivalent `src/knowledge_engine` package into the M27 branch:

```text
prod_py 382
missing 0 []
diff 0 []
extra 0 []
```

So the M27 branch now has a Python package source tree equivalent to the running production image.

## Previously missing production modules now present

The M27 branch now includes the production-only Console/Admin/Ingestion/QA/Promotion surface that was missing from the clean f746 base, including:

```text
m26_console_api.py
m26_admin_*.py
m26_ingestion_*.py
m26_qa_inbox_integration.py
m26_production_promotion.py
m26_jobs_rollback_api.py
m26_daily_ip_rate_limit.py
qa_answer_quality*.py
suggested_questions*.py
```

## Previously divergent answer-path files reconciled

The following files now match the running production image:

```text
m26_aq_semantic_contract.py
m26_ask_api.py
m26_pa7_arbitrary_query_runtime.py
m26_pa7_semantic_closure_runtime.py
m26_production_answer_bundle.py
m26_public_api.py
```

## Generic fallback guard

The production guard is present in the M27 branch:

```text
# Guard: do not emit generic extractive evidence fallback as user-facing answer.
return None
```

Location:

```text
src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py
```

## Local compile gate

The following compile gate passed:

```text
python3 -m compileall -q src/knowledge_engine scripts/m26_suggested_questions_quality_gate.py tests/test_m26_canonical_runtime_reachability.py tests/test_m26_deadline_aware_semantic_routing.py tests/test_m26_pa_7_arbitrary_query_runtime.py tests/test_m26_public_api.py
```

Result:

```text
PY_COMPILE_OK
```

## Quality gate script smoke

The current M26 suggested-questions quality gate script was copied into M27 and its CLI help imports successfully:

```text
python3 scripts/m26_suggested_questions_quality_gate.py --help
```

## Test runner limitation

Host-level pytest could not be executed because `pytest` is not installed on the VM host:

```text
bash: pytest: command not found
```

This is not a production blocker, but it is a Stage 0D/0E test-environment blocker. Resolve by running tests inside a dev image or installing dev dependencies in an isolated venv, not on production.

## Production safety result

Current production remained untouched and healthy during reconciliation:

```text
llm_wiki-knowledge-engine-1|knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z|healthy|127.0.0.1:8080->8080/tcp
```

No production restart, route change, nginx change, R2 pointer change, Qdrant alias change, or production DB mutation was performed.
