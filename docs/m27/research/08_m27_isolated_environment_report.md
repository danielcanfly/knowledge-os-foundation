# M27 Isolated Environment Report

## Goal

Create a separate M27 runtime environment that does not touch current production.

## Created files

```text
docker-compose.m27-isolated.yml
.env.m27.example
```

Local private env used for smoke testing was intentionally not committed:

```text
.env.m27
```

`.gitignore` now excludes `.env.m27`.

## Isolated Docker image

Built successfully:

```text
knowledge-engine:m27-context-runtime-stage0c
```

Image id:

```text
sha256:9b068a0bfac1684aad59f029366ccd204ffc7fbe7c8c9f29c06bb3068bc983df
```

## Isolated container

Created and started separately from production:

```text
container: llm_wiki-m27-context-runtime-1
image: knowledge-engine:m27-context-runtime-stage0c
host port: 127.0.0.1:18080 -> 8080
```

## Isolation properties

The M27 compose file uses:

```text
separate container name
separate image tag
separate host port
separate Docker volumes
no restart policy
no nginx/Cloudflare route
no production container mutation
```

M27 uses command override to match the current production entrypoint without modifying the shared Dockerfile:

```text
uvicorn knowledge_engine.m26_console_api:app --host 0.0.0.0 --port 8080
```

## Startup smoke

The first startup attempt exposed an isolation env bug:

```text
sqlite3.OperationalError: unable to open database file
```

Root cause:

```text
M26_PUBLIC_QUOTA_DB pointed to a newly mounted path not writable by the container user.
```

Mitigation applied locally:

```text
M26_PUBLIC_QUOTA_DB=/var/lib/knowledge-engine/cache/m27-quota.sqlite3
```

After mitigation, the container starts and imports the Console/Public API stack.

## Health status

The isolated container currently returns:

```text
HTTP/1.1 503 Service Unavailable
SERVICE_NOT_READY
The public answer service is missing required staging configuration.
```

This is expected for a non-production isolated container without production/staging runtime config. It is not a production failure.

## Import smoke

The image imports the core production modules successfully under isolated env:

```text
IMPORT_OK knowledge_engine.m26_console_api
IMPORT_OK knowledge_engine.m26_public_api
IMPORT_OK knowledge_engine.m26_aq_semantic_contract
IMPORT_OK knowledge_engine.m26_pa7_arbitrary_query_runtime
```

## Production status

Production remained untouched and healthy:

```text
llm_wiki-knowledge-engine-1|knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z|healthy|127.0.0.1:8080->8080/tcp
```

## Remaining environment blocker

To make M27 isolated container return healthy and run behavioral equivalence tests, create a non-production/read-only M27 env that provides the same readiness inputs without production write authority.

Do not solve this by pointing M27 at production write-capable credentials.
