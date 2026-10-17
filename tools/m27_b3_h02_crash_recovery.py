"""B3-03 two real SIGKILL boundaries and independent G02 durable recovery."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/knowledge_engine"
sys.path.insert(0, str(SRC))
pkg = types.ModuleType("knowledge_engine")
pkg.__path__ = [str(SRC)]
sys.modules["knowledge_engine"] = pkg

from m27_b0_research_outcome import canonical
from m27_b1_g02_native_bridge import ResearchBridge, REQUEST_SCHEMA
from m27_task_contracts_v1 import sha256 as task_sha


def run(input_dir: Path, receipt_dir: Path) -> None:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    output = receipt_dir / "outcome"
    output.mkdir(exist_ok=True)
    c = json.loads((input_dir / "task_contract.json").read_bytes())
    s = json.loads((input_dir / "sources.json").read_bytes())
    contract = receipt_dir / "task_contract.json"
    registry = receipt_dir / "sources.json"
    contract.write_bytes(canonical(c))
    registry.write_bytes(canonical(s))
    db = receipt_dir / "research.sqlite"
    run_id = "b3-h02-joined-recovery-20261017"
    journal = []
    for marker in ("AFTER_STEP_1", "AFTER_FINALIZATION"):
        cmd = [
            sys.executable, str(SRC / "m27_b0_research_outcome.py"),
            "--db", str(db), "--contract", str(contract),
            "--sources", str(registry), "--out", str(output),
            "--run-id", run_id, "--pause-at", marker,
        ]
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            ready, _writes, _errors = select.select([p.stdout], [], [], 12)
            if not ready:
                raise RuntimeError(marker + ":NO_PAUSE_RECEIPT")
            line = p.stdout.readline().strip()
            if line != "G02_PAUSE_BOUNDARY=" + marker:
                raise RuntimeError(marker + ":WRONG_BOUNDARY:" + line[:100])
            pid = p.pid
            p.send_signal(signal.SIGKILL)
            ended = p.wait(timeout=6)
            if ended != -signal.SIGKILL:
                raise RuntimeError(marker + ":NOT_ACTUAL_OS_SIGKILL")
            with sqlite3.connect(db) as conn:
                events = conn.execute(
                    "SELECT seq,kind FROM g02_events WHERE run_id=? ORDER BY seq",
                    (run_id,)).fetchall()
            expected = 2 if marker == "AFTER_STEP_1" else 4
            if len(events) != expected:
                raise RuntimeError(marker + ":JOURNAL_WAS_NOT_DURABLE:" + repr(events))
            journal.append({
                "marker": marker, "actual_os_pid": pid, "exit_signal": 9,
                "durable_event_count": len(events),
                "event_kinds": [event[1] for event in events],
            })
        finally:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=6)
    checker = ROOT / "tools/m27_b0_research_independent_check.py"
    bridge = ResearchBridge(
        contract_path=contract, registry_path=registry, db_path=db,
        outcome_dir=output, independent_checker=checker,
        tenant_id="owner-m27-nonprod", principal_id="owner-delegated-b0-02")
    q = dict(schema=REQUEST_SCHEMA, request_id="b3-h02-killed-then-recovered",
             run_id=run_id, task_id=c["task_id"], task_version=c["task_version"],
             tenant_id="owner-m27-nonprod", principal_id="owner-delegated-b0-02",
             contract_sha256=task_sha(c),
             registry_sha256=hashlib.sha256(canonical(s)).hexdigest(),
             outcome_id=c["output_specs"][0]["outcome_id"])
    recovered = bridge.dispatch(q)
    read_again = bridge.dispatch(q)
    assert recovered == read_again
    assert recovered["state"] == "DURABLE_SOURCE_BACKED_RESEARCH_READBACK_PASS"
    assert recovered["citations"] == 4
    with sqlite3.connect(db) as conn:
        events = conn.execute(
            "SELECT kind FROM g02_events WHERE run_id=? ORDER BY seq", (run_id,)
        ).fetchall()
    assert [k for (k,) in events] == [
        "PLANNED", "CHARTER_EXTRACTED", "AUDIT_COMPARED", "OUTCOME_COMMITTED"]
    response = dict(
        result="PASS_SCOPED_NONPROD_SIGKILL_G02_RECOVERY",
        signals=journal,
        final_event_count=len(events),
        receipt_sha256=recovered["receipt_sha256"],
        markdown_sha256=recovered["markdown_sha256"],
        json_sha256=recovered["json_sha256"],
        journal_head_sha256=recovered["journal_head_sha256"],
        independently_verified_citations=recovered["citations"],
        byte_identical_resume=True,
        answer_cache_used=False,
        formal_product_qualified=False)
    (receipt_dir / "crash_recovery_receipt.json").write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n")
    print(json.dumps(response, indent=2, sort_keys=True))


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
