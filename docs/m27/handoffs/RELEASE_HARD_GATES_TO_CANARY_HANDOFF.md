# M27 Release Hard Gates to Canary Handoff

Status: `M27_RELEASE_HARD_GATES_NOT_READY_WITH_DIAGNOSIS`

Workspace: `/home/ubuntu/LLM_Wiki-m27-release-hard-gate-closure`
Branch: `m27/release-hard-gate-closure`
Base: `f406be4a07ae360655e073c4dea1e13fe2796689`

## Decision

Do not proceed to canary or production deployment yet.

The accepted full523 admission result is preserved and remains valid as report-only release-candidate evidence, but production deployment readiness is still blocked by the quality hard gate.

## Gate status

### Full523 admission evidence

- full523: PASS, `523 / 523`
- cited final-answer rate: `100%`, `237 / 237`
- safe-terminal correctness: `100%`, `130 / 130`
- citation/provenance integrity: `100%`
- p95 latency: `2365.529 ms`
- production touched: NO

### Independent quality score

Status: `BLOCKING`

Reason codes:

- `QUALITY_SCORER_UNAVAILABLE`
- `MISSING_EVALUATOR_IDENTITY`
- `MISSING_RUBRIC_VERSION`

The release gate now explicitly fails closed rather than treating deterministic admission success as a semantic quality score.

### First-answer-text streaming

Status: `READY_FOR_ISOLATED_M27_PATH`

Implemented and proven:

- isolated endpoint: `POST /v1/answers/stream`
- schema: `m27-isolated-first-answer-stream/v1`
- first material event emitted before `final_answer_done`
- material text requires verified/cited final state
- safe terminals emit no material answer text
- disconnect/backpressure bounded
- final-answer parity preserved
- no production endpoint behavior changed

## Required next action before canary

Provide or wire an independent semantic quality scorer for release hard-gate use. The scorer must produce:

- evaluator identity
- rubric/version
- score artifact identity
- score `>= 85`
- stale-artifact protection
- explicit failure on missing/invalid receipts, failed citation/provenance, failed safe-terminal correctness, or production mutation evidence

After that, run the release hard-gate decision again. Only if quality scoring passes and the existing streaming gate remains valid should the next session consider canary planning.

## Do not do yet

- do not deploy
- do not activate canary
- do not mutate release pointers
- do not restart/rebuild production
- do not write production R2/Qdrant/SQLite
- do not rerun full523 unless separately authorized

## Artifacts

- report: `docs/m27/research/53_release_hard_gate_closure_report.md`
- receipts: `docs/m27/research/release_hard_gate_receipts.json`
- quality/combined gate module: `src/knowledge_engine/m27_release_hard_gates.py`
- isolated streaming module: `src/knowledge_engine/m27_isolated_streaming.py`
- isolated endpoint: `src/knowledge_engine/m27_isolated_http.py`
- tests: `tests/test_m27_release_hard_gates.py`, `tests/test_m27_isolated_streaming.py`

`M27_RELEASE_HARD_GATES_NOT_READY_WITH_DIAGNOSIS`
