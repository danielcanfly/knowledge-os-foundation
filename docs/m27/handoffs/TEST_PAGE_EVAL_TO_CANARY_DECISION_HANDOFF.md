# M27 Test Page Eval to Canary Decision Handoff

Final state: `M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`

Workspace: `/home/ubuntu/LLM_Wiki-m27-test-page-eval`
Branch: `m27/test-page-m27-vs-production-eval`
Base HEAD: `d4cd99e936df544c45a2065e9dada0d8f40163d8`
Candidate proof HEAD referenced: `f4c8692e9f7876dabd48626082cf2a8087459968`

## What was evaluated

A local owner-only test-page-equivalent comparison was used because the current backend does not expose a direct `/test/answers` UI route. Nginx maps `/test/answers` to the M26 test backend at `127.0.0.1:8081/v1/answers`; direct `127.0.0.1:8081/test/answers` returns 404.

M26 test backend answers on `127.0.0.1:8081/v1/answers`. Two one-question probes succeeded and produced SSE ending in `answer.completed`.

M27 candidate image `sha256:3a5ac320208a2bba5560009aaa78016dfdd4d41fcf5a6c650d5e8ebf79a9342c` was launched only as a local eval container on `127.0.0.1:18080`, with eval labels and no production mounts/credentials. Its `/v1/health` and `/v1/preflight` passed, but `POST /v1/answers/stream` returned HTTP 503 `M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE`.

## Decision boundary

Do not proceed to canary consideration from this evidence. Historical M27 hard gates remain `M27_RELEASE_HARD_GATES_READY`, but product/test-page answer-plane evidence is incomplete.

## Next closure gates

1. Wire a real isolated M27 stream executor into an owner-only test-page-equivalent surface.
2. Keep public production routing unchanged and default to zero public traffic.
3. Prove candidate has no production R2/Qdrant/SQLite write path.
4. Run a bounded 20-case side-by-side set covering cited answer, multilingual, retrieval-hard/source-locator drift, safe terminal, deadline/budget pressure and streaming.
5. Capture answer payloads and run independent `ANSWER_QUALITY_RUBRIC_v1` scoring on the side-by-side product outputs.
6. Measure p50, p95, max latency, TTFT to material answer text, first material event before final event, final parity, citation/provenance, safe-terminal correctness, provider/tool/route telemetry and product UX behavior.
7. Recheck production 8080 health/build/entrypoint, owned eval containers, port 18080 and release pointer no-change after the run.

## Forbidden until a new explicit session authorizes it

No production deploy, no canary activation, no release pointer mutation, no production restart/rebuild, no public route to M27, no production R2/Qdrant/SQLite writes, no admission/full523 rerun, no Stage13/14, no Chunk002, and no runtime answer-behavior tuning to win the comparison.

Evidence:
- `docs/m27/research/61_test_page_m27_vs_production_eval_report.md`
- `docs/m27/research/test_page_m27_vs_production_eval_receipts.json`
- `scripts/m27_test_page_compare.py`
- `tests/test_m27_test_page_eval.py`
