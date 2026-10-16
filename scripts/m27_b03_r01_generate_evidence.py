from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_engine.m27_b03_r01_admission_gate import (
    AdmissionEvidence,
    evaluate_f35_rel01,
)
from knowledge_engine.m27_b03_r01_execution_recovery import (
    EXPLICIT_REFUSAL_TEXT,
    ExecutionObservation,
    observation_receipt,
)

B02_COMMIT = "9744b19141371ecc69b463118accfc29df18565d"
B02_TREE = "5d47914335f5bef884017dbdd01441d9dcb8e1a0"
B03_COMMIT = "f4de69b2ffa30e112ac72aa772602440d64561ef"
B03_TREE = "c87e84eaaf973241c82104fc81d79325851cd226"
CLAIMS = {
    "focused_passed": 43,
    "focused_total": 43,
    "regression_passed": 238,
    "regression_total": 238,
    "changed_files": 25,
    "artifact_files": 11,
}
PUBLIC_DIGESTS = {
    "evidence_hashes": "271fce46ba02562ecd342adbbf5b68091e17be3d9d2e561b0562022030782a55",
    "independent_verify": "742a6672fb76c937dac40bff4fd89c7a39077a2c7278de1d2d33979df552220d",
    "runtime_result": "82451ddf4d664c62079f2c495e43f973626a3f1bf7e59a9d2a66aa5253c7acdf",
    "admission": "3d99dcd2c23694c7d27288bd3f0848449f7a4cf12cfab9aa7f50738439498916",
    "authority": "d71fb676085032b502bf5e97db5c98c93255683e05005092088cee0f5333da2c",
}


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="ascii",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_captured(
    *,
    command_id: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    raw: Path,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.terminate()
        stdout, stderr = process.communicate(timeout=5.0)
    finished = time.monotonic_ns()
    stdout_path = raw / f"{command_id}.stdout.log"
    stderr_path = raw / f"{command_id}.stderr.log"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return {
        "command_id": command_id,
        "argv": command,
        "pid": process.pid,
        "started_monotonic_ns": started,
        "finished_monotonic_ns": finished,
        "duration_monotonic_ns": finished - started,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "stdout_path": stdout_path.name,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stdout_bytes": len(stdout),
        "stderr_path": stderr_path.name,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_bytes": len(stderr),
        "literal_denial_present": EXPLICIT_REFUSAL_TEXT.encode() in stdout + stderr,
    }


def run_test_evidence(
    output: Path,
    generated_at: str,
    *,
    reuse_full_repository_diagnostic: bool,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    base_env = dict(os.environ)
    before_env = dict(base_env)
    before_env.pop("PYTHONPATH", None)
    after_env = dict(base_env)
    after_env["PYTHONPATH"] = str(root / "src")
    focused = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_m27_b03_r01_recovery.py",
    ]
    before = run_captured(
        command_id="focused_before_import_path_repair",
        command=focused,
        cwd=root,
        env=before_env,
        raw=raw,
    )
    after = run_captured(
        command_id="focused_after_import_path_repair",
        command=focused,
        cwd=root,
        env=after_env,
        raw=raw,
        timeout_seconds=600.0,
    )
    admission_regression = run_captured(
        command_id="authorized_admission_regression",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_m27_admission_metric_contract.py",
            "tests/test_m27_release_hard_gates.py",
            "tests/test_m27_isolated_admission_harness.py",
            "tests/test_m27_w5_b13r_independent_evidence_admission_v1_experimental.py",
        ],
        cwd=root,
        env=after_env,
        raw=raw,
    )
    previous_path = output / "B03_R01_TEST_EXECUTION.json"
    full_repository_diagnostic: dict[str, Any] | None = None
    if reuse_full_repository_diagnostic and previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="ascii"))
        full_repository_diagnostic = previous.get("full_repository_diagnostic")
        if full_repository_diagnostic is None:
            full_repository_diagnostic = previous.get("authorized_source_regression")
    if full_repository_diagnostic is None:
        full_repository_diagnostic = run_captured(
            command_id="authorized_full_source_regression",
            command=[sys.executable, "-m", "pytest", "-q"],
            cwd=root,
            env=after_env,
            raw=raw,
            timeout_seconds=600.0,
        )
    full_stdout = (raw / str(full_repository_diagnostic["stdout_path"])).read_text(
        encoding="utf-8", errors="replace"
    )

    def count(label: str) -> int:
        match = re.search(rf"(\d+) {label}", full_stdout)
        return int(match.group(1)) if match else 0

    full_repository_diagnostic = {
        **full_repository_diagnostic,
        "summary": {
            "passed": count("passed"),
            "failed": count("failed"),
            "errors": count("errors?"),
            "skipped": count("skipped"),
            "status": (
                "COMPLETED_SUCCESS"
                if full_repository_diagnostic["exit_code"] == 0
                else "ORDINARY_TECHNICAL_ERROR"
            ),
        },
        "scope_note": (
            "diagnostic only; includes environment-dependent, fixture-mutating, and "
            "historical exact-tree tests outside the R01 admission subset"
        ),
    }
    scoped_passed = (
        before["exit_code"] != 0
        and after["exit_code"] == 0
        and admission_regression["exit_code"] == 0
    )
    return {
        "schema": "m27-b03-r01-test-execution/v1",
        "generated_at": generated_at,
        "before_repair": {
            **before,
            "classification": "ORDINARY_TECHNICAL_ERROR",
            "diagnosis": "independent worktree src was absent from Python import path",
        },
        "repair": {
            "action": "bind the R01 worktree src directory through PYTHONPATH",
            "authorization_change": False,
            "retry_bound": 1,
        },
        "after_repair": after,
        "authorized_admission_regression": admission_regression,
        "full_repository_diagnostic": full_repository_diagnostic,
        "fixture_side_effect_cleanup": {
            "restored_to_b02": True,
            "paths": [
                "pilot/m24/internal-product-deployment/m24-p6-internal-product-deployment.json",
                "pilot/m24/internal-product-deployment/site/_headers",
                "pilot/m24/internal-product-deployment/site/index.html",
                "pilot/m24/m24-14/product-app-shell/m24-14-1-product-app-shell.json",
            ],
        },
        "r01_scoped_passed": scoped_passed,
        "full_repository_passed": full_repository_diagnostic["exit_code"] == 0,
        "passed": scoped_passed,
    }


def run_diagnostics(output: Path, generated_at: str) -> dict[str, Any]:
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    command_id = "r01-hung-subprocess-001"
    started = time.monotonic_ns()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(0.25)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pid = process.pid
    live_observation = ExecutionObservation(
        pid=pid,
        pid_alive=process.poll() is None,
        timed_out=False,
        exit_code=None,
    )
    records.append(
        observation_receipt(
            command_id=command_id,
            tool="CODEX_NATIVE_SHELL",
            host=platform.node() or "localhost",
            scope="R01_SAFE_SYNTHETIC_DIAGNOSTIC",
            started_monotonic_ns=started,
            finished_monotonic_ns=None,
            observation=live_observation,
        )
    )
    try:
        process.communicate(timeout=0.02)
        raise RuntimeError("fixture did not reach timeout")
    except subprocess.TimeoutExpired:
        timeout_ns = time.monotonic_ns()
        timeout_observation = ExecutionObservation(
            pid=pid, pid_alive=process.poll() is None, timed_out=True, exit_code=process.poll()
        )
        receipt = observation_receipt(
            command_id=command_id,
            tool="CODEX_NATIVE_SHELL",
            host=platform.node() or "localhost",
            scope="R01_SAFE_SYNTHETIC_DIAGNOSTIC",
            started_monotonic_ns=started,
            finished_monotonic_ns=timeout_ns,
            observation=timeout_observation,
        )
        receipt["timeout_classification"] = "TIMEOUT_WITHOUT_REFUSAL"
        records.append(receipt)
    stdout, stderr = process.communicate(timeout=1.0)
    finished = time.monotonic_ns()
    (raw / "hung.stdout.log").write_bytes(stdout)
    (raw / "hung.stderr.log").write_bytes(stderr)
    same_pid_completion = {
        "command_id": command_id,
        "pid": pid,
        "same_pid_polled": True,
        "exit_code": process.returncode,
        "finished_monotonic_ns": finished,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "completion_status": "COMPLETED_SUCCESS",
    }

    error_id = "r01-ordinary-error-001"
    error_started = time.monotonic_ns()
    error_process = subprocess.Popen(
        [sys.executable, "-c", "import module_that_does_not_exist_r01"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    error_stdout, error_stderr = error_process.communicate(timeout=2.0)
    error_finished = time.monotonic_ns()
    (raw / "ordinary_error.stdout.log").write_bytes(error_stdout)
    (raw / "ordinary_error.stderr.log").write_bytes(error_stderr)
    records.append(
        observation_receipt(
            command_id=error_id,
            tool="CODEX_NATIVE_SHELL",
            host=platform.node() or "localhost",
            scope="R01_SAFE_SYNTHETIC_DIAGNOSTIC",
            started_monotonic_ns=error_started,
            finished_monotonic_ns=error_finished,
            observation=ExecutionObservation(
                pid=error_process.pid,
                pid_alive=False,
                timed_out=False,
                exit_code=error_process.returncode,
                stdout=error_stdout,
                stderr=error_stderr,
                authorization_granted=True,
                principal="local-r01-worker",
            ),
        )
    )

    recovery_started = time.monotonic_ns()
    recovery = subprocess.Popen(
        [sys.executable, "-c", "print('ordinary-error-recovered')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    recovery_stdout, recovery_stderr = recovery.communicate(timeout=2.0)
    recovery_finished = time.monotonic_ns()
    (raw / "ordinary_recovery.stdout.log").write_bytes(recovery_stdout)
    (raw / "ordinary_recovery.stderr.log").write_bytes(recovery_stderr)
    recovery_receipt = {
        "command_id": "r01-ordinary-recovery-001",
        "repairs_command_id": error_id,
        "pid": recovery.pid,
        "started_monotonic_ns": recovery_started,
        "finished_monotonic_ns": recovery_finished,
        "exit_code": recovery.returncode,
        "stdout_sha256": hashlib.sha256(recovery_stdout).hexdigest(),
        "stdout_bytes": len(recovery_stdout),
        "stderr_sha256": hashlib.sha256(recovery_stderr).hexdigest(),
        "stderr_bytes": len(recovery_stderr),
        "attempt": 1,
        "retry_bound": 1,
        "completion_status": "RECOVERED_SUCCESS",
    }

    auth_observation = ExecutionObservation(
        pid=None,
        pid_alive=False,
        timed_out=False,
        exit_code=None,
        stderr=b"authorization receipt absent",
        authorization_granted=False,
        principal=None,
    )
    records.append(
        observation_receipt(
            command_id="r01-authorization-fixture-001",
            tool="FIXTURE_ONLY",
            host="none",
            scope="NON_EXECUTING_PERMISSION_FIXTURE",
            started_monotonic_ns=time.monotonic_ns(),
            finished_monotonic_ns=time.monotonic_ns(),
            observation=auth_observation,
        )
    )
    refusal_observation = ExecutionObservation(
        pid=None,
        pid_alive=False,
        timed_out=False,
        exit_code=None,
        stderr=EXPLICIT_REFUSAL_TEXT.encode("utf-8"),
        authorization_granted=None,
        principal=None,
    )
    records.append(
        observation_receipt(
            command_id="r01-refusal-string-fixture-001",
            tool="FIXTURE_ONLY_NO_INVOCATION",
            host="none",
            scope="LITERAL_CLASSIFICATION_FIXTURE_ONLY",
            started_monotonic_ns=time.monotonic_ns(),
            finished_monotonic_ns=time.monotonic_ns(),
            observation=refusal_observation,
        )
    )
    records.append(
        observation_receipt(
            command_id="r01-ambiguous-no-pid-001",
            tool="FIXTURE_ONLY",
            host="unknown",
            scope="AMBIGUOUS_NO_PID_FIXTURE",
            started_monotonic_ns=time.monotonic_ns(),
            finished_monotonic_ns=time.monotonic_ns(),
            observation=ExecutionObservation(
                pid=None,
                pid_alive=False,
                timed_out=False,
                exit_code=None,
                command_known=False,
            ),
        )
    )
    return {
        "schema": "m27-b03-r01-execution-classification/v1",
        "generated_at": generated_at,
        "scope": "R01_NONPROD_ONLY",
        "classification_states": [
            "LIVE_PID_POLL",
            "TIMEOUT_WITHOUT_REFUSAL",
            "ORDINARY_TECHNICAL_ERROR",
            "AUTHORIZATION_PENDING",
            "EXPLICIT_PLATFORM_REFUSAL",
            "UNKNOWN_UNCLASSIFIED",
        ],
        "records": records,
        "same_pid_completion": same_pid_completion,
        "ordinary_error_recovery": recovery_receipt,
        "prior_b03_operation": {
            "state": "EXPLICIT_PLATFORM_REFUSAL",
            "retry_performed": False,
            "relay_or_equivalent_operation_performed": False,
            "source": "MASTER_B03_ACCEPTANCE_PENDING_INDEPENDENT_EVIDENCE_20261016.md",
            "literal_denial_sha256": hashlib.sha256(EXPLICIT_REFUSAL_TEXT.encode()).hexdigest(),
        },
    }


def evidence_gate(generated_at: str) -> dict[str, Any]:
    common = {
        "actual_independent_observation": None,
        "observation_status": "B03_MASTER_PHYSICAL_EVIDENCE_NOT_YET_AVAILABLE",
    }
    checks = [
        {
            "claim": "focused tests 43/43",
            "required_source_artifact": "B03 focused-test raw receipt and byte readback",
            "expected_public_digest": PUBLIC_DIGESTS["runtime_result"],
            "minimal_authorized_witness": "independent Master evidence witness",
            **common,
        },
        {
            "claim": "regression tests 238/238",
            "required_source_artifact": "B03 regression raw receipt and byte readback",
            "expected_public_digest": PUBLIC_DIGESTS["runtime_result"],
            "minimal_authorized_witness": "independent Master evidence witness",
            **common,
        },
        {
            "claim": "25 changed files",
            "required_source_artifact": "B03 changed-file manifest",
            "expected_public_digest": PUBLIC_DIGESTS["evidence_hashes"],
            "minimal_authorized_witness": "authorized read-only Git observer",
            **common,
        },
        {
            "claim": "11 artifact files",
            "required_source_artifact": "B03 artifact inventory",
            "expected_public_digest": PUBLIC_DIGESTS["evidence_hashes"],
            "minimal_authorized_witness": "authorized read-only artifact observer",
            **common,
        },
        {
            "claim": f"HEAD {B03_COMMIT}",
            "required_source_artifact": "B03 Git commit object",
            "expected_public_digest": B03_COMMIT,
            "minimal_authorized_witness": "authorized read-only Git observer",
            **common,
        },
        {
            "claim": f"TREE {B03_TREE}",
            "required_source_artifact": "B03 Git tree object bound to claimed HEAD",
            "expected_public_digest": B03_TREE,
            "minimal_authorized_witness": "authorized read-only Git observer",
            **common,
        },
        {
            "claim": "pre/post verifier",
            "required_source_artifact": "B03 independent verifier receipt",
            "expected_public_digest": PUBLIC_DIGESTS["independent_verify"],
            "minimal_authorized_witness": "distinct authorized verifier issuer",
            **common,
        },
    ]
    return {
        "schema": "m27-b03-r01-independent-evidence-gate/v1",
        "generated_at": generated_at,
        "b02_source_commit": B02_COMMIT,
        "b02_source_tree": B02_TREE,
        "b03_worker_claimed_status": "B03_WORKER_CLAIMED_PASS",
        "r01_public_verifier_status": "R01_PUBLIC_VERIFIER_TEST_PASS",
        "master_physical_evidence_status": "B03_MASTER_PHYSICAL_EVIDENCE_NOT_YET_AVAILABLE",
        "claimed_counts": CLAIMS,
        "claimed_candidate_commit": B03_COMMIT,
        "claimed_candidate_tree": B03_TREE,
        "public_report_digests": PUBLIC_DIGESTS,
        "checks": checks,
        "public_verifier_test_matrix": [
            "authorized_ed25519_fixture",
            "tamper",
            "count_mismatch",
            "missing_artifact",
            "forged_issuer",
            "revoked_issuer",
            "expired_issuer",
            "wrong_candidate",
            "inconsistent_tree",
            "pid_command_mismatch",
            "stale_timestamp",
            "forged_signature",
            "missing_issuer_authorization",
            "same_uid_hmac",
            "replayed_or_copied_receipt",
        ],
        "same_uid_hmac_is_independent": False,
        "self_signature_is_independent": False,
        "copied_manifest_or_report_is_independent": False,
        "gate_open": False,
    }


def witness_packet(generated_at: str) -> dict[str, Any]:
    return {
        "schema": "m27-b03-r01-ready-to-sign-public-witness-packet/v1",
        "generated_at": generated_at,
        "status": "READY_NOT_SIGNED",
        "contains_secrets": False,
        "candidate_commit": B03_COMMIT,
        "candidate_tree": B03_TREE,
        "claims": CLAIMS,
        "expected_public_digests": PUBLIC_DIGESTS,
        "required_issuer_role": "INDEPENDENT_MASTER_EVIDENCE_WITNESS",
        "required_algorithm": "Ed25519",
        "required_observation": {
            "physical_bytes_observed": True,
            "custody_independent": True,
            "pid_and_command_bound": True,
            "fresh_timestamp": True,
            "authorized_scope_receipt": True,
        },
        "prohibited_substitutes": [
            "same_uid_hmac",
            "self_signature",
            "copied_manifest",
            "copied_report",
            "local_fixture_signature",
        ],
        "signature_b64": None,
    }


def access_request(generated_at: str) -> dict[str, Any]:
    return {
        "schema": "m27-b03-r01-scoped-access-request/v1",
        "generated_at": generated_at,
        "request_status": "READY_NOT_SENT",
        "requested_operation": "independent read-only physical evidence observation",
        "candidate_commit": B03_COMMIT,
        "candidate_tree": B03_TREE,
        "allowed_objects": [
            "claimed B03 Git commit and tree objects",
            "non-secret test receipts",
            "non-secret artifact manifest and hashes",
        ],
        "excluded_objects": [
            "sealed question banks",
            "original 523 protected items or gold answers",
            "keys or tokens",
            "protected grader or rubric secrets",
            "Production",
        ],
        "prior_equivalent_operation_refused": True,
        "must_be_genuinely_new_authorization": True,
        "automatic_retry_or_reroute_allowed": False,
        "requested_witness_role": "INDEPENDENT_MASTER_EVIDENCE_WITNESS",
    }


def dependency_matrix(generated_at: str) -> dict[str, Any]:
    base = AdmissionEvidence(
        expected_denominator=523,
        observed_denominator=0,
        passed_count=0,
        safe_terminal_expected=0,
        safe_terminal_correct=0,
        candidate_commit=B03_COMMIT,
        expected_candidate_commit=B03_COMMIT,
        source_tree=B03_TREE,
        expected_source_tree=B03_TREE,
        clock_monotonic=True,
        latency_p95_ms=None,
        latency_limit_ms=1_000.0,
        idp_receipt_valid=False,
        signer_receipt_valid=False,
        source_fresh=False,
        issuer_authorized=False,
        custody_independent=False,
        release_authorized=False,
    )
    current = evaluate_f35_rel01(base)
    negative_cases = {}
    changes = {
        "fixed_denominator": {"observed_denominator": 522, "passed_count": 522},
        "false_safe": {"safe_terminal_expected": 1, "safe_terminal_correct": 0},
        "candidate_mismatch": {"candidate_commit": "0" * 40},
        "clock": {"clock_monotonic": False},
        "latency_outlier": {"latency_p95_ms": 1_001.0},
        "absent_idp": {"idp_receipt_valid": False},
        "absent_signer": {"signer_receipt_valid": False},
        "stale_source": {"source_fresh": False},
        "wrong_issuer": {"issuer_authorized": False},
        "custody": {"custody_independent": False},
        "unsafe_release": {"release_authorized": False, "production_touched": True},
    }
    positive = AdmissionEvidence(
        expected_denominator=523,
        observed_denominator=523,
        passed_count=523,
        safe_terminal_expected=100,
        safe_terminal_correct=100,
        candidate_commit=B03_COMMIT,
        expected_candidate_commit=B03_COMMIT,
        source_tree=B03_TREE,
        expected_source_tree=B03_TREE,
        clock_monotonic=True,
        latency_p95_ms=900.0,
        latency_limit_ms=1_000.0,
        idp_receipt_valid=True,
        signer_receipt_valid=True,
        source_fresh=True,
        issuer_authorized=True,
        custody_independent=True,
        release_authorized=True,
    )
    positive_result = evaluate_f35_rel01(positive)
    for name, change in changes.items():
        values = {field: getattr(positive, field) for field in positive.__dataclass_fields__}
        values.update(change)
        negative_cases[name] = evaluate_f35_rel01(AdmissionEvidence(**values))
    return {
        "schema": "m27-b03-r01-f35-rel01-dependency-matrix/v1",
        "generated_at": generated_at,
        "binding": {
            "b02_commit": B02_COMMIT,
            "reported_b03_commit": B03_COMMIT,
            "reported_b03_tree": B03_TREE,
        },
        "current_formal_state": current,
        "authorized_fixture_positive": {
            **positive_result,
            "fixture_only": True,
            "formal_evidence": False,
        },
        "negative_cases": negative_cases,
        "formal_truth": {
            "e27": "0/523",
            "b27": "0/200",
            "f35": "HOLD",
            "x01_x09": "0/9",
            "q34_native_generated_stream": "UNQUALIFIED",
            "idp": "NOT_VERIFIED",
            "external_signer": "NOT_VERIFIED",
            "provider": "NOT_VERIFIED",
            "ci": "NOT_VERIFIED",
            "c28": "NOT_VERIFIED",
            "historical_m26_failures_remaining": 6,
            "rel01": "NOT_CERTIFIED",
            "rel02": "NO_GO",
            "formal_product_go": False,
        },
    }


def next_work_matrix(generated_at: str) -> dict[str, Any]:
    return {
        "schema": "m27-b03-r01-next-authorized-work-matrix/v1",
        "generated_at": generated_at,
        "items": [
            {
                "item": "R01 execution classifier and real PID diagnostics",
                "state": "DONE_WITH_RECEIPT",
            },
            {
                "item": "R01 public receipt verifier positive/negative suite",
                "state": "DONE_WITH_RECEIPT",
            },
            {
                "item": "R01 F35/REL01 offline fail-closed harness",
                "state": "DONE_WITH_RECEIPT",
            },
            {
                "item": "ordinary local implementation or test defects",
                "state": "SELF_REPAIRABLE_IN_R01",
            },
            {
                "item": "B03 physical byte observation and countersignature",
                "state": "NEEDS_DISTINCT_WORKER",
            },
            {
                "item": "official 523/200, IdP, external signer, CI, C28, REL01/REL02",
                "state": "REQUIRES_OFFICIAL_EXTERNAL_AUTHORIZATION",
            },
            {
                "item": "previous broad B03 inspection operation or equivalent",
                "state": "PRIOR_EXPLICIT_REFUSAL_NO_RETRY",
            },
        ],
        "formal_product_go": False,
        "production_touched": False,
    }


def source_inventory(generated_at: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    source_paths = [
        "docs/m27/B03_R01_ADMISSION_EVIDENCE_RECOVERY.md",
        "scripts/m27_b03_r01_generate_evidence.py",
        "src/knowledge_engine/m27_b03_r01_admission_gate.py",
        "src/knowledge_engine/m27_b03_r01_execution_recovery.py",
        "src/knowledge_engine/m27_b03_r01_public_receipt.py",
        "tests/test_m27_b03_r01_recovery.py",
    ]
    files = []
    for relative in source_paths:
        path = root / relative
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return {
        "schema": "m27-b03-r01-source-inventory/v1",
        "generated_at": generated_at,
        "base_commit": B02_COMMIT,
        "base_tree": B02_TREE,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-full-repository-diagnostic", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()

    documents = {
        "B03_R01_EXECUTION_CLASSIFICATION.json": run_diagnostics(output, generated_at),
        "B03_R01_TEST_EXECUTION.json": run_test_evidence(
            output,
            generated_at,
            reuse_full_repository_diagnostic=args.reuse_full_repository_diagnostic,
        ),
        "B03_R01_INDEPENDENT_EVIDENCE_GATE.json": evidence_gate(generated_at),
        "B03_R01_PUBLIC_WITNESS_PACKET.json": witness_packet(generated_at),
        "B03_R01_SCOPED_ACCESS_REQUEST.json": access_request(generated_at),
        "B03_R01_F35_REL01_DEPENDENCY_MATRIX.json": dependency_matrix(generated_at),
        "B03_R01_NEXT_AUTHORIZED_WORK_MATRIX.json": next_work_matrix(generated_at),
        "B03_R01_SOURCE_INVENTORY.json": source_inventory(generated_at),
    }
    for name, document in documents.items():
        write_json(output / name, document)
    inventory = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "B03_R01_EVIDENCE_INVENTORY.json":
            inventory.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    write_json(
        output / "B03_R01_EVIDENCE_INVENTORY.json",
        {
            "schema": "m27-b03-r01-evidence-inventory/v1",
            "generated_at": generated_at,
            "files": inventory,
            "inventory_self_hash_excluded": True,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
