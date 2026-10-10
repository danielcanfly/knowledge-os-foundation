"""Nonmutating AR08 native Q&A byte stream experiment, NOT an M26 route.

AR03 supplies exact bytes/pins through a separately trusted SourceAuthorityPort;
AR05 supplies a proposal through a separately trusted VerificationPort. These
ports are *not* implementations of real identity, source rights or a signer.
The local transport callback proves only in-process enqueue/flush ordering.
No external client ACK or product TTFT is inferred.
"""
from __future__ import annotations

import codecs
import hashlib
from dataclasses import dataclass
from typing import Protocol

VERSION = "AR08NativeQAStream/1.0-test-only"
COMPONENT_PASS = "QA_LOCAL_NONMUTATING_STREAM_COMPONENT_PASS"
PRODUCT_TTFT = "PRODUCT_TTFT_UNVERIFIED"
DELIVERY = "client_delivery_unverified"


class StreamDenied(ValueError):
    """Fail closed with a nonsecret error code."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise StreamDenied(code)


def _text(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise StreamDenied("invalid_utf8_boundary") from exc


def _boundary(raw: bytes, start: int, end: int) -> None:
    _require(0 <= start < end <= len(raw), "span_out_of_bounds")
    _text(raw[:start])
    _text(raw[:end])


@dataclass(frozen=True, slots=True)
class NativeSourceBytes:
    tenant_id: str
    actor_id: str
    source_id: str
    native_citation_id: str
    revision: str
    sha256: str
    original_bytes: bytes
    observation_id: str
    expires_wall_ms: int


@dataclass(frozen=True, slots=True)
class CitationByteSpan:
    native_citation_id: str
    source_id: str
    source_revision: str
    source_sha256: str
    start_byte: int
    end_byte: int
    original_claim_bytes: bytes


@dataclass(frozen=True, slots=True)
class AnswerEvidenceLink:
    """AR05-proposed answer range pinned to an exact native citation span."""

    answer_start: int
    answer_end: int
    citation: CitationByteSpan


@dataclass(frozen=True, slots=True)
class VerificationProposal:
    tenant_id: str
    actor_id: str
    run_id: str
    proof_id: str
    verified_answer_bytes: bytes
    verified_answer_sha256: str
    links: tuple[AnswerEvidenceLink, ...]
    issued_wall_ms: int
    expires_wall_ms: int
    verifier_revision: str


@dataclass(frozen=True, slots=True)
class ClockSample:
    domain: str
    monotonic_ns: int
    wall_ms: int


@dataclass(frozen=True, slots=True)
class VerifiedTextFrame:
    version: str
    run_id: str
    sequence: int
    answer_start_byte: int
    answer_end_byte: int
    data: bytes
    data_sha256: str
    citation_ids: tuple[str, ...]
    proposal_id: str


@dataclass(frozen=True, slots=True)
class StreamSequenceState:
    run_id: str
    status: str
    next_sequence: int
    next_byte_offset: int
    received_input_bytes: int
    first_substantive_sequence: int | None
    terminal_monotonic_ns: int | None
    client_delivery: str = DELIVERY
    product_ttft: str = PRODUCT_TTFT


@dataclass(frozen=True, slots=True)
class SubstantiveFirstAnswerReceipt:
    version: str
    run_id: str
    first_sequence: int
    answer_start_byte: int
    verified_utf8_sha256: str
    enqueued_monotonic_ns: int
    flushed_monotonic_ns: int
    terminal_monotonic_ns: int | None
    server_flush: str = "in_process_transport_callback_only"
    client_delivery: str = DELIVERY
    product_ttft: str = PRODUCT_TTFT


class SourceAuthorityPort(Protocol):
    """Externally bound, independently controlled AR03 authority injection."""

    def assert_current(
        self, sources: tuple[NativeSourceBytes, ...],
        tenant_id: str, actor_id: str, wall_ms: int
    ) -> None: ...


class VerificationPort(Protocol):
    """Independently controlled AR05 proposal validation injection."""

    def assert_current(
        self, proposal: VerificationProposal, wall_ms: int
    ) -> None: ...


class ClockPort(Protocol):
    def sample(self) -> ClockSample: ...


class TransportPort(Protocol):
    """Port is in-process, not an authenticated remote client ACK."""

    def enqueue(self, frame: VerifiedTextFrame) -> None: ...

    def flush(self, sequence: int) -> None: ...


class NativeQATransportAdapter:
    """Fail-closed local verified bytes adapter; owns no native data or rights.

    In-process callbacks may have ambiguous side effects on exceptions; this
    adapter quarantines the stream rather than retries a possibly flushed frame.
    A second channel must independently prove real authenticated delivery.
    """

    def __init__(
        self, *, proposal: VerificationProposal,
        sources: tuple[NativeSourceBytes, ...],
        source_authority: SourceAuthorityPort,
        verification: VerificationPort, transport: TransportPort,
        clock: ClockPort,
    ) -> None:
        self.proposal = proposal
        self.sources = sources
        self.source_authority = source_authority
        self.verification = verification
        self.transport = transport
        self.clock = clock
        self._status = "active"
        self._input = bytearray()
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._frames: list[VerifiedTextFrame] = []
        self._receipt: SubstantiveFirstAnswerReceipt | None = None
        self._last_sample: ClockSample | None = None
        self._terminal_ns: int | None = None
        self.events: list[tuple[str, int, int]] = []
        self._validate_contract()
        self._check_fresh()

    @property
    def state(self) -> StreamSequenceState:
        return StreamSequenceState(
            self.proposal.run_id, self._status, len(self._frames),
            sum(len(frame.data) for frame in self._frames), len(self._input),
            self._receipt.first_sequence if self._receipt else None,
            self._terminal_ns,
        )

    @property
    def frames(self) -> tuple[VerifiedTextFrame, ...]:
        return tuple(self._frames)

    @property
    def first_answer_receipt(self) -> SubstantiveFirstAnswerReceipt | None:
        if self._receipt is None:
            return None
        from dataclasses import replace
        return replace(self._receipt, terminal_monotonic_ns=self._terminal_ns)

    def _sample(self) -> ClockSample:
        stamp = self.clock.sample()
        _require(
            stamp.domain == "monotonic_ns" and
            type(stamp.monotonic_ns) is int and stamp.monotonic_ns >= 0 and
            type(stamp.wall_ms) is int and stamp.wall_ms >= 0,
            "wrong_clock_domain",
        )
        if self._last_sample:
            _require(
                stamp.monotonic_ns >= self._last_sample.monotonic_ns and
                stamp.wall_ms >= self._last_sample.wall_ms,
                "clock_rollback",
            )
        self._last_sample = stamp
        return stamp

    def _validate_contract(self) -> None:
        p = self.proposal
        _require(
            all((p.tenant_id, p.actor_id, p.run_id, p.proof_id,
                 p.verifier_revision)), "missing_identity",
        )
        _require(
            isinstance(p.verified_answer_bytes, bytes) and
            bool(_text(p.verified_answer_bytes).strip()) and
            digest(p.verified_answer_bytes) == p.verified_answer_sha256,
            "invalid_answer_proposal",
        )
        _require(len(self.sources) > 0 and len(p.links) > 0, "missing_citation")
        keys: set[str] = set()
        lookup: dict[str, NativeSourceBytes] = {}
        for source in self.sources:
            _require(
                bool(source.native_citation_id and source.source_id and
                     source.revision and source.observation_id) and
                source.tenant_id == p.tenant_id and
                source.actor_id == p.actor_id, "source_identity_mismatch",
            )
            _require(
                isinstance(source.original_bytes, bytes) and
                digest(source.original_bytes) == source.sha256,
                "source_digest_mismatch",
            )
            _text(source.original_bytes)
            _require(source.native_citation_id not in keys, "duplicate_citation_id")
            keys.add(source.native_citation_id)
            lookup[source.native_citation_id] = source
        covered = bytearray(len(p.verified_answer_bytes))
        for link in p.links:
            _boundary(p.verified_answer_bytes, link.answer_start, link.answer_end)
            pin = link.citation
            src = lookup.get(pin.native_citation_id)
            _require(src is not None, "citation_drift")
            _require(
                pin.source_id == src.source_id and
                pin.source_revision == src.revision and
                pin.source_sha256 == src.sha256, "citation_drift",
            )
            _boundary(src.original_bytes, pin.start_byte, pin.end_byte)
            _require(
                pin.original_claim_bytes ==
                src.original_bytes[pin.start_byte:pin.end_byte] and
                bool(_text(pin.original_claim_bytes).strip()),
                "claim_bytes_mismatch",
            )
            for i in range(link.answer_start, link.answer_end):
                covered[i] = 1
        for i, b in enumerate(p.verified_answer_bytes):
            if b not in b" \t\r\n":
                _require(bool(covered[i]), "unsupported_answer_byte")

    def _check_fresh(self) -> ClockSample:
        stamp = self._sample()
        p = self.proposal
        _require(
            p.issued_wall_ms <= stamp.wall_ms < p.expires_wall_ms,
            "stale_verification_proof",
        )
        for src in self.sources:
            _require(stamp.wall_ms < src.expires_wall_ms, "stale_source")
        self.source_authority.assert_current(
            self.sources, p.tenant_id, p.actor_id, stamp.wall_ms,
        )
        self.verification.assert_current(p, stamp.wall_ms)
        return stamp

    def push(self, fragment: bytes, *, answer_offset: int) -> tuple[VerifiedTextFrame, ...]:
        _require(self._status == "active", "stream_not_active")
        _require(isinstance(fragment, bytes) and bool(fragment), "empty_fragment")
        _require(
            type(answer_offset) is int and answer_offset == len(self._input),
            "replayed_or_gap_fragment",
        )
        p = self.proposal
        _require(
            p.verified_answer_bytes.startswith(bytes(self._input) + fragment),
            "unverified_or_mutated_bytes",
        )
        try:
            complete = self._decoder.decode(fragment, final=False).encode("utf-8")
        except UnicodeError as exc:
            self._status = "quarantined"
            raise StreamDenied("invalid_utf8_fragment") from exc
        self._input.extend(fragment)
        if not complete:
            return ()
        self._check_fresh()
        start = sum(len(f.data) for f in self._frames)
        end = start + len(complete)
        citations = tuple(sorted({
            link.citation.native_citation_id for link in p.links
            if link.answer_start < end and link.answer_end > start
        }))
        _require(bool(citations), "missing_chunk_citation")
        frame = VerifiedTextFrame(
            VERSION, p.run_id, len(self._frames), start, end, complete,
            digest(complete), citations, p.proof_id,
        )
        try:
            stamp = self._sample()
            self.transport.enqueue(frame)
            self.events.append(("enqueue", frame.sequence, stamp.monotonic_ns))
            self._check_fresh()  # revocation may happen *after* enqueue
            self.transport.flush(frame.sequence)
            flushed = self._sample()
            self.events.append(("flush", frame.sequence, flushed.monotonic_ns))
        except Exception:
            self._status = "quarantined"
            raise
        self._frames.append(frame)
        if self._receipt is None and complete.decode("utf-8").strip():
            self._receipt = SubstantiveFirstAnswerReceipt(
                VERSION, p.run_id, frame.sequence, start, frame.data_sha256,
                stamp.monotonic_ns, flushed.monotonic_ns, None,
            )
        return (frame,)

    def terminal(self) -> StreamSequenceState:
        _require(self._status == "active", "stream_not_active")
        self._check_fresh()
        try:
            self._decoder.decode(b"", final=True)
        except UnicodeError as exc:
            self._status = "quarantined"
            raise StreamDenied("incomplete_utf8_at_terminal") from exc
        _require(
            bytes(self._input) == self.proposal.verified_answer_bytes,
            "terminal_before_full_answer",
        )
        _require(
            self._receipt is not None and bool(self._frames),
            "no_substantive_preterminal_text",
        )
        self._terminal_ns = self._sample().monotonic_ns
        _require(
            self._receipt.flushed_monotonic_ns <= self._terminal_ns,
            "terminal_order_violation",
        )
        self._status = "terminal"
        self.events.append(("terminal", len(self._frames), self._terminal_ns))
        return self.state

    def cancel(self) -> StreamSequenceState:
        _require(self._status == "active", "stream_not_active")
        self._status = "cancelled"
        return self.state

    def reconnect(
        self, *, actor_id: str, tenant_id: str, next_sequence: int,
    ) -> tuple[VerifiedTextFrame, ...]:
        _require(
            actor_id == self.proposal.actor_id and
            tenant_id == self.proposal.tenant_id, "reconnect_actor_mismatch",
        )
        _require(self._status == "active", "stream_not_active")
        self._check_fresh()
        _require(
            type(next_sequence) is int and next_sequence == len(self._frames),
            "duplicate_or_future_reconnect",
        )
        return ()  # No replay or fabricated external delivery.

    def accept_client_ack(self, *_args: object, **_kwargs: object) -> None:
        """No external ACK proof available in this component; reject all."""
        raise StreamDenied("unauthenticated_client_ack")
