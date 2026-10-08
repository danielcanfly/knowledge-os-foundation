# M27 Stage 30G Semantic Publication Gate Integration Handoff

Final decision: M27_SEMANTIC_PUBLICATION_GATE_INTEGRATION_FAIL_RETRIEVAL

Workspace: /home/ubuntu/LLM_Wiki-m27-semantic-publication-gate-30g
Branch: m27/stage30g-semantic-publication-gate
Base: 1c4af5302a407ee4444ae95e17abd1e3d1d9d344
Implementation HEAD used by active candidate: 1511d934b9d43b5633063bbe6a19c105376d14b4

## State to preserve
- Offline semantic publication integration: PASS 20/20.
- Active isolated 18080 image: knowledge-engine:m27-semantic-publication-gate-30g-1511d934, healthy.
- Rollback retained: m27-owner-canary-28-pre30g / knowledge-engine:m27-owner-canary-29v.
- Direct20 final: FAIL, 5/18 answerable cited final.
- p95 final: 11747.02 ms.
- p95 first material: 11745.247 ms.
- semantic bad-publish: 0.
- topic contamination: 0.
- 100-case and full523: NOT RUN.

## Next repair boundary
Do not weaken the semantic publication verifier. The remaining blocker is evidence retrieval/corpus coverage. Repair should introduce a governed, generic, versioned evidence source or production corpus update that can supply authoritative material for missing domains, then rerun the same direct20 without case-specific routing or hard-coded answers.

Do not use historical eval answers/receipts as evidence. Do not infer owner-only route certification.
