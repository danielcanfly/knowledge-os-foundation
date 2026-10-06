# M27 Memory Activation Handoff

Status: `M27_MEMORY_ACTIVATION_READY`

## Branch / Workspace

- Branch: `m27/governed-memory-activation`
- Workspace: `/home/ubuntu/LLM_Wiki-m27-memory-activation`
- Base: `433e1f81f795ce945cd204df931dd281d1cb0ba6`

## What Changed

This session activates governed memory reads as auxiliary context only.

Primary files:

- `src/knowledge_engine/m27_memory_activation.py`
- `src/knowledge_engine/m27_runtime_harness.py`
- `tests/test_m27_memory_activation.py`
- `tests/test_m27_memory_runtime.py`

The activation policy permits memory reads only when all of the following hold:

1. The runtime task explicitly sets `allow_memory_read=True`.
2. The memory runtime is enabled and isolated.
3. The task kind is `KNOWLEDGE` or `OPS`.
4. The candidate memory class is `PROJECT` or `EPISODIC`.
5. The candidate is reviewed and currently retained.
6. The candidate scope matches the current `task_id`.

## Non-Authority Contract

Memory remains a sidecar.

It cannot:

- satisfy citations
- satisfy source identity
- satisfy locators
- satisfy release or manifest requirements
- satisfy evidence requirements
- override an answer
- promote itself into authoritative knowledge
- write production state

Safe-terminal empty answers remain empty even when memory is available.

## Review Workflow

Supported workflow:

1. Write sanitized candidate memory.
2. Append review receipts.
3. Read only latest-retained candidates.
4. Exclude latest-rejected candidates.
5. Use retained candidates only as auxiliary runtime context.

No automatic promotion to authoritative knowledge exists in this session. Any future promotion must be a separate Owner-approved evidence/provenance workflow.

## Verification

- Targeted regression: `91 passed in 2.39s`
- Bounded M27 suite: `549 passed, 1 warning in 11.41s`
- Ruff: `All checks passed!`
- Compileall: `PASS`

The only warning is the pre-existing FastAPI / Starlette / httpx deprecation warning.

## Explicit Non-Actions

Not run or touched:

- production deploy / restart / rebuild
- production R2 / Qdrant / SQLite / release pointers
- Stage13 / Stage14 legacy admission
- Chunk002
- 100-case
- full523

## Next Suggested Gate

Use this handoff as the input to the next production-grade compiler/evidence bundle bridge or fresh small admission smoke gate. Memory should remain non-authoritative in all downstream gates unless Owner explicitly approves a separate promotion mechanism.
