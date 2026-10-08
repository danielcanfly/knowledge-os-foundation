# Stage 28 Handoff

Final state: `M27_OWNER_ONLY_CANARY_ACTIVATED`

Owner-only canary is active. Non-owner traffic falls back to M26 production. Candidate and auth sidecar are loopback-only.

Active pieces:

- M27 candidate: Docker container `m27-owner-canary-28`, port `127.0.0.1:18080`.
- Owner-auth sidecar: host process from `/tmp/m27_owner_auth_28.pid`, port `127.0.0.1:18081`.
- Nginx site: `/etc/nginx/sites-enabled/llamaindex-demo`.
- Route id: `m27-owner-only-stage28`.

Route-to-zero:

```bash
sudo cp /tmp/llamaindex-demo.pre-m27-owner-canary-20261008T020954Z /etc/nginx/sites-enabled/llamaindex-demo
sudo nginx -t
sudo systemctl reload nginx
docker rm -f m27-owner-canary-28
if [ -f /tmp/m27_owner_auth_28.pid ]; then kill "$(cat /tmp/m27_owner_auth_28.pid)" || true; fi
```

Monitoring focus: non-owner fallback, any 5xx, empty nonterminal, false safe-terminal for answerable queries, p95 final latency above 15s, missing route/candidate telemetry, or any secret in logs/artifacts.

Preserve the Stage 25 raw comparison provenance warning.
