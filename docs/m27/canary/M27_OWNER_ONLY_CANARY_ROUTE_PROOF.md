# Stage 28 Owner-only Canary Route Proof

Decision: Owner-only route activated.

## Active route

`/v1/answers` now uses Nginx `auth_request` to call a loopback Owner-auth sidecar. If Owner validation succeeds, the request is proxied to `127.0.0.1:18080/v1/answers/stream`. If validation fails or the auth/candidate path errors, the request is internally routed to M26 production at `127.0.0.1:8080`.

## Isolation properties

- Owner-auth sidecar is bound to `127.0.0.1:18081` only.
- M27 candidate is bound to `127.0.0.1:18080` only.
- Private Owner header is cleared before M27 proxying.
- Non-owner probe returned HTTP 200 through fallback and did not include the M27 stream schema.
- Owner smoke requests produced M27 isolated stream events.

## Checksums

- Nginx main before/after: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`.
- Nginx site before: `1d1c4edfddca4da6c89a054a0ddf33179bbe3265e21666f2e8a49a1606045219`.
- Nginx site after: `289f235410196a12fa366a3e1110c30bf3eb7362fc3aab9f49d1aeba94d40d9f`.

## Route-to-zero

Restore `/tmp/llamaindex-demo.pre-m27-owner-canary-20261008T020954Z`, validate Nginx, reload, stop `m27-owner-canary-28`, and stop the auth sidecar pid in `/tmp/m27_owner_auth_28.pid`.
