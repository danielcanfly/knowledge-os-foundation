# 02｜M27 Request Flow

## Target flow

```text
USER / TASK
  ↓
AGENT HARNESS
  ↓
Context Planner        Compute Policy
  │                    │
  └──── DecisionProvider ────┐
                             ↓
Knowledge / Memory / Skills / Workspace / Tools
                             ↓
Evidence Gathering
  search → inspect → open → retry
                             ↓
Context Compiler
  trust / rank / dedupe / compress / budget / citation binding
                             ↓
Frontier Model
                             ↓
Verification
  insufficient → gather more
  pass → final
                             ↓
Governed write-back candidate
```

## Stage 1 shadow flow

```text
USER / TASK
  ↓
M26 production path answers normally
  ↓
M27 shadow planner records:
  route
  compute_tier
  context_sources
  suggested_tools
  confidence
  reason_code
```

No answer behavior changes.

## Required trace fields

```text
request_id
task_type
route
compute_tier
selected_skill
candidate_tools
called_tools
retrieval_rounds
candidate_context_tokens
compiled_context_tokens
model_tier
verification_result
latency_by_stage_ms
cost_estimate
reason_codes
feature_flags
```
