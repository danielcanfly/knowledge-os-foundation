# Stage 30L Direct100 provenance runtime activation report

Decision: M27_DIRECT100_PROVENANCE_RUNTIME_ACTIVATION_BLOCKED_BY_PROVIDER_CONFIG

VM: vm-dev-01; workspace: /home/ubuntu/LLM_Wiki-m27-direct100-provenance-30k; initial HEAD: 0719e40cfb5d3a3c86b7709caef3da69d7fe25e4; clean worktree. Prior Stage 30K report and handoff present. Target image knowledge-engine:m27-direct100-provenance-30k exists (image prefix 1acfa0a4db5f).

Active container m27-owner-canary-28 remains knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e bound to 127.0.0.1:18080. Rollback reference is this unchanged candidate. Correct /v1/health returned HTTP 200 on 8080, 8081 and 18080. /health initially yielded HTTP 404 because it is not the service health route.

Activation diagnosis: no verified existing secret-blind image-only deployment interface was found in the reviewed project scripts. Stage 30K's earlier provider-environment preparation was safety-blocked; it was not repeated. Secret-bearing material was not read, printed, copied, transformed, committed or exposed. No activation, candidate swap, rollback, production/test changes, owner-only observation, public route, or protected verification access occurred.

Targeted8: NOT RUN (activation prerequisite failed).
Regression9: NOT RUN.
Direct100: NOT RUN.
Full523: NOT RUN.

Owner-only route certification remains pending and must not be inferred from this result.
