# P28 | Authenticated local T27 source to isolated unsigned OCI

## Exact source and boundaries

Original **T27** Git HEAD `8604752934fb43a3441055d33c01940028cc5938`, tree `123578f9e1059d1b554fc3fdc011bdc171033afd`, not this P28 recipe branch. Independently compare the 857 tracked physical source files (13,931,942 bytes) copied under `src/`, `pilot/`, `pyproject.toml`, `README.md` against `git show HEAD:path` and fail on added/altered/symlinked paths. Export the exact selected paths from `git archive HEAD` into a staging directory. P28's Dockerfile and version constraints are build inputs, not changes to T27. Inspect `P28_T27_SOURCE_COPY_BYTE_CHAIN.json`; the manifest digest is `82f4b814eea8c962fed9a12fc1d12925ac01df8ed5c2a07d9b63991e1a533be0`.

## Actual local build

The base is `python@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3` for linux/arm64. `constraints-p28.txt` is a pinned-*version* snapshot of the local Python 3.11 testing environment; transitive Linux extras and the isolated build backend were not fully hash locked. A same-digest rebuild at another epoch is NOT yet certified. No secret, CI production environment, push, Provider or remote side effect may be used.

```sh
docker buildx build --platform linux/arm64 --pull=false --no-cache --load \
  -t p28-t27-nonprod:20261012-build-a --metadata-file P28_BUILDX_BUILD_A_CORRECTED_METADATA.json \
  -f P28_GIT_COMMITTED_SOURCE_CONTEXT/Dockerfile P28_GIT_COMMITTED_SOURCE_CONTEXT
docker buildx build --platform linux/arm64 --pull=false \
  --label io.knowledge_engine.p28.rehearsal=next --load \
  -t p28-t27-nonprod:20261012-build-b -f P28_GIT_COMMITTED_SOURCE_CONTEXT/Dockerfile \
  P28_GIT_COMMITTED_SOURCE_CONTEXT
docker buildx build --platform linux/arm64 --pull=false \
  --label io.knowledge_engine.p28.rehearsal=next \
  --output type=oci,dest=P28_T27_NONPROD_LOCAL_CORRECTED.oci.tar \
  -f P28_GIT_COMMITTED_SOURCE_CONTEXT/Dockerfile P28_GIT_COMMITTED_SOURCE_CONTEXT
```

The image contains original CMD `uvicorn knowledge_engine.m26_production_api:app --host 0.0.0.0 --port 8080`, not the T27 Chrome client as a separately deployed App. The original startup **preloads a production answer bundle** and therefore fails closed with exit 3 in a sealed empty nonproduction filesystem. Do not use real Production bundle, R2 credentials or Provider merely to make this test pass.

## Minimal diagnostic localhost smoke and rollback

Use `scripts/p28_nonprod_smoke_rollback.py` against A/B. It runs a real uvicorn OS process using `--lifespan off` **only in disconnected local diagnostics** (`--network none`, no ports, read-only root, per-container tmpfs owned by UID 10001, no provider credentials) and probes **inside the container** at `127.0.0.1:8080/v1/health` and `/openapi.json`. This exercises import, packaging, HTTP routing and nonprod read-only API but skips production bundle preload. The expected health status is `starting`, not `healthy`; do not treat it as real service readiness. Three separately observed OS processes execute **image A → B → A**, record PID / exit, then are removed. Both images derive from the same T27 source with distinct local config/index digests. Never switch production image, pointer or Nginx route.

The shipped `pilot/m27/t27-local-native-trial/client.js` must byte-match T27 committed JS and pass host `node --check`. Its presence does NOT prove a remotely authenticated browser App is deployed.

## Missing independent completion proof

Independent nonproduction CI signer/registry controller, signed source-to-image provenance, hash-locked Linux wheels/build-backend/base mirror, an authorized nonprod M26 release fixture/bundle for *default lifespan* with no Production data, an independently observed client on the exact immutable I28 image, approved real Provider usage/invoice and genuine rights/holdout custody are still required before any external admission. Coordinate **P28-NONPROD-BUILD-CONTROLLER** with T27's `T27-NONPROD-CONTROLLER-GRANT`, but do not invent grants, signatures or financial receipts.

No Production services, release pointers, Nginx, official CI production workflow or external public endpoint were modified or dispatched. Starting the **local** Docker Desktop daemon also automatically resumed existing local staging/demo containers under their existing restart policies; no existing container definition or image was intentionally edited by P28.
