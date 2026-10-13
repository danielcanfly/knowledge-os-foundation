"""N31 dedicated local-only ASGI launch; never runs the default M26 App."""
from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path

import uvicorn


def _lock_connects() -> None:
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    log = Path(os.environ["N31_CONNECT_LOG"])

    def permitted(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            allowed = isinstance(address, tuple) and address[0] == "127.0.0.1"
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "kind": "loopback_connect" if allowed else "nonloopback_denied",
                    "host": str(address[0]) if isinstance(address, tuple) else "unknown",
                }) + "\n")
            if not allowed:
                raise OSError("N31_NO_EXTERNAL_CONNECTIONS")
        return True

    def connect(self, address):
        permitted(self, address)
        return original(self, address)

    def connect_ex(self, address):
        permitted(self, address)
        return original_ex(self, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", required=True, type=int)
    args = p.parse_args()
    if (args.host != "127.0.0.1" or not 1024 <= args.port <= 65535
            or os.environ.get("APP_ENV") != "test"
            or os.environ.get("N31_LOCAL_ONLY") != "1"):
        p.error("N31_NONLOOPBACK_OR_FEATURE_FLAG_DENIED")
    _lock_connects()
    uvicorn.run("knowledge_engine.m27_n31_nonprod_app:app", host="127.0.0.1",
                port=args.port, lifespan="off", access_log=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
