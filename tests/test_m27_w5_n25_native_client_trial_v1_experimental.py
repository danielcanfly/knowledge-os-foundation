"""N25 independently rerunnable, exclusively synthetic / offline unit tests."""
from __future__ import annotations

import hashlib
import itertools
from dataclasses import replace

import pytest

from knowledge_engine.m27_w5_c24_client_observation_v1_experimental import (
    CasePlan,
    ObservationDenied,
    SourcePin,
    evaluate_cohort,
    make_test_frame,
)
from knowledge_engine.m27_w5_n25_native_client_trial_v1_experimental import (
    AppAttachment,
    NativeTrial,
    review_independent_authority,
    run_received_bytes,
)


def h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def clock():
    return itertools.count(1_000_000_000, 1_000_000).__next__


def objects():
    source = SourcePin(
        citation_id="src-1", source_id="knowledge-base-1",
        revision="fixture-r1", original_bytes=b"Evidence: trusted fixture.",
        source_sha256=h(b"Evidence: trusted fixture."),
        authorized=True,
    )
    case = CasePlan(
        case_id="case-1", request_id="request-1", nonce="nonce-1",
        runner_sha256=h(b"runner"), candidate_sha256=h(b"candidate"),
        expected_citation=True,
    )
    app = AppAttachment("fixture-app", h(b"app"), h(b"instrument"), "fixture-local")
    return case, source, app


def payload(case):
    return {
        "case_id": case.case_id, "request_id": case.request_id,
        "nonce": case.nonce, "runner_sha256": case.runner_sha256,
        "candidate_sha256": case.candidate_sha256,
    }


def frames(case, source, text="A cited answer"):
    raw = text.encode("utf-8")
    cited = {
        "citation_id": source.citation_id, "source_id": source.source_id,
        "revision": source.revision, "source_sha256": source.source_sha256,
        "source_start": 0, "source_end": len(source.original_bytes),
        "quote_sha256": h(source.original_bytes),
        "answer_start": 0, "answer_end": len(raw),
    }
    common = payload(case)
    answer = {
        **common, "sequence": 0, "start": 0, "end": len(raw),
        "sha256": h(raw), "text": text, "citations": [cited],
    }
    terminal = {**common, "status": "completed",
                "answer_bytes": len(raw), "answer_sha256": h(raw)}
    header = b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream; charset=utf-8\r\n\r\n"
    return header, (
        make_test_frame("progress", {**common, "phase": "preparing"}),
        make_test_frame("answer", answer),
        make_test_frame("terminal", terminal),
    ), answer, terminal


def run(stream=None, **kw):
    case, source, app = objects()
    if stream is None:
        hd, events, _, _ = frames(case, source)
        stream = (hd, *events)
    return run_received_bytes(
        case, [source], app, stream, clock_ns=clock(), **kw
    )


def test_complete_observer_source_citations_and_bounded_client_time():
    receipt = run()
    assert receipt["status"] == "COMPLETE"
    assert receipt["synthetic"] is True
    assert receipt["recv_calls"] == 4
    assert receipt["progress_events"] == 1
    assert receipt["answer_events"] == 1
    assert receipt["first_substantive_before_terminal"] is True
    assert receipt["full_final_answer_latency_ms"] == 4
    assert receipt["outcome_latency_ms"] == 4
    assert receipt["first_text_latency_ms"] == 3
    assert receipt["real_app_connected"] is False
    assert receipt["official_qualified"] is False
    assert receipt["product_p95_ms"] is None
    assert len(receipt["source_native_citations"]) == 1
    assert len(receipt["wire_transcript_sha256"]) == 64
    assert len(receipt["app_attachment_sha256"]) == 64


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 4, 5, 7, 11, 32, 128, 2048])
def test_split_transport_preserves_utf8_before_terminal(chunk_size):
    case, source, _ = objects()
    hd, events, _, _ = frames(case, source, "第一個可靠回覆 📎")
    blob = hd + b"".join(events)
    result = run(
        [blob[i:i + chunk_size] for i in range(0, len(blob), chunk_size)]
    )
    if chunk_size == 2048:
        # One recv contains answer+terminal. C24 can only timestamp the
        # single recv, so strict first-text-before-terminal is unprovable.
        assert result["status"] == "REJECTED"
        assert result["product_p95_ms"] is None
    else:
        assert result["status"] == "COMPLETE"
        assert result["first_substantive_before_terminal"]
        assert result["answer_bytes"] == len("第一個可靠回覆 📎".encode())


@pytest.mark.parametrize("reason", ["disconnect", "timeout", "cancelled", "rejected"])
def test_progress_without_answer_keeps_denominator_and_no_latency_p95(reason):
    case, source, _ = objects()
    hd, events, _, _ = frames(case, source)
    result = run([hd, events[0]], close_reason=reason)
    assert result["status"] == reason.upper()
    assert result["progress_events"] == 1
    assert result["first_substantive_text_ns"] is None
    assert result["full_final_answer_latency_ms"] is None
    assert result["outcome_latency_ms"] > 0
    assert result["product_p95_ms"] is None
    assert result["official_qualified"] is False


def test_partial_answer_and_disconnect_is_not_final_answer():
    case, source, _ = objects()
    hd, ev, _, _ = frames(case, source)
    r = run([hd, ev[1]])
    assert r["status"] == "DISCONNECT"
    assert r["answer_events"] == 1
    assert r["full_answer_ns"] is None
    assert r["answer_bytes"] is None
    assert r["full_final_answer_latency_ms"] is None


def test_error_event_is_not_complete_or_p95():
    case, source, _ = objects()
    hd, _, _, _ = frames(case, source)
    error = make_test_frame("error", {**payload(case), "code": "HTTP_FAILURE"})
    r = run([hd, error])
    assert r["status"] == "ERROR"
    assert r["terminal_ns"] is not None
    assert r["full_answer_ns"] is None
    assert r["outcome_latency_ms"] > 0
    assert r["product_p95_ms"] is None


@pytest.mark.parametrize("bad_value", [
    "", "bad/app", "bad@app", "bad:id", "bad?key", "bad#hash",
    "bad\\slash", "bad space", "é",
])
def test_unsafe_app_id_rejected(bad_value):
    _, _, app = objects()
    with pytest.raises(ObservationDenied):
        replace(app, app_id=bad_value).validate()


@pytest.mark.parametrize("bad_value", [
    "", "https://service.example", "user@host", "/local/app",
    "hostname:1234", "id?secret", "id#fragment", "id\\path",
])
def test_endpoint_url_or_secret_rejected(bad_value):
    _, _, app = objects()
    with pytest.raises(ObservationDenied):
        replace(app, endpoint_id=bad_value).validate()


@pytest.mark.parametrize("field", [
    "app_build_sha256", "instrumentation_sha256",
    "controller_grant_sha256", "independent_client_ack_sha256",
    "signed_source_roster_sha256",
])
@pytest.mark.parametrize("bad", ["not-sha", "A" * 64, "0" * 63, "g" * 64])
def test_image_and_external_reference_require_exact_digest(field, bad):
    _, _, app = objects()
    with pytest.raises(ObservationDenied):
        replace(app, **{field: bad}).validate()


@pytest.mark.parametrize("break_kind", [
    "bad_http", "no_citation", "bad_sha", "bad_offset", "bad_seq",
    "empty_answer", "wrong_request", "wrong_nonce", "wrong_runner",
    "wrong_candidate", "wrong_case", "bad_terminal", "missing_terminal",
    "unexpected_event", "fake_signature",
])
def test_corrupt_wire_fail_closed_no_p95(break_kind):
    case, source, _ = objects()
    hd, ev, answer, terminal = frames(case, source)
    a = dict(answer)
    t = dict(terminal)
    if break_kind == "bad_http":
        hd = hd.replace(b"200 OK", b"403 ERR")
    elif break_kind == "no_citation":
        a["citations"] = []
    elif break_kind == "bad_sha":
        a["sha256"] = h(b"wrong")
    elif break_kind == "bad_offset":
        a["end"] = 999
    elif break_kind == "bad_seq":
        a["sequence"] = 99
    elif break_kind == "empty_answer":
        a["text"] = ""
    elif break_kind == "wrong_request":
        a["request_id"] = "other"
    elif break_kind == "wrong_nonce":
        a["nonce"] = "other"
    elif break_kind == "wrong_runner":
        a["runner_sha256"] = h(b"other")
    elif break_kind == "wrong_candidate":
        a["candidate_sha256"] = h(b"other")
    elif break_kind == "wrong_case":
        a["case_id"] = "other"
    elif break_kind == "bad_terminal":
        t["answer_sha256"] = h(b"wrong")
    elif break_kind == "unexpected_event":
        a["signature"] = "no"
    elif break_kind == "fake_signature":
        a["authenticated_ack"] = True
    stream = [hd, make_test_frame("answer", a)]
    if break_kind != "missing_terminal":
        stream.append(make_test_frame("terminal", t))
    r = run(stream)
    assert r["status"] != "COMPLETE"
    assert r["product_p95_ms"] is None
    assert r["official_qualified"] is False


def test_exception_in_external_reader_not_silently_dropped():
    def broken():
        yield frames(*objects()[:2])[0]
        raise OSError("fixture transport exception")
    r = run(broken())
    assert r["status"] == "REJECTED"
    assert r["client_transport_fault"] == "CLIENT_RECV_FAILURE:OSError"


def test_synthetic_not_eligible_for_independent_real_app_attestation():
    out = review_independent_authority(run())
    assert out["real_app_connected"] is False
    assert out["status"] == "UNKNOWN"


def test_signed_external_references_do_not_self_admit():
    receipt = run()
    receipt["synthetic"] = False
    receipt["app_attachment"].update({
        "controller_grant_sha256": h(b"controller"),
        "independent_client_ack_sha256": h(b"ack"),
        "signed_source_roster_sha256": h(b"sources"),
    })
    from knowledge_engine.m27_w5_n25_native_client_trial_v1_experimental import _digest
    receipt["app_attachment_sha256"] = _digest(receipt["app_attachment"])
    out = review_independent_authority(receipt, grant={}, ack={})
    assert out["real_app_connected"] is False
    assert out["official_qualified"] is False
    assert out["product_p95_ms"] is None


@pytest.mark.parametrize("denominator,rank", [(341, 324), (237, 226)])
def test_nearest_rank_calibration_only_never_real_product(denominator, rank):
    plan = []
    receipts = []
    for i in range(denominator):
        case, _, _ = objects()
        case = replace(case, case_id=f"case-{i}", nonce=f"nonce-{i}")
        plan.append(case)
        receipts.append({
            "schema": "m27.w5.c24.client_observation.v1",
            **payload(case),
            "synthetic": True, "status": "COMPLETE",
            "client_pid": i + 100, "client_process_nonce": f"p-{i}",
            "request_admitted_ns": 0, "first_substantive_text_ns": 1,
            "terminal_ns": (i + 1) * 1_000_000,
            "full_response_latency_ms": float(i + 1),
            "answer_bytes": 10, "answer_sha256": h(b"fixture"),
            "answer_events": 1, "source_native_citations": [{"id": "fixture"}],
        })
    calibrated = evaluate_cohort(plan, receipts, synthetic_calibration=True)
    assert calibrated["rank"] == rank
    assert calibrated["synthetic_calibration_p95_ms"] == rank
    assert calibrated["all_outcome_p95_ms"] is None
    receipts.pop()
    incomplete = evaluate_cohort(plan, receipts, synthetic_calibration=True)
    assert incomplete["synthetic_calibration_p95_ms"] is None
    assert incomplete["all_outcome_p95_ms"] is None


def test_session_cannot_be_double_closed_or_receive_after_done():
    case, source, app = objects()
    trial = NativeTrial(case, [source], app, clock_ns=clock())
    trial.before_send()
    hd, ev, _, _ = frames(case, source)
    for part in (hd, *ev):
        trial.on_recv(part)
    assert trial.close()["status"] == "COMPLETE"
    with pytest.raises(ObservationDenied):
        trial.close()
    with pytest.raises(ObservationDenied):
        trial.on_recv(b"late")
