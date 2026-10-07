# M27 Canary Route-to-Zero Runbook

Status: documentation and dry-run proof only. No route mutation was performed in Stage 27.

## Future activation route object

The currently authoritative public API site is `/etc/nginx/sites-enabled/llamaindex-demo`.
Production answers are the exact Nginx location `location = /v1/answers` with `proxy_pass http://127.0.0.1:8080`.
The owner test surface is `location = /test/answers` with `proxy_pass http://127.0.0.1:8081/v1/answers`.

A future canary session must create an explicitly reviewable canary route object or conditional owner-only branch that names the candidate loopback target `127.0.0.1:18080`. Stage 27 does not define or install a live route.

## Pre-route checksum

Before any future edit:

```bash
sha256sum /etc/nginx/nginx.conf
sha256sum /etc/nginx/sites-enabled/llamaindex-demo
```

Stage 27 observed:
- main: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`
- site: `1d1c4edfddca4da6c89a054a0ddf33179bbe3265e21666f2e8a49a1606045219`

Any mismatch before activation requires review and renewed Owner authorization.

## Route-to-zero

1. Require explicit Owner authorization for rollback or activation changes.
2. Set candidate weight to zero or disable the owner-only canary predicate in the exact canary route object.
3. Validate the candidate route draft before reload with the environment's standard Nginx config test.
4. Reload only in the explicitly authorized activation/rollback session.
5. Verify `/v1/answers` resolves to production M26 on `127.0.0.1:8080`.
6. Verify production health reports build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd` and entrypoint `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`.
7. Stop/remove only the labeled M27 canary container or process.
8. Verify `ss -ltnp | grep :18080` returns no listener.
9. Verify no M27 canary/eval container remains.
10. Recompute both Nginx checksums and preserve the before/after values in the canary receipt.

## Telemetry identity prerequisite

Before admitting any candidate traffic, each telemetry record must persist route id, candidate id, candidate git SHA, immutable runtime identity when available, canary mode, request id, terminal kind, first-material latency, final latency, product-gate outcome, and stop-condition flags. `src/knowledge_engine/m27_canary_telemetry.py` is the Stage 27 schema/persistence hook. It writes only to an explicitly supplied file sink and has no production datastore selection or network side effect.

## Stage 27 dry-run proof

Stage 27 only read the existing config and checksums. It did not edit Nginx, reload Nginx, start a candidate, bind port 18080, or send canary traffic.
