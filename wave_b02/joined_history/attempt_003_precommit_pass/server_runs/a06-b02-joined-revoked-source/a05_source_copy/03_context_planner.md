# 03｜Context Planner

## Question answered

```text
What does this task need before the model answers?
```

## Planner outputs

```text
route
required_context_sources
candidate_skills
candidate_tools
need_retrieval
need_live_tool
need_memory
need_workspace
need_verification
confidence
reason_code
```

## Initial routes

```text
NO_RETRIEVAL
KNOWLEDGE
LIVE_TOOL
COMPLEX
OUT_OF_SCOPE
```

## Stage 1 implementation

Rule-based shadow planner only. No production behavior changes.

## Non-responsibilities

The Context Planner does not call tools, fetch sources, write memory, decide production truth, or bypass policy.
