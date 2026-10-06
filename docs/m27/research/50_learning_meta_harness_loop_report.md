# M27 Learning + Meta-Harness Offline Loop Report

Status: `M27_LEARNING_META_LOOP_READY`

## Scope

This session implemented the governed offline improvement loop requested in `09_LEARNING_META_HARNESS_PROMPT.md`.

The loop is review-only and connects existing Stage 11 learning proposal contracts with Stage 12 meta-harness candidate contracts. It does not apply patches, merge code, promote releases, deploy, mutate production, or change runtime behavior automatically.

Base HEAD used:

- `7defd3498873c65c956ca5cba13d58ae7d25c1e3`
- Branch: `m27/learning-meta-loop`
- Worktree: `/home/ubuntu/LLM_Wiki-m27-learning-meta`

## Implemented artifacts

### New module

- `src/knowledge_engine/m27_learning_meta_loop.py`

The module adds:

- `SanitizedOfflineObservation` for bounded sanitized telemetry/report summaries.
- `OfflineFailureClass` for deterministic failure classes.
- `mine_failure_modes(...)` for aggregate failure mining.
- `OfflineLearningMetaHarnessLoop.run(...)` for deterministic:
  - sanitized observation consumption,
  - learning signal creation,
  - learning proposal generation,
  - meta-harness eval-plan candidate generation,
  - review-only status transition.
- `render_review_packet(...)` for metadata-only review packets.
- `learning_meta_loop_governance()` for explicit authority boundaries.

### New tests

- `tests/test_m27_learning_meta_loop.py`

Coverage added for:

- raw/private payload marker rejection,
- deterministic failure classification,
- sanitized report grouping,
- proposal + eval candidate creation,
- idempotent deterministic loop output,
- metadata-only review packets,
- no mutation/auto-apply/auto-merge/auto-promote authority,
- no provider/backend/process/production dependencies,
- no wiring into runtime execution or production surfaces.

### Adjusted isolation sentinels

The existing Stage 11 and Stage 12 isolation tests now explicitly allow only the new coordinator file:

- `tests/test_m27_learning_runtime.py`
- `tests/test_m27_meta_harness_runtime.py`

This is a narrow exception for `m27_learning_meta_loop.py` only. All other Stage 11/12 isolation restrictions remain in force.

## Governance properties

The loop enforces:

- sanitized inputs only,
- no raw private payloads,
- proposal-only learning output,
- candidate-only meta-harness output,
- human review required,
- offline gate required,
- no self-patching,
- no auto-apply,
- no auto-merge,
- no auto-promote,
- no production writes,
- no release authority,
- no deployment authority,
- no runtime behavior change.

The loop consumes only opaque refs, upper-snake classifications/reason codes, bounded counts, and sanitized summaries. Existing Stage 11/12 validators reject private/raw/backend markers.

## Validation

### Targeted learning/meta/runtime chain

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/pytest -q   tests/test_m27_learning_meta_loop.py   tests/test_m27_learning_runtime.py   tests/test_m27_meta_harness_runtime.py   tests/test_m27_memory_activation.py   tests/test_m27_adaptive_compute.py
```

Result:

- `101 passed in 1.52s`

### Bounded M27 suite

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/pytest -q tests/test_m27*.py
```

Result:

- `576 passed, 1 warning in 13.71s`

Warning:

- Existing FastAPI / Starlette / httpx deprecation warning from testclient stack. Not introduced by this session.

### Ruff / compileall

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/ruff check   src/knowledge_engine/m27_learning_meta_loop.py   tests/test_m27_learning_meta_loop.py   tests/test_m27_learning_runtime.py   tests/test_m27_meta_harness_runtime.py

python3 -m compileall -q   src/knowledge_engine/m27_learning_meta_loop.py   tests/test_m27_learning_meta_loop.py   tests/test_m27_learning_runtime.py   tests/test_m27_meta_harness_runtime.py
```

Result:

- Ruff: PASS
- compileall: PASS

## Explicit non-actions

This session did not:

- mutate production,
- restart, stop, rebuild, or deploy production,
- write production R2 / Qdrant / SQLite / release pointers,
- run full523,
- run Stage13/14 legacy admission,
- run Chunk002 or 100-case,
- import dirty changes from `/home/ubuntu/LLM_Wiki-m27-context-runtime`,
- auto-apply any learning proposal,
- auto-generate or apply code patches from meta-harness candidates.

## Conclusion

The governed offline improvement loop is implemented and verified. It is ready for human-reviewed future use as a proposal/evaluation planning surface only.

Canonical completion state:

`M27_LEARNING_META_LOOP_READY`
