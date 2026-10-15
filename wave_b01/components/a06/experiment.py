#!/usr/bin/env python3
"""A06 real OS E2E evidence harness; nonprod local reversible observation only."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import runner

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "evidence" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
PY = sys.executable
records = {}
results = {}

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(label, out, err, exitcode):
    files = {}
    for suffix, text in (("stdout", out), ("stderr", err), ("exit", str(exitcode) + "\n")):
        f = RAW / (label + "." + suffix + ".log")
        f.write_text(text, encoding="utf-8")
        files[suffix] = {"path": str(f), "sha256": sha(f)}
    records[label] = {"exit_code": exitcode, "files": files}
    return exitcode

def command(label, args, expected=0):
    res = subprocess.run([PY, str(ROOT / args[0])] + args[1:],
                         capture_output=True, text=True)
    save(label, res.stdout, res.stderr, res.returncode)
    if res.returncode != expected:
        raise RuntimeError(f"{label} expected rc {expected} got {res.returncode}: {res.stderr}")
    return res.stdout

def new_contract(run_id):
    return {"run_id": run_id, "tenant": "tenant-a", "actor": "owner-researcher",
            "goal": "Research the current M27 task-native mission, bounded I37 acceptance and unresolved AR08 persisted coding gate using exact first-party sources; persist verifiable research and write one authorized reversible observation.",
            "deadline": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "budget": {"max_source_reads": 3, "max_action_attempts": 1},
            "sources": ["CHARTER", "DELIVERY", "I37_ACCEPTANCE"],
            "rights": ["read-firstparty", "write-own-observation"],
            "outcome": "verified-research-and-reversible-observation", "version": "a06-v1"}

def start(run_id, key):
    run_dir = ROOT / "state" / run_id
    db = run_dir / "task.sqlite3"
    if db.exists():
        raise RuntimeError("Refusing to overwrite existing durable experiment: " + str(db))
    run_dir.mkdir(parents=True)
    baseline = {"observation": "idle", "revision": 0}
    runner.atomic(run_dir / "observation.json", runner.encode(baseline))
    contract = run_dir / "contract.json"
    runner.atomic(contract, runner.encode(new_contract(run_id)))
    command(key + "_before", ["observer.py", "--run-id", run_id])
    command(key + "_admit", ["runner.py", "admit", "--db", str(db), "--contract", str(contract)])
    return db

def finish(run_id, key, db):
    command(key + "_after", ["observer.py", "--run-id", run_id])
    ver = command(key + "_independent_verify", ["verifier.py", "--db", str(db), "--run-id", run_id])
    obj = json.loads(ver)
    assert obj["verdict"] == "PASS" and obj["source_count"] == 3 and obj["attempts"] == 1
    con = sqlite3.connect(db)
    events = con.execute("SELECT seq,at,event,body FROM journal ORDER BY seq").fetchall()
    ledger = con.execute("SELECT attempts,status FROM actions WHERE run_id=?", (run_id,)).fetchone()
    con.close()
    state = ROOT / "state" / run_id
    results[key] = {"run_id": run_id, "db_path": str(db),
                    "research_json": str(state / "research.json"),
                    "research_json_sha256": sha(state / "research.json"),
                    "research_markdown": str(state / "research.md"),
                    "research_md_sha256": sha(state / "research.md"),
                    "observation_path": str(state / "observation.json"),
                    "observed_sha256": sha(state / "observation.json"),
                    "ledger": ledger, "journal_events": len(events), "independent_verification": obj}

def os_kill(run_id, key, db):
    child = subprocess.Popen([PY, "-u", str(ROOT / "runner.py"), "run", "--db", str(db),
                              "--run-id", run_id, "--hold-at", "GATHERED_2"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    lines = []
    try:
        for _ in range(12):
            s = child.stdout.readline()
            if not s:
                break
            lines.append(s)
            if "HOLD_POINT GATHERED_2" in s:
                break
        if not any("HOLD_POINT GATHERED_2" in line for line in lines):
            raise RuntimeError("Child never reached real durable checkpoint")
        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=8)
        if child.returncode != -signal.SIGKILL:
            raise RuntimeError("OS SIGKILL not confirmed")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=8)
        stderr = child.stderr.read()
        child.stdout.close()
        child.stderr.close()
    save(key + "_actual_sigkill", f"pid={child.pid}\n" + "".join(lines), stderr, child.returncode)
    command(key + "_resume", ["runner.py", "run", "--db", str(db), "--run-id", run_id])

def main():
    p = ROOT / "evidence" / "experiment_results.json"
    if p.exists():
        raise RuntimeError("Existing experiment receipt, refusing overwrite")
    name = "a06-real-normal-20261014"
    db = start(name, "normal")
    command("normal_run", ["runner.py", "run", "--db", str(db), "--run-id", name])
    finish(name, "normal", db)

    name = "a06-real-sigkill-20261014"
    db = start(name, "sigkill")
    os_kill(name, "sigkill", db)
    finish(name, "sigkill", db)

    name = "a06-real-unknown-20261014"
    db = start(name, "unknown")
    command("unknown_crash_after_effect", ["runner.py", "run", "--db", str(db),
            "--run-id", name, "--inject-unknown"], expected=73)
    con = sqlite3.connect(db)
    assert con.execute("SELECT attempts,status FROM actions").fetchone() == (1,"UNKNOWN")
    con.close()
    command("unknown_pre_reconcile_observe", ["observer.py", "--run-id", name])
    command("unknown_resume", ["runner.py", "run", "--db", str(db), "--run-id", name])
    finish(name, "unknown", db)
    assert results["unknown"]["ledger"] == (1, "RECONCILED")

    name = "a06-real-rollback-20261014"
    db = start(name, "rollback")
    command("rollback_run", ["runner.py", "run", "--db", str(db), "--run-id", name])
    finish(name, "rollback", db)
    command("rollback_action", ["runner.py", "rollback", "--db", str(db), "--run-id", name])
    command("rollback_observed_after", ["observer.py", "--run-id", name])
    failed = command("rollback_expected_verifier_fail",
                     ["verifier.py", "--db", str(db), "--run-id", name], expected=1)
    assert json.loads(failed)["verdict"] == "FAIL"
    con = sqlite3.connect(db)
    assert con.execute("SELECT attempts,status FROM actions").fetchone() == (1, "ROLLED_BACK")
    con.close()
    results["rollback"]["compensation_proved"] = True

    result = {"overall": "PASS", "context": "owner-firstparty local nonprod exact-source research + reversible sandbox action",
              "denominator": 4, "completed": 4, "source_ids": list(runner.ALLOWED),
              "experiments": results, "invocations": records,
              "not_tested": ["historical refused AR08 persisted coding-source edit",
                             "real third-party external action or issuer", "production", "provider LLM",
                             "independent semantic model quality"]}
    runner.atomic(p, runner.encode(result))
    print(json.dumps({"overall": "PASS", "experiments": list(results),
                      "raw_calls": len(records), "receipt": str(p)}, ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("EXPERIMENT_FAILURE: " + type(e).__name__ + ": " + str(e), file=sys.stderr)
        raise
