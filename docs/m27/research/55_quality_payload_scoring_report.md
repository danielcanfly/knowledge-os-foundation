# M27 Quality Payload Capture + Independent Semantic Scoring Report

## Decision

`M27_QUALITY_PAYLOAD_SCORING_READY`

A real independent semantic quality score artifact now exists, is digest-linked to payload-bearing isolated answer/evidence records, exceeds the release threshold, and preserves production no-mutation evidence.

## Canonical lineage

- source admission HEAD: `f406be4a07ae360655e073c4dea1e13fe2796689`
- release hard-gate HEAD: `e864417c2380f2ce8d6c24576fb129c37b95ccad`
- quality-gate HEAD: `80b0b0ddc1ccc52ccb86b3acb1d2e9782579102a`
- source admission receipts SHA-256: `e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137`
- workspace: `/home/ubuntu/LLM_Wiki-m27-quality-payload-scoring`
- branch: `m27/quality-payload-scoring`

## Preflight

PASS before payload capture/scoring.

- production `/v1/health`: HTTP 200, `ok=true`
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- owned M27 eval containers before scoring: 0
- port 18080 listeners before scoring: 0
- evaluator credential: available through the existing VM secret file; secret value was not printed
- evaluator provider seam: MiniMax
- evaluator model: `MiniMax-M3`
- production answer endpoint was not used for payload generation
- no production datastore or release-pointer mutation path was used

The initial qualified `ProviderAnswerQualityEvaluator` call correctly failed closed because the provider response did not satisfy the required `criterion_scores` JSON object contract. No score from that failed call was accepted. The scoring harness therefore used the same qualified MiniMax provider/model and the same `ANSWER_QUALITY_RUBRIC_v1` seven-dimension contract with a stricter JSON-only scorer adapter. Runtime answer behavior was not modified.

## Payload capture

Accepted full523 receipts contain 237 verified-answer rows but do not retain answer/evidence semantic payload. This session regenerated payload only under the explicit label:

`isolated quality-scoring payload capture; not admission authority`

The capture path uses the isolated M27 runtime harness and production-equivalent read-only fixture evidence. Accepted admission receipts were not overwritten or mutated.

Each scored record preserves:

- case ID and category
- question
- answer payload
- citations
- selected evidence payload
- integrity fields
- forensic/runtime trace
- per-record input digest

The score artifact links each per-case score back to the corresponding payload digest.

## Sampling policy

The policy was written to `docs/m27/research/55_quality_payload_sampling_policy.md` before semantic scoring calls.

Policy: `unique-question-stratified-all-verified-categories/v1`.

The 237 eligible verified-answer rows contain only 9 unique `(category, question)` semantic prompts. All 9 were scored. Coverage includes every verified-answer category:

- `cited_answer`
- `multilingual`
- `retrieval_hard`

The remaining 228 rows are deterministic repeated instances of those same semantic prompts across full523 repetitions. Safe terminals are excluded from semantic quality aggregation and remain governed by the accepted separate safe-terminal correctness evidence.

## Independent semantic scoring

- evaluator provider: `minimax`
- evaluator model: `MiniMax-M3`
- evaluator identity: `repo-qualified-minimax-answer-quality-evaluator`
- evaluator version: `aq-semantic-evaluator/v3`
- rubric: `ANSWER_QUALITY_RUBRIC_v1`
- scoring policy: `m27-independent-quality-scoring-policy/v1`
- scored cases: 9
- eligible verified-answer rows: 237
- aggregate quality score: **91.222 / 100**
- release threshold: **85 / 100**
- aggregate gate: PASS

Per-case results are retained without filtering:

- `F523-001-R01`: 100, pass
- `F523-002-R02`: 78, fail
- `F523-003-R03`: 84, fail
- `F523-004-R04`: 88, pass
- `F523-005-R05`: 74, fail
- `F523-006-R06`: 98, pass
- `F523-013-R13`: 87, fail under boundary policy
- `F523-014-R14`: 98, pass
- `F523-015-R15`: 96, pass

The release hard-gate contract evaluates the independent aggregate quality score and required provenance/evidence fields. It does not require every sampled case to individually clear 85. The lower-scoring cases remain visible in the artifact and were not tuned or rerun selectively.

## Score artifact

Required artifact:

`docs/m27/research/quality_payload_score_receipts.json`

- artifact SHA-256 after scoring: `057122e7733283a0f4b0f40f5836ce6c860a2596a27f59a7da1c6199019324da`
- per-case score digest: `67960dc1790e35573b9f04946e6a15c26759e971194d5c69ae586abf7042d9ef`
- payload traceability validator: PASS, no reason codes
- repo quality hard gate: PASS, no reason codes

The artifact records schema version, artifact ID, source heads, evaluator provider/model/identity/version, rubric version, scoring policy, eligible/scored/skipped counts, payload records, per-case scores, aggregate score, threshold, source/input/output digests, reason codes, and production no-mutation proof.

## Required validations

Focused suite:

```text
37 passed, 1 warning in 2.98s
```

Covered:

- quality payload contract
- independent score artifact validation
- fail-closed missing evaluator identity/credential proxy
- fail-closed missing payload
- fail-closed synthetic/placeholder scorer identity
- admission metric contract regression
- release hard-gate regression
- isolated streaming regression
- no production mutation proof
- existing release quality gate regression

Additional validation:

- `python3 -m compileall src tests`: PASS
- changed-file `ruff check`: PASS
- `git diff --check`: PASS

The single test warning is the existing Starlette/httpx deprecation warning.

## Production and release safety

Final read-only proof:

- production health: `ok=true`
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint unchanged: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- owned M27 eval containers: 0
- port 18080 listeners: 0
- production deploy: NOT performed
- canary: NOT performed
- release pointer mutation: NOT performed
- production restart/rebuild: NOT performed
- production R2/Qdrant/SQLite writes: NOT performed
- admission rerun: NOT performed
- Stage13/14 legacy admission: NOT performed
- Chunk002: NOT performed
- runtime answer tuning: NOT performed

## Final state

`M27_QUALITY_PAYLOAD_SCORING_READY`
