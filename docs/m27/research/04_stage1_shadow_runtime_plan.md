# 04｜Stage 1 Shadow Runtime Plan

Status: conditional plan. Do not implement until Stage 0C source reconciliation clears B001-B004.

## Revised Stage 1 principle

Stage 1 is not a new agent runtime. Stage 1 is:

```text
Existing M26 runtime decisions
  -> normalize into M27 trace objects
  -> optionally compare with shadow proposal
  -> log only
  -> no answer-path behavior change
```

The first runtime implementation must be adapter-normalization over M26, not a parallel planner.

## Feature flags

Proposed flags, all default off:

```text
M27_SHADOW_CONTEXT_RUNTIME_ENABLED=false
M27_SHADOW_CONTEXT_TRACE_ENABLED=false
M27_SHADOW_CONTEXT_COMPARE_ENABLED=false
```

Behavior:

- If all flags are false: zero behavior change.
- If trace enabled: add sanitized decision trace to internal runtime/QA trace only.
- If compare enabled: compute a non-authoritative shadow proposal but never use it to route or answer.

## Insertion points after source reconciliation

Candidate insertion points:

### Runtime-level normalized actual decision

Source:

```text
src/knowledge_engine/m26_aq_semantic_contract.py
```

Locations to inspect after source reconciliation:

```text
_routing_decision(...)
_fast_failure_route(...)
_low_information_retry_decision(...)
_semantic_failure_route(...)
_consolidated_semantic_recovery(...)
run_owner_arbitrary_query(...)
```

Plan:

```text
SemanticRoutingDecision.public()
  -> normalize_context_plan(...)
  -> normalize_compute_decision(...)
  -> emit internal sanitized m27.shadow.actual_decision event
```

### Public SSE safety boundary

Source:

```text
src/knowledge_engine/m26_public_api.py
```

Do not emit M27 traces to public SSE by default. If debugging is needed, emit only admin/QA internal trace, not public user stream.

### QA internal context

Production `m26_public_api.py` now includes QA internal context publication helpers. M27 trace can join this internal context, but must remain redacted.

## Proposed trace payload

```json
{
  "schema_version": "m27-shadow-context-runtime/v1",
  "trace_id": "...",
  "request_id": "...",
  "shadow_only": true,
  "actual": {
    "m26_route": "SEMANTIC_CLOSURE",
    "terminal_status": "...",
    "reason_codes": [],
    "selected_evidence_count": 0
  },
  "context_plan": {
    "context_sources": ["knowledge"],
    "strategy": "legacy_m26_semantic_route",
    "reason_code": "..."
  },
  "compute_decision": {
    "tier_label": "standard",
    "deadline_remaining_ms": 0,
    "minimum_budget_ms": 0,
    "provider_attempts_remaining": 0,
    "affordable": true
  },
  "suggested_tools": [],
  "privacy": {
    "raw_question_logged": false,
    "raw_answer_logged": false
  }
}
```

## What Stage 1 must not do

```text
Do not change route decisions.
Do not retry differently.
Do not add a new provider call.
Do not alter evidence selection.
Do not alter context compilation.
Do not alter final answer text.
Do not alter citations.
Do not add MCP.
Do not add Jev.
Do not add memory.
Do not expose release/promote/rollback tools.
Do not stream M27 internals to public clients.
```

## Stage 1 acceptance criteria

```text
1. Feature flags default off.
2. With flags off, behavior is unchanged.
3. With trace-only on, answer text/citations/status are unchanged.
4. Existing 523/100 brutal/bad-template gates do not regress.
5. Generic fallback guard remains enforced.
6. Public SSE material answer still appears only in terminal verified event.
7. No raw query or raw answer is stored in M27 trace.
8. No additional provider calls caused by Stage 1 trace-only mode.
9. No Qdrant/R2/release/admin mutation.
10. M27 layer can be disabled by env flag without redeploying code changes.
```

## Suggested first tests

After source reconciliation, add tests before implementation:

```text
test_m27_shadow_flags_default_off
test_m27_shadow_trace_does_not_change_terminal_event
test_m27_shadow_trace_has_no_raw_question_or_answer
test_m27_shadow_trace_normalizes_legacy_route
test_m27_shadow_trace_does_not_add_provider_call
test_m27_shadow_trace_not_public_sse_by_default
test_m27_generic_fallback_guard_still_blocks_publication
```

## Rollback plan

Stage 1 rollback must be trivial:

```text
set M27_SHADOW_CONTEXT_RUNTIME_ENABLED=false
set M27_SHADOW_CONTEXT_TRACE_ENABLED=false
set M27_SHADOW_CONTEXT_COMPARE_ENABLED=false
```

If deployed behind code feature flags, no DB schema migration and no production data mutation are allowed in Stage 1.

## Recommended next stage after Stage 1

Only after trace-only equivalence is stable:

```text
Stage 2: Native read-only domain tool boundaries
Stage 3: Context/Evidence boundary extraction
Stage 4: bounded iterative retrieval behind feature flag
```
