#!/usr/bin/env python3
"""No-egress, no-secrets isolated local OCI image -> OS process smoke and rollback."""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SOURCE = "8604752934fb43a3441055d33c01940028cc5938"
TREE = "123578f9e1059d1b554fc3fdc011bdc171033afd"
PROBE = """
import json, urllib.request
out={}
for path in ("/v1/health","/openapi.json"):
    with urllib.request.urlopen("http://127.0.0.1:8080"+path, timeout=3) as r:
        body=json.loads(r.read())
        out[path]={"http":r.status}
        if path == "/v1/health":
            out[path]["status"]=body.get("status")
            out[path]["release_id"]=body.get("release_id")
        else:
            out[path]["routes"]={name: name in body.get("paths",{})
                             for name in ("/v1/health","/api/m26/query/stream")}
print(json.dumps(out))
"""


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def inspect_image(ref):
    v = json.loads(docker("image", "inspect", ref).stdout)[0]
    labels = v["Config"]["Labels"]
    if (
        labels.get("org.opencontainers.image.revision") != SOURCE
        or labels.get("org.opencontainers.image.source_tree") != TREE
    ):
        raise RuntimeError("reject incorrect source identity for image: " + ref)
    if labels.get("io.knowledge_engine.signed") != "false":
        raise RuntimeError("reject image claiming signature")
    cmd = v["Config"]["Cmd"]
    if cmd != [
        "uvicorn",
        "knowledge_engine.m26_production_api:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ]:
        raise RuntimeError("reject incorrect original executable CMD: " + str(cmd))
    return {
        "ref": ref,
        "image_id": v["Id"],
        "cmd": cmd,
        "labels": labels,
        "architecture": v["Architecture"],
        "os": v["Os"],
    }


def run_smoke(image, phase, evidence):
    name = "p28-local-rehearsal-" + phase.lower()
    container = None
    events = {
        "phase": phase,
        "image": image,
        "started_at": datetime.now(UTC).isoformat(),
        "negative_external_network": "--network none",
        "host_ports_published": False,
        "secrets_injected": False,
        "lifespan_off_diagnostic_only": True,
        "default_preload_executed": False,
    }
    try:
        started = docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev",
            "--tmpfs",
            "/var/lib/knowledge-engine:rw,nosuid,nodev,uid=10001,gid=10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-e",
            "APP_ENV=test",
            "-e",
            "AUTH_MODE=disabled",
            image,
            "uvicorn",
            "knowledge_engine.m26_production_api:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8080",
            "--lifespan",
            "off",
        )
        container = started.stdout.strip()
        events["container_id"] = container
        ready = False
        for _n in range(60):
            state = json.loads(docker("inspect", "-f", "{{json .State}}", container).stdout)
            if not state["Running"]:
                events["failure_state"] = state
                raise RuntimeError("container stopped before localhost probe")
            probe = docker("exec", container, "python", "-B", "-c", PROBE, check=False)
            if probe.returncode == 0:
                out = json.loads(probe.stdout)
                if out["/v1/health"]["http"] != 200 or out["/v1/health"]["status"] not in (
                    "healthy",
                    "starting",
                ):
                    raise RuntimeError("health response unexpected " + str(out))
                if not all(out["/openapi.json"]["routes"].values()):
                    raise RuntimeError("required routes not packaged " + str(out))
                events["probe"] = out
                events["probe_exec_exit"] = probe.returncode
                events["os_container_pid"] = state["Pid"]
                events["running"] = state["Running"]
                events["health_ready"] = out["/v1/health"]["status"] == "healthy"
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("no localhost HTTP probe became ready in bounded loop")
        events["probe_pass"] = True
    finally:
        if container:
            events["stdout_stderr"] = docker("logs", container, check=False).stderr[-6000:]
            stopped = docker("stop", "-t", "5", container, check=False)
            events["stop_exit"] = stopped.returncode
            events["stopped_state"] = json.loads(
                docker("inspect", "-f", "{{json .State}}", container).stdout
            )
            events["remove_exit"] = docker("rm", container, check=False).returncode
        events["finished_at"] = datetime.now(UTC).isoformat()
        (evidence / ("P28_" + phase + "_CONTAINER_RECEIPT.json")).write_text(
            json.dumps(events, indent=2, sort_keys=True) + "\n"
        )
    if (
        not events.get("probe_pass")
        or events.get("stop_exit") != 0
        or events.get("remove_exit") != 0
    ):
        raise RuntimeError("smoke or OS shutdown did not pass for " + phase)
    return events


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image-before", required=True)
    p.add_argument("--image-after", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    a = p.parse_args()
    a.evidence.mkdir(parents=True, exist_ok=True)
    before = inspect_image(a.image_before)
    after = inspect_image(a.image_after)
    if before["image_id"] == after["image_id"]:
        raise RuntimeError("rollback rehearsal needs two PHYSICALLY DISTINCT local images")
    receipts = [
        run_smoke(a.image_before, "BEFORE", a.evidence),
        run_smoke(a.image_after, "AFTER", a.evidence),
        run_smoke(a.image_before, "ROLLBACK", a.evidence),
    ]
    result = {
        "schema": "P28_LOCAL_NONPROD_OCI_PROCESS_ROLLBACK_V1",
        "source_head": SOURCE,
        "source_tree": TREE,
        "before_image": before,
        "after_image": after,
        "processes": receipts,
        "rollback_pass": True,
        "external_app_qualified": False,
        "production_modified": False,
        "release_authorized": False,
    }
    (a.evidence / "P28_LOCAL_ROLLBACK_SMOKE.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "rollback_pass": result["rollback_pass"],
                "image_ids": [before["image_id"], after["image_id"]],
                "phases": [
                    {
                        "phase": x["phase"],
                        "pid": x.get("os_container_pid"),
                        "health": x["probe"]["/v1/health"]["status"],
                        "exit": x["stopped_state"]["ExitCode"],
                    }
                    for x in receipts
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print("P28 isolated smoke FAIL: " + str(exc), file=sys.stderr)
        sys.exit(29)
