# 06｜Tool and Capability Registry

## Principle

Expose domain capabilities, not infrastructure internals.

Agent should see:

```text
knowledge.search
knowledge.fetch
evidence.expand
evidence.verify
eval.run_subset
runtime.health
runtime.trace
release.create_candidate
```

Agent should not see low-level implementation names first:

```text
qdrant_search
r2_get
redis_get
postgres_select
```

## Transport boundary

MCP is capability transport, not architecture.

Initial providers:

```text
NativeToolProvider
MCPToolProvider
APIToolProvider
```

## Write tools

All write tools require PolicyEngine approval.
