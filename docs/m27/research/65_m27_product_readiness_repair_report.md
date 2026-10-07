# 65 M27 Product Readiness Repair Report

## Final state

`M27_PRODUCT_READINESS_NOT_READY_WITH_DIAGNOSIS`

Generated: `2026-10-07T09:46:40Z`
Workspace: `/home/ubuntu/LLM_Wiki-m27-product-readiness-repair`
Base HEAD: `ba3fbb9779e221753800550939f011c5a660ae60`
Current HEAD at report generation: `ba3fbb9779e221753800550939f011c5a660ae60`

## Scope guard

This session stayed inside the M27 product-readiness repair lane. It did not activate canary, deploy production, mutate release pointers, rerun admission/full523, run Stage13/14, run Chunk002, restart production, or send owner-bypass material to M27. The owner-bypass token was used only as an HTTP header for the M26 test backend baseline, and serialized artifacts were scanned by the comparison script with `secret_recorded=false` and `serialized_artifact_scan_passed=true`.

## Repair performed

The Stage 19R diagnosis showed that the M27 product executor was dropping or reselecting evidence after canonical retrieval/strengthening, then spending provider budget in a partial reimplementation of the M26 answer ladder. The repair therefore made these product-integration changes:

1. Preserve the canonical strengthened evidence set instead of truncating it in `SnapshotKnowledgeProvider` / `m27_test_page_executor`.
2. After production-equivalent evidence authority admission, preserve the admitted evidence instead of sending it through the synthetic-only M26.3 compiler selector.
3. Carry the endpoint proof from canonical strengthening into the verifier path.
4. Add a canonical evidence-bound preflight and a canonical fast provider answer path before falling back to full `synthesize_and_verify`.
5. Keep verifier standards intact: no lowered citation, support, or safe-terminal thresholds; no 20-case memorization.

Changed files:

```text
src/knowledge_engine/m27_runtime_execution.py  | 181 ++++++++++++++++++++++---
 src/knowledge_engine/m27_test_page_executor.py |   8 +-
 2 files changed, 171 insertions(+), 18 deletions(-)
```

## Stage 20 bounded 20-case rerun

Receipts: `docs/m27/research/test_page_product_readiness_stage20_side_by_side_receipts.json`

| System | HTTP success | cited-answer rate | safe-terminal rate | p50 final latency | p95 final latency | p50 first material | p95 first material |
|---|---:|---:|---:|---:|---:|---:|---:|
| M26 test backend | 85.0% | 94.12% | 0.0% | 2999.967 ms | 10454.136 ms | 2996.265 ms | 10446.802 ms |
| M27 Stage 20 candidate | 100.0% | 65.0% | 35.0% | 14978.29 ms | 50723.779 ms | 14963.562 ms | 50717.224 ms |

Compared with Stage 19R, M27 improved cited-answer rate from 50.0% to 65.0%, and the Browser Use warning case now returns a cited answer. However, the production product gate is still missed: cited-answer success is below >95%, safe terminals remain too high, and p95 final/first-material latency is far above 15s.

## Per-case M27 diagnosis

| Case | Slice | Cited | Safe terminal | Latency ms | Answer chars | Diagnosis |
|---|---|---:|---:|---:|---:|---|
| C01 | browser_use_warning | True | False | 19380.184 | 872 | latency >15s |
| C03 | ordinary_cited | False | True | 8842.818 | 0 | no cited answer, verifier-gap safe terminal |
| C04 | ordinary_cited | True | False | 15757.046 | 96 | latency >15s, thin cited answer surface |
| C05 | ordinary_cited | False | True | 14172.117 | 0 | no cited answer, verifier-gap safe terminal |
| C06 | ordinary_cited | True | False | 16771.378 | 136 | latency >15s, thin cited answer surface |
| C10 | ordinary_cited | True | False | 31566.75 | 182 | latency >15s, thin cited answer surface |
| C11 | ordinary_cited | True | False | 23258.059 | 193 | latency >15s, thin cited answer surface |
| C12 | ordinary_cited | False | True | 50723.779 | 0 | no cited answer, verifier-gap safe terminal, latency >15s |
| C15 | multilingual | False | True | 27379.01 | 0 | no cited answer, verifier-gap safe terminal, latency >15s |
| C16 | multilingual | False | True | 16088.114 | 0 | no cited answer, verifier-gap safe terminal, latency >15s |
| C18 | retrieval_hard | False | True | 22518.249 | 0 | no cited answer, verifier-gap safe terminal, latency >15s |
| C20 | safe_terminal | True | False | 22702.922 | 216 | latency >15s |

## Telemetry diagnosis

Workspace telemetry copied from the candidate container showed that the remaining latency is dominated by provider time, not tool execution or compiler overhead. Representative examples:

- C12: `provider_ms=43358.461`, terminal `VERIFIER_GAP_SAFE_TERMINAL`, total telemetry `44272.354 ms`.
- C15: `provider_ms=23139.385`, terminal `VERIFIER_GAP_SAFE_TERMINAL`, total telemetry `23401.589 ms`.
- C10: `provider_ms=27048.254`, terminal `VERIFIED_CITED_ANSWER`, but answer surface was thin at 182 chars.
- C19: prompt-injection safety case returned a safe terminal quickly, about 15 ms, which is expected.

This means the remaining issue is not the read-only tool executor or production-evidence authority bridge. The unresolved seam is that M27 still lacks a fully product-ready canonical answer-publication path that can produce high-quality cited answers before the provider tail dominates.

## Canonical direct-path probe

A bounded probe of the canonical M26 product path inside the Stage 20 image showed that direct delegation can improve some cases but still does not satisfy the production gate:

- C12 can become a cited answer, but took about 19.9s with 3 provider calls.
- C15 can become a cited answer in about 9.6s with 2 provider calls.
- C16 still ended as safe abstention with semantic coverage failures.

Therefore, directly switching M27 to canonical product delegation would not be enough to claim readiness without further latency and multilingual coverage work.

## Browser Use warning case

The Browser Use warning case is improved: C01 now returns a cited answer with 3 citations. It remains too slow in the external product measurement, at about 19.38s final latency, so it is fixed for correctness but not for product latency.

## Product gate decision

Current gate definition:

- p95 final latency < 15s
- final-answer success rate > 95%
- successful final-answer output must meet Owner 85-point semantic quality threshold

Stage 20 does not meet these conditions. M27 cited-answer rate is 65.0%, safe-terminal rate is 35.0%, p95 latency is 50723.779 ms, and multiple cited answers have thin answer surfaces. The quality gate cannot be honestly claimed because too few successful final answers exist and several successful outputs are likely below the Owner 85-point bar.

## Required next repair

1. Replace the partial M27 answer-publication ladder with a complete canonical product-publication adapter, not only the preflight slices currently wired.
2. Add a deterministic, verifier-preserving product answer path for AI Infra article-style questions that produces 85-point surfaces without live provider tail.
3. Fix multilingual requirement coverage for Chinese/Japanese AI Infra questions.
4. Emit verified material as soon as a verified segment is available; the current stream still effectively emits material near completion for provider paths.
5. Rerun the exact same 20-case Stage 19R set after repair.

## Production no-change proof

- Candidate container: `m27-stage20-product-readiness`, isolated label `com.daniel.m27.eval=true`.
- Candidate endpoint: `127.0.0.1:18080` only.
- M27 candidate received no owner-bypass header.
- Owner-bypass file mode remained `0600` and secret was not printed.
- Production Nginx checksum remained `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2` before Stage 20 testing.
- Public production route was not mutated.

## Generated artifacts

- `docs/m27/research/65_m27_product_readiness_repair_report.md`
- `docs/m27/research/test_page_product_readiness_stage20_side_by_side_receipts.json`
- `docs/m27/handoffs/M27_PRODUCT_READINESS_REPAIR_HANDOFF.md`
