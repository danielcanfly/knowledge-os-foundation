"""F03 Native Product Consumer seam, default OFF, with real loopback HTTP framing.

This module is a handoff interface, NOT the product route, an IdP, a source
rights controller, a semantic verifier, a cache service or an authorization
grant. Its injected authority MUST be supplied by a future trusted Native
server and is deliberately simulated in tests. Nothing here admits Product
HIT/WRITE even when an injected component claims that it has verified.

Never mount this loopback test transport on production or assume that an
authenticated=True envelope proves issuer authenticity.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
from threading import Lock
from typing import Any, Callable, Mapping, Protocol

from . import m27_b0_cache_contracts as abi
from . import m27_b1_cache_policy as cache03

CLIENT_SCHEMA = "m27.native-cache-client/v1"
SEAM_SCHEMA = "m27.f03.native-product-cache-seam/v1"
NATIVE_PATH = "/nonprod/f03/native/cache/plan"
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,96}\Z")
_MAX_BODY = 4096


class NativeCacheProtocolError(ValueError):
    """Denial with a bounded code; no secrets or upstream data in HTTP errors."""

    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


class NativeAuthorityResolver(Protocol):
    """Backend-only port: real IAM/rights qualification is NOT implemented here.

    resolve() must return a trusted server-built context and source lease, not
    values deserialized from a client body. recheck() must consult a real,
    independent revocation/source controller when one becomes available.
    This module cannot verify the authenticity of these implementations.
    """

    def resolve(self, client_request: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def recheck(self, request: Mapping[str, Any], identity: Mapping[str, Any],
                source: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _deny(ok: bool, code: str, status: int = 400) -> None:
    if not ok:
        raise NativeCacheProtocolError(code, status)


def _shape(value: Any, exact: set[str], code: str) -> dict:
    _deny(type(value) is dict and set(value) == exact, code)
    return value


def _parse_client(body: Any) -> dict:
    fields = {"schema_version", "request_id", "cache_mode", "question"}
    request = _shape(body, fields, "UNKNOWN_OR_MISSING_CLIENT_FIELD")
    _deny(request["schema_version"] == CLIENT_SCHEMA, "CLIENT_SCHEMA_MISMATCH")
    _deny(type(request["request_id"]) is str and
          _REQUEST_ID.fullmatch(request["request_id"]) is not None, "BAD_REQUEST_ID")
    question = request["question"]
    _deny(type(question) is str and 1 <= len(question) <= 2000
          and question.strip() == question
          and not any(ord(char) < 32 for char in question),
          "BAD_QUESTION")
    try:
        abi.parse_public_cache_choice({"cache_mode": request["cache_mode"]})
    except (ValueError, TypeError, KeyError) as exc:
        raise NativeCacheProtocolError("INVALID_CACHE_MODE") from exc
    return request


_LEASE_FIELDS = {"tenant_id", "principal_id", "auth_context_sha256",
                 "source_manifest_sha256", "rights_sha256", "revocation_epoch",
                 "expires_at", "source_current", "rights_current", "acl_current"}


def _utc_instant(timestamp: Any) -> dt.datetime:
    if type(timestamp) is not str or len(timestamp) > 40 or not timestamp.endswith("Z"):
        raise NativeCacheProtocolError("LEASE_TIME_INVALID", 403)
    try:
        result = dt.datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise NativeCacheProtocolError("LEASE_TIME_INVALID", 403) from exc
    _deny(result.tzinfo is not None and result.utcoffset() == dt.timedelta(0),
          "LEASE_TIME_INVALID", 403)
    return result


def _validate_lease(lease: Any, request: dict, *, now: dt.datetime) -> dict:
    lease = _shape(lease, _LEASE_FIELDS, "AUTHORITY_LEASE_INVALID")
    expected = {
        "tenant_id": request["identity"]["tenant_id"],
        "principal_id": request["identity"]["principal_id"],
        "auth_context_sha256": request["identity"]["auth_context_sha256"],
        "source_manifest_sha256": request["source"]["source_manifest_sha256"],
        "rights_sha256": request["source"]["rights_sha256"],
        "revocation_epoch": request["policy"]["revocation_epoch"],
    }
    for key, value in expected.items():
        _deny(type(lease[key]) is type(value) and lease[key] == value,
              "AUTHORITY_SCOPE_OR_EPOCH_MISMATCH", 403)
    for key in ("source_current", "rights_current", "acl_current"):
        _deny(lease[key] is True, "SOURCE_OR_RIGHTS_NOT_CURRENT", 403)
    _deny(_utc_instant(lease["expires_at"]) > now, "LEASE_EXPIRED", 403)
    return lease


def _namespace_digest(request: dict, lease: dict) -> str:
    """Never a permission token or an authorized store key, only a plan digest.

    Every field that changes safe cache reuse, including the complete semantic
    obligation set, participates. Do not collapse to an intent ID or text-only
    embedding, and never treat this digest as a product isolation boundary.
    """
    partition = {
        "identity": request["identity"],
        "question": request["question"],
        "source": request["source"],
        "policy": request["policy"],
        "ttl_seconds": request["cache_window"]["ttl_seconds"],
        "lease_expires_at": lease["expires_at"],
    }
    raw = json.dumps(partition, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def screen_untrusted_candidate(request: dict, candidate: Any,
                               *, now: dt.datetime | None = None) -> str:
    """Only structural/semantic pre-screen. NEVER returns an authorized HIT.

    Reuses CACHE01's exact scoped expiry check plus CACHE03's lexical safety
    discriminator, without invoking FixtureAuthority or a production store.
    There is no qualified semantic issuer here.
    """
    try:
        result = abi.screen_candidate(request, candidate, now=now)
        if result != "PROVER_REQUIRED":
            return "DENY_CANDIDATE"
        conflict = cache03._semantic_collision(request, candidate)
        if conflict is not None:
            return "DENY_CANDIDATE"
    except (ValueError, TypeError, KeyError, AttributeError):
        return "DENY_CANDIDATE"
    return "PROVER_REQUIRED_NOT_ADMITTED"


class NativeProductCacheSeam:
    """Bounded Native Consumer port with no store, provider or write activation.

    The sole authority dependency is a backend-native resolver. Its integrity
    is a future Integrator requirement, not a self-issued qualification.
    FEATURE OFF is an invariant here; a new signed admission-controlled
    implementation is required for actual Product cache IO.
    """

    def __init__(self, *, authority: NativeAuthorityResolver,
                 feature_enabled: bool = False,
                 clock: Callable[[], dt.datetime] | None = None,
                 store_factory: Callable[..., Any] | None = None,
                 verifier: Callable[..., Any] | None = None):
        if feature_enabled is not False or type(feature_enabled) is not bool:
            raise ValueError("PRODUCT_CACHE_ACTIVATION_REQUIRES_EXTERNAL_ADMISSION")
        if authority is None or not callable(getattr(authority, "resolve", None)) or not callable(
                getattr(authority, "recheck", None)):
            raise ValueError("NATIVE_AUTHORITY_PORT_REQUIRED")
        self.authority = authority
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        # Accepted as future interface hints, but NEVER invoked/instantiated.
        self._store_factory = store_factory
        self._verifier = verifier
        self._seen: set[str] = set()
        self._seen_lock = Lock()
        self.last_envelope: dict | None = None

    def consume(self, client_body: Any) -> dict:
        client = _parse_client(client_body)
        reqid = client["request_id"]
        # Atomic local replay fence before any resolver is called.
        with self._seen_lock:
            _deny(reqid not in self._seen, "REPLAY_DENIED", 409)
            _deny(len(self._seen) < 1024, "REPLAY_FENCE_CAP_REACHED", 429)
            self._seen.add(reqid)
        self.last_envelope = None
        try:
            resolved = self.authority.resolve(copy.deepcopy(client))
            resolved = _shape(resolved, {"context", "lease"}, "AUTHORITY_RESPONSE_INVALID")
            context = _shape(resolved["context"],
                             {"identity", "question", "source", "policy", "cache_window"},
                             "AUTHORITY_CONTEXT_INVALID")
            # Never synthesize fixture identity, derive claims from question text,
            # or let the client provide privileged identity/source/policy fields.
            _deny(type(context["question"]) is dict and
                  context["question"].get("text") == client["question"],
                  "SOURCE_TO_CLIENT_QUESTION_MISMATCH", 403)
            request = copy.deepcopy({
                "schema_version": abi.SCHEMA_VERSION, "request_id": reqid,
                "cache_mode": client["cache_mode"], **context,
            })
            try:
                request = abi.parse_internal_request(request)
            except (ValueError, TypeError, KeyError) as exc:
                raise NativeCacheProtocolError("NATIVE_CONTEXT_CONTRACT_DENIED", 403) from exc
            # Untrusted text cannot be accompanied by inconsistent prefilled
            # numeric/negation semantics. This is an extra conservative guard,
            # NOT a substitute for qualified semantic extraction/verifier.
            question = request["question"]
            _deny(bool(cache03._NEG.search(question["text"])) == question["negated"],
                  "NATIVE_QUESTION_NEGATION_MISMATCH", 403)
            _deny(sorted(cache03._NUMBER.findall(question["text"])) ==
                  sorted(question["numeric_literals"]),
                  "NATIVE_QUESTION_NUMERIC_MISMATCH", 403)
            now = self.clock()
            _deny(isinstance(now, dt.datetime) and now.tzinfo is not None
                  and now.utcoffset() == dt.timedelta(0),
                  "TRUSTED_UTC_CLOCK_REQUIRED", 503)
            initial = _validate_lease(resolved["lease"], request, now=now)
            # A second authority observation refuses changed source, expiry,
            # ACL, principal, rights digest or revocation epoch.
            checked = self.authority.recheck(copy.deepcopy(request),
                                             copy.deepcopy(request["identity"]),
                                             copy.deepcopy(request["source"]))
            checked = _validate_lease(checked, request, now=self.clock())
            _deny(checked == initial, "AUTHORITY_REVOCATION_OR_SOURCE_RACE", 409)
            plan = abi.describe_cache_operations(request, feature_enabled=False)
            # This is an unexecuted, nonauthorizing *what-if* mode plan.
            proposal = abi.describe_cache_operations(request, feature_enabled=True)
            receipt = abi.build_response_contract(request, status=plan.decision)
            receipt.update({
                "seam_schema": SEAM_SCHEMA,
                "scope": "NONPROD_PROTOCOL_ONLY_NO_ISSUER",
                "cache_status": plan.decision,
                "proposed_mode_decision": proposal.decision,
                "cache_scope_fingerprint_sha256": _namespace_digest(request, checked),
                "product_cache_enabled": False,
                "product_authenticated": False,
                "answer_cache_hit_admitted": False,
                "answer_cache_write_admitted": False,
                "answer_cache_lookup_invocations": 0,
                "answer_cache_write_invocations": 0,
                "cache_io_performed": False,
                "external_side_effect_replayed": False,
                "real_issuer_admission": "HOLD",
                "source_revocation_admission": "HOLD",
            })
            self.last_envelope = copy.deepcopy(request)
            return receipt
        except NativeCacheProtocolError:
            raise
        except Exception as exc:
            raise NativeCacheProtocolError("UPSTREAM_NATIVE_AUTHORITY_UNAVAILABLE", 503) from exc


class _LoopbackHandler(BaseHTTPRequestHandler):
    server: "NativeProductCacheLoopback"

    def log_message(self, *_: Any) -> None:
        return  # no query, token or subject emitted to logs

    def _reply(self, status: int, value: Mapping[str, Any]) -> None:
        data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        for key, v in (
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
        ):
            self.send_header(key, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if (self.client_address[0] != "127.0.0.1" or
            self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or
            not hmac.compare_digest(self.headers.get("X-Native-Seam-Token", ""),
                                    self.server.transport_token)):
            self._reply(HTTPStatus.FORBIDDEN, {"error": "NONPROD_NATIVE_TRANSPORT_DENIED"})
            return
        if self.path != NATIVE_PATH:
            self._reply(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
            return
        if self.headers.get("Content-Type", "").lower() != "application/json":
            self._reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON_ONLY"})
            return
        size = self.headers.get("Content-Length", "")
        if not size.isdecimal() or not 0 < int(size) <= _MAX_BODY:
            self._reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "INVALID_BODY_LENGTH"})
            return
        try:
            body = json.loads(self.rfile.read(int(size)))
            result = self.server.seam.consume(body)
        except NativeCacheProtocolError as exc:
            self._reply(exc.status, {"error": exc.code})
            return
        except (UnicodeError, json.JSONDecodeError):
            self._reply(HTTPStatus.BAD_REQUEST, {"error": "MALFORMED_JSON"})
            return
        self._reply(HTTPStatus.OK, result)


class NativeProductCacheLoopback(ThreadingHTTPServer):
    """Independent non-fixture HTTP transport; localhost ephemeral port only."""

    allow_reuse_address = False

    def __init__(self, seam: NativeProductCacheSeam, *,
                 host: str = "127.0.0.1", port: int = 0):
        if type(seam) is not NativeProductCacheSeam or host != "127.0.0.1" or port != 0:
            raise ValueError("NONPROD_LOOPBACK_EPHEMERAL_ONLY")
        self.seam = seam
        self.transport_token = secrets.token_urlsafe(32)
        super().__init__((host, port), _LoopbackHandler)
