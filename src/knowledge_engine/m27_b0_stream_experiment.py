"""B0-03 exclusively isolated, loopback-only verified model-generation stream.
Not wired to M26, Q34, shared gateway, native composer or production.
Conservative source-specific claim grammar, NOT general semantic entailment/IdP.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/07_MASTER_REBASE_20261010/08_MASTER_TAKEOVER_20261012/09_MASTER_RESET_POST_V34_20261013")
SOURCE = ROOT / "01_DISPATCH/REPLAN_B0_20261017/B0-00_SHARED_RULES_20261017.md"
SOURCE_SHA256 = "5d54676e235557648a488380385212d31e1953d206028e9881c6b58134d1ebb4"
MODEL = ROOT / "06_WORKSITES/PARALLEL_VNEXT_20261014/A04/model_runtime/qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
CLI = ROOT / "06_WORKSITES/PARALLEL_VNEXT_20261014/A04/model_runtime/llama-b11425/llama-cli"
CLI_SHA256 = "cf4f088f32507af619a1d65516d235ef7644db8c81ff1d3e175ff640dab75ab7"
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct-GGUF Q4_K_M"
OWNER = "B0_LOCAL_OWNER_TEST_ONLY"
MAX_NEW_TOKENS = 52
MODEL_DEADLINE_SEC = 25
FACTS = (
    ("cache", "Initial semantic answer cache remains OFF in Nonprod."),
    ("commander", "All new engineering uses Remote Desktop Commander first on MacBook."),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def authorize_source(name: str, *, principal: str = OWNER, rights: bool = True,
                     revoked: bool = False, source_path: Path = SOURCE,
                     expected_sha: str = SOURCE_SHA256) -> dict:
    if principal != OWNER or not rights or revoked:
        raise ValueError("source_acl_or_revocation_denied")
    data = source_path.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError("source_digest_mismatch")
    matching = [(key, quote) for key, quote in FACTS if key == name]
    if len(matching) != 1:
        raise ValueError("unknown_fact")
    key, quote = matching[0]
    fragment = quote.encode("utf-8")
    if data.count(fragment) != 1:
        raise ValueError("source_span_not_unique")
    start = data.index(fragment)
    return {"source_id": "B0-OWNER-RULES/" + key, "source_sha256": expected_sha,
            "source_path": str(source_path), "byte_span": [start, start + len(fragment)],
            "excerpt_sha256": sha(fragment), "quote": quote, "rights": "owner-first-party-nonprod",
            "principal": principal, "revoked": False}


def verify_generated(text: str, binding: dict) -> dict:
    # Enforce exact source snapshot/byte span at publication time, not just proposal time.
    try:
        fresh = authorize_source(binding["source_id"].split("/")[-1],
                                 principal=binding.get("principal", ""),
                                 rights=binding.get("rights") == "owner-first-party-nonprod",
                                 revoked=binding.get("revoked", True))
    except (ValueError, OSError, KeyError) as exc:
        return {"accepted": False, "reason": str(exc)}
    for key in ("source_sha256", "byte_span", "excerpt_sha256", "quote", "source_id"):
        if binding.get(key) != fresh[key]:
            return {"accepted": False, "reason": "binding_" + key + "_mismatch"}
    text = text.strip()
    low = text.lower()
    if not text or len(text) > 240 or len(text.split()) > 32:
        return {"accepted": False, "reason": "empty_or_unbounded_output"}
    if re.search(r"[\r\n<>]|(?:\.\s+\S)", text):
        return {"accepted": False, "reason": "multi_claim_or_markup"}
    if re.search(r"\d", text):
        return {"accepted": False, "reason": "unattested_quantity"}
    if re.search(r"\b(?:always|never|production|globally|all tenants|paid|free|guarantees?|permanent|unrestricted)\b", low):
        return {"accepted": False, "reason": "unsupported_extension"}
    # Closed vocabulary per owner-authored fact: do not accidentally approve extra clauses
    # merely because a generated sentence contains required key terms.
    permitted_cache = set("the initial initially semantic answer cache is remains off in nonprod disabled by default currently stays turned not enabled".split())
    permitted_commander = set("all new engineering uses use remote desktop commander first on macbook for work tasks initially is used the tool starting with should a must".split())
    allowed_words = permitted_cache if binding["source_id"].endswith("/cache") else permitted_commander
    if any(token not in allowed_words for token in re.findall(r"[a-z]+", low)):
        return {"accepted": False, "reason": "extra_claim_vocabulary_outside_source"}
    if binding["source_id"].endswith("/cache"):
        ok = ("semantic" in low and "cache" in low and "nonprod" in low
              and any(x in low for x in ("off", "disabled", "not enabled", "turned off"))
              and not re.search(r"\b(?:enabled|on)\b", low.replace("not enabled", "").replace("turned off", "")))
    else:
        ok = ("remote desktop commander" in low and "macbook" in low
              and any(x in low for x in ("first", "initial", "starting"))
              and any(x in low for x in ("engineering", "work", "task", "process")))
    if not ok:
        return {"accepted": False, "reason": "bounded_entailment_not_established"}
    return {"accepted": True, "reason": "bounded_owner_source_fact_verified",
            "source_id": fresh["source_id"], "source_sha256": fresh["source_sha256"],
            "byte_span": fresh["byte_span"], "excerpt_sha256": fresh["excerpt_sha256"],
            "text_sha256": sha(text.encode("utf-8"))}


def generate_local(quote: str, seed: int, *, audit=None) -> str:
    if digest_file(MODEL) != MODEL_SHA256 or digest_file(CLI) != CLI_SHA256:
        raise RuntimeError("local_model_or_binary_pin_mismatch")
    prompt = ("<|im_start|>system\n"
              "Write ONE short factual English sentence paraphrasing the given evidence. "
              "Keep all named entities, temporal qualifiers, and whether something is OFF or FIRST. "
              "Do not introduce extra facts, numbers, or interpretations. "
              "Do not copy the evidence word for word. No explanation.\n"
              "<|im_end|>\n<|im_start|>user\n"
              "Evidence: " + quote +
              "\nOne-sentence paraphrase only.\n<|im_end|>\n<|im_start|>assistant\n")
    args = [str(CLI), "-m", str(MODEL), "-p", prompt, "-n", str(MAX_NEW_TOKENS),
            "-c", "1024", "--temp", "0.35", "-s", str(seed),
            "--no-display-prompt", "--simple-io", "--no-perf", "--single-turn"]
    begun = time.monotonic_ns()
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=MODEL_DEADLINE_SEC)
    except subprocess.TimeoutExpired as exc:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=3)
        raise RuntimeError("real_model_timeout") from exc
    marker = "<|im_start|>assistant\n"
    output = stdout.rsplit(marker, 1)[-1] if marker in stdout else ""
    for trailer in ("\n[ Prompt:", "\n\n[ Prompt:", "\nExiting...", "\n>"):
        output = output.split(trailer, 1)[0]
    output = output.strip().strip('"').strip("'").strip()
    record = {"kind": "real_llama_model_generation", "pid": proc.pid,
              "model_id": MODEL_ID, "model_sha256": MODEL_SHA256,
              "cli_sha256": CLI_SHA256, "seed": seed, "max_new_tokens": MAX_NEW_TOKENS,
              "request_duration_ms": round((time.monotonic_ns() - begun) / 1e6, 3),
              "finished_ns": time.monotonic_ns(), "exit_code": proc.returncode,
              "model_output": output, "output_sha256": sha(output.encode()),
              "raw_stdout_sha256": sha(stdout.encode()), "stderr_sha256": sha(stderr.encode()),
              "provider_usage_tokens": None, "billable_external_provider_calls": 0}
    if audit:
        audit(record)
    if proc.returncode != 0 or not output:
        raise RuntimeError("model_nonzero_or_empty")
    return output


def verify_in_separate_process(text: str, binding: dict, audit) -> dict:
    """Separate OS verifier recomputes first-party source bytes, not an independent signed issuer."""
    begun = time.monotonic_ns()
    verifier = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "verify"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = verifier.communicate(
            json.dumps({"text": text, "binding": binding}), timeout=5)
    except subprocess.TimeoutExpired as exc:
        verifier.kill()
        verifier.communicate()
        raise RuntimeError("source_verifier_deadline") from exc
    if verifier.returncode != 0:
        raise RuntimeError("source_verifier_process_failed")
    try:
        verdict = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("source_verifier_malformed_result") from exc
    if not isinstance(verdict, dict) or not isinstance(verdict.get("accepted"), bool):
        raise RuntimeError("source_verifier_invalid_contract")
    audit({"kind": "source_verifier_os_process", "verifier_pid": verifier.pid,
           "verifier_code_sha256": digest_file(Path(__file__).resolve()),
           "verifier_process_returncode": verifier.returncode,
           "duration_ms": round((time.monotonic_ns() - begun) / 1e6, 3),
           "stderr_sha256": sha(stderr.encode()), "verdict": verdict})
    return verdict


class ExperimentServer(ThreadingHTTPServer):
    # Join bounded in-flight request handlers on close; do not orphan model/journal work.
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, evidence_dir: Path, *, rights=True, revoked=False,
                 generator=generate_local):
        super().__init__(address, StreamHandler)
        self.rights = rights
        self.revoked = revoked
        self.generator = generator
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.audit_lock = threading.Lock()
        self.ack_lock = threading.Lock()
        self.pending_ack = {}
        self.ack_log = []

    def audit(self, data):
        record = {**data, "written_monotonic_ns": time.monotonic_ns(), "server_pid": os.getpid()}
        with self.audit_lock:
            with (self.evidence_dir / "server_and_model.jsonl").open("a", encoding="utf-8") as fd:
                fd.write(json.dumps(record, sort_keys=True) + "\n")
                fd.flush()
                os.fsync(fd.fileno())


class StreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        return

    def do_POST(self):
        if self.path != "/ack":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n < 1 or n > 3000:
                raise ValueError("invalid_body_length")
            data = json.loads(self.rfile.read(n))
            nonce = data.get("nonce")
            with self.server.ack_lock:
                expected = self.server.pending_ack.get(nonce) if isinstance(nonce, str) else None
                ok = (expected is not None and not expected["ack_seen"]
                      and data.get("request_id") == expected["request_id"]
                      and data.get("seq") == expected["seq"]
                      and data.get("text_sha256") == expected["text_sha256"])
                if ok:
                    expected["ack_seen"] = True
                    expected["event"].set()
            code = 200 if ok else 403
        except (ValueError, TypeError, json.JSONDecodeError):
            code, ok = 400, False
        record = {"kind": "ack_received", "ok": ok, "http_status": code,
                  "received_ns": time.monotonic_ns()}
        self.server.audit(record)
        self.server.ack_log.append(record)
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path != "/stream" or self.headers.get("X-B0-Principal") != OWNER:
            self.send_error(403)
            return
        request_id = secrets.token_hex(10)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-B0-Request", request_id)
        self.end_headers()
        seq = 0
        accepted = []
        try:
            def emit(kind, payload):
                nonlocal seq
                seq += 1
                data = {"request_id": request_id, "seq": seq, **payload}
                wire = ("event: " + kind + "\ndata: " + json.dumps(data, sort_keys=True)
                        + "\n\n").encode("utf-8")
                self.wfile.write(wire)
                self.wfile.flush()
                self.server.audit({"kind": "wire_event", "event": kind, "seq": seq,
                                   "wire_sha256": sha(wire), "event_ns": time.monotonic_ns(),
                                   "request_id": request_id, "body": data})
                return data

            emit("request_started", {"substantive": False})
            for index, (key, _) in enumerate(FACTS):
                binding = authorize_source(key, rights=self.server.rights, revoked=self.server.revoked)
                generated = self.server.generator(binding["quote"], 8001 + index,
                                                  audit=self.server.audit)
                verdict = verify_in_separate_process(generated, binding, self.server.audit)
                self.server.audit({"kind": "source_verifier", "source_id": binding["source_id"],
                                   "verdict": verdict, "model_output_sha256": sha(generated.encode()),
                                   "request_id": request_id})
                if not verdict["accepted"]:
                    raise ValueError("verifier_denied:" + verdict["reason"])
                nonce = secrets.token_hex(16)
                next_seq = seq + 1
                waiter = threading.Event()
                with self.server.ack_lock:
                    self.server.pending_ack[nonce] = {
                        "request_id": request_id, "seq": next_seq,
                        "text_sha256": verdict["text_sha256"],
                        "event": waiter, "ack_seen": False}
                emit("answer_text", {"substantive": True, "generated": True,
                                     "verified": True, "text": generated,
                                     "text_sha256": verdict["text_sha256"],
                                     "citation": {key: verdict[key] for key in
                                                  ("source_id", "source_sha256", "byte_span",
                                                   "excerpt_sha256")}, "nonce": nonce,
                                     "model_id": MODEL_ID})
                accepted.append(generated)
                confirmed = waiter.wait(3.0)
                with self.server.ack_lock:
                    self.server.pending_ack.pop(nonce, None)
                if not confirmed:
                    raise ValueError("independent_client_ack_missing")
            emit("terminal", {"status": "answered", "answer_text": " ".join(accepted),
                              "claims": len(accepted)})
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            self.server.audit({"kind": "client_disconnected", "request_id": request_id,
                               "reason": type(exc).__name__, "accepted_count": len(accepted)})
        except (ValueError, RuntimeError, KeyError) as exc:
            self.server.audit({"kind": "refused", "reason": str(exc), "request_id": request_id})
            try:
                emit("terminal", {"status": "safe_abstention" if not accepted else "partial_terminated",
                                  "answer_text": "", "claims": 0, "reason": str(exc)})
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.server.audit({"kind": "client_disconnected_on_terminal",
                                   "request_id": request_id})
        finally:
            self.server.audit({"kind": "worker_finished", "request_id": request_id,
                               "finished_ns": time.monotonic_ns(), "accepted_count": len(accepted)})


def parse_events(wire: bytes) -> list[tuple[str, dict]]:
    events = []
    for frame in wire.split(b"\n\n"):
        if not frame:
            continue
        lines = frame.split(b"\n")
        if len(lines) != 2 or not lines[0].startswith(b"event: ") or not lines[1].startswith(b"data: "):
            raise ValueError("invalid_sse_frame")
        events.append((lines[0][7:].decode("ascii"),
                       json.loads(lines[1][6:].decode("utf-8"))))
    return events


def validate_client_receipts(events: list[dict]) -> None:
    if not events or events[0]["kind"] != "request_started":
        raise ValueError("missing_start")
    if events[-1]["kind"] != "terminal":
        raise ValueError("missing_terminal")
    seen = set()
    seen_answer = False
    last_time = 0
    request = events[0]["body"]["request_id"]
    for pos, item in enumerate(events):
        if item["client_received_ns"] < last_time:
            raise ValueError("non_monotonic_client_clock")
        last_time = item["client_received_ns"]
        body = item["body"]
        seq = body["seq"]
        if seq != pos + 1 or seq in seen or body["request_id"] != request:
            raise ValueError("broken_sequence")
        seen.add(seq)
        if item["kind"] == "answer_text":
            if not (body.get("generated") and body.get("verified") and body.get("text")
                    and sha(body["text"].encode()) == body.get("text_sha256")
                    and body.get("citation", {}).get("source_sha256") == SOURCE_SHA256
                    and item.get("ack_http_status") == 200):
                raise ValueError("unverified_or_unacked_answer")
            seen_answer = True
        elif item["kind"] == "terminal":
            if pos != len(events) - 1:
                raise ValueError("post_terminal_event")
            if body.get("status") != "answered":
                raise ValueError("terminal_not_answered")
            if not seen_answer:
                raise ValueError("terminal_before_substantive_answer")
    if not seen_answer:
        raise ValueError("empty_progress_only_or_abstained")


def independent_tcp_client(port: int, *, forged_ack=False) -> dict:
    receipt = []
    begun = time.monotonic_ns()
    req = Request("http://127.0.0.1:%d/stream" % port,
                  headers={"X-B0-Principal": OWNER})
    with urlopen(req, timeout=65) as stream:
        data = bytearray()
        while True:
            line = stream.readline()
            if not line:
                break
            data.extend(line)
            if line != b"\n":
                continue
            frame = bytes(data)
            data.clear()
            kind, body = parse_events(frame)[0]
            record = {"kind": kind, "body": body,
                      "client_received_ns": time.monotonic_ns(), "client_pid": os.getpid()}
            if kind == "answer_text":
                ack = {k: body[k] for k in ("request_id", "seq", "text_sha256", "nonce")}
                if forged_ack:
                    ack["nonce"] = "forged-not-the-minted-challenge"
                payload = json.dumps(ack).encode()
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                conn.request("POST", "/ack", body=payload,
                             headers={"Content-Type": "application/json"})
                resp = conn.getresponse()
                record["ack_http_status"] = resp.status
                resp.read()
                conn.close()
            receipt.append(record)
    result = {"client_pid": os.getpid(), "client_started_ns": begun,
              "client_finished_ns": time.monotonic_ns(), "receipts": receipt}
    try:
        validate_client_receipts(receipt)
        result["client_validated"] = True
    except ValueError as exc:
        result["client_validated"] = False
        result["validation_failure"] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("client", "verify"))
    parser.add_argument("--port", type=int)
    parser.add_argument("--forged-ack", action="store_true")
    arguments = parser.parse_args()
    if arguments.mode == "verify":
        payload = json.loads(sys.stdin.read(8192))
        verdict = verify_generated(payload["text"], payload["binding"])
        print(json.dumps(verdict, sort_keys=True), flush=True)
        return
    if not isinstance(arguments.port, int) or not (1 <= arguments.port <= 65535):
        parser.error("client requires a valid --port")
    print(json.dumps(independent_tcp_client(arguments.port, forged_ack=arguments.forged_ack),
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
