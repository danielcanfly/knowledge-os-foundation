"""W5 T14: isolated REAL loopback SSE client receipt, fixture authority only.

No production hooks, provider calls, arbitrary network host, external ACK or
signed attestations. Child PIDs use a real TCP socket on 127.0.0.1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from knowledge_engine import m27_w3_ar08_qa_stream_v1_experimental as ar08

VERSION = "W5T14LocalFirstTextWireProbeV1"
LOCAL_WIRE_PASS = "T14_LOOPBACK_ACTUAL_CLIENT_BYTES_RECEIVED_LOCAL_PASS"
FIRST_PASS = "T14_LOCAL_PRETERMINAL_FIRST_SUBSTANTIVE_TEXT_PASS"
DENIED = (
    "REAL_AUTHENTICATED_CLIENT_ACK_UNVERIFIED",
    "PRODUCTION_PRODUCT_P95_UNVERIFIED",
    "REAL_PROVIDER_AND_SOURCE_RIGHTS_UNVERIFIED",
    "ORIGINAL_523_FINAL_CITED_GATE_UNVERIFIED",
    "REL01_NOT_CERTIFIED",
    "REL02_NOT_AUTHORIZED",
)
HOST = "127.0.0.1"
MAX_EVENT = 65536
MAX_TOTAL = 1048576
MAX_EVENTS = 32
MAX_HEADER = 8192
REQUEST_ID = "t14-fixture-request-001"
TENANT = "t14-fixture-tenant"
ACTOR = "t14-fixture-actor"
TRACE = "t14-fixture-trace"
RUN = "t14-fixture-run"
CITATION = "t14-fixture-citation"
SOURCE = "t14-fixture-source"
REVISION = "t14-fixture-revision-1"
ANSWER = "Alpha βeta, locally cited text.".encode()
SOURCE_BYTES = ANSWER
SOURCE_SHA = hashlib.sha256(SOURCE_BYTES).hexdigest()
MODES = frozenset(
    {
        "positive",
        "progress_only",
        "drop_terminal",
        "disconnect",
        "server_500",
        "wrong_tenant",
        "corrupt_digest",
        "delay_first",
        "corrupt_source",
        "bad_utf8",
        "terminal_early",
    }
)


class WireDenied(ValueError):
    """Non-sensitive stable code for fail-closed local experiments."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise WireDenied(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ns() -> int:
    return time.monotonic_ns()


def identity() -> dict:
    return {
        "request_id": REQUEST_ID,
        "tenant_id": TENANT,
        "actor_id": ACTOR,
        "run_id": RUN,
        "trace_id": TRACE,
    }


@dataclass(frozen=True)
class WireResult:
    status: str
    client_pid: int
    request_ns: int
    first_recv_ns: int | None
    first_data_ns: int | None
    terminal_ns: int | None
    recv_calls: int
    recv_bytes: int
    answer_sha256: str | None
    answer_length: int
    progress_events: int
    answer_events: int

    def as_dict(self) -> dict:
        d = vars(self).copy()
        d.update(
            {
                "fixture": True,
                "trust": "local_loopback_process_only",
                "qualifications": list(DENIED),
                "first_text_ms": (
                    (self.first_data_ns - self.request_ns) / 1e6
                    if self.first_data_ns is not None
                    else None
                ),
                "terminal_ms": (
                    (self.terminal_ns - self.request_ns) / 1e6
                    if self.terminal_ns is not None
                    else None
                ),
            }
        )
        return d


def fixture_adapter(transport: object) -> ar08.NativeQATransportAdapter:
    """AR03 and AR05 ports are explicit local-only *independent mock objects*."""

    class Clock:
        def sample(self) -> ar08.ClockSample:
            return ar08.ClockSample("monotonic_ns", ns(), int(time.time() * 1000))

    class SourcePort:
        def assert_current(
            self, sources: tuple, tenant_id: str, actor_id: str, wall_ms: int
        ) -> None:
            need(tenant_id == TENANT and actor_id == ACTOR, "FIXTURE_SOURCE_AUTHORITY_IDENTITY")
            need(
                all(s.sha256 == sha(s.original_bytes) and s.revision == REVISION for s in sources),
                "FIXTURE_SOURCE_REVOKED",
            )

    class VerificationPort:
        def assert_current(self, proposal: ar08.VerificationProposal, wall_ms: int) -> None:
            need(proposal.verified_answer_sha256 == sha(ANSWER), "FIXTURE_VERIFICATION_FAILED")
            need(proposal.proof_id == "t14-fixture-ar05", "FIXTURE_PROOF_ID")

    wall = int(time.time() * 1000)
    source = ar08.NativeSourceBytes(
        TENANT,
        ACTOR,
        SOURCE,
        CITATION,
        REVISION,
        SOURCE_SHA,
        SOURCE_BYTES,
        "t14-fixture-ar03-observation",
        wall + 120000,
    )
    cite = ar08.CitationByteSpan(
        CITATION,
        SOURCE,
        REVISION,
        SOURCE_SHA,
        0,
        len(SOURCE_BYTES),
        SOURCE_BYTES,
    )
    proposal = ar08.VerificationProposal(
        TENANT,
        ACTOR,
        RUN,
        "t14-fixture-ar05",
        ANSWER,
        sha(ANSWER),
        (ar08.AnswerEvidenceLink(0, len(ANSWER), cite),),
        wall - 1000,
        wall + 120000,
        "t14-fixture-verifier-v1",
    )
    return ar08.NativeQATransportAdapter(
        proposal=proposal,
        sources=(source,),
        source_authority=SourcePort(),
        verification=VerificationPort(),
        transport=transport,
        clock=Clock(),
    )


def frame_dict(frame: ar08.VerifiedTextFrame) -> dict:
    return {
        **identity(),
        "sequence": frame.sequence,
        "start": frame.answer_start_byte,
        "end": frame.answer_end_byte,
        "text": frame.data.decode("utf-8"),
        "sha256": frame.data_sha256,
        "citation_ids": list(frame.citation_ids),
        "source_bindings": [[CITATION, SOURCE, REVISION, SOURCE_SHA]],
        "proof_id": frame.proposal_id,
        "fixture": True,
    }


def encode_event(kind: str, data: dict) -> bytes:
    need(kind in ("progress", "answer", "terminal"), "ILLEGAL_EVENT_TYPE")
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    need(len(raw) < MAX_EVENT and b"\r" not in raw and b"\n" not in raw, "INVALID_SSE_PAYLOAD")
    return b"event: " + kind.encode() + b"\ndata: " + raw + b"\n\n"


def headers(status: int = 200) -> bytes:
    if status != 200:
        return b"HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n"
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; charset=utf-8\r\n"
        b"Cache-Control: no-store\r\nConnection: close\r\n\r\n"
    )


class SSEReceiver:
    """Strict incremental HTTP/SSE decoder over independent recv() chunks."""

    def __init__(self) -> None:
        self.pending = bytearray()
        self.raw_count = 0
        self.header = False
        self.status = "OPEN"
        self.events = 0
        self.progress = 0
        self.answers = 0
        self.offset = 0
        self.answer = bytearray()
        self.first_data_ns: int | None = None
        self.terminal_ns: int | None = None
        self.first_recv_ns: int | None = None

    def feed(self, data: bytes, *, received_ns: int) -> None:
        need(self.status == "OPEN", "STREAM_AFTER_TERMINAL")
        need(type(received_ns) is int and received_ns >= 0, "INVALID_CLIENT_CLOCK")
        if data and self.first_recv_ns is None:
            self.first_recv_ns = received_ns
        self.raw_count += len(data)
        need(self.raw_count <= MAX_TOTAL, "WIRE_TOTAL_OVER_LIMIT")
        self.pending.extend(data)
        if not self.header:
            i = self.pending.find(b"\r\n\r\n")
            need(
                i < MAX_HEADER or (i == -1 and len(self.pending) <= MAX_HEADER),
                "HTTP_HEADER_OVER_LIMIT",
            )
            if i == -1:
                return
            raw = bytes(self.pending[:i])
            del self.pending[: i + 4]
            self._header(raw)
            self.header = True
        while b"\n\n" in self.pending:
            need(self.status == "OPEN", "STREAM_AFTER_TERMINAL")
            n = self.pending.index(b"\n\n")
            need(n < MAX_EVENT, "SSE_EVENT_OVER_LIMIT")
            raw = bytes(self.pending[:n])
            del self.pending[: n + 2]
            self._event(raw, received_ns)
        need(len(self.pending) <= MAX_EVENT, "SSE_EVENT_OVER_LIMIT")

    @staticmethod
    def _header(raw: bytes) -> None:
        need(b"\n" not in raw.replace(b"\r\n", b""), "INVALID_HTTP_HEADER_NEWLINE")
        lines = raw.split(b"\r\n")
        need(lines[0] == b"HTTP/1.1 200 OK", "HTTP_NON_200")
        fields = {}
        for line in lines[1:]:
            need(b":" in line, "INVALID_HTTP_HEADER")
            k, v = line.split(b":", 1)
            key = k.strip().lower()
            need(key not in fields, "DUPLICATE_HTTP_HEADER")
            fields[key] = v.strip().lower()
        need(
            fields.get(b"content-type") == b"text/event-stream; charset=utf-8",
            "HTTP_WRONG_CONTENT_TYPE",
        )
        need(b"content-length" not in fields, "HTTP_FAKE_CONTENT_LENGTH")
        need(b"transfer-encoding" not in fields, "HTTP_UNSUPPORTED_ENCODING")

    def _event(self, raw: bytes, stamp: int) -> None:
        need(b"\r" not in raw, "SSE_CR_AMBIGUOUS")
        lines = raw.split(b"\n")
        need(
            len(lines) == 2 and lines[0].startswith(b"event: ") and lines[1].startswith(b"data: "),
            "MALFORMED_SSE_FIELD",
        )
        try:
            kind = lines[0][7:].decode("ascii")
            text = lines[1][6:].decode("utf-8", "strict")
            payload = json.loads(text)
        except (UnicodeError, ValueError) as exc:
            raise WireDenied("INVALID_SSE_UTF8_OR_JSON") from exc
        need(type(payload) is dict, "INVALID_SSE_JSON_OBJECT")
        self.events += 1
        need(self.events <= MAX_EVENTS, "SSE_EVENT_COUNT_OVER_LIMIT")
        need(kind in ("progress", "answer", "terminal"), "UNKNOWN_SSE_EVENT")
        for k, v in identity().items():
            need(payload.get(k) == v, "FRAME_IDENTITY_MISMATCH_" + k.upper())
        need(payload.get("fixture") is True, "NON_FIXTURE_SPOOF")
        need(
            "signature" not in payload
            and "authenticated_ack" not in payload
            and "product_p95" not in payload,
            "SELF_ASSERTED_EXTERNAL_PROOF",
        )
        if kind == "progress":
            need(self.answers == 0 and self.terminal_ns is None, "LATE_PROGRESS")
            need(
                set(payload) == set(identity()) | {"fixture", "phase"}, "PROGRESS_IMPERSONATES_DATA"
            )
            need(payload.get("phase") == "preparing", "PROGRESS_WRONG_PHASE")
            self.progress += 1
        elif kind == "answer":
            self._answer(payload, stamp)
        else:
            need(self.terminal_ns is None, "DUPLICATE_TERMINAL")
            need(payload.get("status") == "completed", "TERMINAL_NOT_COMPLETE")
            need(self.answers > 0, "PROGRESS_ONLY_NO_FIRST_TEXT")
            need(self.answer == ANSWER, "INCOMPLETE_ANSWER_TERMINAL")
            need(payload.get("answer_sha256") == sha(ANSWER), "TERMINAL_ANSWER_DIGEST_MISMATCH")
            need(
                self.first_data_ns is not None and self.first_data_ns < stamp,
                "FIRST_NOT_BEFORE_TERMINAL",
            )
            self.terminal_ns = stamp
            self.status = "COMPLETE"

    def _answer(self, p: dict, stamp: int) -> None:
        need(
            type(p.get("sequence")) is int and p["sequence"] == self.answers,
            "ANSWER_SEQUENCE_REPLAY_OR_GAP",
        )
        need(
            type(p.get("start")) is int and p["start"] == self.offset, "ANSWER_OFFSET_REPLAY_OR_GAP"
        )
        need(type(p.get("end")) is int, "INVALID_ANSWER_END")
        need(type(p.get("text")) is str and bool(p["text"].strip()), "NON_SUBSTANTIVE_FIRST_TEXT")
        raw = p["text"].encode("utf-8")
        need(len(raw) <= 32768, "ANSWER_FRAME_OVER_LIMIT")
        need(p["end"] == self.offset + len(raw), "ANSWER_END_MISMATCH")
        need(p.get("sha256") == sha(raw), "ANSWER_FRAME_SHA_MISMATCH")
        need(p.get("citation_ids") == [CITATION], "UNBOUND_CITATION")
        need(
            p.get("source_bindings") == [[CITATION, SOURCE, REVISION, SOURCE_SHA]],
            "MUTATED_SOURCE_PIN",
        )
        need(p.get("proof_id") == "t14-fixture-ar05", "WRONG_VERIFIER_PROOF")
        need(ANSWER.startswith(bytes(self.answer) + raw), "ANSWER_NOT_VERIFIED_PREFIX")
        self.answer.extend(raw)
        self.offset += len(raw)
        self.answers += 1
        if self.first_data_ns is None:
            self.first_data_ns = stamp

    def finish(self) -> None:
        need(self.header, "HTTP_TRUNCATED")
        need(not self.pending, "SSE_TRUNCATED")
        need(self.status == "COMPLETE", "MISSING_TERMINAL")


def sample_events() -> list[bytes]:
    """Unit-test fixture built from real accepted AR08 public adapter frames."""

    class Capture:
        def __init__(self) -> None:
            self.frames = []

        def enqueue(self, frame: ar08.VerifiedTextFrame) -> None:
            self.frames.append(frame)

        def flush(self, sequence: int) -> None:
            need(self.frames[-1].sequence == sequence, "AR08_FLUSH_ORDER")

    capture = Capture()
    adapter = fixture_adapter(capture)
    adapter.push(ANSWER, answer_offset=0)
    adapter.terminal()
    return (
        [encode_event("progress", {**identity(), "fixture": True, "phase": "preparing"})]
        + [encode_event("answer", frame_dict(frame)) for frame in capture.frames]
        + [
            encode_event(
                "terminal",
                {
                    **identity(),
                    "fixture": True,
                    "status": "completed",
                    "answer_sha256": sha(ANSWER),
                },
            )
        ]
    )


def parse_bytes(raw: bytes, fragment: int = 13) -> SSEReceiver:
    receiver = SSEReceiver()
    for offset in range(0, len(raw), fragment):
        receiver.feed(raw[offset : offset + fragment], received_ns=ns() + offset)
    receiver.finish()
    return receiver


def server(mode: str) -> None:
    need(mode in MODES, "UNSUPPORTED_FIXTURE_MODE")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        listener.bind((HOST, 0))
        listener.listen(1)
        listener.settimeout(8.0 if mode != "delay_first" else 21.0)
        print(
            json.dumps(
                {
                    "ready": True,
                    "port": listener.getsockname()[1],
                    "server_pid": os.getpid(),
                    "host": HOST,
                }
            ),
            flush=True,
        )
        result = {
            "server_pid": os.getpid(),
            "mode": mode,
            "enqueue_ns": [],
            "flush_ns": [],
            "terminal_ns": None,
            "bytes_sent": 0,
            "server_error": None,
        }
        try:
            conn, peer = listener.accept()
            with conn:
                conn.settimeout(20 if mode == "delay_first" else 5)
                need(peer[0] == HOST, "REMOTE_PEER_DENIED")
                req = bytearray()
                while b"\r\n\r\n" not in req:
                    chunk = conn.recv(512)
                    need(bool(chunk), "MISSING_REQUEST")
                    req.extend(chunk)
                    need(len(req) <= 2048, "REQUEST_OVER_LIMIT")
                expected = (
                    f"GET /fixture-sse HTTP/1.1\r\nHost: {HOST}\r\n"
                    f"X-Request-Id: {REQUEST_ID}\r\n"
                    f"X-Tenant: {TENANT}\r\n\r\n"
                ).encode()
                need(bytes(req) == expected, "REQUEST_IDENTITY_DENIED")

                def send(payload: bytes) -> None:
                    conn.sendall(payload)
                    result["bytes_sent"] += len(payload)

                if mode == "server_500":
                    send(headers(500))
                    return
                send(headers())
                send(
                    encode_event("progress", {**identity(), "fixture": True, "phase": "preparing"})
                )
                if mode == "progress_only":
                    send(
                        encode_event(
                            "terminal",
                            {
                                **identity(),
                                "fixture": True,
                                "status": "completed",
                                "answer_sha256": sha(ANSWER),
                            },
                        )
                    )
                    return
                if mode == "disconnect":
                    return
                if mode == "terminal_early":
                    send(
                        encode_event(
                            "terminal",
                            {
                                **identity(),
                                "fixture": True,
                                "status": "completed",
                                "answer_sha256": sha(ANSWER),
                            },
                        )
                    )
                    return
                if mode == "delay_first":
                    time.sleep(15.05)

                class Transport:
                    def __init__(self) -> None:
                        self.frames: dict[int, ar08.VerifiedTextFrame] = {}

                    def enqueue(self, frame: ar08.VerifiedTextFrame) -> None:
                        self.frames[frame.sequence] = frame
                        result["enqueue_ns"].append(ns())

                    def flush(self, sequence: int) -> None:
                        frame = self.frames.pop(sequence)
                        p = frame_dict(frame)
                        if mode == "wrong_tenant":
                            p["tenant_id"] = "foreign-tenant"
                        if mode == "corrupt_digest":
                            p["sha256"] = sha(b"forged")
                        if mode == "corrupt_source":
                            p["source_bindings"][0][2] = "rev-forged"
                        if mode == "bad_utf8":
                            send(b"event: answer\ndata: \xff\n\n")
                        else:
                            send(encode_event("answer", p))
                        result["flush_ns"].append(ns())

                adapter = fixture_adapter(Transport())
                adapter.push(ANSWER, answer_offset=0)
                state = adapter.terminal()
                result["terminal_ns"] = state.terminal_monotonic_ns
                if mode != "drop_terminal":
                    time.sleep(0.012)
                    send(
                        encode_event(
                            "terminal",
                            {
                                **identity(),
                                "fixture": True,
                                "status": "completed",
                                "answer_sha256": sha(ANSWER),
                            },
                        )
                    )
        except (OSError, WireDenied, ar08.StreamDenied) as exc:
            result["server_error"] = type(exc).__name__ + ":" + str(exc)
        finally:
            print(json.dumps(result, sort_keys=True), flush=True)


def client(port: int) -> dict:
    need(0 < port < 65536, "INVALID_LOOPBACK_PORT")
    start = ns()
    receiver = SSEReceiver()
    calls = total = 0
    error = None
    try:
        with socket.create_connection((HOST, port), timeout=4) as conn:
            conn.settimeout(20)
            request_ns = ns()
            conn.sendall(
                (
                    f"GET /fixture-sse HTTP/1.1\r\nHost: {HOST}\r\n"
                    f"X-Request-Id: {REQUEST_ID}\r\n"
                    f"X-Tenant: {TENANT}\r\n\r\n"
                ).encode()
            )
            while True:
                chunk = conn.recv(19)
                if not chunk:
                    break
                calls += 1
                total += len(chunk)
                receiver.feed(chunk, received_ns=ns())
            receiver.finish()
    except (WireDenied, OSError, TimeoutError) as exc:
        error = (
            str(exc)
            if isinstance(exc, WireDenied)
            else ("CLIENT_SOCKET_" + type(exc).__name__.upper())
        )
    result = WireResult(
        status="COMPLETE" if error is None else error,
        client_pid=os.getpid(),
        request_ns=locals().get("request_ns", start),
        first_recv_ns=receiver.first_recv_ns,
        first_data_ns=receiver.first_data_ns,
        terminal_ns=receiver.terminal_ns,
        recv_calls=calls,
        recv_bytes=total,
        answer_sha256=sha(bytes(receiver.answer)) if receiver.answer else None,
        answer_length=len(receiver.answer),
        progress_events=receiver.progress,
        answer_events=receiver.answers,
    )
    return result.as_dict()


def denominator(cases: list[dict]) -> dict:
    """Every attempt is included; mixed failures make p95 UNKNOWN, not cherry-picked."""
    need(bool(cases), "NO_LATENCY_CASES")
    seen: set[str] = set()
    times = []
    status_counts: dict[str, int] = {}
    for c in cases:
        cid = c.get("case_id")
        need(type(cid) is str and bool(cid) and cid not in seen, "DUPLICATE_OR_MISSING_CASE_ID")
        seen.add(cid)
        s = c.get("status")
        need(type(s) is str and bool(s), "MISSING_CASE_STATUS")
        status_counts[s] = status_counts.get(s, 0) + 1
        duration = c.get("first_text_ms")
        if s == "COMPLETE":
            need(
                type(duration) in (float, int) and math.isfinite(duration) and duration >= 0,
                "INVALID_COMPLETED_DURATION",
            )
            times.append(float(duration))
        else:
            need(
                duration is None
                or (type(duration) in (float, int) and math.isfinite(duration) and duration >= 0),
                "INVALID_NONCOMPLETED_DURATION",
            )
    eligible = len(times) == len(cases)
    p95 = sorted(times)[math.ceil(0.95 * len(times)) - 1] if eligible else None
    return {
        "fixture": True,
        "metric": "LOCAL_CLIENT_REQUEST_TO_FIRST_DATA_MS",
        "total": len(cases),
        "completed": len(times),
        "failures_in_denominator": len(cases) - len(times),
        "status_counts": status_counts,
        "nearest_rank_p95_ms": p95,
        "diagnostic_15s": ("PASS" if p95 <= 15000 else "FAIL") if p95 is not None else "UNKNOWN",
        "product_p95": "PRODUCTION_PRODUCT_P95_UNVERIFIED",
    }


def _child_env(worktree: Path) -> dict:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "PYTHONPATH": str(worktree / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "en_US.UTF-8",
        "LANG": "en_US.UTF-8",
        "PYTHONUTF8": "1",
    }


def probe(
    *,
    worktree: Path,
    scratch: Path,
    modes: tuple[str, ...] = (
        "positive",
        "progress_only",
        "drop_terminal",
        "server_500",
    ),
) -> dict:
    """Process/subprocess evidence. Scratch must be preselected external to Git."""
    need(all(m in MODES for m in modes), "UNSUPPORTED_FIXTURE_MODE")
    need(worktree.is_dir() and (worktree / "src").is_dir(), "INVALID_WORKTREE")
    need(not scratch.resolve().is_relative_to(worktree.resolve()), "SCRATCH_INSIDE_GIT_DENIED")
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch.chmod(0o700)
    python = sys.executable
    prefix = [
        python,
        "-B",
        "-m",
        "knowledge_engine.m27_w5_t14_loopback_first_text_wire_v1_experimental",
    ]
    env = _child_env(worktree)
    cases = []
    for i, mode in enumerate(modes):
        p = subprocess.Popen(
            prefix + ["server", "--mode", mode],
            cwd=worktree,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready = p.stdout.readline()
            info = json.loads(ready)
            need(
                info.get("ready") is True
                and info.get("host") == HOST
                and info.get("server_pid") == p.pid,
                "SERVER_READY_NOT_VERIFIED",
            )
            result = subprocess.run(
                prefix + ["client", "--port", str(info["port"])],
                cwd=worktree,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=23,
                check=False,
            )
            need(result.returncode == 0, "CLIENT_PROCESS_FAILED")
            receipt = json.loads(result.stdout.strip())
            need(
                receipt.get("client_pid") != p.pid and receipt.get("recv_calls", 0) > 0,
                "NO_INDEPENDENT_RECV",
            )
            remaining, err = p.communicate(timeout=6)
            server_receipt = json.loads(remaining.strip())
            need(p.returncode == 0, "SERVER_PROCESS_FAILED")
            case = {
                "case_id": f"loop-{i:02d}-{mode}",
                "mode": mode,
                "server_endpoint": f"{HOST}:{info['port']}",
                "server": server_receipt,
                "client": receipt,
                "client_stderr_sha256": sha(result.stderr.encode()),
                "server_stderr_sha256": sha(err.encode()),
                "status": receipt["status"],
                "first_text_ms": receipt["first_text_ms"],
            }
            cases.append(case)
        finally:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=2)
            if p.stdout:
                p.stdout.close()
            if p.stderr:
                p.stderr.close()
    totals = denominator(cases)
    positive = [c for c in cases if c["mode"] == "positive"]
    need(bool(positive), "MISSING_REAL_SOCKET_POSITIVE")
    v = positive[0]["client"]
    server_v = positive[0]["server"]
    positive_ok = (
        v["status"] == "COMPLETE"
        and v["recv_bytes"] > 0
        and v["answer_sha256"] == sha(ANSWER)
        and v["answer_length"] == len(ANSWER)
        and server_v["enqueue_ns"]
        and server_v["flush_ns"]
        and server_v["terminal_ns"] >= server_v["flush_ns"][0]
        and v["request_ns"] <= v["first_data_ns"] < v["terminal_ns"]
    )
    no_fake = any(
        c["mode"] == "progress_only" and c["status"] == "PROGRESS_ONLY_NO_FIRST_TEXT" for c in cases
    )
    receipt = {
        "version": VERSION,
        "fixture": True,
        "trust": "actual separate local loopback PIDs, no real app ACK",
        "positive_actual_wire": bool(positive_ok),
        "progress_only_rejected": no_fake,
        "status": ("T14_LOCAL_WIRE_PASS" if positive_ok and no_fake else "T14_BLOCKED"),
        "qualifications": list(DENIED),
        "local_loopback_gate": LOCAL_WIRE_PASS if positive_ok else "T14_REAL_WIRE_NOT_VERIFIED",
        "first_text_gate": FIRST_PASS if positive_ok and no_fake else "T14_FIRST_TEXT_NOT_VERIFIED",
        "source_sha256": SOURCE_SHA,
        "source_revision": REVISION,
        "verified_answer_sha256": sha(ANSWER),
        "latency": totals,
        "cases": cases,
    }
    blob = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    artifact = scratch / "T14_REAL_LOOPBACK_SOCKET_RECEIPT.json"
    artifact.write_bytes(blob)
    artifact.chmod(0o600)
    return {
        "receipt_path": str(artifact),
        "receipt_sha256": sha(blob),
        "status": receipt["status"],
        "denominator": totals,
        "qualifications": list(DENIED),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("server", "client", "probe"))
    parser.add_argument("--mode", choices=sorted(MODES), default="positive")
    parser.add_argument("--port", type=int)
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    if args.action == "server":
        server(args.mode)
    elif args.action == "client":
        need(args.port is not None, "MISSING_LOOPBACK_PORT")
        print(json.dumps(client(args.port), sort_keys=True), flush=True)
    else:
        need(args.worktree is not None and args.scratch is not None, "MISSING_PROBE_PATHS")
        print(
            json.dumps(probe(worktree=args.worktree, scratch=args.scratch), sort_keys=True),
            flush=True,
        )


if __name__ == "__main__":
    main()
