# M27 Stage 5 Read-only Tool / Capability Registry Report

Date: 2026-10-03
Branch: `m27/stage5-readonly-tools`
Base: `5a0c6cc7`

## 1. Files changed

Created:

```text
src/knowledge_engine/m27_tool_contracts.py
src/knowledge_engine/m27_tool_registry.py
src/knowledge_engine/m27_readonly_tools.py

tests/test_m27_tool_contracts.py
tests/test_m27_tool_registry.py
tests/test_m27_readonly_tools.py

docs/m27/research/stage5_readonly_tool_registry_report.md
```

Not modified:

```text
src/knowledge_engine/m27_context_runtime_contracts.py
src/knowledge_engine/m27_compute_policy*.py
all Stage 4 tests/reports
all m26_* production/core files
```

## 2. Tool contract

Stage 5 introduces a native, protocol-independent capability descriptor:

```text
ToolDescriptor
- name
- description
- domain
- read_only
- risk_class
- input_contract
- output_contract
- requires_authorization
- supports_network
- supports_mutation
- exposes_raw_infra
```

Descriptor construction validates structural shape. Stage 5 registry policy performs the actual read-only, authorization-boundary, namespace and raw-infrastructure rejection.

Input/output contracts are frozen dataclasses. Agent-facing output contracts contain domain IDs, counts, fixed status/code metadata and sanitized trace/evidence views. They do not contain raw query, raw answer, evidence bodies, source bodies, SQL, credentials, environment values, filesystem paths, object keys or raw admin endpoints.

## 3. Registry API

`ToolRegistry` provides:

```text
register(descriptor)
resolve(name)
list(domain=None)
describe(name)
len(registry)
```

It intentionally does not provide:

```text
invoke
execute
credential acquisition
authorization granting
network access
database/storage access
```

The registry is descriptor-only.

## 4. Registered domain capabilities

The first Stage 5 registry contains exactly:

```text
knowledge.search
knowledge.expand

evidence.inspect
evidence.verify

runtime.get_trace
runtime.get_budget
runtime.get_health
```

No live production knowledge backend is wired.

`knowledge.search` and `knowledge.expand` terminate at a dependency-injected `KnowledgeProvider` Protocol boundary. Stage 5 ships no live implementation and starts no retrieval loop.

`evidence.inspect` is defined over the existing Stage 3 `EvidencePlanningResult` / `EvidenceIdentity` boundary.

`evidence.verify` inspects an already-produced `VerificationDecision`; it does not rerun the verifier or answer path.

`runtime.get_trace` is defined over the existing sanitized M27 `DecisionTraceEvent`.

`runtime.get_budget` exposes only normalized compute/budget classes already present in sanitized trace metadata. It does not depend on Stage 4 files and does not import a parallel ComputePolicy implementation.

`runtime.get_health` reduces an already-produced health mapping to overall status, freshness and sanitized dependency status rows. It drops request IDs, detail strings, expected/observed identities, maintenance payloads and control-plane/private fields.

## 5. Risk metadata

Every registered tool has explicit metadata and is mechanically inspectable.

Stage 5 risk classes:

```text
DOMAIN_METADATA_READ
EVIDENCE_METADATA_READ
RUNTIME_OBSERVABILITY_READ
```

All seven descriptors currently declare:

```text
read_only = true
requires_authorization = true
supports_network = false
supports_mutation = false
exposes_raw_infra = false
```

`supports_network=false` describes the Stage 5 implementation state. A later authorized provider may require separately reviewed network-backed read access, but Stage 5 does not provide or imply it.

## 6. Read-only enforcement

The registry rejects descriptors when any of these are true:

```text
read_only != true
supports_mutation != false
exposes_raw_infra != false
requires_authorization != true
```

This is registry policy rather than a convention.

The native registry cannot execute capabilities. Therefore registration itself cannot mutate external state.

## 7. Forbidden capability rejection

The hard-forbidden capabilities are rejected:

```text
release.promote
release.rollback
ingestion.finalize

qdrant.raw_search
r2.raw_get
sqlite.raw_query

admin.mutate
```

Equivalent domain-boundary violations are also rejected by namespace/action token policy. Deterministic tests cover examples including:

```text
knowledge.raw_search
knowledge.qdrant_search
runtime.sqlite_query
evidence.admin_update
runtime.release_rollback
runtime.shell_exec
```

The registry also rejects duplicate registration, unknown resolution, malformed namespace/domain combinations, write descriptors, mutation descriptors, raw-infrastructure descriptors and descriptors attempting to remove the authorization requirement.

## 8. Authorization boundary

Stage 5 does not implement a new PolicyEngine and does not claim any actor is authorized.

The boundary is:

```text
registry describes capability
registry requires authorization metadata
registry does not grant authorization
provider Protocol does not create authorization
future caller / PolicyEngine must authorize before provider use
```

There is no `authorized=True` shortcut and no embedded production credential path.

## 9. Infrastructure hiding guarantees

Agent-facing capability names are limited to the domains:

```text
knowledge.*
evidence.*
runtime.*
```

The Stage 5 implementation imports no Qdrant, R2, SQLite, production object-store, admin-health route, Docker/process-control or release actuator implementation.

Tool outputs do not expose:

```text
Qdrant collection internals
R2 object/pointer internals
SQLite file paths
raw SQL
production credentials
raw HTTP admin endpoints
release CAS actuator
filesystem/process/Docker control
```

A runtime health view may carry a sanitized dependency key and status, but not the dependency's raw identity, endpoint, path, credentials, query, collection/object internals or detail payload.

## 10. Privacy guarantees

Stage 5 contracts and adapters are intentionally body-free.

The knowledge input used by deterministic Stage 5 tests is an opaque sanitized `request_token`, not raw query text.

Knowledge outputs contain only sanitized domain identifiers and counts.

Evidence outputs reuse Stage 3 identity/count/gap metadata and never copy passage text, source text, exact quotes or compiled context.

Verification output copies only safe status/count/boolean/code fields from an already-produced verification decision.

Runtime trace/budget output reuses the fixed Stage 1 sanitized trace shape.

Runtime health output discards request IDs, detail strings, expected/observed resource identity values, maintenance/private payloads and provenance internals.

No private test marker is emitted by the registry.

## 11. Exact tests/results

Compile:

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage5-tools
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

Stage 5 focused tests:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage5-tools/src   /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m27_tool_contracts.py   tests/test_m27_tool_registry.py   tests/test_m27_readonly_tools.py
```

Result after the one registry namespace/domain fix:

```text
34 passed
```

Required Stage 1-5 M27 gate:

```bash
PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage5-tools/src   /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m27_context_runtime_contracts.py   tests/test_m27_legacy_m26_adapters.py   tests/test_m27_decision_trace.py   tests/test_m27_replay_harness.py   tests/test_m27_equivalence_report.py   tests/test_m27_evidence_planner.py   tests/test_m27_context_evidence_boundary.py   tests/test_m27_tool_contracts.py   tests/test_m27_tool_registry.py   tests/test_m27_readonly_tools.py
```

Result:

```text
97 passed in 2.22s
```

Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check   src/knowledge_engine/m27_tool_*.py   src/knowledge_engine/m27_readonly_tools.py   tests/test_m27_tool_*.py   tests/test_m27_readonly_tools.py
```

Result:

```text
All checks passed!
```

No full 523 was run.
No Docker build was run.
No production invocation was run.

## 12. Behavior impact

```text
M26 answer behavior change: NONE
retrieval behavior change: NONE
verification behavior change: NONE
publication behavior change: NONE
runtime route change: NONE
production data mutation: NONE
```

Stage 5 adds native contracts, registry policy, pure sanitized views and dependency-injected provider Protocols only.

## 13. Blockers

```text
NONE
```

No shared contract modification was required.

No Stage 4 file modification was required.

No M26 core modification was required.

## 14. Remaining risks

1. `knowledge.search` / `knowledge.expand` are shape/provider boundaries only. A future live read-only provider still requires explicit authorization/policy integration and separate safety review.
2. `runtime.get_health` currently sanitizes an already-produced mapping. Any future live wiring must preserve this reducer and must not expose the richer M26 admin payload directly.
3. Stage 4 is running in parallel, so Stage 5 intentionally does not import a Stage 4 compute-policy object. `runtime.get_budget` uses the already-stable sanitized trace budget metadata. Master can integrate a future normalized Stage 4 view without changing the registry namespace.
4. Stage 6 may eventually need a provider-specific query-bearing contract. Raw query access, if required, must be introduced only inside the authorized KnowledgeProvider boundary and must not be copied into registry output, traces or reports.
5. Registry token rejection is deliberately conservative. New capabilities should be reviewed rather than weakened through aliases that resemble storage/admin/write operations.

## 15. Production untouched

```text
production touched: NO
production restarted: NO
production routes changed: NO
production credentials used: NO
production R2/Qdrant/SQLite writes: NO
```

## 16. Stage 6 readiness

Stage 6 can use the stable native names:

```text
knowledge.search
knowledge.expand
evidence.inspect
```

without importing or exposing raw Qdrant/R2/SQLite interfaces.

Stage 5 does not itself perform bounded iterative retrieval. Stage 6 remains responsible for retrieval-round policy, maximum rounds, evidence-gap decisions, deadline/compute interaction and verifier-preserving behavior.

Stage 6 readiness:

```text
READY_FOR_MASTER_INTEGRATION
```

## 17. Future MCP compatibility without MCP dependency

The registry is native Python and protocol-independent.

Future Stage 9 MCP can wrap:

```text
ToolRegistry descriptors
+ authorized provider implementations
```

without changing the native capability names.

Stage 5 contains:

```text
MCP server: NO
MCP schema: NO
MCP client: NO
MCP adapter: NO
MCP transport dependency: NO
```

The dependency direction remains:

```text
native Tool / Capability Registry
        ^
        |
future MCP adapter
```

not the reverse.

## Required yes/no answers

```text
Can any registered Stage 5 tool mutate state?
NO

Can any tool expose raw Qdrant/R2/SQLite infrastructure?
NO

Can registry itself grant authorization?
NO

Did Stage 5 introduce MCP?
NO

Did Stage 5 start iterative/agentic retrieval?
NO
```
