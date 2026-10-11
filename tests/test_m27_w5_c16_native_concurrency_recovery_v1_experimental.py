"""C16 bounded real-process lifecycle, denial and deterministic fault injection.

Fixture-only. All named mutant parametrizations actually execute independent
source-bound wire parsing; no external permissions, product claims or providers.
"""
import json
import subprocess
import threading
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as c16
from knowledge_engine import m27_w5_t14_loopback_first_text_wire_v1_experimental as t14

FIELDS = (
    "request_id", "run_id", "trace_id", "tenant_id", "actor_id",
    "fixture", "sequence", "start", "end", "text", "sha256",
    "citation_ids", "source_bindings", "proof_id", "source_rights",
    "consent", "claim_start", "claim_end", "claim_sha256",
)
DENIAL = {
    "request_id": "BOUND_IDENTITY_REQUEST_ID",
    "run_id": "BOUND_IDENTITY_RUN_ID",
    "trace_id": "BOUND_IDENTITY_TRACE_ID",
    "tenant_id": "BOUND_IDENTITY_TENANT_ID",
    "actor_id": "BOUND_IDENTITY_ACTOR_ID",
    "fixture": "SYNTHETIC_STATUS_REQUIRED",
    "sequence": "FRAME_SEQUENCE_REPLAY_GAP",
    "start": "FRAME_BYTE_OFFSET_REPLAY_GAP",
    "end": "FRAME_END_CHANGED",
    "text": "EMPTY_TEXT",
    "sha256": "FRAME_SHA_CHANGED",
    "citation_ids": "CITATION_CHANGED",
    "source_bindings": "SOURCE_PIN_CHANGED",
    "proof_id": "PROOF_CHANGED",
    "source_rights": "RIGHTS_NOT_CURRENT",
    "consent": "CONSENT_NOT_GRANTED",
    "claim_start": "CLAIM_SPAN_CHANGED",
    "claim_end": "CLAIM_SPAN_CHANGED",
    "claim_sha256": "CLAIM_SPAN_CHANGED",
}


@pytest.mark.parametrize("field", FIELDS, ids=lambda x: "field_" + x)
@pytest.mark.parametrize("intruder", (None, False, [], {}),
                         ids=("null", "false", "array", "object"))
def test_76_named_fault_injections_fail_closed(field, intruder):
    s = c16.spec(2, "testcase")
    events = c16.local_events(s)
    p = json.loads(events[1].split(b"data: ", 1)[1].split(b"\n\n", 1)[0])
    p[field] = intruder
    events[1] = t14.encode_event("answer", p)
    with pytest.raises(c16.I15Denied, match=DENIAL[field]):
        c16.parse_fixture(s, events, fragment=3)


@pytest.mark.parametrize("namespace", (
    "tenantA", "tenantB", "suite_one", "suite_two", "fault-x", "run_123",
))
def test_cross_suite_identity_namespace_replay_denial(namespace):
    a = c16.spec(1, namespace)
    b = c16.spec(1, namespace + "z")
    assert a["request_id"] != b["request_id"]
    assert a["tenant_id"] != b["tenant_id"]
    assert a["source_sha256"] == b["source_sha256"]
    with pytest.raises(c16.I15Denied, match="BOUND_IDENTITY_REQUEST_ID"):
        c16.parse_fixture(a, c16.local_events(b))


@pytest.mark.parametrize("unsafe", ("bad!", "../escape", " space", "\n", "中文", "x"*41))
def test_namespace_forgery_denied(unsafe):
    with pytest.raises(c16.I15Denied, match="NAMESPACE_INVALID"):
        c16.spec(0, unsafe)


@pytest.mark.parametrize("scenario", (
    "progress_only", "terminal_truncated", "frame_duplicate", "invalid_utf8",
    "wrong_revision", "source_sha_changed", "wrong_principal", "http_500",
    "fragmented_http", "forged_app_ack",
))
def test_protocol_fault_receipts_not_false_first_text(scenario):
    s = c16.spec(3, "denial")
    events = c16.local_events(s)
    if scenario == "progress_only":
        events = [events[0], events[-1]]
    elif scenario == "terminal_truncated":
        events.pop()
    elif scenario == "frame_duplicate":
        events.insert(2, events[1])
    elif scenario == "invalid_utf8":
        events[1] = b"event: answer\ndata: \xff\n\n"
    elif scenario in ("wrong_revision", "source_sha_changed", "wrong_principal",
                      "forged_app_ack"):
        payload = json.loads(events[1].split(b"data: ", 1)[1].split(b"\n\n")[0])
        if scenario == "wrong_revision":
            payload["source_bindings"][0][2] = "expired"
        elif scenario == "source_sha_changed":
            payload["source_bindings"][0][3] = c16.sha(b"stale")
        elif scenario == "wrong_principal":
            payload["actor_id"] = "foreign-actor"
        else:
            payload["authenticated_ack"] = True
        events[1] = t14.encode_event("answer", payload)
    if scenario == "fragmented_http":
        receiver = c16.parse_fixture(s, events, fragment=1)
        assert receiver.closed and receiver.first_data_ns < receiver.terminal_ns
        return
    raw = (t14.headers(500) if scenario == "http_500" else t14.headers())
    raw += b"".join(events)
    receiver = c16.Receiver(s)
    with pytest.raises((c16.I15Denied, t14.WireDenied)):
        for at in range(0, len(raw), 7):
            receiver.feed(raw[at:at+7], c16.now_ns() + at)
        receiver.finish()


def test_flock_budget_slots_bound_and_recover(tmp_path):
    # Actual kernel flock across separately opened FDs, even inside same process.
    acquired = threading.Event()
    release = threading.Event()
    two_ready = threading.Event()
    results = []

    def holder():
        with c16.case_slot(tmp_path, timeout=1) as (number, _):
            results.append(number)
            if len(results) == 2:
                two_ready.set()
            acquired.set()
            release.wait(2)

    threads = [threading.Thread(target=holder) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert two_ready.wait(timeout=2)
    try:
        with (pytest.raises(c16.I15Denied, match="PROCESS_BUDGET_TIMEOUT"),
              c16.case_slot(tmp_path, timeout=0.075)):
            pytest.fail("admission violated")
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=2)
    assert not any(t.is_alive() for t in threads)
    assert set(results) == {0, 1}
    with c16.case_slot(tmp_path, timeout=1):
        pass


@pytest.mark.parametrize("seconds", (0, -1, 61))
def test_invalid_budget_bound(seconds, tmp_path):
    with (pytest.raises(c16.I15Denied, match="BUDGET_DEADLINE_INVALID"),
          c16.case_slot(tmp_path, timeout=seconds)):
        pytest.fail("invalid deadline admitted")


def test_process_kill_reaps_only_owned_child():
    child = subprocess.Popen(
        [c16.PYTHON, "-B", "-c", "import time;time.sleep(15)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    info = c16.terminate_owned(child)
    assert info["pid"] == child.pid
    assert info["terminated"] and info["reaped"]
    assert child.poll() is not None


def test_clean_process_reap_and_synthetic_actual_recv():
    worktree = Path(__file__).resolve().parents[1]
    rec = c16.run_case(worktree, 2, "positive", "oneproc")
    assert rec["status"] == "COMPLETE", rec
    assert rec["endpoint"].startswith("127.0.0.1:")
    assert rec["client"]["first_data_ns"] < rec["client"]["terminal_ns"]
    assert rec["client"]["received_answer_sha256"] == rec["source_sha256"]
    d = rec["diagnostics"]
    assert d["server_spawn_ns"] <= d["server_ready_ns"] <= d["client_spawn_ns"]
    assert d["client_spawn_ns"] <= d["client_exit_ns"] <= d["server_exit_ns"]
    assert d["cleanup"]["client"]["reaped"]
    assert d["cleanup"]["server"]["reaped"]
    assert d["process_limit"] == 4
    assert d["client_stderr"] == d["server_stderr"] == ""


def test_real_http_500_denied_even_with_recv():
    worktree = Path(__file__).resolve().parents[1]
    rec = c16.run_case(worktree, 1, "server_500", "httpfault")
    assert rec["status"] == "HTTP_NON_200"
    assert rec["client"]["recv_calls"] > 0
    assert rec["diagnostics"]["cleanup"]["server"]["reaped"]


def test_hard_failures_remain_denominator():
    data = [
        {"case_id": f"c{i}", "status": "COMPLETE" if i < 2 else "PROCESS_BUDGET_TIMEOUT",
         "client": {"first_text_ms": 4 if i < 2 else None}}
        for i in range(9)
    ]
    receipt = c16.denominator(data)
    assert receipt["total"] == 9 and receipt["completed"] == 2
    assert receipt["failure_or_abstention"] == 7
    assert receipt["first_text_p95_ms"] is None
    assert receipt["p95_classification"] == "UNKNOWN"


def test_no_external_product_upgrade():
    assert "REAL_APP_CLIENT_ACK_UNVERIFIED" in c16.GATES
    assert "B13_RUNTIME_POSITIVE_BLOCKED" in c16.GATES
    assert "ORIGINAL_523_CITED_RATE_UNVERIFIED" in c16.GATES


@pytest.mark.parametrize("scenario,script,reason", (
    ("silent_boot", "import time;time.sleep(10)", "SERVER_BOOT_TIMEOUT"),
    ("malformed_ready", "import time;print('not-json',flush=True);time.sleep(10)",
     "SERVER_READY_MALFORMED"),
    ("oversized_ready", "import time;print('x'*2400,flush=True);time.sleep(10)",
     "SERVER_READY_TOO_LARGE"),
    ("closed_pipe", "import os,time;os.close(1);time.sleep(10)", "SERVER_BOOT_EOF"),
))
def test_real_child_startup_faults_bounded_and_reaped(scenario, script, reason):
    proc = subprocess.Popen(
        [c16.PYTHON, "-B", "-c", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    try:
        with pytest.raises(c16.I15Denied, match=reason):
            c16.read_server_ready(proc, timeout=.5)
    finally:
        state = c16.terminate_owned(proc)
    assert state["reaped"] and state["owned"], scenario


def test_simulated_fork_resource_exhaustion_retains_attempt(monkeypatch, tmp_path):
    def denied(*args, **kwargs):
        raise OSError("injected EMFILE")
    monkeypatch.setattr(c16.subprocess, "Popen", denied)
    rec = c16.run_case(tmp_path, 1, "positive", "forkfailed")
    assert rec["status"] == "OSERROR_PROCESS_FAILURE"
    assert rec["case_id"].startswith("synthetic-01")
    assert rec["diagnostics"]["failure_stage"] == "server_boot"
    assert rec["diagnostics"]["cleanup"]["server"]["reaped"]
    assert rec["client"]["first_data_ns"] is None


def test_injected_startup_deadline_retains_attempt(monkeypatch):
    monkeypatch.setattr(c16, "BOOT_DEADLINE_SECONDS", .0001)
    worktree = Path(__file__).resolve().parents[1]
    rec = c16.run_case(worktree, 0, "positive", "bootstalled")
    assert rec["status"] == "SERVER_BOOT_TIMEOUT", rec
    assert rec["diagnostics"]["cleanup"]["server"]["reaped"]


def test_injected_client_deadline_kills_reaps_child(monkeypatch):
    monkeypatch.setattr(c16, "CLIENT_DEADLINE_SECONDS", .0001)
    worktree = Path(__file__).resolve().parents[1]
    rec = c16.run_case(worktree, 0, "positive", "clientstalled")
    assert rec["status"] == "CLIENT_SUBPROCESS_TIMEOUT", rec
    assert rec["diagnostics"]["cleanup"]["client"]["terminated"]
    assert rec["diagnostics"]["cleanup"]["client"]["reaped"]
    assert rec["diagnostics"]["cleanup"]["server"]["reaped"]
    assert rec["client"]["first_data_ns"] is None


def test_injected_socket_receive_timeout_keeps_first_text_unknown(monkeypatch):
    class Hung:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def settimeout(self, seconds):
            assert seconds == 3
        def sendall(self, data):
            assert b"GET /i15-native-fixture" in data
        def recv(self, size):
            assert size == 7
            raise TimeoutError("injected receive stall")
    monkeypatch.setattr(c16.socket, "create_connection", lambda *a, **kw: Hung())
    receipt = c16.client(2, 12345, "recvstalled")
    assert receipt["status"] == "SOCKET_TIMEOUTERROR"
    assert receipt["first_data_ns"] is None
    assert receipt["terminal_ns"] is None


def test_duplicate_attempt_namespaces_are_distinct():
    a = c16.run_case(Path(__file__).resolve().parents[1], 0, "positive", "left")
    b = c16.run_case(Path(__file__).resolve().parents[1], 0, "positive", "right")
    assert a["case_id"] != b["case_id"]
    assert a["client"]["client_pid"] != b["client"]["client_pid"]
    assert a["status"] == b["status"] == "COMPLETE"
