# M27 Semantic Publication Gate Integration Handoff

Final decision: `M27_SEMANTIC_PUBLICATION_GATE_INTEGRATION_PASS`

Owner-only route certification remains pending and must not be inferred from this result.

## Current state
- Stage 30G isolated direct candidate is active on `127.0.0.1:18080`.
- Active candidate image: `knowledge-engine:m27-semantic-publication-gate-30g-67ca9928`
- Active HEAD: `67ca9928b54feb7cd81083313f845c264c565b37`
- Offline integration gate: `20/20 PASS`
- Direct20: PASS
  - HTTP: `20/20`
  - Answerable cited final: `18/18`
  - Expected safe terminals: `2/2`
  - p95 final latency: `9510.349 ms`
  - p95 first-material latency: `9509.107 ms`

## Do next
- Do not infer owner-only route certification from this result.
- Do not mutate release pointers from this handoff alone.
- A later authorized stage may decide whether to run a broader direct100 harness if one is explicitly provided or created under a new prompt.
- full523 remains out of scope unless explicitly authorized by a later prompt.

## Safety preserved
No public owner-gated route, no protected owner material, no Nginx reload, no production M26 restart/rebuild, no test backend restart/rebuild, no release pointer mutation, and no public canary were performed.
