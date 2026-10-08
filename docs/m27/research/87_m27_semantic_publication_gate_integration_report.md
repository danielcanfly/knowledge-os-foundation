# Stage 30G — Semantic Publication Gate Integration Report

## Final decision
`M27_SEMANTIC_PUBLICATION_GATE_INTEGRATION_PASS`

Owner-only route certification remains pending and must not be inferred from this result.

## Scope executed
- Integrated the calibrated Stage 30F narrow semantic entailment provider into the M27 publication gate.
- Kept the provider as a verifier only; no M26 mature answer composer delegation was introduced.
- Rebuilt only the isolated direct candidate on `127.0.0.1:18080`.
- Ran deterministic offline integration tests and direct 20-case candidate verification.
- Did not run 100-case because no existing safe direct100 harness was present.
- Did not run full523; this prompt explicitly forbids admission/full523 rerun.

## Current isolated candidate
- Workspace: `/home/ubuntu/LLM_Wiki-m27-semantic-publication-gate-30g`
- Branch: `m27/stage30g-semantic-publication-gate`
- HEAD: `67ca9928b54feb7cd81083313f845c264c565b37`
- Candidate image: `knowledge-engine:m27-semantic-publication-gate-30g-67ca9928`
- Candidate endpoint: `127.0.0.1:18080/v1/answers/stream`

## Offline integration gate
- Offline integration gate: `True`
- Cases: `20/20` passed
- Literal overlap accepted as semantic support: `False`
- Citation existence accepted as semantic support: `False`
- Thin cited answer can publish: `False`
- M26 mature composer delegation: `False`
- Schema retry limit: `1`

## Direct 20-case verification
- Direct20 pass: `True`
- HTTP success: `20/20`
- Answerable cited final: `18/18`
- Expected safe terminal pass: `2/2`
- False safe terminal count: `0`
- Missed safe terminal count: `0`
- Empty nonterminal count: `0`
- Thin cited answer count: `0`
- Topic contamination count: `0`
- Semantic bad publish count: `0`
- p50 final latency: `4277.8 ms`
- p95 final latency: `9510.349 ms`
- p50 first-material latency: `4276.423 ms`
- p95 first-material latency: `9509.107 ms`
- No M26 mature composer delegation: `True`

## Code-level changes
- Added fail-closed semantic publication gate policy.
- Added confidence, attempt count, and one-schema-retry audit to entailment verdicts.
- Split accepted publication receipts from rejected semantic audit receipts so rejected candidate claims cannot poison a verified final answer while still preserving auditability.
- Added adaptive semantic fill: publish at least two verified claims, fill up to three only when needed to avoid thin answers.
- Preserved fail-closed handling for missing provider, provider errors, schema-invalid output, low-confidence verdicts, invalid references, unsupported claims, and contradicted claims.

## Safety confirmation
- No public owner-gated route was used.
- No protected owner verification material was read or emitted.
- No Nginx modification or reload was performed.
- No production M26 restart/rebuild was performed.
- No test backend restart/rebuild was performed.
- No release pointer mutation was performed.
- No public percentage canary was performed.

## Artifacts
- `docs/m27/research/87_m27_semantic_publication_gate_integration_report.md`
- `docs/m27/research/m27_semantic_publication_gate_integration_receipts.json`
- `docs/m27/research/87_m27_semantic_publication_gate_eval_cases.csv`
- `docs/m27/research/87_m27_semantic_publication_gate_claim_audit.csv`
- `docs/m27/research/87_m27_semantic_publication_gate_direct20_cases.csv`
- `docs/m27/research/87_m27_semantic_publication_gate_direct20_receipts.json`
- `docs/m27/research/m27_stage30g_offline_integration_receipt.json`
- `docs/m27/handoffs/M27_SEMANTIC_PUBLICATION_GATE_INTEGRATION_HANDOFF.md`
