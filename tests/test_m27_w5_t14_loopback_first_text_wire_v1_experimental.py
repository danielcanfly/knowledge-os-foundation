"""Adversarial T14 fixture wire testing. Real server/client PIDs plus strict denial codes."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_t14_loopback_first_text_wire_v1_experimental as t


def base() -> list[bytes]:
    return t.sample_events()


def packet(events: list[bytes], header: bytes | None = None) -> bytes:
    return (t.headers() if header is None else header) + b"".join(events)


def edit(index: int, key: str, value: object) -> bytes:
    lines = base()
    kind = ("progress", "answer", "terminal")[index]
    original = json.loads(lines[index].split(b"data: ", 1)[1].split(b"\n", 1)[0])
    original[key] = value
    lines[index] = t.encode_event(kind, original)
    return packet(lines)


def remove(index: int, key: str) -> bytes:
    lines = base()
    kind = ("progress", "answer", "terminal")[index]
    original = json.loads(lines[index].split(b"data: ", 1)[1].split(b"\n", 1)[0])
    original.pop(key)
    lines[index] = t.encode_event(kind, original)
    return packet(lines)


def replace_event(index: int, raw: bytes) -> bytes:
    lines = base()
    lines[index] = raw
    return packet(lines)


def prefixed(raw: bytes) -> bytes:
    return t.headers() + raw + b"".join(base()[1:])


def _raw(kind: bytes, data: bytes) -> bytes:
    return b"event: " + kind + b"\ndata: " + data + b"\n\n"


def _wrong_binding(idx: int, field: int, value: str) -> bytes:
    lines = base()
    obj = json.loads(lines[idx].split(b"data: ", 1)[1].split(b"\n", 1)[0])
    obj["source_bindings"][0][field] = value
    lines[idx] = t.encode_event("answer", obj)
    return packet(lines)


def _append_terminal() -> bytes:
    return packet(base() + [base()[-1]])


def _post_terminal_data() -> bytes:
    lines = base()
    return packet(lines + [lines[1]])


def _reorder_progress() -> bytes:
    events = base()
    return packet([events[1], events[0], events[2]])


def _progress_terminal() -> bytes:
    e = base()
    return packet([e[0], e[-1]])


def _wrong_answer_text(value: str) -> bytes:
    obj = json.loads(base()[1].split(b"data: ", 1)[1].split(b"\n", 1)[0])
    obj["text"] = value
    obj["sha256"] = t.sha(value.encode())
    obj["end"] = len(value.encode())
    events = base()
    events[1] = t.encode_event("answer", obj)
    return packet(events)


def _large_raw(n: int) -> bytes:
    return t.headers() + b"event: answer\ndata: " + b"z" * n + b"\n\n"


def _double_json() -> bytes:
    return replace_event(1, b'event: answer\ndata: {"a":1}\ndata: {"b":2}\n\n')


NEGATIVE = [
    ("http_500", lambda: t.headers(500) + b"".join(base()), "HTTP_NON_200"),
    ("http_404", lambda: packet(base(), b"HTTP/1.1 404 No\r\n\r\n"), "HTTP_NON_200"),
    ("http_100", lambda: packet(base(), b"HTTP/1.1 100 Continue\r\n\r\n"), "HTTP_NON_200"),
    (
        "http_wrong_type",
        lambda: packet(base(), b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n"),
        "HTTP_WRONG_CONTENT_TYPE",
    ),
    ("http_no_type", lambda: packet(base(), b"HTTP/1.1 200 OK\r\n\r\n"), "HTTP_WRONG_CONTENT_TYPE"),
    (
        "http_duplicate_header",
        lambda: packet(
            base(),
            t.headers().replace(
                b"Cache-Control:",
                b"Content-Type: text/event-stream; charset=utf-8\r\nCache-Control:",
            ),
        ),
        "DUPLICATE_HTTP_HEADER",
    ),
    (
        "http_fake_length",
        lambda: packet(
            base(), t.headers().replace(b"\r\n\r\n", b"\r\nContent-Length: 999\r\n\r\n")
        ),
        "HTTP_FAKE_CONTENT_LENGTH",
    ),
    (
        "http_transfer_encoding",
        lambda: packet(
            base(), t.headers().replace(b"\r\n\r\n", b"\r\nTransfer-Encoding: chunked\r\n\r\n")
        ),
        "HTTP_UNSUPPORTED_ENCODING",
    ),
    (
        "http_header_missing_colon",
        lambda: packet(base(), b"HTTP/1.1 200 OK\r\nContent-Type text/event-stream\r\n\r\n"),
        "INVALID_HTTP_HEADER",
    ),
    (
        "http_bare_lf",
        lambda: packet(
            base(),
            b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; charset=utf-8\nX: y\r\n\r\n",
        ),
        "INVALID_HTTP_HEADER_NEWLINE",
    ),
    (
        "http_header_oversize",
        lambda: packet(base(), b"HTTP/1.1 200 OK\r\nX: " + b"x" * 8192 + b"\r\n\r\n"),
        "HTTP_HEADER_OVER_LIMIT",
    ),
    ("http_truncated", lambda: b"HTTP/1.1 200 OK\r\n", "HTTP_TRUNCATED"),
    (
        "event_unknown_name",
        lambda: replace_event(0, base()[0].replace(b"event: progress", b"event: potato")),
        "UNKNOWN_SSE_EVENT",
    ),
    (
        "event_field_typo",
        lambda: replace_event(0, base()[0].replace(b"event: ", b"eveNt: ")),
        "MALFORMED_SSE_FIELD",
    ),
    (
        "event_data_field_typo",
        lambda: replace_event(0, base()[0].replace(b"data: ", b"datum: ")),
        "MALFORMED_SSE_FIELD",
    ),
    ("event_missing_event_field", lambda: replace_event(0, b"data: {}\n\n"), "MALFORMED_SSE_FIELD"),
    (
        "event_missing_data_field",
        lambda: replace_event(0, b"event: progress\n\n"),
        "MALFORMED_SSE_FIELD",
    ),
    (
        "event_comment_field",
        lambda: replace_event(0, b": ping\n" + base()[0]),
        "MALFORMED_SSE_FIELD",
    ),
    ("event_double_data", _double_json, "MALFORMED_SSE_FIELD"),
    (
        "event_raw_crlf",
        lambda: replace_event(0, base()[0].replace(b"\n", b"\r\n")),
        "SSE_CR_AMBIGUOUS",
    ),
    (
        "event_binary_utf8",
        lambda: replace_event(0, _raw(b"progress", b"\xff")),
        "INVALID_SSE_UTF8_OR_JSON",
    ),
    (
        "event_invalid_json",
        lambda: replace_event(0, _raw(b"progress", b"{ nope }")),
        "INVALID_SSE_UTF8_OR_JSON",
    ),
    (
        "event_json_array",
        lambda: replace_event(0, _raw(b"progress", b"[]")),
        "INVALID_SSE_JSON_OBJECT",
    ),
    (
        "event_json_null",
        lambda: replace_event(0, _raw(b"progress", b"null")),
        "INVALID_SSE_JSON_OBJECT",
    ),
    (
        "event_json_string",
        lambda: replace_event(0, _raw(b"progress", b'"progress"')),
        "INVALID_SSE_JSON_OBJECT",
    ),
    ("event_over_64k", lambda: _large_raw(70000), "SSE_EVENT_OVER_LIMIT"),
    ("wire_over_1m", lambda: _large_raw(1048577), "SSE_EVENT_OVER_LIMIT"),
    ("event_truncated", lambda: packet(base())[:-1], "SSE_TRUNCATED"),
    ("no_terminal", lambda: packet(base()[:-1]), "MISSING_TERMINAL"),
    ("only_progress", lambda: t.headers() + base()[0], "MISSING_TERMINAL"),
    ("progress_then_terminal", _progress_terminal, "PROGRESS_ONLY_NO_FIRST_TEXT"),
    (
        "terminal_before_answer",
        lambda: packet([base()[0], base()[2], base()[1]]),
        "PROGRESS_ONLY_NO_FIRST_TEXT",
    ),
    ("empty_events", lambda: t.headers(), "MISSING_TERMINAL"),
    (
        "wrong_request_progress",
        lambda: edit(0, "request_id", "other"),
        "FRAME_IDENTITY_MISMATCH_REQUEST_ID",
    ),
    (
        "wrong_tenant_progress",
        lambda: edit(0, "tenant_id", "other"),
        "FRAME_IDENTITY_MISMATCH_TENANT_ID",
    ),
    (
        "wrong_actor_progress",
        lambda: edit(0, "actor_id", "other"),
        "FRAME_IDENTITY_MISMATCH_ACTOR_ID",
    ),
    ("wrong_run_progress", lambda: edit(0, "run_id", "other"), "FRAME_IDENTITY_MISMATCH_RUN_ID"),
    (
        "wrong_trace_progress",
        lambda: edit(0, "trace_id", "other"),
        "FRAME_IDENTITY_MISMATCH_TRACE_ID",
    ),
    (
        "wrong_request_answer",
        lambda: edit(1, "request_id", "other"),
        "FRAME_IDENTITY_MISMATCH_REQUEST_ID",
    ),
    (
        "wrong_tenant_answer",
        lambda: edit(1, "tenant_id", "other"),
        "FRAME_IDENTITY_MISMATCH_TENANT_ID",
    ),
    (
        "wrong_actor_answer",
        lambda: edit(1, "actor_id", "other"),
        "FRAME_IDENTITY_MISMATCH_ACTOR_ID",
    ),
    ("wrong_run_answer", lambda: edit(1, "run_id", "other"), "FRAME_IDENTITY_MISMATCH_RUN_ID"),
    (
        "wrong_trace_answer",
        lambda: edit(1, "trace_id", "other"),
        "FRAME_IDENTITY_MISMATCH_TRACE_ID",
    ),
    (
        "wrong_tenant_terminal",
        lambda: edit(2, "tenant_id", "foreign"),
        "FRAME_IDENTITY_MISMATCH_TENANT_ID",
    ),
    ("progress_fixture_false", lambda: edit(0, "fixture", False), "NON_FIXTURE_SPOOF"),
    ("answer_fixture_false", lambda: edit(1, "fixture", False), "NON_FIXTURE_SPOOF"),
    ("terminal_fixture_false", lambda: edit(2, "fixture", False), "NON_FIXTURE_SPOOF"),
    ("fake_signed_ack", lambda: edit(1, "signature", "fake"), "SELF_ASSERTED_EXTERNAL_PROOF"),
    (
        "fake_authenticated_ack",
        lambda: edit(1, "authenticated_ack", True),
        "SELF_ASSERTED_EXTERNAL_PROOF",
    ),
    ("fake_product_p95", lambda: edit(2, "product_p95", 1), "SELF_ASSERTED_EXTERNAL_PROOF"),
    ("progress_impersonates_text", lambda: edit(0, "text", "answer"), "PROGRESS_IMPERSONATES_DATA"),
    (
        "progress_impersonates_sha",
        lambda: edit(0, "sha256", t.sha(b"answer")),
        "PROGRESS_IMPERSONATES_DATA",
    ),
    ("progress_wrong_phase", lambda: edit(0, "phase", "answered"), "PROGRESS_WRONG_PHASE"),
    ("progress_missing_phase", lambda: remove(0, "phase"), "PROGRESS_IMPERSONATES_DATA"),
    ("progress_after_answer", _reorder_progress, "LATE_PROGRESS"),
    ("answer_seq_replay", lambda: edit(1, "sequence", -1), "ANSWER_SEQUENCE_REPLAY_OR_GAP"),
    ("answer_seq_gap", lambda: edit(1, "sequence", 2), "ANSWER_SEQUENCE_REPLAY_OR_GAP"),
    ("answer_seq_float", lambda: edit(1, "sequence", 0.0), "ANSWER_SEQUENCE_REPLAY_OR_GAP"),
    ("answer_start_replay", lambda: edit(1, "start", -1), "ANSWER_OFFSET_REPLAY_OR_GAP"),
    ("answer_start_gap", lambda: edit(1, "start", 3), "ANSWER_OFFSET_REPLAY_OR_GAP"),
    ("answer_start_float", lambda: edit(1, "start", 0.0), "ANSWER_OFFSET_REPLAY_OR_GAP"),
    ("answer_end_missing", lambda: remove(1, "end"), "INVALID_ANSWER_END"),
    ("answer_end_float", lambda: edit(1, "end", 29.2), "INVALID_ANSWER_END"),
    ("answer_end_replayed", lambda: edit(1, "end", 1), "ANSWER_END_MISMATCH"),
    ("answer_text_empty", lambda: edit(1, "text", ""), "NON_SUBSTANTIVE_FIRST_TEXT"),
    ("answer_text_whitespace", lambda: edit(1, "text", "   "), "NON_SUBSTANTIVE_FIRST_TEXT"),
    ("answer_text_wrong_type", lambda: edit(1, "text", 9), "NON_SUBSTANTIVE_FIRST_TEXT"),
    (
        "answer_digest_corrupt",
        lambda: edit(1, "sha256", t.sha(b"evil")),
        "ANSWER_FRAME_SHA_MISMATCH",
    ),
    ("answer_digest_missing", lambda: remove(1, "sha256"), "ANSWER_FRAME_SHA_MISMATCH"),
    (
        "answer_text_changed",
        lambda: _wrong_answer_text("Evil unrelated text"),
        "ANSWER_NOT_VERIFIED_PREFIX",
    ),
    ("answer_text_truncated", lambda: _wrong_answer_text("Alpha "), "INCOMPLETE_ANSWER_TERMINAL"),
    ("answer_citation_missing", lambda: remove(1, "citation_ids"), "UNBOUND_CITATION"),
    ("answer_citation_other", lambda: edit(1, "citation_ids", ["fake"]), "UNBOUND_CITATION"),
    (
        "answer_citation_duplicate",
        lambda: edit(1, "citation_ids", [t.CITATION, t.CITATION]),
        "UNBOUND_CITATION",
    ),
    ("answer_bindings_empty", lambda: edit(1, "source_bindings", []), "MUTATED_SOURCE_PIN"),
    ("answer_source_id_wrong", lambda: _wrong_binding(1, 1, "fake"), "MUTATED_SOURCE_PIN"),
    (
        "answer_source_revision_wrong",
        lambda: _wrong_binding(1, 2, "rev-evil"),
        "MUTATED_SOURCE_PIN",
    ),
    (
        "answer_source_sha_wrong",
        lambda: _wrong_binding(1, 3, t.sha(b"mutated")),
        "MUTATED_SOURCE_PIN",
    ),
    ("answer_citation_binding_wrong", lambda: _wrong_binding(1, 0, "other"), "MUTATED_SOURCE_PIN"),
    ("answer_wrong_verifier", lambda: edit(1, "proof_id", "evil"), "WRONG_VERIFIER_PROOF"),
    ("answer_missing_verifier", lambda: remove(1, "proof_id"), "WRONG_VERIFIER_PROOF"),
    (
        "terminal_wrong_status",
        lambda: edit(2, "status", "safe_abstention"),
        "TERMINAL_NOT_COMPLETE",
    ),
    ("terminal_missing_status", lambda: remove(2, "status"), "TERMINAL_NOT_COMPLETE"),
    (
        "terminal_digest_corrupt",
        lambda: edit(2, "answer_sha256", t.sha(b"evil")),
        "TERMINAL_ANSWER_DIGEST_MISMATCH",
    ),
    (
        "terminal_digest_missing",
        lambda: remove(2, "answer_sha256"),
        "TERMINAL_ANSWER_DIGEST_MISMATCH",
    ),
    ("terminal_duplicate", _append_terminal, "STREAM_AFTER_TERMINAL"),
    ("terminal_followed_by_data", _post_terminal_data, "STREAM_AFTER_TERMINAL"),
    (
        "stream_21_extra_progress",
        lambda: packet([base()[0]] * 34 + base()[1:]),
        "SSE_EVENT_COUNT_OVER_LIMIT",
    ),
    (
        "missing_request_progress",
        lambda: remove(0, "request_id"),
        "FRAME_IDENTITY_MISMATCH_REQUEST_ID",
    ),
    ("missing_tenant_answer", lambda: remove(1, "tenant_id"), "FRAME_IDENTITY_MISMATCH_TENANT_ID"),
    ("missing_trace_terminal", lambda: remove(2, "trace_id"), "FRAME_IDENTITY_MISMATCH_TRACE_ID"),
]


@pytest.mark.parametrize(("name", "mutator", "reason"), NEGATIVE, ids=[row[0] for row in NEGATIVE])
def test_negative_wire_mutation(name: str, mutator: object, reason: str) -> None:
    del name
    with pytest.raises(t.WireDenied, match="^" + reason + "$"):
        t.parse_bytes(mutator(), fragment=11)


@pytest.mark.parametrize("fragment", [1, 2, 3, 5, 7, 11, 19, 43, 111])
def test_valid_real_ar08_adapter_sse_fragmentation(fragment: int) -> None:
    r = t.parse_bytes(packet(base()), fragment=fragment)
    assert bytes(r.answer) == t.ANSWER
    assert r.answers == 1
    assert r.progress == 1
    assert r.status == "COMPLETE"
    assert r.first_data_ns < r.terminal_ns


@pytest.mark.parametrize(
    ("cases", "reason"),
    [
        ([], "NO_LATENCY_CASES"),
        (
            [{"case_id": "", "status": "COMPLETE", "first_text_ms": 1}],
            "DUPLICATE_OR_MISSING_CASE_ID",
        ),
        (
            [{"case_id": "a", "status": "COMPLETE", "first_text_ms": 1}] * 2,
            "DUPLICATE_OR_MISSING_CASE_ID",
        ),
        ([{"case_id": "a", "first_text_ms": 1}], "MISSING_CASE_STATUS"),
        (
            [{"case_id": "a", "status": "COMPLETE", "first_text_ms": float("nan")}],
            "INVALID_COMPLETED_DURATION",
        ),
        (
            [{"case_id": "a", "status": "COMPLETE", "first_text_ms": float("inf")}],
            "INVALID_COMPLETED_DURATION",
        ),
        (
            [{"case_id": "a", "status": "COMPLETE", "first_text_ms": -1}],
            "INVALID_COMPLETED_DURATION",
        ),
        (
            [{"case_id": "a", "status": "COMPLETE", "first_text_ms": "3"}],
            "INVALID_COMPLETED_DURATION",
        ),
        (
            [{"case_id": "a", "status": "timeout", "first_text_ms": float("nan")}],
            "INVALID_NONCOMPLETED_DURATION",
        ),
        (
            [{"case_id": "a", "status": "5xx", "first_text_ms": float("inf")}],
            "INVALID_NONCOMPLETED_DURATION",
        ),
    ],
)
def test_negative_denominator(cases: list[dict], reason: str) -> None:
    with pytest.raises(t.WireDenied, match="^" + reason + "$"):
        t.denominator(cases)


def test_failure_denominator_keeps_all_noncompletions() -> None:
    cases = [
        {"case_id": f"c{i}", "status": status, "first_text_ms": value}
        for i, (status, value) in enumerate(
            [
                ("COMPLETE", 300),
                ("timeout", None),
                ("disconnected", 55),
                ("safe_abstained", None),
                ("5xx", None),
                ("missing", None),
            ]
        )
    ]
    res = t.denominator(cases)
    assert res["total"] == 6 and res["completed"] == 1
    assert res["nearest_rank_p95_ms"] is None
    assert res["failures_in_denominator"] == 5
    assert res["diagnostic_15s"] == "UNKNOWN"
    assert res["product_p95"] == "PRODUCTION_PRODUCT_P95_UNVERIFIED"


def test_nearest_rank_and_injected_delayed_first_not_wall_clock() -> None:
    cases = [
        {"case_id": f"case{i}", "status": "COMPLETE", "first_text_ms": float(i * 1000)}
        for i in range(1, 21)
    ]
    r = t.denominator(cases)
    assert r["nearest_rank_p95_ms"] == 19000
    assert r["diagnostic_15s"] == "FAIL"
    assert (
        t.denominator([{"case_id": "f", "status": "COMPLETE", "first_text_ms": 15000.0}])[
            "diagnostic_15s"
        ]
        == "PASS"
    )


def test_ar08_fixture_and_t09_are_not_external_authority() -> None:
    adapter = t.fixture_adapter(
        type(
            "Capture",
            (),
            {
                "enqueue": lambda self, frame: None,
                "flush": lambda self, sequence: None,
            },
        )()
    )
    adapter.push(t.ANSWER, answer_offset=0)
    assert adapter.terminal().status == "terminal"
    assert adapter.first_answer_receipt.client_delivery == t.ar08.DELIVERY
    assert t.DENIED == (
        "REAL_AUTHENTICATED_CLIENT_ACK_UNVERIFIED",
        "PRODUCTION_PRODUCT_P95_UNVERIFIED",
        "REAL_PROVIDER_AND_SOURCE_RIGHTS_UNVERIFIED",
        "ORIGINAL_523_FINAL_CITED_GATE_UNVERIFIED",
        "REL01_NOT_CERTIFIED",
        "REL02_NOT_AUTHORIZED",
    )
    assert "PRODUCTION_PRODUCT_P95_UNVERIFIED" in t.DENIED


def test_real_socket_independent_processes_and_progress_denial(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    result = t.probe(
        worktree=project,
        scratch=tmp_path / "private",
        modes=(
            "positive",
            "progress_only",
            "drop_terminal",
            "server_500",
            "disconnect",
            "wrong_tenant",
            "corrupt_digest",
            "corrupt_source",
            "bad_utf8",
            "terminal_early",
        ),
    )
    report = json.loads(Path(result["receipt_path"]).read_text())
    assert result["status"] == "T14_LOCAL_WIRE_PASS"
    assert report["positive_actual_wire"] is True
    assert report["progress_only_rejected"] is True
    assert report["local_loopback_gate"] == t.LOCAL_WIRE_PASS
    assert report["first_text_gate"] == t.FIRST_PASS
    assert report["latency"]["total"] == 10
    assert report["latency"]["completed"] == 1
    assert report["latency"]["nearest_rank_p95_ms"] is None
    assert report["latency"]["diagnostic_15s"] == "UNKNOWN"
    pos = report["cases"][0]
    assert pos["server"]["server_pid"] != pos["client"]["client_pid"]
    assert pos["server_endpoint"].startswith("127.0.0.1:")
    assert pos["client"]["recv_calls"] > 1
    assert pos["client"]["answer_sha256"] == t.sha(t.ANSWER)
    assert pos["client"]["request_ns"] < pos["client"]["first_data_ns"]
    assert pos["client"]["first_data_ns"] < pos["client"]["terminal_ns"]
    assert pos["server"]["enqueue_ns"][0] <= pos["server"]["flush_ns"][0]
    assert pos["server"]["flush_ns"][0] <= pos["server"]["terminal_ns"]
    by_mode = {c["mode"]: c["status"] for c in report["cases"]}
    assert by_mode["progress_only"] == "PROGRESS_ONLY_NO_FIRST_TEXT"
    assert by_mode["drop_terminal"] == "MISSING_TERMINAL"
    assert by_mode["server_500"] == "HTTP_NON_200"
    assert by_mode["wrong_tenant"] == "FRAME_IDENTITY_MISMATCH_TENANT_ID"
    assert by_mode["corrupt_digest"] == "ANSWER_FRAME_SHA_MISMATCH"
    assert by_mode["corrupt_source"] == "MUTATED_SOURCE_PIN"
    assert by_mode["bad_utf8"] == "INVALID_SSE_UTF8_OR_JSON"
    assert by_mode["terminal_early"] == "PROGRESS_ONLY_NO_FIRST_TEXT"
    assert by_mode["disconnect"] == "MISSING_TERMINAL"
    assert t.sha(Path(result["receipt_path"]).read_bytes()) == result["receipt_sha256"]


def test_no_fake_loopback_or_external_receipt_from_unit_parser() -> None:
    raw = packet(base())
    receiver = t.parse_bytes(raw, fragment=1)
    assert receiver.first_data_ns is not None
    assert not hasattr(receiver, "authenticated_client_ack")
    assert t.LOCAL_WIRE_PASS not in repr(receiver)


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (lambda: t.SSEReceiver().feed(b"x", received_ns=-1), "INVALID_CLIENT_CLOCK"),
        (lambda: t.encode_event("admin", t.identity()), "ILLEGAL_EVENT_TYPE"),
        (
            lambda: t.encode_event("answer", {"text": "x" * (t.MAX_EVENT + 1)}),
            "INVALID_SSE_PAYLOAD",
        ),
        (
            lambda: t.probe(
                worktree=Path(__file__).resolve().parents[1],
                scratch=Path(__file__).resolve().parents[1] / "scratch",
            ),
            "SCRATCH_INSIDE_GIT_DENIED",
        ),
        (
            lambda: t.denominator(
                [{"case_id": "a", "status": "COMPLETE", "first_text_ms": math.nan}]
            ),
            "INVALID_COMPLETED_DURATION",
        ),
    ],
)
def test_negative_utility_boundary(action: object, reason: str) -> None:
    with pytest.raises(t.WireDenied, match="^" + reason + "$"):
        action()
