# M27 Learning Meta-Harness Handoff

Status: `M27_LEARNING_META_LOOP_READY`

## Final workspace

- Worktree: `/home/ubuntu/LLM_Wiki-m27-learning-meta`
- Branch: `m27/learning-meta-loop`
- Base HEAD: `7defd3498873c65c956ca5cba13d58ae7d25c1e3`

## New entrypoint

Use the review-only coordinator:

- `src/knowledge_engine/m27_learning_meta_loop.py`

Primary class:

- `OfflineLearningMetaHarnessLoop`

Input record:

- `SanitizedOfflineObservation`

Output:

- `LearningMetaLoopResult`
- metadata-only review packet from `render_review_packet(...)`

## What it does

The loop converts sanitized offline telemetry/report summaries into:

1. deterministic failure-mode mining,
2. Stage 11 learning signals,
3. Stage 11 learning proposals marked `READY_FOR_REVIEW`,
4. Stage 12 meta-harness eval-plan candidates marked `READY_FOR_REVIEW`,
5. metadata-only review packets.

## What it must not do

The loop has no authority to:

- self-patch,
- apply patches,
- merge branches,
- promote releases,
- deploy,
- write production,
- mutate runtime behavior,
- execute tools or MCP,
- use raw private payloads,
- satisfy evidence/citation requirements.

## Test receipts

Targeted chain:

- `101 passed in 1.52s`

Bounded M27 suite:

- `576 passed, 1 warning in 13.71s`

Ruff / compileall:

- PASS

The single warning is an existing FastAPI / Starlette / httpx deprecation warning.

## Follow-up guidance

Future sessions may feed sanitized telemetry/report summaries into `SanitizedOfflineObservation`. Any proposal or candidate produced by this loop must remain review-only until a separate human-approved patch/merge/promotion workflow is explicitly dispatched.

Do not treat `READY_FOR_REVIEW` as approval to apply changes. It means only that the proposal/candidate has enough sanitized metadata to enter human review.
