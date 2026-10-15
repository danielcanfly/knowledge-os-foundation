#!/usr/bin/env python3
"""Run reproducible B01 acceptance groups and seal raw stdout/stderr hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
WAVE = ROOT.parents[2]
REPORTS = WAVE / "02_REPORTS" / "PARALLEL_VNEXT_20261014"
EVIDENCE = ROOT / "wave_b01" / "evidence" / "acceptance"
PRIVATE_STORE = ROOT / "wave_b01" / "evidence" / "private_store"
PY = WAVE / "06_WORKSITES" / "MG09_LOCAL_NONPROD_BOOTSTRAP_20261013" / ".venv" / "bin" / "python"
MG36 = WAVE / "06_WORKSITES" / "MG36_STREAM_OFF_REMAINING_NONPROD_TESTS_20261014"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict[str, str]:
    external_tmp = REPORTS / "B01_EVIDENCE" / "tmp"
    external_home = external_tmp / "home"
    external_test_tmp = external_tmp / "test-tmp"
    external_home.mkdir(parents=True, exist_ok=True)
    external_test_tmp.mkdir(parents=True, exist_ok=True)
    return {
        # Keep all ephemeral test state outside the repository.  Several M26
        # tests intentionally copy the repository and would recursively copy
        # pytest scratch if HOME or TMPDIR lived under ROOT.
        "HOME": str(external_home),
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
        "PYTHONPATH": f"{MG36}:{ROOT / 'src'}:{ROOT}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "APP_ENV": "test",
        "MG36_STREAMING_MODE": "disabled",
        "AUTH_MODE": "disabled",
        "OBJECT_STORE_BACKEND": "filesystem",
        "FILESYSTEM_STORE_ROOT": str(PRIVATE_STORE),
        "KNOWLEDGE_CHANNEL": "mg27-owner-lexical-test-only",
        "M26_ACCEPTED_PRODUCTION_RELEASE_ID": "mg27ownerlex-7835ec95cee63972",
        "M26_ACCEPTED_PRODUCTION_MANIFEST_KEY":
            "releases/mg27ownerlex-7835ec95cee63972/manifest.json",
        "M26_ACCEPTED_PRODUCTION_MANIFEST_SHA256":
            "187fa1aeb5cbc3b81709f53846d4efa10cfda347abf789a1aee5c2a2ebf05d2d",
        "M26_ACCEPTED_QDRANT_COLLECTION": "a01-offline-no-vectors",
        # Several accepted M27 packaging/socket tests correctly reject scratch
        # space located inside any Git worktree.
        "TMPDIR": str(external_test_tmp),
    }


def selectors(name: str) -> list[str]:
    path = REPORTS / "A01_EVIDENCE" / f"{name}.invocation.log"
    value = json.loads(path.read_text(encoding="utf-8"))
    return list(value["selectors"])


def execute(name: str, command: list[str], cwd: Path, expectation: str) -> dict:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment(),
        text=True,
        capture_output=True,
        timeout=900,
        errors="replace",
    )
    output = completed.stdout + ("\n" if completed.stdout else "") + completed.stderr
    # Accepted archive/package regressions can create several GiB of disposable
    # scratch.  Remove only this runner-owned, outside-worktree directory after
    # the child has exited so evidence sealing itself cannot fail for disk space.
    external_tmp = REPORTS / "B01_EVIDENCE" / "tmp"
    scratch_bytes = sum(path.stat().st_size for path in external_tmp.rglob("*")
                        if path.is_file()) if external_tmp.exists() else 0
    if external_tmp.exists():
        shutil.rmtree(external_tmp)
    log = EVIDENCE / f"{name}.log"
    log.write_text(output, encoding="utf-8")
    summaries = [line for line in output.splitlines()
                 if re.search(r"\b(passed|failed|tests? in|OK|SUMMARY|all_pass)\b", line)]
    if expectation == "pass":
        accepted = completed.returncode == 0
    elif expectation == "m26_historical_6":
        accepted = (completed.returncode == 1
                    and any("6 failed, 857 passed" in line for line in summaries))
    else:
        raise ValueError("UNKNOWN_EXPECTATION")
    record = {
        "schema": "m27.wave-b01.test-receipt/v1",
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "expectation": expectation,
        "expectation_met": accepted,
        "seconds": round(time.monotonic() - started, 3),
        "disposed_test_scratch_bytes": scratch_bytes,
        "summary": summaries[-30:],
        "log": str(log),
        "log_sha256": sha256(log),
    }
    receipt = EVIDENCE / f"{name}.json"
    receipt.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    record["receipt_sha256"] = sha256(receipt)
    print(json.dumps(record, indent=2, ensure_ascii=False), flush=True)
    return record


def pytest_command(paths: list[str]) -> list[str]:
    return [str(PY), "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--disable-warnings", "--tb=short", *paths]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("targeted", "components", "m27", "m26"))
    args = parser.parse_args()
    if args.suite == "targeted":
        records = [
            execute("b01_cross_module_10",
                    [str(PY), "-B", "-m", "unittest", "-v",
                     "wave_b01.test_integration"], ROOT, "pass"),
            execute("a01_a08_a09_targeted_78", pytest_command([
                "tests/test_a01_fast_public_contract_v2.py",
                "tests/test_a01_production_bridge_negative.py",
                "tests/test_m27_production_evidence_bridge.py",
                "tests/test_m27_a09_abi_conformance.py",
                "a08_nonprod/test_experiment.py",
            ]), ROOT, "pass"),
        ]
    elif args.suite == "components":
        records = [
            execute("a05_component_31", [str(PY), "-B", "a05_run_tests.py"],
                    ROOT / "wave_b01/components/a05/adapter", "pass"),
            execute("a06_component_25", [str(PY), "-B", "-m", "unittest", "-v",
                                                 "test_a06"],
                    ROOT / "wave_b01/components/a06", "pass"),
            execute("a07_component_21", [str(PY), "-B", "-m", "unittest", "-v",
                                                 "test_a07_memory"],
                    ROOT / "wave_b01/components/a07", "pass"),
        ]
    elif args.suite == "m27":
        records = [execute("m27_85_modules", pytest_command(
            selectors("m27_85_after_repair")), ROOT, "pass")]
    else:
        records = [execute("m26_75_modules_historical", pytest_command(
            selectors("m26_75_after_repair")), ROOT, "m26_historical_6")]
    return 0 if all(record["expectation_met"] for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
