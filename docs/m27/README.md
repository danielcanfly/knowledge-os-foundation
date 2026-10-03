# M27 Context-Native Adaptive AI Runtime

Created: 2026-10-03T07:21:55Z
Workspace: `/home/ubuntu/LLM_Wiki-m27-context-runtime`
Branch: `m27/context-native-runtime-spec`
Base commit: `f746822503b7b27b2f5d4bb98ad406b15f558732`

M27 is the next architecture layer above the current M26 Knowledge Engine. It is not a rewrite of M26 and not an agent-first replacement.

## M27 definition

```text
M26 = deterministic Knowledge Engine / AQV2 / QGate / production answer runtime
M27 = Context-Native Adaptive AI Runtime
```

## Non-negotiable principle

```text
Agent proposes.
Infrastructure enforces.
```

## Current production baseline

```text
llm_wiki-knowledge-engine-1	knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z	Up About an hour (healthy)	127.0.0.1:8080->8080/tcp
```

## Production freezes known at prework time

```text
/home/ubuntu/production-freezes/m26-production-freeze-20261003T060811Z
/home/ubuntu/production-freezes/m26-production-freeze-generic-fallback-guard-20261003T063245Z
```

## Stage 0 hard rules

1. Do not modify production runtime.
2. Do not attach M27 to `/v1/answers` yet.
3. Do not build agent loops before contracts.
4. Do not import vendor SDKs in core domain code.
5. Do not put Jev, MCP, Qdrant, or any model vendor in architecture-level contracts.
6. Preserve M26 as the deterministic knowledge/data plane.
7. All write paths require deterministic policy enforcement.
