"""B1-05 isolated loopback-only cache-mode UI/HTTP adapter, NOT a Product endpoint.

No external IdP, real source rights, qualified verifier, generated answer,
semantic HIT or production cache writes. Public caller controls choice only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from threading import Lock
from typing import Any

from .m27_b0_cache_contracts import (
    CacheContractError, SCHEMA_VERSION, build_response_contract,
    describe_cache_operations, parse_internal_request, parse_public_cache_choice,
)

UI_SCHEMA = "m27.cache04-choice-demo/v1"
DEMO_PATH = "/__cache04/demo/request"
UI_FILE = Path(__file__).resolve().parents[2] / "docs/m27/b1_cache04_demo/index.html"
SHA = hashlib.sha256(b"m27-cache04-publicly-unqualified-fixture").hexdigest()
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,96}\Z")


class DemoError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


class FixtureCacheIOSpy:
    """Bounded in-memory test-only I/O. Never claims an admitted Product HIT."""
    def __init__(self, max_entries: int = 8):
        if not 1 <= max_entries <= 8:
            raise ValueError("FIXTURE_STORE_BOUND")
        self.max_entries = max_entries
        self.entries: dict[str, tuple[str, str]] = {}
        self.reads = 0
        self.writes = 0
        self.lock = Lock()

    def lookup_fixture(self, key: str) -> bool:
        with self.lock:
            self.reads += 1
            return key in self.entries

    def cas_fixture(self, key: str, value: str, prior: str | None) -> bool:
        with self.lock:
            current = self.entries.get(key)
            if current is not None and current[0] != prior:
                return False
            if current is None and prior is not None:
                return False
            if current is None and len(self.entries) >= self.max_entries:
                return False
            revision = hashlib.sha256(value.encode()).hexdigest()
            self.entries[key] = revision, value
            self.writes += 1
            return True


def internal_demo_envelope(mode: str, question: str, request_id: str) -> dict[str, Any]:
    """Fixture identity is always server-generated; not a real authenticated principal."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    result = {
        "schema_version": SCHEMA_VERSION, "request_id": request_id, "cache_mode": mode,
        "identity": {"tenant_id": "fixture-tenant", "principal_id": "fixture-principal",
                     "auth_context_sha256": SHA, "authenticated": True},
        "question": {"text": question, "language": "en", "task_kind": "QA",
                     "intent_id": "cache04-toggle-demo", "obligations": ["source-bound"],
                     "negated": False, "numeric_literals": [], "temporal_scope": "STATIC",
                     "answer_type": "EXPLANATION"},
        "source": {"corpus_id": "fixture-only", "corpus_revision": "fixture-r1",
                   "corpus_sha256": SHA, "source_manifest_sha256": SHA,
                   "acl_sha256": SHA, "rights_sha256": SHA, "source_ids": ["fixture-source"]},
        "policy": {"policy_version": "fixture-policy-v1", "policy_sha256": SHA,
                   "verifier_version": "unqualified", "embedding_version": "unqualified",
                   "admission_version": "unqualified", "revocation_epoch": 0},
        "cache_window": {"requested_at": timestamp, "ttl_seconds": 30},
    }
    return parse_internal_request(result)


def parse_ui_request(body: Any) -> tuple[str, str, str]:
    if type(body) is not dict or set(body) != {
        "schema_version", "request_id", "cache_mode", "question"
    }:
        raise DemoError("UNKNOWN_OR_MISSING_UI_FIELD")
    if body["schema_version"] != UI_SCHEMA:
        raise DemoError("UI_SCHEMA_MISMATCH")
    reqid = body["request_id"]
    if type(reqid) is not str or REQUEST_ID.fullmatch(reqid) is None:
        raise DemoError("BAD_REQUEST_ID")
    question = body["question"]
    if (type(question) is not str or not 1 <= len(question) <= 2000 or
            question.strip() != question or any(ord(ch) < 32 for ch in question) or
            "<" in question or ">" in question or "javascript:" in question.lower()):
        raise DemoError("UNSAFE_OR_INVALID_QUESTION")
    try:
        mode = parse_public_cache_choice({"cache_mode": body["cache_mode"]})
    except (CacheContractError, TypeError) as exc:
        raise DemoError("INVALID_CACHE_MODE") from exc
    return mode, question, reqid


def run_adapter(envelope: dict, *, feature_enabled: bool = False,
                fixture_io: FixtureCacheIOSpy | None = None,
                fixture_authority: bool = False,
                fixture_verified_final: dict | None = None) -> dict:
    """Test-only authority switch is not exposed by HTTP, and never admits a HIT."""
    policy = describe_cache_operations(envelope, feature_enabled=feature_enabled)
    status = policy.decision
    before_reads = fixture_io.reads if fixture_io else 0
    before_writes = fixture_io.writes if fixture_io else 0
    if fixture_authority and feature_enabled and fixture_io is not None:
        key = envelope["identity"]["tenant_id"] + "|" + envelope["identity"]["principal_id"]
        if status == "LOOKUP_REQUIRED":
            if fixture_io.lookup_fixture(key):
                status = "PROVER_REQUIRED"  # Candidate, NOT HIT.
        elif status == "REGENERATE_NO_LOOKUP" and fixture_verified_final is not None:
            proof = fixture_verified_final
            expected_keys = {"qualification_class", "final_verified",
                             "source_current", "rights_current", "answer", "prior"}
            if (type(proof) is dict and set(proof) == expected_keys and
                proof["qualification_class"] == "FIXTURE_ONLY" and
                proof["final_verified"] is True and proof["source_current"] is True and
                proof["rights_current"] is True and type(proof["answer"]) is str and
                len(proof["answer"]) > 0 and
                (proof["prior"] is None or type(proof["prior"]) is str)):
                if fixture_io.cas_fixture(key, proof["answer"], proof["prior"]):
                    status = "VERIFIED_FIXTURE_ONLY"
                else:
                    status = "WRITE_NOT_ADMITTED"
            else:
                status = "WRITE_NOT_ADMITTED"
    receipt = build_response_contract(envelope, status=status)
    receipt.update({
        "ui_schema_version": UI_SCHEMA, "scope": "LOCAL_FIXTURE_ONLY",
        "product_authenticated": False, "answer_published": False,
        "answer_cache_hit_admitted": False,
        "demo_fixture_io_reads": (fixture_io.reads - before_reads) if fixture_io else 0,
        "demo_fixture_io_writes": (fixture_io.writes - before_writes) if fixture_io else 0,
    })
    return receipt


class Cache04Demo(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 *, feature_enabled: bool = False):
        if host != "127.0.0.1" or type(feature_enabled) is not bool:
            raise ValueError("LOCAL_ONLY_AND_EXPLICIT_BOOLEAN")
        self.feature_enabled = feature_enabled
        self.session = secrets.token_urlsafe(32)
        self.seen: set[str] = set()
        self.seen_lock = Lock()
        super().__init__((host, port), Cache04Handler)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


class Cache04Handler(BaseHTTPRequestHandler):
    server: Cache04Demo

    def log_message(self, *_args: Any) -> None:
        return  # no question/cookie/key in access log

    def _headers(self, status: int, ctype: str, size: int) -> None:
        self.send_response(status)
        for k, value in (
            ("Content-Type", ctype), ("Content-Length", str(size)),
            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Frame-Options", "DENY"),
        ):
            self.send_header(k, value)

    def _reply(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        return self.client_address[0] == "127.0.0.1" and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self) -> None:
        if not self._host_ok():
            self._reply(403, {"error": "NON_LOOPBACK_DENIED"})
            return
        if self.path.split("?")[0] != "/__cache04/demo/":
            self._reply(404, {"error": "NOT_FOUND"})
            return
        nonce = secrets.token_urlsafe(20)
        html = UI_FILE.read_text(encoding="utf-8").replace("__CSP_NONCE__", nonce)
        body = html.encode("utf-8")
        self._headers(200, "text/html; charset=utf-8", len(body))
        self.send_header("Set-Cookie", f"demo_session={self.server.session}; HttpOnly; SameSite=Strict; Path=/__cache04/demo/")
        self.send_header("Content-Security-Policy",
                         f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _session_ok(self) -> bool:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            value = cookie["demo_session"].value if "demo_session" in cookie else ""
        except Exception:
            return False
        return hmac.compare_digest(value, self.server.session)

    def do_POST(self) -> None:
        if not self._host_ok():
            self._reply(403, {"error": "NON_LOOPBACK_DENIED"})
            return
        if self.path != DEMO_PATH:
            self._reply(404, {"error": "NOT_FOUND"})
            return
        if (not self._session_ok() or
            self.headers.get("Origin") != self.server.origin or
            self.headers.get("X-Cache-Demo-Request") != "1"):
            self._reply(403, {"error": "DEMO_AUTH_OR_ORIGIN_DENIED"})
            return
        if self.headers.get("X-Cache-Demo-Cancelled") == "1":
            self._reply(409, {"error": "CANCELLED_BEFORE_EXECUTION"})
            return
        if self.headers.get("Content-Type", "").lower() != "application/json":
            self._reply(415, {"error": "JSON_ONLY"})
            return
        raw_len = self.headers.get("Content-Length", "")
        if not raw_len.isdecimal() or not 0 < int(raw_len) <= 4096:
            self._reply(413, {"error": "INVALID_BODY_LENGTH"})
            return
        try:
            obj = json.loads(self.rfile.read(int(raw_len)))
            mode, question, reqid = parse_ui_request(obj)
            with self.server.seen_lock:
                if reqid in self.server.seen:
                    raise DemoError("REPLAY_DENIED", 409)
                if len(self.server.seen) >= 256:
                    raise DemoError("REQUEST_CAP_REACHED", 429)
                self.server.seen.add(reqid)
            envelope = internal_demo_envelope(mode, question, reqid)
            receipt = run_adapter(envelope, feature_enabled=self.server.feature_enabled)
        except (ValueError, UnicodeError, json.JSONDecodeError, CacheContractError) as exc:
            code = exc.code if isinstance(exc, DemoError) else "MALFORMED_REQUEST"
            status = exc.status if isinstance(exc, DemoError) else 400
            self._reply(status, {"error": code})
            return
        self._reply(HTTPStatus.OK, receipt)


def serve_local_demo() -> None:
    server = Cache04Demo()
    print("CACHE04_LOCAL_FIXTURE_ONLY_URL=" + server.origin + "/__cache04/demo/", flush=True)
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()


if __name__ == "__main__":
    serve_local_demo()
