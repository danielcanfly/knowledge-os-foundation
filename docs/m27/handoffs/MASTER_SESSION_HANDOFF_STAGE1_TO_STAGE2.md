# M27 Master Session Handoff｜Stage 1 → Stage 2 Orchestration

Date: 2026-10-03
Branch: `m27/context-native-runtime-spec`
Current confirmed commit before this handoff: `d8510d20`

## Mission

You are the new **M27 Master Session**.

Your job is not to build random agent features. Your job is to orchestrate M27 in controlled waves, dispatch sub-sessions only when boundaries are stable, integrate their work, run gates, and decide when the system may advance to the next stage.

M27 is an isolated runtime lab. Current production must remain untouched.

## Current state

### Production

```text
container: llm_wiki-knowledge-engine-1
image: knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z
status: healthy
port: 127.0.0.1:8080->8080/tcp
```

Production must not be restarted, routed, or mutated by M27 work.

### M27 isolated runtime

```text
workspace: /home/ubuntu/LLM_Wiki-m27-context-runtime
branch: m27/context-native-runtime-spec
latest known commit: d8510d20
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
status: healthy
port: 127.0.0.1:18080->8080/tcp
```

### Cleared prerequisites

```text
Stage 0C source reconciliation: done
Stage 0D isolated runtime health: done
M27 package source equivalence to production image: done
safe Stage 1 gate: 49 passed
Stage 1 no-blocker handoff: created
```

Important files:

```text
docs/m27/research/03_blocker_register.md
docs/m27/research/05_no_blocker_handoff.md
docs/m27/research/07_production_invariant_registry.md
docs/m27/research/09_remaining_blocker_burndown_plan.md
docs/m27/research/10_stage0d_blocker_closeout_report.md
```

## Non-negotiable production safety rules

```text
1. Do not modify current production container.
2. Do not restart current production container.
3. Do not change nginx / Cloudflare / public routes.
4. Do not write production R2 pointers.
5. Do not mutate production Qdrant aliases or collections.
6. Do not write production QA/admin/rate-limit SQLite.
7. Do not use production write-capable credentials in M27.
8. Do not expose secrets, env values, API keys, tokens, or hashes.
9. Do not introduce behavior-changing answer path work before its assigned stage.
10. All M27 behavior must remain isolated behind the M27 branch/container/env.
```

## Architecture truth

M27 is not a rewrite of M26 into an agent.

M27 is:

```text
Context-Native Adaptive AI Runtime
= minimum sufficient trustworthy context
+ minimum sufficient compute
+ deterministic governance
+ isolated future learning plane
```

M26 is the deterministic knowledge/evidence/verification/data plane. M27 should extract, normalize, and wrap M26 behavior before attempting to enhance it.

Core principle:

```text
Agent proposes.
Infrastructure enforces.
```

### High-level target architecture

```text
M27 Isolated Runtime
│
├── Runtime Harness
│   └── initially existing M26 runtime loop
│
├── Context Planner
│   └── initially LegacyM26SemanticRoutingAdapter
│
├── ComputePolicy
│   └── initially LegacyM26DeadlineBudgetAdapter
│
├── EvidencePlanner
│   └── initially existing M26 retrieval/evidence machinery
│
├── ContextCompiler
│   └── initially existing m26_context_compiler + context manifest behavior
│
├── Verifier
│   └── existing semantic/citation/support proof gates
│
├── Tool Registry
│   └── read-only native tools first, MCP later
│
├── Skills
│   └── ops skills first, no public-answer replacement first
│
├── Workspace
│   └── isolated task state/artifacts/checkpoints
│
├── Memory
│   └── candidate-only, later
│
└── Learning Plane
    ├── Autonomous Agent Learning, candidate-only
    └── Meta-Harness Engineering, isolated lab only
```

## Stage overview and parallelization plan

| Stage | Name | Core task | Parallelizable? | Suggested owner model | Gate to advance |
|---:|---|---|---|---|---|
| 0C | Source reconciliation | Align M27 source to production image | Done | Done | source diff 0 |
| 0D | Isolated readiness | Healthy M27 isolated env + safe tests | Done | Done | health 200 + 49 passed |
| 1 | Adapter-only contracts + decision trace | Add contracts, LegacyM26 adapters, sanitized trace, default-off flag | Partially | Master + 2 sub-sessions max | behavior unchanged, safe gates pass |
| 2 | Replay / equivalence harness | Compare M26/M27 adapter decisions and traces | Yes | Dedicated sub-session after Stage 1 | equivalence report generated, no unresolved blockers |
| 3 | Context/Evidence boundary extraction | Separate EvidencePlanner vs ContextCompiler responsibilities | Limited | Single primary coder + test/docs helper | context manifest/citations stable |
| 4 | ComputePolicy shadow | Formalize test-time compute signals and FAST/STANDARD/DEEP shadow tiering | Yes after Stage 1 contracts freeze | Dedicated sub-session | no behavior change unless flag, latency budget trace stable |
| 5 | Read-only Tool Registry | Native read-only domain tools, no MCP yet | Yes | Dedicated sub-session | read-only tools pass, no infra leak |
| 6 | Bounded agentic retrieval | max 2 retrieval rounds, evidence-gap driven, same verifier | No for core code | Master only; sub-sessions can run eval/failure analysis | success ↑ on gap cases, no p95 explosion |
| 7 | Ops Skills Runtime | investigate-answer-failure, diagnose-latency, run-quality-gate | Yes | Skill sub-sessions | skills produce reports/candidates only |
| 8 | Workspace | Isolated workspace for task state/artifacts/checkpoints | Yes | Infrastructure sub-session | isolated path, no prod writes |
| 9 | MCP exposure | Read-only MCP adapters over stable ToolProvider | Yes, after Stage 5 | Adapter sub-session | MCP off does not affect native runtime |
| 10 | Memory Runtime | candidate-only episodic/project memory | Yes, late only | Separate sub-session | memory never overrides cited knowledge |
| 11 | Autonomous Agent Learning | proposal generation from traces/evals | Research parallel only | Research sub-session | candidate-only, eval required |
| 12 | Meta-Harness Engineering | candidate harness patch/eval/report lab | Research parallel only | Research sub-session | no auto-promotion |

## Immediate next move

Start **Stage 1**.

Recommended sub-sessions now:

```text
Sub-session A: Stage 1 Contracts + LegacyM26 adapters
Sub-session B: Stage 1 Decision Trace + Feature Flag + tests
```

Do not start Stage 2 until Stage 1 is merged and gated.

After Stage 1 completes, the master session must generate a Stage 2 handoff for a replay/equivalence sub-session.

## Stage 1 allowed files

Allowed to create:

```text
src/knowledge_engine/m27_context_runtime_contracts.py
src/knowledge_engine/m27_legacy_m26_adapters.py
src/knowledge_engine/m27_decision_trace.py
src/knowledge_engine/m27_feature_flags.py
tests/test_m27_context_runtime_contracts.py
tests/test_m27_legacy_m26_adapters.py
tests/test_m27_decision_trace.py
docs/m27/research/11_stage1_implementation_report.md
```

Allowed to minimally touch existing files only if absolutely necessary and with explanation:

```text
src/knowledge_engine/m26_aq_semantic_contract.py
src/knowledge_engine/m26_public_api.py
src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py
```

Preferred: do not touch these in Stage 1. Stage 1 should be adapter-only and trace-only.

Forbidden in Stage 1:

```text
production deployment files
nginx / Cloudflare config
production env files
release promote/rollback behavior
R2/Qdrant production pointers
MCP runtime
Jev provider
Memory runtime
Agent loop
Learning plane
Meta-Harness
```

## Stage 1 feature flag

Use:

```text
M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED=false
```

Default must be false.

When false, answer behavior must be unchanged.

When true, only emit/record sanitized decision trace inside M27 isolated runtime. No raw query, raw answer, secret, full evidence text, or private env value may be logged.

## Stage 1 contract expectations

Define protocols/dataclasses for:

```text
ContextPlan
ComputeDecision
EvidencePlan
ContextCompileResult
VerificationDecision
DecisionTraceEvent
RuntimeTraceStore
PolicyDecision
```

Implement adapters that read existing M26 outputs/signals but do not change behavior:

```text
LegacyM26SemanticRoutingAdapter
LegacyM26DeadlineBudgetAdapter
LegacyM26ContextCompilerAdapter
LegacyM26VerifierAdapter
```

If a signal is not yet available without invasive changes, mark it:

```text
unavailable_in_stage1
```

Do not invent fake signals.

## Stage 1 gates

Before Stage 1 is considered complete, run:

```bash
cd /home/ubuntu/LLM_Wiki-m27-context-runtime
python3 -m compileall -q src/knowledge_engine tests
.venv/bin/pytest -q \
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

Expected baseline before adding new Stage 1 tests:

```text
49 passed, 1 warning
```

## Stage 1 required report

Every Stage 1 sub-session must write a report before handoff:

```text
docs/m27/research/stage1_subsession_<A_or_B>_report.md
```

Report must include:

```text
1. Summary of files changed
2. Exact behavior impact: should be none
3. Feature flags added or used
4. New contracts / dataclasses / protocols
5. Trace privacy guarantees
6. Tests run with exact command and output summary
7. Blockers encountered and status
8. Remaining risks
9. Suggested next step
10. Confirmation production was untouched
```

The master session must not advance to Stage 2 until both sub-session reports are read and integrated.

## Stage 2 sub-session handoff template

Only issue this after Stage 1 passes gates.

```text
# M27 Stage 2｜Replay / Equivalence Harness Sub-session

You are Stage 2 replay/equivalence sub-session.

Prerequisite:
Stage 1 contracts + LegacyM26 adapters + sanitized decision trace are merged and green.

Mission:
Build a replay/equivalence harness that compares current M26 behavior against M27 adapter-normalized decisions without changing answer behavior.

Allowed files:
- src/knowledge_engine/m27_replay_harness.py
- src/knowledge_engine/m27_equivalence_report.py
- tests/test_m27_replay_harness.py
- tests/test_m27_equivalence_report.py
- docs/m27/research/stage2_replay_equivalence_report.md

Forbidden:
- production changes
- answer path behavior changes
- retrieval behavior changes
- Jev/MCP/Memory/Learning/Meta-Harness
- production credentials

Compare at minimum:
- response status class
- safe abstention vs cited answer vs error
- route / decision reason when available
- compute tier / budget signal when available
- selected evidence count, not full evidence text
- citation count and citation shape, not full source text
- provider call count / budget class when available
- bad-template guard outcome
- unsupported-claim guard outcome

Privacy:
Do not persist raw query, raw answer, full evidence text, secrets, env values, or private content.
Use stable hashes / counts / enums.

Required gates:
- compileall pass
- Stage 1 safe gate pass
- Stage 2 tests pass
- M27 isolated health 200
- production healthy

Required final report:
Write docs/m27/research/stage2_replay_equivalence_report.md with:
1. files changed
2. harness API
3. comparison fields
4. privacy guarantees
5. test commands/results
6. equivalence findings
7. blockers and mitigations
8. whether Stage 3 can start

Final response back to master:
M27_STAGE2_REPLAY_SUBSESSION_DONE
commit:
files changed:
tests:
blockers:
recommendation:
```

## Master integration rule

The master session must require each sub-session to give a construction report before advancing stages.

Advancement rule:

```text
No report → no merge.
No tests → no merge.
No production-safety confirmation → no merge.
Unclear behavior impact → no merge.
```

## Recommended current parallel plan

Start with exactly two sub-sessions:

```text
A. Stage 1 Contracts + LegacyM26 adapters
B. Stage 1 Decision Trace + Feature Flag
```

Do not start Stage 2 until A+B are merged and Stage 1 gates pass.

Do not start Stage 4/5 until Stage 1 contract shapes are stable.

Do not start Stage 6 until Stage 2 replay/equivalence exists.

## Current deferred non-blocker

`tests/test_m26_pa_7_arbitrary_query_runtime.py` has legacy semantic expectation drift under current production-reconciled source. It is not a Stage 1 blocker.

Reason: some tests expect invalid/unsupported provider outputs to be repaired into cited answers, while current production-reconciled behavior is more conservative and safe-abstains.

Do not weaken runtime to satisfy old expectations. Revisit before Stage 6 behavior-changing retrieval/answer work.

## Final reminder

M27 success is not “agent runs.”

M27 success is:

```text
current production stays stable
M27 isolated runtime stays healthy
contracts make behavior explicit
decision traces make future changes debuggable
compute policy makes resource use controllable
bounded retrieval improves complex success without p95 explosion
learning/meta-harness remain candidate-only until gated
```
