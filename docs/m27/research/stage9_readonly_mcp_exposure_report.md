# M27 Stage 9 Read-only MCP Exposure Report

Date: 2026-10-03
Branch: `m27/stage9-readonly-mcp-exposure`
Base: `2debb030`

## 1. Scope

Stage 9 adds a descriptor-first, default-off, read-only MCP exposure boundary over the already-stable Stage 5 native capability registry.

It does not add a live MCP server, network listener, provider execution path, tool invocation surface, authorization grant, workspace exposure, skill execution, memory runtime, production mutation authority, or answer-path behavior change.

Dependency direction remains:

```text
Stage 5 ToolRegistry
        |
        v
Stage 9 MCP descriptor / manifest adapter
        |
        v
static read-only MCP exposure description
```

## 2. Files changed

Created:

```text
src/knowledge_engine/m27_mcp_contracts.py
src/knowledge_engine/m27_mcp_exposure.py
tests/test_m27_mcp_contracts.py
tests/test_m27_mcp_exposure.py
docs/m27/research/stage9_readonly_mcp_exposure_report.md
```

Not modified:

```text
all m26_* source
src/knowledge_engine/m27_tool_contracts.py
src/knowledge_engine/m27_tool_registry.py
src/knowledge_engine/m27_readonly_tools.py
src/knowledge_engine/m27_skill_contracts.py
src/knowledge_engine/m27_workspace_contracts.py
src/knowledge_engine/m27_workspace_store.py
docker-compose*.yml
production env/deployment/routing files
```

## 3. MCP contract

Stage 9 adds:

```text
McpExposureMode
McpToolInputSchema
McpToolOutputSchema
McpExposurePolicy
McpToolDescriptor
McpExposureManifest
McpExposureRegistry
McpToolAdapter
```

Every exposed descriptor is required to preserve:

```text
read_only = true
requires_authorization = true
supports_mutation = false
exposes_raw_infra = false
default_enabled = false
isolated_runtime_required = true
```

The MCP name is identical to the native Stage 5 capability name. Stage 9 does not create aliases.

## 4. Allowed capabilities

The Stage 9 allowlist is exactly:

```text
knowledge.search
knowledge.expand
evidence.inspect
evidence.verify
runtime.get_trace
runtime.get_budget
runtime.get_health
```

Canonical enabled manifests are deterministic and sorted.

Unknown capabilities are rejected even if they satisfy the generic `domain.action` name shape.

## 5. Default-off and isolated-runtime policy

Default policy:

```text
enabled = false
isolated_runtime = false
isolated_runtime_required = true
allow_network_server = false
allow_mutation = false
```

Result:

```text
default policy -> zero active MCP descriptors
```

An enabled policy is constructible only when:

```text
enabled = true
isolated_runtime = true
```

Network-server and mutation policy widening fail closed.

No production env flag is read or written by Stage 9. This stage defines the policy/descriptor boundary only.

## 6. Authorization and Stage 5 validation preservation

`McpToolAdapter` accepts a `ToolRegistry` and resolves native capabilities through:

```text
ToolRegistry.resolve()
```

before converting them to MCP-safe descriptors.

There is no public raw-`ToolDescriptor` adapter entrypoint in the Stage 9 exposure module.

Stage 9 rechecks:

```text
native allowlist
read_only
requires_authorization
supports_mutation
exposes_raw_infra
forbidden raw payload field names
```

Stage 9 never grants authorization. Authorization remains an external caller / future policy-engine responsibility.

## 7. Descriptor privacy and raw-infrastructure protection

The MCP descriptor exposes contract metadata only:

```text
contract class name
sorted field names
risk class
read-only/auth/mutation/raw-infra flags
```

It does not expose runtime payload values, raw query, raw answer, evidence/source bodies, provider prompts, filesystem paths, object keys, credentials, environment values, SQL, or backend endpoints.

Forbidden names/prefixes include release, ingestion, workspace, memory, agent, skill, raw tool invocation, Qdrant, R2, SQLite, admin mutation, Docker, filesystem, process, shell, env, secret, and credential namespaces.

The denylist contains raw backend terms only as rejection constants; no backend implementation is imported or wired.

## 8. No execution/server surface

Stage 9 intentionally has no API named:

```text
run_tool
execute_tool
invoke_tool
call_provider
start_server
listen
serve
run
execute
invoke
```

`McpToolAdapter.adapt()` is descriptor conversion only. It does not call a provider.

There is no MCP transport dependency and no network server.

## 9. Stage 7 / Stage 8 boundary

Stage 9 does not import:

```text
m27_skill_contracts
m27_workspace_contracts
m27_workspace_store
```

It does not expose:

```text
skill.*
workspace.*
skill.execute
workspace.write
workspace.read_raw
```

Stage 7 remains descriptive-plan-only.

Stage 8 remains an isolated artifact/state store and is not read or written through MCP.

## 10. Explicit forbidden capability tests

Negative tests cover at least:

```text
release.promote
release.rollback
ingestion.finalize
ingest-and-update-knowledge
promote-knowledge-release
workspace.write
workspace.read_raw
memory.read
memory.write
agent.run
skill.execute
tool.invoke_raw
qdrant.raw_search
r2.raw_get
sqlite.raw_query
admin.mutate
docker.ps
filesystem.read
process.list
shell.exec
env.dump
secret.read
credential.read
```

All are rejected.

## 11. Focused gate

Compile:

```bash
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

Focused pytest:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_mcp_contracts.py \
  tests/test_m27_mcp_exposure.py
```

Result:

```text
45 passed in 0.51s
```

Focused Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m27_mcp*.py \
  tests/test_m27_mcp*.py
```

Result:

```text
All checks passed!
```

One import-order issue was found on the first Ruff pass and fixed mechanically with Ruff before the final green gate. No behavior code changed in that formatting fix.

## 12. Safe regression gate

Command population matched the Stage 9 handoff:

```text
5 M26 safe baseline test files
Stage 1 through Stage 8 M27 test files
Stage 9 MCP tests
```

Result:

```text
278 passed, 1 warning in 11.64s
```

The warning is the pre-existing FastAPI/Starlette TestClient deprecation warning.

M27 Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m27_*.py \
  tests/test_m27_*.py
```

Result:

```text
All checks passed!
```

Known M26 lint gate:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m26_aq_semantic_contract.py \
  --ignore F841
```

Result:

```text
All checks passed!
```

No full523, Docker build, container restart, or production invocation was run.

## 13. Behavior impact

```text
M26 answer behavior change: NONE
M27 answer path change: NONE
retrieval behavior change: NONE
verification behavior change: NONE
provider calls added: NONE
tool execution added: NONE
skill execution added: NONE
workspace MCP exposure added: NONE
memory runtime added: NONE
network listener/server added: NONE
production mutation authority added: NONE
```

## 14. Remaining risks

1. This is a descriptor/manifest boundary only. A future live MCP transport or provider runner must undergo a separate authorization, isolation, privacy, and production-safety review.
2. MCP contract schemas intentionally expose class/field metadata rather than a live JSON-RPC execution schema. Future transport binding must preserve the same body-free metadata boundary.
3. Stage 5 knowledge providers remain dependency-injected abstractions with no live implementation in this stage.
4. The policy object is explicit Python configuration. A later Master-controlled integration may bind it to isolated runtime flags, but Stage 9 itself intentionally does not edit feature-flag or env files.

None of these risks blocks Stage 9 descriptor-boundary integration.

## 15. Production safety

```text
production touched: NO
production restarted: NO
production routes changed: NO
production credentials used: NO
production R2/Qdrant/SQLite writes: NO
M26 answer path touched: NO
Stage 7 execution authority added: NO
Stage 8 workspace exposure added: NO
```

## Verdict

```text
M27_STAGE9_MCP_EXPOSURE: READY_FOR_MASTER_INTEGRATION
PRODUCTION_ENABLEMENT: NOT_APPLICABLE
```
