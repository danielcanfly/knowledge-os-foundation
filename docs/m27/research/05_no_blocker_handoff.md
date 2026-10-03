# M27 Stage 1 No-Blocker Handoff

Status: Stage 1 adapter-only / decision-trace implementation is unblocked.

## Workspace

```text
/home/ubuntu/LLM_Wiki-m27-context-runtime
branch: m27/context-native-runtime-spec
```

## Production safety rules

Do not modify or restart current production. Do not change nginx/Cloudflare. Do not write production R2 pointers, Qdrant aliases/collections, QA SQLite, admin SQLite, or rate-limit SQLite. Do not copy production write credentials into M27.

## M27 isolated runtime

```text
compose: docker-compose.m27-isolated.yml
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
port: 127.0.0.1:18080
health: GET /v1/health -> 200 OK
```

Restart M27 isolated only:

```bash
cd /home/ubuntu/LLM_Wiki-m27-context-runtime
M27_RUNTIME_ENV_FILE=.env.m27 docker compose -f docker-compose.m27-isolated.yml up -d
```

## Allowed Stage 1 files

Prefer new files:

```text
src/knowledge_engine/m27_context_runtime_contracts.py
src/knowledge_engine/m27_legacy_m26_adapters.py
src/knowledge_engine/m27_decision_trace.py
src/knowledge_engine/m27_feature_flags.py
schemas/m27-*.schema.json
tests/test_m27_*.py
docs/m27/**/*.md
```

Existing files may be edited only for inert default-off wiring:

```text
src/knowledge_engine/m26_public_api.py
src/knowledge_engine/m26_console_api.py
src/knowledge_engine/m26_aq_semantic_contract.py
```

## Not allowed in Stage 1

No Jev, MCP exposure, Memory writes, Agent loop, Learning Plane, Meta-Harness, promote/rollback tools, production route changes, or production credential use.

## Feature flag

Use default-off flag:

```text
M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED=false
```

With flag off: behavior must be identical, no extra provider calls, no extra retrieval rounds, no answer output changes.

With flag on in M27 isolated runtime only: sanitized trace may include route, compute tier, deadline budget, provider budget, context sources, reason code, trace id. No raw query, raw answer, secrets, credentials, or full evidence text.

## Required tests

```bash
cd /home/ubuntu/LLM_Wiki-m27-context-runtime
python3 -m compileall -q src/knowledge_engine tests scripts
.venv/bin/python -m pytest -q \
  tests/test_m26_canonical_runtime_reachability.py \
  tests/test_m26_deadline_aware_semantic_routing.py \
  tests/test_m26_public_api.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_aq_surface_guard.py
curl -sS -i http://127.0.0.1:18080/v1/health | head -40
```

Expected current safe gate:

```text
49 passed, 1 warning
M27 /v1/health 200 OK
production remains healthy
```

## Rollback plan

Stop only M27 isolated lab:

```bash
docker compose -f docker-compose.m27-isolated.yml down
```

Code rollback:

```bash
git reset --hard <last-known-good-m27-commit>
```

## Acceptance criteria for Stage 1

- Contract interfaces exist.
- LegacyM26 adapters wrap current behavior.
- Default-off feature flag exists.
- Flag off safe gate remains green.
- Flag on emits/captures sanitized decision trace in M27 isolated runtime only.
- Production remains untouched and healthy.
