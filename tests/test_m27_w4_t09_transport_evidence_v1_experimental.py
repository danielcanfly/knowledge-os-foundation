"""W4 T09 adversarial *local fixture* receipts, not production telemetry."""
from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine import m27_w4_t09_transport_evidence_v1_experimental as t


def h(s: str) -> str:
    return t.sha(s.encode())


ANSWER = "Source β answer".encode()
FIRST_BYTES = b"Source "
LAST_BYTES = "β answer".encode()


def candidate(**kwargs: object) -> t.Candidate:
    c = t.Candidate(
        source_commit="a" * 40, tree_sha256=h("tree"),
        image_digest="sha256:" + h("image"),
        build_attestation_sha256=h("build"),
        runner_sha256=h("runner"), instrumentation_sha256=h("instrumentation"),
        dataset_sha256=h("dataset"), source_manifest_sha256=h("manifest"),
        request_id="request-1", run_id="run-1", trace_id="trace-1",
        task_id="task-1", durable_task_head="epoch:42:tail-sha",
        tenant_id="tenant-1", actor_id="actor-1",
    )
    return replace(c, **kwargs)


def event(kind: str, index: int, *, wall_ms: int | None = None,
          domain: str = "host-a", ns: int | None = None,
          **kwargs: object) -> t.TransportEvent:
    e = t.TransportEvent(
        event_id=f"event-{index}", sequence=index, kind=kind,
        stamp=t.ClockSample(domain, 1_000_000_000 + index * 100_000_000
                            if ns is None else ns,
                            1000 + index * 100 if wall_ms is None else wall_ms),
        request_id="request-1", trace_id="trace-1",
        tenant_id="tenant-1", actor_id="actor-1",
    )
    return replace(e, **kwargs)


def pin(**kwargs: object) -> t.SourcePin:
    p = t.SourcePin("cite-1", "source-1", "revision-1", h("native"),
                    "tenant-1", "actor-1", 900, 4000)
    return replace(p, **kwargs)


def good_capture() -> t.Capture:
    stages = (
        event(t.REQUEST, 1),
        event(t.VERIFIED, 2, verifier_receipt_id="verify-1"),
        event(t.FIRST, 3, boundary="server_flush_observed", frame_id="frame-1",
              frame_bytes=FIRST_BYTES, frame_sha256=t.sha(FIRST_BYTES),
              start_byte=0, end_byte=len(FIRST_BYTES),
              citation_ids=("cite-1",),
              source_bindings=(("cite-1", "source-1", "revision-1", h("native")),),
              verifier_receipt_id="verify-1"),
        event(t.CITED, 4, boundary="server_write_observed", frame_id="frame-2",
              frame_bytes=LAST_BYTES, frame_sha256=t.sha(LAST_BYTES),
              start_byte=len(FIRST_BYTES), end_byte=len(ANSWER),
              citation_ids=("cite-1",),
              source_bindings=(("cite-1", "source-1", "revision-1", h("native")),),
              verifier_receipt_id="verify-1"),
        event(t.TERMINAL, 5, terminal_kind="answer"),
    )
    return t.Capture(candidate(), (pin(),), "verify-1", ANSWER, t.sha(ANSWER),
                     stages)


def evt(c: t.Capture, index: int, **updates: object) -> t.Capture:
    seq = list(c.events)
    seq[index] = replace(seq[index], **updates)
    return replace(c, events=tuple(seq))


def patch(c: t.Capture, *events: t.TransportEvent) -> t.Capture:
    return replace(c, events=events)


def make_ack(*, fixture: bool = True, **kwargs: object) -> t.ClientProof:
    p = t.ClientProof(
        client_id="trusted-client", issuer_id="independent-test-issuer",
        request_id="request-1", trace_id="trace-1",
        tenant_id="tenant-1", actor_id="actor-1", frame_id="frame-1",
        frame_sha256=t.sha(FIRST_BYTES), receipt_nonce="nonce-1",
        signature="fake-structural-signature", fixture=fixture,
    )
    return replace(p, **kwargs)


def with_ack(c: t.Capture, proof: t.ClientProof | None = None) -> t.Capture:
    ack = event(t.CLIENT, 6, client_proof=proof or make_ack())
    return replace(c, events=(*c.events, ack))


class FakeFixtureVerifier:
    def verify(self, proof: t.ClientProof) -> bool:
        return proof.signature == "fake-structural-signature"


class RejectFixtureVerifier:
    def verify(self, proof: t.ClientProof) -> bool:
        return False


class FakeClock:
    def __init__(self) -> None:
        self.count = 0

    def sample(self) -> t.ClockSample:
        self.count += 1
        return t.ClockSample("fake-clock", self.count * 1_000_000, 1000 + self.count)


class FakeTransport:
    def __init__(self, recorder: t.CaptureAdapter) -> None:
        self.recorder = recorder

    def write(self, data: bytes, frame_id: str, first: bool) -> None:
        self.recorder.observe(
            t.FIRST if first else t.CITED, boundary="server_write_observed",
            frame_id=frame_id, frame_bytes=data, citation_ids=("cite-1",),
            source_bindings=(("cite-1", "source-1", "revision-1", h("native")),),
            verifier_receipt_id="verify-1",
        )


def test_valid_fixture_stream_not_real_client_or_product() -> None:
    result = t.validate(good_capture())
    assert result.status == t.LOCAL_PASS
    assert result.product_ttft == t.PRODUCT_TTFT
    assert result.delivery == t.CLIENT_UNAVAILABLE
    assert result.client_ack_class == t.CLIENT_UNAVAILABLE
    assert result.first_server_text_ms == pytest.approx(200.0)
    assert result.first_cited_ms == pytest.approx(300.0)
    assert result.final_request_ms == pytest.approx(400.0)


def test_real_image_provenance_not_inferred() -> None:
    c = good_capture()
    result = t.validate(replace(c, candidate=candidate(
        image_digest=None, build_attestation_sha256=None,
        mode="externally_observed",
    )), external_provenance_verified=True)
    assert result.status == t.LOCAL_PASS
    assert result.delivery == t.CLIENT_UNAVAILABLE
    assert result.product_ttft == t.PRODUCT_TTFT


def test_safe_abstention_in_denominator_without_first_bytes() -> None:
    c = good_capture()
    safe_events = (
        c.events[0], c.events[1],
        event(t.TERMINAL, 3, terminal_kind="safe_abstention",
              abstention_reason="no_authorized_source"),
    )
    safe = replace(c, events=safe_events, verified_answer_bytes=b"",
                   verified_answer_sha256=t.sha(b""))
    result = t.validate(safe)
    assert result.status == t.LOCAL_PASS
    assert result.first_server_text_ms is None
    assert result.eligible_answer is False


def test_local_capture_adapter_fake_transport_no_real_ack() -> None:
    c = good_capture()
    recorder = t.CaptureAdapter(c.candidate, FakeClock())
    fake = FakeTransport(recorder)
    recorder.observe(t.REQUEST)
    recorder.observe(t.VERIFIED, verifier_receipt_id="verify-1")
    fake.write(FIRST_BYTES, "frame-1", first=True)
    fake.write(LAST_BYTES, "frame-2", first=False)
    recorder.observe(t.TERMINAL, terminal_kind="answer")
    assert t.validate(replace(c, events=tuple(recorder.events))).status == t.LOCAL_PASS
    with pytest.raises(t.EvidenceDenied, match="CLIENT_ACK_REQUIRES_EXTERNAL_PORT"):
        recorder.observe(t.CLIENT)


def test_fixture_ack_must_never_certify_real_delivery() -> None:
    v = t.validate(with_ack(good_capture()),
                   external_client_verifier=FakeFixtureVerifier())
    assert v.client_ack_class == "FIXTURE_ACK_ONLY"
    assert v.delivery == t.CLIENT_UNAVAILABLE
    assert v.product_ttft == t.PRODUCT_TTFT


def test_untrusted_external_named_ack_still_not_certification() -> None:
    v = t.validate(with_ack(good_capture(), make_ack(fixture=False)),
                   external_client_verifier=FakeFixtureVerifier())
    assert v.client_ack_class == "ACK_AUTHORITY_NOT_CERTIFIED"
    assert v.delivery == t.CLIENT_UNAVAILABLE


def test_calibrated_cross_domain_order_only_not_latency() -> None:
    c = good_capture()
    e = evt(c, 3, stamp=t.ClockSample("host-b", 1_400_000_000, 1400))
    e = replace(e, anchors=(
        t.CalibratedAnchor("host-a", 1_000_000_000, 1_000_000_000, 0),
        t.CalibratedAnchor("host-b", 1_000_000_000, 1_000_000_000, 0),
    ))
    result = t.validate(e)
    assert result.status == t.LOCAL_PASS
    assert result.first_cited_ms is None


def _reorder(c: t.Capture, a: int, b: int) -> t.Capture:
    entries = list(c.events)
    entries[a], entries[b] = entries[b], entries[a]
    return replace(c, events=tuple(entries))


def _truncated(c: t.Capture) -> t.Capture:
    return replace(c, events=(c.events[0], c.events[1], c.events[4]))


def _terminal_only(c: t.Capture) -> t.Capture:
    return replace(c, events=(
        c.events[0], c.events[1],
        event(t.TERMINAL, 3, terminal_kind="answer"),
    ))


def _progress_only(c: t.Capture) -> t.Capture:
    return replace(c, events=(
        c.events[0], c.events[1],
        event("first_material", 3),
        event(t.TERMINAL, 4, terminal_kind="answer"),
    ))


def _diagnostic_terminal_name(c: t.Capture) -> t.Capture:
    return replace(c, events=(
        c.events[0], c.events[1],
        event("final_answer_done", 3),
        event(t.TERMINAL, 4, terminal_kind="answer"),
    ))


def _unsafe_safe_terminal(c: t.Capture) -> t.Capture:
    return evt(c, 4, terminal_kind="safe_abstention",
               abstention_reason="policy_denied")


def _bad_client(c: t.Capture, **kw: object) -> t.Capture:
    return with_ack(c, make_ack(**kw))


NEGATIVE = [
    ("short_git", lambda c: replace(c, candidate=candidate(source_commit="a" * 8))),
    ("invalid_git_uppercase", lambda c: replace(
        c, candidate=candidate(source_commit="A" * 40))),
    ("invalid_runner_sha", lambda c: replace(
        c, candidate=candidate(runner_sha256="not-sha"))),
    ("invalid_dataset_sha", lambda c: replace(
        c, candidate=candidate(dataset_sha256="z" * 64))),
    ("invalid_instrumentation_sha", lambda c: replace(
        c, candidate=candidate(instrumentation_sha256="a" * 63))),
    ("invalid_tree_sha", lambda c: replace(
        c, candidate=candidate(tree_sha256=""))),
    ("invalid_source_manifest_sha", lambda c: replace(
        c, candidate=candidate(source_manifest_sha256="bad"))),
    ("mutable_image_tag", lambda c: replace(
        c, candidate=candidate(image_digest="stage30p:latest"))),
    ("invalid_image_digest", lambda c: replace(
        c, candidate=candidate(image_digest="sha256:BAD"))),
    ("unbound_build_attestation", lambda c: replace(
        c, candidate=candidate(image_digest=None))),
    ("bad_build_attestation", lambda c: replace(
        c, candidate=candidate(build_attestation_sha256="123"))),
    ("missing_task_head", lambda c: replace(
        c, candidate=candidate(durable_task_head=""))),
    ("missing_trace", lambda c: replace(c, candidate=candidate(trace_id=""))),
    ("invalid_answer_sha", lambda c: replace(c, verified_answer_sha256="bad")),
    ("invalid_answer_utf8", lambda c: replace(
        c, verified_answer_bytes=b"\xff",
        verified_answer_sha256=t.sha(b"\xff"))),
    ("missing_events", lambda c: replace(c, events=())),
    ("terminal_only", _terminal_only),
    ("missing_first_bytes", _truncated),
    ("progress_event_name_only", _progress_only),
    ("final_event_name_only", _diagnostic_terminal_name),
    ("first_as_whitespace", lambda c: evt(
        c, 2, frame_bytes=b"       ", frame_sha256=t.sha(b"       "))),
    ("event_out_of_order", lambda c: _reorder(c, 2, 3)),
    ("replayed_event_id", lambda c: evt(c, 3, event_id="event-3")),
    ("sequence_duplicate", lambda c: evt(c, 3, sequence=3)),
    ("reverse_clock", lambda c: evt(
        c, 3, stamp=t.ClockSample("host-a", 1_100_000_000, 1400))),
    ("different_clock_domain", lambda c: evt(
        c, 3, stamp=t.ClockSample("host-b", 1_400_000_000, 1400))),
    ("missing_timestamp", lambda c: evt(
        c, 2, stamp=t.ClockSample("host-a", -1, 1300))),
    ("invalid_wall_clock", lambda c: evt(
        c, 2, stamp=t.ClockSample("host-a", 1_300_000_000, -1))),
    ("wrong_tenant", lambda c: evt(c, 2, tenant_id="attacker")),
    ("wrong_actor", lambda c: evt(c, 2, actor_id="attacker")),
    ("wrong_request", lambda c: evt(c, 2, request_id="foreign")),
    ("stale_source_rights", lambda c: replace(
        c, sources=(pin(rights_expires_wall_ms=1200),))),
    ("revoked_source", lambda c: replace(c, sources=(pin(revoked=True),))),
    ("source_future_issued", lambda c: replace(
        c, sources=(pin(rights_issued_wall_ms=1600),))),
    ("wrong_source_tenant", lambda c: replace(
        c, sources=(pin(tenant_id="attacker"),))),
    ("invalid_source_digest", lambda c: replace(
        c, sources=(pin(sha256="123"),))),
    ("unsupported_citation", lambda c: evt(
        c, 2, citation_ids=("unknown",))),
    ("duplicate_citation", lambda c: evt(
        c, 2, citation_ids=("cite-1", "cite-1"))),
    ("missing_source_binding", lambda c: evt(c, 2, source_bindings=())),
    ("source_revision_drift", lambda c: evt(
        c, 2, source_bindings=(("cite-1", "source-1", "revision-2", h("native")),))),
    ("source_digest_drift", lambda c: evt(
        c, 2, source_bindings=(("cite-1", "source-1", "revision-1", h("other")),))),
    ("wrong_source_identity", lambda c: evt(
        c, 2, source_bindings=(("cite-1", "source-OTHER", "revision-1", h("native")),))),
    ("missing_citation", lambda c: evt(c, 2, citation_ids=())),
    ("frame_digest_mismatch", lambda c: evt(c, 2, frame_sha256=h("other"))),
    ("utf8_split", lambda c: evt(
        c, 3, frame_bytes=b"\xce", frame_sha256=t.sha(b"\xce"))),
    ("offset_replay", lambda c: evt(c, 3, start_byte=0)),
    ("offset_gap", lambda c: evt(c, 3, end_byte=len(ANSWER) + 1)),
    ("same_frame_id", lambda c: evt(c, 3, frame_id="frame-1")),
    ("fake_flush_boundary", lambda c: evt(c, 2, boundary="server_enqueued")),
    ("frame_no_verifier", lambda c: evt(c, 2, verifier_receipt_id="")),
    ("verification_not_matching", lambda c: evt(
        c, 1, verifier_receipt_id="foreign-verifier")),
    ("answer_not_complete", lambda c: replace(
        c, verified_answer_bytes=ANSWER + b" tail",
        verified_answer_sha256=t.sha(ANSWER + b" tail"))),
    ("safe_with_answer_bytes", _unsafe_safe_terminal),
    ("terminal_bad_kind", lambda c: evt(c, 4, terminal_kind="unknown")),
    ("terminal_same_timestamp", lambda c: evt(
        c, 4, stamp=c.events[3].stamp)),
    ("ack_without_verifier", lambda c: with_ack(c)),
    ("ack_wrong_frame", lambda c: _bad_client(c, frame_id="frame-2")),
    ("ack_wrong_tenant", lambda c: _bad_client(c, tenant_id="other")),
    ("ack_wrong_digest", lambda c: _bad_client(c, frame_sha256=h("fake"))),
    ("ack_missing_signature", lambda c: _bad_client(c, signature="")),
]


@pytest.mark.parametrize(("name", "mutation"), NEGATIVE,
                         ids=[name for name, _ in NEGATIVE])
def test_negative_stream(name: str, mutation: object) -> None:
    del name
    # The tests deliberately exercise independently generated malformed inputs.
    c = mutation(good_capture())
    with pytest.raises(t.EvidenceDenied):
        t.validate(c)


def test_rejected_client_signature() -> None:
    with pytest.raises(t.EvidenceDenied, match="ACK_SIGNATURE_REJECTED"):
        t.validate(with_ack(good_capture()),
                   external_client_verifier=RejectFixtureVerifier())


def test_explicit_client_ack_identity_mismatch() -> None:
    with pytest.raises(t.EvidenceDenied, match="ACK_WRONG_FRAME_OR_IDENTITY"):
        t.validate(with_ack(good_capture(), make_ack(actor_id="other")),
                   external_client_verifier=FakeFixtureVerifier())


def test_client_after_terminal_is_allowed_only_structural() -> None:
    v = t.validate(with_ack(good_capture()),
                   external_client_verifier=FakeFixtureVerifier())
    assert v.client_ack_class == "FIXTURE_ACK_ONLY"


def test_cross_domain_overlapping_anchor_refused() -> None:
    c = evt(good_capture(), 3, stamp=t.ClockSample(
        "host-b", 1_400_000_000, 1400))
    c = replace(c, anchors=(
        t.CalibratedAnchor("host-a", 1_000_000_000, 1_000_000_000, 70_000_000),
        t.CalibratedAnchor("host-b", 1_000_000_000, 1_000_000_000, 70_000_000),
    ))
    with pytest.raises(t.EvidenceDenied, match="CLOCK_UNCERTAINTY_OVERLAP"):
        t.validate(c)


def test_duration_nearest_rank_diagnostic_only() -> None:
    rows = tuple(t.DurationCase(
        f"case{i}", f"req{i}", True, "completed", float(i * 1000),
    ) for i in range(1, 21))
    receipt = t.duration_denominator(rows)
    assert receipt.nearest_rank_p95_ms == 19000
    assert receipt.total == receipt.eligible == receipt.completed == 20
    assert receipt.synthetic_diagnostic_within_15s is False
    assert receipt.product_p95 == t.PRODUCT_P95


def test_duration_bound_15s_and_one_second_too_late() -> None:
    fine = t.duration_denominator((
        t.DurationCase("one", "req1", True, "completed", 15000.0),
    ))
    late = t.duration_denominator((
        t.DurationCase("one", "req1", True, "completed", 16000.0),
    ))
    assert fine.synthetic_diagnostic_within_15s
    assert not late.synthetic_diagnostic_within_15s
    assert fine.product_p95 == late.product_p95 == t.PRODUCT_P95


def test_timeout_missing_abstention_counted_not_silently_dropped() -> None:
    rows = (
        t.DurationCase("a", "req1", True, "completed", 3000.0),
        t.DurationCase("b", "req2", True, "timeout", None),
        t.DurationCase("c", "req3", True, "missing", None),
        t.DurationCase("d", "req4", False, "safe_abstention", None),
    )
    v = t.duration_denominator(rows)
    assert (v.total, v.eligible, v.completed, v.timeout, v.missing,
            v.safe_abstention) == (4, 3, 1, 1, 1, 1)
    assert v.nearest_rank_p95_ms is None
    assert not v.synthetic_diagnostic_within_15s


@pytest.mark.parametrize("rows,code", [
    ((), "NO_DURATION_MANIFEST"),
    ((t.DurationCase("same", "r1", True, "completed", 4),
      t.DurationCase("same", "r2", True, "completed", 4)),
     "DUPLICATE_DURATION_CASE"),
    ((t.DurationCase("one", "r1", True, "completed", -1),),
     "INVALID_FINAL_DURATION"),
    ((t.DurationCase("one", "r1", True, "timeout", 1200),),
     "UNTRUSTED_NONCOMPLETION_DURATION"),
    ((t.DurationCase("one", "r1", True, "completed", float("nan")),),
     "INVALID_FINAL_DURATION"),
    ((t.DurationCase("one", "r1", True, "completed", float("inf")),),
     "INVALID_FINAL_DURATION"),
])
def test_negative_duration_manifest(rows: tuple[t.DurationCase, ...],
                                    code: str) -> None:
    with pytest.raises(t.EvidenceDenied, match=code):
        t.duration_denominator(rows)
