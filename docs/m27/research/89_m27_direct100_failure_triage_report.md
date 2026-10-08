# Stage 30I: Direct100 failure triage and targeted repair

## Final decision
`M27_DIRECT100_FAILURE_TRIAGE_FAIL_THIN_CITED_ANSWER`

## Boundary
Stage 30I is an isolated worktree. No production M26, test backend, owner-only authenticated route, protected owner materials, Nginx, release pointers, or production datastore were changed. No full523, Stage13/14, Chunk002, or mature composer delegation.

## Preflight
- 30H HEAD, 30G artifact commit, and expected image verified.
- All three runtime health responses HTTP 200 at `/v1/health`; `/health` is not the supported endpoint.
- Four direct100 evidence files present and read; 30H handoff and evaluator inspected.
- Source: frozen M26 200-case population; Direct100 deterministic 100-sample with 13 expected safe and 87 answerable.

## Nine adjudications
- 8/8 missed safe terminals: `TRUE_RUNTIME_SAFE_MISS` (HIGH), not label drift. All queries request an **exact release-linked production traffic volume**; none of the emitted answers supplies that measurement. Citations semantically support unrelated technical excerpts only.
- 1/1 thin answer: `TRUE_THIN_CITED_ANSWER` (HIGH). Question asks harness provenance identities; citation and answer refer to IRAS corporate tax exemptions. This also establishes cross-domain question/answer mismatch that the old contamination heuristic did not detect.
- See `89_m27_direct100_failure_adjudication_matrix.csv` for case-by-case details and source provenance.
- No label overrides. No corpus-version drift proved. Independent current corpus version reconciliation has not been established; evidence is sufficient to decide these responses failed their question obligations.

## Targeted code repair
Isolated `src/knowledge_engine/m27_agent_product_runtime.py` adds `_question_obligation_gap` and fail-closed publication blocking for explicit exact production traffic measurements and provenance-identity questions. The gate uses question-class requirements, not question IDs or dataset labels; semantic provider thresholds unchanged. It does **not** reintroduce mature M26 composer delegation.

6 deterministic AST-extracted guard unit tests PASS. Full integrated runtime tests and live candidate validation have **not** passed, so this is an unpromoted code candidate, not a completed fix. The new rule requires explicit release-linked measurement and does not manufacture unknown metrics.

## Frozen vs adjudicated score
- Frozen labels: 5/13 safe terminals; 8 missed; 86/87 answerable cited finals; 1 thin cited answer; 0 false safe.
- Adjudicated labels: exactly the same, as the observed answers did not satisfy the question. No relabeling used to lift score.
- Existing p95 final 6.31s and first-material 6.30s describe only old Stage30H image. No new performance claim.

## Verification blocked from PASS
The requested 9-case live targeted rerun and exactly-same-100 full rerun were **not executed**, because isolated source changes have not been built into a candidate and the existing 18080 candidate is the separate preexisting image. Avoiding replacement of that service preserves the owner-only candidate boundary. The offline fix cannot be claimed sufficient. Moreover, the thin answer requires better evidence selection/grounded response or a justified safe terminal, and this remains unverified.

## Required next verification
Build an isolated direct-only candidate from the 30I commit without displacing owner-only routing, run 9 targeted cases and ensure all question-obligation failures fail closed or produce truly responsive cited answers, independently adjudicate thin case, and only then run exactly the same Direct100 population with frozen and adjudicated metrics in parallel. If it cannot achieve an answerable cited final without irrelevant tax evidence, do not count the thin case as pass.

Owner-only route certification remains pending and must not be inferred from this result.
