# Stage 30B: Direct Candidate Product Quality Repair

## Final decision
`M27_DIRECT_CANDIDATE_PRODUCT_QUALITY_REPAIR_FAIL_SYNTHESIS`

This is an **incomplete repair**, not a successfully validated candidate. The isolated M27 code remains undeployed.

## Scope and provenance
- Workspace: `/home/ubuntu/LLM_Wiki-m27-direct-candidate-quality-repair-30b`
- Branch: `m27/stage30b-native-quality`
- Base HEAD: `c5d2a18d4e32f9233705810cb2fa76b786d57691`
- Candidate remains `m27-owner-canary-28`, image `knowledge-engine:m27-owner-canary-29v`
- Direct-only. No owner-auth route, protected verification material, M26/test restarts, Nginx or datastore mutations.

## Stage 30A failure reproduction
The historical 30A source CSV and receipts were inspected, not just the summary: 20/20 HTTP, 18/18 answerable cited, p95 5.784s; 13/20 heuristic thin flags. C05 Kubernetes evidence contains unrelated x402 payment/hospitality concepts. C02/C03/C04 contain template-heavy answer leads; C19/C20 are expected safe-terminal cases.

## Root cause matrix
See `82_m27_direct_candidate_product_quality_root_cause_matrix.csv`, 20 rows. Each row records query, actual answer excerpt, evidence topic fragments when extractable, suspected contamination, citation support status, thin flag, likely boundary, and a proposed repair. The initial 30A receipt lacks complete retrieved candidate passages/reranker traces, so per-row precise retrieval origin and semantic citation validity are **not proven**. Do not misread provisional classifications as ground truth.

## Confirmed code root causes
1. `_score_evidence` rewarded generic ecosystem vocabulary, allowing topical impostors.
2. `_select_evidence` filled to target breadth even when weakly relevant and could repeat the same passage due to fallback ID inconsistency.
3. `_localized_answer` manufactures general leads/conclusions and stitches quotes without claim-specific semantics.
4. Verifier treats locator/citation existence and length as support; this does **not** establish claim-to-evidence alignment.

## Repair changes (isolated source only)
- `src/knowledge_engine/m27_agent_product_runtime.py`: introduced original-query topic-anchor filtering, removed generic AI vocabulary score bonus, excluded evidence without lexical anchor and corrected source+locator deduplication; added pre-answer support check.
- `tests/test_m27_stage30b_topic_guard.py`: targeted safety assertions for Kubernetes-versus-payment contamination and source deduplication.
- This lexical guard is **not** a semantic verifier and has multilingual false-negative and synonym coverage risks. The synthesis template has not been replaced. Thus no product PASS.

## Tests and health
- Targeted direct-module static assertions: PASS (5).
- `python3 -m py_compile`: PASS.
- Edited native file does not reference `run_owner_arbitrary_query` or `synthesize_and_verify`: PASS.
- Conventional pytest unavailable: `No module named pytest`; ordinary package import hits missing `httpx`.
- Health after isolated edits: 8080 HTTP 200, 8081 HTTP 200, 18080 HTTP 200.
- No runtime rebuild/deploy, so **no post-repair direct 20-case metrics exist**; 100/523 skipped by gate. Existing live metrics remain Stage 30A baseline only.

## Remaining blockers / next action
Implement real topic-aware evidence planning, claim-level semantic support scoring, multilingual normalization, and grounded native answer synthesis in M27. Restore a working test environment; run targeted tests, rebuild only isolated candidate, then gated direct 20 -> 100 -> optional 523 evaluation. Owner rubric at least 85 has not been demonstrated. Do not interpret unchanged 18080 health as repair validation.

**Owner-only route certification remains pending and must not be inferred from this result.**
