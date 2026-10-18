# H02 Native Nonprod A05 Source Consumer | Frozen Interface Spec | 2026-10-18

**Scope:** one H02-owned loopback source consumer. It is NOT native Product routing, model generation, independent signed issuer, Product Client admission, authorized Cloudflare custom Gateway, or Q34-equivalent behavior.

## Source and authority
- Starting H02 HEAD be9b88c7a2d02fd4089223b8516644bfed97fbd9, TREE f67792a04fbcdd4be85ab117088e129d5ff18435. Parent B3-05 is only historical; all new H02 commits derive from be9b88c7.
- Real Owner A05 release: 11 first-party documents and 21 verified passages, source manifest SHA256 7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3; release ID a05context-7835ec95cee63972; source revision 89f1d7be1623cd6926a69e38871544eefe39e584. Local Git-pinned B3-05 source version is required.
- Local independently provisioned, OS-permission-restricted epoch fence is only local nonprod rights evidence; NOT Product IdP/third-party Custodian.
- Product admission remains PRODUCT_NOT_ADMITTED, cache OFF, provider NOT_RUN, G03 Action denied, invoice/savings unverifiable, no fallback.

## Actual import and call graph

H02-owned executable src/knowledge_engine/m27_h02_native_nonprod_consumer.py:
  1. imports m27_g01_qa_outcome.task_contract for a validated, tightly bound v1 QA TaskContract (NOT the synthetic G01 Session)
     -> m27_task_contracts_v1.task_contract + sha256
  2. imports m27_f03_source_rights_admission.A05OwnerCorpusAdmission
     -> pinned Git B3-05 release/corpus/doc SHA + separately OS-owned local epoch fence
     -> dynamically loads wave_b01/components/a05/adapter/a05_retrieval.py
     -> ContextIndex.search, bounded BM25/local distributional source retrieval (NOT Product Vector/LLM)
     -> rights/TTL/document-sha/byte-span revalidation
  3. subprocess tools/m27_h02_native_source_verifier.py
     -> independent OS process reloads original A05 corpus + document, verifies exact source URI, byte range, release ID, document/excerpt SHA, literal text clause
  4. new local ThreadingHTTPServer, bound 127.0.0.1 only:
     -> independent Client start request
     -> two separate exact SOURCE clauses; neither is generated or an answer_text
     -> two per-claim nonce/SHA independent Client ACKs before Terminal
     -> request cancellation/revocation causes failclosed termination; journal append+fsync
  5. restart Journal returns INCOMPLETE_NO_REPLAY; no automatic previously published effect replay.

## Inherited source status, distinguishing presence from wiring

- F02: m27_b0_stream_experiment, m27_b1_online_stream_client, m27_b2_multiclaim_stream, m27_f02_reliability_stream exist but are NOT invoked by new consumer. Model/provider streaming NOT_RUN. Existing MiniMax FALLBACK_NONPROD cannot impersonate Cloudflare PRIMARY.
- F03: m27_f03_source_rights_admission IS used with real A05 source/rights.
- G01: m27_g01_qa_outcome.task_contract IS used; G01 synthetic Session and independent semantic Product verification NOT used.
- G02: inherited m27_b0_research_outcome durable local Research is NOT hooked into the current QA HTTP request. Historical Scoped G02 proof remains separate.
- G04: inherited m27_b0_revocation_contract/m27_b3_h02_cache_join is not invoked for Product caching. Current consumer cache OFF; remote revocation/restore not certified.
- G05: m27_g05_governed_cost source present, NOT used for invoice, tariffs or governed learning, always not verified.
- B3-05: m27_b3_h02_routing_successor, m27_b3_gateway_route_spec, m27_b3_provider_router retained, not imported by this new entry. No authenticated custom Gateway or live fallback.
- G03: allowed=false, no Action execution. H01 X01-X09 0/9; F04 signed Product image 0.

## Frozen source-candidate HTTP interface

ABI: m27.h02.native-a05-source-consumer/nonprod.v1
GET /nonprod/h02-native/status -> local recovery/hold status, never an admission grant.
POST /nonprod/h02-native/source-candidate -> exactly one JSON field question=PolicyEngine. Constructs a local TaskContract and reads real A05 source, returns exactly two distinct, source-excerpt clauses with claim_id, text, citation, sha256, nonce, process proof and model_generated=false; complete_answer=false. Arbitrary issuer/tenant/provider/client-added authority keys are rejected.
POST /nonprod/h02-native/ack -> exactly session_id, claim_id, challenge, text_sha256. Checks nonce, digest, source and epoch; no duplicate ACK.
POST /nonprod/h02-native/terminal -> exactly session_id. Requires current source and both ACKs before terminal. Returns LOCAL_SOURCE_TWO_CLAUSES_ACKED_NOT_PRODUCT.
POST /nonprod/h02-native/cancel -> exactly session_id, closes session with CANCELLED_NO_REPLAY.
Max JSON body 3072 bytes, Cache-Control no-store; invalid/revoked inputs failclosed with status 403/503 and PRODUCT_NOT_ADMITTED. No external network bind, production route, model call, remote credential or effect.

## F04 exact nondeploy handoff (current Nonprod entry, NOT Product build closure)

Required source files for this specific diagnostic entry:
  - src/knowledge_engine/m27_h02_native_nonprod_consumer.py
  - src/knowledge_engine/m27_g01_qa_outcome.py
  - src/knowledge_engine/m27_task_contracts_v1.py
  - src/knowledge_engine/m27_f03_source_rights_admission.py
  - tools/m27_h02_native_source_verifier.py
  - wave_b01/components/a05/adapter/a05_retrieval.py
  - wave_b01/components/a05/source/corpus.json
  - wave_b01/components/a05/source/release.json
  - wave_b01/components/a05/source/revocations.json
  - all 11 original A05 markdown documents named in the verified manifest
  - accessible Git B3-05 pinned objects, Git executable, provisioned private local fence, writeable nonprod fsync journal path.
Additional tests: tests/test_m27_h02_native_nonprod_consumer.py.
Any F04 14-source allowlist predating native consumer is insufficient. A Product image requires wholly separate full verified Product source/dependency/lock/context closure, licenses, SBOM, independent exact-current signer, IdP and H01 9/9, then H03 actual C28; this nonprod script MUST NOT be silently used as a Product image entry.

## Claims that are NOT being made

No true model-generated multi-claim same-request answer, no formal F02 first-answer-text PASS, no G01 Product QA, no authenticated native Product Client, no remote IdP/source grant, no original 523/blind200, no H03 current signed Product image, no REL01 certification or fresh Owner Production GO. Synthetic or local deterministic excerpts may never be upgraded to Product answer evidence.
