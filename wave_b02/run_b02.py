#!/usr/bin/env python3
"""Execute and seal the authorized Wave B02 local Nonprod preflight."""
from __future__ import annotations

import hashlib
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

from wave_b02.authority import (
    REPO,
    build_authority_ledger,
    enforce_provider_budget,
    evaluate_release_gates,
    sha256_file,
    validate_local_model_runtime,
    write_json,
)
from wave_b02.candidate import build_candidate


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
RAW = EVIDENCE / "raw"
PYTHON = Path("/opt/homebrew/bin/python3.11")
TEST_PYTHON = REPO.parents[2] / "06_WORKSITES/MG09_LOCAL_NONPROD_BOOTSTRAP_20261013/.venv/bin/python"
ASSET_DIR = REPO.parent / "A04" / "model_runtime"
MODEL_MANIFEST = REPO / "wave_b01/components/a04/MODEL_RUNTIME_MANIFEST.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clean_env() -> dict[str, str]:
    env = {
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
        "PYTHONPATH": f"{REPO / 'src'}:{REPO}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "APP_ENV": "test",
        "AUTH_MODE": "disabled",
    }
    return env


def execute(name: str, command: list[str], cwd: Path, *, timeout: int = 900,
            extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.time_ns()
    env = clean_env()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(command, cwd=cwd, env=env, text=True,
                               capture_output=True, timeout=timeout, errors="replace")
    stdout = RAW / f"{name}.stdout.log"
    stderr = RAW / f"{name}.stderr.log"
    stdout.write_text(completed.stdout, encoding="utf-8")
    stderr.write_text(completed.stderr, encoding="utf-8")
    receipt = {
        "schema": "m27.wave-b02.test-receipt/v1",
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "started_unix_ns": started,
        "completed_unix_ns": time.time_ns(),
        "exit_code": completed.returncode,
        "pass": completed.returncode == 0,
        "stdout": str(stdout.relative_to(REPO)),
        "stdout_sha256": sha256_file(stdout),
        "stderr": str(stderr.relative_to(REPO)),
        "stderr_sha256": sha256_file(stderr),
        "summary": [line for line in (completed.stdout + "\n" + completed.stderr).splitlines()
                    if re.search(r"(passed|failed|Ran \d+ tests|^OK$|PASS|FAIL)", line)][-30:],
    }
    write_json(RAW / f"{name}.receipt.json", receipt)
    if completed.returncode:
        raise RuntimeError(f"SUITE_FAILED:{name}")
    return receipt


def run_a04() -> tuple[dict[str, Any], dict[str, Any]]:
    if not ASSET_DIR.is_dir():
        raise RuntimeError("AUTHORIZED_A04_ASSET_DIRECTORY_MISSING")
    component_evidence = REPO / "wave_b01/components/a04/evidence"
    if component_evidence.exists():
        raise RuntimeError("A04_COMPONENT_EVIDENCE_NOT_CLEAN")
    temp_root = Path(tempfile.mkdtemp(prefix="m27-b02-local-", dir="/tmp"))
    runtime = temp_root / "runtime"
    scratch = temp_root / "scratch"
    try:
        stage = execute(
            "a04_runtime_stage",
            [str(PYTHON), "-B", "stage_model_runtime.py", "--asset-dir", str(ASSET_DIR),
             "--destination", str(runtime), "--model-mode", "hardlink"],
            REPO / "wave_b01/components/a04", timeout=180,
        )
        runtime_validation = validate_local_model_runtime(runtime, MODEL_MANIFEST)
        write_json(EVIDENCE / "A04_RUNTIME_VALIDATION.json", runtime_validation)
        replay = execute(
            "a04_clean_real_model_21_plus_8",
            [str(PYTHON), "-B", "run_repro_v2.py", "--runtime", str(runtime),
             "--scratch", str(scratch)],
            REPO / "wave_b01/components/a04", timeout=900,
            extra_env={"A04_PYTHON": str(PYTHON)},
        )
        archived = EVIDENCE / "a04_clean_replay"
        shutil.copytree(component_evidence, archived)
        shutil.rmtree(component_evidence)
        return stage, replay
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def a04_metrics() -> dict[str, Any]:
    root = EVIDENCE / "a04_clean_replay"
    stub = json.loads((root / "acceptance_results.json").read_text(encoding="utf-8"))
    real = json.loads((root / "return_model_test_results.json").read_text(encoding="utf-8"))
    positive = json.loads((root / "return_model_cases/two_real_model_generated_claims_preterminal.json").read_text(encoding="utf-8"))
    records = []
    for path in sorted((root / "model_generation").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    successful = [float(row["duration_ms"]) for row in records
                  if row.get("kind") == "real_model_generation" and row.get("exit_code") == 0]
    ordered = sorted(successful)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)] if ordered else None
    enforce_provider_budget(records, max_attempts=8, max_total_ms=120000)
    events = positive["data"]["events"]
    if positive["pass"] is not True or events[-1].get("status") != "succeeded":
        raise RuntimeError("FIRST_GENERATED_VERIFIED_ANSWER_MISSING")
    if sum(event.get("event") == "claim.verified" for event in events) < 2:
        raise RuntimeError("VERIFIED_CLAIM_COUNT_TOO_LOW")
    return {
        "schema": "m27.wave-b02.local-model-metrics/v1",
        "actual_model_inference": real["actual_model_inference"],
        "model": real["model"],
        "model_sha256": real["model_sha256"],
        "deterministic_cases": stub["counts"],
        "real_model_cases": real["counts"],
        "successful_generation_attempts": len(successful),
        "latency_p95_ms": p95,
        "latency_denominator": len(successful),
        "total_generation_duration_ms": round(sum(successful), 3),
        "max_new_tokens_budget_sum": sum(int(row.get("max_new_tokens", 0)) for row in records),
        "billable_provider_calls": sum(int(row.get("billable_provider_calls", 0)) for row in records),
        "first_answer_event_clock": {
            "run_id": positive["data"]["run_id"],
            "first_server_ns": events[0].get("server_ns"),
            "first_client_received_ns": events[0].get("client_received_ns"),
            "terminal_server_ns": events[-1].get("server_ns"),
            "terminal_client_received_ns": events[-1].get("client_received_ns"),
        },
        "positive_receipt_sha256": sha256_file(
            root / "return_model_cases/two_real_model_generated_claims_preterminal.json"),
        "negative_cases": [test["name"] for test in real["tests"] if test["name"] != "two_real_model_generated_claims_preterminal"],
        "native_q34": False,
        "external_provider_calls": False,
    }


def secret_scan() -> dict[str, Any]:
    patterns = [
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._-]{12,}"),
        re.compile(r"(?i)(?:api[_-]?key|client[_-]?secret)\s*[=:]\s*['\"][A-Za-z0-9._-]{12,}"),
    ]
    checked = 0
    matches: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".log", ".md", ".txt", ".py"}:
            continue
        checked += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in patterns):
            matches.append(str(path.relative_to(REPO)))
    return {"pass": not matches, "files_checked": checked, "matching_files": matches,
            "secret_values_recorded": False}


def artifact_inventory() -> dict[str, Any]:
    inventory_path = ROOT / "B02_ARTIFACT_INVENTORY.json"
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path != inventory_path and "__pycache__" not in path.parts:
            rows.append({"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size,
                         "sha256": sha256_file(path)})
    return {"schema": "m27.wave-b02.artifact-inventory/v1", "artifact_count": len(rows),
            "artifacts": rows}


def archive_failed_attempt() -> Path:
    history = ROOT / "history"
    history.mkdir(exist_ok=True)
    number = 1
    while (history / f"attempt_{number:03d}").exists():
        number += 1
    destination = history / f"attempt_{number:03d}"
    destination.mkdir()
    if EVIDENCE.exists():
        shutil.move(str(EVIDENCE), destination / "evidence")
    for name in ("B02_AUTHORITY_LEDGER.json", "B02_RELEASE_GATES.json",
                 "B02_NONPROD_CANDIDATE_MANIFEST.json", "B02_ARTIFACT_INVENTORY.json",
                 "B02_RESULTS.json"):
        path = ROOT / name
        if path.exists():
            shutil.move(str(path), destination / name)
    write_json(destination / "ARCHIVE_RECEIPT.json", {
        "schema": "m27.wave-b02.failed-attempt-archive/v1",
        "reason": "PRESERVED_BEFORE_EXPLICIT_RESUME",
        "destination": str(destination.relative_to(REPO)),
    })
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true",
                        help="preserve a failed attempt and start a fresh evidence directory")
    args = parser.parse_args()
    outputs_exist = EVIDENCE.exists() or any((ROOT / name).exists() for name in (
            "B02_AUTHORITY_LEDGER.json", "B02_RELEASE_GATES.json",
            "B02_NONPROD_CANDIDATE_MANIFEST.json", "B02_ARTIFACT_INVENTORY.json",
            "B02_RESULTS.json"))
    if outputs_exist and args.resume:
        archive_failed_attempt()
    elif outputs_exist:
        raise RuntimeError("CLEAN_B02_OUTPUT_REQUIRED")
    if not TEST_PYTHON.is_file():
        raise RuntimeError("ACCEPTED_TEST_PYTHON_MISSING")
    RAW.mkdir(parents=True)
    ledger = build_authority_ledger()
    write_json(ROOT / "B02_AUTHORITY_LEDGER.json", ledger)

    suites = []
    suites.append(execute("b02_authority_candidate_11",
                          [str(PYTHON), "-B", "-m", "unittest", "-v", "wave_b02.test_b02"], REPO))
    suites.append(execute("b01_cross_module_regression_10",
                          [str(TEST_PYTHON), "-B", "-m", "unittest", "-v", "wave_b01.test_integration"], REPO))
    suites.append(execute("a05_source_context_regression_31",
                          [str(TEST_PYTHON), "-B", "a05_run_tests.py"],
                          REPO / "wave_b01/components/a05/adapter"))
    suites.append(execute("a06_durable_recovery_regression_25",
                          [str(TEST_PYTHON), "-B", "-m", "unittest", "-v", "test_a06"],
                          REPO / "wave_b01/components/a06"))
    suites.append(execute("a07_memory_revocation_regression_21",
                          [str(TEST_PYTHON), "-B", "-m", "unittest", "-v", "test_a07_memory"],
                          REPO / "wave_b01/components/a07"))
    stage, replay = run_a04()
    suites.extend((stage, replay))
    metrics = a04_metrics()
    write_json(EVIDENCE / "B02_LOCAL_MODEL_METRICS.json", metrics)

    candidate_dir = EVIDENCE / "candidate_oci_content"
    candidate = build_candidate(candidate_dir)
    write_json(ROOT / "B02_NONPROD_CANDIDATE_MANIFEST.json", candidate)
    gates = evaluate_release_gates(ledger)
    gates["engineering_suites_pass"] = all(row["pass"] for row in suites)
    gates["candidate_content_hash_verified"] = True
    gates["local_model_e2e_verified"] = (
        metrics["deterministic_cases"] == {"total": 21, "pass": 21, "fail": 0}
        and metrics["real_model_cases"] == {"total": 8, "pass": 8, "fail": 0}
    )
    gates["nonprod_preflight_engineering_pass"] = (
        gates["nonprod_preflight_engineering_pass"]
        and gates["engineering_suites_pass"]
        and gates["candidate_content_hash_verified"]
        and gates["local_model_e2e_verified"]
    )
    write_json(ROOT / "B02_RELEASE_GATES.json", gates)

    scan = secret_scan()
    if not scan["pass"]:
        raise RuntimeError("EVIDENCE_SECRET_SCAN_FAILED")
    write_json(EVIDENCE / "SECRET_SCAN.json", scan)
    result = {
        "schema": "m27.wave-b02.results/v1",
        "status": "PASS" if gates["nonprod_preflight_engineering_pass"] else "FAIL",
        "scope": "NONPROD_PREFLIGHT_ENGINEERING_ONLY",
        "test_suites": suites,
        "test_case_total": 11 + 10 + 31 + 25 + 21 + 21 + 8,
        "local_model_metrics": metrics,
        "release_gates": gates,
        "candidate_manifest_sha256": sha256_file(ROOT / "B02_NONPROD_CANDIDATE_MANIFEST.json"),
        "authority_ledger_sha256": sha256_file(ROOT / "B02_AUTHORITY_LEDGER.json"),
        "release_gates_sha256": sha256_file(ROOT / "B02_RELEASE_GATES.json"),
        "secret_scan": scan,
        "production_mutated": False,
        "q34_mutated": False,
        "sealed_evaluation_accessed": False,
        "external_operations_attempted": False,
        "deployment_attempted": False,
    }
    write_json(ROOT / "B02_RESULTS.json", result)
    write_json(ROOT / "B02_ARTIFACT_INVENTORY.json", artifact_inventory())
    print(json.dumps({"status": result["status"], "tests": result["test_case_total"],
                      "formal_product_go": gates["formal_product_go"],
                      "c28_live_trial": gates["c28_live_trial"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
