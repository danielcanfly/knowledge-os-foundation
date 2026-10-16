# 04｜Context Compiler

## Question answered

```text
What exact context should the model receive?
```

## Inputs

```text
retrieved chunks
source documents
memory candidates
workspace state
skill instructions
tool results
conversation state
policy constraints
compute budget
```

## Responsibilities

```text
ACL filtering
trust scoring
freshness check
deduplication
ranking
compression
token budgeting
citation binding
priority allocation
```

## Output

```text
compiled_context
citation_map
excluded_items
context_budget_report
trust_report
freshness_report
```

## Hard rule

The compiler must not silently promote unverified memory or agent observations into production knowledge.
