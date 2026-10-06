# M27 Runtime Composition Inventory

Date: 2026-10-06
Workspace: /home/ubuntu/LLM_Wiki-m27-runtime-composition
Branch: m27/runtime-composition
Base: 06681024634b2590ce6115498a5c87ed887b9aea

## Inventory conclusion

Stage 1-12 primitives are real and safe, but before this composition phase they are mostly independent boundaries. The genuinely missing layer is a small runtime harness that can accept an isolated task, plan context sources, observe compute policy, invoke read-only tools through policy, select an ops skill, create isolated workspace state, keep memory non-authoritative, and produce learning/meta-harness candidate records from sanitized signals only.

## Primitive map

| Primitive | Existing module / class / function | Current authority | Currently wired | Runtime input needed | Output produced | Safe composition point | Missing adapter / executor | Required for first executable composition |
|---|---|---:|---:|---|---|---|---|---:|
| Stage 1 contracts | m27_context_runtime_contracts.py protocols/dataclasses | schema only | yes, tests | already-produced M26 signals | normalized plans/decisions | harness normalization boundary | task-level harness state | yes |
| Stage 1 legacy adapters | LegacyM26SemanticRoutingAdapter, LegacyM26DeadlineBudgetAdapter, LegacyM26ContextCompilerAdapter, LegacyM26VerifierAdapter | observation only | tests only | sanitized dict/object signals | normalized context/compute/compiler/verifier records | harness input normalization | orchestration caller | yes |
| Stage 1 sanitized trace | m27_decision_trace.DecisionTraceEvent | observability only | tests only | route/compute/source/status counts | privacy-safe trace event | after verification / branch decision | trace assembly from composed runtime | yes |
| Stage 2 replay | m27_replay_harness.py, m27_equivalence_report.py | offline comparison | tests only | captured sanitized replay inputs | drift classifications | post-run eval/reporting | not on live request path | no |
| Stage 3 evidence boundary | LegacyM26EvidencePlannerAdapter, LegacyM26ContextEvidenceBoundary | normalization only | tests only | existing selected evidence and gap signals | EvidencePlanningResult | before tools / verifier continuation | orchestration caller | yes |
| Stage 4 compute policy | RuleBasedComputePolicy.classify | shadow observation only | tests only | deadline/provider budget signal | ComputePolicyObservation | budget gate / bounded loop | harness budget interpretation | yes |
| Stage 5 tool registry | build_stage5_readonly_registry | descriptor-only | tests only | none | read-only capability descriptors | before any capability call | actual read-only executor with policy and injected providers | yes |
| Stage 5 read-only tool views | m27_readonly_tools.py provider protocols / view helpers | read-only adapter | tests only | typed requests / existing trace/evidence/verification | typed sanitized outputs | tool execution boundary | dispatcher and authorization policy | yes |
| Stage 6 bounded retrieval | run_bounded_agentic_second_round, plan_second_retrieval_round | default-off isolated behavior | M26 path only under flags | material evidence gap, retrieval functions, budget | optional second-round result | bounded continuation policy reference | do not import benchmark tuning; expose loop contract only | partial |
| Stage 7 skills | build_stage7_ops_skill_registry and SkillRegistry.plan | descriptor/plan only | tests only | ops intent and read-only capability descriptors | descriptive SkillPlan | plan selection before read-only tool calls | bounded skill-plan executor that only calls allowed tools | yes |
| Stage 8 workspace | WorkspaceStore, WorkspaceId, artifact/checkpoint contracts | isolated filesystem state | tests only | injected root and sanitized task token | task workspace, artifacts, checkpoints | run start/end | harness lifecycle and sanitized artifacts | yes |
| Stage 9 MCP exposure | build_stage9_mcp_manifest | descriptor exposure only | tests only | Stage 5 registry plus policy | MCP-safe descriptors | optional transport descriptor | no live network transport needed | no |
| Stage 10 memory | GovernedMemoryRuntime, MemoryCandidate | candidate-only, non-authoritative | tests only | sanitized summary/provenance/review | memory candidates / retained candidate list | explicit policy boundary after trace | harness-controlled candidate write-back/read list | yes |
| Stage 11 learning | LearningRuntime, LearningSignal, LearningProposal | proposal-only | tests only | sanitized signals | proposal metadata | after sanitized trace/failure summary | harness signal creation | yes |
| Stage 12 meta-harness | MetaHarnessRuntime, MetaHarnessInput, candidate reports | candidate metadata only | tests only | sanitized eval/runtime signal metadata | candidate plan/report metadata | after run summary | harness metadata creation | yes |

## Genuinely missing pieces

1. A task-facing runtime harness that composes the primitives in one execution path.
2. A deterministic context orchestrator that selects Knowledge / Tools / Skills / Workspace / Memory explicitly without treating memory as truth.
3. A read-only tool executor behind Stage 5 descriptor policy and injected providers.
4. A bounded verifier-driven continuation contract with explicit round/tool/budget counters.
5. Architecture-specific tests proving composition across Knowledge, Tool, Workspace, Skill, Memory, Learning, Meta-Harness, trace, and feature-off behavior.

## Duplicates intentionally avoided

- No new Knowledge Engine or retrieval engine is introduced.
- No new MCP transport is introduced.
- No production release/promotion surface is introduced.
- No memory-to-knowledge promotion path is introduced.
- No learning/meta-harness auto-apply path is introduced.
- No Stage13/14 benchmark-specific runtime patch is imported.
