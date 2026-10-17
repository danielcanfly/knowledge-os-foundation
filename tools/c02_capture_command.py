#!/usr/bin/env python3
"""Run one command and preserve raw stdout/stderr plus an execution receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        raise SystemExit("command required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_wall_ns = time.time_ns()
    started_mono_ns = time.monotonic_ns()
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, start_new_session=True
    )
    stdout, stderr = proc.communicate()
    ended_wall_ns = time.time_ns()
    receipt = {
        "schema": "m27.c02.command-receipt/v1",
        "name": args.name,
        "command": command,
        "pid": proc.pid,
        "exit_code": proc.returncode,
        "started_wall_epoch_ns": started_wall_ns,
        "ended_wall_epoch_ns": ended_wall_ns,
        "duration_ms": round((time.monotonic_ns() - started_mono_ns) / 1_000_000, 3),
        "stdout_bytes": len(stdout),
        "stdout_sha256": sha(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": sha(stderr),
        "cwd": os.getcwd(),
    }
    (args.output_dir / f"{args.name}.stdout.log").write_bytes(stdout)
    (args.output_dir / f"{args.name}.stderr.log").write_bytes(stderr)
    (args.output_dir / f"{args.name}.receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "name": args.name,
                "exit_code": proc.returncode,
                "receipt": str(args.output_dir / f"{args.name}.receipt.json"),
            },
            sort_keys=True,
        )
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
