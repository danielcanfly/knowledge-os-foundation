# M27 Skills + MCP Activation Handoff

## Canonical State

`M27_SKILLS_MCP_ACTIVATION_READY`

## Workspace

- Branch: `m27/skills-mcp-activation`
- Workspace: `/home/ubuntu/LLM_Wiki-m27-skills-mcp`
- Base HEAD: `433e1f81f795ce945cd204df931dd281d1cb0ba6`

## What Changed

### New Modules

- `src/knowledge_engine/m27_skill_runner.py`
  - bounded isolated ops skill execution boundary
  - keeps `SkillRegistry` descriptor-only
  - requires explicit policy authorization
  - calls only `ReadOnlyToolExecutor`
  - enforces max tool calls and timeout checks
  - returns body-free diagnostic/report metadata only

- `src/knowledge_engine/m27_mcp_readonly_transport.py`
  - optional local read-only MCP transport shim
  - default-disabled by policy
  - no network listener
  - no raw infrastructure exposure
  - dispatches only capabilities present in the Stage 9 MCP read-only manifest allowlist
  - still passes through `ToolExecutionPolicy` and `ReadOnlyToolExecutor`

### New Tests

- `tests/test_m27_skill_runner.py`
  - demonstrates `diagnose-latency` end-to-end in isolated mode
  - validates authorization, budget, timeout, and body-free output boundaries

- `tests/test_m27_mcp_readonly_transport.py`
  - demonstrates optional MCP read-only dispatch
  - validates disabled and forbidden capability fail-closed behavior

## Verified Commands

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m pytest -q \
  tests/test_m27_skill_runner.py \
  tests/test_m27_mcp_readonly_transport.py \
  tests/test_m27_skill_contracts.py \
  tests/test_m27_tool_executor.py \
  tests/test_m27_mcp_exposure.py

34 passed in 2.64s
```

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/python -m pytest -q tests/test_m27_*.py

548 passed, 1 warning in 31.99s
```

```text
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-adaptive-planner/.venv/bin/ruff check \
  src/knowledge_engine/m27_skill_runner.py \
  src/knowledge_engine/m27_mcp_readonly_transport.py \
  tests/test_m27_skill_runner.py \
  tests/test_m27_mcp_readonly_transport.py

All checks passed!
```

```text
python3 -m compileall -q src tests
PASS
```

## Operational Notes

- Use `ReadOnlySkillRunner` when an ops skill should execute its declared read-only tool steps.
- Do not add execution methods to `SkillRegistry`; it remains descriptor/planning only.
- Use `ReadOnlyMcpTransport` only for local, isolated, explicitly enabled MCP tool transport.
- Do not enable network listener behavior without a new explicit Owner-approved session.
- Do not add write/admin/release/shell/filesystem/raw infra capabilities to either activation surface.

## Not Done by Design

- No production deployment.
- No production write path.
- No raw MCP command surface.
- No answer-generation skills activated.
- No ingestion/promotion/release skills activated.
- No Stage13/14 legacy admission, Chunk002, 100-case, or full523 run.

## Next Suggested Session

A future session can wire this activated skill runner into a higher-level ops diagnostic command path, still behind isolated runtime policy and without production mutation.
