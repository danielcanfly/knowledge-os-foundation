#!/usr/bin/env python3
"""P28R isolated actual Docker default-lifespan fail-closed acceptance.

No host ports, credentials, network, provider, preexisting container control,
Docker daemon start, CI, bundle injection or external resource access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def call(*args: str, timeout: int = 12) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def snapshot() -> list[dict]:
    result = call("docker", "ps", "-a", "--format", "{{json .}}")
    if result.returncode:
        raise RuntimeError("docker daemon must ALREADY be running")
    return [json.loads(row) for row in result.stdout.splitlines() if row]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    a = parser.parse_args()
    if not a.image.startswith("p28r-t27-nonprod:"):
        raise SystemExit("REJECT unscoped nonproduction image")
    image = call("docker", "image", "inspect", a.image, "--format", "{{.Id}}")
    if image.returncode:
        raise SystemExit("REJECT image not local; no pull")
    start_snapshot = snapshot()
    name = "p28r-default-negative-" + uuid.uuid4().hex[:12]
    command = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "768m",
        "--tmpfs",
        "/var/lib/knowledge-engine/store:rw,noexec,nosuid,uid=10001,gid=10001",
        "--tmpfs",
        "/var/lib/knowledge-engine/cache:rw,noexec,nosuid,uid=10001,gid=10001",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,uid=10001,gid=10001",
        a.image,
    ]
    record = {
        "schema": "P28R_ISOLATED_REAL_DEFAULT_LIFESPAN_NEGATIVE_V1",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "image_ref": a.image,
        "image_id": image.stdout.strip(),
        "baseline_container_ids": sorted(x["ID"] for x in start_snapshot),
        "network_mode": "none",
        "host_ports": [],
        "credentials": [],
        "production_access": False,
        "original_entrypoint_unmodified": True,
        "lifespan_override": False,
        "container_name": name,
        "docker_run_argv": command,
    }
    container_id = ""
    try:
        created = call(*command, timeout=30)
        record["docker_run_exit"] = created.returncode
        record["docker_run_stderr"] = created.stderr[-2000:]
        if created.returncode:
            record["verdict"] = "FAILED_TO_LAUNCH"
            return 7
        container_id = created.stdout.strip()
        record["container_id"] = container_id
        state = {}
        for _ in range(30):
            inspected = call("docker", "inspect", container_id, "--format", "{{json .State}}")
            if inspected.returncode:
                break
            state = json.loads(inspected.stdout)
            if not state.get("Running"):
                break
            time.sleep(1)
        record["state"] = state
        logs = call("docker", "logs", container_id)
        record["logs_sha256"] = hashlib.sha256((logs.stdout + logs.stderr).encode()).hexdigest()
        record["log_tail"] = (logs.stdout + logs.stderr)[-7500:]
        exit_code = state.get("ExitCode")
        record["actual_exit"] = exit_code
        record["missing_manifest_confirmed"] = (
            exit_code == 3
            and "FileNotFoundError: releases/m25blog-" in record["log_tail"]
            and "Application startup failed" in record["log_tail"]
        )
        record["verdict"] = (
            "PASS_EXPECTED_FAIL_CLOSED"
            if record["missing_manifest_confirmed"]
            else "FAIL_UNEXPECTED_RUNTIME"
        )
        return 0 if record["missing_manifest_confirmed"] else 8
    finally:
        if container_id:
            removal = call("docker", "rm", "-f", container_id, timeout=15)
            record["own_container_cleanup_exit"] = removal.returncode
        finish_snapshot = snapshot()
        record["final_container_ids"] = sorted(x["ID"] for x in finish_snapshot)
        record["other_containers_unchanged"] = (
            record["baseline_container_ids"] == record["final_container_ids"]
        )
        a.evidence.parent.mkdir(parents=True, exist_ok=True)
        a.evidence.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
