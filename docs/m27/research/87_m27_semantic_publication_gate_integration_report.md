# Stage 30G: semantic publication gate integration attempt

## Decision
`M27_SEMANTIC_PUBLICATION_GATE_INTEGRATION_FAIL_VERIFIER`

This is an honest non-PASS. The partial M27-native code integrates a narrow MiniMax NLI adapter and a fail-closed material-claim check, but has **not** met the complete offline gate. In particular, the existing extraction path verifies each selected claim against only its source passage, without verified multi-passage cluster construction; the new verdict receipts do not yet include confidence, and full tests were not runnable. This does not satisfy all mandatory Stage 30G publication requirements.

## Proven preflight
- Stage 30F clean HEAD: `1c4af5302a407ee4444ae95e17abd1e3d1d9d344`
- Isolated worktree: `/home/ubuntu/LLM_Wiki-m27-semantic-publication-gate-30g`; branch `m27/stage30g-semantic-publication-gate`
- `/v1/health` returned 200 on 8080, 8081, and 18080 before work.
- Active image before/after: `knowledge-engine:m27-owner-canary-29v`.
- No rebuild. No direct-20, 100, or 523 evaluation.
- Python compile and isolated network-disabled container package import passed.
- Host Python lacks `pytest` and `httpx`; existing container lacks `pytest`. Existing tests were not fully executed.

## Targeted offline regression
Five synthetic unittest cases passed in a network-disabled, read-only-mounted candidate image. This covers a narrow subset of fail-closed pathways, not the complete mandatory Stage30G offline suite.

## Important incomplete conditions
- Verify calibrated provider's exact production runtime prompt, timeout, schema retry and confidence receipt behavior end-to-end.
- Implement genuine claim-to-multiple-passage cluster binding and rigorous claim extraction, rather than single-source quotes.
- Make all offline cases pass (paraphrase, cross-language, clusters, negatives, contamination, schema errors, missing provider and thin answer).
- Require verified evidence support for every material factual claim and test end-to-end failure modes.
- Validate latency under provider calls before any rebuild.

## Safety
No Nginx change/reload, no release pointer mutation, no M26 or test restart, no production datastore write, no protected owner material, no public owner-gated route. Owner-only route certification remains pending.

## Next action
Finish verifier completeness and offline testing in this worktree. Do not rebuild 18080 until all checks pass. This is not owner-only route certification.
