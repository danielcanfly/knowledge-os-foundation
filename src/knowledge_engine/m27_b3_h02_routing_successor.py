"""B3-05 sole successor: isolated H02 route wiring, never a custom Gateway admission.

No production connection, credentials, deployment, live probe, or independent issuer.
Only an explicitly opted-in local fixture can exercise simulated provider envelopes.
H02 cache/G04/G02 source modules are inherited unchanged from frozen B3-03.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from typing import Any, Protocol

from . import m27_b1_cache_native_adapter as ui
from . import m27_b3_h02_cache_join as h02
from . import m27_b3_gateway_route_spec as map01
from . import m27_b3_provider_router as policy

ABI = "m27.b3.05.h02-routing-successor/v1"
ROUTE_PATH = "/nonprod/h02/route"
ACK_PATH = "/nonprod/h02/route/ack"
GATEWAY_FIXTURE_ROUTE_ID = "fixture-custom-gateway-not-deployed"
OBLIGATIONS = ("fixture_claim_1", "fixture_claim_2")
CITATION_IDS = ("fixture-source",)
SOURCE_TEXT = h02._FIXTURE_SOURCE.decode("utf-8")
assert all(x in SOURCE_TEXT for x in ("Fixture-only source", "not a signed claim"))
PRIMARY_LIVE = "PRIMARY_LIVE_HOLD"
HOLD_REASON = "CUSTOM_WORKER_GATEWAY_NOT_AUTHENTICATED_OR_DEPLOYED"
_UNTRUSTED = frozenset((
    "tenant", "principal", "source_sha256", "source_rights",
    "identity", "rights", "provider", "upstream_model_id", "gateway_route_id",
    "issuer", "claims", "fallback", "terms_approved", "source_region",
    "acl_epoch", "capability_gap", "cache_feature_enabled",
))


class Endpoint(Protocol):
    def stream(self, request: policy.ProviderRequest, timeout_s: float) -> Iterable[Mapping[str, object]]: ...


class StrictEnvelopePair:
    """Own each distinct transport; no silent substitution of Workers AI direct."""
    def __init__(self, primary: Endpoint, fallback: Endpoint, *, route_id: str = GATEWAY_FIXTURE_ROUTE_ID):
        if not route_id or route_id == "workers_ai_direct":
            raise ValueError("CUSTOM_GATEWAY_ROUTE_REQUIRED")
        self.primary, self.fallback, self.route_id = primary, fallback, route_id
        self.calls: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def stream(self, request: policy.ProviderRequest, timeout_s: float) -> Iterable[policy.WireEvent]:
        if request.abi != policy.ABI or request.provider not in (policy.PRIMARY, policy.FALLBACK):
            raise ValueError("INVALID_PROVIDER_REQUEST")
        endpoint = self.primary if request.provider == policy.PRIMARY else self.fallback
        with self.lock:
            self.calls.append({
                "provider": request.provider, "request_id": request.request_id,
                "task_sha256": request.task_sha256, "tenant": request.tenant,
                "principal": request.principal, "acl_epoch": request.acl_epoch,
                "obligation_ids": request.obligation_ids, "citation_ids": request.citation_ids,
                "cache_mode": request.cache_mode,
                "billing_idempotency_key_sha256": hashlib.sha256(
                    request.billing_idempotency_key.encode()).hexdigest(),
                "timeout_s": timeout_s, "t_monotonic": time.monotonic(),
            })
        for i, raw in enumerate(endpoint.stream(request, timeout_s)):
            if i >= 128:
                raise ValueError("UNBOUNDED_PROVIDER_FRAMES")
            if not isinstance(raw, Mapping):
                raise ValueError("NONMAPPING_PROVIDER_FRAME")
            if request.provider == policy.PRIMARY:
                yield policy.canonicalize_custom_cloudflare_gateway(
                    raw, required_route_id=self.route_id)
            else:
                yield policy.canonicalize_minimax(raw)


class G04FixtureRights:
    """Not a Product ACL issuer; checks frozen CACHE03/G04 fixture on every claim."""
    def __init__(self, join: h02.H02CacheJoin, envelope: dict[str, Any]):
        self.join, self.envelope = join, envelope

    def check(self, task: policy.Task) -> policy.Rights:
        ident = self.envelope["identity"]
        source = self.envelope["source"]
        current = (
            self.join.fixture_only and
            task.tenant == ident["tenant_id"] and
            task.principal == ident["principal_id"] and
            task.acl_epoch == str(self.envelope["policy"]["revocation_epoch"]) and
            task.source_sha256 == h02._FIXTURE_SHA and
            task.source_sha256 == hashlib.sha256(h02._FIXTURE_SOURCE).hexdigest() and
            task.source_rights == "fixture-approved" and
            source["source_ids"] == ["fixture-source"] and
            self.join._current_source_rights(self.envelope)
        )
        return policy.Rights(bool(current), "REVOKED" if not current else "",
                             task.acl_epoch if current else "",
                             task.source_sha256 if current else "",
                             task.source_rights if current else "")


class SourceBoundFixtureVerifier:
    """Two source-entailment checks against immutable bytes; not independent."""
    def verify(self, task: policy.Task, claim: policy.WireEvent,
               provider: str, upstream_model: str) -> policy.Proof:
        snippets = {
            OBLIGATIONS[0]: "Fixture-only source for local CACHE03/CACHE05 tests",
            OBLIGATIONS[1]: "not a signed claim.",
        }
        accepted = (
            provider in (policy.PRIMARY, policy.FALLBACK)
            and bool(upstream_model)
            and task.source_sha256 == h02._FIXTURE_SHA
            and claim.obligation_id in snippets
            and claim.text.strip() == snippets.get(claim.obligation_id)
            and claim.text.strip() in SOURCE_TEXT
            and claim.citation_ids == CITATION_IDS
        )
        return policy.Proof(
            accepted=accepted, reason="TEST_FIXTURE_ONLY" if accepted else "ENTAILMENT_DENIED",
            obligation_id=claim.obligation_id, source_sha256=h02._FIXTURE_SHA,
            citation_ids=CITATION_IDS, independent_issuer=False)


class H02RoutingSuccessor:
    """H02 source + local safe routing. No missing Gateway credentials are assumed."""
    def __init__(self, join: h02.H02CacheJoin, *, fixture_pair: StrictEnvelopePair | None = None,
                 allow_test_fallback: bool = False, rights_override: Any = None,
                 verifier_override: Any = None):
        if type(join) is not h02.H02CacheJoin:
            raise ValueError("B303_JOIN_REQUIRED")
        if (map01.PRIMARY != policy.PRIMARY or map01.FALLBACK != policy.FALLBACK
                or map01.product_acceptance_matrix() != {
                    gate: "HOLD_AWAIT_INDEPENDENT_REAL_AUTHORITY"
                    for gate in map01.HOLD_GATES}):
            raise ValueError("B301_GATEWAY_ROUTE_AUTHORITY_INVARIANT")
        # A fixture ID is deliberately insufficient proof of a deployed Gateway.
        self.gateway_inventory_audit = map01.audit_route_registry({
            "primary_kind": policy.PRIMARY, "fallback_kind": policy.FALLBACK,
            "worker_gateway_deployed": False, "fallback_on_auth_failure": False,
            "fallback_after_answer_text": False,
        })
        if self.gateway_inventory_audit.shape_valid:
            raise ValueError("UNVERIFIED_GATEWAY_CANNOT_BE_ADMITTED")
        if fixture_pair is not None and (
            os.environ.get("M27_B3_H02_ROUTE_FIXTURE_MODE") != "1" or not join.fixture_only
        ):
            raise ValueError("FIXTURE_ONLY_ROUTE_AUTHORITY_REQUIRED")
        self.join = join
        self.pair = fixture_pair
        self.allow_test_fallback = bool(allow_test_fallback) and fixture_pair is not None
        self.rights_override = rights_override
        self.verifier_override = verifier_override
        self.local = threading.local()
        self.router = None
        if self.pair is not None:
            # Provenance is expressly false: route ID denotes a *nondeployed* fixture.
            self.router = policy.Router(
                policy.RouteConfig(mode="nonprod_fixture",
                                   gateway_route_id=GATEWAY_FIXTURE_ROUTE_ID,
                                   provenance_verified=False, max_primary_attempts=2,
                                   max_fallback_attempts=1, backoff_s=0,
                                   attempt_timeout_s=2, total_deadline_s=8,
                                   max_total_attempt_tokens=1200, max_input_tokens=200,
                                   max_output_tokens=96, max_known_cost_usd=0.10),
                self.pair, rights_override or self, verifier_override or SourceBoundFixtureVerifier(),
                publish=self._publish, cancelled=self._cancelled)

    def _publish(self, obligation: str, text: str) -> None:
        receiver = getattr(self.local, "publish", None)
        if receiver is None:
            raise ValueError("MISSING_CLIENT_PUBLICATION")
        receiver(obligation, text)

    def _cancelled(self) -> bool:
        f = getattr(self.local, "cancelled", None)
        return f() if f else True

    def check(self, task: policy.Task) -> policy.Rights:
        envelope = getattr(self.local, "envelope", None)
        if envelope is None:
            return policy.Rights(False, "REVOKED")
        return G04FixtureRights(self.join, envelope).check(task)

    def dispatch(self, *, body: dict[str, Any], publish: Any,
                 cancelled: Any = lambda: False) -> tuple[policy.Outcome | None, dict[str, Any]]:
        if self.router is None:
            return None, {
                "schema": ABI, "status": "safe_abstention", "reason": HOLD_REASON,
                "primary_live": PRIMARY_LIVE, "route_activated": False,
                "product_authenticated": False, "cache_feature_enabled": False,
                "answer_cache_hit_admitted": False, "actual_provider_calls": 0,
            }
        if not isinstance(body, dict) or _UNTRUSTED.intersection(body):
            raise ValueError("CLIENT_CANNOT_ISSUE_IDENTITY_PROVIDER_OR_RIGHTS")
        if set(body) != {"schema_version", "request_id", "cache_mode", "question"}:
            raise ValueError("STRICT_UI_SCHEMA_REQUIRED")
        mode, question, rid = ui.parse_ui_request(body)
        envelope = ui.internal_demo_envelope(mode, question, rid)
        # Preserve B3-03 cache and G04 semantics; BYPASS has zero store I/O.
        cache_receipt = self.join.dispatch_cache(mode=mode, question=question, request_id=rid)
        if cache_receipt["cache_status"] in ("SOURCE_RIGHTS_DENIED", "SOURCE_RIGHTS_CHANGED"):
            return None, {"schema": ABI, "status": "safe_abstention",
                          "reason": "SOURCE_RIGHTS_DENIED", "primary_live": PRIMARY_LIVE,
                          "cache_receipt": cache_receipt, "actual_provider_calls": 0}
        ident = envelope["identity"]
        task = policy.Task(
            request_id=rid,
            task_sha256=hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            tenant=ident["tenant_id"], principal=ident["principal_id"],
            acl_epoch=str(envelope["policy"]["revocation_epoch"]),
            source_sha256=h02._FIXTURE_SHA, source_rights="fixture-approved",
            source_region="TW", obligation_ids=OBLIGATIONS, citation_ids=CITATION_IDS,
            estimated_input_tokens=60, max_output_tokens=96,
            fallback_consent=self.allow_test_fallback,
            fallback_regions=("TW",) if self.allow_test_fallback else (),
            fallback_terms_approved=self.allow_test_fallback,
            cache_mode=mode)
        self.local.envelope = envelope
        self.local.publish = publish
        self.local.cancelled = cancelled
        try:
            result = self.router.route(task)
        finally:
            self.local.envelope = None
            self.local.publish = None
            self.local.cancelled = None
        # Missing final usage cannot silently be accepted after streamed text.
        # Abort terminal and withhold ACK admission; never initiate a second provider.
        if result.status == "answered" and (
                result.actual_input_tokens is None or
                result.actual_output_tokens is None or
                result.actual_cost_usd is None):
            result.status = "partial_terminated"
            result.reason = "USAGE_RECEIPT_MISSING_AFTER_TEXT"
            result.client_notified_status = "partial_terminated"
        receipt = {
            "schema": ABI, "status": result.status, "reason": result.reason,
            "scope": "ISOLATED_FIXTURE_ONLY_NOT_PRODUCT",
            "primary_live": PRIMARY_LIVE, "route_activated": True,
            "primary_route": policy.PRIMARY, "fallback_route": policy.FALLBACK,
            "route_provenance": result.route_provenance,
            "actual_provider_calls": len(result.attempted), "route_id": result.route_id,
            "primary_error_class": result.primary_error_class,
            "fallback_reason": result.fallback_reason,
            "attempts": [asdict(x) for x in result.attempted],
            "first_text_monotonic": result.first_text_monotonic,
            "terminal_monotonic": result.terminal_monotonic,
            "observed_input_tokens": result.actual_input_tokens,
            "observed_output_tokens": result.actual_output_tokens,
            "observed_cost_usd": result.actual_cost_usd,
            "answer_cache_hit_admitted": False, "product_authenticated": False,
            "cache_receipt": cache_receipt,
            "issued_by_independent_verifier": False,
        }
        return result, receipt


class H02SuccessorHandler(h02.H02JoinedHandler):
    """Actual loopback HTTP streaming+ACK; inherits G02 research and cache endpoints."""
    def do_GET(self) -> None:
        if self.path != "/nonprod/h02/session":
            return super().do_GET()
        if not self._host_ok():
            return self._reply(403, {"error": "NON_LOOPBACK_DENIED"})
        body = b'{"scope":"NONPROD_FIXTURE_SESSION_NOT_PRODUCT"}'
        self._headers(200, "application/json; charset=utf-8", len(body))
        self.send_header("Set-Cookie",
                         f"demo_session={self.server.session}; HttpOnly; SameSite=Strict; Path=/nonprod/h02/")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path not in (ROUTE_PATH, ACK_PATH):
            return super().do_POST()
        if not self._host_ok():
            return self._reply(403, {"error": "NON_LOOPBACK_DENIED"})
        if (not self._session_ok() or self.headers.get("Origin") != self.server.origin
                or self.headers.get("X-Cache-Demo-Request") != "1"):
            return self._reply(403, {"error": "NONPROD_SESSION_OR_ORIGIN_DENIED"})
        if self.headers.get("X-Cache-Demo-Cancelled") == "1":
            return self._reply(409, {"error": "CANCELLED_BEFORE_EXECUTION"})
        if self.headers.get("Content-Type", "").lower() != "application/json":
            return self._reply(415, {"error": "JSON_ONLY"})
        size = self.headers.get("Content-Length", "")
        if not size.isdecimal() or not 0 < int(size) <= 4096:
            return self._reply(413, {"error": "INVALID_BODY_LENGTH"})
        try:
            body = json.loads(self.rfile.read(int(size)))
            if self.path == ACK_PATH:
                return self._ack(body)
            if self.server.successor.router is None:
                # The default is genuinely OFF. No transport is ever contacted.
                _, receipt = self.server.successor.dispatch(body={},
                                                            publish=lambda *_: None)
                return self._reply(503, receipt)
            if type(body) is not dict or set(body) != {
                    "schema_version", "request_id", "cache_mode", "question"}:
                raise ValueError("STRICT_UI_SCHEMA_REQUIRED")
            if _UNTRUSTED.intersection(body):
                raise ValueError("IDENTITY_PROVIDER_OVERRIDE_DENIED")
            mode, question, rid = ui.parse_ui_request(body)
            with self.server.seen_lock:
                if rid in self.server.seen or len(self.server.seen) >= 256:
                    return self._reply(409, {"error": "REPLAY_OR_REQUEST_CAP"})
                self.server.seen.add(rid)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return self._reply(400, {"error": "ADMISSION_DENIED"})
        self.send_response(200)
        for key, value in (("Content-Type", "application/x-ndjson; charset=utf-8"),
                           ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                           ("X-Route-Scope", "FIXTURE_ONLY_PRIMARY_LIVE_HOLD"),
                           ("Connection", "close")):
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True
        published: list[dict[str, Any]] = []
        sent_ns: list[int] = []
        def emit(frame: dict[str, Any]) -> None:
            self.wfile.write((json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n").encode())
            self.wfile.flush()
        def publish(ob: str, value: str) -> None:
            digest = hashlib.sha256(value.encode()).hexdigest()
            emit({"event": "answer_text", "obligation_id": ob,
                  "text": value, "text_sha256": digest, "verified_by": "LOCAL_FIXTURE_ONLY"})
            sent_ns.append(time.monotonic_ns())
            published.append({"obligation_id": ob, "text_sha256": digest})
        try:
            outcome, receipt = self.server.successor.dispatch(
                body=body, publish=publish,
                cancelled=lambda: self.headers.get("X-Demo-Client-Revoked") == "1")
            if outcome is None or outcome.status != "answered":
                published.clear()  # a partial/cancelled answer cannot be ACK-admitted
            receipt["server_first_text_ns"] = sent_ns[0] if sent_ns else None
            receipt["server_terminal_ns"] = time.monotonic_ns()
            receipt["client_ack_state"] = "PENDING_EXTERNAL_CLIENT" if published else "DENIED"
            with self.server.ack_lock:
                self.server.pending[rid] = tuple((x["obligation_id"], x["text_sha256"]) for x in published)
            emit({"event": "terminal", "receipt": receipt})
        except (BrokenPipeError, ConnectionResetError, OSError):
            # The Router's callback failure fails closed; never retry another provider.
            with self.server.ack_lock:
                self.server.pending.pop(rid, None)

    def _ack(self, body: Any) -> None:
        if (type(body) is not dict or set(body) != {"request_id", "claims"}
                or not isinstance(body["request_id"], str)
                or not isinstance(body["claims"], list)
                or not all(type(x) is dict and set(x) == {"obligation_id", "text_sha256"}
                           for x in body["claims"])):
            return self._reply(400, {"error": "ACK_SCHEMA_DENIED"})
        claim_tuples = tuple((x["obligation_id"], x["text_sha256"]) for x in body["claims"])
        with self.server.ack_lock:
            rid = body["request_id"]
            known = self.server.pending.get(rid)
            if not known or known != claim_tuples or rid in self.server.acked:
                return self._reply(409, {"error": "UNMATCHED_OR_REPLAYED_ACK"})
            self.server.acked.add(rid)
            self.server.pending.pop(rid, None)
        self._reply(200, {"status": "CLIENT_ACK_RECEIVED", "request_id": rid,
                          "ack_count": len(claim_tuples), "scope": "INDEPENDENT_OS_CLIENT_FIXTURE"})


class H02RoutedLoopback(h02.H02JoinedLoopback):
    def __init__(self, successor: H02RoutingSuccessor, *, research_bridge: Any = None,
                 host: str = "127.0.0.1", port: int = 0):
        super().__init__(successor.join, research_bridge=research_bridge, host=host, port=port)
        self.successor = successor
        self.pending: dict[str, tuple[tuple[str, str], ...]] = {}
        self.acked: set[str] = set()
        self.ack_lock = threading.Lock()
        self.RequestHandlerClass = H02SuccessorHandler
