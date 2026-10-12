"""R29: physically separate localhost/SQLite reversible action fixture only.

Never an external-provider dispatch adapter. No generic URL, DNS, scheme, or
third-party action endpoint accepted. Feature disabled unless explicitly injected.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import sqlite3
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

VERSION = "R29-ACT-LOCAL-FIXTURE-v1"


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


@dataclass(frozen=True)
class R29Action:
    idempotency_key: str
    effect_id: str
    tenant_id: str
    run_id: str
    actor_id: str
    source_revision: str
    mode: str = "normal"


class R29LocalFixtureAdapter:
    """A local-only test seam; host is a constant, never caller-controlled."""

    def __init__(self, *, port: int, token: str, enabled: bool = False):
        if (
            not enabled
            or type(port) is not int
            or not 1024 <= port <= 65535
            or not isinstance(token, str)
            or len(token) < 24
        ):
            raise ValueError("ACT_LOCAL_FEATURE_OFF_OR_INVALID_FIXTURE")
        self.port = port
        self.token = token

    def _call(self, verb: str, path: str, payload: dict | None = None) -> dict:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        body = canonical(payload) if payload is not None else None
        try:
            connection.request(
                verb,
                path,
                body=body,
                headers={
                    "X-R29-Fixture-Token": self.token,
                    "Content-Type": "application/json",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            raw = response.read(4096)
            if response.status != 200:
                raise OSError("ACT_LOCAL_FIXTURE_OBSERVER_UNAVAILABLE")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise OSError("ACT_LOCAL_INVALID_RECEIPT")
            return data
        finally:
            connection.close()

    def send_once(self, action: R29Action, claim_id: str, digest: str) -> dict:
        return self._call(
            "POST",
            "/fixture/apply",
            {
                "tenant": action.tenant_id,
                "run": action.run_id,
                "claim": claim_id,
                "intent": digest,
                "effect_id": action.effect_id,
                "key": action.idempotency_key,
                "source": action.source_revision,
                "mode": action.mode,
            },
        )

    def observe(self, action: R29Action, claim_id: str, digest: str) -> dict:
        from urllib.parse import urlencode

        data = self._call(
            "GET",
            "/fixture/observe?"
            + urlencode(
                {
                    "tenant": action.tenant_id,
                    "run": action.run_id,
                    "claim": claim_id,
                }
            ),
        )
        if (
            data.get("tenant") != action.tenant_id
            or data.get("run") != action.run_id
            or data.get("claim") != claim_id
            or data.get("intent") != digest
        ):
            raise OSError("ACT_LOCAL_OBSERVER_WRONG_SCOPE_OR_DIGEST")
        if data.get("effect") not in {"applied", "not_applied", "unknown"}:
            raise OSError("ACT_LOCAL_OBSERVER_UNCERTAIN")
        return data


class R29LocalActionVerifier:
    """Separate local fixture verifier key, no signed external IdP rights."""

    def __init__(self, verifier_id: str, key: bytes):
        if verifier_id in {"", "principalA", "fixture-observer"} or len(key) < 16:
            raise ValueError("INVALID_INDEPENDENT_LOCAL_VERIFIER")
        self.verifier_id = verifier_id
        self._key = key

    def verify(self, data: dict, *, action: R29Action, claim: str, intent: str) -> str:
        if (data.get("tenant"), data.get("run"), data.get("claim"), data.get("intent")) != (
            action.tenant_id,
            action.run_id,
            claim,
            intent,
        ):
            raise ValueError("AR05_LOCAL_ACTION_RECEIPT_SCOPE_FAILURE")
        if data.get("effect") not in {"applied", "not_applied"}:
            raise ValueError("AR05_LOCAL_ACTION_UNKNOWN")
        if data.get("observer") != "fixture-os-sqlite-observer" or data.get("posts") != 1:
            raise ValueError("AR05_LOCAL_ACTION_INDEPENDENT_RECEIPT_MISSING")
        return sha(data)

    def sign_local_terminal(self, message: bytes) -> str:
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()


def serve(db_path: Path, port: int, token: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect():
        db = sqlite3.connect(db_path, timeout=5)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("""CREATE TABLE IF NOT EXISTS posts (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
          run TEXT NOT NULL, claim TEXT NOT NULL, intent TEXT NOT NULL,
          effect_id TEXT NOT NULL, dedupe_key TEXT NOT NULL, mode TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS effects (
          tenant TEXT NOT NULL, run TEXT NOT NULL, dedupe_key TEXT NOT NULL,
          claim TEXT NOT NULL, intent TEXT NOT NULL, effect_id TEXT NOT NULL,
          PRIMARY KEY(tenant, run, dedupe_key))""")
        db.commit()
        return db

    with connect():
        pass

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def respond(self, status: int, obj: dict) -> None:
            raw = canonical(obj)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self.wfile.write(raw)

        def authorized(self) -> bool:
            return hmac.compare_digest(self.headers.get("X-R29-Fixture-Token", ""), token)

        def do_POST(self):
            if not self.authorized() or self.path != "/fixture/apply":
                return self.respond(403, {"error": "DENIED"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n < 2048:
                    raise ValueError("SIZE")
                payload = json.loads(self.rfile.read(n))
                fields = ("tenant", "run", "claim", "intent", "effect_id", "key", "source", "mode")
                if any(not isinstance(payload.get(x), str) or not payload[x] for x in fields):
                    raise ValueError("FIELDS")
                if payload["mode"] not in {"normal", "lost_ack", "observer_unknown"}:
                    raise ValueError("MODE")
                if payload["source"] != "rev1":
                    raise ValueError("REVISION")
                with connect() as db:
                    db.execute(
                        "INSERT INTO posts(tenant,run,claim,intent,effect_id,"
                        "dedupe_key,mode)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (
                            payload["tenant"],
                            payload["run"],
                            payload["claim"],
                            payload["intent"],
                            payload["effect_id"],
                            payload["key"],
                            payload["mode"],
                        ),
                    )
                    db.execute(
                        """INSERT OR IGNORE INTO effects
                        VALUES (?,?,?,?,?,?)""",
                        (
                            payload["tenant"],
                            payload["run"],
                            payload["key"],
                            payload["claim"],
                            payload["intent"],
                            payload["effect_id"],
                        ),
                    )
                if payload["mode"] == "lost_ack":
                    self.close_connection = True
                    self.connection.shutdown(2)
                    self.connection.close()
                    return
                self.respond(200, {"accepted": True})
            except (ValueError, KeyError, sqlite3.DatabaseError, OSError):
                self.respond(400, {"error": "INVALID_FIXTURE_INPUT"})

        def do_GET(self):
            if not self.authorized():
                return self.respond(403, {"error": "DENIED"})
            path = urlsplit(self.path)
            if path.path not in ("/fixture/observe", "/fixture/ready"):
                return self.respond(404, {"error": "NOT_FOUND"})
            if path.path == "/fixture/ready":
                return self.respond(200, {"ready": True, "scope": VERSION})
            query = parse_qs(path.query)
            if any(len(query.get(x, [])) != 1 for x in ("tenant", "run", "claim")):
                return self.respond(400, {"error": "SCOPE"})
            tenant, run, claim = (query[x][0] for x in ("tenant", "run", "claim"))
            with connect() as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT * FROM posts WHERE tenant=? AND run=? AND claim=?", (tenant, run, claim)
                ).fetchall()
                effect = db.execute(
                    "SELECT * FROM effects WHERE tenant=? AND run=? AND claim=?",
                    (tenant, run, claim),
                ).fetchone()
            if rows and rows[0]["mode"] == "observer_unknown":
                return self.respond(503, {"error": "OBSERVATION_UNAVAILABLE"})
            self.respond(
                200,
                {
                    "tenant": tenant,
                    "run": run,
                    "claim": claim,
                    "intent": rows[0]["intent"] if rows else "",
                    "effect": "applied" if effect else ("not_applied" if not rows else "unknown"),
                    "effect_id": effect["effect_id"] if effect else None,
                    "posts": len(rows),
                    "observer": "fixture-os-sqlite-observer",
                    "effects": int(effect is not None),
                },
            )

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.05)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--token", required=True)
    args = p.parse_args()
    if os.environ.get("R29_SYNTHETIC_LOCAL_ONLY") != "1":
        raise SystemExit("LOCAL_FIXTURE_ONLY")
    serve(args.db, args.port, args.token)
