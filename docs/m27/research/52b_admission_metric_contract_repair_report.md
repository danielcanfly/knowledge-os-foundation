# M27 Wave-E Admission Metric Contract Repair Report

## Session scope

This session repaired only the admission/evaluation metric contract identified by the blocked 10R Wave-E admission ladder.

Starting state:

- status: M27_ADMISSION_NOT_READY_WITH_DIAGNOSIS
- blocked workspace: /home/ubuntu/LLM_Wiki-m27-admission-release
- blocked HEAD: 8e014f95bbe398b675a2184ae58a45b3824425e7
- blocker: GATE1_CITATION_RATE_METRIC_COUNTS_INTENTIONAL_SAFE_TERMINALS_IN_DENOMINATOR

No admission questions were sent. The 20-case gate was not rerun. The 100-case, full523, Chunk002, Stage13/14, release, canary, and production deployment paths were not run.

## Investigation

The persisted 20-case receipts contain:

- 9 rows with expectation verified_cited_answer
- 2 rows with expectation safe_abstention
- 2 rows with expectation rejected_before_provider
- 1 row with expectation budget_terminal
- 1 row with expectation m26_invariant
- 5 rows with expectation governance_contract

All 9 verified-answer rows had citations. The 5 intentional safe-terminal rows had zero citations.

The old temporary 10R runner used non-null terminal answer objects, represented in receipts as answer_present, to form the citation denominator. M27 safe terminals also carry a structured terminal result object, so the denominator became 14 rows instead of 9. That produced the incorrect 9/14 = 64.29% result.

answer_present is therefore not a valid visible-answer leakage signal and is no longer part of the metric contract.

## Repaired metric contract

New code:

- src/knowledge_engine/m27_admission_metric_contract.py

The repaired contract defines:

1. cited_final_answer_rate
   - denominator: only rows whose expected outcome is verified_cited_answer
   - numerator: those rows with at least one citation
   - expected safe terminals, governance contracts, and feature-off invariant rows are excluded

2. Expected safe terminals
   - safe_abstention
   - rejected_before_provider / drift_rejection
   - budget_terminal / deadline_terminal
   - generic safe_terminal

3. Safe-terminal metrics
   - safe_terminal_correctness
   - safe_abstention_correctness
   - drift_rejection_correctness
   - budget_terminal_correctness
   - unexpected_answer_on_safe_terminal_count
   - safe_terminal_missing_leakage_signal_count

4. Safe-terminal leakage contract
   - citation_count must be zero
   - a semantically explicit visible-answer leakage signal must be present and false
   - legacy answer_present is deliberately ignored because it means a terminal result object exists
   - missing explicit leakage signal fails closed
   - answer leakage or citation leakage fails safe-terminal correctness

5. Aggregate gate
   - cited-answer coverage must be >= 95% on verified-answer-expected rows
   - safe-terminal correctness must be exactly 100% on expected safe-terminal rows
   - feature-off invariant must remain true when present
   - production no-mutation must remain true

A verified-answer row without citations remains in the denominator and fails citation coverage.

## Deterministic proof cases

New tests:

- tests/test_m27_admission_metric_contract.py

Covered cases:

1. 9 cited verified answers + 5 expected safe terminals => cited final-answer rate 1.0, not 9/14.
2. 8 cited verified answers + 1 uncited verified answer + 5 safe terminals => 8/9 and aggregate gate fails the 95% requirement.
3. Safe-terminal rows with zero citations and no visible-answer leakage pass.
4. Safe-terminal rows with answer leakage or citation leakage fail.
5. Missing explicit leakage signal fails closed.
6. Overall gate requires both citation coverage and safe-terminal correctness.
7. Feature-off invariant and production no-mutation remain gate inputs.

## Offline replay of persisted 20-case receipts

No admission questions were sent. The existing persisted receipts were re-aggregated offline only.

For the five already-diagnosed intentional safe-terminal rows, the replay supplied the semantically explicit answer_leaked = false signal that the repaired runner contract now requires.

Result:

- verified answer expected: 9
- verified answer cited: 9
- cited final-answer rate: 1.0
- safe terminal expected: 5
- safe terminal correct: 5
- safe-terminal correctness: 1.0
- safe-abstention correctness: 1.0
- drift-rejection correctness: 1.0
- budget-terminal correctness: 1.0
- unexpected answer on safe terminal: 0
- feature-off invariant: true
- production no-mutation: true
- aggregate metric gate: pass

This is an offline metric-contract proof only. It is not a rerun of Gate 1 and is not an admission result.

## Validation

A shared existing repository virtual environment was used because the fresh worktree had no local .venv; no packages were installed and no environment mutation was required.

Executed:

- pytest -q tests/test_m27_admission_metric_contract.py tests/test_m27_isolated_admission_harness.py tests/test_m27_wave_d_integration.py
  - PASS: 27 passed in 1.02s
- python -m compileall -q src/knowledge_engine tests
  - PASS
- scoped Ruff on the changed Python files
  - PASS
- git diff --check
  - PASS

No unrelated M26 test failure was encountered in the bounded validation set.

## Production no-mutation proof

This session:

- sent zero admission questions
- sent zero benchmark questions
- performed no production write
- performed no production restart, stop, rebuild, deploy, pointer update, R2 write, Qdrant write, or SQLite write
- changed no runtime answer behavior
- changed no adaptive policy, evidence retrieval, memory, skill, MCP, or learning semantics

The repair is isolated to admission metric code, deterministic tests, and documentation.

## 10R rerun readiness

The metric-contract blocker is repaired and deterministically validated. A later 10R session may rerun from its required fresh preflight and must use the repaired metric contract, including the explicit safe-terminal visible-answer leakage signal.

This report does not authorize skipping preflight or any admission ladder gate.
