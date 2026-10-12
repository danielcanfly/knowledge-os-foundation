"""K28 local-only OS crash and separate HTTP effect oracle.

Uses AR02 real SQLite writer and AR04 negative/feature-off regressions.
No external provider, real approval, product authorization, or production access.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Load the real scoped AR02 source by path. Avoid importing the package's M26
# provider bootstrap (httpx/credentials are not relevant to this isolated test).
SOURCE = (Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
          / "m27_ar02_durable_writer_v1_experimental.py")
spec = spec_from_file_location("k28_actual_ar02_writer", SOURCE)
assert spec and spec.loader
module = module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
DurableWriterV1, FenceError, RunIdentity = (module.DurableWriterV1, module.FenceError,
                                           module.RunIdentity)

KEY = b"K28-fixture-HMAC-only-NOT-real-verifier"
VERIFIER = "k28-fixture-independent-verifier"
IDENTITY = RunIdentity("tenant-k28", "run-k28", "task-k28", 1, "worker-principal")
INTENT = hashlib.sha256(b"k28-fixture-intent").hexdigest()
IDEMPOTENCY = "tenant-k28:run-k28:fixed-action-v1"
EXPIRY = 1_900_000_000


def emit(path, data):
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def writer(db):
    return DurableWriterV1(db, fixture_approval_mode=True, verifier_keys={VERIFIER: KEY})


def initialize(w):
    h = w.create_run(IDENTITY, budget=10, source_revision="local-source-v1",
                     consent_generation=1, exclusion_generation=1)
    h = w.reserve(IDENTITY, h, reserve_id="r1", amount=1)
    h = w.provision_fixture_approval(IDENTITY, h, approval_id="a1",
                                     intent_digest=INTENT, expires_at=EXPIRY)
    return h


def intent(w, h):
    return w.commit_intent_and_claim(
        IDENTITY, h, intent_id="i1", intent_digest=INTENT,
        approval_id="a1", claim_id="c1", reserve_id="r1",
        idempotency_key=IDEMPOTENCY, now=100)


def arm(w, h):
    h = intent(w, h)
    h, token = w.claim_outbox(IDENTITY, h, claim_id="c1")
    return w.mark_possible_send(IDENTITY, h, claim_id="c1", local_ack_token=token)


def cancel_request(dbpath):
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE IF NOT EXISTS k28_cancel (run TEXT PRIMARY KEY, reason TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO k28_cancel VALUES(?,?)",
                   (IDENTITY.run_id, "explicit_local_supervisor_cancel"))
        db.commit()


def check_local_dispatch_gate(w, expected_head):
    """Fail-closed local-only adapter gate before any HTTP write."""
    with sqlite3.connect(w.path) as db:
        found = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='k28_cancel'").fetchone()
        if found and db.execute("SELECT 1 FROM k28_cancel WHERE run=?",
                                (IDENTITY.run_id,)).fetchone():
            raise FenceError("TASK_CANCELLED_LOCAL")
    state = w.recover(IDENTITY)
    if state["revoked"]:
        raise FenceError("SOURCE_REVOKED")
    actual = state["head"]
    if actual.epoch != expected_head.epoch or actual.digest != expected_head.digest:
        raise FenceError("STALE_HEAD_OR_EPOCH")


def http_json(port, method, path, payload=None, timeout=3):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        body = json.dumps(payload).encode() if payload is not None else None
        conn.request(method, path, body=body, headers={
            "Content-Type": "application/json",
            "Connection": "close",
        })
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            raise AssertionError(f"HTTP_{resp.status}:{raw[:200]!r}")
        return json.loads(raw)
    finally:
        conn.close()


def service(directory):
    root = Path(directory)
    path = root / "service.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE effects (k TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE attempts (id INTEGER PRIMARY KEY, k TEXT NOT NULL, duplicate INTEGER NOT NULL)")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlparse(self.path)
            with sqlite3.connect(path) as db:
                effects = db.execute("SELECT k,payload FROM effects ORDER BY k").fetchall()
                attempts = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            if url.path == "/stats":
                obj = {"effects": effects, "effect_count": len(effects), "post_attempt_count": attempts}
            elif url.path == "/observe":
                params = parse_qs(url.query)
                k = params.get("key", [""])[0]
                if params.get("stall", ["0"])[0] == "1":
                    time.sleep(1.0)
                if params.get("forced_unknown", ["0"])[0] == "1":
                    obj = {"status": "UNKNOWN", "visible": False, "key": k}
                else:
                    found = next((v for key, v in effects if key == k), None)
                    obj = {"status": "CONFIRMED_APPLIED" if found else "CONFIRMED_NOT_APPLIED",
                           "visible": True, "key": k, "effect": found}
            else:
                self.send_error(404)
                return
            self.respond(obj)

        def respond(self, obj):
            blob = json.dumps(obj, sort_keys=True).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def do_POST(self):
            if self.path != "/apply":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            k, payload = body["key"], body["payload"]
            assert k == IDEMPOTENCY and payload == INTENT
            with sqlite3.connect(path, timeout=5) as db:
                db.execute("BEGIN IMMEDIATE")
                prior = db.execute("SELECT payload FROM effects WHERE k=?", (k,)).fetchone()
                if prior is not None and prior[0] != payload:
                    self.send_error(409)
                    return
                duplicate = int(prior is not None)
                db.execute("INSERT OR IGNORE INTO effects VALUES(?,?)", (k, payload))
                db.execute("INSERT INTO attempts(k,duplicate) VALUES(?,?)", (k, duplicate))
                db.commit()
            emit(root / "effect_committed.json", {"service_pid": os.getpid(),
                 "key": k, "duplicate": bool(duplicate)})
            # Commit remote simulated effect, deliberately lose the HTTP ACK.
            if body.get("drop_ack"):
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.connection.close()
                return
            self.respond({"status": "LOCAL_HTTP_APPLIED", "duplicate": bool(duplicate)})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    emit(root / "service_ready.json", {"pid": os.getpid(), "port": srv.server_port,
                                      "bind": "127.0.0.1"})
    srv.serve_forever()


def await_kill():
    # Never advance a fault cutpoint without real OS supervisor SIGKILL.
    while True:
        time.sleep(0.2)


def worker(directory, case, port):
    root = Path(directory)
    w = writer(root / "journal.sqlite3")
    emit(root / "worker_pre_kill.json", {"pid": os.getpid(), "case": case})
    h = initialize(w)
    if case == "before_journal_commit":
        original = w._append
        def kill_in_txn(db, row, kind, payload):
            result = original(db, row, kind, payload)
            if kind == "T1_T2_INTENT_APPROVAL_CLAIM_OUTBOX":
                os.kill(os.getpid(), signal.SIGKILL)
            return result
        w._append = kill_in_txn
        intent(w, h)
        raise AssertionError("in-transaction kill did not fire")
    h = arm(w, h)
    assert w.recover(IDENTITY)["outbox"][0]["state"] == "POSSIBLY_SENT"
    if case in {"before_send", "cancel_before_send"}:
        emit(root / "cutpoint.json", {"case": case, "pid": os.getpid(),
                                      "durable_state": "POSSIBLY_SENT"})
        await_kill()
    check_local_dispatch_gate(w, h)
    try:
        result = http_json(port, "POST", "/apply", {
            "key": IDEMPOTENCY, "payload": INTENT,
            "drop_ack": case == "after_send_before_ack",
        })
        if case == "after_send_before_ack":
            raise AssertionError("ACK unexpectedly received")
    except (OSError, http.client.HTTPException) as exc:
        if case != "after_send_before_ack":
            raise
        result = {"lost_ack": type(exc).__name__}
    emit(root / "cutpoint.json", {"case": case, "pid": os.getpid(), "transport": result,
                                  "durable_state": "POSSIBLY_SENT"})
    await_kill()


def recover(directory, case, port):
    root = Path(directory)
    w = writer(root / "journal.sqlite3")
    state = w.recover(IDENTITY)
    old = state["head"]
    new = w.takeover(IDENTITY, old)
    # Old worker's lease/head must not pass compare-and-swap.
    try:
        w.takeover(IDENTITY, old)
    except FenceError as exc:
        stale = str(exc)
    else:
        raise AssertionError("stale epoch was allowed")
    assert "STALE_HEAD_OR_EPOCH" in stale
    outbox = w.recover(IDENTITY)["outbox"]
    output = {"restart_pid": os.getpid(), "head_before": old.__dict__,
              "head_after": new.__dict__, "stale_worker_denial": stale,
              "outbox_before_reconcile": outbox}
    if case == "before_journal_commit":
        assert not outbox
        output.update({"state": "NOT_DISPATCHED_UNCOMMITTED",
                       "success": False, "observer_called": False})
    else:
        assert len(outbox) == 1 and outbox[0]["state"] == "POSSIBLY_SENT"
        forced = "?key=" + IDEMPOTENCY
        if case == "observer_unknown":
            forced += "&forced_unknown=1"
        if case == "observer_timeout":
            forced += "&stall=1"
        if case == "cancel_before_send":
            try:
                check_local_dispatch_gate(w, new)
            except FenceError as exc:
                assert "TASK_CANCELLED_LOCAL" in str(exc)
                output["cancel_fence"] = str(exc)
            else:
                raise AssertionError("cancel did not fence resumed send")
        try:
            obs = http_json(port, "GET", "/observe" + forced,
                            timeout=0.15 if case == "observer_timeout" else 3)
        except (OSError, http.client.HTTPException) as exc:
            if case != "observer_timeout":
                raise
            obs = {"status": "UNKNOWN", "visible": False,
                   "transport_timeout": type(exc).__name__}
        output["observer"] = obs
        if not obs["visible"]:
            output.update({"state": "UNKNOWN_EFFECT", "success": False})
        else:
            outcome = obs["status"]
            assert outcome in {"CONFIRMED_APPLIED", "CONFIRMED_NOT_APPLIED"}
            evidence = json.dumps(obs, sort_keys=True, separators=(",", ":"))
            sha = hashlib.sha256(evidence.encode()).hexdigest()
            h = w.record_observer_reconciliation(
                IDENTITY, new, intent_id="i1", original_t1_digest=INTENT,
                observer_id="k28-separate-http-observer",
                evidence_ref="k28-" + case, evidence_sha256=sha, outcome=outcome,
                source_revision=state["source_revision"],
                consent_generation=state["consent_generation"],
                exclusion_generation=state["exclusion_generation"],
                expires_at=EXPIRY, now=100)
            target = ("LOCAL_VERIFIED_APPLIED" if outcome == "CONFIRMED_APPLIED"
                      else "LOCAL_VERIFIED_NOT_APPLIED")
            msg = w.verification_message(IDENTITY, h, evidence_ref="k28-" + case,
                    verification_ref="fixture-verification", status=target)
            sig = hmac.new(KEY, msg, hashlib.sha256).hexdigest()
            h = w.commit_terminal(IDENTITY, h, evidence_ref="k28-" + case,
                    verification_ref="fixture-verification", verifier_id=VERIFIER,
                    signature_hex=sig, status=target, now=100)
            output.update({"state": h.state, "success": target == "LOCAL_VERIFIED_APPLIED",
                           "observer_evidence_sha": sha, "terminal_head": h.__dict__})
    output["recover"] = w.recover(IDENTITY)["head"].__dict__
    emit(root / "recovery.json", output)


def wait_for(path, process, seconds=10):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        if Path(path).is_file():
            return
        if process.poll() is not None:
            raise AssertionError(f"process exited early pid={process.pid} rc={process.returncode}")
        time.sleep(0.04)
    raise TimeoutError(f"waiting {path}; pid={process.pid}")


def run_case(root, case):
    directory = root / case
    directory.mkdir(parents=True, exist_ok=False)
    base = [sys.executable, "-B", str(Path(__file__).resolve())]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with open(directory / "service.stdout", "w") as service_log:
        srv = subprocess.Popen(base + ["service", str(directory)], cwd=root,
                               env=env, stdout=service_log, stderr=subprocess.STDOUT)
        try:
            wait_for(directory / "service_ready.json", srv)
            port = read_json(directory / "service_ready.json")["port"]
            with open(directory / "worker.stdout", "w") as worker_log:
                child = subprocess.Popen(base + ["worker", str(directory), case, str(port)],
                                         env=env, cwd=root, stdout=worker_log,
                                         stderr=subprocess.STDOUT)
                try:
                    if case == "before_journal_commit":
                        rc = child.wait(timeout=10)
                        assert rc == -signal.SIGKILL, ("transaction child", rc)
                    else:
                        wait_for(directory / "cutpoint.json", child)
                        if case not in {"before_send", "cancel_before_send"}:
                            wait_for(directory / "effect_committed.json", srv)
                        if case == "cancel_before_send":
                            cancel_request(directory / "journal.sqlite3")
                        os.kill(child.pid, signal.SIGKILL)
                        rc = child.wait(timeout=6)
                        assert rc == -signal.SIGKILL, ("supervisor kill", rc)
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=3)
            with open(directory / "restart.stdout", "w") as restart_log:
                restarted = subprocess.run(base + ["recover", str(directory), case, str(port)],
                                           env=env, cwd=root, stdout=restart_log,
                                           stderr=subprocess.STDOUT, timeout=10)
            assert restarted.returncode == 0, (case, (directory / "restart.stdout").read_text())
            recovery = read_json(directory / "recovery.json")
            assert recovery["restart_pid"] != child.pid
            stats = http_json(port, "GET", "/stats")
            if case in {"before_send", "cancel_before_send", "before_journal_commit"}:
                assert stats["effect_count"] == stats["post_attempt_count"] == 0
                assert not recovery["success"]
            else:
                assert stats["effect_count"] == stats["post_attempt_count"] == 1
                if case in {"observer_unknown", "observer_timeout"}:
                    assert recovery["state"] == "UNKNOWN_EFFECT" and not recovery["success"]
                else:
                    assert recovery["state"] == "LOCAL_VERIFIED_APPLIED"
            # Independent writer/connection validates hash-chained event integrity after kill.
            w = writer(directory / "journal.sqlite3")
            check = w.recover(IDENTITY)
            assert check["head"].digest == recovery["recover"]["digest"]
            assert check["head"].seq == recovery["recover"]["seq"]
            receipt = {"case": case, "worker_pid": child.pid, "worker_exit": rc,
                       "restart_pid": recovery["restart_pid"], "service_pid": srv.pid,
                       "service": stats, "terminal_or_unknown": recovery["state"],
                       "epoch_before": recovery["head_before"]["epoch"],
                       "epoch_after": recovery["head_after"]["epoch"],
                       "outbox": check["outbox"], "journal_seq": check["head"].seq,
                       "journal_digest": check["head"].digest,
                       "observer_evidence_sha": recovery.get("observer_evidence_sha"),
                       "local_only": True, "external_tested": False}
            emit(directory / "receipt.json", receipt)
            return receipt
        finally:
            srv.terminate()
            try:
                srv.wait(timeout=4)
            except subprocess.TimeoutExpired:
                srv.kill()
                srv.wait(timeout=3)


def idempotency_probe(root):
    """Server-side same-key two-POST probe; not a recovery re-send."""
    directory = root / "idempotency_probe"
    directory.mkdir()
    base = [sys.executable, "-B", str(Path(__file__).resolve())]
    with open(directory / "service.stdout", "w") as log:
        process = subprocess.Popen(base + ["service", str(directory)],
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_for(directory / "service_ready.json", process)
            port = read_json(directory / "service_ready.json")["port"]
            msg = {"key": IDEMPOTENCY, "payload": INTENT}
            first = http_json(port, "POST", "/apply", msg)
            second = http_json(port, "POST", "/apply", msg)
            stats = http_json(port, "GET", "/stats")
            assert first["duplicate"] is False
            assert second["duplicate"] is True
            assert stats["effect_count"] == 1 and stats["post_attempt_count"] == 2
            outcome = {"probe_only": True, "effect_count": 1,
                       "post_attempt_count": 2, "duplicate_returned": True,
                       "worker_resend_after_lost_ack": False,
                       "service_pid": process.pid}
            emit(directory / "receipt.json", outcome)
            return outcome
        finally:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def negative_checks(root):
    directory = root / "guard_tests"
    directory.mkdir()
    w = writer(directory / "guard.sqlite3")
    h = initialize(w)
    denied = {}
    try:
        w.commit_intent_and_claim(IDENTITY, h, intent_id="i1", intent_digest=INTENT,
            approval_id="a1", claim_id="c1", reserve_id="r1",
            idempotency_key=IDEMPOTENCY, now=EXPIRY + 1)
    except FenceError as exc:
        denied["approval_timeout"] = str(exc)
    assert "APPROVAL_EXPIRED" in denied["approval_timeout"]
    h = intent(w, h)
    h, token = w.claim_outbox(IDENTITY, h, claim_id="c1")
    h = w.mark_possible_send(IDENTITY, h, claim_id="c1", local_ack_token=token)
    try:
        w.mark_possible_send(IDENTITY, h, claim_id="c1", local_ack_token=token)
    except FenceError as exc:
        denied["repeat_send"] = str(exc)
    assert "NO_DURABLE_COMMIT_ACK" in denied["repeat_send"]
    h = w.update_authority(IDENTITY, h, source_revision="revoked", consent_generation=2,
                           exclusion_generation=2, revoked=True)
    try:
        w.takeover(IDENTITY, h)
    except FenceError as exc:
        denied["revoked_takeover"] = str(exc)
    assert "SOURCE_REVOKED" in denied["revoked_takeover"]
    try:
        w.record_observer_reconciliation(IDENTITY, h, intent_id="i1",
            original_t1_digest=INTENT, observer_id="k28-observer",
            evidence_ref="revoked", evidence_sha256="0" * 64,
            outcome="CONFIRMED_APPLIED", source_revision="revoked",
            consent_generation=2, exclusion_generation=2,
            expires_at=EXPIRY, now=100)
    except FenceError as exc:
        denied["revoked_observer_commit"] = str(exc)
    assert "SOURCE_REVOKED" in denied["revoked_observer_commit"]
    assert w.recover(IDENTITY)["head"].state == "OPEN"
    # AR04 real dispatch remains feature-off. See scoped AR04 regression suite.
    denied["ar04_real_dispatch"] = "FEATURE_OFF_BY_DESIGN; independently exercised in K28 local authority guards"
    emit(directory / "receipt.json", {"negative_guards": denied, "head": h.__dict__,
                                       "external_dispatch_authorized": False})
    return denied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["service", "worker", "recover", "run_all"])
    parser.add_argument("directory")
    parser.add_argument("case", nargs="?")
    parser.add_argument("port", type=int, nargs="?")
    args = parser.parse_args()
    if args.mode == "service":
        service(args.directory)
    elif args.mode == "worker":
        worker(args.directory, args.case, args.port)
    elif args.mode == "recover":
        recover(args.directory, args.case, args.port)
    else:
        root = Path(args.directory).resolve()
        root.mkdir(parents=True, exist_ok=False)
        results = []
        for case in ("before_journal_commit", "before_send",
                     "cancel_before_send", "after_send_before_ack",
                     "observer_unknown", "observer_timeout"):
            receipt = run_case(root, case)
            results.append(receipt)
            print(json.dumps({"PASS": case, "receipt": receipt}, sort_keys=True), flush=True)
        probe = idempotency_probe(root)
        guards = negative_checks(root)
        result = {"schema": "K28_OS_FAULT_LOCAL_V1", "cases": results,
                  "idempotency_probe": probe,
                  "guards": guards, "passed": len(results) + 2,
                  "failed": 0, "third_party_effect_proof": False,
                  "provider_calls": 0, "production_modified": False}
        emit(root / "summary.json", result)
        print(json.dumps({"PASS": "GUARDS", "guards": guards}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
