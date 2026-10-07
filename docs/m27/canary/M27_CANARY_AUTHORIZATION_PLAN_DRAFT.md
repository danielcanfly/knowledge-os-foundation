# M27 Canary Authorization Plan Draft

Status: documentation-only draft. This file does not activate canary, deploy production, mutate public routing, mutate a release pointer, restart production, or write production datastores.

## Candidate identity

- Source workspace: `/home/ubuntu/LLM_Wiki-m27-2027-agent-product-gate-repair-25`
- Source branch: `m27/2027-agent-product-gate-repair-25`
- Reviewed commit: `6d0ac012e5b8f43a1de86b812a932bdf2f0dc3d4`
- Candidate source identity: M27 agent-native / claim-native product path in `src/knowledge_engine/m27_agent_product_runtime.py` and `src/knowledge_engine/m27_test_page_executor.py`
- Candidate image: build only from the reviewed commit in the later canary session; do not reuse an unpinned local image.

## Route target and scope

- Candidate target: loopback-only `127.0.0.1:18080` running the isolated M27 app.
- Initial scope: owner-only. If owner-only route is unavailable, use no greater than 1% traffic only after explicit Owner approval.
- Production 8080 remains M26 unless a later session explicitly authorizes a route change.

## Route-to-zero procedure

Documentation only, not executed here.

1. Set canary traffic weight to zero or disable the owner-only canary flag.
2. Remove the temporary M27 upstream from the canary route draft.
3. Validate routing config using the standard Nginx validation command in the canary session.
4. Reload routing only after validation in that later authorized session.
5. Stop and remove only the labeled M27 canary container/process.
6. Confirm `127.0.0.1:18080` has no listener.
7. Confirm production and test backend health SHAs match expected values.

## Health and smoke endpoints

- Production health: `http://127.0.0.1:8080/v1/health`
- M26 test backend health: `http://127.0.0.1:8081/v1/health`
- Candidate health: `http://127.0.0.1:18080/v1/health`
- Candidate stream smoke: `http://127.0.0.1:18080/v1/answers/stream`

## Alert thresholds and stop conditions

Stop and route to zero if any trigger fires: p95 final latency >= 15000 ms, p95 first-material latency >= 15000 ms, product/final-answer success <= 95%, any final answer below Owner rubric 85, false safe-terminal count > 0, empty nonterminal count > 0, thin cited answer count > 0, canary 429 rate above same-run M26 baseline, any repeated 5xx, citation drift, unsupported accepted claim, or missing locator in a publishable answer.

## Logs and metrics

- Candidate container logs.
- Isolated runtime stdout/stderr with sensitive values redacted.
- Nginx logs filtered by route id / candidate id.
- Redacted canary receipt under `docs/m27/research/` after the later session.

Required per request: request id, route id, candidate id, product state transitions, claim-ready timestamp, cited-segment-ready timestamp, first-material timestamp, final timestamp, product success state, verifier gap category, safe-terminal reason, empty-nonterminal counter, provider call count/duration, retrieval/evidence timing, and redacted execution summary.

## Safety proof

- No production datastore write path: candidate reads from pinned bundle/snapshot only.
- Public route isolation: candidate starts loopback-only before explicit route authorization.
- No release pointer mutation in this review.
- Sensitive-value redaction: later session must scan receipts/log excerpts and record counts only.

## Observation window

- Owner-only: maximum 24 hours unless Owner extends.
- Tiny percentage: maximum 2 hours before route-to-zero or explicit next-step authorization.

## Authorization

Only Owner can authorize actual canary activation. This Stage 26 review authorizes planning readiness only.
