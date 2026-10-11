"""I15 actual multi-process local wire, strict negatives and regression contract."""
import hashlib
import json
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15
from knowledge_engine import m27_w5_t14_loopback_first_text_wire_v1_experimental as t14


@pytest.fixture
def sample():
    return i15.spec(2)


def answer_payload(sample):
    raw = i15.local_events(sample)[1]
    return json.loads(raw.split(b"data: ", 1)[1].split(b"\n\n", 1)[0])


def frame(s, payload):
    return t14.encode_event("answer", payload)


def first_and_terminal(s, packet):
    events = i15.local_events(s)
    events[1] = packet
    return events


def test_distinct_fixture_corpus_and_revisions():
    cases = [i15.spec(i) for i in range(12)]
    assert len({x["source_sha256"] for x in cases}) == 12
    assert len({x["source_revision"] for x in cases}) == 12
    assert len({x["request_id"] for x in cases}) == 12
    assert len({x["run_id"] for x in cases}) == 12
    assert len({x["trace_id"] for x in cases}) == 12
    assert all(x["answer_sha256"] == hashlib.sha256(x["answer_bytes"]).hexdigest()
               for x in cases)


@pytest.mark.parametrize("index", range(12), ids=lambda i: f"case_{i:02d}_ar08_original_wire")
def test_each_cited_multibyte_fixture(index):
    s = i15.spec(index)
    receiver = i15.parse_fixture(s, i15.local_events(s), fragment=1)
    assert receiver.closed
    assert receiver.progress == 1
    assert receiver.answers >= 2
    assert bytes(receiver.answer) == s["answer_bytes"]


# 23 distinct fields x 3 mutation classes: 69 genuinely executed negative inputs.
MUTABLE_FIELDS = (
    "request_id", "run_id", "trace_id", "tenant_id", "actor_id",
    "fixture", "sequence", "start", "end", "text", "sha256",
    "citation_ids", "source_bindings", "proof_id", "source_rights",
    "consent", "claim_start", "claim_end", "claim_sha256",
)
MUTATION_CLASSES = ("attacker-value", None, False, [], {"forged": True})


@pytest.mark.parametrize("field", MUTABLE_FIELDS, ids=lambda x: "field_" + x)
@pytest.mark.parametrize("evil", MUTATION_CLASSES,
                         ids=("forged_string", "null", "false", "array", "object"))
def test_negative_exact_field_mutation(sample, field, evil):
    # 19 fields * 5 mutation classes = 95 individually named/fault-injected cases.
    p = answer_payload(sample)
    p[field] = evil
    with pytest.raises((i15.I15Denied, t14.WireDenied, TypeError, ValueError)):
        i15.parse_fixture(sample, first_and_terminal(sample, frame(sample, p)))


@pytest.mark.parametrize("attack", (
    "authenticated_ack", "signature", "product_p95", "real_provider",
    "cost_attestation", "image_digest", "release_certified",
), ids=lambda x: "forged_external_" + x)
def test_negative_external_authority_forgery(sample, attack):
    p = answer_payload(sample)
    p[attack] = "claimed-by-untrusted-server"
    with pytest.raises(i15.I15Denied, match="FORGED_EXTERNAL_AUTHORITY"):
        i15.parse_fixture(sample, first_and_terminal(sample, frame(sample, p)))


@pytest.mark.parametrize("attack", (
    "missing_terminal", "progress_only", "terminal_before_answer",
    "duplicate_terminal", "duplicate_frame", "frame_gap", "invalid_utf8",
    "invalid_json", "http_500", "unsupported_http_content_type",
    "source_pin_wrong", "cross_case_replay", "empty_progress",
    "progress_impersonates_answer", "terminal_wrong_digest",
), ids=lambda x: "fault_" + x)
def test_negative_stream_protocol(sample, attack):
    events = i15.local_events(sample)
    if attack == "missing_terminal":
        events.pop()
    elif attack == "progress_only":
        events = [events[0], events[-1]]
    elif attack == "terminal_before_answer":
        events = [events[0], events[-1], *events[1:-1]]
    elif attack == "duplicate_terminal":
        events.append(events[-1])
    elif attack == "duplicate_frame":
        events.insert(2, events[1])
    elif attack == "frame_gap":
        p = answer_payload(sample)
        p["sequence"] = 4
        events[1] = frame(sample, p)
    elif attack == "invalid_utf8":
        events[1] = b"event: answer\ndata: \xff\n\n"
    elif attack == "invalid_json":
        events[1] = b"event: answer\ndata: NOJSON\n\n"
    elif attack == "source_pin_wrong":
        p = answer_payload(sample)
        p["source_bindings"][0][2] = "stale-revision"
        events[1] = frame(sample, p)
    elif attack == "cross_case_replay":
        events[1] = i15.local_events(i15.spec(3))[1]
    elif attack == "empty_progress":
        events[0] = t14.encode_event("progress", {
            **i15.identity(sample), "fixture": True, "phase": "",
        })
    elif attack == "progress_impersonates_answer":
        events[0] = t14.encode_event("progress", {
            **i15.identity(sample), "fixture": True,
            "phase": "preparing", "first_text": True,
        })
    elif attack == "terminal_wrong_digest":
        events[-1] = t14.encode_event("terminal", {
            **i15.identity(sample), "fixture": True,
            "status": "completed", "answer_sha256": i15.sha(b"malicious"),
        })
    raw = t14.headers() + b"".join(events)
    if attack == "http_500":
        raw = t14.headers(500) + b"".join(events)
    if attack == "unsupported_http_content_type":
        raw = raw.replace(b"text/event-stream", b"text/html")
    with pytest.raises((i15.I15Denied, t14.WireDenied)):
        receiver = i15.Receiver(sample)
        for idx in range(0, len(raw), 5):
            receiver.feed(raw[idx:idx + 5], i15.now_ns() + idx)
        receiver.finish()


def test_negative_unknown_case_id():
    with pytest.raises(i15.I15Denied, match="UNKNOWN_CASE"):
        i15.spec(12)


def test_negative_bad_source_digest():
    s = i15.spec(1)
    s["source_sha256"] = i15.sha(b"fake-source")
    class Capture:
        def enqueue(self, frame):
            pass
        def flush(self, sequence):
            pass
    with pytest.raises((i15.I15Denied, ValueError)):
        i15.fixture_adapter(s, Capture())


@pytest.mark.parametrize("bad", ("", "duplicate", "not_complete", "empty"))
def test_negative_denominator_manifest(bad):
    entry = {
        "case_id": "fixture-1", "status": "COMPLETE",
        "client": {"first_text_ms": 1.0},
    }
    c = [entry]
    if bad == "empty":
        c = []
    if bad == "duplicate":
        c = [entry, dict(entry)]
    if bad == "not_complete":
        c = [dict(entry, status="FAILED", client={"first_text_ms": None})]
        result = i15.denominator(c)
        assert result["first_text_p95_ms"] is None
        assert result["failure_or_abstention"] == 1
        return
    if bad == "":
        c = [dict(entry, case_id="")]
        # Empty identifiers in denominator deliberately denied by T09.
    with pytest.raises((i15.I15Denied, ValueError)):
        i15.denominator(c)


def test_valid_denominator_only_when_all_complete():
    cases = [
        {"case_id": f"case-{i}", "status": "COMPLETE",
         "client": {"first_text_ms": i + .5}}
        for i in range(12)
    ]
    data = i15.denominator(cases)
    assert data["total"] == 12
    assert data["completed"] == 12
    assert data["first_text_p95_ms"] == 11.5
    assert data["product_p95"] == "PRODUCT_P95_UNVERIFIED"


def test_actual_independent_client_socket_probe(tmp_path):
    # Actual nonmock OS server processes, actual different client processes/recv.
    worktree = Path(__file__).resolve().parents[1]
    result = i15.probe(worktree, tmp_path)
    assert result["status"] == i15.PASS
    receipt_path = Path(result["receipt_path"])
    raw = receipt_path.read_bytes()
    assert i15.sha(raw) == result["receipt_sha256"]
    receipt = json.loads(raw)
    assert receipt["case_count"] == 12 + len(i15.FAULT_MODES)
    assert receipt["positive_count"] == 12
    assert receipt["negative_socket_count"] == len(i15.FAULT_MODES)
    assert receipt["denominator"]["first_text_p95_ms"] is None
    assert receipt["denominator"]["p95_classification"] == "UNKNOWN"
    for c in receipt["cases"]:
        assert c["endpoint"].startswith("127.0.0.1:")
        assert c["client"]["client_pid"] != c["server"]["server_pid"]
        assert c["client"]["recv_calls"] >= 1
        assert c["client"]["recv_bytes"] > 0
        if c["mode"] == "positive":
            assert c["status"] == "COMPLETE"
            assert c["client"]["received_answer_sha256"] == c["source_sha256"]
            assert c["client"]["first_data_ns"] < c["client"]["terminal_ns"]
        else:
            assert c["status"] != "COMPLETE"
    assert len({c["source_revision"] for c in receipt["cases"][:12]}) == 12


def test_scope_gate_remains_external():
    assert "REAL_APP_CLIENT_ACK_UNVERIFIED" in i15.GATES
    assert "W4_AR09_PHASE_B_BLOCKED" in i15.GATES
    assert "B13_RUNTIME_POSITIVE_BLOCKED" in i15.GATES
    assert "REL02_NOT_AUTHORIZED" in i15.GATES
