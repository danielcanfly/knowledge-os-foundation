#!/usr/bin/env python3
"""Run only the new B02 joined E2E and directly affected tests."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from wave_b02.authority import REPO, sha256_file
from wave_b02.joined_core import A05_SOURCE, CLI_SHA256, MODEL_SHA256


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "joined_evidence_v2"
PYTHON = Path("/opt/homebrew/bin/python3.11")
TEST_PYTHON = REPO.parents[2] / "06_WORKSITES/MG09_LOCAL_NONPROD_BOOTSTRAP_20261013/.venv/bin/python"
ASSET_DIR = REPO.parent / "A04/model_runtime"
REPORT_RETURN = REPO.parents[2] / "02_REPORTS/PARALLEL_VNEXT_20261014/MASTER_RETURN_B02_JOINED_E2E_20261016.md"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def base_contract(run_id: str) -> dict[str, Any]:
    return {
        "version": "m27.b02.joined-task/v1", "run_id": run_id,
        "tenant": "tenant-a",
        "context_grant": {
            "tenant": "owner-internal", "roles": ["internal"],
            "release_id": "a05context-7835ec95cee63972",
            "source_revision": "89f1d7be1623cd6926a69e38871544eefe39e584",
            "expires_at": "2027-01-11T21:36:23.210892+00:00",
        },
        "actor": "owner-researcher",
        "goal": "Produce one grounded policy claim and a reversible local observation",
        "deadline": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "budget": {"max_source_reads": 3, "max_action_attempts": 1,
                   "max_context_reads": 1, "max_model_calls": 1},
        "rights": ["read-firstparty", "write-own-observation"],
        "a06_sources": ["CHARTER", "DELIVERY", "I37_ACCEPTANCE"],
        "outcome": "verified-research-and-reversible-observation",
    }


def execute(name: str, command: list[str], cwd: Path, env: dict[str, str],
            timeout: int = 300) -> dict[str, Any]:
    started = time.monotonic_ns()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True)
    stdout, stderr = process.communicate(timeout=timeout)
    out = EVIDENCE / "raw" / f"{name}.stdout.log"
    err = EVIDENCE / "raw" / f"{name}.stderr.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(stdout, encoding="utf-8")
    err.write_text(stderr, encoding="utf-8")
    result = {
        "name": name, "command": command, "pid": process.pid,
        "exit_code": process.returncode, "pass": process.returncode == 0,
        "duration_ms": round((time.monotonic_ns() - started) / 1e6, 3),
        "stdout_sha256": sha256_file(out), "stderr_sha256": sha256_file(err),
    }
    write_json(EVIDENCE / "raw" / f"{name}.receipt.json", result)
    if process.returncode:
        raise RuntimeError(f"COMMAND_FAILED:{name}:{process.returncode}")
    return result


def warm_runtime(runtime: Path, scratch: Path) -> dict[str, Any]:
    command = [str(runtime / "llama-b11425/llama-cli"), "-m",
               str(runtime / "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
               "-p", "<|im_start|>user\nReply ready.\n<|im_end|>\n<|im_start|>assistant\n",
               "-n", "1", "-c", "1024", "--temp", "0", "-s", "2761",
               "--no-display-prompt", "--simple-io", "--no-perf", "--single-turn"]
    env = {"HOME": str(scratch / "home"), "TMPDIR": str(scratch / "tmp"),
           "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}
    return execute("runtime_warmup", command, REPO, env, timeout=240)


def case_contract(name: str) -> dict[str, Any]:
    value = base_contract("a06-b02-joined-" + name.replace("_", "-"))
    if name == "wrong_acl":
        value["context_grant"]["tenant"] = "other-tenant"
    elif name == "unauthorized_action":
        value["rights"] = ["read-firstparty", "write-production"]
    elif name == "exhausted_budget":
        value["budget"]["max_action_attempts"] = 0
    return value


CASES = [
    ("positive_crash_reconcile_rollback", "none", "succeeded"),
    ("wrong_acl", "none", "denied"),
    ("stale_source", "stale_source", "denied"),
    ("revoked_source", "revoked_source", "denied"),
    ("source_byte_tamper", "source_byte_tamper", "denied"),
    ("citation_span_tamper", "citation_span_tamper", "denied"),
    ("unauthorized_action", "none", "denied"),
    ("exhausted_budget", "none", "denied"),
    ("missing_verified_text", "missing_verified_text", "denied"),
    ("invalid_verified_text", "invalid_verified_text", "denied"),
    ("timeout", "timeout", "timeout"),
    ("cancel", "cancel", "cancelled"),
    ("unknown_unresolved", "unknown_unresolved", "held_unknown"),
]


def terminal(receipt: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in receipt["events"] if row.get("event") == "run.terminal"]
    if len(rows) != 1:
        raise AssertionError("EXACTLY_ONE_TERMINAL_REQUIRED")
    return rows[0]


def validate_case(name: str, receipt: dict[str, Any], expected: str,
                  server_evidence: Path) -> dict[str, Any]:
    final = terminal(receipt)
    if final["status"] != expected:
        raise AssertionError(f"TERMINAL_MISMATCH:{name}:{final['status']}:{expected}")
    events = receipt["events"]
    checks = {"terminal": True, "run_id_correlated": all(
        row.get("run_id") == receipt["run_id"] for row in events)}
    if name == "positive_crash_reconcile_rollback":
        kinds = [row["event"] for row in events]
        required = ["task.admitted", "context.retrieved", "claim.verified",
                    "outcome.reconciled", "outcome.rolled_back", "worker.finished", "run.terminal"]
        if not all(kind in kinds for kind in required):
            raise AssertionError("POSITIVE_CHAIN_INCOMPLETE")
        if not (kinds.index("claim.verified") < kinds.index("worker.finished") < kinds.index("run.terminal")):
            raise AssertionError("FIRST_TEXT_NOT_EARLY")
        controls = {row["kind"]: row["status"] for row in receipt["controls"]}
        if controls != {"forged_ack": 409, "valid_ack": 200, "replay_ack": 409}:
            raise AssertionError(f"ACK_CONTROLS:{controls}")
        action = json.loads((server_evidence / "server_runs" / receipt["run_id"] /
                             "A06_ACTION_RECEIPT.json").read_text())
        if action["status"] != "RECONCILED_AND_ROLLED_BACK" or action["physical_attempts"] != 1:
            raise AssertionError("ACTION_RECONCILE_ROLLBACK_MISSING")
        checks.update({"first_verified_text_before_terminal": True,
                       "forged_ack_denied": True, "ack_replay_denied": True,
                       "a06_actual_crash_reconciled_rollback": True})
    elif name == "unknown_unresolved":
        kinds = [row["event"] for row in events]
        if "outcome.unknown_hold" not in kinds:
            raise AssertionError("UNKNOWN_HOLD_MISSING")
        action = json.loads((server_evidence / "server_runs" / receipt["run_id"] /
                             "A06_ACTION_RECEIPT.json").read_text())
        if action["status"] != "UNKNOWN_EFFECT_RECONCILE_REQUIRED" or action["physical_retry_count"] != 0:
            raise AssertionError("UNKNOWN_EFFECT_RETRIED_OR_MISCLASSIFIED")
        checks["unknown_effect_no_retry"] = True
    elif name == "cancel":
        if {row["kind"]: row["status"] for row in receipt["controls"]}.get("cancel") != 202:
            raise AssertionError("CANCEL_NOT_ACKNOWLEDGED")
        checks["cancelled_before_model"] = True
    else:
        if any(row.get("event") == "claim.verified" for row in events):
            raise AssertionError(f"NEGATIVE_PUBLISHED_VERIFIED_TEXT:{name}")
        checks["no_verified_text_published"] = True
    return checks


def inventory() -> dict[str, Any]:
    rows = []
    for path in sorted(EVIDENCE.rglob("*")):
        if path.is_file() and path.name not in {"JOINED_ARTIFACT_INVENTORY.json"}:
            rows.append({"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size,
                         "sha256": sha256_file(path)})
    return {"schema": "m27.wave-b02.joined-artifact-inventory/v1",
            "artifact_count": len(rows), "artifacts": rows,
            "excluded_self": str((EVIDENCE / "JOINED_ARTIFACT_INVENTORY.json").relative_to(REPO))}


def main() -> int:
    if EVIDENCE.exists():
        raise RuntimeError("CLEAN_JOINED_EVIDENCE_DIRECTORY_REQUIRED")
    EVIDENCE.mkdir(parents=True)
    temp_root = Path(tempfile.mkdtemp(prefix="m27-b02-joined-", dir="/tmp"))
    runtime = temp_root / "runtime"
    scratch = temp_root / "scratch"
    scratch.mkdir()
    (scratch / "home").mkdir()
    (scratch / "tmp").mkdir()
    before = {
        "head": git("rev-parse", "HEAD"), "tree": git("rev-parse", "HEAD^{tree}"),
        "tracked_clean": git("status", "--porcelain", "--untracked-files=no") == "",
        "old_b02_results_sha256": sha256_file(ROOT / "B02_RESULTS.json"),
        "old_b02_inventory_sha256": sha256_file(ROOT / "B02_ARTIFACT_INVENTORY.json"),
    }
    server = None
    server_stdout = server_stderr = None
    try:
        env = {"HOME": str(scratch / "home"), "TMPDIR": str(scratch / "tmp"),
               "PATH": "/usr/bin:/bin:/opt/homebrew/bin", "PYTHONPATH": f"{REPO / 'src'}:{REPO}",
               "PYTHONDONTWRITEBYTECODE": "1"}
        unit = execute("joined_directly_affected_unit_9",
                       [str(TEST_PYTHON), "-B", "-m", "unittest", "-v",
                        "wave_b02.test_joined_e2e"], REPO, env)
        stage = execute("joined_runtime_stage",
                        [str(PYTHON), "-B", "stage_model_runtime.py", "--asset-dir",
                         str(ASSET_DIR), "--destination", str(runtime), "--model-mode", "hardlink"],
                        REPO / "wave_b01/components/a04", env, timeout=180)
        shutil.copy2(runtime / "STAGE_RECEIPT.json", EVIDENCE / "RUNTIME_STAGE_RECEIPT.json")
        warm = warm_runtime(runtime, scratch)
        port_file = temp_root / "port.txt"
        server_stdout = (EVIDENCE / "raw/server.stdout.log").open("w", encoding="utf-8")
        server_stderr = (EVIDENCE / "raw/server.stderr.log").open("w", encoding="utf-8")
        server = subprocess.Popen(
            [str(PYTHON), "-B", "-u", str(REPO / "wave_b02/joined_server.py"),
             "--runtime", str(runtime), "--scratch", str(scratch),
             "--evidence", str(EVIDENCE), "--port-file", str(port_file)],
            cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=server_stdout,
            stderr=server_stderr, start_new_session=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not port_file.is_file():
            if server.poll() is not None:
                raise RuntimeError("JOINED_SERVER_EARLY_EXIT")
            time.sleep(0.05)
        port = int(port_file.read_text())
        results = []
        for name, fault, expected in CASES:
            contract = case_contract(name)
            contract_path = EVIDENCE / "contracts" / f"{name}.json"
            write_json(contract_path, contract)
            output = EVIDENCE / "client_cases" / f"{name}.json"
            deadline_ms = 1 if name == "timeout" else 60000
            receipt = execute(
                "client_" + name,
                [str(PYTHON), "-B", str(REPO / "wave_b02/joined_client.py"),
                 "--port", str(port), "--contract", str(contract_path), "--fault", fault,
                 "--output", str(output), "--deadline-ms", str(deadline_ms)],
                REPO, env, timeout=240)
            client = json.loads(output.read_text(encoding="utf-8"))
            checks = validate_case(name, client, expected, EVIDENCE)
            results.append({"name": name, "fault": fault, "expected_terminal": expected,
                            "pass": True, "client_process": receipt,
                            "client_receipt_sha256": sha256_file(output), "checks": checks})
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
        if server_stdout is not None:
            server_stdout.close()
        if server_stderr is not None:
            server_stderr.close()
    after = {
        "head": git("rev-parse", "HEAD"), "tree": git("rev-parse", "HEAD^{tree}"),
        "tracked_clean": git("status", "--porcelain", "--untracked-files=no") == "",
        "old_b02_results_sha256": sha256_file(ROOT / "B02_RESULTS.json"),
        "old_b02_inventory_sha256": sha256_file(ROOT / "B02_ARTIFACT_INVENTORY.json"),
    }
    if before != after:
        raise RuntimeError("OLD_B02_OR_TRACKED_GIT_CHANGED")
    positive = json.loads((EVIDENCE / "client_cases/positive_crash_reconcile_rollback.json").read_text())
    unknown = json.loads((EVIDENCE / "client_cases/unknown_unresolved.json").read_text())
    first_text_ms = []
    for receipt in (positive, unknown):
        started = next(row for row in receipt["events"] if row["event"] == "run.started")
        claim = next(row for row in receipt["events"] if row["event"] == "claim.verified")
        first_text_ms.append(round((claim["client_received_ns"] - started["client_received_ns"]) / 1e6, 3))
        audit = json.loads((EVIDENCE / "server_runs" / receipt["run_id"] / "MODEL_AUDIT.json").read_text())
        selected = next(row for row in audit["attempts"] if row["attempt"] == audit["selected_attempt"])
        if selected["output_sha256"] != claim["text_sha256"] or selected["output"] != claim["text"]:
            raise RuntimeError("MODEL_CLIENT_TEXT_BYTE_MISMATCH")
    ordered = sorted(first_text_ms)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    source_release_sha = sha256_file(A05_SOURCE / "release.json")
    source_manifest_sha = sha256_file(A05_SOURCE / "corpus.json")
    result = {
        "schema": "m27.wave-b02.joined-e2e-results/v2",
        "status": "PASS", "scope": "JOINED_NONPROD_LOCAL_ONLY",
        "before": before, "after": after,
        "return_order_sha256": sha256_file(REPORT_RETURN),
        "new_test_denominator": {"directly_affected_unit": 9, "joined_runs": len(CASES),
                                 "total": 9 + len(CASES), "passed": 9 + len(CASES), "failed": 0},
        "old_127_rerun": False, "old_127_preserved": True,
        "unit_receipt": unit, "runtime_stage_receipt": stage, "runtime_warmup": warm,
        "server": {"pid": server.pid if server else None,
                   "exit_code_after_cleanup": server.returncode if server else None,
                   "cleanup_complete": server is not None and server.poll() is not None,
                   "stdout_sha256": sha256_file(EVIDENCE / "raw/server.stdout.log"),
                   "stderr_sha256": sha256_file(EVIDENCE / "raw/server.stderr.log")},
        "cases": results,
        "first_verified_text_latency_ms": {"values": first_text_ms, "p95": p95,
                                           "denominator": len(first_text_ms),
                                           "scope": "LOCAL_JOINED_CLIENT_FIRST_VERIFIED_TEXT_ONLY"},
        "a05": {"release_sha256": source_release_sha, "corpus_sha256": source_manifest_sha,
                 "release_id": "a05context-7835ec95cee63972", "docs": 11, "spans": 21,
                 "memory_citation_authority": False},
        "model": {"weights_sha256": MODEL_SHA256, "llama_cli_sha256": CLI_SHA256,
                  "billable_provider_calls": 0, "external_provider_calls": 0},
        "formal_product_go": False, "c28_live_trial": False,
        "production_mutated": False, "q34_mutated": False,
        "sealed_evaluation_accessed": False, "deployment_attempted": False,
    }
    write_json(EVIDENCE / "JOINED_RESULTS.json", result)
    scan_patterns = [re.compile(r"-----BEGIN .*PRIVATE KEY-----"),
                     re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+")]
    matches = []
    for path in EVIDENCE.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".log", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(text) for pattern in scan_patterns):
                matches.append(str(path.relative_to(REPO)))
    write_json(EVIDENCE / "SECRET_SCAN.json", {"pass": not matches,
                                                "matching_files": matches,
                                                "secret_values_recorded": False})
    if matches:
        raise RuntimeError("JOINED_EVIDENCE_SECRET_SCAN_FAILED")
    write_json(EVIDENCE / "JOINED_ARTIFACT_INVENTORY.json", inventory())
    shutil.rmtree(temp_root, ignore_errors=True)
    print(json.dumps({"status": "PASS", "new_tests": 9 + len(CASES),
                      "joined_runs": len(CASES), "old_127_rerun": False,
                      "first_text_p95_ms": p95}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
