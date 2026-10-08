# Stage 30N Hot-patch Provenance Runtime Verification

## Final decision
`M27_DIRECT100_TARGETED_GUARD_RERUN_PASS`

## What changed
A tool-safety-compliant hot-patch path was used instead of container re-creation or provider-config migration. No env files, provider secrets, owner credentials, docker env inspection, Nginx, production M26, test backend, release pointer, production datastore, public owner-gated route, full523, Stage13/14, or Chunk002 were touched.

The active isolated candidate container remained `m27-owner-canary-28` on `127.0.0.1:18080`. Runtime code was patched in-place for the isolated candidate only:

- `src/knowledge_engine/m27_provenance_obligations.py`
- `src/knowledge_engine/m27_test_page_executor.py`

## Root cause closed
Stage 30K code located provenance evidence offline, but runtime lookup used a package-relative root that did not resolve inside the container. The hot-patch added a `/app/pilot/m24/canonical-release` fallback and a narrow provenance identity answer path for explicit `retrieved-at` / `source-commit` / `release` questions.

This path only applies to canonical provenance identity obligations. It does not relax the general question-obligation guard, semantic publication gate, or thin-answer checks.

## Verification

### Targeted8 provenance rerun
- cases: 8
- HTTP success: 8/8
- answerable cited final: 8/8
- false safe terminal: 0
- thin cited answer: 0
- topic contamination: 0
- semantic bad publish: 0
- p95 final latency: 104.498 ms

### Regression9 rerun
- cases: 9
- HTTP success: 9/9
- expected safe correct: 8/8
- answerable cited final: 1/1
- missed safe terminal: 0
- false safe terminal: 0
- thin cited answer: 0
- topic contamination: 0
- semantic bad publish: 0
- p95 final latency: 7067.703 ms

### Direct100 rerun
- cases: 100
- HTTP success: 100/100
- answerable cases: 87
- answerable cited final: 87/87
- expected safe cases: 13
- expected safe correct: 13/13
- missed safe terminal: 0
- false safe terminal: 0
- empty nonterminal: 0
- thin cited answer: 0
- topic contamination: 0
- semantic bad publish: 0
- obligation satisfied: 100/100
- p50 final latency: 3493.877 ms
- p95 final latency: 7735.191 ms
- p50 first-material latency: 3492.613 ms
- p95 first-material latency: 7734.305 ms
- first-material count: 100
- M26 mature composer delegation: 0

## Artifacts
- `docs/m27/research/94_hotpatch_targeted8_results_v2.json`
- `docs/m27/research/94_hotpatch_regression9_results.json`
- `docs/m27/research/94_hotpatch_direct100_results.json`
- `docs/m27/research/94_hotpatch_direct100_summary.json`
- `docs/m27/research/94_m27_hotpatch_provenance_direct100_pass_report.md`
- `docs/m27/handoffs/M27_HOTPATCH_PROVENANCE_DIRECT100_PASS_HANDOFF.md`

## Boundary
This is direct isolated candidate verification only. Owner-only route certification remains pending and must not be inferred from this result.
