# 61 — M27 Test Page Product Evaluation: M27 vs Production M26

Final state: `M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`
Date: 2026-10-07 UTC
Workspace: `/home/ubuntu/LLM_Wiki-m27-test-page-eval`
Branch: `m27/test-page-m27-vs-production-eval`
Base HEAD: `d4cd99e936df544c45a2065e9dada0d8f40163d8`
Candidate proof reference HEAD: `f4c8692e9f7876dabd48626082cf2a8087459968`

This session evaluated the current `/test/answers`-equivalent product surface without deploying M27, activating canary, mutating a release pointer, changing public production routing, restarting/rebuilding M26, running admission/full523, running Stage13/14 or Chunk002, or tuning runtime answer behavior.

## Executive verdict

M27 remains architecturally more advanced than production M26, but the current test-page/product answer plane is not ready for canary consideration.

The blocker is concrete: the pinned M27 candidate HTTP container reports healthy `/v1/health` and `/v1/preflight`, but its real product stream endpoint `POST /v1/answers/stream` returns HTTP 503 with `M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE`. That is a correct fail-closed behavior, but it means no current `/test/answers` or owner-only equivalent product endpoint can produce M27 answers, citations, live semantic-quality payloads, p50/p95 answer latency, TTFT for material text, safe-terminal outputs, retrieval-hard behavior, or multilingual behavior.

Historical hard-gate evidence still says M27 is strong in isolated release evaluation: full523 `523/523`, cited final-answer `237/237`, safe-terminal `130/130`, isolated first-answer-text streaming PASS, p95 `2365.529 ms`, and independent semantic quality `91.222/100`. This session does not reverse those gates. It only says the current product/test-page integration evidence is insufficient.

## Required first-step inspection

| Surface | Finding |
| --- | --- |
| Production 8080 health | `ok=true`, build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd`, entrypoint `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`. |
| Test backend 8081 health | `status=ok`, build SHA `f746822503b7b27b2f5d4bb98ad406b15f558732`, same M26 entrypoint. |
| `/test/answers` implementation | Nginx maps `/test/answers` to `127.0.0.1:8081/v1/answers`; direct backend `http://127.0.0.1:8081/test/answers` is `404`. This is an API test route, not a native UI page in the backend. |
| M27 candidate | Pinned candidate image `sha256:3a5ac320208a2bba5560009aaa78016dfdd4d41fcf5a6c650d5e8ebf79a9342c`; launched only as local owner-only test container on `127.0.0.1:18080`, label `com.daniel.m27.eval=true`, no production mounts or credentials. |
| Safe side-by-side hosting | Current `/test/answers` can compare M26 test backend. It cannot yet host M27 because the candidate stream endpoint lacks an injected isolated executor. A local owner-only test-page-equivalent probe was used instead. |
| Owner-only/public boundary | No public routing was modified. The candidate was only bound to localhost `127.0.0.1:18080` during the probe. |

## Product metric comparison

Current product/test-page-equivalent evidence:

| Metric | M26 test backend path | M27 candidate path | Verdict |
| --- | ---: | ---: | --- |
| Health endpoint | PASS, `200` | PASS, `200` | Tie on health. |
| Preflight | M26 health only, test backend ready | PASS, `200`, `answer_execution_authorized=false` | M27 preflight intentionally does not authorize answers. |
| Answer endpoint availability | PASS on `127.0.0.1:8081/v1/answers` | FAIL, `503 M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE` on `127.0.0.1:18080/v1/answers/stream` | M26 wins product availability. |
| Observed answer runs | 2 one-question probes on `What is safe?` | 1 stream probe, 0 answers | M27 cannot be scored. |
| TTFT / first byte | `1086.8 ms` first run; `74.86 ms` second run | unavailable because HTTP 503 | M27 product TTFT not measurable. |
| Final latency | `10697.76 ms` first run; `1901.91 ms` second run | unavailable because HTTP 503 | M27 product p50/p95 not measurable. |
| First material/final answer event | second run: `answer.completed` at `1894.59 ms`; publication completed at `1843.86 ms` | unavailable because HTTP 503 | M27 product streaming not proven. |
| Citation/provenance | M26 second probe reached `owner_only_cited_answer` publication and `answer.completed` with citation keys present | unavailable | M27 no product evidence. |
| Safe-terminal correctness | not sampled live in product route this session | unavailable | no product comparison. |
| Retrieval-hard | not sampled live because M27 answer plane unavailable | unavailable | no product comparison. |
| Multilingual | not sampled live because M27 answer plane unavailable | unavailable | no product comparison. |
| Error / timeout / 429 | M26 observed answer probes succeeded, no 429 | M27 answer probe failed with 503 | M27 product blocker. |

The larger 20-case or 100-case product set was deliberately not run because the M27 candidate product answer endpoint fails closed before answering. Running more cases would only repeat the same 503 and consume M26 test-page quota without creating a valid side-by-side comparison.

## Semantic quality comparison

Side-by-side semantic quality is **not available** and must fail closed.

M27 historical isolated quality remains `91.222/100` from `ANSWER_QUALITY_RUBRIC_v1` over 9 stored verified-answer semantic payloads. That evidence is valid for release hard-gate redecision, but it is not a live `/test/answers` product comparison.

Because current M27 product endpoint returns 503 and produces no answer payload, there is no real M27 product answer to score, no pairwise M26-vs-M27 winner, and no per-case product quality score. Therefore M27 cannot be declared better than production M26 on product quality in this session.

## Latency and streaming comparison

M26 test backend emits SSE progress and reaches `answer.completed`. The second observed run had `ttfb_ms=74.86`, `latency_ms=1901.91`, 9 SSE events, publication `owner_only_cited_answer`, and final `answer.completed`.

M27 candidate health and preflight are fast and green, but the answer stream endpoint returns:

```json
{
  "detail": {
    "code": "M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE",
    "schema_version": "m27-isolated-first-answer-stream/v1",
    "production_touched": false
  }
}
```

That is safe, but not product-ready streaming. It means p50, p95, max latency, TTFT to material answer text, final-answer parity, and streaming regression cases are all unavailable for the current product path.

## Citation, safe-terminal, retrieval-hard and multilingual non-regression

No non-regression claim can be made for current `/test/answers` product behavior, because M27 did not answer. The isolated hard-gate evidence supports citation/provenance and safe-terminal correctness, but the product surface has not been wired to the answer executor. Retrieval-hard and multilingual product behavior remain untested in this session.

## Cost and complexity signals

Current product path evidence is limited:

- M26 test backend produced normal SSE answer traffic.
- M27 candidate health reports `provider_calls=0` and `smoke_questions_sent=0`.
- M27 candidate stream probe fails before provider/tool/retrieval execution, so provider calls, tool calls, continuation rounds, context/evidence size, adaptive tier distribution, route/tool/memory usage and product answer telemetry are unavailable.

## UX / product surface

The existing backend test route is an API route through Nginx, not a standalone rendered UI page in the backend. Direct `8081/test/answers` returns 404; Nginx maps `/test/answers` to `8081/v1/answers`. No UI instrumentation was installed. Therefore this session cannot evaluate visual UI behavior such as suggestion chips, citation rendering in the browser, or answer text appearing earlier in the web page. No existing production UI was modified.

## Architecture audit

Architecture verdict: `M27_ARCHITECTURE_ADVANCED_BUT_PRODUCT_RISK_REMAINS`.

### Why M27 is architecturally ahead

M27 has a cleaner context-native decomposition than current production M26. It separates context/evidence boundaries, decision trace, adaptive compute, read-only tool/MCP contracts, governed memory, isolated production-equivalent runtime, release hard gates, independent semantic quality scoring, and verified first-answer-text streaming adapters. This aligns better with 2026–2027 agent-runtime expectations around context engineering, auditable tool use, memory governance, traceability, bounded compute and controlled deployment.

M26 production remains a more monolithic production answer path with progress SSE and terminal `answer.completed`, anchored in `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`. It is currently more product-integrated and available, but less cleanly decomposed.

### Why product risk remains

The current M27 candidate HTTP app exposes health/preflight but has no injected product stream executor in the container. The real endpoint correctly refuses to pretend by returning 503. Until this is wired in an owner-only test surface with production-safe evidence access, M27 architecture superiority cannot translate into a product canary decision.

## Decision

`M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`

Reasons:

1. M27 did not produce any answer on the current product/test-page-equivalent endpoint.
2. Live side-by-side semantic quality is unavailable and fails closed.
3. Live M27 answer latency, p50/p95 and TTFT to material text are unavailable.
4. Citation/provenance, safe-terminal, retrieval-hard and multilingual product non-regression are unavailable.
5. Architecture is advanced, but product integration remains incomplete.

## Safety / no-change proof

This session did not deploy M27, activate canary, mutate the release pointer, restart/rebuild production M26, route public traffic to M27, run admission/full523/Stage13/14/Chunk002, tune runtime answer behavior, or write production R2/Qdrant/SQLite.

A local candidate container was launched only for evaluation on `127.0.0.1:18080` with label `com.daniel.m27.eval=true`, then removed after evidence capture. Production 8080 health remained M26 with build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd` during evidence capture.

## Generated artifacts

- `docs/m27/research/61_test_page_m27_vs_production_eval_report.md`
- `docs/m27/research/test_page_m27_vs_production_eval_receipts.json`
- `docs/m27/handoffs/TEST_PAGE_EVAL_TO_CANARY_DECISION_HANDOFF.md`
- `scripts/m27_test_page_compare.py`
- `tests/test_m27_test_page_eval.py`

## Next recommended action

Do not proceed to canary consideration from this evidence. Next, wire an owner-only test-page-equivalent M27 answer executor behind a local/authenticated test surface, preserving production datastore read-only boundaries and public-route zero. Then run a bounded 20-case side-by-side product comparison with captured answer payloads, independent semantic scoring, p50/p95/TTFT, citation/provenance, safe-terminal, retrieval-hard and multilingual slices. Only after that should canary readiness be reconsidered.
