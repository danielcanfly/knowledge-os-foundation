# 64 Test Page Owner-Bypass 19R Side-by-Side Report

Final state: `M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`

Stage 19R resolved the previous comparison blocker enough to run the bounded 20-case owner-only M26-vs-M27 product comparison. The M26 preflight returned HTTP 200 and did not hit `429 DAILY_IP_LIMIT_EXCEEDED`.

## Metrics

| Metric | M26 test backend | M27 candidate |
|---|---:|---:|
| HTTP success rate | 85.0% | 100.0% |
| Cited-answer rate | 88.24% | 50.0% |
| Safe-terminal rate | 5.88% | 50.0% |
| p50 final latency | 2624.350 ms | 17393.541 ms |
| p95 final latency | 13486.174 ms | 38754.335 ms |
| p50 first material event | 2621.920 ms | 17392.232 ms |
| p95 first material event | 13109.543 ms | 38754.194 ms |
| 429 rate | 0.0% | 0.0% |

## Verdict

M27 is callable, but the live product surface is not ready for canary consideration. The cited-answer rate is too low, safe-terminal frequency is too high, and latency/first-material latency are materially worse than M26 in this bounded run.

No production deploy, canary activation, release pointer mutation, public Nginx routing change, production restart/rebuild, production datastore write, quota reset, rate-limit increase, admission/full523 rerun, Stage13/14, or Chunk002 was performed.

## Final cleanup proof

- M27 eval/candidate containers after cleanup: none.
- port `18080` after cleanup: free.
- production health after cleanup: OK.
- production build SHA after cleanup: `7d4b2358464654bf3de7d9561ec89de841d279bd`.
- production entrypoint after cleanup: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`.
- M26 test backend health after cleanup: OK.
- Nginx checksum after cleanup: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`.
- final state: `M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`.
