# P28R | Nonprod default-lifespan fail-closed and local readiness

This exclusive P28R source patch descends exact P28 `b90ff73399f4ff187c3a5a8a7327ec57e117cbe1`, which in turn descends T27 `8604752934fb43a3441055d33c01940028cc5938`. It does not incorporate or certify the concurrent I28 branch. It is local, unsigned, unprivileged testing only, never Production deployment.

## Actual dependency chain and deficit

`uvicorn knowledge_engine.m26_production_api:app` imports `api.app`, registering `m26_ask_api._preload_query_runtime` at FastAPI startup. With ASGI lifespan enabled, this invokes `load_production_answer_bundle()` then `prepare_minimax_http_client()`. The loader reads the isolated filesystem `channels/production.json` pointer if present, otherwise falls back to `M26_ACCEPTED_PRODUCTION_RELEASE_ID` or legacy `m25blog-5250f8422f4f-f5f01d82c7a1-fe499db2e043` and `releases/<id>/manifest.json`. It requires SHA256-checked manifest plus graph, graph_v2, lexical_index, provenance artifacts, and any enumerated compatibility artifacts. Graph-v1/v2 release identity, node family, edge validity, counts, bytes and hashes must pass. Separately, `/v1/health` uses `channels/p28-nonprod.json`, checks the pointer, manifest and all artifacts and loads the runtime cache. Missing channel returns HTTP 200 with `status=starting`, not readiness.

**Two distinct pointer paths must resolve inside an authorized isolated TEST store:** `channels/production.json` for legacy M26 startup preload, and `channels/p28-nonprod.json` for health. The word production is an inherited compatibility key **within a TEST store**, not permission to access, clone or modify actual Production storage. Manifest, complete bundle, license, release identity, SHA256s, read grant and retention rights must come from legitimate Owner-authorized nonprod sources. Never copy private Production R2/Qdrant data or invent signed manifests.

A query `/api/m26/query/stream` additionally needs approved owner identity and backend token, PA7 gate/payload and provider rights. This worker makes no such authorized query.

## P28R source and build contract

* `src/knowledge_engine/p28r_local_healthcheck.py`: local-only readiness probe, rejects 200/starting, wrong release/channel/hash. Exit 0 requires `APP_ENV=test`, `OBJECT_STORE_BACKEND=filesystem`, `P28R_NONPROD_TEST_SCOPE=authorized` and health matching explicit expected test release ID, channel and 64-hex manifest SHA256. Environment variables alone are **not** legal authority.
* `docker/nonprod/Dockerfile.p28r`: preserves original uvicorn CMD; replaces P28's status-only HEALTHCHECK with the readiness probe. Does not modify inherited M26 functionality.
* `scripts/p28r_stage_build.py`: first verifies P28's original 857 T27 Git-exact source files, then stages in a fresh build context and overlays exactly one new Python module plus one Dockerfile. Receipt distinguishes the original source chain from added bytes.
* `scripts/p28r_lifespan_negative.py`: real default startup with lifespan **on**, no command override, in an ephemeral rootless, read-only, `--network none`, no-host-port Docker container. Captures exit 3, exact missing manifest, removes its own container, and compares other container IDs.
* `tests/test_p28r_local_healthcheck.py`: unit-test stub payloads for status/identity/scope/permission negatives. Stubs are NOT authentic test release data, nor real application readiness.

Local Git bytes, locally exported OCI layout and independent signed runtime are separate classes of evidence. Version constraints and local wheel/distribution inventories do not themselves prove hash-locked Linux wheelhouse, isolated build backend or reproducible signing.

## Owner input and I28 handoff

Absent an authentic, consented, legally available nonprod release bundle supporting both scoped pointers, this is **PARTIAL**, not local default-lifespan READY. Required Owner action `P28R-NONPROD-TEST-BUNDLE-GRANT`: name grant/steward, immutable nonproduction release, full artifact key/digest inventory, specific rights and read-only test mount. `P28-NONPROD-BUILD-CONTROLLER` separately grants a hash-locked Linux wheelhouse/backend and independent signing/provenance. After legal input, rerun real lifespan/health before a READY claim. P28R source is a handoff to I28/V28, not proof of the as-yet-unfrozen final I28 image. No Production deployments, pushes, production-bound CI or existing staging container actions are permitted.
