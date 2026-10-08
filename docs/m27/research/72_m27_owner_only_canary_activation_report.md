# Stage 28 Owner-only Canary Activation Report

Final state: `M27_OWNER_ONLY_CANARY_ACTIVATED`

## Summary

Stage 28 continued from the initial blocked state by adding a fail-closed Owner-auth sidecar and an audited Nginx owner-only route. The route is active only for requests presenting the private Stage 28 Owner canary header. Non-owner or auth-sidecar failure traffic falls back to M26 production on `127.0.0.1:8080`.

## Candidate identity

- Route id: `m27-owner-only-stage28`
- Candidate container: `2be5117a5b47`
- Candidate git SHA: `b72b2ec9ac95b4bff9c24177002522c9a07039e1`
- Runtime identity: `m27-production-equivalent-runtime`
- Loopback target: `127.0.0.1:18080/v1/answers/stream`
- Auth sidecar: `127.0.0.1:18081`

## Route and isolation proof

- Nginx `auth_request` validates Owner identity through the sidecar before M27 routing.
- The private Owner header is explicitly cleared before proxying to M27.
- Non-owner request proof: HTTP 200 via fallback, M27 stream schema absent.
- Owner smoke proof: 5/5 requests resolved to M27 candidate.
- Nginx config test passed before reload.
- No release pointer was mutated. No public percentage canary was created.

## Smoke results

- Ordinary answerable query: answered, 507 ms final latency.
- Browser Use warning query: answered, 528 ms final latency.
- Multilingual query: answered, 385 ms final latency.
- Prompt-injection/private-secret query: safe terminal, 98 ms final latency.
- Underspecified query: safe terminal, 43 ms final latency.
- Smoke p95/max final latency: 528 ms, below 15,000 ms.
- Stop conditions: none.

## Production safety

- M26 8080 stayed healthy.
- Test backend 8081 stayed healthy.
- Candidate is loopback-only on port 18080.
- Auth sidecar is loopback-only on port 18081.
- Nginx main checksum unchanged: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`.
- Nginx site checksum changed only for the owner-only route: `289f235410196a12fa366a3e1110c30bf3eb7362fc3aab9f49d1aeba94d40d9f`.
- Production datastore write: none.
- M26 restart/rebuild: none.

## Route-to-zero readiness

Rollback backup: `/tmp/llamaindex-demo.pre-m27-owner-canary-20261008T020954Z`.

Route-to-zero command:

```bash
sudo cp /tmp/llamaindex-demo.pre-m27-owner-canary-20261008T020954Z /etc/nginx/sites-enabled/llamaindex-demo
sudo nginx -t
sudo systemctl reload nginx
docker rm -f m27-owner-canary-28
if [ -f /tmp/m27_owner_auth_28.pid ]; then kill "$(cat /tmp/m27_owner_auth_28.pid)" || true; fi
```

## Stage 25 provenance warning

Raw Stage 25 compare evidence remains unrecovered. This is carried forward as `raw_compare_recovered=false`, `raw_compare_fabricated=false`, `committed_evidence_available=true`, and `warning_carried_forward=true`.
