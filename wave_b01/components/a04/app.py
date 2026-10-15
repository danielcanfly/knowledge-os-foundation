#!/usr/bin/env python3
"""A04 isolated first-text streaming reference App. Python 3.11 standard library.
IMPORTANT: fixture producer is deterministic and NOT a live language model.
"""
import argparse
import hashlib
import hmac
import http.server
import json
import os
import re
import signal
import select
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED_MODES = {
    "good", "refuse", "forged_ref", "forged_hash", "forged_span", "contradiction",
    "duplicate", "out_of_order", "repair", "slow", "one", "revoke",
}
MAX_BODY = 4096
MAX_DEADLINE = 4000
MODEL_DEADLINE = 60000
LOCAL_MODEL_MODES = {"real_local", "real_local_negative"}
MIN_DEADLINE = 50

def sha(data):
    return hashlib.sha256(data).hexdigest()

def now():
    return time.monotonic_ns()

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

class Run:
    def __init__(self, run_id, tenant, root):
        self.id = run_id
        self.tenant = tenant
        self.root = root
        self.cancel = threading.Event()
        self.seq = 0
        self.expected_index = 1
        self.lock = threading.RLock()
        self.verified = {}
        self.retracted = set()
        self.client_disconnected = False
        self.terminal = False
        self.journal_path = root / "evidence" / "journals" / (run_id + ".jsonl")

    def journal(self, kind, **fields):
        item = {"kind": kind, "run_id": self.id, "monotonic_ns": now(), **fields}
        with self.lock:
            with self.journal_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return item

class App(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, root):
        self.root = root
        self.manifest = load_json(root / "data" / "manifest.json")
        self.tokens = load_json(root / "data" / "tokens.json")
        self.active = {}
        self.run_lock = threading.RLock()
        super().__init__(addr, Handler)

    def authorization(self, token):
        for tenant, expected in self.tokens.items():
            if hmac.compare_digest(token, expected):
                return tenant
        return None

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        print(json.dumps({"http_log": format % args, "at_ns": now()}), flush=True)

    def reply(self, status, obj):
        body = json.dumps(obj, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def input(self):
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > MAX_BODY:
                return None
            obj = json.loads(self.rfile.read(length))
            return obj if isinstance(obj, dict) else None
        except (ValueError, OSError, json.JSONDecodeError):
            return None

    def tenant(self):
        a = self.headers.get("Authorization", "")
        if not a.startswith("Bearer "):
            return None
        return self.server.authorization(a[7:])

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "nonprod", "provider": "deterministic_external_stub", "native_q34": False})
        else:
            self.reply(404, {"error": "not_found"})

    def do_POST(self):
        tenant = self.tenant()
        if tenant is None:
            return self.reply(401, {"error": "unauthorized"})
        obj = self.input()
        if obj is None:
            return self.reply(400, {"error": "invalid_body"})
        if self.path == "/v1/stream":
            return self.stream(obj, tenant)
        if self.path == "/v1/cancel":
            run_id = obj.get("run_id")
            with self.server.run_lock:
                run = self.server.active.get(run_id)
            if run is None:
                return self.reply(404, {"error": "unknown_run"})
            if run.tenant != tenant:
                return self.reply(403, {"error": "forbidden"})
            run.cancel.set()
            run.journal("cancel.requested")
            return self.reply(202, {"run_id": run_id, "cancel_requested": True})
        if self.path == "/v1/ack":
            run_id = obj.get("run_id")
            with self.server.run_lock:
                run = self.server.active.get(run_id)
            if run is None:
                return self.reply(404, {"error": "unknown_run"})
            if run.tenant != tenant:
                return self.reply(403, {"error": "forbidden"})
            with run.lock:
                proof = run.verified.get(obj.get("seq"))
                correct = isinstance(proof, tuple) and hmac.compare_digest(proof[1], str(obj.get("proof", "")))
                revoked = obj.get("seq") in run.retracted
            if not correct or revoked or not isinstance(obj.get("client_received_ns"), int):
                return self.reply(409, {"error": "unverified_or_retracted_ack"})
            run.journal("client.ack", seq=obj["seq"], proof=obj["proof"],
                        client_received_ns=obj["client_received_ns"])
            return self.reply(200, {"accepted": True})
        return self.reply(404, {"error": "not_found"})

    def stream(self, obj, tenant):
        run_id = obj.get("run_id")
        source_ids = obj.get("source_ids")
        mode = obj.get("mode", "good")
        deadline = obj.get("deadline_ms", 2500)
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,60}", run_id):
            return self.reply(400, {"error": "invalid_run_id"})
        if obj.get("tenant") != tenant:
            return self.reply(403, {"error": "tenant_mismatch"})
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 3 or len(set(map(str,source_ids))) != len(source_ids):
            return self.reply(400, {"error": "invalid_scope"})
        if any(not isinstance(s, str) or s not in self.server.manifest or
               self.server.manifest[s]["tenant"] != tenant for s in source_ids):
            return self.reply(403, {"error": "scope_forbidden"})
        if mode in LOCAL_MODEL_MODES:
            if not os.environ.get("A04_LOCAL_MODEL"):
                return self.reply(403, {"error": "local_model_not_authorized"})
        elif mode not in ALLOWED_MODES or not os.environ.get("A04_TEST_MODE"):
            return self.reply(403, {"error": "test_fixture_only"})
        if not isinstance(deadline, int) or not MIN_DEADLINE <= deadline <= (MODEL_DEADLINE if mode in LOCAL_MODEL_MODES else MAX_DEADLINE):
            return self.reply(400, {"error": "invalid_deadline"})
        with self.server.run_lock:
            if run_id in self.server.active:
                return self.reply(409, {"error": "duplicate_run"})
            run = Run(run_id, tenant, self.server.root)
            self.server.active[run_id] = run
        is_live_model = mode in LOCAL_MODEL_MODES
        provider_kind = "local_open_weight_qwen2.5_0.5b_instruct" if is_live_model else "deterministic_external_stub"
        if is_live_model and len(source_ids) != 2:
            return self.reply(400, {"error": "local_model_exactly_two_sources_required"})
        run.journal("run.admitted", tenant=tenant, allowed_sources=source_ids,
                    deadline_ms=deadline, provider=provider_kind, native_q34=False)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        proc = None
        worker_end = None
        verified_count = 0
        saw_refusal = False
        saw_done = False
        source_revoked = False
        started = now()
        def emit(event_name, **detail):
            run.seq += 1
            event = {"run_id": run.id, "seq": run.seq, "event": event_name, "server_ns": now(),
                     **detail}
            run.journal("event", **event)
            wire = "id: %s\n" % run.seq + "event: %s\n" % event_name + \
                   "data: " + json.dumps(event, sort_keys=True) + "\n\n"
            try:
                self.wfile.write(wire.encode("utf-8"))
                self.wfile.flush()
            except (OSError, BrokenPipeError, ConnectionResetError) as exc:
                run.client_disconnected = True
                run.cancel.set()
                run.journal("client.disconnected", error=type(exc).__name__)
                raise
            return event
        def revocations():
            try:
                obj = load_json(self.server.root / "data" / "revocations.json")
                return set(obj.get("revoked", []))
            except (OSError, ValueError):
                return set(source_ids)  # fail closed on invalid revocation state
        def retract():
            nonlocal verified_count, source_revoked
            gone = revocations()
            with run.lock:
                prior = dict(run.verified)
            for seq, proof_info in prior.items():
                if not isinstance(proof_info, tuple):
                    continue
                source_id, proof = proof_info
                if source_id in gone and seq not in run.retracted:
                    source_revoked = True
                    verified_count -= 1
                    run.retracted.add(seq)
                    emit("claim.retracted", prior_seq=seq, reason="source_revoked")
        def verify(candidate):
            if not isinstance(candidate, dict) or candidate.get("type") != "claim":
                raise ValueError("invalid_candidate")
            index = candidate.get("index")
            if type(index) is not int or index != run.expected_index:
                raise ValueError("claim_sequence")
            source_id = candidate.get("source_id")
            if source_id not in source_ids:
                raise ValueError("source_not_in_scope")
            if source_id in revocations():
                raise ValueError("source_revoked")
            entry = self.server.manifest[source_id]
            if entry["tenant"] != tenant:
                raise ValueError("cross_tenant")
            source = (self.server.root / "data" / entry["file"]).read_bytes()
            actual_sha = sha(source)
            if actual_sha != entry["sha256"]:
                raise ValueError("source_bytes_tampered")
            if candidate.get("source_sha256") != actual_sha:
                raise ValueError("forged_source_digest")
            fact = entry["fact"]
            if candidate.get("fact_key") != fact["key"]:
                raise ValueError("unsupported_fact")
            span = candidate.get("span")
            if span != [fact["start"], fact["end"]]:
                raise ValueError("evidence_span")
            text_bytes = source[span[0]:span[1]]
            if text_bytes.decode("utf-8") != fact["quote"] or candidate.get("quote") != fact["quote"]:
                raise ValueError("evidence_quote")
            sentence = candidate.get("text")
            if not isinstance(sentence, str) or len(sentence) > 180 or not sentence.isascii():
                raise ValueError("text_format")
            if sentence.strip().lower() == fact["quote"].strip().lower():
                raise ValueError("extractive_not_generated")
            if is_live_model:
                # Independently check a bounded fact type, not an exact answer template.
                # Reject unrecognized text and extra claims, even if a model produced it.
                low = sentence.lower()
                known = {"atlas-A": ("atlas", "two", "review", "stage", "intake", "verification"),
                         "delta-B": ("delta", "four", "hour", "every")}
                if source_id not in known:
                    raise ValueError("unqualified_semantic_policy")
                required = known[source_id]
                if not all(v in low for v in required):
                    raise ValueError("semantic_unsupported")
                other_values = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
                expected = required[1]
                actual_numbers = set(re.findall(r"\b(?:"+"|".join(sorted(other_values))+r"|[0-9]+)\b", low))
                if actual_numbers != {expected}:
                    raise ValueError("semantic_number_mismatch")
                if re.search(r"\b(?:not|never|without|false|instead|unless|except|roughly|around)\b", low):
                    raise ValueError("semantic_negation_or_hedge")
                if any(x in low for x in ("dollars","costs","years","months","weeks","financial","profitable")):
                    raise ValueError("semantic_additional_fact")
                if not re.fullmatch(r"[A-Za-z0-9 :;,.\-']{20,180}", sentence) or sentence.count(".") != 1 or not sentence.endswith("."):
                    raise ValueError("semantic_sentence_format")
            elif not re.fullmatch(fact["paraphrase_regex"], sentence):
                raise ValueError("semantic_unsupported")
            proof = sha((source_id + "|" + actual_sha + "|" + str(span) + "|" +
                         fact["key"] + "|" + sentence).encode())
            return {"claim_index": index, "text": sentence, "source_id": source_id,
                    "source_sha256": actual_sha, "span": span, "fact_key": fact["key"],
                    "proof_sha256": proof, "verifier": "bounded_curated_entailment_v1"}
        try:
            emit("run.started", provider=provider_kind)
            if is_live_model:
                cmd = [sys.executable, str(self.server.root / "local_model_provider.py"), mode,
                       str(self.server.root / "data" / "manifest.json"), json.dumps(source_ids)]
            else:
                cmd = [sys.executable, str(self.server.root / "stub_provider.py"), mode,
                       str(self.server.root / "data" / "manifest.json")]
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, start_new_session=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    bufsize=1, text=True, cwd=str(self.server.root))
            run.journal("provider.spawn", pid=proc.pid, command_basename=("local_model_provider.py" if is_live_model else "stub_provider.py"), provider=provider_kind)
            while True:
                if run.client_disconnected:
                    break
                retract()
                if run.cancel.is_set():
                    break
                if (now() - started) / 1e6 > deadline:
                    run.journal("deadline.exceeded", deadline_ms=deadline)
                    break
                ready, _, _ = select.select([proc.stdout], [], [], 0.025)
                if ready:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    if len(line) > 4096:
                        emit("claim.rejected", reason="candidate_too_long")
                        continue
                    try:
                        candidate = json.loads(line)
                    except ValueError:
                        emit("claim.rejected", reason="invalid_json")
                        continue
                    if candidate.get("type") == "refusal":
                        saw_refusal = True
                        emit("safe.refusal", reason="producer_refused")
                        break
                    if candidate.get("type") == "done":
                        saw_done = True
                        break
                    try:
                        attestation = verify(candidate)
                        # Repeat safety check immediately before publication.
                        if run.cancel.is_set() or attestation["source_id"] in revocations():
                            raise ValueError("cancelled_or_revoked_before_publish")
                        with run.lock:
                            run.verified[run.seq + 1] = (attestation["source_id"], attestation["proof_sha256"])
                        event = emit("claim.verified", **attestation)
                        run.expected_index += 1
                        verified_count += 1
                    except (ValueError, OSError, TypeError, KeyError) as exc:
                        emit("claim.rejected", reason=str(exc) if isinstance(exc, ValueError) else "malformed_candidate")
                elif proc.poll() is not None:
                    break
            if saw_done and proc.poll() is None:
                # Producer has reported completion; give it time to exit naturally
                # rather than killing a good run and falsely losing exit status 0.
                try: proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired: pass
            if proc.poll() is None:
                # Kill isolated process group, including any local model subprocess;
                # do not leave an uncontrolled decoder running after cancellation.
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    proc.wait(timeout=1.0)
            stderr = proc.stderr.read(2048) if proc.stderr is not None else ""
            run.journal("provider.exit", pid=proc.pid, exit_code=proc.returncode,
                        stderr=stderr, kind_of_provider=provider_kind)
            worker_end = now()
            run.journal("worker.finished", worker_finished_ns=worker_end)
            if not run.client_disconnected:
                retract()
                emit("worker.finished", worker_finished_ns=worker_end)
                timed_out = (worker_end - started) / 1e6 > deadline
                status = ("cancelled" if run.cancel.is_set() else "timeout" if timed_out else
                          "refused" if saw_refusal else
                          "succeeded" if verified_count >= 2 and not source_revoked and proc.returncode == 0 else "rejected")
                if source_revoked and status == "succeeded":
                    status = "rejected"
                emit("run.terminal", status=status, verified_current=verified_count)
                run.terminal = True
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            if not run.client_disconnected:
                run.client_disconnected = True
                run.journal("client.disconnected", error=type(exc).__name__)
        finally:
            if proc is not None and proc.poll() is None:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait(timeout=1)
            run.journal("run.closed", client_disconnected=run.client_disconnected,
                        terminal_sent=run.terminal, worker_finished_ns=worker_end)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--port-file", type=Path, required=True)
    args = ap.parse_args()
    (ROOT / "evidence" / "journals").mkdir(parents=True, exist_ok=True)
    server = App(("127.0.0.1", args.port), ROOT)
    args.port_file.write_text(str(server.server_address[1]), encoding="utf-8")
    print(json.dumps({"kind": "app.listen", "port": server.server_address[1],
                      "pid": os.getpid(), "provider_modes": ["deterministic_external_stub", "local_open_weight_qwen2.5_0.5b_instruct"]}), flush=True)
    try:
        server.serve_forever(poll_interval=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
