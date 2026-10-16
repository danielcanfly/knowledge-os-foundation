# 05｜Compute Policy

## Question answered

```text
How much test-time compute does this task deserve?
```

## Initial tiers

```text
FAST
  one retrieval or no retrieval
  no subagents
  light verification
  short deadline

STANDARD
  planner
  one to two retrieval rounds
  normal verification
  standard deadline

DEEP
  iterative retrieval
  parallel hypotheses allowed
  subagents allowed
  strong verification
  larger deadline
```

## Output schema

```text
model_tier
reasoning_effort
max_retrieval_rounds
max_tool_calls
context_budget
verification_level
allow_subagents
parallelism
deadline_ms
cost_ceiling
```

## Stage 1

Shadow-only rule policy.

## Future implementations

```text
RuleBasedComputePolicy
JevComputePolicy
LearnedComputePolicy
FrontierLLMComputePolicy
```
