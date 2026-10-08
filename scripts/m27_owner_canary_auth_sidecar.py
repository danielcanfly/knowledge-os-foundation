from __future__ import annotations

import argparse
import hmac
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_HEADER = "x-m27-owner-canary-auth"


def _parse_private_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in (chr(34), chr(39)):
            cleaned = cleaned[1:-1]
        data[key.strip()] = cleaned
    return data


def _load_first_private_value(path: Path) -> str:
    st = path.stat()
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise RuntimeError("OWNER_AUTH_ENV_TOO_PERMISSIVE")
    data = _parse_private_env(path)
    if not data:
        raise RuntimeError("OWNER_AUTH_VALUE_MISSING")
    return next(iter(data.values()))


class OwnerAuthHandler(BaseHTTPRequestHandler):
    server_version = "M27OwnerAuth/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/m27-owner-auth":
            self.send_response(404)
            self.end_headers()
            return
        candidate = self.headers.get(self.server.owner_header, "")  # type: ignore[attr-defined]
        if candidate and hmac.compare_digest(candidate, self.server.owner_value):  # type: ignore[attr-defined]
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(401)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        self.do_GET()

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="M27 owner-only canary auth sidecar")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--header", default=DEFAULT_HEADER)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    owner_value = _load_first_private_value(Path(args.env_file))
    httpd = ThreadingHTTPServer((args.host, args.port), OwnerAuthHandler)
    httpd.owner_value = owner_value  # type: ignore[attr-defined]
    httpd.owner_header = args.header.lower()  # type: ignore[attr-defined]
    print("m27-owner-auth-sidecar-ready", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
