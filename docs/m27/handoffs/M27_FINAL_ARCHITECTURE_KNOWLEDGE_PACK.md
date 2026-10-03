# M27 Final Architecture Knowledge Pack

This document is the full master knowledge pack for M27. It is intended for the next Master Session so it can orchestrate all sub-sessions without relying on the retired discussion session.

## 0. Non-negotiable framing

M27 is **not** a rewrite of M26 into a generic agent.

M27 is:

```text
Context-Native Adaptive AI Runtime
```

Goal:

```text
minimum sufficient trustworthy context
+
minimum sufficient test-time compute
+
deterministic governance
+
fully isolated M27 runtime lab
```

The current production M26 system remains stable and untouched. M27 must run in a separate isolated environment until it beats or matches M26 through explicit gates.

Core principle:

```text
Agent proposes.
Infrastructure enforces.
```

This applies to retrieval, evidence, citations, verification, release, rollback, memory, learning, and meta-harness changes.

## 1. Current verified state

```text
workspace:
/home/ubuntu/LLM_Wiki-m27-context-runtime

branch:
m27/context-native-runtime-spec
```

Current production:

```text
container: llm_wiki-knowledge-engine-1
image: knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z
status: healthy
port: 127.0.0.1:8080->8080/tcp
```

M27 isolated runtime:

```text
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
status: healthy
port: 127.0.0.1:18080->8080/tcp
```

Already completed:

```text
Stage 0C: source reconciliation done
Stage 0D: isolated runtime health + safe gate done
source-equivalent to production image: yes
safe Stage 1 gate: 49 passed
Stage 1 no-blocker handoff: exists
```

Key documents:

```text
docs/m27/research/03_blocker_register.md
docs/m27/research/05_no_blocker_handoff.md
docs/m27/research/07_production_invariant_registry.md
docs/m27/research/09_remaining_blocker_burndown_plan.md
docs/m27/research/10_stage0d_blocker_closeout_report.md
docs/m27/handoffs/MASTER_SESSION_HANDOFF_STAGE1_TO_STAGE2.md
```

## 2. Production isolation rule

M27 must not mutate current production.

Forbidden unless owner explicitly approves a later promotion session:

```text
- restarting llm_wiki-knowledge-engine-1
- changing nginx / Cloudflare / public routes
- binding M27 to production port 8080
- changing production R2 active pointer
- mutating production Qdrant aliases or collections
- writing production QA sqlite
- writing production admin audit sqlite
- using production write-capable credentials
- exposing release.promote / release.rollback as agent-facing tools
- changing current production answer path
```

M27 may use:

```text
- isolated source branch
- isolated image tag
- isolated container
- isolated port 18080
- isolated env .env.m27, git ignored
- isolated volume / cache / quota DB
- read-only fixture or copied data
```

If a sub-session is unsure whether an operation touches production, it must stop and report to Master.

## 3. Source-of-truth lesson

A major blocker was discovered and cleared:

```text
M27 clean branch was not the current production source.
```

The production image contained production-only modules absent from the clean branch. Stage 0C reconciled M27 source with the production image.

The M27 branch now includes production-only modules such as:

```text
m26_console_api.py
m26_admin_*.py
m26_ingestion_*.py
m26_qa_inbox_integration.py
m26_production_promotion.py
m26_jobs_rollback_api.py
m26_daily_ip_rate_limit.py
qa_answer_quality*.py
suggested_questions*.py
```

Production entrypoint is:

```text
knowledge_engine.m26_console_api:app
```

not merely:

```text
knowledge_engine.m26_public_api:app
```

Master must remember this when selecting insertion points.

## 4. Existing M26 runtime is already partly M27-shaped

Do not rebuild these from scratch. Extract, normalize, and wrap them.

Existing M26 already has:

```text
Context Planner embryo:
- SemanticRoutingDecision
- _routing_decision
- _fast_failure_route
- _semantic_failure_route
- low-information retry decisions

Compute Policy embryo:
- deadline_remaining_ms
- route_minimum_budget_ms
- provider_attempts_remaining
- dense deadline and provider-call budget logic

Context Compiler embryo:
- m26_context_compiler.py
- context manifest
- token budget
- evidence binding
- prompt-injection isolation
- mandatory evidence preservation

Evidence Planner / Retrieval embryo:
- lexical retrieval
- dense retrieval
- graph expansion
- evidence strengthening
- rerank / diversity / facet coverage
- dynamic evidence budget

Verification spine:
- semantic requirements
- citation gate
- support proof
- safe abstention
- unsupported material claim protection
- generic fallback guard
```

Therefore M27 must be:

```text
extract / normalize / wrap existing M26 behavior
```

not:

```text
build a parallel context runtime beside M26
```

## 5. Final target architecture

```text
M27 Isolated Context-Native Adaptive AI Runtime
│
├── Runtime Harness
│   └── initially existing M26 runtime loop formalized as adapter
│
├── Context Planner
│   └── extracted from M26 semantic routing
│
├── ComputePolicy
│   └── Test-Time Compute Optimization
│
├── Evidence Planner
│   └── retrieval, gap inspection, source/evidence planning
│
├── Context Compiler
│   └── generalized from m26_context_compiler.py
│
├── Verifier
│   └── existing M26 verification spine
│
├── Tool / Capability Registry
│   └── native first, MCP later
│
├── Skill Runtime
│   └── ops skills first, answer path later if ever
│
├── Workspace
│   └── isolated task state / artifacts / reports
│
├── Memory Runtime
│   └── candidate-only, later stage
│
├── Eval / Governance
│   └── quality, latency, citation, unsupported claim gates
│
└── Learning Plane
    │
    ├── Autonomous Agent Learning
    │   ├── skill policy learning
    │   ├── retrieval policy learning
    │   ├── compute policy learning
    │   ├── routing policy learning
    │   └── memory policy learning
    │
    └── Meta-Harness Engineering
        ├── candidate harness generation
        ├── isolated branch / patch generation
        ├── eval report
        └── promotion proposal only
```

Underneath M27 remains the deterministic data/governance plane:

```text
Qdrant / R2 / lexical / graph / release
ACL / provenance / citation / rollback / audit
```

This layer is not agentized.

## 6. Three advanced capabilities and where they live

### Test-Time Compute Optimization

This is core M27 and should appear relatively early.

It should become:

```text
ComputePolicy
```

It controls:

```text
- model/provider call budget
- retrieval rounds
- repair route allowance
- verification depth
- context budget
- deadline budget
- provider attempt budget
- safe abstention threshold
```

First implementation:

```text
LegacyM26DeadlineBudgetAdapter
```

Then:

```text
RuleBasedComputePolicy
FAST / STANDARD / DEEP / FAIL_CLOSED
```

Eventually:

```text
LearnedComputePolicy
```

Do not add Jev as the first ComputePolicy. Jev can later shadow-predict existing decisions.

### Autonomous Agent Learning

This belongs in the Learning Plane and is candidate-only.

It may learn or propose:

```text
- skill improvements
- retrieval policy changes
- compute threshold changes
- routing threshold changes
- tool description improvements
- memory retention policy
- failure clusters
```

Allowed flow:

```text
trace / eval result
↓
failure mining
↓
candidate proposal
↓
isolated eval
↓
report
↓
human / deterministic gate
```

Forbidden flow:

```text
agent learns
↓
auto writes production
```

### Meta-Harness Engineering

This is the last stage and must never directly edit live production.

Allowed:

```text
Harness vN
↓
trace + eval + failure reports
↓
Meta-Harness optimizer
↓
candidate harness vN+1 branch / patch
↓
full regression / eval
↓
promotion proposal only
```

Forbidden:

```text
production runtime rewrites itself
production deploys itself
```

## 7. Durable architecture vs replaceable technologies

Durable primitives:

```text
Context
Knowledge
Memory
Skills
Workspace
Capabilities
Harness
Policy
Evaluation
Provenance
Compute allocation
Learning loop
```

Replaceable technologies:

```text
MCP
Jev
Qdrant
specific reranker
specific embedding model
OpenAI / Anthropic / Google SDKs
LangGraph / Agents SDK / Claude SDK
specific Skill syntax
```

Core code should depend on contracts/providers, not vendor SDKs.

Desired abstraction families:

```text
ModelProvider
DecisionProvider
KnowledgeProvider
ToolProvider
CapabilityProvider
SkillProvider
MemoryProvider
WorkspaceStore
TraceStore
ComputePolicy
PolicyEngine
Evaluator
Harness
```

## 8. Production invariants

These cannot regress.

```text
1. Generic extractive fallback cannot become user-facing.
2. Bad templates must stay blocked.
3. Unsupported material claims must fail closed / repair / abstain.
4. No unverified material answer text should stream as final answer.
5. Citation binding must remain strict.
6. Evidence IDs and source bindings must remain deterministic.
7. Owner/public admission must remain enforced.
8. Rate-limit and owner bypass behavior must not regress.
9. QA capture must not leak secrets or raw sensitive data.
10. Production R2 pointer cannot be changed by M27.
11. Production Qdrant aliases cannot be changed by M27.
12. Production sqlite files cannot be written by M27.
13. Release promotion / rollback cannot be agent-facing in early stages.
14. M27 feature flags default off.
15. M27 can be killed without affecting production.
```

Known guard that must not be undone:

```python
# Guard: do not emit generic extractive evidence fallback as user-facing answer.
return None
```

## 9. Stage plan

Already done:

```text
Stage 0C: source reconciliation
Stage 0D: isolated runtime health + safe gate
```

Core MVP stages:

```text
Stage 1: Adapter-only Contracts + Decision Trace
Stage 2: Replay / Equivalence Harness
Stage 3: Context / Evidence Boundary Extraction
Stage 4: ComputePolicy / Test-Time Compute Optimization
Stage 5: Read-only Tool / Capability Registry
Stage 6: Bounded Agentic Retrieval
```

Full architecture stages:

```text
Stage 7: Ops Skills Runtime
Stage 8: Workspace
Stage 9: MCP Exposure
Stage 10: Memory Runtime
Stage 11: Autonomous Agent Learning
Stage 12: Meta-Harness Engineering
```

Core MVP = Stage 1–6.

Full 2027-style architecture = Stage 1–12.

## 10. Parallelization rules

Can run in parallel after Master approval:

```text
Stage 1A: Contracts + LegacyM26 adapters
Stage 1B: Decision Trace + Feature Flag
Stage 2: Replay/equivalence harness
Stage 4: ComputePolicy shadow logic
Stage 5: Tool Registry
Stage 7: Ops Skills
Stage 8: Workspace
Stage 9: MCP, after Tool Registry is stable
Stage 10: Memory, late only
Stage 11/12 research-only lab work, late only
```

Must remain single-threaded or master-controlled:

```text
Answer behavior changes
Retrieval behavior changes
Verification behavior changes
Publication path changes
m26_aq_semantic_contract.py major changes
m26_pa7_arbitrary_query_runtime.py major changes
m26_public_api.py changes
m26_context_compiler.py behavior changes
release / rollback / promotion changes
```

Heavy eval / full 523 / docker build should not run in many sessions at once due VM constraints.

Recommended active load:

```text
coding sub-sessions: 2–3 max
heavy eval runner: 1 max
master integration: always single source of truth
```

## 11. Expected benefits

Success rate:

```text
Stage 1–3: no regression expected, not direct improvement.
Stage 4: possible small improvement, mostly latency/control benefit.
Stage 6: strongest direct success-rate improvement potential.
Stage 7+: indirect improvement through better debugging, skills, learning, and faster failure repair.
```

Latency:

```text
p50 likely improves after ComputePolicy / FAST path.
p95 will not automatically improve and may rise if bounded agentic retrieval is too loose.
Keep strict max rounds, provider budget, and hard deadline.
Target: p50 down, p95 <= current production baseline, complex success up without p95 explosion.
```

Functionality:

```text
- decision trace
- replay harness
- compute tier observability
- tool registry
- ops skills
- workspace
- MCP exposure
- candidate memory
- learning proposals
- meta-harness candidate patches
```

## 12. Stage 1 immediate work

The next Master Session should launch exactly two sub-sessions first.

### Sub-session A: Stage 1 Contracts + LegacyM26 Adapters

Files expected:

```text
src/knowledge_engine/m27_context_runtime_contracts.py
src/knowledge_engine/m27_legacy_m26_adapters.py
tests/test_m27_context_runtime_contracts.py
tests/test_m27_legacy_m26_adapters.py
docs/m27/research/stage1_subsession_A_report.md
```

Allowed:

```text
- Protocol/dataclass definitions
- LegacyM26 adapters
- tests proving adapter shape
```

Forbidden:

```text
- behavior changes
- calling new LLM providers
- adding Jev/MCP/Memory
- touching production
```

### Sub-session B: Stage 1 Decision Trace + Feature Flag

Files expected:

```text
src/knowledge_engine/m27_decision_trace.py
src/knowledge_engine/m27_feature_flags.py
tests/test_m27_decision_trace.py
docs/m27/research/stage1_subsession_B_report.md
```

Allowed:

```text
- sanitized trace schema
- feature flag default off
- unit tests proving no raw query/answer/full evidence/secret
```

Forbidden:

```text
- changing answer output
- changing public API behavior
- emitting traces by default
- storing raw sensitive fields
```

Feature flag:

```text
M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED=false
```

## 13. Required sub-session report format

Every sub-session must create a report:

```text
docs/m27/research/stageX_subsession_<ID>_report.md
```

It must include:

```text
1. Summary of files changed
2. Exact behavior impact
3. Feature flags added/used
4. New contracts/dataclasses/protocols
5. Trace privacy guarantees, if relevant
6. Tests run with exact command and output summary
7. Blockers encountered and status
8. Remaining risks
9. Suggested next step
10. Confirmation production was untouched
```

Master rule:

```text
No report -> no merge.
No tests -> no merge.
No production-safety confirmation -> no merge.
Unclear behavior impact -> no merge.
```

## 14. Stage 1 master integration gate

After Stage 1 A/B reports arrive, Master must run at least:

```bash
cd /home/ubuntu/LLM_Wiki-m27-context-runtime
source .venv/bin/activate
pytest -q \
  tests/test_m26_canonical_runtime_reachability.py \
  tests/test_m26_deadline_aware_semantic_routing.py \
  tests/test_m26_public_api.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_aq_surface_guard.py \
  tests/test_m27_context_runtime_contracts.py \
  tests/test_m27_legacy_m26_adapters.py \
  tests/test_m27_decision_trace.py
curl -sS -i http://127.0.0.1:18080/v1/health | head -40
docker ps --filter name=llm_wiki-knowledge-engine-1 --format "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"
docker ps --filter name=llm_wiki-m27-context-runtime-1 --format "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"
```

Expected:

```text
M26 safe baseline tests pass
M27 tests pass
M27 health 200
production healthy
no production changes
```

Only after this can Master issue Stage 2 handoff.

## 15. Stage 2 purpose

Stage 2 is Replay / Equivalence Harness.

It compares:

```text
M26 behavior
vs
M27 adapter-normalized decisions
```

It still must not change answer output.

Compare:

```text
- status class
- route / route reason
- compute/budget classification
- selected evidence count
- citation shape
- safe abstention behavior
- provider call count/budget
- generic fallback guard
- bad template guard
```

Stage 2 output should be:

```text
replay/equivalence report
fixture coverage report
remaining drift classification
```

## 16. Known deferred item

Full legacy arbitrary semantic expectation tests are not Stage 1 blockers:

```text
tests/test_m26_pa_7_arbitrary_query_runtime.py
```

After production source reconciliation, several legacy expectations still expect “repair into cited answer,” while current reconciled source often safe-abstains more conservatively. Do not loosen runtime to satisfy old expectations without explicit Stage 2/Stage 6 review.

Treat this as:

```text
DEFERRED_OUTSIDE_STAGE1
```

Needs calibration before behavior-changing retrieval/answer work.

## 17. What not to do next

Do not start:

```text
- Jev
- MCP
- Memory
- Agent loop
- Learning Plane
- Meta-Harness
- Bounded agentic retrieval
- production promotion tools
```

until Stage 1 and Stage 2 gates are clean.

## 18. Master session mission

The next Master Session is not a coder-only session. It is the orchestrator.

It must:

```text
1. Read this pack.
2. Read MASTER_SESSION_HANDOFF_STAGE1_TO_STAGE2.md.
3. Launch sub-session A and B only.
4. Require reports from each sub-session.
5. Inspect reports and changed files.
6. Run integration gates itself.
7. Commit only after tests pass.
8. Then generate Stage 2 sub-session handoff.
```

Master should not outsource production-safety judgment.

## 19. Final mental model

M26 is a strong, production-hardened governed knowledge runtime.

M27 should make it:

```text
contract-based
context-native
adaptive-compute-aware
provider-replaceable
fully observable
skill/tool/workspace capable
candidate-learning capable
meta-harness-ready
```

But all of this grows from M26, not around it.

The first move is not to build a new brain. The first move is to expose the existing nervous system cleanly, then add new reflexes one by one.
