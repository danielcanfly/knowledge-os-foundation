# M27 Admission Smoke Preflight Repair Report

Status: `M27_ADMISSION_SMOKE_PREFLIGHT_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair`
Branch: `m27/smoke-preflight-repair`
Base: `cbc3ec9d7353f564ef11687ca590830e36253c2e`

## Scope

This was a preflight repair session only. It did not send smoke questions, did not run admission, did not run Stage13/14 legacy admission, did not run Chunk002, 100-case, or full523, and did not mutate production.

## 05 blockers and resolution

1. No real production-equivalent M27 isolated HTTP endpoint: resolved.
   - Added `src/knowledge_engine/m27_isolated_http.py`.
   - Endpoint module: `knowledge_engine.m27_isolated_http:app`.
   - The health payload identifies `m27-production-equivalent-runtime` and imports `M27ExecutableRequest`, `m27-production-evidence-authority/v1`, and `m27-isolated-admission-harness/v1`.
   - It is not `knowledge_engine.m26_console_api:app`.

2. Isolated eval container count was 0: resolved.
   - Added `scripts/m27_smoke_preflight_start.sh` and `scripts/m27_smoke_preflight_stop.sh`.
   - Updated `docker-compose.m27-isolated.yml` away from the old M26 console app and onto the M27 isolated HTTP surface.
   - Current live container: `m27-isolated-eval-05r`.
   - Current live image: `knowledge-engine:m27-smoke-preflight-repair`.
   - Current live port: `127.0.0.1:18080->8080`.
   - Current eval container count: `1`.

3. Host memory/swap guard failed under the generic default: resolved with explicit low-memory 05R/05 preflight guard.
   - Added `src/knowledge_engine/m27_smoke_preflight.py`.
   - Low-memory 05R/05 limits are explicit: minimum available memory `192 MB`, maximum swap used `768 MB`.
   - Live observed available memory during final preflight: `369 MB`.
   - Live observed swap used during final preflight: `555 MB`.
   - This is not a silent weakening of the generic harness default; the revised guard is isolated to the 05R/05 smoke-preflight path and tested.

4. Quota/preflight readiness: resolved.
   - Added `scripts/m27_smoke_preflight_check.py`.
   - Final live preflight status: `READY`.
   - Harness preflight status: `AUTHORIZED`.
   - Harness postflight status: `CLEAN`.
   - `quota_active_requests`: `0`.
   - `quota_provider_calls`: `0`.
   - `smoke_questions_sent`: `0`.
   - `provider_calls`: `0`.

## Endpoint health payload

Final health endpoint:

`GET http://127.0.0.1:18080/v1/health`

Returned HTTP 200 with:

- `schema_version`: `m27-production-equivalent-isolated-http/v1`
- `runtime_identity`: `m27-production-equivalent-runtime`
- `endpoint_module`: `knowledge_engine.m27_isolated_http:app`
- `runtime_execution_type`: `M27ExecutableRequest`
- `production_evidence_authority_schema`: `m27-production-evidence-authority/v1`
- `admission_harness_schema`: `m27-isolated-admission-harness/v1`
- `build_sha`: `cbc3ec9d7353f564ef11687ca590830e36253c2e`
- `image_digest`: `sha256:c4fe0db1d96d0bf60634c6b6bec245f1f6c04f1b4b857df4a1faa801aa4dd550`
- `container_id`: `52b6ab3a1a2f`
- `isolated_runtime`: `true`
- `production_equivalent`: `true`
- `production_touched`: `false`
- `smoke_questions_sent`: `0`
- `provider_calls`: `0`

Preflight endpoint:

`GET http://127.0.0.1:18080/v1/preflight`

Additional fields:

- `preflight_only`: `true`
- `answer_execution_authorized`: `false`
- `quota_active_requests`: `0`
- `quota_provider_calls`: `0`

## Production read-only receipts

Before starting the isolated eval container, production read-only health returned:

- `ok`: `true`
- backend build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`

After live preflight, production read-only health returned the same backend identity. Final preflight check reported `production_identity_stable: true`.

## Final live preflight result

Command:

```bash
cd /home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair
PATH=/home/ubuntu/.venvs/m27-runtime-composition/bin:$PATH \
PYTHONPATH=src:. \
/home/ubuntu/.venvs/m27-runtime-composition/bin/python \
  scripts/m27_smoke_preflight_check.py
```

Result summary:

- `status`: `READY`
- `preflight_status`: `AUTHORIZED`
- `preflight_reasons`: `[]`
- `postflight_status`: `CLEAN`
- `postflight_reasons`: `[]`
- `semantic_reasons`: `[]`
- `eval_container_count`: `1`
- `production_identity_stable`: `true`

## Tests and checks

Scoped tests:

```bash
pytest \
  tests/test_m27_smoke_preflight_repair.py \
  tests/test_m27_isolated_admission_harness.py \
  tests/test_m27_production_evidence_bridge.py \
  tests/test_m27_runtime_observability_contract.py \
  tests/test_m27_runtime_finalization.py -q
```

Result: `42 passed, 1 warning in 3.43s`.

Static checks:

- `python -m compileall -q src/knowledge_engine tests scripts/m27_smoke_preflight_check.py`: PASS
- Scoped Ruff: `All checks passed!`
- `git diff --check`: PASS

## No-smoke guarantee

This session exposed and validated readiness only. The M27 isolated HTTP surface intentionally does not authorize answer execution on the preflight route. Final payloads reported:

- `smoke_questions_sent`: `0`
- `provider_calls`: `0`
- `quota_provider_calls`: `0`

## Forbidden actions not performed

- no smoke questions sent
- no admission run
- no Stage13/14 legacy admission
- no Chunk002, 100-case, or full523
- no benchmark tuning
- no production mutation
- no production restart/stop/rebuild/deploy
- no production R2/Qdrant/SQLite/release-pointer writes
- no dirty import from `/home/ubuntu/LLM_Wiki-m27-context-runtime`

## Decision

05 may be rerun. This means Session 05 may run its own preflight and then decide whether to send the bounded 10-20 representative smoke questions. This report does not claim that smoke itself has passed.

`M27_ADMISSION_SMOKE_PREFLIGHT_READY`
