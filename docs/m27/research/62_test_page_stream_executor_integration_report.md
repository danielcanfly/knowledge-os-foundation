# 62 Test Page Stream Executor Integration Report

## Final state

`M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`

Workspace: `/home/ubuntu/LLM_Wiki-m27-test-page-stream-executor-integration`  
Branch: `m27/test-page-stream-executor-integration`  
Base HEAD: `b8163db71158999bc72547e1e98618b941ee456a`  
Current HEAD at report generation: `3e1a490ec70a59ae6a17221b12d3b23d51c55a59`

## Scope decision

This session stayed inside the owner-only `/test/answers` product-surface evaluation lane. It did not deploy M27 to production, activate canary, mutate release pointers, change public Nginx routing, restart or rebuild production M26, write production R2/Qdrant/SQLite, rerun admission/full523, or run Stage13/14/Chunk002.

## What changed

The previous blocker was `POST /v1/answers/stream` returning HTTP 503 `M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE` on the candidate product surface. The integration repair wires the owner-only factory path:

- default isolated app remains fail-closed without an executor;
- `knowledge_engine.m27_isolated_http:create_test_page_app` constructs an app with a real `build_owner_only_stream_executor()`;
- the executor uses a read-only production-bundle snapshot plus live provider access, without R2/Qdrant/SQLite env keys in the candidate;
- the Docker image packaging bug for `pilot/m26/m26-3-context-policy.json` was repaired so the factory can start inside `/app`.

The candidate stream endpoint is now available: health and preflight returned HTTP 200, and stream smoke returned real SSE rather than 503.

## Candidate-only stream smoke

| Probe | HTTP | Event sequence | Terminal | Latency |
|---|---:|---|---|---:|
| safe terminal | 200 | request_started → safe_abstention_done | PROMPT_INJECTION_OR_PRIVACY_RISK | 95.955 ms |
| ordinary answer | 200 | request_started → retrieval_started → retrieval_ready → safe_abstention_done | VERIFIER_GAP_SAFE_TERMINAL | 22086.667 ms |

The ordinary smoke entered retrieval and produced a safe terminal rather than a cited answer. Follow-up probes found cited-answer paths, so the executor exists, but readiness remains mixed.

## M27 answer probes

M27 probe summary:

- cases: `10`
- HTTP success: `10/10`
- cited answers: `4/10`
- safe terminals: `6/10`
- p50 latency: `11998.317` ms
- p95 latency: `13921.396` ms
- p50 TTFB: `2.0505` ms
- p95 TTFB: `86.274` ms

The probe set produced real verified streaming sequences on 4 cases, including cited material events before final completion. Six cases still ended as `VERIFIER_GAP_SAFE_TERMINAL`, so product answer success is not strong enough to claim readiness.

## Bounded product comparison

The side-by-side comparison could not complete. The M26 test backend returned HTTP 429 `DAILY_IP_LIMIT_EXCEEDED` on the first comparison case, so only one attempted comparison row exists and the required 20-case product comparison is not satisfied.

| System | HTTP success | cited answers | safe terminals | p50 latency | p95 latency | p50 TTFB | p95 TTFB |
|---|---:|---:|---:|---:|---:|---:|---:|
| M26 test backend | 6 | 4 | 1 | 1948.271 | 14359.096 | 20.909 | 167.886 |
| M27 candidate | 8 | 4 | 4 | 13590.266500000002 | 28629.028 | 5.866 | 146.385 |

Because M26 baseline outputs were unavailable, no success-rate, product-quality, pairwise-quality, or latency superiority claim is valid.

## Quality summary

Independent semantic scoring did not run. The required live product quality comparison is therefore unavailable. Historical release-gate quality evidence remains separate and was not substituted as a product quality score.

Qualitative caution: one M27 cited output in the probe set answered that the cited passage did not define the requested Browser Use behavior. That is a live product-output quality warning and requires review before canary consideration.

## Architecture audit

M27 still has the stronger architecture on paper: context/evidence boundary, decision trace, adaptive compute, tool/MCP governance, memory governance, verified streaming design, and isolated owner-only testability are cleaner than M26. The integration also improved deployability by providing an owner-only app factory and preserving fail-closed default behavior.

Product readiness is different from architecture quality. The product surface is now callable, but product comparison and quality evidence are insufficient.

Verdict:

- architecture quality: favorable to M27;
- product readiness: not ready;
- canary readiness: not ready for canary consideration.

## Production no-change proof

- production health after cleanup: OK
- production build SHA after cleanup: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint after cleanup: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- Nginx checksum after: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2  /etc/nginx/nginx.conf`
- owned M27 eval containers after cleanup: none
- port 18080 after cleanup: no listener

No deploy, canary activation, release pointer mutation, production restart/rebuild, public route mutation, production datastore writes, admission/full523 rerun, Stage13/14, or Chunk002 occurred.

## Remaining blockers

1. M26 baseline product comparison could not run because the M26 test backend returned HTTP 429 daily limit.
2. The required 20-case side-by-side product comparison did not complete.
3. Independent semantic scoring did not run, so product quality superiority is unproven.
4. M27 probe cited-answer rate was only 4/10, with 6/10 verifier-gap safe terminals.
5. At least one live M27 cited output needs quality review before any canary decision.

## Generated files

- `docs/m27/research/62_test_page_stream_executor_integration_report.md`
- `docs/m27/research/test_page_stream_executor_integration_receipts.json`
- `docs/m27/handoffs/TEST_PAGE_STREAM_EXECUTOR_TO_CANARY_DECISION_HANDOFF.md`
- `src/knowledge_engine/m27_test_page_executor.py`
- `src/knowledge_engine/m27_isolated_http.py`
- `tests/test_m27_test_page_stream_executor_integration.py`
