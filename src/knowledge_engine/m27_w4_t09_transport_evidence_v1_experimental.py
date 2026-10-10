"""Feature-off W4 T09 transport evidence *sidecar*, never a production hook.

Events are assertions supplied by an observer, not proof that a client received
bytes. A caller cannot upgrade fixture observations to live product telemetry.
No network/Provider/IdP access; no modification to native M26 or S08Q routes.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Literal, Protocol

VERSION = "W4T09/1.0-local"
LOCAL_PASS = "LOCAL_EVENT_VALIDATOR_PASS"
CLIENT_UNAVAILABLE = "REAL_CLIENT_ACK_UNAVAILABLE"
PRODUCT_TTFT = "PRODUCT_TTFT_UNVERIFIED"
PRODUCT_P95 = "PRODUCT_P95_UNVERIFIED"

FIRST = "verified_substantive_utf8_first_byte_sent"
CITED = "first_cited_segment_sent"
REQUEST = "request_received"
VERIFIED = "evidence_verified"
TERMINAL = "terminal"
CLIENT = "client_received"
DIAGNOSTIC = frozenset({
    "server_enqueued", "server_write", "server_flush",
    "first_progress_emitted", "first_material", "verified_claim_ready",
    "cited_segment_ready", "final_answer_done",
})
KINDS = DIAGNOSTIC | {FIRST, CITED, REQUEST, VERIFIED, TERMINAL, CLIENT}
SHA64 = re.compile(r"^[0-9a-f]{64}$")
COMMIT40 = re.compile(r"^[0-9a-f]{40}$")


class EvidenceDenied(ValueError):
    """Stable non-sensitive refusal code."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise EvidenceDenied(code)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha_ok(value: object) -> bool:
    return isinstance(value, str) and SHA64.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class Candidate:
    """Immutable declared identity; independently obtained build proof is optional."""

    source_commit: str
    tree_sha256: str
    image_digest: str | None
    build_attestation_sha256: str | None
    runner_sha256: str
    instrumentation_sha256: str
    dataset_sha256: str
    source_manifest_sha256: str
    request_id: str
    run_id: str
    trace_id: str
    task_id: str
    durable_task_head: str
    tenant_id: str
    actor_id: str
    mode: Literal["fixture", "externally_observed"] = "fixture"


@dataclass(frozen=True, slots=True)
class SourcePin:
    citation_id: str
    source_id: str
    revision: str
    sha256: str
    tenant_id: str
    actor_id: str
    rights_issued_wall_ms: int
    rights_expires_wall_ms: int
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class ClockSample:
    domain: str
    monotonic_ns: int
    wall_ms: int


@dataclass(frozen=True, slots=True)
class CalibratedAnchor:
    """Signed/external calibration must be verified outside this local module."""

    domain: str
    monotonic_anchor_ns: int
    shared_anchor_ns: int
    uncertainty_ns: int


@dataclass(frozen=True, slots=True)
class ClientProof:
    """Opaque external receipt; never trust an unauthenticated claimed flag."""

    client_id: str
    issuer_id: str
    request_id: str
    trace_id: str
    tenant_id: str
    actor_id: str
    frame_id: str
    frame_sha256: str
    receipt_nonce: str
    signature: str
    fixture: bool = True


@dataclass(frozen=True, slots=True)
class TransportEvent:
    event_id: str
    sequence: int
    kind: str
    stamp: ClockSample
    request_id: str
    trace_id: str
    tenant_id: str
    actor_id: str
    boundary: str = "observation"
    frame_id: str = ""
    frame_bytes: bytes = b""
    frame_sha256: str = ""
    start_byte: int = 0
    end_byte: int = 0
    citation_ids: tuple[str, ...] = ()
    # Each frame binds native citation -> source ID, revision, immutable digest.
    source_bindings: tuple[tuple[str, str, str, str], ...] = ()
    verifier_receipt_id: str = ""
    terminal_kind: str = ""
    abstention_reason: str = ""
    client_proof: ClientProof | None = None


@dataclass(frozen=True, slots=True)
class Capture:
    candidate: Candidate
    sources: tuple[SourcePin, ...]
    verifier_receipt_id: str
    verified_answer_bytes: bytes
    verified_answer_sha256: str
    events: tuple[TransportEvent, ...]
    anchors: tuple[CalibratedAnchor, ...] = ()


@dataclass(frozen=True, slots=True)
class StreamVerdict:
    status: str
    delivery: str
    product_ttft: str
    first_server_text_ms: float | None
    first_cited_ms: float | None
    final_request_ms: float | None
    eligible_answer: bool
    client_ack_class: str
    event_count: int


class ExternalClientVerifier(Protocol):
    """Implement independently; an in-process callback is never external proof."""

    def verify(self, proof: ClientProof) -> bool: ...


def _identity(candidate: Candidate) -> None:
    require(bool(COMMIT40.fullmatch(candidate.source_commit)), "INVALID_COMMIT")
    for value in (
        candidate.tree_sha256, candidate.runner_sha256,
        candidate.instrumentation_sha256, candidate.dataset_sha256,
        candidate.source_manifest_sha256,
    ):
        require(sha_ok(value), "INVALID_PROVENANCE_SHA")
    if candidate.image_digest is not None:
        require(candidate.image_digest.startswith("sha256:") and
                sha_ok(candidate.image_digest[7:]), "MUTABLE_OR_INVALID_IMAGE")
    if candidate.build_attestation_sha256 is not None:
        require(sha_ok(candidate.build_attestation_sha256), "INVALID_ATTESTATION")
        require(candidate.image_digest is not None, "ATTESTATION_WITHOUT_IMAGE")
    require(all(isinstance(value, str) and value.strip() for value in (
        candidate.request_id, candidate.run_id, candidate.trace_id,
        candidate.task_id, candidate.durable_task_head,
        candidate.tenant_id, candidate.actor_id,
    )), "MISSING_TASK_OR_TRACE")
    require(candidate.mode in ("fixture", "externally_observed"), "BAD_MODE")


def _clock(events: tuple[TransportEvent, ...],
           anchors: tuple[CalibratedAnchor, ...]) -> list[int]:
    domains = {event.stamp.domain for event in events}
    if len(domains) == 1:
        return [e.stamp.monotonic_ns for e in events]
    calibrated = {anchor.domain: anchor for anchor in anchors}
    require(len(calibrated) == len(anchors) and domains <= calibrated.keys(),
            "UNCALIBRATED_CLOCK_DOMAINS")
    for anchor in anchors:
        require(anchor.uncertainty_ns >= 0 and
                anchor.uncertainty_ns <= 100_000_000 and
                anchor.monotonic_anchor_ns >= 0 and
                anchor.shared_anchor_ns >= 0, "INVALID_CLOCK_CALIBRATION")
    aligned = [
        calibrated[e.stamp.domain].shared_anchor_ns +
        e.stamp.monotonic_ns - calibrated[e.stamp.domain].monotonic_anchor_ns
        for e in events
    ]
    for before, after, left, right in zip(
        events, events[1:], aligned, aligned[1:], strict=False
    ):
        if before.stamp.domain != after.stamp.domain:
            # Worst-case intervals must not overlap; no uncalibrated subtraction.
            require(left + calibrated[before.stamp.domain].uncertainty_ns <=
                    right - calibrated[after.stamp.domain].uncertainty_ns,
                    "CLOCK_UNCERTAINTY_OVERLAP")
    return aligned


def _pin_check(pin: SourcePin, c: Candidate, wall_ms: int) -> None:
    require(pin.tenant_id == c.tenant_id and
            pin.actor_id == c.actor_id, "WRONG_SOURCE_PRINCIPAL")
    require(bool(pin.citation_id and pin.source_id and pin.revision) and
            sha_ok(pin.sha256), "INVALID_SOURCE_PIN")
    require(type(pin.rights_issued_wall_ms) is int and
            type(pin.rights_expires_wall_ms) is int and
            pin.rights_issued_wall_ms <= wall_ms <
            pin.rights_expires_wall_ms and not pin.revoked, "STALE_SOURCE_RIGHTS")


def validate(capture: Capture, *,
             external_client_verifier: ExternalClientVerifier | None = None,
             external_provenance_verified: bool = False) -> StreamVerdict:
    """Check integrity and ordering; never certify live TTFT/client provenance.

    external_provenance_verified is advisory only: a caller's assertion alone
    cannot turn a local validation into product measurement.
    """
    del external_provenance_verified
    c = capture.candidate
    _identity(c)
    require(bool(capture.verifier_receipt_id), "MISSING_VERIFIER_RECEIPT")
    require(isinstance(capture.verified_answer_bytes, bytes) and
            sha(capture.verified_answer_bytes) ==
            capture.verified_answer_sha256, "ANSWER_DIGEST_MISMATCH")
    try:
        capture.verified_answer_bytes.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise EvidenceDenied("INVALID_ANSWER_UTF8") from exc
    require(bool(capture.events), "MISSING_EVENTS")
    events = capture.events
    require(len({p.citation_id for p in capture.sources}) ==
            len(capture.sources), "DUPLICATE_CITATION_PIN")
    sources = {p.citation_id: p for p in capture.sources}
    require(len({e.event_id for e in events}) == len(events),
            "REPLAYED_EVENT_ID")
    for index, e in enumerate(events, start=1):
        require(e.kind in KINDS, "UNKNOWN_EVENT_KIND")
        require(e.sequence == index and bool(e.event_id), "OUT_OF_ORDER_SEQUENCE")
        require(e.request_id == c.request_id and e.trace_id == c.trace_id and
                e.tenant_id == c.tenant_id and e.actor_id == c.actor_id,
                "WRONG_EVENT_PRINCIPAL")
        require(bool(e.stamp.domain) and
                type(e.stamp.monotonic_ns) is int and
                e.stamp.monotonic_ns >= 0 and
                type(e.stamp.wall_ms) is int and e.stamp.wall_ms >= 0,
                "INVALID_CLOCK_SAMPLE")
    timeline = _clock(events, capture.anchors)
    require(all(a <= b for a, b in zip(timeline, timeline[1:], strict=False)),
            "NONMONOTONIC_STREAM")
    require(all(e.stamp.monotonic_ns <= later.stamp.monotonic_ns for e, later
                in zip(events, events[1:], strict=False)
                if e.stamp.domain == later.stamp.domain),
            "CLOCK_ROLLBACK")
    kinds = [e.kind for e in events]
    for required in (REQUEST, VERIFIED, TERMINAL):
        require(kinds.count(required) == 1, "MISSING_OR_DUPLICATE_STAGE")
    require(kinds[0] == REQUEST, "REQUEST_NOT_FIRST")
    ri, vi, ti = (kinds.index(k) for k in (REQUEST, VERIFIED, TERMINAL))
    require(ri < vi < ti, "VERIFICATION_ORDER")
    require(events[vi].verifier_receipt_id == capture.verifier_receipt_id,
            "VERIFIER_RECEIPT_MISMATCH")
    terminal = events[ti]
    require(terminal.terminal_kind in ("answer", "safe_abstention"),
            "INVALID_TERMINAL")
    require(all(e.kind == CLIENT for e in events[ti + 1:]),
            "SERVER_EVENT_AFTER_TERMINAL")
    require(kinds.count(CLIENT) <= 1, "DUPLICATE_CLIENT_ACK")
    is_answer = terminal.terminal_kind == "answer"
    first_i = kinds.index(FIRST) if FIRST in kinds else None
    cited_i = kinds.index(CITED) if CITED in kinds else None
    if is_answer:
        require(kinds.count(FIRST) == 1 and kinds.count(CITED) == 1,
                "NO_VERIFIED_PRETERMINAL_TEXT")
        assert first_i is not None and cited_i is not None
        require(vi < first_i < cited_i < ti, "FIRST_TEXT_CITATION_ORDER")
        require(timeline[first_i] < timeline[ti] and
                timeline[cited_i] < timeline[ti], "TEXT_NOT_PRETERMINAL")
        require(bool(capture.verified_answer_bytes.strip()) and
                not terminal.abstention_reason, "EMPTY_ANSWER")
    else:
        require(terminal.abstention_reason != "" and
                not capture.verified_answer_bytes and
                first_i is None and cited_i is None and
                CLIENT not in kinds, "INVALID_SAFE_ABSTENTION")
    # No progress/event-name/queue-only signals qualify as answer bytes.
    assembled = bytearray()
    written_frames: dict[str, str] = {}
    for e in events:
        if e.kind not in (FIRST, CITED):
            require(not e.frame_bytes and not e.frame_sha256 and
                    not e.source_bindings and
                    e.start_byte == 0 and e.end_byte == 0,
                    "NON_FRAME_CLAIMS_PAYLOAD")
            continue
        require(e.boundary in ("server_write_observed", "server_flush_observed"),
                "UNOBSERVED_TRANSPORT_WRITE")
        require(e.verifier_receipt_id == capture.verifier_receipt_id,
                "FRAME_NOT_VERIFIED")
        require(bool(e.frame_id) and e.frame_id not in written_frames,
                "FRAME_REPLAY")
        require(isinstance(e.frame_bytes, bytes) and bool(e.frame_bytes) and
                sha(e.frame_bytes) == e.frame_sha256, "FRAME_SHA_MISMATCH")
        try:
            decoded = e.frame_bytes.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise EvidenceDenied("SPLIT_UTF8_FRAME") from exc
        require(bool(decoded.strip()), "WHITESPACE_OR_EMPTY_FRAME")
        require(type(e.start_byte) is int and type(e.end_byte) is int and
                e.start_byte == len(assembled) and
                e.end_byte == e.start_byte + len(e.frame_bytes),
                "FRAME_OFFSET_REPLAY_OR_GAP")
        require(bool(e.citation_ids) and
                len(set(e.citation_ids)) == len(e.citation_ids),
                "MISSING_CITATION_IDS")
        require(len(e.source_bindings) == len(e.citation_ids) and
                {row[0] for row in e.source_bindings} == set(e.citation_ids),
                "MISSING_SOURCE_BINDING")
        for cid, sid, revision, digest in e.source_bindings:
            require(cid in sources, "UNSUPPORTED_CITATION")
            pinned = sources[cid]
            require((sid, revision, digest) ==
                    (pinned.source_id, pinned.revision, pinned.sha256),
                    "SOURCE_REVISION_DIGEST_DRIFT")
            _pin_check(pinned, c, e.stamp.wall_ms)
        require(e.stamp.wall_ms >= events[vi].stamp.wall_ms,
                "FRAME_BEFORE_VERIFICATION_WALL")
        assembled.extend(e.frame_bytes)
        written_frames[e.frame_id] = e.frame_sha256
    if is_answer:
        for pinned in sources.values():
            _pin_check(pinned, c, terminal.stamp.wall_ms)
        require(bytes(assembled) == capture.verified_answer_bytes,
                "ANSWER_BYTES_NOT_COMPLETE")
    client_class = CLIENT_UNAVAILABLE
    if CLIENT in kinds:
        ci = kinds.index(CLIENT)
        e = events[ci]
        p = e.client_proof
        require(first_i is not None and ci > first_i and
                timeline[ci] >= timeline[first_i], "ACK_BEFORE_FIRST_BYTE")
        require(p is not None and external_client_verifier is not None,
                "UNAUTHENTICATED_CLIENT_ACK")
        require(bool(p.client_id and p.issuer_id and p.receipt_nonce and
                     p.signature), "INCOMPLETE_CLIENT_ACK")
        require(p.frame_id == events[first_i].frame_id and
                p.frame_sha256 == written_frames[p.frame_id] and
                p.request_id == c.request_id and p.trace_id == c.trace_id and
                p.tenant_id == c.tenant_id and p.actor_id == c.actor_id,
                "ACK_WRONG_FRAME_OR_IDENTITY")
        require(external_client_verifier.verify(p), "ACK_SIGNATURE_REJECTED")
        # A fake fixture verifier can test schema but never certify real delivery.
        client_class = "FIXTURE_ACK_ONLY" if p.fixture else "ACK_AUTHORITY_NOT_CERTIFIED"
    # Compare only same-domain measurements; calibrated durations are not
    # release-authoritative even when order can be structurally checked.
    def local_ms(i: int) -> float | None:
        if events[i].stamp.domain != events[ri].stamp.domain:
            return None
        return (events[i].stamp.monotonic_ns -
                events[ri].stamp.monotonic_ns) / 1_000_000

    return StreamVerdict(
        LOCAL_PASS, CLIENT_UNAVAILABLE, PRODUCT_TTFT,
        local_ms(first_i) if first_i is not None else None,
        local_ms(cited_i) if cited_i is not None else None,
        local_ms(ti), is_answer, client_class, len(events),
    )


class ClockPort(Protocol):
    def sample(self) -> ClockSample: ...


class CaptureAdapter:
    """Read-only recorder. Has no method to fabricate authenticated client ACK."""

    def __init__(self, candidate: Candidate, clock: ClockPort) -> None:
        self.candidate = candidate
        self.clock = clock
        self.events: list[TransportEvent] = []

    def observe(self, kind: str, *, boundary: str = "observation",
                frame_id: str = "", frame_bytes: bytes = b"",
                citation_ids: tuple[str, ...] = (),
                source_bindings: tuple[tuple[str, str, str, str], ...] = (),
                verifier_receipt_id: str = "",
                terminal_kind: str = "",
                abstention_reason: str = "") -> TransportEvent:
        require(kind != CLIENT and kind in KINDS, "CLIENT_ACK_REQUIRES_EXTERNAL_PORT")
        sample = self.clock.sample()
        start = sum(len(e.frame_bytes) for e in self.events if
                    e.kind in (FIRST, CITED))
        event = TransportEvent(
            event_id=f"{self.candidate.run_id}:{len(self.events) + 1}",
            sequence=len(self.events) + 1, kind=kind, stamp=sample,
            request_id=self.candidate.request_id, trace_id=self.candidate.trace_id,
            tenant_id=self.candidate.tenant_id, actor_id=self.candidate.actor_id,
            boundary=boundary, frame_id=frame_id, frame_bytes=frame_bytes,
            frame_sha256=sha(frame_bytes) if frame_bytes else "",
            start_byte=start if frame_bytes else 0,
            end_byte=start + len(frame_bytes) if frame_bytes else 0,
            citation_ids=citation_ids, source_bindings=source_bindings,
            verifier_receipt_id=verifier_receipt_id,
            terminal_kind=terminal_kind, abstention_reason=abstention_reason,
        )
        self.events.append(event)
        return event


@dataclass(frozen=True, slots=True)
class DurationCase:
    case_id: str
    request_id: str
    eligible: bool
    status: Literal["completed", "timeout", "missing", "safe_abstention"]
    authoritative_final_request_ms: float | None


@dataclass(frozen=True, slots=True)
class DurationVerdict:
    total: int
    eligible: int
    completed: int
    timeout: int
    missing: int
    safe_abstention: int
    nearest_rank_p95_ms: float | None
    synthetic_diagnostic_within_15s: bool
    product_p95: str = PRODUCT_P95


def duration_denominator(cases: tuple[DurationCase, ...], *,
                         diagnostic_fixture: bool = True) -> DurationVerdict:
    """Nearest-rank diagnostic, with no silent dropped timeout/unknown cases.

    Never labels caller-provided numerics as independently certified product p95.
    """
    require(bool(cases), "NO_DURATION_MANIFEST")
    require(len({c.case_id for c in cases}) == len(cases) and
            len({c.request_id for c in cases}) == len(cases),
            "DUPLICATE_DURATION_CASE")
    require(all(c.case_id and c.request_id for c in cases), "MISSING_CASE_ID")
    completed: list[float] = []
    timeout = missing = safe = eligible = 0
    for c in cases:
        require(c.status in ("completed", "timeout", "missing", "safe_abstention"),
                "INVALID_DURATION_STATUS")
        eligible += int(c.eligible)
        if c.status == "completed":
            v = c.authoritative_final_request_ms
            require(c.eligible and type(v) in (float, int) and
                    math.isfinite(v) and v >= 0, "INVALID_FINAL_DURATION")
            completed.append(float(v))
        else:
            require(c.authoritative_final_request_ms is None,
                    "UNTRUSTED_NONCOMPLETION_DURATION")
            timeout += int(c.status == "timeout")
            missing += int(c.status == "missing")
            safe += int(c.status == "safe_abstention")
    # Noncompletion is retained in the manifest; p95 fails closed rather than
    # shaving the failed tail. Abstentions also remain in SLO denominator.
    full = len(completed) == len(cases)
    p95 = sorted(completed)[math.ceil(.95 * len(completed)) - 1] if full else None
    return DurationVerdict(
        len(cases), eligible, len(completed), timeout, missing, safe, p95,
        bool(diagnostic_fixture and p95 is not None and p95 <= 15000),
    )
