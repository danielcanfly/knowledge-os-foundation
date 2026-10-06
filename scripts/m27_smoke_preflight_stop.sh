#!/usr/bin/env bash
set -euo pipefail
NAME=m27-isolated-eval-05r
if ! docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  exit 0
fi
LABEL=$(docker inspect -f '{{ index .Config.Labels "com.daniel.m27.eval" }}' "$NAME" 2>/dev/null || true)
if [ "$LABEL" != "true" ]; then
  echo "refusing to remove unowned container $NAME" >&2
  exit 20
fi
docker rm -f "$NAME"
