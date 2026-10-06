# Preflight Repair to Small Smoke Handoff

State: `M27_ADMISSION_SMOKE_PREFLIGHT_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair`
Branch: `m27/smoke-preflight-repair`
Base: `cbc3ec9d7353f564ef11687ca590830e36253c2e`

fresh_small_smoke_may_rerun: YES

## What is ready

A real loopback-only M27 production-equivalent isolated readiness surface is running at:

`http://127.0.0.1:18080`

Endpoint module:

`knowledge_engine.m27_isolated_http:app`

Current isolated eval container:

- name: `m27-isolated-eval-05r`
- image: `knowledge-engine:m27-smoke-preflight-repair`
- port: `127.0.0.1:18080->8080`
- label: `com.daniel.m27.eval=true`

This endpoint is not `knowledge_engine.m26_console_api:app` and does not use Stage13/14 legacy admission.

## Command 05 should use before sending questions

```bash
cd /home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair
PATH=/home/ubuntu/.venvs/m27-runtime-composition/bin:$PATH \
PYTHONPATH=src:. \
/home/ubuntu/.venvs/m27-runtime-composition/bin/python \
  scripts/m27_smoke_preflight_check.py
```

Only if that command returns `status: READY` should Session 05 proceed to its own bounded fresh small smoke questions.

## If container restart is required

Start or refresh only the owned isolated eval container:

```bash
cd /home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair
./scripts/m27_smoke_preflight_start.sh
```

Cleanup only the owned isolated eval container:

```bash
cd /home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair
./scripts/m27_smoke_preflight_stop.sh
```

The cleanup script refuses to remove production/test-page containers.

## Final validated preflight facts

- endpoint health: HTTP 200
- runtime identity: `m27-production-equivalent-runtime`
- build SHA: `cbc3ec9d7353f564ef11687ca590830e36253c2e`
- image digest: `sha256:c4fe0db1d96d0bf60634c6b6bec245f1f6c04f1b4b857df4a1faa801aa4dd550`
- container id: `52b6ab3a1a2f`
- eval container count: `1`
- low-memory host guard: PASS under explicit 05R/05 limits
- quota active requests: `0`
- quota provider calls: `0`
- smoke questions sent: `0`
- provider calls: `0`
- production identity stable: `true`

## Boundaries preserved

Production was not mutated, restarted, stopped, rebuilt, deployed, or written. No R2/Qdrant/SQLite/release pointer was touched. No smoke questions were sent. No admission, Stage13/14, Chunk002, 100-case, or full523 was run.

`M27_ADMISSION_SMOKE_PREFLIGHT_READY`
