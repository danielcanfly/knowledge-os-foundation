# F03 immutable Git blob reuse for real first-party A05 retrieval | 2026-10-18
**Scoped Nonprod performance engineering for AR03 Context/Capability, not Product answer cache/Provider/semantic-qualification or final p95 certification.**

## Measured defect
- 20 existing real first-party `PolicyEngine` source retrievals on this MacBook: median 2207.54 ms, p95 nearest-rank 2974.50 ms, worst 6170.43 ms, all source-candidate status.
- One-call `cProfile`: 3.261s total, `_pinned` 27 Git `cat-file blob BASE_H02:path` commands and 3.107s cumulative subprocess time; actual A05 scoring only ~18ms. Raw `09_A05_ONE_CALL_CPROFILE.txt`, baseline `08_REAL_A05_SOURCE_RETRIEVAL_TIMING.json`.
- Original fixed ancestor Git commit `7966e9c766a38a22cd91432edb5dbf2115eff305` is content addressed; `relative` is a normalized input constrained by the original function's guard.

## Change and invariants
Only per-instance `A05OwnerCorpusAdmission._pinned` immutable blob bytes are memoized behind a reentrant lock. No memoized question, result, citation, source file on disk, revocation receipt, IdP, license, tenant, TTL or callback.
Every `source_retrieval` still calls `_pinned_release` before and after query, re-opens and SHA-validates corpus/release and all 11 real documents against the exact Git object bytes, runs original adapter validation and BM25, rechecks `_epoch`/owner OS fence and revocation, rereads final citation spans before candidate is returned. Source changes after warm must produce DENY. No Product Cache HIT/WRITE, no generated answer.
The first cold query still accesses Git and validates every source; warm queries reuse only static baseline. New processes have independent cache. This only improves long-lived H02/F03 instances, not one-shot cold startup or any full model request.

## Result
- After change 20 more real A05 retrievals (no external Provider): first cold 1297.95 ms, median 32.87 ms, p95 nearest rank 44.80ms, worst 1297.95ms. Improvement of local subsystem p95 ~98.5% versus before sample; this is a sequential before/after diagnostic, not randomized controlled experiment or official current-product p95.
- After negative tests: raw changed local document after warm `DENY`, changed local fence epoch `DENY`, git-parent path traversal `DENY`, duplicate Git blob launches suppressed for same reader. Existing F03/H02 end-to-end locally authorized source and OS Client positive/negative suites were rerun.
- Raw results under `02_REPORTS/PARALLEL_VNEXT_20261014/REPLAN_EK_20261017/M27_OWNER_DIRECT_G02_CONFORMANCE_20261018/`, specifically `11_AFTER_IMMUTABLE_GIT_PIN_20_REAL_A05_TIMINGS.json` and `10_A05_IMMUTABLE_PIN_NEGATIVE_*.log`.

## Strict release boundary
Final Owner test remains **success >95%** on independent fixed 523 (>=497 actual successes), **independently graded quality >85/100** using Owner's named Suggested Questions rubric and its hard fails, and **complete-answer p95 <15s** on same source/data/Provider/Image/Client. This code does NOT produce semantic QA answers, nor independently qualified Issuer or remote Rights. H01 0/9, 523 0/523, unseen 200 0/200, F35/REL01 HOLD, Production NO-GO. Note: the source-pinned G02 Charter remains exact original Desktop bytes; the 2026-10-18 stricter Owner acceptance is stored as a separate addendum, never injected into immutable first-party source bytes.
