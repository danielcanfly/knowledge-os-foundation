"""B3-03 exclusive H02 Nonprod join: verified research plus fail-closed cache.

Only this isolated loopback service uses the frozen worker adapters together.
Fixture identity/keys/rights are never Product credentials. No provider calls.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from . import m27_b0_cache_contracts as abi
from . import m27_b1_cache_store as cache02
from . import m27_b1_cache_policy as cache03
from . import m27_b1_cache_native_adapter as cache04
from . import m27_b2_cache_writeback_gate as cache05
from . import m27_b0_revocation_contract as g04

JOIN_SCHEMA = "m27.h02.cache-join-nonprod/v1"
RESEARCH_PATH = "/nonprod/h02/research"
ROUTE_CONTRACT = {
    "schema": "m27.h02.provider-routing-reserved/v1",
    "primary": "CUSTOM_CLOUDFLARE_WORKER_GATEWAY",
    "fallback": "MINIMAX_ONLY_CLASSIFIED_OPERATIONAL_FAILURE",
    "primary_live": "PRIMARY_LIVE_HOLD",
    "activated": False,
    "model_calls": 0,
    "unaccepted_b3_01_02_code_merged": False,
}
_FIXTURE_SOURCE = b"Fixture-only source for local CACHE03/CACHE05 tests; not a signed claim."
_FIXTURE_SHA = hashlib.sha256(_FIXTURE_SOURCE).hexdigest()
_FIXTURE_KEY = b"B3-03 LOCAL FIXTURE INTEGRITY KEY NEVER PRODUCT 2026"
_FIXTURE_PROOF_KEY = b"B3-03 LOCAL FIXTURE ASSERTION KEY NEVER PRODUCT 2026"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


class H02CacheJoin:
    """Strictly nonpublic orchestration. NO auth, no Production admission.

    OFF requires no cache backend initialization and ZERO cache I/O.
    ON is a separate test-only temp-directory experiment with an explicit
    environment switch. The browser cannot set any issuer/authority controls.
    """

    def __init__(self, *, feature_enabled: bool = False,
                 fixture_only: bool = False, fixture_root: Path | None = None):
        if type(feature_enabled) is not bool or type(fixture_only) is not bool:
            raise ValueError("BOOLEAN_FLAGS_REQUIRED")
        if feature_enabled and not fixture_only:
            raise ValueError("INDEPENDENT_PRODUCT_ISSUER_UNAVAILABLE")
        if feature_enabled:
            if (os.environ.get("M27_H02_CACHE_JOIN_FIXTURE_MODE") != "1"
                    or os.environ.get("M27_CACHE02_FIXTURE_TEST_MODE") != "1"
                    or os.environ.get("M27_CACHE05_FIXTURE_TEST_MODE") != "1"):
                raise ValueError("TEST_ONLY_SWITCH_REQUIRED")
            if fixture_root is None or not Path(fixture_root).resolve().is_relative_to(
                    Path(tempfile.gettempdir()).resolve()):
                raise ValueError("FIXTURE_ONLY_SYSTEM_TEMP_STORAGE")
        self.feature_enabled = feature_enabled
        self.fixture_only = feature_enabled and fixture_only
        self.store = None
        self.authority = None
        self.revocation = None
        self.actor = None
        self.store_lookup_calls = 0
        self.store_write_calls = 0
        if self.fixture_only:
            root = Path(fixture_root).resolve()
            root.mkdir(parents=True, exist_ok=True)
            template = cache04.internal_demo_envelope(
                "AUTO", "What does this fixture source say?", "fixture-init-0001")
            ident = template["identity"]
            self.actor = cache03.Actor(ident["tenant_id"], ident["principal_id"],
                                       ident["principal_id"], ident["auth_context_sha256"],
                                       True, "LOCAL_TEST_FIXTURE_NOT_PRODUCT")
            self.authority = cache03.FixtureAuthority(root / "rights.sqlite3",
                                                      fixture_only=True)
            self.revocation = g04.LocalRevocationContract(
                root / "revoked_data.sqlite3", root / "revoked_authority.sqlite3",
                fixture_only=True)
            self.store = cache02.DurableSemanticAnswerCacheStore(
                root / "answer_store.sqlite3", feature_enabled=True, fixture_only=True,
                authority_guard=self._current_source_rights,
                integrity_key=_FIXTURE_KEY)

    def provision_test_source(self) -> None:
        """Explicit test setup, NOT an HTTP API or automatic self-issued rights."""
        if not self.fixture_only:
            raise ValueError("TEST_FIXTURE_ONLY")
        r = cache04.internal_demo_envelope(
            "AUTO", "What does this fixture source say?", "fixture-init-0001")
        now = utcnow()
        binding = {
            "source_id": "fixture-source", "source_sha256": _FIXTURE_SHA,
            "revision": r["source"]["corpus_revision"],
            "citation_sha256": _FIXTURE_SHA,
        }
        self.authority.provision_fixture(
            r, actor=self.actor, bindings=[binding],
            consent_until=cache05.z(now + dt.timedelta(minutes=15)),
            authorized_fixture=True)
        self.revocation.provision_fixture(
            tenant=r["identity"]["tenant_id"],
            principal=r["identity"]["principal_id"],
            source_id="fixture-source", source_revision=r["source"]["corpus_revision"],
            right_version=1, consent_expires_at=int(time.time()) + 900,
            actor=r["identity"]["principal_id"], authorized_fixture=True)

    def _current_source_rights(self, request: dict, _op: str = "read") -> bool:
        if not self.fixture_only:
            return False
        try:
            r = abi.parse_internal_request(request)
            ident = r["identity"]
            if ident["tenant_id"] != self.actor.tenant_id or ident["principal_id"] != self.actor.principal_id:
                return False
            for source_id in r["source"]["source_ids"]:
                lease = self.revocation.current_lease_fixture(
                    tenant=ident["tenant_id"], principal=ident["principal_id"],
                    source_id=source_id, actor=self.actor.actor_id,
                    authorized_fixture=True, now=int(time.time()))
                if lease.revocation_epoch != r["policy"]["revocation_epoch"]:
                    return False
                if lease.source_revision != r["source"]["corpus_revision"]:
                    return False
            self.authority.snapshot(r, actor=self.actor, now=utcnow())
            return True
        except (ValueError, KeyError, g04.RevocationDenied):
            return False

    def fixture_gate(self) -> cache05.FinalWriteGate:
        """Test-only CAS adapter; not callable by HTTP clients."""
        if not self.fixture_only:
            raise ValueError("PRODUCT_CACHE_WRITE_DENIED")
        return cache05.FinalWriteGate(
            store=self.store, authority=self.authority, actor=self.actor,
            fixture_verifier_secret=_FIXTURE_PROOF_KEY,
            fixture_only=True, feature_enabled=True)

    def dispatch_cache(self, *, mode: str, question: str, request_id: str) -> dict:
        # Reuse exact CACHE04 untrusted UI parsing and frozen CACHE01 envelope.
        cache04.parse_ui_request({
            "schema_version": cache04.UI_SCHEMA, "request_id": request_id,
            "cache_mode": mode, "question": question})
        request = cache04.internal_demo_envelope(mode, question, request_id)
        operation = abi.describe_cache_operations(request, feature_enabled=self.feature_enabled)
        decision = operation.decision
        candidate_count = 0
        lookup_invocations = 0
        if self.fixture_only and decision in ("LOOKUP_REQUIRED", "REGENERATE_NO_LOOKUP"):
            if not self._current_source_rights(request):
                decision = "SOURCE_RIGHTS_DENIED"
            elif decision == "LOOKUP_REQUIRED":
                # CACHE02 guard performs an additional source/rights check.
                lookup_invocations = 1
                self.store_lookup_calls += 1
                candidates = self.store.lookup_candidates(request, limit=4)
                if not self._current_source_rights(request):
                    decision = "SOURCE_RIGHTS_CHANGED"
                    candidates = []
                candidate_count = len(candidates)
                if candidates:
                    # Even a verified local fixture candidate MUST NOT be a HIT.
                    decision = "PROVER_REQUIRED"
        receipt = abi.build_response_contract(request, status=operation.decision)
        receipt.update({
            "schema": JOIN_SCHEMA, "ui_schema_version": cache04.UI_SCHEMA,
            "scope": "LOCAL_FIXTURE_ONLY",
            "cache_feature_enabled": self.feature_enabled,
            "cache_status": decision, "candidate_count": candidate_count,
            "answer_cache_lookup_invocations": lookup_invocations,
            "answer_cache_write_invocations": 0,
            "cache_io_performed": bool(lookup_invocations and self.store.path.exists()),
            "actual_store_io_authorized_as_product": False,
            "product_authenticated": False, "answer_published": False,
            "answer_cache_hit_admitted": False,
            "product_write_status": cache05.FinalWriteGate.product_write().status,
            "g04_current_rights_checked": bool(
                self.fixture_only and operation.decision in
                ("LOOKUP_REQUIRED", "REGENERATE_NO_LOOKUP")),
            "provider_route_contract": dict(ROUTE_CONTRACT),
        })
        return receipt


class H02JoinedHandler(cache04.Cache04Handler):
    """Reuse CACHE04 HTML/session/CSRF security and replace demo POST backend."""

    def do_POST(self) -> None:
        if not self._host_ok():
            self._reply(403, {"error": "NON_LOOPBACK_DENIED"})
            return
        if self.path not in (cache04.DEMO_PATH, RESEARCH_PATH):
            self._reply(404, {"error": "NOT_FOUND"})
            return
        if (not self._session_ok()
                or self.headers.get("Origin") != self.server.origin
                or self.headers.get("X-Cache-Demo-Request") != "1"):
            self._reply(403, {"error": "NONPROD_SESSION_OR_ORIGIN_DENIED"})
            return
        if self.headers.get("X-Cache-Demo-Cancelled") == "1":
            self._reply(409, {"error": "CANCELLED_BEFORE_EXECUTION"})
            return
        if self.headers.get("Content-Type", "").lower() != "application/json":
            self._reply(415, {"error": "JSON_ONLY"})
            return
        raw_len = self.headers.get("Content-Length", "")
        if not raw_len.isdecimal() or not 0 < int(raw_len) <= 16384:
            self._reply(413, {"error": "INVALID_BODY_LENGTH"})
            return
        try:
            body = json.loads(self.rfile.read(int(raw_len)))
            if self.path == RESEARCH_PATH:
                if self.server.research_bridge is None:
                    self._reply(503, {"error": "RESEARCH_BRIDGE_NOT_MOUNTED"})
                    return
                if type(body) is not dict:
                    raise ValueError("BAD_RESEARCH_REQUEST")
                # Original G02 validates TaskContract, exact identity, sources and replay.
                result = self.server.research_bridge.dispatch(body)
                result["cache_join"] = "RESEARCH_NONCACHEABLE"
                result["product_authenticated"] = False
                self._reply(200, result)
                return
            mode, question, reqid = cache04.parse_ui_request(body)
            with self.server.seen_lock:
                if reqid in self.server.seen:
                    raise cache04.DemoError("REPLAY_DENIED", 409)
                if len(self.server.seen) >= 256:
                    raise cache04.DemoError("REQUEST_CAP_REACHED", 429)
                self.server.seen.add(reqid)
            receipt = self.server.join.dispatch_cache(
                mode=mode, question=question, request_id=reqid)
        except cache04.DemoError as exc:
            self._reply(exc.status, {"error": exc.code})
            return
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._reply(400, {"error": "ADMISSION_OR_SOURCE_DENIED"})
            return
        self._reply(200, receipt)


class H02JoinedLoopback(cache04.Cache04Demo):
    def __init__(self, join: H02CacheJoin, *, research_bridge: Any = None,
                 host: str = "127.0.0.1", port: int = 0):
        if type(join) is not H02CacheJoin:
            raise ValueError("JOIN_REQUIRED")
        super().__init__(host, port, feature_enabled=join.feature_enabled)
        self.join = join
        self.research_bridge = research_bridge
        self.RequestHandlerClass = H02JoinedHandler
