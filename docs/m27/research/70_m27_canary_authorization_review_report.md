# 70 M27 Canary Authorization Review Report

Final state: `M27_CANARY_AUTHORIZATION_READY`

## Scope

This was a canary authorization review only. It did not activate canary, deploy production, mutate a release pointer, change public routing, restart production M26, write production datastores, rerun admission/full523, run Stage13/14, or run Chunk002.

Workspace: `/home/ubuntu/LLM_Wiki-m27-2027-agent-product-gate-repair-25`

Branch: `m27/2027-agent-product-gate-repair-25`

Reviewed Stage 25 HEAD: `6d0ac012e5b8f43a1de86b812a932bdf2f0dc3d4`

## Evidence integrity decision

All required Stage 25 artifacts exist. Stage 25 receipts report final state `M27_2027_AGENT_PRODUCT_GATE_READY_FOR_CANARY_CONSIDERATION`. The committed receipts/report support the same-run 20-case decision: M26 cases `20`, M27 cases `20`, case ids `C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20`.

| Gate | Decision | Evidence |
|---|---:|---|
| M27 p95 final latency <15s | PASS | `9136.395` ms |
| M27 p95 first material <15s | PASS | `9124.25` ms |
| M27 answerable final-answer success >95% | PASS | `18/18 = 100.0%` |
| Successful final answers Owner rubric >=85 | PASS | min `87` |
| False safe terminal count | PASS | `0` |
| Empty nonterminal count | PASS | `0` |
| Thin cited answer count | PASS | `0` |
| Browser Use warning case | PASS | `True` |
| C15/C16 multilingual | PASS | both cited answers in Stage 25 report |
| No worse than same-run M26 | PASS | `True` |

Evidence note: Stage 25 receipts contain `raw_compare_receipt = docs/m27/research/m27_2027_agent_product_gate_repair_receipts.raw_compare2.json`, but that raw compare file is not present in the committed tree. This is recorded as a provenance warning and a pre-canary cleanup task, not as an authorization blocker, because the committed Stage 25 report and receipts preserve the reviewed aggregate gate metrics and M27 per-case product receipts.

## Same-run M26 vs M27 metrics

| Metric | M26 | M27 | Result |
|---|---:|---:|---|
| HTTP success | `85.0%` | `100.0%` | M27 better |
| p95 final latency ms | `11495.034` | `9136.395` | M27 better |
| p95 first material ms | `10421.557` | `9124.25` | M27 better |
| 429 rate | `0.0%` | `0.0%` | tie |
| timeout/error rate | `15.0%` | `0.0%` | M27 better |

## M27-native dependency audit

| Reference | Classification | Decision |
|---|---|---|
| `m27_agent_product_runtime.py` | M27-native product runtime | PASS: no M26 import; product answer generation is claim-native. |
| `m27_test_page_executor.py` import of `m26_aq_semantic_contract` | allowed neutral helper / bundle helper, suspicious namespace | PASS with cleanup: used for canonical bundle assertion and pre-retrieval safety helpers, not composer delegation. |
| `m27_test_page_executor.py` import of `m26_pa7_arbitrary_query_runtime` | allowed neutral safety/normalization helper, suspicious namespace | PASS with cleanup: used for normalization and safety heuristics only. |
| `ProductionAnswerBundle` | allowed bundle/provenance helper | PASS. |
| Legacy provider block after product-path return | suspicious but not used in product path | PASS with required cleanup: product path returns at line 300 before this block. |
| `m27_runtime_execution.py` M26 compiler/envelope helpers | allowed neutral/provenance helper | PASS. Stage 25 removed direct `synthesize_and_verify` import. |

No disallowed M26 mature answer composer dependency was found. No `run_owner_arbitrary_query` or `synthesize_and_verify` delegation is used as the M27 product path.

## Canary plan

Documentation-only plan draft created at `docs/m27/canary/M27_CANARY_AUTHORIZATION_PLAN_DRAFT.md`. It covers candidate identity, exact commit, loopback route target, owner-only or tiny traffic scope, route-to-zero procedure, health and stream smoke endpoints, alert thresholds, logs/metrics locations, no-write datastore proof, public route isolation, sensitive-value redaction, stop conditions, maximum observation window, and Owner-only activation authority.

## Observability decision

Sufficient for owner-only canary planning. Existing Stage 25 evidence includes product answer state transitions, claim-ready timestamp, cited-segment-ready timestamp, first-material timestamp, final timestamp, per-case metrics, gap taxonomy, safe-terminal reason, provider call count/duration, and redacted execution summary.

Activation-session requirements: persist route id and candidate id per request, and tighten non-null retrieval/evidence-admission timing where applicable.

## Production safety proof

Read-only checks observed during review:

- production 8080 health OK with build `7d4b2358464654bf3de7d9561ec89de841d279bd` and entrypoint `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`.
- M26 test backend 8081 health OK with build `f746822503b7b27b2f5d4bb98ad406b15f558732` and the same entrypoint.
- port 18080 free.
- active labeled M27 eval containers: none.
- Nginx site checksum: `1d1c4edfddca4da6c89a054a0ddf33179bbe3265e21666f2e8a49a1606045219`.
- Nginx main config checksum: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`.

No production route mutation, release pointer mutation, production restart/rebuild, production datastore write, admission/full523 rerun, or canary activation occurred in this review.

## Validation

- `python3 -m compileall src scripts tests`: PASS, exit 0.
- Focused pytest: unavailable on host, `No module named pytest`.
- Stage 25 receipts JSON load: PASS.
- `git diff --check` before Stage 26 artifact writing: PASS.

## Decision

`M27_CANARY_AUTHORIZATION_READY`

This authorizes a later explicit canary planning/activation session to proceed. It does not authorize activation by itself.
