"""Actual separate-OS-process HTTP Client/ACK test with SYNTHETIC model frames.

G01 independent delivery engineering only. Never a real model/gateway/product claim.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from m27_g01_qa_outcome import (
    IndependentVerifier, Journal, OwnerSource, Session,
    SOURCE_SUFFIX, SPANS, OWNER_SOURCE_SHA, task_contract,
)

HERE = Path(__file__).resolve()
SOURCE = HERE.parents[7] / SOURCE_SUFFIX  # replaced by explicit --source on normal runs
ANSWERS = {
    "cache_initial_mode": "The semantic answer cache is OFF in Nonprod initially.",
    "macbook_first_tool": "Remote Desktop Commander is first for engineering on MacBook.",
}


def citation(ob):
    start, end, val = SPANS[ob]
    return {"citation_id": "B0-OWNER-RULES/" + (
        "cache" if ob == "cache_initial_mode" else "commander"),
        "source_sha256": OWNER_SOURCE_SHA, "start_byte": start, "end_byte": end,
        "excerpt_sha256": hashlib.sha256(val.encode()).hexdigest()}


def client(url: str, case: str):
    with urllib.request.urlopen(url + "/session", timeout=5) as resp:
        session = json.load(resp)
    req = urllib.request.Request(url + "/run",
                                 data=json.dumps({"challenge": session["challenge"]}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    events, acks = [], []
    first, terminal = None, None
    first_claim_challenge = None
    with urllib.request.urlopen(req, timeout=12) as stream:
        for raw in stream:
            evt = json.loads(raw)
            t = time.monotonic_ns()
            events.append({"kind": evt["kind"], "status": evt.get("status"),
                           "obligation": evt.get("obligation"), "synthetic": evt.get("synthetic"),
                           "client_mono_ns": t, "text_sha256": evt.get("text_sha256"),
                           "claim_challenge_sha256": (
                               hashlib.sha256(evt["challenge"].encode()).hexdigest()
                               if evt.get("challenge") else None)})
            if evt["kind"] == "answer_text":
                first = first or t
                first_claim_challenge = first_claim_challenge or evt["challenge"]
                if case != "no_ack":
                    payload = {"obligation": evt["obligation"], "challenge": evt["challenge"],
                               "text_sha256": hashlib.sha256(evt["text"].encode()).hexdigest()}
                    if case == "wrong_ack":
                        payload["challenge"] = "forged-claim-token"
                    elif case == "wrong_hash":
                        payload["text_sha256"] = "0" * 64
                    elif case == "wrong_obligation":
                        payload["obligation"] = "nonexistent-claim"
                    ackreq = urllib.request.Request(url + "/ack",
                        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
                        method="POST")
                    try:
                        with urllib.request.urlopen(ackreq, timeout=5) as r:
                            acks.append({"obligation": evt["obligation"],
                                         "http": r.status, "mono_ns": time.monotonic_ns()})
                    except Exception:
                        acks.append({"obligation": evt["obligation"], "http": "DENIED"})
            if evt["kind"] == "terminal":
                terminal = t
    # Replay an already ACKed frame must be rejected, even with known challenge.
    replay_http = None
    if case == "happy":
        ob = "cache_initial_mode"
        replay = {"obligation": ob, "challenge": first_claim_challenge,
                  "text_sha256": hashlib.sha256(ANSWERS[ob].encode()).hexdigest()}
        req = urllib.request.Request(url + "/ack", data=json.dumps(replay).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            replay_http = 200
        except Exception as exc:
            replay_http = getattr(exc, "code", "DENIED")
    print(json.dumps({
        "client_pid": __import__("os").getpid(), "server_pid": session["server_pid"],
        "case": case, "events": events, "acks": acks, "replay_http": replay_http,
        "first_before_terminal": bool(first and terminal and first < terminal),
        "first_to_terminal_ms": ((terminal - first) / 1e6 if first and terminal else None),
        "provider_frames": "SYNTHETIC_LOCAL_FIXTURE_NO_LIVE_MODEL",
        "source_sha256": OWNER_SOURCE_SHA,
    }, sort_keys=True))


def serve(source_path: str, case: str, journal_path: str):
    source = OwnerSource(source_path)
    verifier = IndependentVerifier(sys.executable, str(HERE.with_name("m27_g01_independent_verifier.py")))
    journal = Journal(journal_path)
    session = Session(task=task_contract(), source=source, journal=journal,
                      verifier=verifier, synthetic=True)
    counters = {"claims": 0, "acks": 0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *_):
            return

        def reply(self, status: int, obj: dict):
            raw = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()

        def body(self):
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("BOUNDED_BODY")
            return json.loads(self.rfile.read(size))

        def do_GET(self):
            if self.path != "/session":
                return self.reply(404, {"error": "NOT_FOUND"})
            return self.reply(200, {"challenge": session.challenge,
                                    "server_pid": __import__("os").getpid(),
                                    "schema": "G01_FIXTURE_ONLY"})

        def do_POST(self):
            if self.path == "/ack":
                try:
                    body = self.body()
                    success = set(body) == {"challenge", "text_sha256", "obligation"} and (
                        session.ack(**body))
                except (ValueError, TypeError, KeyError):
                    success = False
                if success:
                    counters["acks"] += 1
                return self.reply(200 if success else 409,
                                  {"accepted": bool(success), "synthetic": True})
            if self.path != "/run":
                return self.reply(404, {"error": "NOT_FOUND"})
            try:
                req = self.body()
                if req != {"challenge": session.challenge}:
                    return self.reply(403, {"error": "CHALLENGE_MISMATCH"})
            except (ValueError, TypeError):
                return self.reply(400, {"error": "INVALID_BODY"})
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Connection", "close")
            self.end_headers()

            def send(evt):
                self.wfile.write(json.dumps(evt).encode() + b"\n")
                self.wfile.flush()

            reason = ""
            done = True
            try:
                for i, obligation in enumerate(SPANS):
                    if case == "second_missing" and i == 1:
                        done = False
                        reason = "SECOND_OBLIGATION_MISSING"
                        break
                    if case == "revoke_midstream" and i == 1:
                        source.revoked = True
                    if case == "cancel_before" and i == 0:
                        session.cancel()
                    answer, cite = ANSWERS[obligation], citation(obligation)
                    if case == "bad_numeric" and i == 0:
                        answer = "The cache is ON for 42 seconds."
                    if case == "bad_citation" and i == 0:
                        cite["start_byte"] = cite["start_byte"] + 1
                    if case == "progress_only":
                        send({"kind": "progress", "synthetic": True})
                        done = False
                        reason = "NO_SUBSTANTIVE_ANSWER"
                        break
                    evt = session.emit(obligation, answer, cite)
                    counters["claims"] += 1
                    send(evt)
                    if not session.await_ack(obligation, timeout=1.5):
                        done = False
                        reason = "ACK_MISSING_OR_INVALID"
                        break
                send(session.terminal(done=done, reason=reason))
            except Exception as exc:
                # The failure is explicitly terminal and never promoted to answered.
                send(session.terminal(done=False, reason=type(exc).__name__))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([sys.executable, str(HERE), "--client",
                                 f"http://127.0.0.1:{port}", "--case", case],
                                capture_output=True, text=True, timeout=16,
                                check=False)
        if result.returncode != 0:
            raise RuntimeError("CLIENT_FAILED:" + result.stderr[-700:])
        data = json.loads(result.stdout)
        data["server_receipts"] = counters
        data["journal_recovered_status"] = journal.recover()
        data["rights"] = "LOCAL_OWNER_SOURCE_ONLY_UNSIGNED_PRODUCT_ISSUER"
        data["primary"] = "CUSTOM_CLOUDFLARE_WORKER_GATEWAY_LIVE_HOLD"
        data["fallback"] = "MINIMAX_LIVE_NOT_USED"
        print(json.dumps(data, sort_keys=True))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client")
    parser.add_argument("--case", choices=("happy", "second_missing", "revoke_midstream",
                        "bad_numeric", "bad_citation", "cancel_before", "no_ack",
                        "progress_only", "wrong_ack", "wrong_hash", "wrong_obligation"),
                        default="happy")
    parser.add_argument("--source")
    parser.add_argument("--journal")
    a = parser.parse_args()
    if a.client:
        client(a.client, a.case)
    else:
        if not a.source or not a.journal:
            parser.error("Explicit source path and isolated journal required")
        serve(a.source, a.case, a.journal)
