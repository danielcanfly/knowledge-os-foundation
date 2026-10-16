# 01｜M27 Contracts

Contracts are the first deliverable. Implementations come later.

## Contract rule

```text
Core domain code must never import vendor-specific SDKs directly.
```

Vendor-specific code belongs only under:

```text
/providers
/adapters
/integrations
```

## Initial contracts

```text
ContextSource
KnowledgeProvider
MemoryProvider
SkillProvider
ToolProvider
DecisionProvider
ModelProvider
ComputePolicy
PolicyEngine
Evaluator
Harness
WorkspaceStore
TraceStore
```

## Contract template

Each contract must define:

```text
responsibility
non-responsibility
input schema
output schema
failure modes
policy boundary
trace fields
allowed implementations
conformance tests
```

## Provider boundaries

### KnowledgeProvider

Responsible for knowledge retrieval and authoritative source access. Must not own final answer synthesis.

### DecisionProvider

Responsible for bounded decisions such as routing, classification, scoring, and compute tier suggestions. Must not own deep synthesis or production truth.

### ToolProvider

Responsible for capability discovery and invocation. Must not bypass policy.

### ComputePolicy

Responsible for selecting compute budget per request.

### PolicyEngine

Responsible for deterministic enforcement. Agent may request. PolicyEngine decides.

## Hard boundary

```text
Agent proposes.
Infrastructure enforces.
```
