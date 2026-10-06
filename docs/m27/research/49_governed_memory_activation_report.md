# M27 Governed Memory Activation Report

Status: `M27_MEMORY_ACTIVATION_READY`

## Scope

This session activates governed memory as useful auxiliary context for the isolated M27 runtime. Memory remains non-authoritative: it cannot become citation truth, source truth, locator truth, release truth, or evidence truth.

The session was based on the latest approved upstream base supplied by Owner:

- Base HEAD: `433e1f81f795ce945cd204df931dd281d1cb0ba6`
- Branch: `m27/governed-memory-activation`
- Workspace: `/home/ubuntu/LLM_Wiki-m27-memory-activation`

No production deploy, restart, release-pointer update, R2 write, Qdrant write, SQLite production write, Stage13/14 legacy admission, Chunk002, 100-case, or full523 execution was performed.

## Implemented Changes

### Memory read policy

Added `src/knowledge_engine/m27_memory_activation.py` with a strict `GovernedMemoryReadPolicy`:

- Memory read is enabled only when the runtime task explicitly sets `allow_memory_read=True`.
- Memory read requires an enabled `MemoryActivation(enabled=True, isolated_runtime=True)` runtime.
- Eligible task kinds are limited to `KNOWLEDGE` and `OPS`.
- Eligible memory classes are limited to reviewed `PROJECT` and `EPISODIC` candidates.
- Scope is bound to the current `task_id`; cross-task memory is not read.
- Memory reads emit trace reason `EXPLICIT_TASK_MEMORY_READ` and reason codes including `REVIEWED_CANDIDATES_ONLY`, `TASK_SCOPE_BOUND`, `AUXILIARY_CONTEXT_ONLY`, and `NO_CITATION_AUTHORITY`.
- The policy rejects attempts to widen memory classes, scope binding, or item budget.

### Auxiliary-only integration

Integrated governed memory into `src/knowledge_engine/m27_runtime_harness.py` as a sidecar only:

- The runtime gathers retained memory through `read_auxiliary_memory_context(...)`.
- The runtime records `auxiliary_memory_context` in harness summaries/results.
- Executable answers may include an `auxiliary_memory` sidecar only when an evidence-backed answer exists.
- Empty safe-terminal answers remain empty, preserving the rule that memory cannot substitute for evidence.

### Authority boundary

Every memory context carries an explicit authority boundary:

- `knowledge_authority=False`
- `citation_eligible=False`
- `source_identity_eligible=False`
- `locator_eligible=False`
- `release_eligible=False`
- `can_satisfy_evidence_requirements=False`
- `can_override_answer=False`
- `can_promote_to_knowledge=False`
- `production_write=False`

`assert_memory_cannot_satisfy_evidence(...)` rejects memory payloads that expose evidence-authority fields such as citation, source identity, locator, release id, or manifest sha.

### Review / promotion workflow

This session does not implement automatic promotion to authoritative knowledge.

The only supported workflow is:

1. Propose sanitized candidate memory through the existing governed memory runtime.
2. Append immutable review receipts.
3. Read only candidates whose latest review is `RETAIN_CANDIDATE`.
4. Exclude candidates whose latest review is `REJECT_CANDIDATE`.
5. Treat retained candidates only as auxiliary context.

Any future promotion from memory into authoritative knowledge must be a separate Owner-approved workflow with explicit evidence/provenance reconstruction. It is intentionally not part of this activation.

## Tests Added / Updated

Added `tests/test_m27_memory_activation.py` covering:

- explicit task allowance and isolated runtime requirement
- ineligible task kind denial
- task-scope isolation
- stale / incorrect memory exclusion through latest rejection
- private payload rejection
- no answer override
- authority boundary enforcement
- policy widening rejection

Updated `tests/test_m27_memory_runtime.py` to recognize `m27_memory_activation.py` as the intentional Stage 08 activation module while preserving the older isolation check for other M27 modules.

## Verification

Targeted memory/runtime regression:

```text
91 passed in 2.39s
```

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m pytest tests/test_m27_memory_activation.py tests/test_m27_memory_contracts.py tests/test_m27_memory_runtime.py tests/test_m27_context_orchestrator.py tests/test_m27_runtime_finalization.py tests/test_m27_production_evidence_bridge.py -q
```

Bounded M27 suite:

```text
549 passed, 1 warning in 11.41s
```

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m pytest tests/test_m27_*.py -q
```

The single warning is the existing FastAPI / Starlette / httpx deprecation warning from the shared virtual environment and is unrelated to this change.

Ruff:

```text
All checks passed!
```

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/ruff check src/knowledge_engine/m27_memory_activation.py src/knowledge_engine/m27_runtime_harness.py tests/test_m27_memory_activation.py tests/test_m27_memory_runtime.py
```

Compile check:

```text
PASS
```

Command:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m compileall -q src tests
```

Repo-wide `pytest -q` was attempted for situational awareness, but it entered unrelated historical failures outside this dispatch scope and was not used as the completion gate. The run was stopped and unrelated generated dirty pilot files were reverted. The completion gate for this session is the bounded M27 suite plus targeted memory/runtime regression above.

## Production Mutation Audit

Production mutation: `NONE`.

No production services were restarted, stopped, rebuilt, or deployed. No production R2, Qdrant, SQLite, or release pointers were written.

## Result

`M27_MEMORY_ACTIVATION_READY`
