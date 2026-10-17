# B0-01 F03-CACHE-01 | Versioned semantic answer cache & native ingress map

**Status:** Contract implemented in a new standalone module; feature **OFF**. Neither a production cache nor a deployed/native authenticated M27 API. Evidence inspected at pinned D01 HEAD `97a5d18ffcada39632426146d7f73681a054bd54`, TREE `50d6e6bb59f4c3864978fcbbe39ee2198a405d62`.

## 1. Native ingress proof, exact files/functions (read-only)

| Real file under `src/knowledge_engine/` | Observed entrypoint/function | Meaning for CACHE01 |
| --- | --- | --- |
| `m27_n31_nonprod_app.py` | `N31LocalApp.__call__` permits `POST /task` only after local loopback and `x-n31-local-token` checks; `N31LocalApp._check_body` lists workload/run/tenant/actor/source_revision/lease_epoch/mode/revoke_after_enqueue. `build_app` constructs fixture app. | **Established LOCAL FIXTURE route only.** `APP_ENV=test`, `N31_LOCAL_ONLY=1` required. `mode` is action fixture mode (normal/lost_ack/observer_unknown), **not cache_mode**. Rejects cache_mode as unknown. Not an authentic Product ingress. |
| `m27_isolated_http.py` | `create_app` exposes `GET /v1/health`, `GET /v1/preflight`, `POST M27_ISOLATED_STREAM_PATH` via `stream_answer`. Default `app=create_app()` has **no executor** and answers with 503 `M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE`; `create_test_page_app` installs owner-only stream executor. | **Established isolated runtime route in source, NOT a proved authenticated published native Product route**. Requires exact H02 consumer ownership, qualification, and separately admitted executor. |
| `m27_c02_native_composer.py` | `compose_native_candidate(request_id, run_id, question, tenant_id, principal, sources, generator, semantic_provider, client_publisher, verify_client_ack, budget_units, ...)` | Direct Python candidate callable and client acknowledgement verifier, **not a registered HTTP route**. Default nonqualified fixture path cannot establish Product admission. |
| `m27_task_contracts_v1.py` | `task_contract(o, now=None)`, `context_request` separately in `m27_context_contracts_v1.py`. | Tenant/authority/task/budget/privacy/Outcome contracts exist, but neither is this new cache API and no shared edit authorized. |
| `m27_ar03_verified_rights_v1_experimental.py` | `VerifiedRightsConsumer.authorize_read(...)` and `authorize_publication(...)` require real Provider observations/checkpoints and independent publication rights. | Real rights must be bound **before lookup** and revalidated on every HIT/publication. Experimentally sourced mechanisms are not automatically proof of current authorized issuer. |
| `m26_translation_gateway_public_api.py` | `create_app` `public_answers` at `POST /v1/answers`, `ALLOWED_FIELDS={"question"}`, unknown fields rejected, `StreamingResponse` has `Cache-Control: no-store`. | M26 translation gateway cannot accept new `cache_mode` without H02-controlled separate API change; not this Worker's scope. |
| `m26_multilingual_public_api.py` | `create_app` `answers` at `POST /v1/answers`; `ALLOWED_FIELDS={"question","answer_language"}`; `_parse_track2_public_request` validates. | Another M26 strict `/v1/answers` handler, not safe to unify by assumption. |
| `m26_public_api.py` | `create_app` `answers` at `POST /v1/answers`. | Separate M26 public route; no cache-mode entitlement asserted. |
| `docs/m27/README.md` | Stage 0 hard rule **"Do not attach M27 to /v1/answers yet."** | Strong negative product-ingress evidence; keep M26 untouched. |

**Native publicly authenticated M27 Product ingress: NOT_ESTABLISHED** by inspected source. H02 must identify exact deployed/authorized native consumer entrypoint, request parser, real Task admission, principal and source grants; H01 must ratify cache ABI before the only Integrator adjusts shared API/UI. `Cache-Control: no-store` is an HTTP/proxy directive; not evidence of nor a ban on private internal semantic answer caching. Existing M26 runtime/read/retrieval/provider prompt caches remain separate and unchanged.

## 2. Contract envelope `m27.semantic-answer-cache/v1`

`parse_public_cache_choice({"cache_mode": "AUTO" | "BYPASS" | "REFRESH"})`: **sole** client-controlled extension. No identity, source, policy, ttl, skip-verifier, admin, or provider knobs allowed; no implicit coercion, no extra fields. UI default **AUTO** is a future proposal only while feature remains OFF. H02 must separately and explicitly wire an authenticated UI selection to server-side request context, verify the same value survives Task admission, and display a truthful status.

`parse_internal_request` requires **exactly**:
- `schema_version` and `request_id`, `cache_mode`.
- `identity`: `tenant_id`, `principal_id`, `auth_context_sha256`, `authenticated=true`. H02 constructs only after actual external authentication; client claims are inadmissible.
- `question`: `text`, `language`, `task_kind`, `intent_id`, `obligations[]`, `negated`, `numeric_literals[]`, `temporal_scope` (`STATIC`/`POINT_IN_TIME`/`RELATIVE`/`LIVE`), `answer_type`. Obligations represent required answer/citation/policy constraints, not just vector intent. Only QA is eligible; no Research/Coding/Action replay.
- `source`: `corpus_id`, `corpus_revision`, `corpus_sha256`, `source_manifest_sha256`, `acl_sha256`, `rights_sha256`, `source_ids[]`. Bind to current source bytes/revision and independently authorized read/publication/consent, not a caller-provided digest alone.
- `policy`: `policy_version`, `policy_sha256`, `verifier_version`, `embedding_version`, `admission_version`, `revocation_epoch`. Revocation epoch monotonic under G04 authority, backed by external source/rights verifier.
- `cache_window`: UTC Z `requested_at`, server-bounded `ttl_seconds` 1..3600. This cap is solely a contract upper limit, not authorization to accept client-requested TTL. Actual expiry and refresh depend on latest source freshness.

`parse_candidate` requires exactly `schema_version`, `identity`, `question`, `source`, `policy`, `lifecycle`, `answer`, `citations`, `provenance`. Lifecycle: `created_at`/`expires_at`/TTL/monotonic revocation_epoch/ACTIVE-or-REVOKED; expiry <= TTL. Citations must bind source IDs with revision, byte/source SHA and citation SHA. Provenance: `answer_sha256`, `final_verifier_receipt_sha256`, `source_verifier_receipt_sha256`, `rights_receipt_sha256`, `qualification_class`; SHA protects content, **does not authenticate evidence issuer**.

`build_response_contract` emits only `schema_version`, `request_id`, `cache_mode`, `cache_status`, `answer:null`, `citations:[]`, `verifier_receipt_sha256:null`, `internal_answer_cache_enabled:false`, `cache_io_performed:false`. It rejects answer payloads and unadmitted `HIT` status. H02/CACHE06 must version an actual publishable result envelope after independent admission. No public-facing cache HIT claim in CACHE01.

## 3. Admission semantics & explicit conservative decisions

1. Authenticate tenant/principal and Task purpose before any lookup. Call real Provider/source right verifiers and create current source/ACL/revocation snapshot before any candidate lookup. A compromised store is untrusted.
2. `plan_cache_request(..., feature_enabled=False)` => `DISABLED` (no answer cache I/O). `BYPASS` => `BYPASSED`, no semantic answer cache reads **or writes**, while normal QA verification remains mandatory. `REFRESH` => `REGENERATE_NO_LOOKUP` and must not read old answer/HIT; only qualified verified final permits future compare-and-swap. `AUTO` => `LOOKUP_REQUIRED` only for static/point-in-time QA with effective rights. Research/Coding/Action, temporal LIVE/RELATIVE => failclosed non-cache route.
3. CACHE02 may look up bounded candidates in a tenant and principal partition only after #1. CACHE03 re-screens every candidate. Exact tenant/principal/auth context, source corpus/version/manifests/ACL/rights, policy, verifier/embedding/admission versions, revocation, locale, intent, obligations, numeric/negation/temporal fields, cited source membership and time validity must match. `screen_candidate` returns only `DENY_CANDIDATE` or `PROVER_REQUIRED`, **never HIT**.
4. CACHE03 requires a **fresh qualified verifier** for semantic equivalence, question entailment, rights/consent, ACL, current source and citation binding, answer-type and temporal constraints. A matching vector alone cannot prove equivalence. `verify_hit_contract` parses strict prover shape, rejects unknown flags/malformed/fixture receipt, and still returns nonadmission until trusted issuer and full published-product binding exist.
5. CACHE05 accepts only verifier-qualified **final** output, never draft/partial/failed/refused/safe-terminal payload. Atomic `compare_and_swap_verified` must reject concurrent policy/source revoke or source drift, and never destroy the last safe record when a REFRESH final fails. `qualify_final_write` is a strict contract placeholder and returns nonadmission, with no active store.
6. On revoke/erasure, invalidate primary and derived index/data, ensure restoring stale backups cannot resurrect revoked material, bump revocation epoch, and deny old candidates even within TTL. No stale-while-revalidate for private or revoked answers.
7. Preserve provider prompt cache, retrieval/read cache, memory, and Task journal under their **own** boundaries. Do not repurpose answer-cache status as a provider cache, citation-rights override or Action-effect replay.

## 4. Typed handoffs & code owners

- **CACHE02** (`CacheStoreV1` Protocol): `lookup_candidates(request, *, limit) -> list[record]`; `compare_and_swap_verified(request, record, *, previous_revision) -> bool`; `invalidate_reachability(*, tenant_id, principal_id, source_manifest_sha256, revocation_epoch) -> int`. Store isolation, TTL, encryption, atomic CAS, durable revocation, backup invalidation required; no Qdrant deployment or shared API edit.
- **CACHE03** (`CacheGateV1`): `authorize_and_snapshot(request) -> rights/source snapshot`; `reverify_hit(request, record) -> signed qualified proof`. Must use real source observations, citation and rights/consent issuer; prevent structural-constraint collisions. Hook may return deny. No assumed provider availability.
- **CACHE04** (H02-only public integration): propose public UI `cache_mode` choice schema, server authn/policy/source building, API version negotiation, backward compatibility, request/response receipt, accessibility and no-store HTTP headers. **No endpoint name invented as live**. Must not add fields to existing M26 strict API independently.
- **CACHE05** (`CacheGateV1.verify_final_write(request, final)` plus CACHE02 CAS): require final verified source-bound answer plus qualified real verifier and no revocation race; atomic insert/replace after successful checked generation. AUTO miss qualified write, REFRESH qualified replacement, BYPASS none.
- **CACHE06 / H02**: single versioned native Product ingress, independent end-to-end positive+negative verification, source/citation/revoke concurrency, Client ACK, cold/warm separate permitted corpus. H02 owns shared integrations; no use of official 523 or sealed blind200 for warming/inspection.
- **H01**: ratify precise same-request policy authority, issuer signature/trust store, current rights snapshots and distributed invalidation semantics before allowing real HIT or write admission. Existing right consumer `authorize_read`/`authorize_publication` is guidance, not automatically portable signature approval.

## 5. Telemetry and rejection controls

Private-safe telemetry only: `schema_version`, request ID, operation mode, `cache_status` (`DISABLED`, `BYPASSED`, `REFUSED_NON_QA`, `LOOKUP_REQUIRED`, `REGENERATE_NO_LOOKUP`, `DENY_CANDIDATE`, `PROVER_REQUIRED`, `VERIFIED_FIXTURE_ONLY`, `HIT_NOT_ADMITTED`, `WRITE_NOT_ADMITTED`), blinded tenant/principal references, source/corpus/policy version fingerprints, snapshot age, expiry, revocation epoch, miss/deny reason, qualified receipt hash, verifier latency, CAS outcome, budget. Never log raw answer, query, client credential, raw vectors, bearer token or inaccessible citation. Fixture receipt is always `FIXTURE_ONLY`, not a formal Product HIT.

**Evidence boundary:** `tests/test_m27_b0_cache_contracts.py` executes pure positive/negative examples, synthetic digests and mock issuer callback. None constitute a real current source provider, authenticated public endpoint, HIT, store, verifier, true Client ACK, or Production/Release certification. All code/QA remains independent Nonprod and feature OFF.

## 6. Continuation: definitive isolated route discovery and historical production boundary

An additional **read-only** source/discovery pass identified the **exact isolated M27 consumer** beyond the C02 callable:

- `src/knowledge_engine/m27_isolated_streaming.py`: `M27_ISOLATED_STREAM_PATH = "/v1/answers/stream"`, `M27_ISOLATED_STREAM_SCHEMA = "m27-isolated-first-answer-stream/v1"`.
- `src/knowledge_engine/m27_isolated_http.py`: `create_app` registers `@candidate.post(M27_ISOLATED_STREAM_PATH)` on `stream_answer`; `app = create_app()` receives no `stream_executor` and fails closed with HTTP 503 if called. `create_test_page_app` is a **different** owner-only executor factory, not the default App.
- `docker-compose.m27-isolated.yml`: launches `uvicorn knowledge_engine.m27_isolated_http:app`, binds `127.0.0.1:18080:8080`, `restart: "no"`, eval labels. This **demonstrates deployable isolated evaluator wiring in repository source**, not a current public deployment.
- `scripts/m27_smoke_preflight_check.py`: expects `http://127.0.0.1:18080` and checks the isolated module identity. It is a **nonprod smoke harness**, not production qualification.
- `src/knowledge_engine/m27_d01_nonprod_integration.py`: explicitly declares D01 opt-in Nonprod not registered in any default Product entrypoint, and keeps fixture-only delivery and authentic publication separate. `D01_INTEGRATION_ADMISSION_DECISION.json` has `FORMAL_PRODUCT_GO=false`, `NATIVE_COMPOSER_ADMISSION=false`, `PRODUCTION=NO_GO`.
- `docs/m27/canary/M27_OWNER_ONLY_CANARY_ROUTE_PROOF.md` and `docs/m27/research/72_m27_owner_only_canary_activation_report.md`: **historical Stage28** documentation says an Owner-only authenticated Nginx canary forwarded `/v1/answers` to `127.0.0.1:18080/v1/answers/stream`, with M26 fallback for other users. The recorded old candidate SHA is `b72b2ec9ac95b4bff9c24177002522c9a07039e1`, **not pinned D01**. These are **historical reports only**; they do not establish the current remote Nginx configuration, running binary, valid signer/IdP, current route authorization, or that the D01 cache contract reaches it. No privileged host inspection/health probe/deploy was authorized or attempted here.

**Ingress conclusion remains:** `POST /v1/answers/stream` is a **source-established isolated M27 HTTP route** (now corroborated by AST and Compose tests), but `AUTHENTICATED_CURRENT_M27_PRODUCT_ROUTE = NOT_ESTABLISHED`. The prior historical owner-only canary is an insufficient basis for declaring current Product admission. Formal B0-01 handoff must retain this distinct H02 proof gap.

### H02-only proposed native adapter, no shared code changes by CACHE01

```text
[client proposed cache_mode AUTO|BYPASS|REFRESH]
    -> [H02 versioned authenticated native M27 endpoint, identity from IdP]
    -> [native Task contract validation + task-kind QA classification]
    -> [H01 effective source/ACL/consent/current policy snapshot]
    -> [CACHE01 parse_internal_request (server-built, never trust client ACL)]
    -> [CACHE01 describe_cache_operations, default feature OFF]
      BYPASS: 0 semantic answer cache I/O -> normal verified answer generation
      REFRESH: 0 old answer HIT reads -> normal generation -> CACHE05 final verifier -> CAS
      AUTO: CACHE02 tenant/principal lookup -> CACHE03 current semantic + source recheck
        -> verified citation-bound HIT (future only) OR verified model final
        -> CACHE05 guarded write (future only)
    -> [native response includes authoritative cache_mode/cache_status, H01 signature]
    -> [Client confirms same request ID, terminal and cache status separately]
```

**Do not wire now:** H02 owns any actual route, user toggle, middlewares, current source/rights fetching and shared API. Privileged input fields from UI must remain prohibited, `Cache-Control: no-store` intact. The `CacheOperationPolicy` immutable flags describe *candidate downstream operations after authority*, and `actual_store_io_authorized` is **always False**. Only H01 plus CACHE02/03/05 can turn future snapshots/verifier results into real cache reads, HIT eligibility or writes. H01 issuer approval and H02 exact consumer freeze remain open. No official 523 or sealed blind200 use.

**Machine-checked source invariants:** `TestNativeIngressStaticContract` asserts the M27 registered route and default executor-free app via Python AST, Compose loopback/eval properties, M26 strict allowlists, and N31 fixture flag/route. These tests confirm the *source tree*, never the installed runtime or deployed Product.
