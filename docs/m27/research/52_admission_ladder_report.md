# M27 Admission Ladder + Release Readiness Report

Status: `M27_ADMISSION_NOT_READY_WITH_DIAGNOSIS`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-admission-release-rerun`
Branch: `m27/admission-ladder-release-rerun`
Wave-D base: `e9adcc58ba17818c3c34ca46d158314c2279a012`
Metric repair source: `763af5a322af568f7fb818256f7c7ad76c14adde`
Metric repair cherry-pick in rerun: `1869c99ae9693cc0fd05ccf3f317ae63a833156a`

## Scope

This is a fresh 10R Wave E admission rerun after `M27_ADMISSION_METRIC_CONTRACT_READY`. It consumed the accepted Wave-D integrated base plus the admission metric contract repair. It did not modify runtime answer behavior, tune benchmark failures, run Stage13/14 legacy admission, run Chunk002, mutate production, or deploy a release/canary.

## Required source review

The required production-equivalent runtime, smoke, preflight repair, adaptive, skills/MCP, governed memory, learning/meta, Wave-D integration, smoke handoff, Wave-D handoff, and metric-repair report/handoff were reviewed before evaluation.

## Fresh live preflight

PASS / AUTHORIZED before question 1.

- production health: HTTP 200 / ok true
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- isolated endpoint: `http://127.0.0.1:18080`
- runtime identity: `m27-production-equivalent-runtime`
- isolated build SHA: `1869c99ae9693cc0fd05ccf3f317ae63a833156a`
- image digest: `sha256:7f83a435da2b27ae40db100ea4e06b6ec82a06e23e4b74f8e606c30e3602a70d`
- container: `18ed7208fd5f` / `m27-isolated-eval-05r`
- exactly one owned eval container: YES
- quota active requests/provider calls: `0 / 0`
- smoke/admission questions before authorization: `0`
- available memory: 373 MB on first formal preflight, 369 MB before Gate 2
- swap used: 588 MB then 595 MB, within the explicit 768 MB low-memory ceiling
- production identity stable: YES
- no competing M27/pytest/docker-build runtime-changing session detected before evaluation

The preflight was rechecked after Gate 1 and remained `READY` before Gate 2.

## Gate 1: 20-case representative evaluation

PASS.

Coverage included cited answers, safe abstention, multilingual prompts, retrieval/source-locator drift, deadline pressure, feature-off M26 invariant, skills read-only, MCP default-off/read-only behavior, memory non-authority, and learning/meta review-only behavior.

Metrics:

- passed: `20 / 20`
- failed: `0`
- verified-answer expected/cited: `9 / 9`
- cited final-answer rate: `100%`
- safe terminal expected/correct: `5 / 5`
- safe-terminal correctness: `100%`
- safe-abstention correctness: `100%`
- drift-rejection correctness: `100%`
- budget-terminal correctness: `100%`
- citation/provenance integrity: `100%`
- unexpected visible answer on safe terminal: `0`
- provider calls: `22`
- tool calls: `15`
- continuation rounds: `0`
- errors / 429 / provider failures: `0 / 0 / 0`
- p50: `36.025 ms`
- p95: `2775.028 ms`
- max: `3023.562 ms`
- streaming: `not yet supported by isolated preflight endpoint; terminal runtime receipts only`
- independent quality score: unavailable in this deterministic harness
- feature-off invariant: PASS (`M26_BASELINE_UNCHANGED`)
- production mutation: NONE

The repaired metric contract correctly excludes intentional safe terminals from the cited-answer denominator while scoring those rows separately.

## Gate 2: 100-case evaluation

PASS after Gate 1 and preflight revalidation.

Metrics:

- passed: `100 / 100`
- failed: `0`
- verified-answer expected/cited: `45 / 45`
- cited final-answer rate: `100%`
- safe terminal expected/correct: `25 / 25`
- safe-terminal correctness: `100%`
- safe-abstention / drift-rejection / budget-terminal correctness: `100% / 100% / 100%`
- citation/provenance integrity: `100%`
- provider calls: `110`
- tool calls: `75`
- continuation rounds: `0`
- errors / 429 / provider failures: `0 / 0 / 0`
- p50: `27.389 ms`
- p95: `1906.016 ms`
- max: `2700.538 ms`
- telemetry-complete runtime cases: `75`
- streaming: not yet supported by the isolated preflight endpoint
- independent quality score: unavailable in this deterministic harness

Per-category pass rates were all 100%: cited answer, abstention, multilingual, retrieval hard, deadline pressure, feature-off, skills read-only, MCP default-off, MCP read-only, memory non-authority, and learning/meta review-only.

Policy-profile distribution: abstention 10, cited answer 30, deadline pressure 5, feature-off 5, learning/meta review-only 5, MCP default-off 5, MCP read-only 5, memory non-authority 5, multilingual 10, retrieval hard 15, skills read-only 5.

Adaptive-compute distribution: STANDARD 65, FAIL_CLOSED 5, N/A governance/feature-off rows 30. Verifier-gap continuation distribution: 0 rounds for all 100 cases. Memory/skill/MCP coverage: memory non-authority 5, skills 5, MCP 10.

## Gate 3: full523

NOT RUN.

Reason: `FULL523_REQUIRES_EXPLICIT_OWNER_AUTHORIZATION`.

The 10R contract requires a separate explicit Owner authorization only after the 100-case result is known. No such post-Gate-2 authorization was available in this active execution turn, so the session stops here. Previous full523 or Stage13/14 results are not used as authority.

## Release / canary

A release/canary deployment was not authorized and was not performed. Because full523 was not authorized/run, this report does not claim `M27_RELEASE_CANDIDATE_READY`.

## Known pre-existing M26 issue

The Wave-D report documents the pre-existing failure `tests/test_m26_final_answer_synthesis.py::test_compact_segment_role_contract_keeps_evidence_boundaries_material`. It reproduces on the untouched 09 base and is not a Wave-D or admission-rerun regression.

## Cleanup and production proof

The owned container was removed through the ownership-checked cleanup script.

After cleanup:

- owned M27 eval containers: `0`
- listeners on port 18080: `0`
- production health: HTTP 200 / ok true
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint unchanged: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- production mutation: NONE

## Final state

`M27_ADMISSION_NOT_READY_WITH_DIAGNOSIS`

Remaining blocker: `FULL523_REQUIRES_EXPLICIT_OWNER_AUTHORIZATION`.
