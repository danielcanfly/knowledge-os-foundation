#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:-/home/ubuntu/LLM_Wiki-m27-smoke-preflight-repair}
NAME=m27-isolated-eval-05r
IMAGE=knowledge-engine:m27-smoke-preflight-repair
PORT=18080
cd "$ROOT"
HEAD=$(git rev-parse HEAD)
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${PORT}$"; then
  echo "port ${PORT} already occupied" >&2
  exit 10
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  LABEL=$(docker inspect -f '{{ index .Config.Labels "com.daniel.m27.eval" }}' "$NAME" 2>/dev/null || true)
  if [ "$LABEL" != "true" ]; then
    echo "existing container name is not owned eval container" >&2
    exit 11
  fi
  docker rm -f "$NAME" >/dev/null
fi
docker build --provenance=false -t "$IMAGE" . >/tmp/m27-smoke-preflight-build.log
IMAGE_ID=$(docker image inspect -f '{{.Id}}' "$IMAGE")
docker run -d --name "$NAME" \
  --label com.daniel.m27.eval=true \
  --label com.daniel.m27.session=05R \
  --memory=256m --memory-swap=768m \
  -e M27_BUILD_SHA="$HEAD" \
  -e M27_IMAGE_DIGEST="$IMAGE_ID" \
  -p 127.0.0.1:${PORT}:8080 \
  "$IMAGE" \
  uvicorn knowledge_engine.m27_isolated_http:app --host 0.0.0.0 --port 8080 >/tmp/m27-smoke-preflight-container-id
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:${PORT}/v1/health >/tmp/m27-smoke-preflight-health.json; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:${PORT}/v1/health
