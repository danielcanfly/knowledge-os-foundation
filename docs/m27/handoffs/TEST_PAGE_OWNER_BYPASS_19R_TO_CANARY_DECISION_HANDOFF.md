# TEST PAGE OWNER BYPASS 19R TO CANARY DECISION HANDOFF

Decision: `M27_TEST_PAGE_EVAL_NOT_READY_WITH_DIAGNOSIS`

Do not advance to canary from this run.

## Evidence

- M26 owner-only preflight: HTTP 200, no 429.
- Bounded comparison: 20 cases completed.
- M27 candidate was bound to `127.0.0.1:18080` only.
- Production 8080 was not modified.
- Nginx public routing was not modified.

## Key metrics

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

## Remaining blockers

1. M27 cited-answer rate is too low.
2. M27 safe-terminal frequency is too high.
3. M27 first material event latency is too late.
4. Browser Use warning case is not cleared.
5. Independent semantic scoring was not available in this bounded run.

## Safety status

No deploy, canary activation, release pointer mutation, public routing change, production restart/rebuild, production datastore write, quota reset, rate-limit increase, admission/full523 rerun, Stage13/14, or Chunk002 occurred.
