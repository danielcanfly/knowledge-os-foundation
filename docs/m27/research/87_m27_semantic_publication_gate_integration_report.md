# Stage 30G — M27 Semantic Publication Gate Integration

## Final decision

M27_SEMANTIC_PUBLICATION_GATE_INTEGRATION_FAIL_RETRIEVAL

The semantic publication gate integration itself is implemented and its deterministic offline gate passes. The isolated candidate rebuild is healthy and the calibrated semantic verifier fails closed correctly. Stage 30G cannot PASS because the required direct 20-case product gate fails on retrieval/evidence coverage: only 5/18 answerable cases produce a semantically verified cited final.

## Workspace and code identity

- Workspace: /home/ubuntu/LLM_Wiki-m27-semantic-publication-gate-30g
- Branch: m27/stage30g-semantic-publication-gate
- Base Stage 30F HEAD: 1c4af5302a407ee4444ae95e17abd1e3d1d9d344
- Semantic/retrieval implementation HEAD used by active candidate: 1511d934b9d43b5633063bbe6a19c105376d14b4
- Candidate before Stage 30G: knowledge-engine:m27-owner-canary-29v
- Candidate after Stage 30G rebuild: knowledge-engine:m27-semantic-publication-gate-30g-1511d934
- Rollback retained: stopped container m27-owner-canary-28-pre30g, image knowledge-engine:m27-owner-canary-29v

## Integration implemented

The M27 native publication path now:
1. extracts bound material claim surfaces from source passages,
2. binds every claim to explicit citation evidence IDs,
3. calls the Stage 30F-calibrated narrow semantic NLI provider through the M27 adapter,
4. accepts only calibrated positive semantic support,
5. requires true multi-evidence references for CLUSTER_SUPPORT,
6. rejects topical-only, unsupported, contradicted, low-confidence, invalid-schema, invalid-evidence-reference, missing-provider and unavailable-provider results,
7. permits at most one fresh schema retry and never repairs illegal enum casing,
8. records sanitized claim/evidence/support/provider/confidence/retry/fail-closed receipts,
9. keeps citation presence and lexical/canonical overlap strictly outside semantic proof,
10. rejects thin cited publication,
11. contains no M26 mature answer-composer delegation.

## Offline integration gate

PASS: 20/20 deterministic offline cases.

Coverage includes direct support, paraphrase, cross-language provider-verified support, multi-passage cluster support, single-passage fake cluster rejection, topical-only, unsupported, contradicted, citation-without-support, low confidence, bounded schema retry, invalid schema after retry, provider unavailable, invalid evidence references, Kubernetes/x402/hotel contamination, thin cited answer, positive runtime publication path, sanitized receipts, and no M26 composer delegation.

## Isolated rebuild

Rebuild was allowed only after offline PASS.

- 18080 /v1/health: HTTP 200
- 8080 /v1/health: HTTP 200 postflight
- 8081 /v1/health: HTTP 200 postflight
- Active image: knowledge-engine:m27-semantic-publication-gate-30g-1511d934
- Rollback image retained and not deleted.
- No Nginx change/reload.
- No production M26 restart/rebuild.
- No test backend restart/rebuild.
- No release pointer mutation.

## Direct 20-case final run

Direct endpoint only: 127.0.0.1:18080/v1/answers/stream.

| Metric | Result |
| --- | ---: |
| HTTP success | 20/20 |
| Answerable cited final | 5/18 |
| Expected safe terminal | 2/2 |
| False safe terminal | 13 |
| Empty nonterminal | 0 |
| Thin cited published | 0 |
| Topic contamination | 0 |
| Semantic bad-publish | 0 |
| p50 final | 491.527 ms |
| p95 final | 11747.02 ms |
| p50 first-material | 485.582 ms |
| p95 first-material | 11745.247 ms |

Latency is within the <15s gate and no unsupported semantic publication escaped. Product success still fails because 13 answerable cases fail closed.

## Retrieval root cause

A generic retrieval repair was applied after the first direct20:
- original user terms dominate ranking,
- canonical expansion is recall-only,
- strong same-source passages are no longer discarded merely to manufacture source diversity,
- insufficient source breadth is diagnostic rather than semantic proof,
- cross-language generic expansion noise is suppressed when a domain-specific expansion exists.

After this repair the earlier premature TRUE_NO_EVIDENCE / hard source-breadth failures largely converted into UNSUPPORTED_CLAIM_SPAN or PRODUCT_THIN_SURFACE. The answerable cited-final count remained 5/18. That is the decisive signal: retrieval can surface candidates, but the bound production corpus still does not contain enough direct semantic support for these queries.

The current production bundle was independently read in read-only mode and matches the candidate snapshot exactly: release m26blog-2882cfb8adae-b73886128198-212ced6f5c79, promoted 2026-09-22T12:25:19.742793Z, 4861 lexical documents. Corpus inspection found no direct AI infrastructure or private AI content and no production-corpus source for the M27 context-native runtime. Repo-local M27 architecture documentation exists, but it was not injected as ad-hoc evidence because Stage 30G forbids special-casing the 20-case set and requires evidence-bound publication.

Therefore the remaining failure is classified as retrieval/evidence-corpus coverage, not verifier weakness. Lowering verifier standards would make the gate less correct.

## 100 / 523

- 100-case: NOT RUN because direct20 failed.
- full523: NOT RUN and not authorized.

## Safety closure

No owner-authenticated public route was used. No protected owner verification material was accessed. No production datastore write occurred. No Stage13/14 or Chunk002 work was performed. Owner-only route certification remains pending; no certification is inferred from Stage 30G.
