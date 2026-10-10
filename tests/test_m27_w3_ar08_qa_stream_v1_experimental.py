"""AR08 S08Q local byte-level, adversarial, negative and fault-injection tests.

Trust callbacks and clocks are synthetic test fixtures; none are external authority.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine.m27_w3_ar08_qa_stream_v1_experimental import (
    DELIVERY,
    PRODUCT_TTFT,
    AnswerEvidenceLink,
    CitationByteSpan,
    ClockSample,
    NativeQATransportAdapter,
    NativeSourceBytes,
    StreamDenied,
    VerificationProposal,
    digest,
)

ANSWER = "Alpha βeta\n".encode()
CITATION_ID = "NATIVE:knowledge:001"
SENTINEL = "independent-fixture-only"


class Clock:
    def __init__(self):
        self.domain = "monotonic_ns"
        self.mono = 100
        self.wall = 1000

    def sample(self):
        self.mono += 10
        return ClockSample(self.domain, self.mono, self.wall)


class Authority:
    def __init__(self):
        self.revoked = False
        self.calls = 0

    def assert_current(self, sources, tenant_id, actor_id, wall_ms):
        self.calls += 1
        if self.revoked:
            raise StreamDenied("revoked_by_external_authority_port")
        assert all(s.tenant_id == tenant_id for s in sources)
        assert all(s.actor_id == actor_id for s in sources)
        assert wall_ms >= 0


class Verifier:
    def __init__(self):
        self.revoked = False
        self.calls = 0

    def assert_current(self, proposal, wall_ms):
        self.calls += 1
        if self.revoked:
            raise StreamDenied("ar05_proposal_revoked")
        assert proposal.proof_id == "ar05-proposal-1"
        assert wall_ms >= proposal.issued_wall_ms


class Transport:
    def __init__(self):
        self.events = []
        self.frames = []
        self.on_enqueue = None
        self.on_flush = None
        self.fail_enqueue = False
        self.fail_flush = False

    def enqueue(self, frame):
        self.events.append(("enqueue", frame.sequence))
        if self.on_enqueue:
            self.on_enqueue(frame)
        if self.fail_enqueue:
            raise OSError("enqueue_fault")
        self.frames.append(frame)

    def flush(self, sequence):
        self.events.append(("flush", sequence))
        if self.on_flush:
            self.on_flush(sequence)
        if self.fail_flush:
            raise OSError("flush_fault")


def fixture():
    src = NativeSourceBytes(
        "tenant-A", "actor-A", "source:native:A", CITATION_ID,
        "rev-0x20", digest(ANSWER), ANSWER, "ar03-observation-1", 2000,
    )
    span = CitationByteSpan(
        CITATION_ID, src.source_id, src.revision, src.sha256, 0,
        len(ANSWER), ANSWER,
    )
    link = AnswerEvidenceLink(0, len(ANSWER), span)
    proposal = VerificationProposal(
        "tenant-A", "actor-A", "task-QA-1", "ar05-proposal-1",
        ANSWER, digest(ANSWER), (link,), 900, 2000, "ar05-v1",
    )
    ports = (Authority(), Verifier(), Transport(), Clock())
    return src, proposal, ports


def build(src=None, proposal=None, ports=None):
    original, p, dep = fixture()
    dep = ports or dep
    return NativeQATransportAdapter(
        proposal=proposal or p, sources=(src or original,),
        source_authority=dep[0], verification=dep[1],
        transport=dep[2], clock=dep[3],
    ), dep


def drive(adapter, data=ANSWER):
    offset = 0
    for part in (data[:7], data[7:8], data[8:10], data[10:]):
        if part:
            adapter.push(part, answer_offset=offset)
            offset += len(part)
    return adapter.terminal()


def test_positive_utf8_split_and_preterminal_flush_order():
    adapter, (_, _, transport, _) = build()
    state = drive(adapter)
    assert state.status == "terminal"
    assert b"".join(f.data for f in adapter.frames) == ANSWER
    assert adapter.first_answer_receipt is not None
    receipt = adapter.first_answer_receipt
    assert receipt.flushed_monotonic_ns < state.terminal_monotonic_ns
    assert receipt.enqueued_monotonic_ns <= receipt.flushed_monotonic_ns
    assert state.first_substantive_sequence == 0
    assert all(f.citation_ids == (CITATION_ID,) for f in adapter.frames)
    assert all(f.data.decode("utf-8") for f in adapter.frames)
    assert adapter.events[-1][0] == "terminal"
    assert transport.events == [
        ("enqueue", f.sequence) if j % 2 == 0
        else ("flush", f.sequence)
        for f in adapter.frames for j in (0, 1)
    ]
    assert receipt.client_delivery == DELIVERY
    assert receipt.product_ttft == PRODUCT_TTFT
    assert len(adapter.frames) >= 2


def test_non_substantive_first_flush_does_not_count():
    # Separate proof containing whitespace prefix.
    src, p, ports = fixture()
    data = b"  " + ANSWER
    p = replace(
        p, verified_answer_bytes=data, verified_answer_sha256=digest(data),
        links=(replace(p.links[0], answer_start=0, answer_end=len(data)),),
    )
    a, _ = build(src, p, ports)
    a.push(b"  ", answer_offset=0)
    assert a.first_answer_receipt is None
    a.push(ANSWER, answer_offset=2)
    assert a.first_answer_receipt.first_sequence == 1
    assert a.terminal().status == "terminal"


def test_native_citation_identity_and_exact_claim_byte_span():
    src, p, ports = fixture()
    a, _ = build(src, p, ports)
    frame = a.push(ANSWER, answer_offset=0)[0]
    assert frame.citation_ids == (src.native_citation_id,)
    assert frame.data_sha256 == digest(src.original_bytes)
    assert p.links[0].citation.original_claim_bytes == src.original_bytes


def test_in_process_callbacks_not_client_ack():
    a, (_, _, transport, _) = build()
    assert drive(a).product_ttft == PRODUCT_TTFT
    assert transport.frames
    with pytest.raises(StreamDenied, match="unauthenticated_client_ack"):
        a.accept_client_ack({"actor": "actor-A", "verified": True})
    assert a.state.client_delivery == DELIVERY


def test_empty_no_progress_frame():
    a, (_, _, transport, _) = build()
    with pytest.raises(StreamDenied, match="empty_fragment"):
        a.push(b"", answer_offset=0)
    assert transport.events == []


def test_terminal_without_substantive_preterminal_emission():
    a, _ = build()
    with pytest.raises(StreamDenied, match="terminal_before_full_answer"):
        a.terminal()


def test_text_after_terminal_is_rejected():
    a, _ = build()
    drive(a)
    with pytest.raises(StreamDenied, match="stream_not_active"):
        a.push(b"more", answer_offset=len(ANSWER))


def test_double_terminal_blocked():
    a, _ = build()
    drive(a)
    with pytest.raises(StreamDenied, match="stream_not_active"):
        a.terminal()


def test_cancel_forbids_stream_and_reconnect():
    a, _ = build()
    assert a.cancel().status == "cancelled"
    with pytest.raises(StreamDenied, match="stream_not_active"):
        a.push(b"A", answer_offset=0)
    with pytest.raises(StreamDenied, match="stream_not_active"):
        a.reconnect(actor_id="actor-A", tenant_id="tenant-A", next_sequence=0)


def test_cancel_after_partial_unicode_discards_without_flush():
    a, (_, _, transport, _) = build()
    a.push(ANSWER[:6], answer_offset=0)
    before = len(transport.frames)
    a.push(ANSWER[6:7], answer_offset=6)
    assert len(transport.frames) == before
    assert a.cancel().status == "cancelled"
    assert len(transport.frames) == before


@pytest.mark.parametrize(("mutation", "code"), [
    (lambda s: replace(s, original_bytes=b"attacker"), "source_digest_mismatch"),
    (lambda s: replace(s, sha256="0" * 64), "source_digest_mismatch"),
    (lambda s: replace(s, source_id=""), "source_identity_mismatch"),
    (lambda s: replace(s, native_citation_id=""), "source_identity_mismatch"),
    (lambda s: replace(s, revision=""), "source_identity_mismatch"),
    (lambda s: replace(s, observation_id=""), "source_identity_mismatch"),
    (lambda s: replace(s, tenant_id="other"), "source_identity_mismatch"),
    (lambda s: replace(s, actor_id="other"), "source_identity_mismatch"),
    (lambda s: replace(s, original_bytes=b"\xff",
                       sha256=digest(b"\xff")), "invalid_utf8_boundary"),
])
def test_bad_native_source(mutation, code):
    src, p, ports = fixture()
    with pytest.raises(StreamDenied, match=code):
        build(mutation(src), p, ports)


@pytest.mark.parametrize(("mutation", "code"), [
    (lambda p: replace(p, tenant_id=""), "missing_identity"),
    (lambda p: replace(p, actor_id=""), "missing_identity"),
    (lambda p: replace(p, run_id=""), "missing_identity"),
    (lambda p: replace(p, proof_id=""), "missing_identity"),
    (lambda p: replace(p, verifier_revision=""), "missing_identity"),
    (lambda p: replace(p, verified_answer_sha256="f" * 64),
     "invalid_answer_proposal"),
    (lambda p: replace(p, verified_answer_bytes=b"  ",
                       verified_answer_sha256=digest(b"  ")),
     "invalid_answer_proposal"),
    (lambda p: replace(p, verified_answer_bytes=b"\xff",
                       verified_answer_sha256=digest(b"\xff")),
     "invalid_utf8_boundary"),
    (lambda p: replace(p, links=()), "missing_citation"),
    (lambda p: replace(p, links=(replace(
        p.links[0], answer_end=4),)), "unsupported_answer_byte"),
    (lambda p: replace(p, links=(replace(
        p.links[0], answer_end=len(ANSWER) + 1),)), "span_out_of_bounds"),
    (lambda p: replace(p, links=(replace(
        p.links[0], answer_start=2, answer_end=3),)),
     "unsupported_answer_byte"),
])
def test_bad_ar05_proposal(mutation, code):
    src, p, ports = fixture()
    with pytest.raises(StreamDenied, match=code):
        build(src, mutation(p), ports)


@pytest.mark.parametrize(("mutation", "code"), [
    (lambda c: replace(c, native_citation_id="substituted"), "citation_drift"),
    (lambda c: replace(c, source_id="substituted"), "citation_drift"),
    (lambda c: replace(c, source_revision="stale"), "citation_drift"),
    (lambda c: replace(c, source_sha256="0" * 64), "citation_drift"),
    (lambda c: replace(c, start_byte=-1), "span_out_of_bounds"),
    (lambda c: replace(c, end_byte=len(ANSWER) + 1), "span_out_of_bounds"),
    (lambda c: replace(c, start_byte=7), "invalid_utf8_boundary"),
    (lambda c: replace(c, original_claim_bytes=b"forged"), "claim_bytes_mismatch"),
    (lambda c: replace(c, original_claim_bytes=b""), "claim_bytes_mismatch"),
])
def test_citation_drift_and_claim_byte_faults(mutation, code):
    src, p, ports = fixture()
    link = p.links[0]
    p = replace(p, links=(replace(link, citation=mutation(link.citation)),))
    with pytest.raises(StreamDenied, match=code):
        build(src, p, ports)


@pytest.mark.parametrize(("method", "offset", "data", "code"), [
    ("push", -1, b"A", "replayed_or_gap_fragment"),
    ("push", 1, b"A", "replayed_or_gap_fragment"),
    ("push", 0, b"Z", "unverified_or_mutated_bytes"),
    ("push", 0, ANSWER + b"Z", "unverified_or_mutated_bytes"),
    ("push", 0, b"\xff", "unverified_or_mutated_bytes"),
    ("push", True, b"A", "replayed_or_gap_fragment"),
])
def test_invalid_fragment_and_offset(method, offset, data, code):
    a, _ = build()
    assert method == "push"
    with pytest.raises(StreamDenied, match=code):
        a.push(data, answer_offset=offset)


def test_replayed_initial_byte_offset_detected():
    a, _ = build()
    a.push(b"A", answer_offset=0)
    with pytest.raises(StreamDenied, match="replayed_or_gap_fragment"):
        a.push(b"A", answer_offset=0)


@pytest.mark.parametrize(("actor", "tenant", "cursor", "code"), [
    ("attacker", "tenant-A", 0, "reconnect_actor_mismatch"),
    ("actor-A", "different", 0, "reconnect_actor_mismatch"),
    ("actor-A", "tenant-A", -1, "duplicate_or_future_reconnect"),
    ("actor-A", "tenant-A", 1, "duplicate_or_future_reconnect"),
    ("actor-A", "tenant-A", True, "duplicate_or_future_reconnect"),
])
def test_reconnect_rejects_identity_gap_and_duplicate(actor, tenant, cursor, code):
    a, _ = build()
    with pytest.raises(StreamDenied, match=code):
        a.reconnect(actor_id=actor, tenant_id=tenant, next_sequence=cursor)


def test_reconnect_idempotent_cursor_never_reemits_frames():
    a, (_, _, transport, _) = build()
    a.push(ANSWER, answer_offset=0)
    previous = list(transport.events)
    assert a.reconnect(
        actor_id="actor-A", tenant_id="tenant-A", next_sequence=1
    ) == ()
    assert transport.events == previous
    with pytest.raises(StreamDenied, match="duplicate_or_future_reconnect"):
        a.reconnect(actor_id="actor-A", tenant_id="tenant-A", next_sequence=0)


def test_revocation_before_prepared_stream():
    src, p, ports = fixture()
    ports[0].revoked = True
    with pytest.raises(StreamDenied, match="revoked_by_external_authority_port"):
        build(src, p, ports)


def test_revocation_after_prepare_before_first_flush():
    a, (auth, _, transport, _) = build()
    transport.on_enqueue = lambda _: setattr(auth, "revoked", True)
    with pytest.raises(StreamDenied, match="revoked_by_external_authority_port"):
        a.push(ANSWER, answer_offset=0)
    assert a.state.status == "quarantined"
    assert transport.events == [("enqueue", 0)]
    assert not a.frames


def test_ar05_revocation_after_prepare():
    a, (_, verifier, transport, _) = build()
    transport.on_enqueue = lambda _: setattr(verifier, "revoked", True)
    with pytest.raises(StreamDenied, match="ar05_proposal_revoked"):
        a.push(ANSWER, answer_offset=0)
    assert a.state.status == "quarantined"


@pytest.mark.parametrize(("port", "fault"), [
    ("enqueue", "enqueue_fault"),
    ("flush", "flush_fault"),
])
def test_callback_fault_injection_quarantines_no_resend(port, fault):
    a, (_, _, transport, _) = build()
    setattr(transport, "fail_" + port, True)
    with pytest.raises(OSError, match=fault):
        a.push(ANSWER, answer_offset=0)
    assert a.state.status == "quarantined"
    assert not a.frames
    with pytest.raises(StreamDenied, match="stream_not_active"):
        a.push(ANSWER, answer_offset=0)


def test_stale_proof_on_prepare():
    src, p, ports = fixture()
    p = replace(p, expires_wall_ms=1000)
    with pytest.raises(StreamDenied, match="stale_verification_proof"):
        build(src, p, ports)


def test_stale_proof_after_prepare():
    a, (_, _, _, clock) = build()
    clock.wall = 2000
    with pytest.raises(StreamDenied, match="stale_verification_proof"):
        a.push(ANSWER, answer_offset=0)


def test_revoked_native_source_expiry():
    src, p, ports = fixture()
    src = replace(src, expires_wall_ms=1000)
    with pytest.raises(StreamDenied, match="stale_source"):
        build(src, p, ports)


def test_stale_native_source_after_prepare():
    a, (_, _, _, clock) = build()
    clock.wall = 2000
    with pytest.raises(StreamDenied, match="stale_source|stale_verification_proof"):
        a.push(ANSWER, answer_offset=0)


def test_wrong_clock_domain_rejected():
    src, p, ports = fixture()
    ports[3].domain = "wall_clock"
    with pytest.raises(StreamDenied, match="wrong_clock_domain"):
        build(src, p, ports)


def test_clock_rollback_rejected():
    a, (_, _, _, clock) = build()
    clock.wall = 999
    with pytest.raises(StreamDenied, match="clock_rollback"):
        a.push(ANSWER, answer_offset=0)


def test_substantive_receipt_not_client_ack_and_no_523_claim():
    a, _ = build()
    drive(a)
    r = a.first_answer_receipt
    assert r.version.startswith("AR08NativeQAStream/")
    assert r.server_flush == "in_process_transport_callback_only"
    assert r.client_delivery == DELIVERY
    assert r.product_ttft == PRODUCT_TTFT
    assert "523" not in repr(r)
    assert r.server_flush != SENTINEL


def test_citation_range_binds_multibyte_answer_claim():
    src, p, ports = fixture()
    link = p.links[0]
    p = replace(
        p, links=(
            replace(link, answer_start=0, answer_end=6),
            replace(link, answer_start=6, answer_end=len(ANSWER)),
        ),
    )
    a, _ = build(src, p, ports)
    assert drive(a).status == "terminal"


def test_partial_utf8_terminal_rejected_without_fake_success():
    a, _ = build()
    a.push(ANSWER[:7], answer_offset=0)  # first byte of β left pending
    with pytest.raises(StreamDenied, match="incomplete_utf8_at_terminal"):
        a.terminal()
    assert a.state.status == "quarantined"


def test_duplicate_native_id_rejected():
    src, p, ports = fixture()
    with pytest.raises(StreamDenied, match="duplicate_citation_id"):
        NativeQATransportAdapter(
            proposal=p, sources=(src, src), source_authority=ports[0],
            verification=ports[1], transport=ports[2], clock=ports[3],
        )
