# Stage 30A: M27 Direct Candidate Batch Evaluation

## Final state
`M27_DIRECT_CANDIDATE_BATCH_EVAL_FAIL_PRODUCT_QUALITY`

- Workspace: `/home/ubuntu/LLM_Wiki-m27-direct-candidate-batch-eval-30a`
- Branch: `m27/stage30a-direct-candidate-eval`
- HEAD: see committed SHA in git history; this report is part of the Stage 30A commit
- Candidate container: `m27-owner-canary-28`
- Candidate image: `knowledge-engine:m27-owner-canary-29v`
- Candidate source predecessor HEAD: `914c8fc5594c63ab3cd6a55f3459245d279b1e11`
- Endpoint: `http://127.0.0.1:18080/v1/answers/stream` (direct loopback)
- Health: M26 8080 = HTTP 200; test 8081 = HTTP 200; M27 candidate 18080 = HTTP 200. Container healthy.
- Scope: 20-case direct-only, sequential; 100/523 not run due to product-quality early-stop.

## 20-case metrics

| Metric | Result |
|---|---:|
| HTTP success | 20/20 = 100% |
| Answerable cited | 18/18 = 100% |
| Safe-terminal classified for intended safe cases | 2/2 |
| False safe terminal among 18 answerable | 0 |
| Empty nonterminal | 0 |
| Suspected thin cited answers (heuristic review flags) | 13/20 |
| p50 final latency | 181.063 ms |
| p95 final latency | 5784.062 ms |
| p50 first-material latency | 178.835 ms |
| p95 first-material latency | 5781.355 ms |
| HTTP 429 | 0 |
| Owner rubric score | Not available; cannot assert >=85 |

p95 uses the existing harness's nearest-rank interpolation on all HTTP-200 cases. First material is based on streamed events, not independently verified claim usefulness.

## Failure analysis

| Cases | Observed issue | Interpretation |
|---|---|---|
| C02, C03, C04 | Generic templated response framing, weakly grounded relevance | Suspected thin citation |
| C05 | Kubernetes answer mixes unrelated x402 payment and hospitality evidence | Strong indication of retrieval/grounding drift |
| C06, C09–C14, C17–C18 | Repeated `Evidence N says` / `strongest grounded answer` template | Heuristic thin-cited risk requiring rubric verification |
| C14 | 5.784s outlier | Still below 15s p95 hard gate |
| C19, C20 | HTTP 200 with safe terminal and no cited answer | Intentional safe-terminal cases, not cited-answer failures |

13 suspected thin answers are automatic review flags, not 13 adjudicated rubric failures. Independently inspected C05 demonstrates plainly unrelated evidence for a Kubernetes question. The task's no-thin-cited-success policy prevents treating the apparent 18/18 cited answers as proven product-ready. Quality score >=85 was not established.

## Historical comparison

Known historical M26 full523 baseline: 487/523 cited (93.12%), p50 7.56s, p95 19.93s. These are not cohort-equivalent; M27 20-case numbers must not be interpreted as a comparative win. Stage 25 product-readiness is a contextual predecessor; exact comparable values not established by this run.

## Safeguards and next action

No owner bypass material, owner-only public route, Nginx mutations, release pointers, production backend mutation, or datastore writes were used. No M26 mature composer delegation was invoked by this evaluation harness; internal candidate implementation provenance was not independently certified.

**Owner-only route certification remains pending.** This evaluation is not owner-only canary certification, and it cannot establish canary HEALTHY. **Pause further owner-only route certification until runtime product quality is repaired.**

Next: isolate citation relevance and answer-composition failure in native M27, enforce query-specific evidence selection and quality rubric on representative samples, then rerun 20-case followed by conditional 100/523 direct-only evaluation. Stage 30B route-certification architecture should remain deferred.
