"""I15 independent multi-case local Native Client HTTP/SSE experiment.

Synthetic-only citations. Actual 127.0.0.1 server/client child processes and
client recv timing. No real app ACK, external rights, Provider or production.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import select
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from knowledge_engine import m27_w3_ar08_qa_stream_v1_experimental as ar08
from knowledge_engine import m27_w4_t09_transport_evidence_v1_experimental as t09
from knowledge_engine import m27_w5_t14_loopback_first_text_wire_v1_experimental as t14

VERSION = "W5I15NativeLocalClientIntegrationV1"
PASS = "I15_LOCAL_MULTICASE_WIRE_PASS"
FAIL = "I15_WIRE_NOT_VERIFIED"
HOST = "127.0.0.1"
PYTHON = "/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python"
GATES = (
    "REAL_APP_CLIENT_ACK_UNVERIFIED",
    "REAL_PROVIDER_AND_RIGHTS_UNVERIFIED",
    "ORIGINAL_523_CITED_RATE_UNVERIFIED",
    "PRODUCT_P95_UNVERIFIED",
    "W4_AR09_PHASE_B_BLOCKED",
    "REL01_NOT_CERTIFIED",
    "REL02_NOT_AUTHORIZED",
    "B13_RUNTIME_POSITIVE_BLOCKED",
)
FAULT_MODES = (
    "progress_only", "drop_terminal", "server_500", "disconnect",
    "wrong_tenant", "wrong_revision", "wrong_source_sha", "wrong_trace",
    "wrong_citation", "bad_utf8", "duplicate_frame", "duplicate_terminal",
    "forged_ack", "revoke_after_enqueue", "expire_after_enqueue",
    "timeout_first",
)
IDENTITIES = ("request_id", "run_id", "trace_id", "tenant_id", "actor_id")
FIELDS = set(IDENTITIES) | {
    "fixture", "sequence", "start", "end", "text", "sha256", "citation_ids",
    "source_bindings", "proof_id", "source_rights", "consent", "claim_start",
    "claim_end", "claim_sha256",
}
PHRASES = (
    "案例零：臺北雨後有彩虹 🌈", "案例一：河內咖啡 rất ngon ☕",
    "案例二：東京の桜が咲く 🌸", "案例三：서울 날씨 맑음",
    "案例四：Singapore 你好世界", "案例五：香港電車叮叮",
    "案例六：曼谷市場สวัสดี", "案例七：高雄海風溫柔",
    "案例八：大阪たこ焼き熱々", "案例九：新竹科學園區",
    "案例十：檳城的街道很熱鬧", "案例十一：峴港夕陽美麗",
)


class I15Denied(ValueError):
    """Closed-denial code, never a delivery claim."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise I15Denied(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_ns() -> int:
    return time.monotonic_ns()


def spec(index: int, namespace: str = "") -> dict:
    require(type(namespace) is str and len(namespace) <= 40
            and all(ch.isascii() and (ch.isalnum() or ch in "_-")
                    for ch in namespace), "NAMESPACE_INVALID")
    require(type(index) is int and 0 <= index < len(PHRASES), "UNKNOWN_CASE")
    text = PHRASES[index]
    answer = text.encode("utf-8")
    suffix = f"-{namespace}" if namespace else ""
    return {
        "case_id": f"synthetic-{index:02d}{suffix}",
        "request_id": f"i15-req-{index:02d}{suffix}",
        "run_id": f"i15-run-{index:02d}{suffix}",
        "trace_id": f"i15-trace-{index:02d}{suffix}",
        "tenant_id": f"i15-tenant-{index % 3:02d}{suffix}",
        "actor_id": f"i15-actor-{index:02d}{suffix}",
        "source_id": f"i15-source-{index:02d}",
        "source_revision": f"fixture-r{index + 1:02d}",
        "citation_id": f"i15-citation-{index:02d}",
        "proof_id": f"i15-ar05-proposal-{index:02d}",
        "source_sha256": sha(answer),
        "answer_sha256": sha(answer),
        "claim_sha256": sha(answer),
        "answer_bytes": answer,
        "text": text,
    }


def identity(s: dict) -> dict:
    return {key: s[key] for key in IDENTITIES}


def source_pin(s: dict) -> list:
    return [s["citation_id"], s["source_id"], s["source_revision"], s["source_sha256"]]


def frame_payload(s: dict, frame: ar08.VerifiedTextFrame) -> dict:
    return {
        **identity(s), "fixture": True, "sequence": frame.sequence,
        "start": frame.answer_start_byte, "end": frame.answer_end_byte,
        "text": frame.data.decode("utf-8"), "sha256": frame.data_sha256,
        "citation_ids": list(frame.citation_ids),
        "source_bindings": [source_pin(s)], "proof_id": frame.proposal_id,
        "source_rights": "local_fixture_current", "consent": "local_fixture_granted",
        "claim_start": 0, "claim_end": len(s["answer_bytes"]),
        "claim_sha256": s["claim_sha256"],
    }


def fixture_adapter(
    s: dict, transport: object, ledger: dict | None = None
) -> ar08.NativeQATransportAdapter:
    """Genuine AR08 native adapter, source and proposal authority are local fakes."""
    state = ledger if ledger is not None else {"revoked": False, "expired": False}
    wall = int(time.time() * 1000)
    data = s["answer_bytes"]

    class Clock:
        def sample(self) -> ar08.ClockSample:
            return ar08.ClockSample("monotonic_ns", now_ns(), int(time.time() * 1000))

    class Authority:
        def assert_current(
            self, sources: tuple, tenant_id: str, actor_id: str, wall_ms: int
        ) -> None:
            require(
                (tenant_id, actor_id) == (s["tenant_id"], s["actor_id"]),
                "SOURCE_PRINCIPAL_DENIED",
            )
            require(not state.get("revoked"), "SOURCE_CONSENT_REVOKED")
            require(not state.get("expired"), "SOURCE_RIGHTS_EXPIRED")
            for src in sources:
                pin = t09.SourcePin(
                    src.native_citation_id, src.source_id, src.revision,
                    src.sha256, src.tenant_id, src.actor_id, wall_ms - 1,
                    wall_ms + 60000, bool(state.get("revoked")),
                )
                require(pin.rights_issued_wall_ms <= wall_ms < pin.rights_expires_wall_ms,
                        "SOURCE_RIGHTS_INVALID")
                require(
                    pin.source_id == s["source_id"]
                    and pin.revision == s["source_revision"]
                    and pin.sha256 == sha(src.original_bytes),
                    "SOURCE_REVISION_OR_DIGEST_CHANGED",
                )

    class Verifier:
        def assert_current(self, proposal: ar08.VerificationProposal, wall_ms: int) -> None:
            require(proposal.proof_id == s["proof_id"], "LOCAL_PROPOSAL_CHANGED")
            require(proposal.verified_answer_sha256 == sha(data), "LOCAL_ANSWER_CHANGED")

    source = ar08.NativeSourceBytes(
        s["tenant_id"], s["actor_id"], s["source_id"], s["citation_id"],
        s["source_revision"], s["source_sha256"], data,
        "i15-locally-observed-not-issuer", wall + 60000,
    )
    citation = ar08.CitationByteSpan(
        s["citation_id"], s["source_id"], s["source_revision"],
        s["source_sha256"], 0, len(data), data,
    )
    proposal = ar08.VerificationProposal(
        s["tenant_id"], s["actor_id"], s["run_id"], s["proof_id"],
        data, sha(data), (ar08.AnswerEvidenceLink(0, len(data), citation),),
        wall - 1000, wall + 60000, "i15-fixture-verifier-only",
    )
    return ar08.NativeQATransportAdapter(
        proposal=proposal, sources=(source,), source_authority=Authority(),
        verification=Verifier(), transport=transport, clock=Clock(),
    )


def push_synthetic_answer(s: dict, adapter: ar08.NativeQATransportAdapter) -> None:
    """Deliberately split inside the first CJK UTF-8 code point."""
    raw = s["answer_bytes"]
    for start, end in ((0, 1), (1, 3), (3, len(raw))):
        if end > start:
            adapter.push(raw[start:end], answer_offset=start)
    adapter.terminal()


class Receiver:
    """No progress is first text. Strict case-bound incremental HTTP/SSE decoder."""

    def __init__(self, s: dict) -> None:
        self.s = s
        self.pending = bytearray()
        self.header = False
        self.total = 0
        self.first_recv_ns = None
        self.first_data_ns = None
        self.terminal_ns = None
        self.progress = 0
        self.answers = 0
        self.answer = bytearray()
        self.closed = False

    def feed(self, chunk: bytes, stamp: int) -> None:
        require(not self.closed, "DATA_AFTER_TERMINAL")
        require(type(stamp) is int and stamp >= 0, "CLOCK_BAD")
        if chunk and self.first_recv_ns is None:
            self.first_recv_ns = stamp
        self.total += len(chunk)
        require(self.total <= 1048576, "WIRE_BYTES_OVER_LIMIT")
        self.pending.extend(chunk)
        if not self.header:
            cut = self.pending.find(b"\r\n\r\n")
            require(cut < 8192 or (cut == -1 and len(self.pending) <= 8192),
                    "HTTP_HEADER_TOO_LONG")
            if cut < 0:
                return
            raw = bytes(self.pending[:cut])
            del self.pending[:cut + 4]
            t14.SSEReceiver._header(raw)
            self.header = True
        while b"\n\n" in self.pending:
            require(not self.closed, "EVENT_AFTER_TERMINAL")
            cut = self.pending.index(b"\n\n")
            require(cut < 65536, "EVENT_TOO_LONG")
            raw = bytes(self.pending[:cut])
            del self.pending[:cut + 2]
            require(b"\r" not in raw, "SSE_CR_FORBIDDEN")
            lines = raw.split(b"\n")
            require(len(lines) == 2 and lines[0].startswith(b"event: ")
                    and lines[1].startswith(b"data: "), "SSE_MALFORMED")
            try:
                kind = lines[0][7:].decode("ascii")
                payload = json.loads(lines[1][6:].decode("utf-8", "strict"))
            except (UnicodeError, ValueError) as exc:
                raise I15Denied("SSE_UTF8_JSON_INVALID") from exc
            self.event(kind, payload, stamp)
        require(len(self.pending) < 65536, "SSE_PENDING_OVER_LIMIT")

    def event(self, kind: str, p: dict, stamp: int) -> None:
        require(type(p) is dict, "PAYLOAD_NOT_OBJECT")
        require(kind in ("progress", "answer", "terminal"), "UNKNOWN_EVENT")
        s = self.s
        for key, expected in identity(s).items():
            require(p.get(key) == expected, "BOUND_IDENTITY_" + key.upper())
        require(p.get("fixture") is True, "SYNTHETIC_STATUS_REQUIRED")
        require(not (set(p) & {
            "authenticated_ack", "signature", "product_p95", "real_provider",
            "cost_attestation", "image_digest", "release_certified",
        }), "FORGED_EXTERNAL_AUTHORITY")
        if kind == "progress":
            require(self.answers == 0 and not self.closed, "LATE_PROGRESS")
            require(set(p) == set(IDENTITIES) | {"fixture", "phase"}, "PROGRESS_SPOOF")
            require(p.get("phase") == "preparing", "PROGRESS_INVALID")
            self.progress += 1
            return
        if kind == "terminal":
            require(not self.closed, "DUPLICATE_TERMINAL")
            require(set(p) == set(IDENTITIES) | {
                "fixture", "status", "answer_sha256"
            }, "TERMINAL_SPOOF")
            require(p["status"] == "completed", "TERMINAL_NOT_COMPLETE")
            require(self.answers > 0, "PROGRESS_ONLY_NOT_FIRST_TEXT")
            require(bytes(self.answer) == s["answer_bytes"], "TERMINAL_INCOMPLETE")
            require(p["answer_sha256"] == sha(bytes(self.answer)), "TERMINAL_SHA_CHANGED")
            require(self.first_data_ns is not None and self.first_data_ns < stamp,
                    "TERMINAL_NOT_AFTER_FIRST_TEXT")
            self.terminal_ns = stamp
            self.closed = True
            return
        require(set(p) == FIELDS, "ANSWER_FIELDS_NOT_EXACT")
        require(type(p.get("sequence")) is int and p["sequence"] == self.answers,
                "FRAME_SEQUENCE_REPLAY_GAP")
        require(type(p.get("start")) is int and p["start"] == len(self.answer),
                "FRAME_BYTE_OFFSET_REPLAY_GAP")
        require(type(p.get("text")) is str and bool(p["text"].strip()), "EMPTY_TEXT")
        data = p["text"].encode("utf-8")
        require(type(p.get("end")) is int
                and p["end"] == len(self.answer) + len(data), "FRAME_END_CHANGED")
        require(p.get("sha256") == sha(data), "FRAME_SHA_CHANGED")
        require(p.get("citation_ids") == [s["citation_id"]], "CITATION_CHANGED")
        require(p.get("source_bindings") == [source_pin(s)], "SOURCE_PIN_CHANGED")
        require(p.get("proof_id") == s["proof_id"], "PROOF_CHANGED")
        require(p.get("source_rights") == "local_fixture_current", "RIGHTS_NOT_CURRENT")
        require(p.get("consent") == "local_fixture_granted", "CONSENT_NOT_GRANTED")
        require(type(p.get("claim_start")) is int
                and p.get("claim_start") == 0
                and type(p.get("claim_end")) is int
                and p.get("claim_end") == len(s["answer_bytes"])
                and p.get("claim_sha256") == s["claim_sha256"], "CLAIM_SPAN_CHANGED")
        require(s["answer_bytes"].startswith(bytes(self.answer) + data),
                "UNVERIFIED_OR_MUTATED_ANSWER")
        self.answer.extend(data)
        self.answers += 1
        if self.first_data_ns is None:
            self.first_data_ns = stamp

    def finish(self) -> None:
        require(self.header and not self.pending, "WIRE_TRUNCATED")
        require(self.closed, "TERMINAL_MISSING")


def local_events(s: dict) -> list[bytes]:
    """Positive unit packets run through the same AR08 adapter as real server."""
    frames = []

    class Collect:
        def enqueue(self, frame: ar08.VerifiedTextFrame) -> None:
            frames.append(frame)

        def flush(self, sequence: int) -> None:
            require(sequence == frames[-1].sequence, "FLUSH_ORDER")

    push_synthetic_answer(s, fixture_adapter(s, Collect()))
    return [
        t14.encode_event("progress", {**identity(s), "fixture": True, "phase": "preparing"}),
        *[t14.encode_event("answer", frame_payload(s, f)) for f in frames],
        t14.encode_event("terminal", {
            **identity(s), "fixture": True, "status": "completed",
            "answer_sha256": s["answer_sha256"],
        }),
    ]


def parse_fixture(s: dict, events: list[bytes], fragment: int = 7) -> Receiver:
    receiver = Receiver(s)
    raw = t14.headers() + b"".join(events)
    for i in range(0, len(raw), fragment):
        receiver.feed(raw[i:i + fragment], now_ns() + i)
    receiver.finish()
    return receiver


def _request(s: dict) -> bytes:
    return (
        f"GET /i15-native-fixture HTTP/1.1\r\nHost: {HOST}\r\n"
        f"X-Request-Id: {s['request_id']}\r\n"
        f"X-Run-Id: {s['run_id']}\r\n"
        f"X-Tenant: {s['tenant_id']}\r\n"
        f"X-Trace-Id: {s['trace_id']}\r\n\r\n"
    ).encode("ascii")


def server(index: int, mode: str, namespace: str = "") -> None:
    require(mode == "positive" or mode in FAULT_MODES, "MODE_NOT_ALLOWED")
    s = spec(index, namespace)
    receipt = {
        "server_pid": os.getpid(), "case_id": s["case_id"], "mode": mode,
        "enqueue_ns": [], "flush_ns": [], "terminal_ns": None,
        "sent_bytes": 0, "status": "STARTED",
    }
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))
        listener.listen(1)
        # L22 isolated synthetic server only: give a bounded cold client
        # import enough time to connect after the READY line is emitted.
        listener.settimeout(LOCAL_SERVER_ACCEPT_DEADLINE_SECONDS)
        print(json.dumps({
            "ready": True, "host": HOST, "port": listener.getsockname()[1],
            "server_pid": os.getpid(),
        }), flush=True)
        try:
            conn, peer = listener.accept()
            with conn:
                conn.settimeout(3)
                require(peer[0] == HOST, "REMOTE_PEER_REFUSED")
                req = bytearray()
                while b"\r\n\r\n" not in req:
                    chunk = conn.recv(512)
                    require(bool(chunk), "EMPTY_REQUEST")
                    req.extend(chunk)
                    require(len(req) < 2048, "REQUEST_OVER_LIMIT")
                require(bytes(req) == _request(s), "REQUEST_BINDING_REJECTED")

                def send(blob: bytes) -> None:
                    conn.sendall(blob)
                    receipt["sent_bytes"] += len(blob)

                if mode == "server_500":
                    send(t14.headers(500))
                    receipt["status"] = "HTTP_500_SENT"
                else:
                    send(t14.headers())
                    send(t14.encode_event("progress", {
                        **identity(s), "fixture": True, "phase": "preparing",
                    }))
                    if mode == "progress_only":
                        send(t14.encode_event("terminal", {
                            **identity(s), "fixture": True, "status": "completed",
                            "answer_sha256": s["answer_sha256"],
                        }))
                    elif mode != "disconnect":
                        if mode == "timeout_first":
                            time.sleep(3.2)  # exceed bounded client recv timeout
                        state = {"revoked": False, "expired": False}

                        class Transport:
                            def __init__(self) -> None:
                                self.frames = {}

                            def enqueue(self, frame: ar08.VerifiedTextFrame) -> None:
                                self.frames[frame.sequence] = frame
                                receipt["enqueue_ns"].append(now_ns())
                                if mode == "revoke_after_enqueue":
                                    state["revoked"] = True
                                if mode == "expire_after_enqueue":
                                    state["expired"] = True

                            def flush(self, sequence: int) -> None:
                                frame = self.frames.pop(sequence)
                                p = frame_payload(s, frame)
                                field = {
                                    "wrong_tenant": ("tenant_id", "foreign-tenant"),
                                    "wrong_revision": ("source_bindings", [[
                                        s["citation_id"], s["source_id"], "changed-revision",
                                        s["source_sha256"],
                                    ]]),
                                    "wrong_source_sha": ("source_bindings", [[
                                        s["citation_id"], s["source_id"], s["source_revision"],
                                        sha(b"forged"),
                                    ]]),
                                    "wrong_trace": ("trace_id", "cross-request-trace"),
                                    "wrong_citation": ("citation_ids", ["foreign-citation"]),
                                    "forged_ack": ("authenticated_ack", True),
                                }.get(mode)
                                if field:
                                    p[field[0]] = field[1]
                                if mode == "bad_utf8":
                                    send(b"event: answer\ndata: \xff\n\n")
                                else:
                                    event = t14.encode_event("answer", p)
                                    send(event)
                                    if mode == "duplicate_frame":
                                        send(event)
                                receipt["flush_ns"].append(now_ns())

                        adapter = fixture_adapter(s, Transport(), state)
                        try:
                            push_synthetic_answer(s, adapter)
                            receipt["terminal_ns"] = adapter.state.terminal_monotonic_ns
                            if mode not in ("drop_terminal", "duplicate_frame"):
                                time.sleep(0.025)
                                final = t14.encode_event("terminal", {
                                    **identity(s), "fixture": True, "status": "completed",
                                    "answer_sha256": s["answer_sha256"],
                                })
                                send(final)
                                if mode == "duplicate_terminal":
                                    send(final)
                            receipt["status"] = "SYNTHETIC_TRANSPORT_COMPLETED"
                        except (ar08.StreamDenied, I15Denied) as exc:
                            receipt["status"] = "AR08_DENIED_" + str(exc)
        except (OSError, I15Denied) as exc:
            receipt["status"] = "SERVER_DENIED_" + type(exc).__name__
    print(json.dumps(receipt, sort_keys=True), flush=True)


def client(index: int, port: int, namespace: str = "") -> dict:
    s = spec(index, namespace)
    receiver = Receiver(s)
    start_ns = now_ns()
    connect_started_ns = connected_ns = request_ns = request_sent_ns = None
    response_complete_ns = None
    recv_calls = recv_bytes = 0
    error = None
    try:
        require(0 < port < 65536, "INVALID_PORT")
        # L22 opt-in fixture fault injection: exact five-second late connect.
        # No delay is applied without the explicit synthetic test marker.
        if os.environ.get("M27_L22_SYNTHETIC_DELAY_CONNECT") == "5":
            time.sleep(5)
        connect_started_ns = now_ns()
        with socket.create_connection((HOST, port), timeout=3) as conn:
            connected_ns = now_ns()
            conn.settimeout(3)
            request_ns = now_ns()
            conn.sendall(_request(s))
            request_sent_ns = now_ns()
            while True:
                chunk = conn.recv(7)
                if not chunk:
                    break
                recv_calls += 1
                recv_bytes += len(chunk)
                receiver.feed(chunk, now_ns())
            receiver.finish()
            response_complete_ns = now_ns()
    except (I15Denied, t14.WireDenied, OSError) as exc:
        error = str(exc) if isinstance(exc, (I15Denied, t14.WireDenied)) else (
            "SOCKET_" + type(exc).__name__.upper()
        )
    return {
        "status": error or "COMPLETE",
        "client_pid": os.getpid(),
        "client_spawn_ns": start_ns,
        "connect_start_ns": connect_started_ns,
        "connect_complete_ns": connected_ns,
        "request_send_complete_ns": request_sent_ns,
        "response_complete_ns": response_complete_ns,
        "request_ns": request_ns if request_ns is not None else start_ns,
        "first_recv_ns": receiver.first_recv_ns,
        "first_data_ns": receiver.first_data_ns,
        "terminal_ns": receiver.terminal_ns,
        "recv_calls": recv_calls, "recv_bytes": recv_bytes,
        "progress_events": receiver.progress, "answer_events": receiver.answers,
        "answer_length": len(receiver.answer),
        "received_answer_sha256": sha(bytes(receiver.answer)),
        "first_text_ms": (
            (receiver.first_data_ns - request_ns) / 1e6
            if request_ns is not None and receiver.first_data_ns is not None else None
        ),
        "terminal_ms": (
            (receiver.terminal_ns - request_ns) / 1e6
            if request_ns is not None and receiver.terminal_ns is not None else None
        ),
    }


def _child_env(worktree: Path) -> dict:
    return {
        "PATH": "/usr/bin:/bin", "HOME": "/tmp", "TMPDIR": "/tmp",
        "PYTHONPATH": str(worktree / "src"), "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8", "PYTHONUTF8": "1",
    }


PROCESS_CASE_SLOTS = 2
PROCESS_CHILD_LIMIT = 2 * PROCESS_CASE_SLOTS
BOOT_DEADLINE_SECONDS = 6.0
# Larger than the cold Python child import under observed development-host load;
# applies ONLY to this nonproduction L22 repair worktree.
LOCAL_SERVER_ACCEPT_DEADLINE_SECONDS = 20.0
CLIENT_DEADLINE_SECONDS = 8.0
SERVER_EXIT_DEADLINE_SECONDS = 5.0
BUDGET_WAIT_SECONDS = 30.0
_ADMISSION_CV = threading.Condition()
_ADMISSION_QUEUE: list[object] = []


@contextlib.contextmanager
def case_slot(worktree: Path, timeout: float = BUDGET_WAIT_SECONDS):
    """FIFO thread admission plus cross-process flock: at most four direct children."""
    require(0 < timeout <= 60, "BUDGET_DEADLINE_INVALID")
    root = Path(tempfile.gettempdir()) / (
        "m27_c16_" + sha(str(worktree.resolve()).encode())[:20]
    )
    root.mkdir(mode=0o700, exist_ok=True)
    require(root.stat().st_uid == os.getuid()
            and root.stat().st_mode & 0o077 == 0, "BUDGET_DIR_UNSAFE")
    deadline = time.monotonic() + timeout
    start = now_ns()
    token = object()
    with _ADMISSION_CV:
        _ADMISSION_QUEUE.append(token)
        _ADMISSION_CV.notify_all()
    try:
        while time.monotonic() < deadline:
            with _ADMISSION_CV:
                if _ADMISSION_QUEUE[0] is not token:
                    _ADMISSION_CV.wait(timeout=.025)
                    continue
            for number in range(PROCESS_CASE_SLOTS):
                fd = os.open(
                    root / f"slot{number}.lock",
                    os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600,
                )
                try:
                    require(os.fstat(fd).st_uid == os.getuid(), "BUDGET_SLOT_UNSAFE")
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        continue
                    with _ADMISSION_CV:
                        _ADMISSION_QUEUE.remove(token)
                        _ADMISSION_CV.notify_all()
                    try:
                        yield number, now_ns() - start
                    finally:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    return
                finally:
                    os.close(fd)
            time.sleep(.025)
        raise I15Denied("PROCESS_BUDGET_TIMEOUT")
    finally:
        with _ADMISSION_CV:
            if token in _ADMISSION_QUEUE:
                _ADMISSION_QUEUE.remove(token)
                _ADMISSION_CV.notify_all()


def read_server_ready(proc: subprocess.Popen, timeout: float = BOOT_DEADLINE_SECONDS):
    """Unbuffered deadline-limited ready line; never unbounded readline/stderr."""
    require(timeout > 0, "BOOT_DEADLINE_INVALID")
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise I15Denied("SERVER_BOOT_EXITED")
        ready, _, _ = select.select(
            [proc.stdout.fileno()], [], [], min(0.15, max(0, deadline - time.monotonic()))
        )
        if ready:
            fragment = os.read(proc.stdout.fileno(), 1024)
            require(bool(fragment), "SERVER_BOOT_EOF")
            buf.extend(fragment)
            require(len(buf) <= 2048, "SERVER_READY_TOO_LARGE")
            if b"\n" in buf:
                line, tail = bytes(buf).split(b"\n", 1)
                try:
                    data = json.loads(line.decode("utf-8", "strict"))
                except (UnicodeError, ValueError) as exc:
                    raise I15Denied("SERVER_READY_MALFORMED") from exc
                require(type(data) is dict
                        and data.get("ready") is True and data.get("host") == HOST
                        and data.get("server_pid") == proc.pid
                        and type(data.get("port")) is int
                        and 0 < data["port"] < 65536,
                        "SERVER_CHILD_READY_UNVERIFIED")
                return data, tail
    raise I15Denied("SERVER_BOOT_TIMEOUT")


def terminate_owned(proc: subprocess.Popen | None) -> dict:
    """Only reap this case's own child, with bounded graceful then forced stop."""
    if proc is None:
        return {"owned": False, "reaped": True}
    state = {"owned": True, "pid": proc.pid, "terminated": False, "killed": False}
    if proc.poll() is None:
        proc.terminate()
        state["terminated"] = True
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            state["killed"] = True
            proc.wait(timeout=1)
    state["reaped"] = proc.poll() is not None
    state["returncode"] = proc.returncode
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()
    return state


def run_case(worktree: Path, index: int, mode: str, namespace: str = "") -> dict:
    """No attempt is dropped on a failed fork, child wait or boot deadline."""
    s = spec(index, namespace)
    require(mode == "positive" or mode in FAULT_MODES, "MODE_NOT_ALLOWED")
    prefix = [
        PYTHON, "-B", "-m",
        "knowledge_engine.m27_w5_i15_native_local_client_integration_v1_experimental",
    ]
    env = _child_env(worktree)
    d = {
        "parent_clock": "parent_monotonic_ns",
        "child_clocks": "each_child_monotonic_ns_separate",
        "case_started_ns": now_ns(), "server_spawn_ns": None,
        "server_ready_ns": None, "client_spawn_ns": None,
        "client_exit_ns": None, "server_exit_ns": None, "finished_ns": None,
        "admission_wait_ms": None, "slot": None,
        "process_limit": PROCESS_CHILD_LIMIT,
        "startup_deadline_s": BOOT_DEADLINE_SECONDS,
        "client_deadline_s": CLIENT_DEADLINE_SECONDS,
        "server_exit_deadline_s": SERVER_EXIT_DEADLINE_SECONDS,
        "failure_stage": "admission", "client_exit": None, "server_exit": None,
        "client_stderr": "", "server_stderr": "", "cleanup": {},
    }
    srv = cli = None
    port = None
    cl = {"status": "NOT_STARTED", "client_pid": None, "recv_calls": 0,
          "recv_bytes": 0, "first_recv_ns": None, "first_data_ns": None,
          "terminal_ns": None, "first_text_ms": None}
    server_data = {"status": "NOT_STARTED", "server_pid": None,
                   "enqueue_ns": [], "flush_ns": [], "terminal_ns": None}
    error = None
    try:
        with case_slot(worktree) as (slot, wait):
            d["slot"], d["admission_wait_ms"] = slot, round(wait / 1e6, 3)
            try:
                d["failure_stage"] = "server_boot"
                d["server_spawn_ns"] = now_ns()
                srv = subprocess.Popen(
                    prefix + ["server", "--index", str(index), "--mode", mode,
                              "--namespace", namespace],
                    cwd=worktree, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                    close_fds=True,
                )
                ready, tail = read_server_ready(srv, timeout=BOOT_DEADLINE_SECONDS)
                d["server_ready_ns"] = now_ns()
                port = ready["port"]
                server_data["server_pid"] = srv.pid
                d["failure_stage"] = "client_subprocess"
                d["client_spawn_ns"] = now_ns()
                cli = subprocess.Popen(
                    prefix + ["client", "--index", str(index), "--port", str(port),
                              "--namespace", namespace],
                    cwd=worktree, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                    close_fds=True,
                )
                try:
                    cout, cerr = cli.communicate(timeout=CLIENT_DEADLINE_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    raise I15Denied("CLIENT_SUBPROCESS_TIMEOUT") from exc
                d["client_exit_ns"], d["client_exit"] = now_ns(), cli.returncode
                d["client_stderr"] = cerr[:4096].decode("utf-8", "replace")
                require(len(cout) <= 131072 and len(cerr) <= 131072,
                        "CLIENT_OUTPUT_OVER_LIMIT")
                require(cli.returncode == 0, "CLIENT_CHILD_FAILED")
                try:
                    cl = json.loads(cout.decode("utf-8", "strict"))
                except (UnicodeError, ValueError) as exc:
                    raise I15Denied("CLIENT_JSON_INVALID") from exc
                require(type(cl) is dict and cl.get("client_pid") == cli.pid,
                        "CLIENT_IDENTITY_INVALID")
                d["failure_stage"] = "server_exit"
                try:
                    sout, serr = srv.communicate(timeout=SERVER_EXIT_DEADLINE_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    raise I15Denied("SERVER_EXIT_TIMEOUT") from exc
                d["server_exit_ns"], d["server_exit"] = now_ns(), srv.returncode
                d["server_stderr"] = serr[:4096].decode("utf-8", "replace")
                require(srv.returncode == 0, "SERVER_CHILD_FAILED")
                require(len(tail) + len(sout) <= 131072 and len(serr) <= 131072,
                        "SERVER_OUTPUT_OVER_LIMIT")
                try:
                    server_data = json.loads((tail + sout).decode("utf-8", "strict").strip())
                except (UnicodeError, ValueError) as exc:
                    raise I15Denied("SERVER_JSON_INVALID") from exc
                require(type(server_data) is dict
                        and server_data.get("server_pid") == srv.pid,
                        "SERVER_RECEIPT_INVALID")
                require(cl["client_pid"] != srv.pid and cl["recv_calls"] > 0,
                        "NOT_ACTUAL_SEPARATE_CLIENT_RECV")
                d["failure_stage"] = None
            finally:
                d["cleanup"]["client"] = terminate_owned(cli)
                d["cleanup"]["server"] = terminate_owned(srv)
    except (I15Denied, OSError, subprocess.SubprocessError, ValueError) as exc:
        error = str(exc) if isinstance(exc, I15Denied) else (
            type(exc).__name__.upper() + "_PROCESS_FAILURE"
        )
    finally:
        d["finished_ns"] = now_ns()
    return {
        "case_id": s["case_id"] + "-" + mode,
        "source_sha256": s["source_sha256"],
        "source_revision": s["source_revision"],
        "answer_sha256": s["answer_sha256"],
        "endpoint": f"{HOST}:{port}" if port else None,
        "server": server_data, "client": cl, "mode": mode, "fixture": True,
        "namespace": namespace, "status": error or cl["status"],
        "diagnostics": d,
        "client_stdout_sha256": sha(json.dumps(cl, sort_keys=True).encode()),
        "client_stderr_sha256": sha(d["client_stderr"].encode()),
        "server_stderr_sha256": sha(d["server_stderr"].encode()),
    }


def denominator(cases: list[dict]) -> dict:
    require(bool(cases), "NO_ATTEMPTS")
    seen = set()
    duration_cases = []
    for c in cases:
        require(c["case_id"] not in seen, "DUPLICATE_ATTEMPT")
        seen.add(c["case_id"])
        complete = c["status"] == "COMPLETE"
        ms = c["client"]["first_text_ms"] if complete else None
        duration_cases.append(t09.DurationCase(
            c["case_id"], c["case_id"], True,
            "completed" if complete else "missing", ms,
        ))
    verdict = t09.duration_denominator(tuple(duration_cases))
    return {
        "total": verdict.total, "completed": verdict.completed,
        "failure_or_abstention": verdict.total - verdict.completed,
        "first_text_p95_ms": (
            sorted(x.authoritative_final_request_ms for x in duration_cases)[
                math.ceil(0.95 * len(duration_cases)) - 1
            ] if verdict.completed == verdict.total else None
        ),
        "product_p95": "PRODUCT_P95_UNVERIFIED",
        "p95_classification": (
            "LOCAL_DIAGNOSTIC_ONLY" if verdict.completed == verdict.total else "UNKNOWN"
        ),
    }


def probe(worktree: Path, scratch: Path, namespace: str | None = None) -> dict:
    namespace = namespace or uuid.uuid4().hex[:16]
    spec(0, namespace)
    require(worktree.is_dir() and (worktree / "src").is_dir(), "BAD_WORKTREE")
    require(not scratch.resolve().is_relative_to(worktree.resolve()), "SCRATCH_WITHIN_GIT")
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch.chmod(0o700)
    plan = [(i, "positive") for i in range(len(PHRASES))]
    plan += [(i % len(PHRASES), mode) for i, mode in enumerate(FAULT_MODES)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_case, worktree, i, mode, namespace)
                   for i, mode in plan]
        cases = [f.result() for f in futures]
    successes = [c for c in cases if c["mode"] == "positive"]
    failures = [c for c in cases if c["mode"] != "positive"]
    valid = (
        len(successes) == 12 and len(failures) == len(FAULT_MODES)
        and len({c["source_sha256"] for c in successes}) == 12
        and len({c["source_revision"] for c in successes}) == 12
        and len({c["case_id"] for c in cases}) == len(cases)
        and all(
            c["status"] == "COMPLETE"
            and c["client"]["received_answer_sha256"] == c["answer_sha256"]
            and c["client"]["request_ns"] <= c["client"]["first_recv_ns"]
            <= c["client"]["first_data_ns"] < c["client"]["terminal_ns"]
            and c["server"]["enqueue_ns"]
            and c["server"]["flush_ns"]
            and c["server"]["enqueue_ns"][0] <= c["server"]["flush_ns"][0]
            <= c["server"]["terminal_ns"]
            for c in successes
        )
        and all(c["status"] != "COMPLETE" for c in failures)
        and any(
            c["mode"] == "progress_only" and c["client"]["first_data_ns"] is None
            for c in failures
        )
    )
    receipt = {
        "version": VERSION, "fixture": True, "namespace": namespace,
        "process_child_limit": PROCESS_CHILD_LIMIT,
        "status": PASS if valid else FAIL, "real_loopback_verified": bool(valid),
        "case_count": len(cases), "positive_count": len(successes),
        "negative_socket_count": len(failures),
        "qualifications": list(GATES), "denominator": denominator(cases),
        "cases": cases,
    }
    raw = json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True).encode()
    receipt_path = scratch / "I15_REAL_MULTICASE_SOCKET_RECEIPT.json"
    receipt_path.write_bytes(raw)
    receipt_path.chmod(0o600)
    return {
        "status": receipt["status"], "receipt_path": str(receipt_path),
        "receipt_sha256": sha(raw), "denominator": receipt["denominator"],
        "case_count": len(cases), "namespace": namespace,
        "qualifications": list(GATES),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("server", "client", "probe"))
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--mode", default="positive")
    parser.add_argument("--port", type=int)
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--namespace", default="")
    args = parser.parse_args()
    if args.action == "server":
        server(args.index, args.mode, args.namespace)
    elif args.action == "client":
        require(args.port is not None, "PORT_REQUIRED")
        print(json.dumps(client(args.index, args.port, args.namespace), sort_keys=True), flush=True)
    else:
        require(args.worktree is not None and args.scratch is not None, "PATH_REQUIRED")
        result = probe(args.worktree, args.scratch, args.namespace or None)
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
