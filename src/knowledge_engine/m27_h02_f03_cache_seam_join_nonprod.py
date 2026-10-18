"""H02 scoped first-party A05 source Consumer + accepted F03 cache *plan* seam.

New nonprod OS/TCP route, ADD-only: never an answer cache, model, Product IdP,
independent semantic verifier or signed release. Actual A05 bytes, owned OS
revocation fence, local citation byte verifier and H02 ACK/terminal apply.
BYPASS/AUTO/REFRESH are nonauthorizing plans only. Zero answer-cache IO.
No legacy /v1/answers, original H02 or Q34 files modified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
from http import HTTPStatus
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import types
from typing import Any

# Direct script mode is isolated from the unrelated M26 application bootstrap.
# Preserve the exact first-party sources rather than copying their algorithms.
if not __package__:
    if "knowledge_engine" not in sys.modules:
        pkg = types.ModuleType("knowledge_engine")
        pkg.__path__ = [str(Path(__file__).resolve().parent)]
        sys.modules["knowledge_engine"] = pkg
import m27_h02_native_nonprod_consumer as h02
from knowledge_engine import m27_f03_product_cache_seam_protocol as f03seam

ROUTE = "/nonprod/h02-f03/source-candidate"
ABI = "m27.h02-f03.local-source-cache-plan/nonprod.v1"
MAX_BODY = 3072
TTL_SECONDS = 120


def _sha(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8")).hexdigest()


def _z(instant: dt.datetime) -> str:
    return instant.astimezone(dt.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


class H02SourceAuthority:
    """Port over a *real H02 local source* result, not simulated Product IdP.

    resolve() actually executes H02.start, including its real read and OS byte
    verifier; recheck() reads the same first-party corpus/rights again. The
    forced \"authenticated\" field is only the existing cache ABI's OS-local
    nonprod slot; never a genuine user or external principal attestation.
    """

    def __init__(self, consumer: "JoinedConsumer"):
        self.consumer = consumer
        self.response: dict | None = None
        self.session: str | None = None
        self.initial_source: dict | None = None
        self.lease: dict | None = None

    def _fresh(self, entry: dict) -> dict:
        self.consumer._current(entry)
        source = self.consumer._source(entry["question"])
        h02.guard(source["rights_epoch"] == entry["epoch"] and
                  source["revocation_sha256"] == entry["rights_sha"] and
                  source["release_sha256"] == entry["release_sha"] and
                  source["source_manifest_sha256"] == h02.f03.A05_SOURCE_PIN and
                  source["source_revision"] == h02.f03.A05_REVISION and
                  source["sources"] == entry["citations"],
                  "H02_REAL_SOURCE_RIGHTS_CHANGED")
        return source

    def resolve(self, client_request: dict) -> dict:
        # Called only after F03 validates client fields and reserves request ID.
        # H02 owns the only actual identity, source retrieval and local lease.
        response = self.consumer.start(client_request["question"])
        self.response = response
        self.session = response["session_id"]
        entry = self.consumer.entries[self.session]
        source = self._fresh(entry)
        self.initial_source = source
        issued = entry["local_issued_at"]
        ctx = {
            "identity": {
                "tenant_id": "owner-internal",
                "principal_id": self.consumer.principal,
                "auth_context_sha256": _sha({
                    "scope": "OS-LOCAL-UNSIGNED-NOT-PRODUCT-IDP",
                    "session_nonce": self.session,
                    "task_sha256": entry["task_sha"],
                    "tenant": "owner-internal",
                    "principal": self.consumer.principal,
                }),
                "authenticated": True,  # OS-local capability ONLY, not real user IdP
            },
            "question": {
                "text": client_request["question"],
                "language": "en",
                "task_kind": "QA",
                "intent_id": "h02-a05-verified-local-clause-source",
                "obligations": [
                    "Responsible for deterministic enforcement.",
                    "PolicyEngine decides.",
                ],
                "negated": False,
                "numeric_literals": [],
                "temporal_scope": "STATIC",
                "answer_type": "FACT",
            },
            "source": {
                **source["source"],
                # Retriever may return multiple passages of the same actual
                # document: semantic cache scope requires distinct identifiers.
                "source_ids": list(dict.fromkeys(source["source"]["source_ids"])),
            },
            "policy": {
                "policy_version": "h02/a05/owner-local-read-only",
                "policy_sha256": _sha({
                    "task_sha256": entry["task_sha"],
                    "source_revision": source["source_revision"],
                    "release_sha256": entry["release_sha"],
                    "rights_epoch": entry["epoch"],
                    "rights_sha256": entry["rights_sha"],
                }),
                "verifier_version": "OS-BYTE-VERIFY-ONLY-NOT-SEMANTIC",
                "embedding_version": "NO-EMBEDDINGS-NOT-RUN",
                "admission_version": "SOURCE-CANDIDATE-NOT-PRODUCT",
                "revocation_epoch": source["rights_epoch"],
            },
            "cache_window": {
                "requested_at": _z(issued),
                "ttl_seconds": TTL_SECONDS,
            },
        }
        lease = {
            "tenant_id": ctx["identity"]["tenant_id"],
            "principal_id": ctx["identity"]["principal_id"],
            "auth_context_sha256": ctx["identity"]["auth_context_sha256"],
            "source_manifest_sha256": ctx["source"]["source_manifest_sha256"],
            "rights_sha256": ctx["source"]["rights_sha256"],
            "revocation_epoch": ctx["policy"]["revocation_epoch"],
            "expires_at": _z(issued + dt.timedelta(seconds=TTL_SECONDS)),
            "source_current": True,
            "rights_current": True,
            "acl_current": True,
        }
        self.lease = lease
        return {"context": ctx, "lease": lease}

    def recheck(self, request: dict, identity: dict, source: dict) -> dict:
        h02.guard(self.session is not None and self.initial_source is not None and
                  self.lease is not None, "H02_SOURCE_CONTEXT_MISSING")
        entry = self.consumer._entry(self.session)
        h02.guard(entry["state"] == "AWAITING_ACK",
                  "SOURCE_DELIVERY_CANCELLED")
        next_source = self._fresh(entry)
        # The same original release/ACL/rights/source is independently sampled
        # a second time. A separate remote IdP is NOT being asserted.
        h02.guard(next_source["source"] == self.initial_source["source"] and
                  next_source["rights_epoch"] == self.initial_source["rights_epoch"] and
                  next_source["release_sha256"] == self.initial_source["release_sha256"] and
                  next_source["source_manifest_sha256"] ==
                  self.initial_source["source_manifest_sha256"],
                  "H02_SOURCE_RACE_OR_ACL_CHANGED")
        return dict(self.lease)


class JoinedConsumer(h02.Consumer):
    """A single scoped H02 owner, explicitly serialized per local OS process."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.join_lock = threading.RLock()
        self.authority = H02SourceAuthority(self)
        self.seam = f03seam.NativeProductCacheSeam(
            authority=self.authority, feature_enabled=False)
        # Optional per-instance test-only fault injection; not a client field.
        self.before_delivery = None

    def delivery_recheck(self, sid: str) -> None:
        with self.join_lock:
            entry = self._entry(sid)
            h02.guard(entry["state"] == "AWAITING_ACK",
                      "SOURCE_DELIVERY_CANCELLED")
            self._current(entry)
            # No Product user token, no cache read/write and no model answer.
            h02.guard(self.seam._store_factory is None and
                      self.seam._verifier is None,
                      "UNQUALIFIED_CACHE_OR_VERIFIER_ADAPTER")

    def start_with_mode(self, client_body: Any) -> dict:
        with self.join_lock:
            self.authority.response = None
            self.authority.session = None
            self.authority.initial_source = None
            self.authority.lease = None
            try:
                plan = self.seam.consume(client_body)
                response = self.authority.response
                h02.guard(type(response) is dict and
                          response["status"] == "LOCAL_FIRSTPARTY_SOURCE_CANDIDATE",
                          "MISSING_H02_FIRSTPARTY_SOURCE_ROUTE")
                h02.guard(plan["product_cache_enabled"] is False and
                          plan["cache_io_performed"] is False and
                          plan["answer_cache_hit_admitted"] is False and
                          plan["answer_cache_write_admitted"] is False and
                          plan["answer_cache_lookup_invocations"] == 0 and
                          plan["answer_cache_write_invocations"] == 0,
                          "F03_CACHE_FEATURE_MUST_REMAIN_OFF")
                if self.before_delivery:
                    self.before_delivery()
                self.delivery_recheck(response["session_id"])
                return {**response, "joined_abi": ABI, "cache_plan": plan,
                        "local_client_auth": "OWNER_OS_PRIVATE_TRANSPORT_TOKEN_NOT_IDP",
                        "product_authenticated": False,
                        "semantic_verifier_qualified": False,
                        "answer_cache_hit": False, "answer_cache_write": False}
            except Exception:
                sid = self.authority.session
                if sid in self.entries and self.entries[sid]["state"] == "AWAITING_ACK":
                    self.cancel(sid)
                raise


class JoinedHandler(h02.Handler):
    """New joined HTTP endpoint; original H02 paths remain existing behavior."""
    consumer: JoinedConsumer
    transport_token: str = ""

    def _deny(self, code: int, error: str):
        return self.reply({"error": error, "scope": ABI,
                           "product_authenticated": False,
                           "cache": "OFF"}, code)

    def do_POST(self):
        if self.path != ROUTE:
            return super().do_POST()
        if (self.client_address[0] != "127.0.0.1" or
            self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or
            not hmac.compare_digest(self.headers.get("X-H02-F03-Token", ""),
                                    self.transport_token)):
            return self._deny(HTTPStatus.FORBIDDEN, "OS_LOCAL_TRANSPORT_DENIED")
        if self.headers.get("Content-Type", "").lower() != "application/json":
            return self._deny(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON_ONLY")
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
            return self._deny(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "BAD_REQUEST_BODY_LENGTH")
        try:
            body = json.loads(self.rfile.read(int(length)))
            result = self.consumer.start_with_mode(body)
            # Same lock order as JoinedConsumer.start_with_mode: hold source
            # session state stable from last local rights check to socket write.
            # This does NOT claim remote atomic revoke or client-read delivery.
            with self.consumer.join_lock, self.consumer.lock:
                self.consumer.delivery_recheck(result["session_id"])
                return self.reply(result)
        except f03seam.NativeCacheProtocolError as exc:
            return self._deny(exc.status, exc.code)
        except h02.Denied as exc:
            # Bounded local denial codes; never return a source or cached answer.
            return self._deny(HTTPStatus.FORBIDDEN, str(exc))
        except (TypeError, ValueError, UnicodeError, OSError):
            return self._deny(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST")
        except Exception:
            return self._deny(HTTPStatus.SERVICE_UNAVAILABLE,
                              "UNEXPECTED_FAILURE_CLOSED")


def serve(*, repo: Path, fence: Path, journal: Path, port: int = 0,
          source_root: Path | None = None, isolated_test_copy: bool = False,
          ready_file: Path | None = None):
    if port != 0:
        raise ValueError("NONPROD_EPHEMERAL_LOOPBACK_ONLY")
    consumer = JoinedConsumer(repo=repo, fence=fence, journal=journal,
                              source_root=source_root,
                              isolated_test_copy=isolated_test_copy)
    class AppHandler(JoinedHandler):
        pass
    AppHandler.consumer = consumer
    AppHandler.transport_token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), AppHandler)
    if ready_file is not None:
        # OS-private capability handoff; no network publication, not IdP.
        payload = json.dumps({"port": server.server_port, "pid": os.getpid(),
                              "status": h02.PRODUCT,
                              "transport_token": AppHandler.transport_token,
                              "joined_abi": ABI})
        fd = os.open(ready_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, payload.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--fence", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file")
    parser.add_argument("--source-root")
    parser.add_argument("--isolated-test-copy", action="store_true")
    args = parser.parse_args()
    serve(repo=Path(args.repo), fence=Path(args.fence), journal=Path(args.journal),
          port=args.port,
          ready_file=Path(args.ready_file) if args.ready_file else None,
          source_root=Path(args.source_root) if args.source_root else None,
          isolated_test_copy=args.isolated_test_copy)


if __name__ == "__main__":
    main()
