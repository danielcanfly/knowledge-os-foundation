# 00｜M27 Architecture Overview

## Name

M27 Context-Native Adaptive AI Runtime

## Purpose

M27 upgrades the current M26 Knowledge Engine into a context-native runtime that can plan context, select capabilities, allocate compute, verify outputs, and learn from traces without weakening deterministic governance.

## What M27 is

```text
Context-Native Adaptive AI Runtime
with a governed Knowledge Engine,
full Agent Harness,
adaptive test-time compute,
pluggable capabilities,
and bounded autonomous learning.
```

## What M27 is not

M27 is not:

- a rewrite of M26
- a generic multi-agent swarm
- an MCP-first system
- a Jev-dependent system
- a LangGraph / Agents SDK wrapper
- a replacement for Qdrant, R2, citations, ACL, release, or evals

## Four planes

```text
1. Intelligence Plane
   Frontier Model
   Decision Models
   Context Planner
   Compute Controller

2. Context & Capability Plane
   Knowledge
   Memory
   Skills
   Workspace
   Tools
   MCP / Native capability transport
   Context Compiler

3. Execution & Governance Plane
   Harness
   Policy
   ACL
   Verification
   Tracing
   Evaluation
   Release

4. Learning Plane
   Experience Store
   Failure Mining
   Skill Evolution
   Memory Learning
   Retrieval Policy Learning
   Compute Policy Learning
   Meta-Harness
```

## Core design objective

```text
Construct the minimum sufficient, trustworthy context
and allocate the minimum compute required
to solve the task reliably
under deterministic governance.
```

## Existing M26 role

M26 remains the deterministic data / knowledge plane:

```text
Qdrant
R2
BM25 / hybrid retrieval
graph
citations
provenance
ACL
release versioning
rollback
evaluation datasets
quality gates
tracing
```

## M27 first executable stage

Stage 1 should be a Shadow Context Runtime:

```text
User request
  ↓
M26 production answer path continues unchanged
  ↓
M27 shadow planner observes only
  ↓
trace route / compute tier / suggested context sources
```

No production answer behavior changes in Stage 1.
