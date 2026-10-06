# M27 Fresh Small Admission Smoke Report

Status: `M27_SMALL_SMOKE_BLOCKED`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-fresh-small-smoke`
Branch: `m27/fresh-small-smoke`
Authorized base HEAD: `cbc3ec9d7353f564ef11687ca590830e36253c2e`

## Mission result

The fresh small admission smoke sent zero admission questions. Session 05 requires every live preflight gate to pass before the first question. Multiple independent gates failed, so this session stopped fail-closed as required.

## Upstream and exclusivity

- Upstream state `M27_PRODUCTION_EQUIV_RUNTIME_READY` confirmed.
- New worktree created from approved Session 04 HEAD `cbc3ec9d7353f564ef11687ca590830e36253c2e`.
- No concurrent docker build, pytest, endpoint evaluation, or M27 eval workload was observed at preflight.
- Production and test-page containers were left untouched.

## Read-only production observation

`GET http://127.0.0.1:8080/v1/health` returned HTTP 200 with backend build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd`, entrypoint `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`, and answer bundle preloaded=true.

No production mutation was performed.

## Blocking preflight evidence

### No valid isolated M27 endpoint

The repo historical `docker-compose.m27-isolated.yml` maps `127.0.0.1:18080:8080` but launches `knowledge_engine.m26_console_api:app`, not the Session 04 production-equivalent M27 executable runtime.

A read-only probe to `http://127.0.0.1:18080/v1/health` failed with connection refused and `HTTP_STATUS=000`.

Observed active isolated eval containers: `0`; required: exactly `1`.

### Host resource guards

Observed available memory: `434 MB`; harness minimum: `1024 MB`. This fails `HOST_MEMORY_GUARD_TRIPPED`.

Observed swap used: `514 MB`; harness maximum: `256 MB`. This fails `HOST_SWAP_GUARD_TRIPPED`.

The only running containers were production `llm_wiki-knowledge-engine-1` on loopback 8080 and test page `knowledge-engine-test-answers` on loopback 8081. No Session 05 isolated eval container existed.

## Why no isolated container was started

The resource guard had already failed. Starting another container after that failure would violate the Session 04 handoff. This session therefore did not change compose/runtime code, tune the host, restart production, or import Stage13/14 admission machinery.

## Smoke execution

- representative questions sent: 0
- admission requests sent: 0
- provider calls attributable to smoke: 0
- Stage13/14 legacy admission: not run
- Chunk002: not run
- 100-case: not run
- full523: not run

Citation correctness, answer quality, abstention correctness, p50/p95, and first-answer-text streaming were not scored because no case was authorized.

## Integrity verification

Targeted Session 04 suite result: `32 passed in 3.03s`.
`git diff --check`: PASS.

## M26 baseline invariant

No M27 smoke request was sent and no production feature/runtime behavior was changed. Production remained on its existing M26 backend.

## Forbidden-action audit

No production mutation/restart/stop/rebuild/deploy; no production R2/Qdrant/SQLite/release-pointer writes; no Stage13/14 legacy admission; no Chunk002/100-case/full523; no failed-case tuning; no runtime repair; no dirty import from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.

## Required next action

Before retrying Session 05, a separately authorized preparation/repair session must expose a clean isolated HTTP surface that actually executes the Session 04 production-equivalent M27 runtime, pin build/image/container identity, restore host resources inside the existing guard, provide exactly one isolated eval container, and prove clean quota lifecycle state plus production-evidence authority binding.

This prompt does not authorize those repairs.

`M27_SMALL_SMOKE_BLOCKED`
