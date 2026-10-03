# 02｜M27 Contract Mapping

Status: Stage 0B research. This mapping is based on production image + dirty worktree source, because M27 clean branch is missing production-only console/control-plane modules.

## Contract strategy update

M27 should not implement fresh contracts beside M26. The safer strategy is:

```text
M27 Contract
  -> LegacyM26Adapter
       -> existing production implementation
```

Only after equivalence is proven should any implementation be replaced.

## Contract mapping table

| M27 contract | Current M26 implementation candidate | Missing pieces | Risk | Stage 1 minimal interface |
|---|---|---|---|---|
| `Harness` | `m26_console_api.create_app`, `m26_public_api.create_app`, `_answer_event_stream`, `m26_ask_api.run_owner_query_for_web`, `m26_aq_semantic_contract.run_owner_arbitrary_query` | No explicit harness object; composition split between console/public/runtime functions | High if replaced by external agent SDK too early | `run(request) -> terminal DTO + sanitized events`; initially adapter-only |
| `ContextPlanner` | `SemanticRoutingDecision`, `_routing_decision`, `_fast_failure_route`, `_semantic_failure_route`, intent classification and recovery decisions in `m26_aq_semantic_contract.py` | No provider-neutral `ContextPlan` schema; current routes are semantic-recovery focused | Medium; parallel router may diverge from proven gates | Normalize existing route into `ContextPlan` without changing behavior |
| `ComputePolicy` | `_deadline_remaining_ms`, `_route_minimum_budget_ms`, provider attempts remaining, soft/hard deadline, public hard deadline | No formal tier schema; compute is embedded in routing | Medium; naive FAST/STANDARD/DEEP could erase real budget signals | `ComputeDecision(deadline_ms, min_budget_ms, provider_attempts, tier_label)` from legacy state |
| `KnowledgeProvider` | `load_production_answer_bundle`, `_run_lexical_primary_retrieval`, dense Qdrant channel, lexical retrieval, graph evidence, production bundle active binding | Clean M27 lacks active production release/dense modules | High until source reconciliation | `search(question, intent, constraints) -> lexical_result, dense_result, candidate refs` adapter |
| `EvidencePlanner` | `_select_evidence`, `_strengthen_evidence`, facet/query coverage, graph/provenance/temporal evidence builders | Not separated from retrieval and publication code | Medium; ContextCompiler could become too broad | `plan_evidence(retrieval_results, requirements) -> evidence + gap/sufficiency` |
| `ContextCompiler` | `m26_context_compiler.build_context_manifest` and `compile_context_package` | M26 semantic runtime also performs evidence budgeting/selection outside compiler | Medium; duplicated context selection possible | Preserve current compiler, define boundary: evidence in, context package out |
| `Verifier` | `m26_verified_answer_citation_gate.py`, semantic requirement checks, `_response_from_verification`, QA/eval gates | No single verifier façade | High if bypassed | `verify(candidate, evidence, requirements) -> publishable/abstain/fail` adapter only |
| `ToolProvider` | No formal user-facing tool registry yet; current capabilities are normal functions/routes | Need domain tools and risk metadata | Medium | Read-only tool registry with native providers only |
| `PolicyEngine` | admin auth/capability gates, public admission, origin/quota checks, owner hash, verified gates, release conflict checks | Contract not centralized | High if tools bypass it | `authorize(action, actor, resource, risk) -> allow/deny`; adapter to existing checks |
| `Evaluator` | QA inbox, `qa_answer_quality*`, quality scripts, 523/brutal gate ecosystem | Test commands and fixtures need exact source-of-truth update | Medium | Expose read-only eval metadata; do not run full eval in request path |
| `TraceStore` | runtime event sink, QA failure trace storage, admin audit SQLite, QA SQLite | Trace fields are split; privacy constraints strict | Medium | Decision trace schema with no raw query/answer, tied to existing trace/request id |
| `WorkspaceStore` | No direct production equivalent; QA failure traces and artifacts are adjacent but not task workspace | New concept | Low for Stage 1 if deferred | Defer until after shadow router; file-backed sandbox only later |
| `MemoryProvider` | No first-class memory runtime; current QA/trace stores are not memory | New concept | High if confused with production truth | Defer; do not add memory in Stage 1 |
| `SkillProvider` | Current SOPs/runbooks/scripts; no runtime skill loader | New concept | Low if used for ops only | Defer answer-path skills; start with ops skills later |
| `DecisionProvider` | Current deterministic routing; potential future Jev/small-model provider | No pluggable provider | Low if shadow-only | Defer; first provider is `LegacyM26DecisionProvider` |
| `ModelProvider` | MiniMax/Cloudflare/Gemini fallback routing in current provider code | Already complex and budgeted | Medium if abstracted too early | Do not abstract in Stage 1; observe provider routing only |
| `CapabilityProvider` | Admin capability providers, ingestion capability provider, production qualified capability gate | Existing admin-only concept not same as agent tool capability | Medium | Keep admin capability provider separate from agent tool registry |

## Minimal Stage 1 contract set

The smallest safe contract set is:

```text
HarnessEvent
ContextPlan
ComputeDecision
EvidencePlanSummary
ShadowRuntimeTrace
```

Do not start with full Tool/Skill/Memory/MCP contracts.

## Suggested minimal schemas

### ContextPlan

```text
schema_version
trace_id
actual_m26_route
normalized_route
context_sources
strategy
reason_codes
evidence_status
shadow_only
```

### ComputeDecision

```text
schema_version
trace_id
tier_label
deadline_remaining_ms
minimum_budget_ms
provider_attempts_remaining
route_affordable
reason_code
shadow_only
```

### ShadowRuntimeTrace

```text
schema_version
trace_id
request_id
production_image
production_source_identity
actual_route
shadow_route
compute_decision
suggested_context_sources
suggested_tools
confidence
reason_code
created_at
privacy_mode
```

Privacy mode must forbid raw question and raw answer. Use hashes and route/evidence metadata.

## Domain tool candidates

Stage 1/2 read-only candidates only:

```text
knowledge.search
knowledge.expand
evidence.inspect
evidence.verify
runtime.get_trace
runtime.get_budget
runtime.get_health
```

Do not expose first:

```text
release.promote
release.rollback
ingestion.finalize
qdrant.raw_search
r2.raw_get
sqlite.raw_query
admin.mutate
```

## Do-not-cross boundaries

```text
ContextPlanner must not publish answers.
ComputePolicy must not override safety gates.
ToolProvider must not bypass PolicyEngine.
KnowledgeProvider must not expose infra implementation directly to agents.
Skills must not gain production write authority.
MCP must not be introduced before native tool boundaries are proven.
Jev/FastDecision must not become a production dependency before shadow agreement/eval.
```

## Stage 1 recommendation

Stage 1 should be adapter-normalization, not new behavior:

```text
existing M26 runtime route
  -> normalize to ContextPlan
existing M26 budget/deadline state
  -> normalize to ComputeDecision
existing runtime event sink
  -> append sanitized decision trace
```

Answer output must remain byte-for-byte behaviorally equivalent unless tracing is disabled/enabled. Feature flag must default off.
