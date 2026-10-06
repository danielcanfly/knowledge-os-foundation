# M27 Quality Scoring to Release Hard Gates Handoff

Status: `M27_QUALITY_PAYLOAD_SCORING_READY`

## Accepted quality evidence

- source admission HEAD: `f406be4a07ae360655e073c4dea1e13fe2796689`
- hard-gate HEAD: `e864417c2380f2ce8d6c24576fb129c37b95ccad`
- quality-gate source HEAD: `80b0b0ddc1ccc52ccb86b3acb1d2e9782579102a`
- quality score: `91.222`
- threshold: `85`
- score result: PASS
- scored sample: all 9 unique verified-answer semantic prompts from 237 eligible full523 rows
- rubric: `ANSWER_QUALITY_RUBRIC_v1`
- evaluator: `minimax / MiniMax-M3`
- evaluator contract version: `aq-semantic-evaluator/v3`
- scoring policy: `m27-independent-quality-scoring-policy/v1`
- payload validator: PASS
- repo release quality hard gate: PASS

Canonical artifact:

`docs/m27/research/quality_payload_score_receipts.json`

Sampling policy:

`docs/m27/research/55_quality_payload_sampling_policy.md`

Report:

`docs/m27/research/55_quality_payload_scoring_report.md`

## Important interpretation

This is independent semantic quality evidence, not a substitute for deterministic admission. The accepted full523 admission receipts remain authoritative for admission correctness, citation/provenance, safe-terminal correctness, and latency. Safe terminals were not averaged into the semantic quality score.

Payload-bearing records were regenerated only in isolated quality-scoring mode and are explicitly not new admission authority. No runtime answer tuning or failed-case tuning was performed.

## Safety state

Production remained untouched. Final read-only identity stayed at build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd` and entrypoint `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`. Owned M27 eval containers and port 18080 listeners both ended at zero.

This handoff does not authorize deployment, canary activation, release pointer mutation, production restart/rebuild, or production datastore writes.
