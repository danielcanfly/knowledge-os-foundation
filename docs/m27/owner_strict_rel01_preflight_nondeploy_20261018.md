# Owner strict REL01 release criteria: add-only Nonprod checker

Purpose: an additional **read-only, failclosed numerical preflight** for current M27 release governance. It does not replace the historic `m27_release_hard_gates.py`, rewrite baseline receipts or amend Q34/Production. Its output can never certify REL01 or authorize REL02 until independent external signature verification is supplied in a distinct, genuinely permitted process.

## Defect in historical gate semantics
- `m27_release_hard_gates.admission_receipts_checks` rejects cited-rate only if `rate < 0.95`; this permits equality 95%. The Owner's latest user threshold for real successes is strictly **>95%**, requiring >=497 actual verified successes out of 523.
- `m27_release_hard_gates.evaluate_quality_hard_gate` similarly permits exactly **85/100**, but Owner latest strict requirement is **>85/100**.
- `decide_release_hard_gates` combines admission, quality and first-text streaming but does not itself independently prove the required **complete final-answer p95 <15s** on the same Product.
- The explicitly referenced rubric at `/Users/huaihsuanhuang/Desktop/語意問題/問題評分標準.md`, SHA `f0f3c2e66dad1b4520a77835d2340f4e471a3af435e2e5f2232f3855640db849`, is an M26 **homepage Suggested Questions** rubric, including homepage visitor fit and distinctiveness. It is not automatically a universal engineering-task answer-quality score. Missing independent applicability review must remain HOLD.

## Scope of the new implementation
`m27_owner_strict_rel01_preflight.py` uses standard-library-only numeric checks:
- exactly 523 raw unique case rows, one pinned 40-hex source HEAD and one signed image digest per row, complete latency and per-case verified cited-supported success outcomes;
- strict 497/523 minimum success count, quality strictly >85, nearest-rank p95 (497th of 523 ordered latencies) strictly below 15,000ms; fails closed on NaN, missing latency, terminal error, timeout, duplicate case IDs, quality source mismatch or incorrect rubric scope;
- **numeric consistency is never formal attestation**: `current_formal_admission` returns REL01 HOLD / REL02 unauthorized / Production false even if numbers or caller-fabricated receipt booleans are positive, until actual independent cryptographic receipt verifier and registered trust roots are available.
- The genuine D02 registry previously inspected contains `formal_enabled_issuer_count:0` and `issuers:{}`; original Master C28/E27/B27/F35 and H01 signoffs are HOLD. Never create fake keys, self-endorse, or upgrade synthetic fixtures.
- Standalone CLI is a read-only tool; real current Gate State CLI execution was **denied by LocalBridge MCP policy**, and must **not** be retried via another host, shell or tool. This restriction is binding. Existing read-only evidence is sufficient to conclude NOT CERTIFIED.

## Verification
Adversarial Python 3.11 and 3.14 tests cover numeric 496 vs 497, exact 85, exact 15s, p95 percentile, all 523 raw IDs/latencies, NaN, other image/version, rubric scope and SHA, bogus signed receipt ignored, absent authority. Test fixtures are synthetic and never represent real official523, Independent Scorer or independent200. Original fail output for import-path/legacy Provider side effects preserved; isolated source loading avoids touching old M26 Provider.

**Current formal status:** P0 HOLD, P1 HOLD, H03 C28 NOT_RUN, P3 523/200/F35 NOT_RUN, REL01 NOT_CERTIFIED, REL02 OWNER NO-GO. No Production or released Source Pointer change.
