"""N21 independent external OS client of the I15 nonproduction localhost server.

Only fixture source authority. Never an external Provider, authenticated ACK,
production benchmark, or general-purpose network client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import select
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = "W5N21IndependentExternalLocalClientV1"
PASS = "N21_EXTERNAL_LOCAL_CLIENT_FIXTURE_PASS"
FAIL = "N21_EXTERNAL_LOCAL_CLIENT_NOT_VERIFIED"
HOST = "127.0.0.1"
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


def fixture_spec(index: int, namespace: str) -> dict:
    need(type(index) is int and 0 <= index < 12, "FIXTURE_INDEX_INVALID")
    need(type(namespace) is str and len(namespace) <= 40
         and all(x.isascii() and (x.isalnum() or x in "_-") for x in namespace),
         "FIXTURE_NAMESPACE_INVALID")
    raw = PHRASES[index].encode("utf-8")
    suffix = "-" + namespace if namespace else ""
    return {
        "request_id": f"i15-req-{index:02d}{suffix}",
        "run_id": f"i15-run-{index:02d}{suffix}",
        "trace_id": f"i15-trace-{index:02d}{suffix}",
        "tenant_id": f"i15-tenant-{index % 3:02d}{suffix}",
        "actor_id": f"i15-actor-{index:02d}{suffix}",
        "citation_id": f"i15-citation-{index:02d}",
        "source_id": f"i15-source-{index:02d}",
        "source_revision": f"fixture-r{index + 1:02d}",
        "source_sha256": digest(raw),
        "claim_sha256": digest(raw),
        "proof_id": f"i15-ar05-proposal-{index:02d}",
        "answer_bytes": raw,
    }
BLOCKED_AUTHORITY = frozenset({
    "authenticated_ack", "signature", "product_p95", "real_provider",
    "cost_attestation", "image_digest", "release_certified",
})


class Denied(ValueError):
    """Fail-closed external-client verdict."""


def need(condition: bool, message: str) -> None:
    if not condition:
        raise Denied(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def monotonic() -> int:
    return time.monotonic_ns()


class ExternalDecoder:
    """Independent strict client parser; does not call the I15 Receiver."""

    def __init__(self, case: dict) -> None:
        self.case = case
        self.pending = bytearray()
        self.total = 0
        self.header = False
        self.closed = False
        self.first_recv_ns = None
        self.first_answer_ns = None
        self.full_answer_ns = None
        self.terminal_ns = None
        self.progress = 0
        self.answers = 0
        self.answer = bytearray()

    def feed(self, chunk: bytes, timestamp: int) -> None:
        need(type(timestamp) is int and timestamp >= 0, "INVALID_MONOTONIC")
        need(not self.closed, "BYTES_AFTER_TERMINAL")
        if chunk and self.first_recv_ns is None:
            self.first_recv_ns = timestamp
        self.total += len(chunk)
        need(self.total <= 1048576, "WIRE_TOO_LARGE")
        self.pending.extend(chunk)
        if not self.header:
            cut = self.pending.find(b"\r\n\r\n")
            need(len(self.pending) <= 8192 or cut >= 0 and cut <= 8192,
                 "HEADER_TOO_LARGE")
            if cut < 0:
                return
            head = bytes(self.pending[:cut])
            del self.pending[:cut + 4]
            lines = head.split(b"\r\n")
            need(lines[0] == b"HTTP/1.1 200 OK", "HTTP_NOT_200")
            need(b"Content-Type: text/event-stream; charset=utf-8" in lines,
                 "NOT_UTF8_SSE")
            self.header = True
        while b"\n\n" in self.pending:
            need(not self.closed, "TRAILING_EVENT")
            pos = self.pending.index(b"\n\n")
            need(pos <= 65536, "EVENT_TOO_LARGE")
            fragment = bytes(self.pending[:pos])
            del self.pending[:pos + 2]
            lines = fragment.split(b"\n")
            need(len(lines) == 2 and lines[0].startswith(b"event: ")
                 and lines[1].startswith(b"data: "), "SSE_SHAPE")
            need(b"\r" not in fragment, "SSE_CR")
            try:
                event = lines[0][7:].decode("ascii", "strict")
                payload = json.loads(lines[1][6:].decode("utf-8", "strict"))
            except (UnicodeError, ValueError) as exc:
                raise Denied("INVALID_EVENT_UTF8_OR_JSON") from exc
            self.event(event, payload, timestamp)
        need(len(self.pending) <= 65536, "PENDING_TOO_LARGE")

    def event(self, kind: str, payload: dict, timestamp: int) -> None:
        need(type(payload) is dict, "PAYLOAD_NOT_DICT")
        need(kind in ("progress", "answer", "terminal"), "UNKNOWN_EVENT")
        s = self.case
        for key in IDENTITIES:
            need(payload.get(key) == s[key], "IDENTITY_" + key.upper())
        need(payload.get("fixture") is True, "FIXTURE_REQUIRED")
        need(not BLOCKED_AUTHORITY.intersection(payload), "FAKE_EXTERNAL_AUTHORITY")
        if kind == "progress":
            need(not self.answers and not self.closed, "LATE_PROGRESS")
            need(set(payload) == set(IDENTITIES) | {"fixture", "phase"}
                 and payload.get("phase") == "preparing", "PROGRESS_INVALID")
            self.progress += 1
            return
        if kind == "answer":
            need(set(payload) == FIELDS, "ANSWER_SCHEMA_INVALID")
            need(type(payload.get("sequence")) is int
                 and payload["sequence"] == self.answers, "SEQUENCE_INVALID")
            need(type(payload.get("start")) is int
                 and payload["start"] == len(self.answer), "OFFSET_INVALID")
            need(type(payload.get("text")) is str and payload["text"].strip(),
                 "TEXT_INVALID")
            data = payload["text"].encode("utf-8")
            need(type(payload.get("end")) is int
                 and payload["end"] == len(self.answer) + len(data), "END_INVALID")
            need(payload.get("sha256") == digest(data), "FRAME_DIGEST_INVALID")
            need(payload.get("citation_ids") == [s["citation_id"]], "CITATION_INVALID")
            expected_pin = [[s["citation_id"], s["source_id"],
                             s["source_revision"], s["source_sha256"]]]
            need(payload.get("source_bindings") == expected_pin, "SOURCE_PIN_INVALID")
            need(payload.get("proof_id") == s["proof_id"], "PROOF_INVALID")
            need(payload.get("source_rights") == "local_fixture_current",
                 "RIGHTS_INVALID")
            need(payload.get("consent") == "local_fixture_granted",
                 "CONSENT_INVALID")
            need(type(payload.get("claim_start")) is int
                 and payload["claim_start"] == 0, "CLAIM_START_INVALID")
            need(type(payload.get("claim_end")) is int
                 and payload["claim_end"] == len(s["answer_bytes"]),
                 "CLAIM_END_INVALID")
            need(payload.get("claim_sha256") == s["claim_sha256"],
                 "CLAIM_HASH_INVALID")
            need(s["answer_bytes"].startswith(self.answer + data),
                 "ANSWER_NOT_SOURCE_BOUND")
            self.answer.extend(data)
            self.answers += 1
            if self.first_answer_ns is None:
                self.first_answer_ns = timestamp
            if len(self.answer) == len(s["answer_bytes"]):
                self.full_answer_ns = timestamp
            return
        need(not self.closed, "DUPLICATE_TERMINAL")
        need(set(payload) == set(IDENTITIES) | {
            "fixture", "status", "answer_sha256"}, "TERMINAL_SCHEMA_INVALID")
        need(payload["status"] == "completed", "TERMINAL_FAILED")
        need(self.answers > 0 and self.first_answer_ns is not None,
             "PROGRESS_NOT_MATERIAL_TEXT")
        need(bytes(self.answer) == s["answer_bytes"], "INCOMPLETE_ANSWER")
        need(payload["answer_sha256"] == digest(bytes(self.answer)),
             "TERMINAL_DIGEST_INVALID")
        need(self.full_answer_ns is not None
             and self.first_answer_ns < timestamp
             and self.full_answer_ns < timestamp, "TERMINAL_ORDER_INVALID")
        self.terminal_ns = timestamp
        self.closed = True

    def finish(self) -> None:
        need(self.header and not self.pending, "TRUNCATED_STREAM")
        need(self.closed, "TERMINAL_NOT_SEEN")


def request(case: dict) -> bytes:
    return (
        "GET /i15-native-fixture HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        f"X-Request-Id: {case['request_id']}\r\n"
        f"X-Run-Id: {case['run_id']}\r\n"
        f"X-Tenant: {case['tenant_id']}\r\n"
        f"X-Trace-Id: {case['trace_id']}\r\n\r\n"
    ).encode("ascii")


def external_client(index: int, port: int, namespace: str) -> dict:
    case = fixture_spec(index, namespace)
    decoder = ExternalDecoder(case)
    begin_ns = monotonic()
    sent_ns = None
    recv_calls = 0
    error = None
    try:
        need(type(port) is int and 0 < port < 65536, "UNSAFE_PORT")
        with socket.create_connection((HOST, port), timeout=2.5) as conn:
            need(conn.getpeername()[0] == HOST, "NON_LOOPBACK_PEER")
            conn.settimeout(3)
            conn.sendall(request(case))
            sent_ns = monotonic()
            while True:
                chunk = conn.recv(7)
                if not chunk:
                    break
                recv_calls += 1
                decoder.feed(chunk, monotonic())
            decoder.finish()
    except (Denied, OSError) as exc:
        error = str(exc) if isinstance(exc, Denied) else (
            "SOCKET_" + type(exc).__name__.upper()
        )
    def ms(ns: int | None) -> float | None:
        return round((ns - sent_ns) / 1e6, 4) if ns is not None and sent_ns else None
    return {
        "status": error or "COMPLETE", "client_pid": os.getpid(),
        "start_ns": begin_ns, "request_sent_ns": sent_ns,
        "first_recv_ns": decoder.first_recv_ns,
        "first_answer_ns": decoder.first_answer_ns,
        "full_answer_ns": decoder.full_answer_ns,
        "terminal_ns": decoder.terminal_ns,
        "first_text_ms": ms(decoder.first_answer_ns),
        "full_answer_ms": ms(decoder.full_answer_ns),
        "terminal_ms": ms(decoder.terminal_ns),
        "recv_calls": recv_calls, "recv_bytes": decoder.total,
        "progress_events": decoder.progress, "answer_events": decoder.answers,
        "received_digest": digest(bytes(decoder.answer)),
        "received_bytes": len(decoder.answer),
    }


def read_client_ready(child: subprocess.Popen, timeout: float = 12.0) -> bytes:
    """Prestart external client so server accept window begins only AFTER readiness."""
    deadline = time.monotonic() + timeout
    pending = bytearray()
    while time.monotonic() < deadline:
        need(child.poll() is None, "CLIENT_PREWARM_EXITED")
        ready, _, _ = select.select(
            [child.stdout.fileno()], [], [],
            min(0.15, max(0, deadline - time.monotonic())),
        )
        if ready:
            block = os.read(child.stdout.fileno(), 1024)
            need(bool(block), "CLIENT_PREWARM_EOF")
            pending.extend(block)
            need(len(pending) < 1024, "CLIENT_PREWARM_OVERLIMIT")
            if b"\n" in pending:
                line, tail = bytes(pending).split(b"\n", 1)
                need(line == f"N21_READY:{child.pid}".encode("ascii"),
                     "CLIENT_READY_PID_INVALID")
                return tail
    raise Denied("CLIENT_PREWARM_TIMEOUT")


def run_case(worktree: Path, index: int, mode: str, namespace: str) -> dict:
    """Launch independent server and new external client, with bounded reaping."""
    from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15

    case = i15.spec(index, namespace)
    need(mode == "positive" or mode in i15.FAULT_MODES, "UNKNOWN_MODE")
    env = i15._child_env(worktree)
    server = client = None
    ready = {}
    server_receipt = {}
    received = {"status": "NOT_STARTED", "client_pid": None}
    failure = None
    wait_ms = None
    cleanup = {}
    stage = "admission"
    try:
        with i15.case_slot(worktree) as (slot, wait_ns):
            wait_ms = round(wait_ns / 1e6, 3)
            try:
                stage = "client_prestart"
                client = subprocess.Popen([
                    i15.PYTHON, "-B", "-m",
                    "knowledge_engine.m27_w5_n21_independent_local_client_v1_experimental",
                    "client", "--index", str(index), "--namespace", namespace,
                ], cwd=worktree, env=env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
                preface = read_client_ready(client)
                stage = "server_boot"
                server = subprocess.Popen([
                    i15.PYTHON, "-B", "-m",
                    "knowledge_engine.m27_w5_i15_native_local_client_integration_v1_experimental",
                    "server", "--index", str(index), "--mode", mode,
                    "--namespace", namespace,
                ], cwd=worktree, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
                ready, tail = i15.read_server_ready(server)
                stage = "client_recv"
                client.stdin.write((str(ready["port"]) + "\n").encode("ascii"))
                client.stdin.flush()
                client.stdin.close()
                client.stdin = None
                out, err = client.communicate(timeout=8)
                out = preface + out
                need(client.returncode == 0 and len(out) <= 131072
                     and len(err) <= 131072, "CLIENT_PROCESS_FAILED")
                received = json.loads(out.decode("utf-8", "strict"))
                need(type(received) is dict and received["client_pid"] == client.pid,
                     "CLIENT_PID_INVALID")
                stage = "server_exit"
                sout, serr = server.communicate(timeout=5)
                need(server.returncode == 0 and len(tail) + len(sout) <= 131072
                     and len(serr) <= 131072, "SERVER_PROCESS_FAILED")
                server_receipt = json.loads((tail + sout).decode("utf-8", "strict"))
                need(server_receipt["server_pid"] == server.pid
                     and server.pid != client.pid, "SERVER_PID_INVALID")
                need(received.get("recv_calls", 0) > 0, "NO_REAL_RECV")
                stage = "complete"
            finally:
                cleanup["client"] = i15.terminate_owned(client)
                cleanup["server"] = i15.terminate_owned(server)
    except (i15.I15Denied, Denied, OSError, ValueError,
            subprocess.SubprocessError, KeyError) as exc:
        failure = type(exc).__name__ + ":" + str(exc)[:100]
    return {
        "case_id": case["case_id"] + "-" + mode, "mode": mode,
        "fixture": True, "source_revision": case["source_revision"],
        "source_sha256": case["source_sha256"],
        "expected_answer_sha256": case["answer_sha256"],
        "server_pid": server.pid if server else None,
        "client_pid": client.pid if client else None,
        "endpoint": f"127.0.0.1:{ready['port']}" if ready else None,
        "client": received, "server": server_receipt,
        "status": failure or received["status"], "stage": stage,
        "admission_wait_ms": wait_ms, "cleanup": cleanup,
    }


def suite(worktree: Path, scratch: Path, namespace: str) -> dict:
    from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15

    i15.spec(0, namespace)
    need(worktree.is_dir() and (worktree / "src").is_dir(), "WORKTREE_INVALID")
    need(not scratch.resolve().is_relative_to(worktree.resolve()),
         "SCRATCH_MUST_BE_OUTSIDE_GIT")
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    scratch.chmod(0o700)
    plan = [(i, "positive") for i in range(12)]
    plan.extend((i % 12, mode) for i, mode in enumerate(i15.FAULT_MODES))
    with ThreadPoolExecutor(max_workers=2) as pool:
        cases = list(pool.map(lambda item: run_case(worktree, *item, namespace), plan))
    positive = [x for x in cases if x["mode"] == "positive"]
    negative = [x for x in cases if x["mode"] != "positive"]
    valid_positive = all(
        x["status"] == "COMPLETE"
        and x["client"]["received_digest"] == x["expected_answer_sha256"]
        and x["client"]["first_recv_ns"] <= x["client"]["first_answer_ns"]
        <= x["client"]["full_answer_ns"] < x["client"]["terminal_ns"]
        and x["client"]["request_sent_ns"] <= x["client"]["first_recv_ns"]
        and x["client"]["answer_events"] >= 1
        and x["client"]["progress_events"] >= 1
        and x["client_pid"] != x["server_pid"]
        and x["cleanup"]["client"]["reaped"]
        and x["cleanup"]["server"]["reaped"]
        for x in positive
    )
    valid_negative = all(
        x["status"] != "COMPLETE"
        and x["cleanup"].get("client", {}).get("reaped", False)
        and x["cleanup"].get("server", {}).get("reaped", False)
        for x in negative
    )
    valid = (
        len(cases) == 28 and len(positive) == 12 and len(negative) == 16
        and len({x["case_id"] for x in cases}) == 28
        and len({x["source_sha256"] for x in positive}) == 12
        and len({x["source_revision"] for x in positive}) == 12
        and valid_positive and valid_negative
        and next(x for x in cases if x["mode"] == "progress_only")[
            "client"]["first_answer_ns"] is None
    )
    receipt = {
        "version": VERSION, "fixture": True, "status": PASS if valid else FAIL,
        "namespace": namespace, "source": "local-synthetic-only",
        "attempted": 28, "completed": sum(x["status"] == "COMPLETE" for x in cases),
        "rejected_or_failed": sum(x["status"] != "COMPLETE" for x in cases),
        "expected_positive": 12, "expected_negative": 16,
        "positive_valid": valid_positive, "negative_valid": valid_negative,
        "first_text_p95_ms": None, "terminal_p95_ms": None,
        "full_answer_p95_ms": None, "denominator_status": "UNKNOWN_HAS_FAILURES",
        "qualified": list(i15.GATES),
        "cases": cases,
    }
    if receipt["completed"] == 28:
        for kind, key in (
            ("first_text_p95_ms", "first_text_ms"),
            ("terminal_p95_ms", "terminal_ms"),
            ("full_answer_p95_ms", "full_answer_ms"),
        ):
            values = sorted(x["client"][key] for x in cases)
            receipt[kind] = values[math.ceil(0.95 * len(values)) - 1]
        receipt["denominator_status"] = "LOCAL_DIAGNOSTIC_ONLY"
    path = scratch / "N21_REAL_EXTERNAL_CLIENT_RECEIPT.json"
    raw = json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return {
        "status": receipt["status"], "path": str(path), "sha256": digest(raw),
        "attempted": 28, "completed": receipt["completed"],
        "rejected_or_failed": receipt["rejected_or_failed"],
        "denominator_status": receipt["denominator_status"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("client", "probe"))
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--port", type=int)
    parser.add_argument("--namespace", default="")
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    if args.action == "client":
        port = args.port
        if port is None:
            print(f"N21_READY:{os.getpid()}", flush=True)
            value = sys.stdin.buffer.readline(16).strip()
            need(value.isdigit(), "PORT_HANDOFF_INVALID")
            port = int(value)
        print(json.dumps(external_client(args.index, port, args.namespace)))
    else:
        need(args.worktree is not None and args.scratch is not None, "PATH_REQUIRED")
        namespace = args.namespace or uuid.uuid4().hex[:16]
        print(json.dumps(suite(args.worktree, args.scratch, namespace),
                         sort_keys=True))


if __name__ == "__main__":
    main()
