# M27 Skills + MCP Activation Report

## Status

`M27_SKILLS_MCP_ACTIVATION_READY`

## Base and Scope

- Base HEAD: `433e1f81f795ce945cd204df931dd281d1cb0ba6`
- Base branch/workspace: `m27/adaptive-planner-compute` / `/home/ubuntu/LLM_Wiki-m27-adaptive-planner`
- Activation branch/workspace: `m27/skills-mcp-activation` / `/home/ubuntu/LLM_Wiki-m27-skills-mcp`
- Scope: isolated M27 only.
- Production mutation: none.
- Stage13/14 legacy admission: not run.
- Chunk002 / 100-case / full523: not run.

## Implemented Surface

### 1. Bounded Skill Runner

Added `src/knowledge_engine/m27_skill_runner.py`.

The runner activates existing Stage 7 ops skill descriptors without changing `SkillRegistry` into an execution surface. `SkillRegistry` remains descriptor-only, preserving the previous contract that it has no `run`, `execute`, or `invoke` method.

New execution boundary:

- `ReadOnlySkillRunner`
- `SkillRunnerPolicy`
- `SkillRunnerContext`
- `SkillToolCallBoundary`
- `SkillRunnerResult`

Boundaries enforced:

- skill must match policy `skill_name`
- all skill-declared capabilities must be explicitly authorized
- capabilities must be unique and sorted in policy
- isolated runtime required
- read-only mode required
- mutation, network, and raw infra are fail-closed
- tool-call budget enforced before each call
- timeout checked before each call
- body-free report envelope only
- report-only/candidate-only output markers

### 2. ToolExecutor-only Skill Capability Calls

`ReadOnlySkillRunner` does not call providers directly. It converts each skill step capability into the typed request required by `ReadOnlyToolExecutor` using the existing `request_for_capability(...)` helper.

Allowed tool calls remain restricted to Stage 5 read-only descriptors:

- `knowledge.search`
- `knowledge.expand`
- `evidence.inspect`
- `evidence.verify`
- `runtime.get_trace`
- `runtime.get_budget`
- `runtime.get_health`

The runner returns `ToolExecutionRecord` metadata only, not raw evidence bodies, private question text, answer text, infrastructure handles, or credentials.

### 3. Optional MCP Read-only Transport

Added `src/knowledge_engine/m27_mcp_readonly_transport.py`.

The transport activates MCP only as a local, optional, read-only shim over the existing `ReadOnlyToolExecutor`. It is not a network MCP server and does not expose shell, filesystem, process, production, credential, release, admin, R2, Qdrant, SQLite, or raw infrastructure APIs.

New transport boundary:

- `ReadOnlyMcpTransport`
- `McpReadonlyTransportPolicy`
- `McpReadonlyTransportResult`

Transport boundaries enforced:

- disabled by default unless policy `enabled=True`
- isolated runtime required
- no network listener
- no mutation
- no raw infra
- capability must exist in the existing Stage 9 read-only MCP manifest allowlist
- call still passes through `ToolExecutionPolicy` and `ReadOnlyToolExecutor`

### 4. Demonstrated End-to-End Ops Skill

Added `tests/test_m27_skill_runner.py`.

End-to-end isolated ops skill demonstrated:

- Skill: `diagnose-latency`
- Invoked steps:
  - `runtime.get_trace`
  - `runtime.get_budget`
  - `runtime.get_health`
- Provider surface: sanitized runtime metadata provider only
- Output: diagnostic report envelope and candidate next-action markers only

Coverage added:

- successful end-to-end isolated ops skill execution
- budget exhaustion before second call
- fail-closed unauthorized capability policy
- timeout before first call
- body-free result envelope
- no mutation/raw infra in returned records

### 5. Demonstrated Optional MCP Tool Dispatch

Added `tests/test_m27_mcp_readonly_transport.py`.

Coverage added:

- optional MCP transport dispatches `runtime.get_health` through the read-only Stage 9 allowlist and ToolExecutor
- disabled MCP policy fails closed
- forbidden capability such as `shell.exec` fails closed before provider access

## Validation

Targeted activation/regression suite:

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m pytest -q \
  tests/test_m27_skill_runner.py \
  tests/test_m27_mcp_readonly_transport.py \
  tests/test_m27_skill_contracts.py \
  tests/test_m27_tool_executor.py \
  tests/test_m27_mcp_exposure.py

34 passed in 2.64s
```

Full M27 suite:

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m pytest -q tests/test_m27_*.py

548 passed, 1 warning in 31.99s
```

Lint and compile:

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/ruff check \
  src/knowledge_engine/m27_skill_runner.py \
  src/knowledge_engine/m27_mcp_readonly_transport.py \
  tests/test_m27_skill_runner.py \
  tests/test_m27_mcp_readonly_transport.py

All checks passed!

python3 -m compileall -q src tests
PASS
```

Known warning:

- Existing FastAPI / Starlette / httpx deprecation warning from the test environment.
- Not introduced by this activation.

## Safety Review

This activation did not:

- mutate production
- restart, stop, rebuild, or deploy production
- write production R2 / Qdrant / SQLite / release pointers
- expose shell/MCP raw commands
- expose write/admin/release tools
- enable a production network listener
- import dirty uncommitted changes from `/home/ubuntu/LLM_Wiki-m27-context-runtime`
- run Stage13/14 legacy admission
- run Chunk002, 100-case, or full523

## Conclusion

Skills and MCP are now activated as bounded, isolated, read-only, policy-gated execution surfaces inside M27. The activation preserves previous descriptor-only contracts while adding explicit execution boundaries, authorization, tool budgets, timeout checks, trace boundaries, and isolated end-to-end proof.

`M27_SKILLS_MCP_ACTIVATION_READY`
