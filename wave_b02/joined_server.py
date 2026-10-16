#!/usr/bin/env python3
"""Loopback-only joined B02 Task→A05→Qwen→Verifier→Client→A06 server."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from wave_b02.joined_core import (
    A05_SOURCE,
    ALLOWED_FAULTS,
    REPO,
    a06_projection,
    admit_joined_contract,
    contract_hash,
    generate_local_model,
    retrieve_a05,
    sha256_file,
    verify_generated_claim,
)


class RunState:
    def __init__(self, run_id: str, journal: Path):
        self.run_id = run_id
        self.journal = journal
        self.seq = 0
        self.claim_seq: int | None = None
        self.proof: str | None = None
        self.acked = False
        self.cancelled = False
        self.ack_event = threading.Event()
        self.lock = threading.RLock()

    def record(self, kind: str, **fields: Any) -> dict[str, Any]:
        with self.lock:
            self.seq += 1
            row = {"seq": self.seq, "event": kind, "run_id": self.run_id,
                   "server_ns": time.monotonic_ns(), **fields}
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return row


class JoinedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, *, runtime: Path, scratch: Path, evidence: Path):
        super().__init__(address, handler)
        self.runtime = runtime
        self.scratch = scratch
        self.evidence = evidence
        self.runs: dict[str, RunState] = {}
        self.runs_lock = threading.Lock()


def child(server: JoinedServer, run_dir: Path, name: str, args: list[str],
          expected: tuple[int, ...]) -> dict[str, Any]:
    command = [sys.executable, "-B", str(REPO / "wave_b02/a06_joined_child.py"), *args]
    started = time.monotonic_ns()
    started_process = subprocess.Popen(
        command, cwd=REPO, env={
            "HOME": str(server.scratch / "home"),
            "TMPDIR": str(server.scratch / "tmp"),
            "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
            "PYTHONPATH": f"{REPO / 'src'}:{REPO}",
            "PYTHONDONTWRITEBYTECODE": "1",
        }, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout_value, stderr_value = started_process.communicate(timeout=120)
    stdout = run_dir / f"{name}.stdout.log"
    stderr = run_dir / f"{name}.stderr.log"
    stdout.write_text(stdout_value, encoding="utf-8")
    stderr.write_text(stderr_value, encoding="utf-8")
    receipt = {
        "name": name, "command": command, "pid": started_process.pid,
        "exit_code": started_process.returncode, "expected_exit_codes": list(expected),
        "expectation_met": started_process.returncode in expected,
        "duration_ms": round((time.monotonic_ns() - started) / 1e6, 3),
        "stdout_sha256": sha256_file(stdout), "stderr_sha256": sha256_file(stderr),
    }
    if started_process.returncode not in expected:
        raise RuntimeError(f"A06_CHILD_UNEXPECTED_EXIT:{name}:{started_process.returncode}")
    return receipt


def run_a06_effect(server: JoinedServer, contract: dict[str, Any], run_dir: Path,
                   *, unresolved: bool) -> dict[str, Any]:
    run_id = contract["run_id"]
    action_root = run_dir / "a06_action"
    action_root.mkdir(parents=True)
    db = action_root / "journal.sqlite"
    state = action_root / "state"
    projection_path = action_root / "A06_TASK_CONTRACT.json"
    projection = a06_projection(contract)
    projection_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    common = ["--db", str(db), "--state", str(state), "--run-id", run_id]
    receipts = [child(server, action_root, "admit", ["admit", *common,
                       "--contract", str(projection_path)], (0,))]
    receipts.append(child(server, action_root, "crash_after_effect",
                          ["run", *common, "--inject-unknown"], (73,)))
    observation = state / run_id / "observation.json"
    after_crash = json.loads(observation.read_text(encoding="utf-8"))
    if unresolved:
        observation.unlink()
        receipts.append(child(server, action_root, "resume_unknown_hold",
                              ["run", *common], (1, 2)))
        receipts.append(child(server, action_root, "status_unknown_hold",
                              ["status", *common], (0,)))
        status = json.loads((action_root / "status_unknown_hold.stdout.log").read_text())
        result = {
            "status": "UNKNOWN_EFFECT_RECONCILE_REQUIRED",
            "run_id": run_id, "after_crash": after_crash,
            "after_unobservable": {"observation": "idle", "revision": 0},
            "a06_stage": status["stage"], "action_ledger": status["action"],
            "physical_retry_count": 0, "receipts": receipts,
        }
    else:
        receipts.append(child(server, action_root, "resume_reconcile",
                              ["run", *common], (0,)))
        receipts.append(child(server, action_root, "rollback",
                              ["rollback", *common], (0,)))
        receipts.append(child(server, action_root, "status_after_rollback",
                              ["status", *common], (0,)))
        status = json.loads((action_root / "status_after_rollback.stdout.log").read_text())
        result = {
            "status": "RECONCILED_AND_ROLLED_BACK",
            "run_id": run_id, "after_crash": after_crash,
            "after_rollback": status["observation"],
            "a06_stage": status["stage"], "action_ledger": status["action"],
            "physical_attempts": status["action"][0], "receipts": receipts,
        }
        if result["a06_stage"] != "VERIFIED" or result["action_ledger"][1] != "ROLLED_BACK" \
                or result["after_rollback"] != {"observation": "idle", "revision": 0}:
            raise RuntimeError("A06_RECONCILE_ROLLBACK_NOT_PROVEN")
    path = run_dir / "A06_ACTION_RECEIPT.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["receipt_sha256"] = sha256_file(path)
    return result


class Handler(BaseHTTPRequestHandler):
    server: JoinedServer

    def log_message(self, fmt, *args):
        return

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 65536:
            raise ValueError("INVALID_BODY_LENGTH")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("OBJECT_REQUIRED")
        return value

    def json_response(self, status: int, value: dict[str, Any]):
        data = json.dumps(value, sort_keys=True).encode("utf-8") + b"\n"
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path == "/v1/ack":
            return self.ack()
        if self.path == "/v1/cancel":
            return self.cancel()
        if self.path != "/v1/joined":
            return self.json_response(404, {"error": "NOT_FOUND"})
        try:
            request = self.read_json()
        except Exception as exc:
            return self.json_response(400, {"error": str(exc)})
        contract = request.get("contract")
        run_id = contract.get("run_id") if isinstance(contract, dict) else None
        fault = request.get("fault", "none")
        if not isinstance(run_id, str) or fault not in ALLOWED_FAULTS:
            return self.json_response(400, {"error": "INVALID_JOINED_REQUEST"})
        with self.server.runs_lock:
            if run_id in self.server.runs:
                return self.json_response(409, {"error": "RUN_REPLAY"})
            state = RunState(run_id, self.server.evidence / "server_runs" / run_id / "journal.jsonl")
            self.server.runs[run_id] = state
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Connection", "close")
        self.end_headers()

        def send(kind: str, **fields: Any) -> dict[str, Any]:
            event = state.record(kind, **fields)
            self.wfile.write(json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n")
            self.wfile.flush()
            return event

        run_dir = self.server.evidence / "server_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            send("run.started", fault=fault, external_provider_calls=0)
            if fault == "cancel":
                time.sleep(0.2)
                if state.cancelled:
                    send("run.terminal", status="cancelled", verified_current=0)
                    return
            if fault == "timeout" or int(request.get("deadline_ms", 60000)) < 5:
                time.sleep(0.01)
                send("run.terminal", status="timeout", verified_current=0)
                return
            admission = admit_joined_contract(contract)
            (run_dir / "JOINED_ADMISSION.json").write_text(
                json.dumps(admission, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            send("task.admitted", contract_sha256=admission["joined_contract_sha256"],
                 a06_projection_sha256=admission["a06_projection_sha256"],
                 tenant=contract["tenant"], context_tenant=contract["context_grant"]["tenant"],
                 rights=contract["rights"], budget=contract["budget"])

            source_root = A05_SOURCE
            if fault in {"revoked_source", "source_byte_tamper"}:
                source_root = run_dir / "a05_source_copy"
                shutil.copytree(A05_SOURCE, source_root)
                if fault == "revoked_source":
                    release = json.loads((source_root / "release.json").read_text())
                    corpus = json.loads((source_root / "corpus.json").read_text())
                    target = next(row for row in corpus["docs"] if row["filename"] == "01_contracts.md")
                    (source_root / "revocations.json").write_text(json.dumps({
                        "epoch": 2, "release_id": release["release_id"],
                        "revoked_document_sha256": [target["sha256"]],
                        "schema": "m27.a05.revocation_state.v1",
                    }, sort_keys=True), encoding="utf-8")
                else:
                    with (source_root / "01_contracts.md").open("ab") as handle:
                        handle.write(b"\nB02_TAMPER\n")
            now = (datetime.now(timezone.utc) + timedelta(days=500)) if fault == "stale_source" else None
            context = retrieve_a05(contract, root=source_root, now=now)
            (run_dir / "A05_CONTEXT.json").write_text(
                json.dumps(context, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8")
            citation = context["results"][0]["citation"]
            send("context.retrieved", passage_id=context["results"][0]["passage_id"],
                 source_id=citation["document"], source_sha256=citation["document_sha256"],
                 span=[citation["byte_start"], citation["byte_end"]],
                 excerpt_sha256=citation["excerpt_sha256"], release_id=citation["release_id"],
                 source_revision=citation["source_revision"], revocation_epoch=citation["revocation_epoch"],
                 memory_candidates_included=0)

            if fault == "missing_verified_text":
                text = ""
                audit = {"actual_local_model": False, "reason": "TEST_MISSING_TEXT"}
            elif fault == "invalid_verified_text":
                text = "A completely unsupported statement."
                audit = {"actual_local_model": False, "reason": "TEST_INVALID_TEXT"}
            else:
                text, audit = generate_local_model(
                    self.server.runtime, context["results"][0]["excerpt"],
                    run_dir / "MODEL_AUDIT.json")
            if fault == "citation_span_tamper":
                context = copy.deepcopy(context)
                context["results"][0]["citation"]["byte_end"] -= 1
            claim = verify_generated_claim(context, text, source_root=source_root)
            proof = hashlib.sha256((run_id + "|" + claim["text_sha256"] + "|" +
                                    claim["excerpt_sha256"]).encode()).hexdigest()
            claim["proof_sha256"] = proof
            event = send("claim.verified", **claim,
                         model_output_sha256=claim["text_sha256"],
                         actual_local_model=True, billable_provider_calls=0)
            state.claim_seq = event["seq"]
            state.proof = proof
            if not state.ack_event.wait(timeout=5):
                raise RuntimeError("INDEPENDENT_CLIENT_ACK_TIMEOUT")
            action = run_a06_effect(self.server, contract, run_dir,
                                    unresolved=(fault == "unknown_unresolved"))
            if fault == "unknown_unresolved":
                send("outcome.unknown_hold", action_status=action["status"],
                     action_receipt_sha256=action["receipt_sha256"], physical_retry_count=0)
                send("worker.finished", outcome="UNKNOWN_EFFECT_RECONCILE_REQUIRED")
                send("run.terminal", status="held_unknown", verified_current=1)
                return
            send("outcome.reconciled", action_status="RECONCILED", physical_attempts=1,
                 action_receipt_sha256=action["receipt_sha256"])
            send("outcome.rolled_back", after_rollback=action["after_rollback"])
            send("worker.finished", outcome="verified-research-and-reversible-observation")
            send("run.terminal", status="succeeded", verified_current=1)
        except Exception as exc:
            code = str(exc) if str(exc) else type(exc).__name__
            state.record("run.error", error_type=type(exc).__name__, error_code=code)
            try:
                send("run.terminal", status="denied", verified_current=0,
                     error_type=type(exc).__name__, error_code=code)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def ack(self):
        try:
            request = self.read_json()
            state = self.server.runs[request["run_id"]]
        except Exception:
            return self.json_response(404, {"accepted": False, "error": "UNKNOWN_RUN"})
        with state.lock:
            if state.acked:
                return self.json_response(409, {"accepted": False, "error": "ACK_REPLAY"})
            if request.get("seq") != state.claim_seq or request.get("proof") != state.proof:
                return self.json_response(409, {"accepted": False, "error": "ACK_PROOF_MISMATCH"})
            if not isinstance(request.get("client_received_ns"), int):
                return self.json_response(400, {"accepted": False, "error": "CLIENT_CLOCK_REQUIRED"})
            state.acked = True
            state.record("client.ack", claim_seq=state.claim_seq,
                         client_received_ns=request["client_received_ns"])
            state.ack_event.set()
        return self.json_response(200, {"accepted": True})

    def cancel(self):
        try:
            request = self.read_json()
            state = self.server.runs[request["run_id"]]
        except Exception:
            return self.json_response(404, {"accepted": False})
        state.cancelled = True
        return self.json_response(202, {"accepted": True})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--port-file", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.runtime, args.scratch):
        path = path.resolve()
        if REPO.resolve() == path or REPO.resolve() in path.parents:
            raise ValueError("RUNTIME_SCRATCH_EVIDENCE_MUST_NOT_ALIAS_REPO")
    args.scratch.mkdir(parents=True, exist_ok=True)
    (args.scratch / "home").mkdir(exist_ok=True)
    (args.scratch / "tmp").mkdir(exist_ok=True)
    args.evidence.mkdir(parents=True, exist_ok=True)
    server = JoinedServer(("127.0.0.1", 0), Handler, runtime=args.runtime.resolve(),
                          scratch=args.scratch.resolve(), evidence=args.evidence.resolve())
    args.port_file.write_text(str(server.server_address[1]), encoding="utf-8")
    print(json.dumps({"pid": os.getpid(), "port": server.server_address[1],
                      "scope": "NONPROD_LOOPBACK_ONLY"}), flush=True)
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
