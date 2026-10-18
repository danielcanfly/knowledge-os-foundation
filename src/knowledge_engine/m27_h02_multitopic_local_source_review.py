"""M27 bounded multiple-topic Owner A05 source review, Nonprod only.

This does NOT generate answers, access a model, impersonate Product IdP, or
reimplement the previously denied Product/Q34 generated-first-text route.
Each claim is an exact, source-supported text excerpt verified by an OS subprocess.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time

try:
    from . import m27_h02_native_nonprod_consumer as h02
    from . import m27_task_contracts_v1 as tc
except ImportError:
    import m27_h02_native_nonprod_consumer as h02
    import m27_task_contracts_v1 as tc

# Specific, grounded Owner-firstparty source topics. Deliberately not a general
# semantic Q&A admission gate. Unsupported/negative/numeric topics fail closed.
TOPIC_OBLIGATIONS = {
    "PolicyEngine": "PolicyEngine decides.",
    "Context Planner": "Context Planner",
    "Context Compiler": "Context Compiler",
    "Workspace Memory": "Workspace",
    "Compute Policy": "Compute Policy",
}
ABI = "m27.h02.local-multitopic-source-review/nonprod.v1"
# Bounded Owner-local resources. Not final Product user quotas.
MAX_PENDING_SOURCE_REVIEWS = 8
MAX_REPLAY_TOMBSTONES = 128
SESSION_LEASE_SECONDS = 120


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_line(excerpt: str, obligation: str) -> str:
    """An exact 256-character-or-shorter source line, never a model paraphrase."""
    for line in excerpt.splitlines():
        candidate = line.strip()
        if obligation.casefold() in candidate.casefold() and 0 < len(candidate) <= 256:
            return candidate
    raise h02.Denied("NO_EXACT_TOPICAL_SOURCE_LINE")


class SourceReview:
    def __init__(self, *, repo: Path, fence: Path, journal: Path,
                 source_root: Path | None = None,
                 isolated_test_copy: bool = False):
        self.inner = h02.Consumer(
            repo=repo, fence=fence, journal=journal,
            source_root=source_root, isolated_test_copy=isolated_test_copy
        )
        self.principal = self.inner.principal
        self.entries: dict[str, dict] = {}
        self.lock = threading.RLock()

    @staticmethod
    def _drop_sensitive(entry: dict) -> None:
        # Preserve only failclosed replay state; erase source content, nonce,
        # challenges and rights-bearing context after terminal or expiry.
        for key in ("topic", "obligation", "context", "issued_at",
                    "release_sha", "revocation_sha", "epoch",
                    "sources", "excerpts", "claims", "acked"):
            entry.pop(key, None)

    def _prune_tombstones(self) -> None:
        terminal_ids = [sid for sid, entry in self.entries.items()
                        if entry["state"] != "AWAITING_ACK"]
        for sid in terminal_ids[:-MAX_REPLAY_TOMBSTONES]:
            del self.entries[sid]

    def _expire_entry(self, sid: str, entry: dict) -> None:
        entry["state"] = "EXPIRED_NO_REPLAY"
        self._drop_sensitive(entry)
        self.inner.journal.record({
            "event": "terminal", "sid": sid, "status": "EXPIRED_NO_REPLAY",
            "when_ns": time.monotonic_ns(),
        })

    def _expire_pending(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        for sid, entry in list(self.entries.items()):
            if entry["state"] == "AWAITING_ACK" and (
                    now - entry["issued_at"]).total_seconds() >= SESSION_LEASE_SECONDS:
                self._expire_entry(sid, entry)
        self._prune_tombstones()

    def _retrieve(self, topic: str, obligation: str) -> dict:
        result = self.inner.reader.source_retrieval(
            topic, tenant="owner-internal", principal=self.principal,
            obligations=[obligation], ttl_seconds=120,
        )
        h02.guard(
            result.get("decision") == "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",
            result.get("decision", "SOURCE_READ_DENIED"),
        )
        h02.guard(
            result["candidate_only"] is True
            and result["product_admitted"] is False
            and result["answer_cache_enabled"] is False
            and result["verified_final"] is False,
            "UNQUALIFIED_SOURCE_STATUS",
        )
        return result

    def _current(self, entry: dict) -> None:
        data = self._retrieve(entry["topic"], entry["obligation"])
        h02.guard(
            data["release_sha256"] == entry["release_sha"]
            and data["revocation_sha256"] == entry["revocation_sha"]
            and data["rights_epoch"] == entry["epoch"]
            and data["sources"] == entry["sources"]
            and data["candidate_excerpts"] == entry["excerpts"],
            "SOURCE_CHANGED_OR_REVOKED",
        )
        self.inner._delivery_guard(
            data, context=entry["context"], issued_at=entry["issued_at"],
            epoch_floor=entry["epoch"],
        )

    def start(self, topic: str, *, tenant: str = "owner-internal",
              principal: str | None = None, issuer: str | None = None) -> dict:
        with self.lock:
            h02.guard(
                issuer is None and tenant == "owner-internal"
                and (principal is None or principal == self.principal),
                "REMOTE_IDP_NOT_ADMITTED",
            )
            h02.guard(type(topic) is str and topic in TOPIC_OBLIGATIONS,
                      "TOPIC_NOT_IN_BOUNDED_FIRSTPARTY_SCOPE")
            self._expire_pending()
            h02.guard(
                sum(entry["state"] == "AWAITING_ACK"
                    for entry in self.entries.values()) < MAX_PENDING_SOURCE_REVIEWS,
                "MAX_ACTIVE_SOURCE_REVIEWS",
            )
            obligation = TOPIC_OBLIGATIONS[topic]
            data = self._retrieve(topic, obligation)
            task = h02.local_task(topic, self.principal)
            task["task_id"] = "h02-a05-multitopic-source-review"
            task["constraints"] = [
                "Only exact topical firstparty source lines",
                "No model-generated answer and no Product rights assertion",
                "Every source line verified by independent OS process",
                "Require an independent Client ACK before local terminal",
                "No action, cache, finance, provider or fallback",
            ]
            task["definition_of_done"]["predicate_refs"] = [
                "source_bytes", "local_epoch", "separate_os_verifier",
                "all_selected_source_lines_acked",
            ]
            task["output_specs"][0]["expected_uri_scope"] = "nonprod/h02/a05-topical-source-review"
            task["metadata"] = {
                "h02:a05_source_pin": h02.f03.A05_SOURCE_PIN,
                "h02:review_only": True,
            }
            task = tc.task_contract(task)
            sid = secrets.token_hex(24)
            issued_at = dt.datetime.now(dt.timezone.utc)
            context = {
                "client_id": "h02-os-local-multitopic-review",
                "session_nonce": sid, "tenant": tenant,
                "principal": self.principal, "channel": "owner-os-local-nonprod",
            }
            self.inner._delivery_guard(
                data, context=context, issued_at=issued_at,
                epoch_floor=data["rights_epoch"],
            )
            claims = []
            seen = set()
            for cite, excerpt in zip(data["sources"], data["candidate_excerpts"]):
                if obligation.casefold() not in excerpt.casefold():
                    continue
                text = _source_line(excerpt, obligation)
                identity = (cite["document_sha256"], cite["excerpt_sha256"], text)
                if identity in seen:
                    continue
                proof = self.inner._verify(text, cite)
                claims.append({
                    "claim_id": "source-review-" + str(len(claims) + 1),
                    "kind": "exact_source_candidate_not_answer",
                    "text": text, "citation": cite,
                    "text_sha256": _sha_text(text),
                    "proof_sha256": h02.digest(json.dumps(proof, sort_keys=True).encode()),
                    "challenge": secrets.token_hex(24),
                    "model_generated": False,
                })
                seen.add(identity)
                if len(claims) >= 2:
                    break
            h02.guard(1 <= len(claims) <= 2, "NO_EXACT_SUPPORTED_SOURCE_CLAIM")
            entry = {
                "topic": topic, "obligation": obligation,
                "context": context, "issued_at": issued_at,
                "release_sha": data["release_sha256"],
                "revocation_sha": data["revocation_sha256"],
                "epoch": data["rights_epoch"],
                "sources": data["sources"],
                "excerpts": data["candidate_excerpts"],
                "claims": claims, "acked": set(),
                "task_sha": tc.sha256(task), "state": "AWAITING_ACK",
            }
            self._current(entry)
            self.entries[sid] = entry
            self.inner.journal.record({
                "event": "multitopic_source_review_sent",
                "sid": sid, "topic": topic,
                "task_sha256": entry["task_sha"],
                "claim_count": len(claims),
                "model_generated": False, "when_ns": time.monotonic_ns(),
            })
            return {
                **h02.fail("LOCAL_MULTITOPIC_SOURCE_REVIEW_AWAITING_ACK"),
                "abi": ABI, "session_id": sid,
                "topic": topic, "task_sha256": entry["task_sha"],
                "claims": claims, "complete_answer": False,
                "model_generated": False,
                "product_qualified": False,
                "source_release_id": h02.f03.A05_RELEASE_ID,
                "source_manifest_sha256": h02.f03.A05_SOURCE_PIN,
                "independent_os_source_verified": True,
            }

    def _entry(self, sid: str) -> dict:
        h02.guard(type(sid) is str and sid in self.entries,
                  "UNKNOWN_SESSION_NO_REPLAY")
        entry = self.entries[sid]
        if entry["state"] == "AWAITING_ACK" and (
                dt.datetime.now(dt.timezone.utc) - entry["issued_at"]
                ).total_seconds() >= SESSION_LEASE_SECONDS:
            self._expire_entry(sid, entry)
            self._prune_tombstones()
            raise h02.Denied("F03_LOCAL_DELIVERY_BOUNDARY_DENIED")
        return entry

    def ack(self, sid: str, claim_id: str, challenge: str, text_sha256: str) -> dict:
        with self.lock:
            entry = self._entry(sid)
            h02.guard(entry["state"] == "AWAITING_ACK", "ACK_AFTER_TERMINAL")
            claim = next((x for x in entry["claims"] if x["claim_id"] == claim_id), None)
            h02.guard(
                claim is not None and claim_id not in entry["acked"],
                "UNKNOWN_OR_DUPLICATE_CLAIM",
            )
            h02.guard(
                type(challenge) is str and type(text_sha256) is str
                and secrets.compare_digest(challenge, claim["challenge"])
                and secrets.compare_digest(text_sha256, claim["text_sha256"]),
                "INVALID_CLIENT_ACK",
            )
            self._current(entry)
            entry["acked"].add(claim_id)
            self.inner.journal.record({
                "event": "client_ack", "sid": sid, "claim_id": claim_id,
                "when_ns": time.monotonic_ns(),
            })
            return {**h02.fail("SOURCE_REVIEW_ACK_RECEIVED"),
                    "acked": len(entry["acked"]), "needed": len(entry["claims"])}

    def terminal(self, sid: str) -> dict:
        with self.lock:
            entry = self._entry(sid)
            h02.guard(entry["state"] == "AWAITING_ACK", "DUPLICATE_TERMINAL")
            self._current(entry)
            h02.guard(len(entry["acked"]) == len(entry["claims"]),
                      "UNACKNOWLEDGED_SOURCE_CANDIDATES")
            entry["state"] = "TERMINATED"
            self.inner.journal.record({
                "event": "terminal", "sid": sid,
                "status": "LOCAL_SOURCE_REVIEW_ACKED_NOT_PRODUCT",
                "when_ns": time.monotonic_ns(),
            })
            self._drop_sensitive(entry)
            self._prune_tombstones()
            return {**h02.fail("LOCAL_SOURCE_REVIEW_ACKED_NOT_PRODUCT"),
                    "obligations_locally_fulfilled": True,
                    "product_pass": False,
                    "model_generated_answer": False}

    def cancel(self, sid: str) -> dict:
        with self.lock:
            entry = self._entry(sid)
            h02.guard(entry["state"] == "AWAITING_ACK", "CANCEL_AFTER_TERMINAL")
            entry["state"] = "CANCELLED"
            self.inner.journal.record({
                "event": "terminal", "sid": sid, "status": "CANCELLED_NO_REPLAY",
                "when_ns": time.monotonic_ns(),
            })
            self._drop_sensitive(entry)
            self._prune_tombstones()
            return h02.fail("CANCELLED_NO_REPLAY")


# Explicit loopback-only Nonprod source-review transport. It transports
# independently verified source candidates, NOT model-generated tokens.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class LocalSourceReviewHandler(BaseHTTPRequestHandler):
    server: ThreadingHTTPServer

    def log_message(self, format, *args):
        return  # no sensitive question body in ordinary HTTP access logs

    def _reply(self, payload: dict, status: int = 200):
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_POST(self):
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return self._reply({"status": "DENY_REMOTE_NETWORK"}, 403)
        # Loopback alone is not a Client authorization boundary: another local
        # process can otherwise read the firstparty corpus. This one process
        # bootstrap secret never claims to be remote Product IdP/tenant rights.
        expected_host = "127.0.0.1:" + str(self.server.server_address[1])
        if self.headers.get("Host") != expected_host:
            return self._reply({"status": "DENY_HOST"}, 403)
        if self.headers.get("Origin") is not None:
            return self._reply({"status": "DENY_CROSS_ORIGIN"}, 403)
        token = self.headers.get("Authorization")
        if not isinstance(token, str) or not secrets.compare_digest(
                token, "Bearer " + self.server.client_auth_token):
            return self._reply({"status": "DENY_LOCAL_CLIENT_AUTH"}, 403)
        if self.headers.get("Content-Type") != "application/json":
            return self._reply({"status": "DENY_CONTENT_TYPE"}, 415)
        length = self.headers.get("Content-Length")
        if length is None or not length.isascii() or not length.isdecimal():
            return self._reply({"status": "DENY_BAD_LENGTH"}, 400)
        size = int(length)
        if not 0 < size <= 8192:
            return self._reply({"status": "DENY_OVERSIZE"}, 413)
        try:
            data = json.loads(self.rfile.read(size))
            h02.guard(type(data) is dict, "INVALID_JSON_OBJECT")
            review = self.server.review
            if self.path == "/nonprod/source-review/start":
                h02.shape(data, {"topic"})
                result = review.start(data["topic"])
            elif self.path == "/nonprod/source-review/ack":
                h02.shape(data, {"session_id", "claim_id", "challenge", "text_sha256"})
                result = review.ack(
                    data["session_id"], data["claim_id"], data["challenge"],
                    data["text_sha256"],
                )
            elif self.path == "/nonprod/source-review/terminal":
                h02.shape(data, {"session_id"})
                result = review.terminal(data["session_id"])
            elif self.path == "/nonprod/source-review/cancel":
                h02.shape(data, {"session_id"})
                result = review.cancel(data["session_id"])
            else:
                return self._reply({"status": "DENY_UNKNOWN_ROUTE"}, 404)
            return self._reply(result)
        except (ValueError, TypeError, KeyError, h02.Denied):
            return self._reply(h02.fail("SOURCE_REVIEW_REQUEST_DENIED"), 403)
        except Exception:
            # No self-authorized Product fallback on unexpected failures.
            return self._reply(h02.fail("SOURCE_REVIEW_FAIL_CLOSED"), 503)


class LocalSourceReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, review: SourceReview, *, port: int = 0):
        super().__init__(("127.0.0.1", port), LocalSourceReviewHandler)
        self.review = review
        self.client_auth_token = secrets.token_urlsafe(48)
