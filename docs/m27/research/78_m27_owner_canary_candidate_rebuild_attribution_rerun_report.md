# Stage 29V Candidate Rebuild and Attribution Rerun

Final state: M27_OWNER_CANARY_ATTRIBUTION_RERUN_BLOCKED_BY_TOOL_SAFETY

- Stage 29U base HEAD: 9529d56004aff2ed7d030162f57894860b293712
- New image ID: sha256:1b1c9860e07e174cc89fa30800c6f05d745d108afc0e9b6fe5a3d3bd6d8f9e02
- New candidate container observed: 16b64806a43fccddbb9424e325cd6fef09753afa6749afbd7dd387854ab3e733
- Old candidate retained under m27-owner-canary-28-previous, not deleted.
- New candidate health: HTTP 200 /v1/health and Docker healthy.
- New candidate health build SHA matches 29U HEAD.
- Production 8080 and test backend 8081 passed preflight HTTP 200.
- Sidecar unauthenticated preflight: HTTP 401.
- Nginx owner route already includes route ID, owner_only mode, and credential-header clearing directive. No Nginx change made.
- Existing Stage 28 route-to-zero backup found.
- The tool security layer blocked the sealed observer execution request before it was run.
- No seven-smoke route-attributed receipts, verified quality decisions or latency distributions exist for this stage.
- Therefore neither HEALTHY nor route-to-zero safety failure is substantiated.
- Production and non-owner postflight still require verification.
