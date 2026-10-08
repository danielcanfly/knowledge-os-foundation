# Stage 29U Owner Canary Route Attribution

**Decision: `M27_OWNER_CANARY_ROUTE_ATTRIBUTION_BLOCKED_BY_RUNTIME`**

## Completed

- Read Stage 29U instructions and Stage 29T reports and sealed observer; established an isolated 29U worktree.
- Confirmed active candidate container Docker health is healthy; production 8080, test 8081, candidate 18080 `/v1/health` return HTTP 200; unauthenticated sidecar returns HTTP 401.
- Inspected active Nginx config: owner-only `auth_request` and M27 upstream 18080, internal M26 fallback 8080, credential header cleared for candidate proxy. Configuration evidence **is not** runtime delivery proof.
- Added source-only M27 SSE `m27_canary_attested` event limited to expected owner-only canary route headers, with safe route/candidate identity, build SHA, random request ID and boolean credential-header presence. Added focused test covering absence of marker for ordinary requests, no raw credential leak and detection of a synthetic injected header.
- Source compiled and `git diff --check` passed; the VM default Python environment lacks pytest, so focused tests were not executable there.

## Outstanding runtime blockers

- Source changes are **not deployed** into the active M27 candidate. No credential was read or handled in this 29U session.
- Owner-to-M27 and non-owner-to-M26 routing lack independent request-correlated runtime receipts. Candidate boundary non-forwarding is unverified.
- Seven owner smoke categories and verified-M27 terminal, latency and product quality metrics are not proven.
- This stage cannot claim HEALTHY and cannot justify p95 against the 15 s gate.

## Safety and rollout

- No Nginx reload, public rollout, M26 restart, datastore writes, or release pointer mutation performed.
- No safety-impacting stop condition independently confirmed; existing owner-only canary preserved pending correctly instrumented candidate deployment and sealed validation.
- No route-to-zero executed. This is insufficient evidence, not a confirmed failure that triggers forced rollback.

## Next technical action

Deploy only the isolated M27 candidate build under a verified owner-only route-to-zero runbook, confirm the immutable candidate SHA, then extend the sealed observer to join signed/safe request identity and candidate-side telemetry; run seven cases and fail closed on any missing proof.
