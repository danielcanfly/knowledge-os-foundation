# M27 Stage 30F Semantic Entailment Provider Selection

## Final decision
\`M27_SEMANTIC_ENTAILMENT_PROVIDER_SELECTION_FAIL_SCHEMA\`

## Evidence and baseline
Stage 30E HEAD \`af590b16f72b50f12767aa4083894b6842470986\`; new isolated Stage 30F worktree. 30E literal baseline cannot establish semantic entailment.

## Provider inventory and selection
See \`86_m27_semantic_entailment_provider_inventory.md\`. MiniMax-M3 generic provider client is installed in the running isolated candidate with existing runtime-safe configuration. It is considered only for narrow semantic NLI judging; independent calibration, not mere API reachability, determines acceptance. No M26 mature answer composer delegation.

## Offline dataset
47 independently labeled synthetic cases: direct 7, paraphrase 7, topical-only 6, unsupported 6, contradicted 6, cross-language 5, multi-passage 5, thin-cited negatives 5. All explicit Kubernetes, x402, hotel contamination themes included. This is an offline *synthetic* dataset and is not direct-20, 100, full523 or owner-route certification.

## Calibration results
Cases with obtained provider output: 47/47.
False-positive accepted negative cases: 0.
Malformed/schema-invalid cases: 1.

| Category | Count | Accepted as supported | Support rate |
| --- | --- | --- | --- |
| DIRECT_SUPPORT | 7 | 7 | 1.0 |
| PARAPHRASE_SUPPORT | 7 | 6 | 0.8571 |
| TOPICAL_ONLY | 6 | 0 | 0.0 |
| UNSUPPORTED | 6 | 0 | 0.0 |
| CONTRADICTED | 6 | 0 | 0.0 |
| CROSS_LANGUAGE_SUPPORT | 5 | 5 | 1.0 |
| CLUSTER_SUPPORT | 5 | 5 | 1.0 |
| THIN_CITED_NEGATIVE | 5 | 0 | 0.0 |

## False positives and recall
No publication PASS is allowed with a single accepted negative (topical, unsupported, contradicted, or misleading thin citation). Direct >=0.90, paraphrase >=0.70, cross-language >=0.60, multi-passage >=0.60 required. Invalid JSON/schema must abstain. No reliance on literal overlap or citation presence.

## Runtime and integration
Offline adapter and schema checks exist in isolated worktree. Integration to M27 publication gate: **not authorized unless all offline gates pass and deterministic integration tests succeed**. Active 18080 rebuilt: **NO**. Production 8080, test backend 8081, Nginx, release pointer and production datastore: **UNTOUCHED**. Public/owner-gated route: **NOT USED**.

Owner-only route certification remains pending and must not be inferred from this result.
