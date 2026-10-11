"""N21 fresh fixture-only external-client negative/failure-injection checks."""
from __future__ import annotations

import json

import pytest

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15
from knowledge_engine import m27_w5_n21_independent_local_client_v1_experimental as n21
from knowledge_engine import m27_w5_t14_loopback_first_text_wire_v1_experimental as t14

NAMESPACE = "n21pytest"
ALTER_FIELDS = (
    "request_id", "run_id", "trace_id", "tenant_id", "actor_id",
    "fixture", "sequence", "start", "end", "text", "sha256",
    "citation_ids", "source_bindings", "proof_id", "source_rights",
    "consent", "claim_start", "claim_end", "claim_sha256",
)
HOSTILE = (None, "spoofed", ["spoofed"], {"forgery": True})


def parse_wire(spec: dict, events: list[bytes], step: int = 7) -> n21.ExternalDecoder:
    receiver = n21.ExternalDecoder(spec)
    raw = t14.headers() + b"".join(events)
    for offset in range(0, len(raw), step):
        receiver.feed(raw[offset:offset + step], 10000 + offset)
    receiver.finish()
    return receiver


@pytest.mark.parametrize("index", range(12))
def test_dynamic_utf8_source_cited_local_packets(index: int) -> None:
    spec = i15.spec(index, NAMESPACE)
    local_expectation = n21.fixture_spec(index, NAMESPACE)
    assert local_expectation["source_sha256"] == spec["source_sha256"]
    assert local_expectation["answer_bytes"] == spec["answer_bytes"]
    decoder = parse_wire(local_expectation, i15.local_events(spec),
                         step=(index % 9) + 1)
    assert decoder.progress == 1
    assert decoder.answers > 0
    assert bytes(decoder.answer) == spec["answer_bytes"]
    assert decoder.first_recv_ns <= decoder.first_answer_ns
    assert decoder.first_answer_ns <= decoder.full_answer_ns < decoder.terminal_ns


@pytest.mark.parametrize("field", ALTER_FIELDS)
@pytest.mark.parametrize("attack", HOSTILE, ids=("null", "foreign", "list", "dict"))
def test_76_independently_injected_source_and_wire_fields(field: str, attack) -> None:
    spec = i15.spec(0, NAMESPACE)
    events = i15.local_events(spec)
    tampered = json.loads(events[1].split(b"data: ", 1)[1])
    assert tampered[field] != attack
    tampered[field] = attack
    events[1] = t14.encode_event("answer", tampered)
    with pytest.raises(n21.Denied):
        parse_wire(spec, events)


@pytest.mark.parametrize(
    ("mode", "wire"),
    (
        ("progress_only", lambda s, e: [e[0]]),
        ("missing_terminal", lambda s, e: e[:-1]),
        ("duplicate_terminal", lambda s, e: e + [e[-1]]),
        ("duplicate_answer", lambda s, e: e[:2] + [e[1]] + e[2:]),
        ("bad_status", lambda s, e: [t14.headers(500)] + e),
        ("not_sse", lambda s, e: [b"HTTP/1.1 200 OK\r\n\r\n"] + e),
        ("empty_events", lambda s, e: []),
    ),
)
def test_negative_transport_conditions(mode: str, wire) -> None:
    spec = i15.spec(0, NAMESPACE)
    events = i15.local_events(spec)
    packets = wire(spec, events)
    if mode in ("bad_status", "not_sse"):
        raw = b"".join(packets)
    else:
        raw = t14.headers() + b"".join(packets)
    receiver = n21.ExternalDecoder(spec)
    with pytest.raises(n21.Denied):
        for off in range(0, len(raw), 7):
            receiver.feed(raw[off:off + 7], 2000 + off)
        receiver.finish()


def test_progress_not_counted_as_first_substantive_data() -> None:
    spec = i15.spec(0, NAMESPACE)
    receiver = n21.ExternalDecoder(spec)
    raw = t14.headers() + i15.local_events(spec)[0]
    for off in range(0, len(raw), 7):
        receiver.feed(raw[off:off + 7], 5000 + off)
    assert receiver.first_recv_ns is not None
    assert receiver.first_answer_ns is None
    assert receiver.full_answer_ns is None
    assert receiver.terminal_ns is None
    with pytest.raises(n21.Denied, match="TERMINAL_NOT_SEEN"):
        receiver.finish()


def test_request_is_bound_to_loopback_only() -> None:
    spec = i15.spec(4, NAMESPACE)
    assert n21.request(spec) == i15._request(spec)
    assert b"Host: 127.0.0.1" in n21.request(spec)


@pytest.mark.parametrize("namespace", ("../bad", "bad space", "non-ascii-臺北"))
def test_invalid_namespace_fails_closed(namespace: str) -> None:
    with pytest.raises(i15.I15Denied):
        i15.spec(0, namespace)


@pytest.mark.parametrize("port", (-1, 0, 65536))
def test_invalid_network_port_rejected(port: int) -> None:
    result = n21.external_client(0, port, NAMESPACE)
    assert result["status"] == "UNSAFE_PORT"
    assert result["first_answer_ns"] is None
    assert result["recv_calls"] == 0


def test_frame_after_terminal_is_not_accepted() -> None:
    spec = i15.spec(3, NAMESPACE)
    receiver = parse_wire(spec, i15.local_events(spec))
    with pytest.raises(n21.Denied, match="BYTES_AFTER_TERMINAL"):
        receiver.feed(b"event: progress\n\n", 999999)

@pytest.mark.parametrize("status,completed,faults,expected", [
    (n21.PASS, 12, 16, 0),
    (n21.FAIL, 10, 18, 20),
    (n21.FAIL, 12, 16, 20),
    (n21.PASS, 11, 17, 20),
    (n21.PASS, 12, 15, 20),
])
def test_n22_probe_exit_code_follows_semantic_receipt(
        monkeypatch, capsys, tmp_path, status, completed, faults, expected):
    receipt = {"status": status, "attempted": 28, "completed": completed,
               "rejected_or_failed": faults, "sha256": "0" * 64}
    monkeypatch.setattr(n21, "suite", lambda *args: receipt)
    monkeypatch.setattr("sys.argv", [
        "n21", "probe", "--worktree", str(tmp_path),
        "--scratch", str(tmp_path / "scratch"), "--namespace", "n22test",
    ])
    assert n21.main() == expected
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_n22_boot_deadlines_bounded_and_original_server_unchanged():
    assert 6.0 < n21.SERVER_BOOT_DEADLINE_SECONDS <= 24.0
    assert 12.0 < n21.CLIENT_PREWARM_DEADLINE_SECONDS <= 24.0
    assert i15.BOOT_DEADLINE_SECONDS == 6.0
