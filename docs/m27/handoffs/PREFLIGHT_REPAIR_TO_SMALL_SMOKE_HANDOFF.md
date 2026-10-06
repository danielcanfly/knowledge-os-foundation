# Preflight Repair to Small Smoke Handoff

State: `M27_ADMISSION_SMOKE_PREFLIGHT_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair`
Branch: `m27/smoke-preflight-repair`
Base: `cbc3ec9d7353f564ef11687ca590830e36253c2e`
Repair code HEAD: `aff6c16582a866d015140e0929c012a8ba6b0bed`

fresh_small_smoke_may_rerun: YES

## Exact 05 preflight startup command

`cd /home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair && ./scripts/m27_smoke_preflight_start.sh`

Then revalidate:

- `GET http://127.0.0.1:18080/v1/health`
- `GET http://127.0.0.1:18080/v1/preflight`
- exactly one container with label `com.daniel.m27.eval=true`
- build SHA/image digest/container ID match
- production `/v1/health` is HTTP 200 and identity stable
- low-memory profile passes: available >=192 MB, swap <=768 MB, load <=8.0
- quota active requests=0
- provider calls=0 before question 1
- no competing build/test/eval workload

Cleanup command:

`cd /home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair && ./scripts/m27_smoke_preflight_stop.sh`

The cleanup script is ownership-label guarded and must not remove production or test-page containers.

## Current live identity

- endpoint: `http://127.0.0.1:18080`
- module: `knowledge_engine.m27_isolated_http:app`
- runtime identity: `m27-production-equivalent-runtime`
- image: `knowledge-engine:m27-smoke-preflight-repair`
- image digest: `sha256:fd69ccb3814af30345bf99afcd70cbb011c764d8df02129b95dd7bbd306f0009`
- container: `m27-isolated-eval-05r`
- production touched: false
- smoke questions sent by 05R: 0
- provider calls by 05R: 0

05R does not authorize answer execution itself. 05 must rerun its own preflight and only then decide whether to send its bounded 10-20 questions.
