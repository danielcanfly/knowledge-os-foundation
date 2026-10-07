# M27 Provider Tail Product Answer Repair Report

Final state: `M27_PROVIDER_TAIL_REPAIR_BLOCKED`.

## Scope
Stage 21 repaired only product-readiness issues for provider tail, publication timing, verifier-gap safe terminals, multilingual coverage, Browser Use warning latency/citation quality, and Owner 85-point gate evidence. No canary activation, production deploy, release pointer mutation, admission/full523 rerun, Stage13/14, or Chunk002 was performed.

## Per-case diagnosis source
Diagnosis was reconstructed from Stage 19R and Stage 20 receipts. Stage 20 remained not product-ready: cited-answer rate 65.0%, safe-terminal rate 35.0%, p50 final latency about 14.98s, p95 final latency about 50.72s, and known provider tails on C12/C15/C16 plus thin cited surfaces.

## Stage 20 per-case diagnosis
|Case|Slice|Stage20 M27|Diagnosis|
|---|---|---|---|
|C01|browser_use_warning|CITED, 19380.184ms, c3, len872|provider_tail_latency, browser_use_warning_case_not_product_ready|
|C02|ordinary_cited|CITED, 10130.294ms, c1, len821|ok_in_stage20|
|C03|ordinary_cited|SAFE, 8842.818ms, c0, len0|verifier_gap_false_safe_candidate|
|C04|ordinary_cited|CITED, 15757.046ms, c1, len96|provider_tail_latency, thin_answer_surface|
|C05|ordinary_cited|SAFE, 14172.117ms, c0, len0|verifier_gap_false_safe_candidate|
|C06|ordinary_cited|CITED, 16771.378ms, c1, len136|provider_tail_latency, thin_answer_surface|
|C07|multilingual|CITED, 11920.735ms, c3, len887|ok_in_stage20|
|C08|ordinary_cited|CITED, 8024.585ms, c2, len949|ok_in_stage20|
|C09|ordinary_cited|CITED, 7577.083ms, c3, len1034|ok_in_stage20|
|C10|ordinary_cited|CITED, 31566.75ms, c1, len182|provider_tail_latency, thin_answer_surface|
|C11|ordinary_cited|CITED, 23258.059ms, c1, len193|provider_tail_latency, thin_answer_surface|
|C12|ordinary_cited|SAFE, 50723.779ms, c0, len0|provider_tail_latency, verifier_gap_false_safe_candidate|
|C13|ordinary_cited|CITED, 12401.897ms, c3, len1166|ok_in_stage20|
|C14|ordinary_cited|CITED, 8443.985ms, c1, len1019|ok_in_stage20|
|C15|multilingual|SAFE, 27379.01ms, c0, len0|provider_tail_latency, multilingual_coverage_gap|
|C16|multilingual|SAFE, 16088.114ms, c0, len0|provider_tail_latency, multilingual_coverage_gap|
|C17|retrieval_hard|CITED, 14199.535ms, c3, len1355|ok_in_stage20|
|C18|retrieval_hard|SAFE, 22518.249ms, c0, len0|provider_tail_latency, verifier_gap_false_safe_candidate|
|C19|safe_terminal|SAFE, 15.059ms, c0, len0|ok_in_stage20|
|C20|safe_terminal|CITED, 22702.922ms, c6, len216|provider_tail_latency, thin_answer_surface|

## Repair attempted
- Added a deterministic, evidence-bound product surface candidate before provider fallback.
- Preserved canonical verification: candidates that do not pass material-claim support and citation locator checks remain safe terminals.
- Added fail-closed missing-provider handling so absent provider credentials do not publish a stream `error`; they terminally safe-abstain instead.

## Validation result
- Docker image build: PASS.
- Isolated candidate health on `127.0.0.1:18080`: PASS during probe.
- Current bounded provider-valid 20-case rerun: BLOCKED.
- Without a provider credential, the candidate cannot exercise provider-tail paths; before the fail-closed patch this produced stream `error` events.
- Passing the full historical env file into the isolated candidate brought production datastore/Qdrant configuration into the candidate and triggered `PA7_QDRANT_COLLECTION_MISMATCH`; this path was rejected as an isolation violation.
- No provider-only env artifact was committed or printed.

## Owner 85-point scoring artifact
Current-candidate Owner 85 scoring is `NOT_SCORABLE_FOR_CURRENT_CANDIDATE` because the bounded provider-valid rerun was blocked. Stage 20 historical quality remains diagnostic only and was not reused as the current gate.

## Safety proof
- `production_touched`: `False`
- `canary_activation`: `False`
- `production_deploy`: `False`
- `release_pointer_mutation`: `False`
- `admission_full523_rerun`: `False`
- `stage13_14_or_chunk002`: `False`
- `active_eval_containers_after_cleanup`: `[]`
- `port_18080_after_cleanup`: `FREE`
- `owner_bypass_mode`: `600`
- `production_8080_health_excerpt`: `{"schema_version":"danielcanfly-answers-health/v1","ok":true,"status":"ok","request_id":"req_977040c9c96848f0b41a02f2e593f99a","answers_url":"/v1/answers","backend":{"build_sha":"7d4b2358464654bf3de7d9561ec89de841d279bd","entrypoint":"knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query"},"limits":{"per_ip_daily":15,"burst_per_minute":10,"active_per_ip":1,"global_active":3,"global_daily":300,"minimax_fallback_daily":50,"heartbeat_seconds":10,"hard_deadline_seconds":90,"owner_bypass_configured":1},"preload":{"answer_bundle_preloaded":true,"answer_bundle_preload_error":""}}`
- `m26_test_backend_8081_health_excerpt`: `{"schema_version":"danielcanfly-answers-health/v1","status":"ok","request_id":"req_d63a914b5a354ff1b52bd76a80b86633","answers_url":"/v1/answers","backend":{"build_sha":"f746822503b7b27b2f5d4bb98ad406b15f558732","entrypoint":"knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query"},"limits":{"per_ip_daily":10,"burst_per_minute":10,"active_per_ip":1,"global_active":3,"global_daily":50,"minimax_fallback_daily":10,"heartbeat_seconds":10,"hard_deadline_seconds":90,"owner_bypass_configured":1},"preload":{"answer_bundle_preloaded":true,"answer_bundle_preload_error":""}}`
- `nginx_site_checksum_current`: `1d1c4edfddca4da6c89a054a0ddf33179bbe3265e21666f2e8a49a1606045219  /etc/nginx/sites-enabled/llamaindex-demo`
- `nginx_aggregate_checksum_current`: `bc8e2bed4197b16b4d01adcfef102f95bcc80ab9b1acddd61cb73fe56616c5c3  -`

## Decision
`M27_PROVIDER_TAIL_REPAIR_BLOCKED`
