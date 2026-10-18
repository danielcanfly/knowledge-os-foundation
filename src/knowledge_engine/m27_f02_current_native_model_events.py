"""M27 F02 current Native model wire adapter (NONPROD / candidate only).

Converts an observed provider event stream into causally attributed, non-published
generated claim *proposals*. F02 never performs semantic verification, publishes
answer_text, claims a client ACK, or treats fixture/replay as a live Provider.
Actual provider calls are separate and gated by a fresh authenticated grant.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


ABI = "m27.nonprod.f02-g01.generated-stream/v1"
SYNTHETIC = "SYNTHETIC_FIXTURE"
HISTORICAL = "HISTORICAL_REPLAY"
LIVE = "LIVE_NEW_PROVIDER"
ALLOWED_ORIGINS = frozenset({SYNTHETIC, HISTORICAL, LIVE})
HASH = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
MAX_RAW_EVENT = 16384
MAX_EVENTS = 512
MAX_TEXT = 8192
MAX_DELTA = 2048
KINDS = frozenset({"request_start", "model_identity", "delta",
                   "provider_done", "stream_end", "error"})


class Refused(ValueError):
    """Fail closed: not a provider, client or product acceptance."""


def require(ok: bool, reason: str):
    if not ok:
        raise Refused(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class Pins:
    task_id: str
    request_id: str
    question_sha256: str
    task_contract_sha256: str
    tenant: str
    principal: str
    source_release_sha256: str
    source_manifest_sha256: str
    source_rights_epoch: int
    source_acl_sha256: str
    answer_obligation_ids: tuple[str, ...]
    model_route_policy_version: str
    max_tokens: int
    deadline_monotonic_ns: int
    cache_mode: str = "OFF"

    def validate(self) -> None:
        for s in (self.task_id, self.request_id, self.tenant, self.principal,
                  self.model_route_policy_version):
            require(type(s) is str and bool(ID.fullmatch(s)), "INVALID_REQUEST_PIN")
        for h in (self.question_sha256, self.task_contract_sha256,
                  self.source_release_sha256, self.source_manifest_sha256,
                  self.source_acl_sha256):
            require(type(h) is str and bool(HASH.fullmatch(h)), "INVALID_HASH_PIN")
        require(type(self.source_rights_epoch) is int and
                self.source_rights_epoch >= 0, "INVALID_RIGHTS_EPOCH")
        require(type(self.answer_obligation_ids) is tuple and
                1 <= len(self.answer_obligation_ids) <= 6 and
                len(set(self.answer_obligation_ids)) == len(self.answer_obligation_ids) and
                all(type(o) is str and ID.fullmatch(o) for o in self.answer_obligation_ids),
                "INVALID_OBLIGATIONS")
        require(type(self.max_tokens) is int and 0 < self.max_tokens <= 2048,
                "TOKEN_BUDGET")
        require(type(self.deadline_monotonic_ns) is int and
                self.deadline_monotonic_ns > time.monotonic_ns(), "DEADLINE_EXPIRED")
        require(self.cache_mode == "OFF", "CACHE_NOT_AUTHORIZED")


class EventJournal:
    """Local append-only fsync receipt. Never stores source text, API keys or raw events."""

    def __init__(self, file_path: Path):
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_sha = "0" * 64
        # Do not append to a prior run; only a fresh exclusive nonprod receipt.
        fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)

    def record(self, public_event: dict) -> dict:
        safe = {k: v for k, v in public_event.items()
                if k not in ("text", "raw", "secret", "token", "authorization")}
        with self._lock:
            entry = {"event": safe, "prev_sha256": self._last_sha}
            entry["record_sha256"] = sha(canonical(entry))
            with self.path.open("ab") as f:
                f.write(canonical(entry) + b"\n")
                f.flush()
                os.fsync(f.fileno())
            self._last_sha = entry["record_sha256"]
        return entry


def verify_record_chain(path: Path) -> list[dict]:
    previous = "0" * 64
    out = []
    for line in Path(path).read_bytes().splitlines():
        obj = json.loads(line)
        require(type(obj) is dict and obj.get("prev_sha256") == previous,
                "JOURNAL_CHAIN_TAMPER")
        check = dict(obj)
        recorded = check.pop("record_sha256", None)
        require(recorded == sha(canonical(check)), "JOURNAL_BYTES_TAMPER")
        require("text" not in obj["event"] and "raw" not in obj["event"],
                "JOURNAL_TEXT_LEAK")
        previous = recorded
        out.append(obj)
    return out


def _authorize_origin(origin_class: str, *, live_receipt_verifier=None,
                      authenticated_provider_receipt=None):
    require(origin_class in ALLOWED_ORIGINS, "UNKNOWN_ORIGIN")
    if origin_class == LIVE:
        # This version deliberately has NO qualified trust root. Neither
        # callback=lambda True nor a caller-supplied receipt is an independent
        # verified, scoped, fresh Provider/Client grant. A future Integrator
        # must add the real pinned authority and re-run exact negative tests.
        raise Refused("NEW_LIVE_GRANT_NOT_VERIFIED")
    require(live_receipt_verifier is None and authenticated_provider_receipt is None,
            "NO_FIXTURE_TO_LIVE_ESCALATION")


class NativeEventProducer:
    """Bounded provider event normalization. No answer_text publication."""

    def __init__(self, pins: Pins, journal: EventJournal, *,
                 origin_class: str = SYNTHETIC, live_receipt_verifier=None,
                 authenticated_provider_receipt=None):
        pins.validate()
        _authorize_origin(origin_class,
                          live_receipt_verifier=live_receipt_verifier,
                          authenticated_provider_receipt=authenticated_provider_receipt)
        self.pins = pins
        self.journal = journal
        self.origin_class = origin_class
        self.seq = 0
        self.started = False
        self.identity = None
        self.done = False
        self.ended = False
        self.failed = False
        self.delta_count = 0
        self.buffer = ""
        self.full_text = ""
        self.events = []
        self.proposals = []
        self.delta_refs = []
        self.started_ns = time.monotonic_ns()
        self.first_delta_ns = None
        self.done_ns = None
        self.provider_usage = "UNKNOWN"
        self.usage_observed = False

    def _emit(self, kind: str, **values) -> dict:
        self.seq += 1
        event = {"abi": ABI, "event_id": f"{self.pins.request_id}:{self.seq}",
                 "seq": self.seq, "event_kind": kind,
                 "task_id": self.pins.task_id, "request_id": self.pins.request_id,
                 "monotonic_ns": time.monotonic_ns(),
                 "model_origin_class": self.origin_class,
                 "cache_mode": "OFF", **values}
        self.journal.record(event)
        self.events.append(event)
        return event

    def ingest(self, raw: bytes) -> list[dict]:
        require(not self.failed and not self.ended, "STREAM_ALREADY_STOPPED")
        require(not self.done, "EVENT_AFTER_PROVIDER_DONE")
        require(time.monotonic_ns() < self.pins.deadline_monotonic_ns,
                "DEADLINE_EXPIRED")
        require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_EVENT,
                "WIRE_EVENT_SIZE")
        require(len(self.events) < MAX_EVENTS, "WIRE_EVENT_COUNT")
        try:
            wire = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise Refused("INVALID_PROVIDER_JSON") from exc
        require(type(wire) is dict and wire.get("event") in KINDS,
                "UNKNOWN_PROVIDER_EVENT")
        # Prevent a wire sender from elevating the provenance class, claiming a
        # verified answer, overriding task/source pins, or prescribing output.
        require(not (set(wire) & {"model_origin_class", "origin_class",
                                 "answer_text", "verified", "task_contract_sha256",
                                 "source_rights_epoch", "client_ack", "published"}),
                "PROVENANCE_OR_AUTHORITY_SPOOF")
        kind = wire["event"]
        ident = {"raw_event_sha256": sha(raw)}
        if kind == "error":
            self.failed = True
            self._emit("provider_error", **ident, category="UPSTREAM_REPORTED_ERROR")
            raise Refused("UPSTREAM_REPORTED_ERROR")
        if kind == "request_start":
            require(not self.started and not self.identity, "DUPLICATE_START")
            require(wire.get("request_id") == self.pins.request_id,
                    "REQUEST_ID_MISMATCH")
            self.started = True
            return [self._emit("provider_start", **ident)]
        require(self.started, "START_REQUIRED")
        if kind == "model_identity":
            require(self.identity is None and not self.delta_count, "MODEL_IDENTITY_ORDER")
            provider = wire.get("provider")
            model = wire.get("model")
            require(type(provider) is str and ID.fullmatch(provider) and
                    type(model) is str and ID.fullmatch(model), "UNOBSERVED_MODEL_IDENTITY")
            self.identity = (provider, model)
            return [self._emit("model_identity_observed", **ident,
                               provider=provider, model=model)]
        require(self.identity is not None, "MODEL_IDENTITY_REQUIRED")
        if kind == "delta":
            chunk = wire.get("text")
            require(type(chunk) is str and chunk and
                    len(chunk.encode("utf-8")) <= MAX_DELTA, "BAD_DELTA")
            require(len(self.full_text.encode("utf-8")) +
                    len(chunk.encode("utf-8")) <= MAX_TEXT, "TEXT_BUDGET")
            self.delta_count += 1
            require(self.delta_count <= self.pins.max_tokens * 4, "DELTA_BUDGET")
            self.full_text += chunk
            if self.first_delta_ns is None:
                self.first_delta_ns = time.monotonic_ns()
            delta = self._emit("provider_delta", **ident, provider=self.identity[0],
                               model=self.identity[1],
                               delta_text_sha256=sha(chunk.encode()),
                               accumulated_text_sha256=sha(self.full_text.encode()))
            self.delta_refs.append(delta["event_id"])
            proposed = [delta]
            self.buffer += chunk
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                if line.strip():
                    require(len(self.proposals) < len(self.pins.answer_obligation_ids),
                            "TOO_MANY_CLAIMS")
                    claim = self._emit(
                        "claim_proposed", obligation_id=self.pins.answer_obligation_ids[
                            len(self.proposals)],
                        text_sha256=sha(line.strip().encode()),
                        raw_delta_event_ids=self.delta_refs[:],
                        verification_status="UNVERIFIED_NEVER_PUBLISH",
                        source_release_sha256=self.pins.source_release_sha256,
                        source_manifest_sha256=self.pins.source_manifest_sha256,
                        source_acl_sha256=self.pins.source_acl_sha256,
                        source_rights_epoch=self.pins.source_rights_epoch)
                    self.proposals.append({"text": line.strip(), "wire": claim})
                    self.delta_refs.clear()
                    proposed.append(claim)
            return proposed
        if kind == "provider_done":
            require(self.delta_count > 0 and not self.buffer.strip() and
                    len(self.proposals) == len(self.pins.answer_obligation_ids),
                    "INCOMPLETE_OBLIGATIONS_OR_TAIL")
            usage = wire.get("usage")
            if usage is not None:
                require(type(usage) is dict and set(usage) == {"input_tokens", "output_tokens"} and
                        all(type(v) is int and 0 <= v <= self.pins.max_tokens * 16
                            for v in usage.values()), "UNTRUSTED_USAGE")
                self.provider_usage = usage
                self.usage_observed = True
            self.done = True
            self.done_ns = time.monotonic_ns()
            return [self._emit("provider_done", **ident, provider=self.identity[0],
                               model=self.identity[1], usage=self.provider_usage,
                               usage_observed=self.usage_observed)]
        if kind == "stream_end":
            raise Refused("PROVIDER_DONE_REQUIRED_BEFORE_STREAM_END")
        raise Refused("UNHANDLED_EVENT")

    def finish(self, raw_end: bytes) -> dict:
        require(self.done and not self.ended and not self.failed, "PROVIDER_DONE_REQUIRED")
        try:
            end = json.loads(raw_end)
        except (UnicodeError, ValueError) as exc:
            raise Refused("BAD_STREAM_END") from exc
        require(type(end) is dict and set(end) == {"event", "provider_done"} and
                end["event"] == "stream_end" and end["provider_done"] is True,
                "BAD_STREAM_END")
        self.ended = True
        result = self._emit("stream_end", raw_event_sha256=sha(raw_end),
                            provider=self.identity[0], model=self.identity[1],
                            proposed_claims=len(self.proposals),
                            completed_ms=round((self.done_ns-self.started_ns)/1e6, 3),
                            first_model_delta_ms=round((self.first_delta_ns-self.started_ns)/1e6, 3),
                            provider_usage=self.provider_usage,
                            usage_observed=self.usage_observed,
                            source_byte_verified=False, semantic_issuer_qualified=False,
                            actual_client_ack=False, actual_complete_answer_ms="UNKNOWN",
                            publishable_answer=False)
        return result


def capture_ndjson(raw_events, producer: NativeEventProducer) -> dict:
    """Consumes observed bytes, never initiates remote calls or upgrades origin."""
    count = 0
    try:
        for raw in raw_events:
            count += 1
            require(count <= MAX_EVENTS, "WIRE_EVENT_COUNT")
            data = raw if type(raw) is bytes else b""
            try:
                kind = json.loads(data).get("event")
            except (ValueError, AttributeError):
                kind = None
            if kind == "stream_end":
                return producer.finish(data)
            producer.ingest(data)
        raise Refused("STREAM_END_MISSING")
    except Refused as exc:
        if not producer.failed:
            producer.failed = True
            # Only a fixed refusal category enters the durable journal.
            producer._emit("safe_abstention", error_class=type(exc).__name__,
                           reason="MODEL_STREAM_NOT_ADMITTED",
                           publishable_answer=False)
        raise


def capture_loopback_http(url: str, producer: NativeEventProducer) -> dict:
    """Restricted OS/TCP transport for synthetic local tests, not a provider route."""
    parts = urlsplit(url)
    require(producer.origin_class == SYNTHETIC and parts.scheme == "http" and
            parts.hostname == "127.0.0.1" and parts.username is None and
            parts.password is None and parts.fragment == "" and
            parts.path == "/nonprod/f02/synthetic-wire" and parts.port is not None,
            "LOCAL_SYNTHETIC_TRANSPORT_ONLY")
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise Refused("REDIRECT_FORBIDDEN")
    # No ambient proxy or redirect: the literal loopback origin remains fixed.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, headers={"Accept": "application/x-ndjson"})
    with opener.open(request, timeout=4) as response:
        require(response.status == 200 and
                response.headers.get_content_type() == "application/x-ndjson",
                "UNTRUSTED_HTTP_RESPONSE")
        return capture_ndjson(response, producer)


def live_request_status() -> dict:
    """Do not infer authority from old MiniMax receipts or coding-plan keys."""
    return {"provider_call": "NOT_RUN",
            "fresh_supported_grant": "NOT_PRESENT_IN_THIS_WORKER",
            "cloudflare_primary": "EXPLICIT_EQUIVALENT_REFUSAL_NO_RETRY",
            "mini_max_fallback": "NOT_A_QUALIFIED_PRIMARY",
            "cache": "OFF", "product": "NOT_ADMITTED"}


def has_fresh_verified_origin(receipts, *, independent_grant_verifier=None) -> bool:
    """Legacy SSE booleans do not authenticate new model-produced answer bytes.

    A current admission requires separately attested live provenance AND a
    complete raw-delta causal trace, neither derivable from legacy answer_text.
    This defensive predicate is not itself an issuer or formal Product verifier.
    """
    if not callable(independent_grant_verifier) or type(receipts) is not list:
        return False
    if not receipts or len(receipts) > MAX_EVENTS:
        return False
    try:
        origins = {r["model_origin_class"] for r in receipts}
        if origins != {LIVE}:
            return False
        kinds = [r["event_kind"] for r in receipts]
        if (kinds[0] != "provider_start" or
            kinds[-1] != "stream_end" or
            "provider_done" not in kinds or
            "provider_delta" not in kinds or
            "claim_proposed" not in kinds):
            return False
        if not all(bool(HASH.fullmatch(r["raw_event_sha256"]))
                   for r in receipts if r["event_kind"] in
                   {"provider_start", "provider_delta", "provider_done", "stream_end"}):
            return False
        ids = [r["event_id"] for r in receipts]
        if len(ids) != len(set(ids)):
            return False
        grant = receipts[0]["authenticated_provider_receipt"]
        return independent_grant_verifier(grant) is True
    except (KeyError, TypeError, ValueError):
        return False
