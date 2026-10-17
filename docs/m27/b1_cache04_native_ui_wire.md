# B1-05 CACHE04 · Isolated Native Cache Mode/UI Wiring (Scoped)
Date: 2026-10-17. Owner-only Nonprod. **Not a deployed Product.**

## Exact frozen parent and protected surface
Parent CACHE01 HEAD `1ac91967f6760edf0e0934be2f4dc7f71f404ead`; TREE `1a6825da10059b404f6368cf88b9cf2cdf888ee1`.
Contract `src/knowledge_engine/m27_b0_cache_contracts.py` is imported unchanged. No shared M26/M27 API, Composer, Auth, TaskContract, native product app or D01 modifications.

Read-only ingress map established by CACHE01 and re-inspected:
- `m27_isolated_http.create_app` has `POST /v1/answers/stream`; default no executor, status 503. This is a source route, not a currently verified authenticated native Product.
- `m27_n31_nonprod_app.N31LocalApp` local `POST /task` fixture; its `mode` is not the semantic cache mode, and its request parser forbids `cache_mode`.
- M26 `m26_translation_gateway_public_api.py` `/v1/answers` allowlist is `{"question"}`; must not add fields in this Worker.
- Historical canary owner-only forwarding does not prove currently deployed Product identity, live IdP, source rights or acceptance. **CURRENT AUTHENTICATED PRODUCT CONSUMER NOT ESTABLISHED**. H02 must verify independently.

## New scoped local UI path
`docs/m27/b1_cache04_demo/index.html` is served by `m27_b1_cache_native_adapter.Cache04Demo` on `127.0.0.1` ephemeral port. No public route, no production ingress, no network provider or model. The UI provides:
- checked `Use answer cache` -> `AUTO`; unchecked -> `BYPASS` (change triggers actual HTTP fetch);
- `Submit selected mode`; advanced `REFRESH` button for a one-request override;
- request/receipt display with mode, decision, UUID request ID, HTTP status, source qualification boundaries; accessible keyboard focus, ARIA status, textContent (no dynamic innerHTML).
- Explains that BYPASS does NOT disable provider prompt caching, retrieval caches, memory or all storage.
- feature flag is server-held **OFF** by default. The browser query `fixture_feature=enabled` controls only its own E2E expected decision for tests; it cannot enable the server flag.

Local loopback test HTTP POST: `/__cache04/demo/request`
Untrusted demo request exact schema:
```json
{"schema_version":"m27.cache04-choice-demo/v1","request_id":"32-character UUID hex","cache_mode":"AUTO","question":"Non-sensitive text"}
```
Only `cache_mode` is portable to a future **new versioned authenticated Product API**. Demo schema and fixture-generated principal are **not** public Product contract. Parser rejects extra privileged fields; server never accepts client identity/source/policy/rights/TTL/feature flags. Server generates fixture internal envelope with CACHE01 `m27.semantic-answer-cache/v1` and calls `parse_internal_request` + `describe_cache_operations` unchanged.

Real local HTTP response includes CACHE01 `build_response_contract` fields and:
`ui_schema_version`, `scope=LOCAL_FIXTURE_ONLY`, `product_authenticated=false`, `answer_published=false`, `answer_cache_hit_admitted=false`, `demo_fixture_io_reads`, `demo_fixture_io_writes`.
Neither answer nor HIT is published; `cache_io_performed=false` is authoritative in this local UI path. HTTP headers are `Cache-Control: no-store`, strict Host/Origin, HttpOnly SameSite session cookie, Content Security Policy nonce, nosniff, no-referrer, no iframe. This demo's cookie is not an external IdP and must never be treated as one.

## Test-only cache operation spy (not a provider, store or verifier)
`FixtureCacheIOSpy` is an in-memory bounded instrumented map. Only directly called local tests can pass `fixture_authority=True` to `run_adapter`; the HTTP handler never does.
- `BYPASS`: 0 lookup, 0 write, regardless of feature flag, supplied final or fixture authority.
- `AUTO` static QA with explicit fixture feature ON: `LOOKUP_REQUIRED`, optional spy candidate read; even existing candidate -> `PROVER_REQUIRED`, never `HIT`.
- `REFRESH`: `REGENERATE_NO_LOOKUP`, 0 old candidate reads. A local **FIXTURE_ONLY** final with all explicit test gates true can exercise the spy CAS. Invalid/absent final, outdated source, wrong CAS prior preserve earlier entry. This is **not** evidence of an authenticated issuer, Provider-qualified answer or durable cache.
- With fixture authority disabled (always disabled in HTTP), **all modes perform zero answer-cache reads/writes**, even if the Nonprod server feature flag is explicitly ON.

## Negative controls
Invalid or missing demo session/Origin/header, unknown privileged fields, forged tenant/principal, bad mode/schema, HTML/script/javascript request strings, invalid JSON/type/body bounds, request replay, cancellation, nonloopback binding attempts. No raw query/cookie or API key is logged. No LLM/local model used. No M26/M27 shared runtime route changed.

## H02 exclusive integration contract
1. Pin/verify latest accepted CACHE01/02/03 and H01 provenance. H02 must discover and prove the genuinely current authenticated native consumer, not route by source name alone.
2. New native Product schema (separate from this demo) validates **only** `cache_mode` from client via `parse_public_cache_choice`; the authenticated server constructs `identity/question/source/policy/cache_window` using IdP, TaskContract, current ACL/source/consent and revocation snapshot. Fail closed if absent.
3. Invoke CACHE01 planner on server-built envelope; CACHE02 lookup and CACHE03 fresh current-rights/source and independent semantic qualification on AUTO only, no semantic HIT by similarity alone.
4. Preserve BYPASS zero semantic answer-cache I/O, REFRESH no prior-cache HIT lookup, and allow CACHE05 conditional atomic verified-final replacement only after genuine fresh authenticated qualification. Invalidate on revocation; do not reuse live/relative, Research/Coding/Action.
5. Return a versioned, authenticated final receipt with same request ID, mode, actual read/write status, independent evidence, citations and no-store headers. Do not substitute this demo receipt, fixture flags, or test-only cookie for qualification.
6. Run H02/H03 real Consumer/Client/source/rights tests separately before any publication. This Worker does not merge, sign, deploy or claim Product PASS.
