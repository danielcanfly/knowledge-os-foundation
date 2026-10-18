# Real M27 complete streamed answer parity defect repair | 2026-10-18

Scope: isolated Nonprod source repair, first-party M27 `m27_release_hard_gates.evaluate_streaming_hard_gate`, no model API, no prior Q34 or Cloudflare equivalent route and no official Product Gate State mutation.

## Measured actual code defect and repair
The old streamed-final quality check compared only `cited_segments[-1].text` with the entire `final_answer_text`. This erroneously denied legitimate two-segment substantive cited answers, and could accept a final answer that matched the last segment even though the Client had already received a malicious/error-bearing first segment. It also accepted cited segments after the final-answer terminal, duplicate terminal, empty or non-string segment, and a missing final parity input in some circumstances.

Baseline was **physically run** against unmodified code using two Python versions: 10 focused scenarios, **7 FAIL** and 3 PASS in each version. Logs in `M27_OWNER_DIRECT_TRUE_STREAM_PARITY_20261018/BEFORE_EXPECTED_RED_python311.log`, `...python314.log` retained. The original source bug was not inferred only from inspection.

After repair:
- reconstruct final answer as **exact concatenation of all cited segments in event order**, fail on any source/client parity mismatch;
- reject missing final reference, empty or wrong-type cited text, or missing cited segments;
- reject cited or verified material on/after first terminal, duplicate `final_answer_done` and safe-abstention with cited material;
- maintain original source citation requirement for each emitted material event.
The code does **not** invent citations or accept unverified output. It checks what the Client actually received. New focused tests are Python 3.11 **10/10 PASS**, Python 3.14 **10/10 PASS**, with exact raw stdout/stderr SHA retained.

Original unchanged `tests/test_m27_release_hard_gates.py`: Python 3.11 and 3.14 did not have `pytest` installed; attempted pytest runner EXIT 1 missing dependency retained as separate source-environment failure. The **original 7 no-fixture test functions** were then executed without changing them through a Python standard-library import harness, using the same real source file and a minimal stub only for the unrelated streaming schema import. Original 7/7 PASS on both Python versions. This does not cover every module or the runtime's full package import side effects.

## What this DOES NOT prove
This is a real first-answer Client/verifier parity correctness fix, not a claim of the user requested >95% actual qualified outcome rate, independent quality >85 or complete-answer p95 <15 sec. No genuine new Provider requests, signer identity, full523/unseen200, ABI, Product IdP or release signing. Owner LocalBridge showed existing VM MiniMax/Cloudflare credentials as nonempty, but the attempted external Direct MiniMax diagnostic was previously blocked by tool safety and **not retried**. H02 newest local firstparty source review is still not accepted Product Native model-generated answer; F04 remains Nondeploy source-only until independently qualified.

Owner Desktop Charter `/Users/huaihsuanhuang/Desktop/06_M27_VNEXT_MASTER_ARCHITECTURE_AND_CONSTRUCTION_CHARTER_V1_20261014.md`. P0–P4 formal gates HOLD; avoid miscounting fixture PASS as 523 model outcomes.
