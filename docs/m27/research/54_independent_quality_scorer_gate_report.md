# M27 Independent Quality Scorer Gate Report

## Decision

`M27_INDEPENDENT_QUALITY_GATE_NOT_READY_WITH_DIAGNOSIS`

The independent semantic quality hard gate remains fail-closed. No valid semantic quality score can be computed from the accepted full523 receipts in this session without violating scope.

## Canonical inputs

- Release candidate HEAD: `f406be4a07ae360655e073c4dea1e13fe2796689`
- Release hard-gate HEAD: `e864417c2380f2ce8d6c24576fb129c37b95ccad`
- Accepted admission receipts: `/home/ubuntu/LLM_Wiki-m27-admission-release-rerun/docs/m27/research/admission_ladder_receipts.json`
- Accepted admission receipts SHA-256: `e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137`
- Prior streaming gate: PASSED for the isolated M27 first-answer-text path and carried forward unchanged.
- Production touched: NO.

## Independent scorer availability

A real semantic evaluator contract exists in `src/knowledge_engine/qa_answer_quality_evaluator.py`:

- adapter: `ProviderAnswerQualityEvaluator`
- semantic evaluator contract version: `aq-semantic-evaluator/v3`
- provider seam used by the existing QA integration: MiniMax
- rubric: `ANSWER_QUALITY_RUBRIC_v1`
- threshold: `>=85`

However, the current oracle-vm session does not have the evaluator credential configured. No evaluator call was made.

The accepted full523 receipts contain 237 rows whose expectation is `verified_cited_answer`, but zero of those rows retain `answer_text`, `answer`, `citations`, or `selected_evidence`. Therefore the accepted receipts are not sufficient input for a semantic judge. Re-running answer generation or full523 to recreate payloads is forbidden by this session scope, so the gate must remain fail-closed.

## Rubric audit

An older owner artifact named `問題評分標準.md` was found under the historical `LLM_Wiki-f746-quality-gate-20260930` fixture tree. It is a **Suggested Questions / homepage curation** rubric with dimensions such as homepage fit, question framing, corpus representativeness, topic balance, and non-duplication. Those dimensions are explicitly forbidden by the current Answer Quality semantic contract, so that document was inspected but was not reused as the M27 runtime semantic quality rubric.

The compatible in-repo semantic rubric is `ANSWER_QUALITY_RUBRIC_v1`, with seven server-owned dimensions totaling 100 points: directness/intent, correctness/grounding, evidence coverage, completeness/facets, citation support, hallucination control, and abstention appropriateness.

## Scoring policy

Scoring policy version: `m27-independent-quality-scoring-policy/v1`.

Preferred scope is all 237 verified-answer rows in full523. A deterministic representative sample is permitted only when it includes real answer/evidence payloads and is sufficient for the release gate. No such payload-bearing sample exists in the accepted receipt artifact, so zero cases were scored.

Safe terminals remain separate from semantic answer scoring. Their 100% correctness evidence is eligibility evidence and is not substituted into the semantic score.

## Quality artifact

Artifact: `docs/m27/research/independent_quality_score_receipts.json`

Contract: `m27-independent-quality-score/v1`

Current artifact state:

- evaluator identity: unavailable
- evaluator provider: unavailable for an actual scoring call
- evaluator model: unavailable for an actual scoring call
- rubric version: `ANSWER_QUALITY_RUBRIC_v1`
- scoring policy version: `m27-independent-quality-scoring-policy/v1`
- quality score: unavailable
- threshold: 85
- case count scored: 0
- production touched: false
- deterministic admission substitution: explicitly forbidden

Reason codes:

- `QUALITY_SCORER_UNAVAILABLE`
- `MISSING_EVALUATOR_IDENTITY`
- `MISSING_EVALUATOR_PROVIDER`
- `MISSING_EVALUATOR_MODEL`
- `NO_SEMANTIC_CASES_SCORED`
- `MISSING_PER_CASE_SCORE_EVIDENCE`
- `EVALUATOR_CREDENTIAL_UNAVAILABLE`
- `SOURCE_RECEIPTS_LACK_SEMANTIC_PAYLOAD`

## Implementation

Added `src/knowledge_engine/m27_independent_quality_scorer.py` with a fail-closed artifact contract and validator. It verifies:

- schema identity
- release candidate and hard-gate HEAD linkage
- exact source receipt SHA-256
- evaluator identity/provider/model
- rubric version and scoring-policy version
- numeric score range and `>=85` threshold
- positive case count
- sampling policy
- per-case evidence count and digest
- no deterministic-admission substitution
- no production mutation

Extended `m27_release_hard_gates.QualityScoreEvidence` and the quality hard-gate decision so a numeric score alone is insufficient. Provider/model, scoring policy, scored-case evidence, source-linkage status, and per-case digest are required whenever an independent score is presented.

## Tests

Focused suite:

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_independent_quality_scorer.py \
  tests/test_m27_release_hard_gates.py \
  tests/test_m27_isolated_streaming.py \
  tests/test_release_quality_gate.py \
  tests/test_m27_admission_metric_contract.py
```

Result: `32 passed, 1 warning`.

The warning is an existing Starlette/httpx deprecation warning and is unrelated to this scope.

The final validation commands and exact session HEAD are recorded at closure after this report is written.

## Production and release safety

- production deploy: NOT performed
- canary activation: NOT performed
- release pointer mutation: NOT performed
- production restart/stop/rebuild: NOT performed
- production R2/Qdrant/SQLite writes: NOT performed
- admission rerun: NOT performed
- Stage13/14 legacy admission: NOT performed
- Chunk002: NOT performed
- full523 rerun: NOT performed
- runtime answer tuning: NOT performed

## Final gate decision

`M27_INDEPENDENT_QUALITY_GATE_NOT_READY_WITH_DIAGNOSIS`

A future session can close this gate only with a real independent evaluator and payload-bearing accepted answer/evidence inputs, or with a valid deterministic human-review artifact that satisfies the same identity, rubric, per-case evidence, tamper-linkage, and no-production-mutation requirements.
