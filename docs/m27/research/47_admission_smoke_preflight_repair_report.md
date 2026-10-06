# M27 Admission Smoke Preflight Repair Report

Status: `M27_ADMISSION_SMOKE_PREFLIGHT_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair`
Branch: `m27/smoke-preflight-repair`
Base: `cbc3ec9d7353f564ef11687ca590830e36253c2e`
Repair code HEAD: `aff6c16582a866d015140e0929c012a8ba6b0bed`

## 1. 05 blockers and resolution

05 failed before question 1 with four live blockers.

1. No real isolated M27 endpoint. Resolved with `knowledge_engine.m27_isolated_http:app`, loopback-only on `127.0.0.1:18080`.
2. Host memory guard was impossible at the previous 1024 MB threshold on a 954 MB VM. Resolved with an explicit 05R/05 low-memory profile: minimum available memory 192 MB, based on the measured isolated endpoint footprint under a 256 MB container cap.
3. Swap exceeded the previous 256 MB limit. Resolved with an explicit low-memory ceiling of 768 MB. Live READY observation used 555 MB.
4. Isolated eval container count was 0. Resolved with an owned container lifecycle named `m27-isolated-eval-05r`, label `com.daniel.m27.eval=true`, and exactly-one detection.

The low-memory values are explicit constants and tests, not a silent weakening of the default harness.

## 2. Endpoint

Endpoint module:

`knowledge_engine.m27_isolated_http:app`

URL:

`http://127.0.0.1:18080`

Health:

`GET /v1/health`

Preflight:

`GET /v1/preflight`

Health identity fields include:

- schema: `m27-production-equivalent-isolated-http/v1`
- runtime identity: `m27-production-equivalent-runtime`
- runtime execution type: `M27ExecutableRequest`
- production evidence authority schema: `m27-production-evidence-authority/v1`
- admission harness schema: `m27-isolated-admission-harness/v1`
- build SHA
- image digest
- container ID
- isolated runtime=true
- production equivalent=true
- production touched=false
- smoke questions sent=0
- provider calls=0

This is not `m26_console_api` and does not use Stage13/14.

The endpoint is deliberately preflight-only in 05R. It binds the 04 executable runtime contracts and evidence authority identity but does not authorize answer execution during this repair session.

## 3. Container identity

Container name:

`m27-isolated-eval-05r`

Image:

`knowledge-engine:m27-smoke-preflight-repair`

Loopback mapping:

`127.0.0.1:18080 -> 8080`

Repair-code build SHA:

`aff6c16582a866d015140e0929c012a8ba6b0bed`

Deterministic image digest:

`sha256:fd69ccb3814af30345bf99afcd70cbb011c764d8df02129b95dd7bbd306f0009`

Observed container ID:

`8621e8db2853`

Exactly-one eval container count: `1`.

Production and test-page containers are excluded by name/label policy.

## 4. Lifecycle safety

Startup script:

`scripts/m27_smoke_preflight_start.sh`

Cleanup script:

`scripts/m27_smoke_preflight_stop.sh`

Startup fails closed if port 18080 is already occupied or an existing same-name container is not owned by the M27 eval label.

Cleanup removes only `m27-isolated-eval-05r` when the ownership label is present. Cleanup was exercised live. Production and test-page remained running and production identity remained stable.

## 5. Host resource decision

VM total memory is about 954 MB, so the prior 1024 MB available-memory guard can never pass on this host.

05R adds an explicit low-memory profile:

- minimum available memory: 192 MB
- maximum swap used: 768 MB
- maximum load 1m: 8.0
- container memory cap: 256 MB
- container memory+swap cap: 768 MB

Final live preflight observation:

- available memory: 389 MB
- swap used: 555 MB
- load 1m: 1.19
- active eval containers: 1
- active build/test/eval workloads: 0

Result: PASS.

No production or test-page service was stopped to manufacture free memory.

## 6. Quota/preflight

`/v1/preflight` reports:

- `quota_active_requests: 0`
- `quota_provider_calls: 0`
- `smoke_questions_sent: 0`
- `provider_calls: 0`
- `answer_execution_authorized: false`

The existing harness still retains the HTTP 429 + zero-provider-call hard stop.

Final live `IsolatedAdmissionHarness.preflight()` result:

`AUTHORIZED`

Reason codes: none.

## 7. Tests and checks

Scoped + existing required suite:

`42 passed, 1 warning in 2.86s`

Included:

- endpoint identity is M27 production-equivalent, not M26 console
- zero questions/provider calls on preflight surface
- exactly-one detection
- zero/multi fail-closed
- production/test-page exclusion
- cleanup protection
- low-memory guard boundaries
- build/image/container identity exposure
- existing isolated admission harness
- production-equivalent runtime
- production evidence bridge
- runtime observability
- runtime finalization

Static checks:

- `python -m compileall -q src/knowledge_engine tests`: PASS
- scoped Ruff: PASS
- `git diff --check`: PASS

Live listener verification:

`GET http://127.0.0.1:18080/v1/health` -> HTTP 200.

## 8. Production read-only receipts

Before repair:

- HTTP 200
- build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`

After cleanup/restart and final preflight:

- HTTP 200
- same build SHA
- same entrypoint

Production backend identity stable: YES.

No production mutation occurred.

## 9. May 05 rerun?

YES. 05 may rerun its own preflight using the isolated endpoint and exactly-one eval container. This READY state is not a smoke PASS and this session sent no smoke questions.

The preflight endpoint itself remains question-disabled by design in 05R. 05 owns the decision to proceed to its bounded smoke after revalidating all gates.

## 10. Forbidden actions not performed

- no smoke questions
- no admission run
- no Stage13/14 legacy admission
- no Chunk002
- no 100-case
- no full523
- no benchmark tuning
- no production mutation
- no production restart/stop/rebuild/deploy
- no production R2/Qdrant/SQLite/release-pointer write
- no dirty import from `/home/ubuntu/LLM_Wiki-m27-context-runtime`

`M27_ADMISSION_SMOKE_PREFLIGHT_READY`
