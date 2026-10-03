# M27 Stage 0D Blocker Closeout Report

## Summary

Stage 0D converts previous environment blockers into verified gates. Stage 1 adapter-only implementation is now unblocked.

## M27 isolated runtime

```text
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
port: 127.0.0.1:18080 -> 8080
health: healthy
```

Health evidence:

```text
GET /v1/health -> 200 OK
schema_version = danielcanfly-answers-health/v1
status = ok
preload.answer_bundle_preloaded = false
```

The private `.env.m27` file is git-ignored and contains only non-production local readiness values: dummy M27-only HMAC, isolated quota DB, bundle preload disabled.

## Production isolation evidence

```text
production container: llm_wiki-knowledge-engine-1
production image: knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z
production status: healthy
production port: 127.0.0.1:8080 -> 8080
```

No production restart, route change, pointer write, DB migration, or production credential copy was performed.

## Test runner

A local `.venv` exists inside the M27 workspace. Pytest version:

```text
pytest 8.4.2
```

Safe Stage 1 gate:

```text
49 passed, 1 warning
```

## Test-only adjustments

- `tests/test_m26_pa_7_arbitrary_query_runtime.py` now patches both the legacy PA7 facade and canonical semantic runtime loader for synthetic bundle loading.
- `tests/m26_answer_bundle_fixture.py` aligns synthetic manifest `semantic_documents` with `FULL_PRODUCTION_NODE_COUNT`.

No runtime code was loosened to pass tests.

## Deferred legacy suite

The full `tests/test_m26_pa_7_arbitrary_query_runtime.py` still has expectation drift under reconciled production source. This is deferred outside Stage 1 because Stage 1 does not change retrieval/answer behavior.
