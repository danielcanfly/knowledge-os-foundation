#!/usr/bin/env python3
"""Run A04 21+8 from a clean checkout with an external staged runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
EVIDENCE = ROOT / "evidence"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO), *args], text=True
    ).strip()


def outside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO.resolve())
        return False
    except ValueError:
        return True


def warm_model_runtime(runtime: Path, env: dict[str, str], python: str) -> dict:
    """Prime llama.cpp's Metal cache inside the disposable clean environment.

    A first launch with a new HOME/TMPDIR compiles Metal kernels and can take
    substantially longer than an inference request.  Make that cold-start work
    explicit, bounded, and auditable before exercising the 20-second request
    deadline in the acceptance suite.
    """
    del python  # Keep the call signature aligned with the selected interpreter.
    stdout_path = EVIDENCE / "runtime_warmup.stdout.log"
    stderr_path = EVIDENCE / "runtime_warmup.stderr.log"
    command = [
        str(runtime / "llama-b11425" / "llama-cli"),
        "-m", str(runtime / "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
        "-p", "<|im_start|>user\nReply with the word ready.\n<|im_end|>\n<|im_start|>assistant\n",
        "-n", "1", "-c", "1024", "--temp", "0", "-s", "1442",
        "--no-display-prompt", "--simple-io", "--no-perf", "--single-turn",
    ]
    started = time.monotonic_ns()
    process = subprocess.Popen(
        command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    result = {
        "pid": process.pid,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "duration_ms": round((time.monotonic_ns() - started) / 1e6, 3),
        "max_new_tokens": 1,
        "timeout_seconds": 240,
        "stdout": stdout_path.name,
        "stdout_sha256": sha256(stdout_path),
        "stderr": stderr_path.name,
        "stderr_sha256": sha256(stderr_path),
        "cache_home_outside_checkout": outside_repo(Path(env["HOME"])),
        "cache_tmp_outside_checkout": outside_repo(Path(env["TMPDIR"])),
    }
    if timed_out or process.returncode != 0 or not stdout.strip():
        raise RuntimeError(f"MODEL_RUNTIME_WARMUP_FAILED:{result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.expanduser().resolve()
    scratch = args.scratch.expanduser().resolve()
    if not outside_repo(runtime) or not outside_repo(scratch):
        raise ValueError("RUNTIME_AND_SCRATCH_MUST_BE_OUTSIDE_CHECKOUT")
    stage_receipt = runtime / "STAGE_RECEIPT.json"
    if not stage_receipt.is_file():
        raise ValueError("STAGE_RECEIPT_REQUIRED")
    if EVIDENCE.exists() and any(EVIDENCE.iterdir()):
        raise ValueError("CLEAN_EVIDENCE_DIRECTORY_REQUIRED")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (scratch / "home").mkdir(parents=True, exist_ok=True)
    (scratch / "tmp").mkdir(parents=True, exist_ok=True)

    env = {
        "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"),
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "A04_TEST_MODE": "1",
        "A04_LOCAL_MODEL": "1",
        "A04_MODEL_RUNTIME": str(runtime),
    }
    python = os.environ.get("A04_PYTHON", "/opt/homebrew/bin/python3.11")
    tracked_before = git("status", "--porcelain", "--untracked-files=no")
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")

    bootstrap = subprocess.run(
        [python, "-B", "bootstrap.py"], cwd=ROOT, env=env,
        text=True, capture_output=True, timeout=30,
    )
    (EVIDENCE / "bootstrap.stdout.log").write_text(bootstrap.stdout, encoding="utf-8")
    (EVIDENCE / "bootstrap.stderr.log").write_text(bootstrap.stderr, encoding="utf-8")
    if bootstrap.returncode:
        raise RuntimeError("BOOTSTRAP_FAILED")

    warmup = warm_model_runtime(runtime, env, python)

    server_stdout = (EVIDENCE / "server.stdout.log").open("w", encoding="utf-8")
    server_stderr = (EVIDENCE / "server.stderr.log").open("w", encoding="utf-8")
    port_file = EVIDENCE / "port.txt"
    server = subprocess.Popen(
        [python, "-B", "-u", "app.py", "--port-file", str(port_file)],
        cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
        stdout=server_stdout, stderr=server_stderr, start_new_session=True,
    )
    clients = []
    failure = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError("SERVER_EXITED_BEFORE_READY")
            if port_file.is_file() and port_file.read_text().strip().isdigit():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("SERVER_READY_TIMEOUT")

        for label, script in (
            ("client_21", "tests/acceptance.py"),
            ("client_real_model_8", "tests/real_model_acceptance.py"),
        ):
            stdout_path = EVIDENCE / f"{label}.stdout.log"
            stderr_path = EVIDENCE / f"{label}.stderr.log"
            with stdout_path.open("w", encoding="utf-8") as out, \
                    stderr_path.open("w", encoding="utf-8") as err:
                client = subprocess.Popen(
                    [python, "-B", script], cwd=ROOT, env=env,
                    stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    start_new_session=True,
                )
                client_pid = client.pid
                client_exit = client.wait(timeout=420)
            clients.append({
                "name": label,
                "script": script,
                "pid": client_pid,
                "exit_code": client_exit,
                "stdout": stdout_path.name,
                "stdout_sha256": sha256(stdout_path),
                "stderr": stderr_path.name,
                "stderr_sha256": sha256(stderr_path),
            })
            if client_exit:
                raise RuntimeError(f"CLIENT_FAILED:{label}")
    except Exception as exc:
        failure = f"{type(exc).__name__}:{exc}"
    finally:
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
        server_stdout.close()
        server_stderr.close()

    stub = EVIDENCE / "acceptance_results.json"
    real = EVIDENCE / "return_model_test_results.json"
    stub_counts = json.loads(stub.read_text())["counts"] if stub.is_file() else None
    real_counts = json.loads(real.read_text())["counts"] if real.is_file() else None
    tracked_after = git("status", "--porcelain", "--untracked-files=no")
    passed = (
        failure is None
        and stub_counts == {"total": 21, "pass": 21, "fail": 0}
        and real_counts == {"pass": 8, "fail": 0, "total": 8}
        and tracked_before == ""
        and tracked_after == ""
    )
    receipt = {
        "schema": "m27.a04.clean-checkout-replay/v2",
        "status": "PASS" if passed else "FAIL",
        "scope": "NONPROD_LOCAL_ONLY",
        "checkout": {"head": head, "tree": tree, "tracked_clean_before": tracked_before == "",
                     "tracked_clean_after": tracked_after == ""},
        "runtime_stage_receipt_sha256": sha256(stage_receipt),
        "runtime_warmup": warmup,
        "server": {
            "pid": server.pid,
            "exit_code_after_cleanup": server.returncode,
            "stdout_sha256": sha256(EVIDENCE / "server.stdout.log"),
            "stderr_sha256": sha256(EVIDENCE / "server.stderr.log"),
            "cleanup_complete": server.poll() is not None,
        },
        "clients": clients,
        "stub_counts": stub_counts,
        "real_model_counts": real_counts,
        "failure": failure,
        "production_authority": False,
        "native_q34": False,
        "sealed_evaluation_access": False,
    }
    receipt_path = EVIDENCE / "REPRO_RUN_RECEIPT_V2.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": receipt["status"],
        "receipt": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "stub_counts": stub_counts,
        "real_model_counts": real_counts,
        "server_cleanup_complete": receipt["server"]["cleanup_complete"],
    }, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
