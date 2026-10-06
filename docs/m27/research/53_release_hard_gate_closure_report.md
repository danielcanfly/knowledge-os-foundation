# M27 Release Hard-Gate Closure Report

Status: `M27_RELEASE_HARD_GATES_NOT_READY_WITH_DIAGNOSIS`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-release-hard-gate-closure`
Branch: `m27/release-hard-gate-closure`
Base: `f406be4a07ae360655e073c4dea1e13fe2796689`

## Scope

This session handled only the two release hard-gate gaps left after `M27_RELEASE_CANDIDATE_READY`:

1. independent quality score unavailable
2. first-answer-text streaming not yet supported/proven by the isolated preflight endpoint

No admission rerun, runtime benchmark repair, Stage13/14 legacy admission, Chunk002, production deploy, canary activation, release pointer mutation, production restart, production rebuild, production R2/Qdrant/SQLite write, or benchmark-case tuning was performed.

## Required source review summary

Before changing code, the session reviewed the admission report, release handoff, admission receipts, admission metric contract, existing release quality gate, semantic answer-quality evaluator, M26 verified streaming implementation, M27 isolated HTTP surface, M27 executable runtime, and focused tests for quality, streaming, admission metrics, isolated harness, and Wave-D integration.

The important findings were:

- The accepted admission receipts preserve full523 `523 / 523` PASS, cited final-answer rate `100%` (`237 / 237`), safe-terminal correctness `100%` (`130 / 130`), citation/provenance integrity `100%`, and production no-mutation proof.
- The deterministic admission harness explicitly has `quality_score: null` and a quality note saying no independent quality scorer exists in that harness.
- The isolated HTTP surface previously exposed only `/v1/health` and `/v1/preflight`; there was no isolated first-answer-text stream route.
- M26 verified streaming already had a safe pattern: runtime progress events may stream early, material answer text only streams after verified/cited final state, safe terminals emit no material text, and final-answer parity is preserved.

## Gate A: independent quality score

Result: `BLOCKING / NOT READY`.

Implemented `src/knowledge_engine/m27_release_hard_gates.py` with a fail-closed quality hard gate. The gate distinguishes deterministic admission correctness from independent semantic quality scoring and refuses to convert `523 / 523` deterministic pass into `quality_score >= 85`.

Current quality result:

- `passed`: false
- `release_blocking`: true
- reason codes:
  - `QUALITY_SCORER_UNAVAILABLE`
  - `MISSING_EVALUATOR_IDENTITY`
  - `MISSING_RUBRIC_VERSION`
- deterministic admission result preserved: yes
- report-only release candidate preserved: yes

This is the correct fail-closed behavior because no independent evaluator identity, rubric version, or score artifact is available in the accepted admission receipts.

## Gate B: first-answer-text streaming

Result: `PROVEN FOR ISOLATED M27 HTTP SURFACE`.

Implemented isolated, non-production SSE support:

- `src/knowledge_engine/m27_isolated_streaming.py`
- `src/knowledge_engine/m27_isolated_http.py` now exposes `POST /v1/answers/stream`
- stream schema: `m27-isolated-first-answer-stream/v1`

Required properties covered:

- the endpoint is isolated/non-production and requires an injected isolated executor
- without that executor, it fails closed with `M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE`
- no production M26 endpoint behavior is changed
- material text emits only from verified/cited final state
- safe terminals emit `safe_abstention_done` and no material answer text
- unverified answers emit an error and no material answer text
- first material event occurs before `final_answer_done`
- cited segment text preserves final-answer parity
- disconnect stops before material/final events
- queue is bounded at 128 to avoid unbounded backpressure

Streaming gate artifact result:

- `passed`: true
- event sequence proved:
  - `request_started`
  - `verified_claim_ready`
  - `cited_segment_ready`
  - `final_answer_done`
- first material event index: before final completion
- final-answer parity: checked
- production touched: false

## Combined hard-gate decision

Combined result: `M27_RELEASE_HARD_GATES_NOT_READY_WITH_DIAGNOSIS`.

The release candidate remains valid for report-only planning, but production deployment readiness remains blocked because independent quality scoring is still unavailable.

Remaining blockers:

- `QUALITY_SCORER_UNAVAILABLE`
- `MISSING_EVALUATOR_IDENTITY`
- `MISSING_RUBRIC_VERSION`

Non-blocking closed item:

- first-answer-text streaming is now supported and proven for the isolated M27 path.

## Artifacts created

- `src/knowledge_engine/m27_release_hard_gates.py`
- `src/knowledge_engine/m27_isolated_streaming.py`
- `tests/test_m27_release_hard_gates.py`
- `tests/test_m27_isolated_streaming.py`
- `docs/m27/research/release_hard_gate_receipts.json`
- `docs/m27/research/53_release_hard_gate_closure_report.md`
- `docs/m27/handoffs/RELEASE_HARD_GATES_TO_CANARY_HANDOFF.md`

Modified:

- `src/knowledge_engine/m27_isolated_http.py`

## Validation

Focused tests:

```text
PYTHONPATH=src:tests /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/pytest -q \
  tests/test_m27_release_hard_gates.py \
  tests/test_m27_isolated_streaming.py \
  tests/test_m27_admission_metric_contract.py \
  tests/test_m27_smoke_preflight_repair.py \
  tests/test_m27_isolated_admission_harness.py \
  tests/test_m27_wave_d_integration.py \
  tests/test_release_quality_gate.py \
  tests/test_m26_verified_streaming.py

62 passed, 1 warning in 3.31s
```

Compile / diff / lint:

```text
PYTHONPATH=src:tests /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m compileall -q src/knowledge_engine tests

git diff --check

/home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/ruff check \
  src/knowledge_engine/m27_isolated_http.py \
  src/knowledge_engine/m27_isolated_streaming.py \
  src/knowledge_engine/m27_release_hard_gates.py \
  tests/test_m27_isolated_streaming.py \
  tests/test_m27_release_hard_gates.py

All checks passed!
```

Environment / cleanup proof:

- owned M27 eval containers after session: `0`
- port 18080 listeners after session: `0`
- production containers observed read-only: `llm_wiki-knowledge-engine-1`, `knowledge-engine-test-answers`
- production `/v1/health` read-only returned `ok: true` and build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd` in the checked response snippet
- production touched: `NO`
- deployment performed: `NO`

## Final decision

`M27_RELEASE_HARD_GATES_NOT_READY_WITH_DIAGNOSIS`

The only remaining gap is independent quality scoring. The isolated M27 first-answer-text streaming gate is closed.
