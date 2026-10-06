# M27 Admission Ladder + Release Readiness Report

Status: `M27_RELEASE_CANDIDATE_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-admission-release-rerun`
Branch: `m27/admission-ladder-release-rerun`
Wave-D base: `e9adcc58ba17818c3c34ca46d158314c2279a012`
Metric repair source: `763af5a322af568f7fb818256f7c7ad76c14adde`
Admission rerun prior HEAD: `9a2af61cebddebb6a1fba9be49402b78d0ef255a`

## Scope

This session is the explicit post-100-case full523 authorization continuation for the 10R Wave E admission ladder. It consumed the accepted Wave-D integrated base, the repaired admission metric contract, and the prior admission rerun where the 20-case and 100-case gates passed. It did not perform runtime feature development, benchmark tuning, Stage13/14 legacy admission, Chunk002, production mutation, or deployment.

## Lineage and prior gates

The prior 10R rerun legally stopped at `M27_ADMISSION_NOT_READY_WITH_DIAGNOSIS` only because full523 required explicit post-100 authorization. The already-recorded gate results were retained as receipts, not recomputed in this continuation:

- 20-case: PASS, `20 / 20`
- 20-case cited final-answer rate: `100%`, `9 / 9`
- 20-case safe-terminal correctness: `100%`, `5 / 5`
- 100-case: PASS, `100 / 100`
- 100-case cited final-answer rate: `100%`, `45 / 45`
- 100-case safe-terminal correctness: `100%`, `25 / 25`
- production touched: NO
- cleanup after 100-case: owned eval containers `0`, port 18080 free

The owner explicitly authorized full523 in this continuation after the 100-case PASS was known.

## Required source review

The 10R prompt was reread. The prior admission report, handoff, and receipts were inspected before running full523. The required earlier reports and handoffs had already been reviewed in the 10R rerun and remain part of the lineage: production-equivalent runtime, fresh small smoke, smoke preflight repair, adaptive planner, skills/MCP, governed memory, learning/meta, Wave-D integration, smoke handoff, Wave-D handoff, and metric repair handoff.

## Fresh live preflight before full523

PASS / AUTHORIZED before sending any full523 case.

- production health before full523: HTTP 200 / ok true
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- isolated endpoint: `http://127.0.0.1:18080`
- runtime identity: `m27-production-equivalent-runtime`
- isolated build SHA: `9a2af61cebddebb6a1fba9be49402b78d0ef255a`
- image digest: `sha256:68fb1aff7d75a6128671756a86fa42ad3e9c0a20645e178fb2bad184b25e993d`
- container: `0e26bc68420d` / `m27-isolated-eval-05r`
- exactly one owned eval container: YES
- quota active requests/provider calls: `0 / 0`
- smoke/admission questions before authorization: `0`
- available memory: 382 MB
- swap used: 589 MB, within the explicit 768 MB low-memory ceiling
- load 1m: 1.67
- production identity stable during preflight: YES

No full523 case was sent before the preflight reached `READY`.

## Gate 3: full523 evaluation

PASS.

Coverage preserved the same admission categories at full523 scale: cited answer, safe abstention, multilingual prompt, retrieval/source-locator drift, deadline pressure, feature-off M26 invariant, skills read-only, MCP default-off/read-only behavior, memory sidecar non-authority, and learning/meta review-only behavior.

Metrics:

- passed: `523 / 523`
- failed: `0`
- verified-answer expected/cited: `237 / 237`
- cited final-answer rate under corrected metric: `100%`
- safe terminal expected/correct: `130 / 130`
- safe-terminal correctness: `100%`
- safe-abstention correctness: `100%`
- drift-rejection correctness: `100%`
- budget-terminal correctness: `100%`
- citation/provenance integrity: `100%`
- unexpected visible answer on safe terminal: `0`
- missing explicit safe-terminal leakage signal: `0`
- provider calls: `578`
- tool calls: `393`
- continuation rounds: `0`
- errors / 429 / provider failures: `0 / 0 / 0`
- p50 latency: `24.528 ms`
- p95 latency: `2365.529 ms`
- max latency: `3886.188 ms`
- telemetry-complete runtime cases: `393`
- streaming: `not yet supported by isolated preflight endpoint; evaluation exercises terminal runtime receipts`
- quality score: unavailable; this deterministic admission harness has no independent quality scorer, so the quality >=85 threshold is not computable in this run
- feature-off invariant: PASS (`M26_BASELINE_UNCHANGED`)
- production mutation: NONE

The corrected admission metric contract was used: only expected `verified_cited_answer` rows enter the cited final-answer denominator, while intentional safe terminals are evaluated separately.

## Full523 distributions

Per-category pass rates were all 100%:

- abstention: `52 / 52`
- cited_answer: `159 / 159`
- deadline_pressure: `26 / 26`
- feature_off: `26 / 26`
- learning_meta_review_only: `26 / 26`
- mcp_default_off: `26 / 26`
- mcp_readonly: `26 / 26`
- memory_non_authority: `26 / 26`
- multilingual: `52 / 52`
- retrieval_hard: `78 / 78`
- skills_readonly: `26 / 26`

Policy-profile distribution: abstention 52, cited answer 159, deadline pressure 26, feature-off 26, learning/meta review-only 26, MCP default-off 26, MCP read-only 26, memory non-authority 26, multilingual 52, retrieval hard 78, skills read-only 26.

Adaptive-compute distribution: STANDARD 341, FAIL_CLOSED 26, N/A governance/feature-off rows 156. Verifier-gap continuation distribution: 0 rounds for all 523 cases. Memory/skill/MCP coverage: memory non-authority 26, skills 26, MCP 52.

## Release / canary readiness plan

Release/canary may be planned as a report-only next step because all authorized gates passed and production was untouched. No deployment was performed.

Report-only canary plan for a later separately authorized deployment session:

1. Prepare a separate deployment prompt that pins this admission HEAD and receipts.
2. Re-run read-only production health and identity checks immediately before any canary action.
3. Deploy only through a separate explicit Owner deployment authorization.
4. Use a canary percentage or owner-only traffic mode first, with M27 feature-off fallback preserved.
5. Monitor cited final-answer rate, safe-terminal correctness, p95 latency, 429/provider failure rate, production identity, and no-mutation invariants.
6. Roll back by returning traffic to the M26 production entrypoint and preserving the current release pointer if any canary guard trips.

This report does not authorize production deployment, production restart, production rebuild, release pointer writes, R2/Qdrant/SQLite writes, or canary activation.

## Known pre-existing M26 issue

The Wave-D report documents the pre-existing failure `tests/test_m26_final_answer_synthesis.py::test_compact_segment_role_contract_keeps_evidence_boundaries_material`. It reproduced on the untouched 09 base and is not a Wave-D or admission-rerun regression. This session did not modify M26 synthesis behavior.

## Cleanup and production proof

The owned isolated eval container was removed through the ownership-checked cleanup script.

After cleanup:

- owned M27 eval containers: `0`
- listeners on port 18080: `0`
- production health: HTTP 200 / ok true
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint unchanged: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- production mutation: NONE
- available memory after cleanup: 448 MB
- swap used after cleanup: 587 MB

## Final state

`M27_RELEASE_CANDIDATE_READY`

Release/canary is report-only planned and not deployed.
