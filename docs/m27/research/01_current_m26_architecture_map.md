# 01｜Current M26 Architecture Map

Status: Stage 0B research, read-only. Production was not modified or restarted.

## Production identity verified

- Container: `llm_wiki-knowledge-engine-1`
- Image: `knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z`
- Freeze tag: `knowledge-engine:m26-production-freeze-generic-fallback-guard-20261003T063245Z`
- Freeze dir: `/home/ubuntu/production-freezes/m26-production-freeze-generic-fallback-guard-20261003T063245Z`
- Runtime status observed: healthy, bound to `127.0.0.1:8080->8080/tcp`
- Entrypoint observed from container inspect:
  `uvicorn knowledge_engine.m26_console_api:app --host 0.0.0.0 --port 8080`

Important: M27 clean workspace is not the complete production source. The production image imports `knowledge_engine.m26_console_api`, while `/home/ubuntu/LLM_Wiki-m27-context-runtime` currently does not contain `src/knowledge_engine/m26_console_api.py`.

## Source truth findings

Compared production image source, dirty production worktree, and M27 clean branch:

- Production Python files under `knowledge_engine`: 382
- Production files matching dirty worktree `/home/ubuntu/LLM_Wiki-f746-quality-gate-20260930`: 382 / 382
- Production files matching M27 clean branch: 331 / 382
- Production `m26*.py` files: 102
- M27 clean `m26*.py` files: 65
- Production `m26*.py` files missing from M27 clean branch: 37
- Production files present in M27 but differing from production: 6 M26 files

Missing from M27 but present in production/dirty source:

```text
m26_active_production_release.py
m26_active_release_dense.py
m26_admin_audit.py
m26_admin_auth.py
m26_admin_contract.py
m26_admin_control_plane.py
m26_admin_corpus.py
m26_admin_health.py
m26_admin_ingestion.py
m26_admin_ingestion_core.py
m26_admin_ingestion_sync.py
m26_admin_overview.py
m26_admin_production.py
m26_admin_qa.py
m26_admin_settings.py
m26_admin_usage.py
m26_console_api.py
m26_console_health_runtime.py
m26_console_p05_ask_playground.py
m26_daily_ip_rate_limit.py
m26_golden_production_provider.py
m26_golden_questions_admin.py
m26_ingestion_candidate_qdrant.py
m26_ingestion_candidate_writer.py
m26_ingestion_finalization.py
m26_ingestion_health_read.py
m26_ingestion_operator_health.py
m26_ingestion_qdrant_qualification.py
m26_ingestion_read_runtime.py
m26_ingestion_runtime.py
m26_jobs_rollback_api.py
m26_production_promotion.py
m26_qa_inbox_integration.py
m26_runtime_read_cache.py
m26_runtime_read_worker.py
m26_sqlite_ingestion.py
m26_suggested_questions_admin.py
```

Production files that exist in M27 but differ from production:

```text
m26_aq_semantic_contract.py
m26_ask_api.py
m26_pa7_arbitrary_query_runtime.py
m26_pa7_semantic_closure_runtime.py
m26_production_answer_bundle.py
m26_public_api.py
```

This is the most important Stage 0B finding. Formal M27 implementation must not start from the clean branch alone.

## Console / public API composition

Production entrypoint is `m26_console_api:create_app()` from the production image / dirty source. It composes the public answer API plus admin/QA/ingestion/control-plane surfaces.

Observed production `m26_console_api.py` structure:

```text
create_app()
  app = create_public_app()
  production_admin = production_admin_runtime_from_env()
  durable_adapter = enrich_read_authority_from_env(build_runtime_ingestion_adapter_from_env())
  install_admin_control_plane(...)
  install_admin_overview(app)
  install_admin_ingestion_routes(app, adapter=durable_adapter, include_job_reads=True)
  install_admin_corpus(app, adapter=object_store_corpus_adapter_from_env())
  install_qa_inbox(app)
  include playground router
  install_suggested_questions_admin(app)
  install_admin_usage(app)
  materialized_console_health_observer()
  install_admin_health(app, observer=health_observer)
  install_jobs_rollback_routes(... include_job_reads=False)
  install_golden_questions_admin(...)
  install_admin_settings(app)
  install_admin_audit(...)
```

M27 insertion planning must account for this composition layer. The public answer path is not the whole production app.

## Public request flow

Primary public endpoint source:

```text
src/knowledge_engine/m26_public_api.py
```

Canonical public path:

```text
POST /v1/answers
  -> create_app().answers()
  -> origin admission
  -> readiness problem check
  -> body parse and language checks
  -> pseudonymous IP key
  -> provider guard
  -> fallback budget guard
  -> quota admission
  -> StreamingResponse(_answer_event_stream(...))
```

`_answer_event_stream()` performs:

```text
request.accepted SSE
  -> background worker thread
  -> run_owner_query_for_web(... event_sink=sink ...)
  -> runtime stage/model events are sanitized
  -> terminal DTO converted to answer.completed / answer.partial / answer.abstained / answer.failed
  -> no material answer is emitted before terminal DTO publication
```

The public stream allow-list currently sanitizes runtime events to fields such as stage, status, provider, model, latency, fallback flags, reason codes, selected evidence count, channel, deadline and elapsed time.

## Owner / runtime path

Owner/web query bridge:

```text
src/knowledge_engine/m26_ask_api.py
  run_owner_query_for_web(...)
  _run_owner_query_for_web_with_default_provider_routing(...)
  build_web_query_dto(...)
```

Runtime core:

```text
src/knowledge_engine/m26_aq_semantic_contract.py
  run_owner_arbitrary_query(...)
```

Important: M26 already contains primitive routing and compute budget logic:

```text
SemanticRoutingDecision
_deadline_remaining_ms(...)
_route_minimum_budget_ms(...)
_routing_decision(...)
_fast_failure_route(...)
_low_information_retry_decision(...)
_semantic_failure_route(...)
```

Routes include patterns equivalent to bounded compute/recovery decisions:

```text
FAST_RETRY_ONCE
SEMANTIC_CLOSURE
EVIDENCE_SLOT_REALIGNMENT
CLAIM_WEAKENING
CONTRADICTION_TRIAGE
SAFE_ABSTENTION
```

M27 should extract/generalize this logic instead of reimplementing a parallel router.

## Runtime core flow

Canonical semantic runtime flow:

```text
run_owner_arbitrary_query
  -> normalize question
  -> canonical intent class
  -> validate gate
  -> admission
  -> prompt-injection / privacy / underspecified workflow guards
  -> provider initialization
  -> load_production_answer_bundle()
  -> _run_lexical_primary_retrieval(... top_k=8 ...)
  -> _select_evidence(...)
  -> derive_semantic_requirements(...)
  -> runtime._strengthen_evidence(...)
  -> low support abstention if no evidence or no meaningful overlap
  -> _try_strict_evidence_bound_answer(...)
  -> _try_fast_supported_answer(...)
  -> _consolidated_semantic_recovery(...)
  -> _publish_support_proof_recovered_answer(...)
  -> runtime._response_from_verification(...)
  -> publication event
```

This is not a plain RAG path. It already contains deterministic adaptive retrieval, bounded semantic repair, verification, and publication gating.

## Data plane map

### Production answer bundle / release binding

Relevant source:

```text
src/knowledge_engine/m26_production_answer_bundle.py
```

Production branch adds important active-binding behavior not present in M27 clean branch:

```text
invalidate_production_answer_bundle_cache()
_resolve_active_production_binding(...)
_accepted_qdrant_collection(...)
expected_qdrant_collection_for_bundle(...)
_validate_manifest_counts(...)
_qdrant_payload_matches_production(...)
```

M27 must preserve active release binding and accepted Qdrant collection checks.

### Lexical / dense / graph retrieval

Relevant sources:

```text
src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py
src/knowledge_engine/m26_aq_semantic_contract.py
src/knowledge_engine/m23_cloudflare_qdrant.py
src/knowledge_engine/m14_retrieval.py
```

Current retrieval/evidence stack includes:

```text
lexical primary retrieval
dense Qdrant retrieval
optional dense fallback
candidate pool construction
graph expansion
source coverage augmentation
facet coverage enforcement
query coverage enforcement
answer-bearing scoring
diverse candidate selection
provenance evidence
graph evidence
temporal evidence
deduped public evidence summaries
```

M27 should expose this as a domain-level `KnowledgeProvider` / `EvidencePlanner`, not raw Qdrant/R2 tools.

### Context compiler

Existing source:

```text
src/knowledge_engine/m26_context_compiler.py
```

Existing responsibilities:

```text
validate envelope / gap / policy
safe-for-context check
mandatory passage preservation
token budget / reserved instruction budget
budget precheck exclusion
mandatory over-budget fail-closed
deterministic excerpt normalization
context manifest hash
budget receipt hash
citation binding
prompt-injection treated as evidence text, not instruction
abstain-required output when compilation fails
```

M27 should generalize the existing compiler rather than create a new compiler from scratch.

### Admin / ingestion / QA / rate limit data plane

Production-only modules missing from M27 clean branch include the current console/admin surface:

```text
m26_admin_control_plane.py
m26_admin_production.py
m26_admin_health.py
m26_qa_inbox_integration.py
m26_ingestion_runtime.py
m26_ingestion_read_runtime.py
m26_runtime_read_worker.py
m26_daily_ip_rate_limit.py
m26_production_promotion.py
m26_jobs_rollback_api.py
m26_suggested_questions_admin.py
qa_answer_quality*.py
```

Important observed responsibilities:

- Admin control plane installs access/auth/capability gates, audit events, idempotency, middleware and admin capabilities.
- Admin production uses a durable SQLite admin audit/idempotency store.
- Admin health observes backend, public ask in-process health, production bundle, R2, Qdrant, source and active release freshness.
- QA inbox captures terminal answer events and internal context, evaluates answer quality, stores failure traces, clusters failures, and exposes admin review routes.
- Daily rate limiting uses SQLite with pseudonymous IP keys.
- Production promotion / rollback is CAS-like and validates candidate/predecessor artifacts plus Qdrant qualification.
- Jobs rollback API is currently evidence/preflight oriented and fail-closed for activation if no qualified actuator is installed.

## Governance / eval plane map

Existing governance layers:

```text
admission / owner authorization
public origin checks
public quota / fallback budget
prompt-injection / privacy guards
semantic requirement derivation
strict evidence-bound preflight
fast candidate validation
semantic closure / repair routes
verified answer citation gate
safe abstention
QA answer quality inbox
quality gate scripts
release / promotion / rollback checks
admin audit / idempotency
health observers
```

Current generic fallback production invariant:

```text
# Guard: do not emit generic extractive evidence fallback as user-facing answer.
return None
```

This guard is in the production image/freeze and must be treated as a permanent M27 invariant.

## Production boundaries

Do not cross these boundaries in M27 Stage 1:

```text
Do not mutate Qdrant/R2/release pointers.
Do not bypass existing admission/auth/quota/owner/public guards.
Do not bypass verified answer/citation gates.
Do not emit material answer text before terminal verified publication.
Do not expose raw Qdrant/R2/SQLite/Postgres-style infra APIs as agent-facing tools.
Do not add write/admin/release tools to the first M27 tool registry.
Do not use M27 clean branch alone as production source of truth.
```
