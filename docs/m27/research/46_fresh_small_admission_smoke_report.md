# M27 05 Fresh Small Admission Smoke Report

State: `M27_FRESH_SMALL_SMOKE_COMPLETE`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-fresh-small-smoke`
Branch: `m27/fresh-small-smoke`
Base 04 HEAD: `cbc3ec9d7353f564ef11687ca590830e36253c2e`
Preflight repair HEAD consumed: `a4ff446c7947940fd1480624722a099bd3e27503`
05 merge HEAD used for smoke: `fbc5ee1fc5b1de852a055ccded887a5b14115bc1`

## 1. Boundary

This session reran 05 Fresh Small Admission Smoke after the authorized preflight repair. It did not run Stage13/14 legacy admission, Chunk002, 100-case, or full523. It did not tune failed cases and did not mutate production.

## 2. 05 live preflight result

05 reran its own live preflight before question 1.

- endpoint: `http://127.0.0.1:18080`
- endpoint module: `knowledge_engine.m27_isolated_http:app`
- runtime identity: `m27-production-equivalent-runtime`
- build SHA: `fbc5ee1fc5b1de852a055ccded887a5b14115bc1`
- image digest: `sha256:38bff76a9e87fbf512f6a64ac7ce4a91d4ffdea7fe5a8f546a6ca327d0affd8e`
- container: `28b63c285ed4 m27-isolated-eval-05r`
- exactly-one eval container: YES
- host guard: available 372 MB, swap 566 MB, load 1.26
- quota active requests: `0`
- quota provider calls before question 1: `0`
- smoke questions sent before preflight completion: `0`
- production identity stable: YES

A first preflight attempt correctly blocked because the startup script defaulted to the 05R workspace and exposed build SHA `a4ff446c...` instead of the 05 merge HEAD. No smoke question was sent in that blocked attempt. The preflight was rerun with the 05 worktree path explicitly supplied and then authorized.

## 3. Smoke shape

Bounded smoke case count: `12`.

Category coverage:

- abstention: 2
- cited_answer: 4
- deadline_pressure: 1
- m26_baseline_invariant: 1
- multilingual: 1
- retrieval_hard: 3

Representative areas covered: cited answers, safe abstention, multilingual prompt, retrieval-hard drift rejection, deadline/budget pressure, and M26 feature-off invariant.

## 4. Results summary

- passed: `12 / 12`
- failed cases: `[]`
- p50 latency: `23.598 ms`
- p95 latency: `41.147 ms`
- max latency: `69.463 ms`
- provider calls total: `16` deterministic harness calls
- production touched any: `False`
- streaming status: `unsupported_by_05R_preflight_endpoint; harness-level smoke records terminal answer receipts`
- receipts: `docs/m27/research/fresh_small_smoke_receipts.json`

## 5. Case receipts

| Case | Category | Expectation | Status | Terminal | Citations | Provider calls | Latency ms | Passed |
|---|---|---|---|---|---:|---:|---:|---|
| SMOKE001 | cited_answer | verified_cited_answer | M27_RUNTIME_COMPOSED | VERIFIED_CITED_ANSWER | 1 | 2 | 39.096 | True |
| SMOKE002 | cited_answer | verified_cited_answer | M27_RUNTIME_COMPOSED | VERIFIED_CITED_ANSWER | 1 | 2 | 69.463 | True |
| SMOKE003 | cited_answer | verified_cited_answer | M27_RUNTIME_COMPOSED | VERIFIED_CITED_ANSWER | 1 | 2 | 20.35 | True |
| SMOKE004 | multilingual | verified_cited_answer | M27_RUNTIME_COMPOSED | VERIFIED_CITED_ANSWER | 1 | 2 | 26.846 | True |
| SMOKE005 | retrieval_hard | verified_cited_answer | M27_RUNTIME_COMPOSED | VERIFIED_CITED_ANSWER | 1 | 2 | 41.147 | True |
| SMOKE006 | abstention | safe_abstention | M27_RUNTIME_SAFE_TERMINAL | VERIFIER_GAP_SAFE_TERMINAL | 0 | 2 | 18.775 | True |
| SMOKE007 | abstention | safe_abstention | M27_RUNTIME_SAFE_TERMINAL | VERIFIER_GAP_SAFE_TERMINAL | 0 | 2 | 27.043 | True |
| SMOKE008 | retrieval_hard | rejected_before_provider | M27_RUNTIME_SAFE_TERMINAL | VERIFIER_GAP_SAFE_TERMINAL | 0 | 0 | 14.387 | True |
| SMOKE009 | retrieval_hard | rejected_before_provider | M27_RUNTIME_SAFE_TERMINAL | VERIFIER_GAP_SAFE_TERMINAL | 0 | 0 | 14.744 | True |
| SMOKE010 | deadline_pressure | budget_terminal | M27_RUNTIME_SAFE_TERMINAL | None | 0 | 0 | 37.661 | True |
| SMOKE011 | m26_baseline_invariant | m26_invariant | M26_BASELINE_UNCHANGED | None | 0 | 0 | 0.02 | True |
| SMOKE012 | cited_answer | verified_cited_answer | M27_RUNTIME_COMPOSED | VERIFIED_CITED_ANSWER | 1 | 2 | 19.001 | True |

## 6. Citation correctness

All verified answer cases returned `M27_RUNTIME_COMPOSED`, `VERIFIED_CITED_ANSWER`, at least one citation, and production-equivalent evidence authority metadata. Retrieval-hard drift cases returned safe terminal with zero provider calls and zero citations.

## 7. Answer quality / abstention correctness

Cited-answer and multilingual cases reached verified cited answers. Abstention cases reached `M27_RUNTIME_SAFE_TERMINAL` with `VERIFIER_GAP_SAFE_TERMINAL`, zero citations, and owner-only safe abstention telemetry. Deadline/budget pressure reached `BUDGET_NOT_AUTHORITATIVE` before retrieval or provider calls. Feature-off returned `M26_BASELINE_UNCHANGED`.

## 8. Latency attribution

Runtime telemetry recorded stage-level latency per case, including tool, evidence binding, compiler, provider, verifier, and round total timings. Smoke-level latency summary was p50 `23.598 ms`, p95 `41.147 ms`, max `69.463 ms`.

## 9. Cleanup and production after-check

The session removed only the owned isolated eval container with label `com.daniel.m27.eval=true`. A follow-up docker check found no live `m27-isolated-eval` container and no listener on 18080.

Production after cleanup:

- ok: `True`
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- production identity stable before/after cleanup: YES

## 10. Forbidden-action audit

- Stage13/14 legacy admission: NOT RUN
- Chunk002: NOT RUN
- 100-case: NOT RUN
- full523: NOT RUN
- production restart/stop/rebuild/deploy: NOT DONE
- production R2/Qdrant/SQLite/release pointer writes: NOT DONE
- benchmark/case tuning: NOT DONE

## 11. Conclusion

`M27_FRESH_SMALL_SMOKE_COMPLETE`

The production-equivalent M27 runtime is structurally ready for the next policy-work phase, based on this bounded 12-case isolated smoke. This is not a 100-case or full523 admission result.
