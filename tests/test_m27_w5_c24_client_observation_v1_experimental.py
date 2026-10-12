"""C24 all-fault client observation tests: independent synthetic calibration only."""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_c24_client_observation_v1_experimental as c24

ANSWER = "河內咖啡 rất ngon ☕".encode()
SOURCE = ANSWER + b" source suffix"
RUNNER = c24.sha(b"synthetic-runner")
CANDIDATE = c24.sha(b"synthetic-candidate")
HEADER = (b"HTTP/1.1 200 OK\r\n"
          b"Content-Type: text/event-stream; charset=utf-8\r\n\r\n")


def plan(index=0, cited=True):
    return c24.CasePlan(
        f"case-{index:04d}", f"request-{index:04d}", f"nonce-{index:04d}",
        RUNNER, CANDIDATE, cited, synthetic=True,
    )


def source():
    return c24.SourcePin("cite-one", "source-one", "revision-1",
                         c24.sha(SOURCE), SOURCE, authorized=True)


def payload(case=None):
    p = case or plan()
    return {key: getattr(p, key) for key in c24.IDENTITY}


def link(data=ANSWER):
    return {
        "citation_id": "cite-one", "source_id": "source-one",
        "revision": "revision-1", "source_sha256": c24.sha(SOURCE),
        "source_start": 0, "source_end": len(ANSWER),
        "quote_sha256": c24.sha(ANSWER),
        "answer_start": 0, "answer_end": len(data),
    }


def answer(case=None, data=ANSWER):
    return {
        **payload(case), "sequence": 0, "start": 0, "end": len(data),
        "text": data.decode(), "sha256": c24.sha(data),
        "citations": [link(data)],
    }


def terminal(case=None, data=ANSWER):
    return {**payload(case), "status": "completed",
            "answer_sha256": c24.sha(data), "answer_bytes": len(data)}


def stream(case=None, answer_frame=None, terminal_frame=None, include_progress=True):
    s = HEADER
    if include_progress:
        s += c24.make_test_frame("progress", {**payload(case), "phase": "preparing"})
    s += c24.make_test_frame("answer", answer_frame or answer(case))
    s += c24.make_test_frame("terminal", terminal_frame or terminal(case))
    return s


class Clock:
    def __init__(self):
        self.now = 1_000_000_000

    def __call__(self):
        self.now += 1_000_000
        return self.now


def capture(case=None, pins=None, clock=None):
    return c24.ClientCapture(case or plan(), [source()] if pins is None else pins,
                             clock_ns=clock or Clock(), client_pid=31415,
                             client_process_nonce="fixture-client-process-0001")


def run(raw, chunk=17, case=None):
    c = capture(case=case)
    c.admit()
    for i in range(0, len(raw), chunk):
        c.feed(raw[i:i + chunk])
    return c.close()


def test_complete_preterminal_source_bound_and_clock():
    result = run(stream())
    assert result["status"] == "COMPLETE"
    assert result["request_admitted_ns"] <= result["first_recv_ns"]
    assert result["first_substantive_text_ns"] < result["terminal_ns"]
    assert result["answer_bytes"] == len(ANSWER)
    assert result["answer_sha256"] == c24.sha(ANSWER)
    assert result["source_native_citations"][0]["revision"] == "revision-1"
    assert result["custody"]["status"] == "UNKNOWN"
    assert result["official_qualified"] is False


@pytest.mark.parametrize("size", [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 19, 23, 29,
    31, 32, 37, 41, 43, 47, 59, 67, 71, 79, 97, 101, 127
])
def test_partial_sse_and_split_utf8_chunk_sizes(size):
    assert run(stream(), chunk=size)["status"] == "COMPLETE"


# Each mutation represents a separately executed denied/tampered frame.
@pytest.mark.parametrize("field,bad", [
    ("case_id", "wrong"), ("request_id", "wrong"), ("nonce", "replay"),
    ("runner_sha256", c24.sha(b"wrong")), ("candidate_sha256", c24.sha(b"wrong")),
    ("sequence", -1), ("sequence", 1), ("sequence", True),
    ("start", -1), ("start", 1), ("start", True),
    ("end", -1), ("end", 1), ("end", False),
    ("text", ""), ("text", "  "), ("text", 3),
    ("sha256", c24.sha(b"tamper")), ("sha256", ""),
    ("citations", []), ("citations", None), ("citations", "fake"),
    ("authenticated_ack", "yes"), ("signature", "self"), ("production_authorized", True),
])
def test_hostile_answer_payloads_are_denied(field, bad):
    frame = answer()
    frame[field] = bad
    with pytest.raises(c24.ObservationDenied):
        run(stream(answer_frame=frame))


@pytest.mark.parametrize("field,bad", [
    ("citation_id", "unknown"), ("source_id", "other"),
    ("revision", "old"), ("source_sha256", c24.sha(b"wrong")),
    ("source_start", -1), ("source_start", 1000),
    ("source_end", -1), ("source_end", 1000),
    ("source_start", True), ("source_end", True),
    ("quote_sha256", c24.sha(b"wrong")),
    ("answer_start", -1), ("answer_start", 1000),
    ("answer_end", -1), ("answer_end", 1000),
    ("answer_start", True), ("answer_end", True),
])
def test_invalid_source_native_span_fails_closed(field, bad):
    frame = answer()
    frame["citations"][0][field] = bad
    with pytest.raises(c24.ObservationDenied):
        run(stream(answer_frame=frame))


@pytest.mark.parametrize("field,bad", [
    ("case_id", "wrong"), ("request_id", "wrong"), ("nonce", "duplicate"),
    ("runner_sha256", c24.sha(b"wrong")), ("candidate_sha256", c24.sha(b"wrong")),
    ("status", "error"), ("answer_sha256", c24.sha(b"wrong")),
    ("answer_bytes", 0), ("answer_bytes", True),
    ("authenticated_ack", True), ("signature", "self"),
])
def test_terminal_tampering_denied(field, bad):
    frame = terminal()
    frame[field] = bad
    with pytest.raises(c24.ObservationDenied):
        run(stream(terminal_frame=frame))


@pytest.mark.parametrize("mutation", [
    lambda x: x.replace(b"HTTP/1.1 200 OK", b"HTTP/1.1 500 BAD"),
    lambda x: x.replace(b"text/event-stream", b"application/json"),
    lambda x: x.replace(b"event: answer", b"event: unknown"),
    lambda x: x.replace(b"event: answer", b"event: errorish"),
    lambda x: x.replace(b"data: ", b"date: "),
    lambda x: x.replace(b"event: ", b"event: \xff", 1),
    lambda x: x.replace(b"\n\n", b"\r\n", 1),
    lambda x: x + b"event: answer\ndata: {}\n\n",
])
def test_wire_corruption_denied(mutation):
    with pytest.raises(c24.ObservationDenied):
        run(mutation(stream()))


def test_progress_only_must_not_count_as_first_text():
    c = capture()
    c.admit()
    c.feed(HEADER + c24.make_test_frame("progress",
                                        {**payload(), "phase": "preparing"}))
    r = c.close("timeout")
    assert r["status"] == "TIMEOUT"
    assert r["first_substantive_text_ns"] is None
    assert r["full_response_latency_ms"] is None


@pytest.mark.parametrize("reason", ["disconnect", "timeout", "cancelled", "rejected"])
def test_partial_answer_missing_terminal_fails(reason):
    c = capture()
    c.admit()
    c.feed(HEADER + c24.make_test_frame("answer", answer()))
    r = c.close(reason)
    assert r["status"] != "COMPLETE"
    assert r["answer_sha256"] is None
    assert r["first_substantive_text_ns"] is not None
    assert r["full_response_latency_ms"] is None


def test_no_response_retained_as_timeout():
    c = capture()
    c.admit()
    r = c.close("timeout")
    assert r["recv_calls"] == 0 and r["status"] == "TIMEOUT"


def test_server_error_retained_not_success():
    c = capture()
    c.admit()
    c.feed(HEADER + c24.make_test_frame(
        "error", {**payload(), "code": "BROKEN_PROVIDER"}))
    r = c.close()
    assert r["status"] == "ERROR"
    assert r["full_response_latency_ms"] is None


def test_terminal_before_answer_denied():
    with pytest.raises(c24.ObservationDenied):
        run(HEADER + c24.make_test_frame("terminal", terminal()))


def test_duplicate_terminal_denied():
    with pytest.raises(c24.ObservationDenied):
        run(stream() + c24.make_test_frame("terminal", terminal()))


def test_nonce_replay_between_case_and_process():
    a = plan()
    out = c24.evaluate_cohort([a] * 341, [], synthetic_calibration=True)
    assert out["decision"] == "UNKNOWN"
    assert out["reason"] == "PLAN_DUPLICATE"


@pytest.mark.parametrize("change", [
    {"revoked": True}, {"authorized": False}, {"source_sha256": c24.sha(b"wrong")},
    {"revision": ""}, {"citation_id": ""}, {"source_id": ""},
])
def test_source_authority_revocation_and_tamper(change):
    with pytest.raises(c24.ObservationDenied):
        capture(pins=[replace(source(), **change)])


def test_monotonic_clock_regression_denied():
    stamps = iter([100, 101, 99])
    c = capture(clock=lambda: next(stamps))
    c.admit()
    c.feed(HEADER[:4])
    with pytest.raises(c24.ObservationDenied, match="CLOCK_REGRESSION"):
        c.feed(HEADER[4:])


def test_duplicate_admission_and_double_close():
    c = capture()
    c.admit()
    with pytest.raises(c24.ObservationDenied):
        c.admit()
    c.close("timeout")
    with pytest.raises(c24.ObservationDenied):
        c.close()


def test_self_asserted_ack_not_accepted():
    r = run(stream())
    assert c24.independent_custody(r, None, None, None)["status"] == "UNKNOWN"
    grant = {"issuer": "owner", "role": "external_controller",
             "payload": dict(r), "signature": "self"}
    ack = {"issuer": "self", "role": "independent_client",
           "payload": dict(r), "signature": "self"}
    assert c24.independent_custody(r, grant, ack,
                                   {"owner": "", "self": ""})["status"] == "UNKNOWN"


def synthetic_cohort(size):
    plans = [plan(i) for i in range(size)]
    recs = []
    for i, case in enumerate(plans):
        r = run(stream(case), case=case)
        r["client_process_nonce"] = "process-" + str(i)
        # Values are synthetic, only the rank math is calibrated.
        r["request_admitted_ns"] = 10
        r["first_substantive_text_ns"] = 1_000_000
        r["terminal_ns"] = (i + 1) * 1_000_000 + 10
        r["full_response_latency_ms"] = i + 1
        recs.append(r)
    return plans, recs


@pytest.mark.parametrize("size,rank", [(341, 324), (237, 226)])
def test_exact_nearest_rank_only_synthetic_calibration(size, rank):
    p, recs = synthetic_cohort(size)
    out = c24.evaluate_cohort(p, recs, synthetic_calibration=True)
    assert out["rank"] == rank
    assert out["decision"] == "SYNTHETIC_CALIBRATION_ONLY"
    assert out["synthetic_calibration_p95_ms"] == rank
    assert out["all_outcome_p95_ms"] is None


@pytest.mark.parametrize("change", ["missing", "duplicate", "timeout",
                                     "latency", "wrong_digest", "false_actual",
                                     "wrong_nonce", "wrong_pid", "no_citations"])
def test_denominator_and_auth_failure_never_false_pass(change):
    p, r = synthetic_cohort(237)
    if change == "missing":
        r.pop()
    elif change == "duplicate":
        r[1] = r[0]
    elif change == "timeout":
        r[1]["status"] = "TIMEOUT"
    elif change == "latency":
        r[1]["full_response_latency_ms"] = -2
    elif change == "wrong_digest":
        r[1]["answer_sha256"] = "bad"
    elif change == "false_actual":
        r[1]["synthetic"] = False
    elif change == "wrong_nonce":
        r[1]["nonce"] = "replayed"
    elif change == "wrong_pid":
        r[1]["client_process_nonce"] = r[0]["client_process_nonce"]
        r[1]["nonce"] = r[0]["nonce"]
    else:
        r[1]["source_native_citations"] = []
    out = c24.evaluate_cohort(p, r, synthetic_calibration=True)
    assert out["all_outcome_p95_ms"] is None
    assert out["decision"] == "UNKNOWN"


def test_synthetic_official_p95_always_unknown():
    p, r = synthetic_cohort(341)
    out = c24.evaluate_cohort(p, r)
    assert out["all_outcome_p95_ms"] is None
    assert out["decision"] == "UNKNOWN"


@pytest.mark.parametrize("bad", [
    {"case_id": "../escape"}, {"nonce": ""}, {"runner_sha256": "unsigned"},
    {"candidate_sha256": ""}, {"synthetic": "false"},
    {"expected_citation": 1}, {"client_role": "bad role"},
])
def test_plan_validation_denied(bad):
    with pytest.raises(c24.ObservationDenied):
        c24.ClientCapture(replace(plan(), **bad), [source()])


def test_real_separate_os_client_synthetic_tcp_capture(tmp_path: Path):
    """Actual kernel socket and independent child PID, never external app proof."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    errs = []

    def serve():
        try:
            conn, _ = server.accept()
            with conn:
                conn.settimeout(4)
                assert conn.recv(1024).startswith(b"GET /synthetic")
                for offset in range(0, len(stream()), 13):
                    conn.sendall(stream()[offset:offset + 13])
        except (OSError, AssertionError) as exc:
            errs.append(str(exc))
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    manifest = {
        "plan": vars(plan()),
        "source": {
            "citation_id": "cite-one", "source_id": "source-one",
            "revision": "revision-1", "source_sha256": c24.sha(SOURCE),
            "authorized": True, "bytes_b64": base64.b64encode(SOURCE).decode(),
        }
    }
    plan_file = tmp_path / "synthetic_plan.json"
    out_file = tmp_path / "os_client_capture.json"
    plan_file.write_text(json.dumps(manifest))
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.run([
        sys.executable, "-m",
        "knowledge_engine.m27_w5_c24_client_observation_v1_experimental",
        "--synthetic-loopback-port", str(port),
        "--plan-json", str(plan_file), "--output", str(out_file),
    ], capture_output=True, timeout=20, env=env, check=False)
    thread.join(timeout=5)
    assert not errs
    assert child.returncode == 0, child.stderr.decode()
    data = json.loads(out_file.read_text())
    assert data["status"] == "COMPLETE"
    assert data["client_pid"] != os.getpid()
    assert data["first_substantive_text_ns"] < data["terminal_ns"]
    assert data["synthetic"] is True
    assert data["official_qualified"] is False



def test_live_authority_revocation_after_admit_denies_first_text():
    state = {"valid": True}
    c = c24.ClientCapture(plan(), [source()], clock_ns=Clock(),
                          source_current=lambda _: state["valid"])
    c.admit()
    c.feed(HEADER + c24.make_test_frame("progress",
                                        {**payload(), "phase": "preparing"}))
    state["valid"] = False
    with pytest.raises(c24.ObservationDenied, match="SOURCE_REVOKED_AFTER_ADMISSION"):
        c.feed(c24.make_test_frame("answer", answer()))


def test_live_authority_revocation_before_terminal_denies_completion():
    state = {"valid": True}
    c = c24.ClientCapture(plan(), [source()], clock_ns=Clock(),
                          source_current=lambda _: state["valid"])
    c.admit()
    c.feed(HEADER + c24.make_test_frame("answer", answer()))
    state["valid"] = False
    with pytest.raises(c24.ObservationDenied, match="SOURCE_REVOKED_BEFORE_TERMINAL"):
        c.feed(c24.make_test_frame("terminal", terminal()))


def test_non_synthetic_without_current_source_controller_denied():
    with pytest.raises(c24.ObservationDenied,
                       match="REAL_SOURCE_AUTHORITY_CALLBACK_MISSING"):
        c24.ClientCapture(replace(plan(), synthetic=False), [source()])


def test_duplicate_native_citation_ids_denied():
    with pytest.raises(c24.ObservationDenied, match="DUPLICATE_SOURCE_PIN"):
        c24.ClientCapture(plan(), [source(), source()])


@pytest.mark.parametrize("tamper", [
    "grant_signature", "ack_signature", "grant_nonce", "ack_candidate",
    "wrong_role", "wrong_ack_digest", "same_signer", "unknown_controller",
])
def test_signed_fixture_custody_tamper_fails_closed(tamper):
    cryptography = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    a, b = cryptography.Ed25519PrivateKey.generate(), cryptography.Ed25519PrivateKey.generate()

    def pub(priv):
        raw = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode()

    r = run(stream())
    r["synthetic"] = False  # Cryptographic fixture, not a real app authorization.
    gp = {**{key: r[key] for key in c24.IDENTITY},
          "role": "controller", "scope": "native_client_evaluation",
          "source_rights_verified": True, "allow": True}
    ap = {**{key: r[key] for key in c24.IDENTITY},
          "client_observed": True, "client_pid": r["client_pid"],
          "client_process_nonce": r["client_process_nonce"],
          "observation_sha256": c24.sha(c24.canonical({
              key: value for key, value in r.items() if key != "custody"
          }))}
    if tamper == "grant_nonce":
        gp["nonce"] = "fake"
    elif tamper == "ack_candidate":
        ap["candidate_sha256"] = c24.sha(b"imposter")
    elif tamper == "wrong_role":
        gp["role"] = "self"
    elif tamper == "wrong_ack_digest":
        ap["observation_sha256"] = c24.sha(b"wrong")
    grant = {"role": "external_controller", "issuer": "controller",
             "payload": gp, "signature": base64.b64encode(
                 a.sign(c24.canonical(gp))).decode()}
    ack = {"role": "independent_client", "issuer": "client",
           "payload": ap, "signature": base64.b64encode(
               b.sign(c24.canonical(ap))).decode()}
    roots = {"controller": pub(a), "client": pub(b)}
    if tamper == "grant_signature":
        grant["signature"] = base64.b64encode(bytes(64)).decode()
    elif tamper == "ack_signature":
        ack["signature"] = base64.b64encode(bytes(64)).decode()
    elif tamper == "same_signer":
        ack["issuer"] = "controller"
    elif tamper == "unknown_controller":
        roots.pop("controller")
    result = c24.independent_custody(r, grant, ack, roots)
    if tamper in ("grant_nonce", "ack_candidate", "wrong_role", "wrong_ack_digest",
                  "grant_signature", "ack_signature", "same_signer", "unknown_controller"):
        assert result["status"] == "UNKNOWN"


def test_valid_signed_fixture_is_only_review_required():
    cryptography = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    a, b = cryptography.Ed25519PrivateKey.generate(), cryptography.Ed25519PrivateKey.generate()
    r = run(stream())
    r["synthetic"] = False  # Only a CRYPTO fixture; no true independent authority.
    gp = {key: r[key] for key in c24.IDENTITY}
    gp.update(scope="native_client_evaluation", allow=True,
              source_rights_verified=True)
    ap = {key: r[key] for key in c24.IDENTITY}
    ap.update(client_observed=True, client_pid=r["client_pid"],
              client_process_nonce=r["client_process_nonce"],
              observation_sha256=c24.sha(c24.canonical({
                  k: v for k, v in r.items() if k != "custody"
              })))
    def encode_key(x):
        return base64.b64encode(x.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )).decode()
    grant = {"role": "external_controller", "issuer": "controller",
             "payload": gp, "signature": base64.b64encode(
                 a.sign(c24.canonical(gp))).decode()}
    ack = {"role": "independent_client", "issuer": "client",
           "payload": ap, "signature": base64.b64encode(
               b.sign(c24.canonical(ap))).decode()}
    status = c24.independent_custody(
        r, grant, ack, {"controller": encode_key(a), "client": encode_key(b)}
    )
    assert status["status"] == "SIGNATURE_VERIFIED_EXTERNAL_REVIEW_REQUIRED"
    assert status["status"] != "INDEPENDENTLY_ADMITTED"
