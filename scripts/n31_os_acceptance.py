"""Real native HTTP/ASGI/R29 SQLite OS acceptance, bounded local fixtures only."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port, path="/task", *, method="POST", data=None, token=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=12)
    headers = {"Host": f"127.0.0.1:{port}"}
    if token:
        headers["X-N31-Local-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    t0 = time.monotonic_ns()
    conn.request(method, path, body=json.dumps(data).encode() if data is not None else None,
                 headers=headers)
    res = conn.getresponse()
    body = res.read()
    millis = (time.monotonic_ns() - t0) / 1e6
    result = {
        "status": res.status, "headers": dict(res.getheaders()),
        "body": body.decode("utf-8"), "elapsed_ms": round(millis, 3),
    }
    conn.close()
    return result


def ready(port, path, token=None):
    for _ in range(100):
        try:
            r = request(port, path, method="GET", token=token)
            if r["status"] in (200, 503):
                return r
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.05)
    raise RuntimeError("OS_CHILD_NOT_READY")


def task(kind, run, **extra):
    return {
        "workload": kind, "run": run, "tenant": "tenantA",
        "actor": "principalA", "source_revision": "rev1", "lease_epoch": 1,
        **extra,
    }


def main():
    base = Path(os.environ["N31_EVIDENCE"]).resolve()
    base.mkdir(parents=True, exist_ok=True)
    runroot = base / "OS_RUN"
    runroot.mkdir(mode=0o700, exist_ok=True)
    token = secrets.token_hex(20)
    ft = secrets.token_hex(20)
    port, effect = free_port(), free_port()
    env = os.environ.copy()
    env.update({
        "APP_ENV": "test", "N31_LOCAL_ONLY": "1",
        "N31_ROOT": str(runroot), "N31_TEST_TOKEN": token,
        "N31_FIXTURE_PORT": str(effect), "N31_FIXTURE_TOKEN": ft,
        "N31_CONNECT_LOG": str(base / "n31_socket_connects.jsonl"),
        "R29_SYNTHETIC_LOCAL_ONLY": "1",
    })
    (base / "n31_socket_connects.jsonl").touch()
    service_db = base / "r29_independent_effects.sqlite"
    commands = {
        "effect": [
            sys.executable, "-m",
            "knowledge_engine.m27_r29_local_action_v1_experimental",
            "--db", str(service_db), "--port", str(effect), "--token", ft,
        ],
        "asgi": [
            sys.executable, "scripts/n31_serve.py",
            "--host", "127.0.0.1", "--port", str(port),
        ],
    }
    children = {}
    logs = {}
    receipts = {}
    negatives = {}
    try:
        for name in ("effect", "asgi"):
            logs[name] = (base / f"n31_{name}_service.log").open("wb")
            children[name] = subprocess.Popen(
                commands[name], env=env, stdout=logs[name], stderr=subprocess.STDOUT,
            )
        ready(effect, "/fixture/ready", token=ft) if False else None
        # R29 uses a distinct local authorization header, so socket readiness
        # is checked by a read-only TCP connect, not by a fabricated R29 receipt.
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", effect), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("EFFECT_SERVICE_NOT_READY")
        health = ready(port, "/health")
        receipts["health"] = health
        if (health["status"] != 503
                or json.loads(health["body"])["status"] != "not_ready"):
            raise RuntimeError("HEALTH_MUST_FAIL_CLOSED")
        negatives["missing_auth"] = request(port, data=task("QA-I", "badToken"))
        negatives["cross_tenant"] = request(
            port, data=task("QA-I", "badTenant", tenant="tenantB"), token=token,
        )
        negatives["wrong_actor"] = request(
            port, data=task("QA-I", "badActor", actor="principalB"), token=token,
        )
        negatives["source_revision"] = request(
            port, data=task("QA-I", "badRevision", source_revision="rev2"), token=token,
        )
        negatives["source_epoch"] = request(
            port, data=task("QA-I", "badEpoch", lease_epoch=2), token=token,
        )
        negatives["unsafe_url"] = request(
            port, data={**task("ACT-LOCAL", "badURL"),
                        "callback_url": "https://outside.example.invalid/"},
            token=token,
        )
        negatives["unsafe_action_mode"] = request(
            port, data=task("ACT-LOCAL", "badMode", mode="remote"), token=token,
        )
        negatives["revoked_after_enqueue"] = request(
            port, data=task("QA-I", "qaRevoke", revoke_after_enqueue=True),
            token=token,
        )
        negatives["revoke_action_after_enqueue"] = request(
            port, data=task("ACT-LOCAL", "actRevoke", revoke_after_enqueue=True),
            token=token,
        )
        receipts["qa"] = request(port, data=task("QA-I", "qaNative"), token=token)
        receipts["research"] = request(port, data=task("RES-L", "resNative"), token=token)
        receipts["action"] = request(port, data=task("ACT-LOCAL", "actNative"), token=token)
        receipts["lost_ack"] = request(
            port, data=task("ACT-LOCAL", "actLost", mode="lost_ack"), token=token,
        )
        receipts["unknown"] = request(
            port, data=task("ACT-LOCAL", "actUnknown", mode="observer_unknown"),
            token=token,
        )
        negatives["unknown_no_replay"] = request(
            port, data=task("ACT-LOCAL", "actUnknown", mode="observer_unknown"),
            token=token,
        )
        qa_lines = [json.loads(line) for line in receipts["qa"]["body"].splitlines()]
        research = json.loads(receipts["research"]["body"])
        artifact = Path(research["artifact_path"])
        artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        obs = subprocess.run(
            [sys.executable, "scripts/n31_observer.py", "--db", str(service_db)],
            env=env, capture_output=True, text=True, check=True, timeout=15,
        )
        (base / "n31_separate_observer_raw.json").write_text(obs.stdout)
        oracle = json.loads(obs.stdout)
        connects = [
            json.loads(line) for line in
            (base / "n31_socket_connects.jsonl").read_text().splitlines() if line
        ]
        feature_off = env.copy()
        feature_off.pop("N31_LOCAL_ONLY")
        disabled = subprocess.run(
            [sys.executable, "-c",
             "import knowledge_engine.m27_n31_nonprod_app"],
            env=feature_off, capture_output=True, text=True, timeout=12,
        )
        nonloopback = subprocess.run(
            [sys.executable, "scripts/n31_serve.py", "--host", "0.0.0.0",
             "--port", str(free_port())],
            env=env, capture_output=True, text=True, timeout=12,
        )
        (base / "n31_feature_disabled.stderr").write_text(disabled.stderr)
        (base / "n31_nonloopback.stderr").write_text(nonloopback.stderr)
        steps = {
            "HEALTH_FAIL_CLOSED": receipts["health"]["status"] == 503,
            "HTTP_TASKCONTRACT_ACTUAL_PATH": (
                receipts["qa"]["status"] == 200
                and receipts["research"]["status"] == 200
                and receipts["action"]["status"] == 200
                and json.loads(receipts["action"]["body"])["status"].startswith(
                    "LOCAL_VERIFIED_APPLIED")
            ),
            "LOCAL_NATIVE_FIRST_CITED_TEXT": (
                receipts["qa"]["status"] == 200
                and len(qa_lines) >= 2 and qa_lines[0]["event"] == "cited_text"
                and bool(qa_lines[0]["text"].strip())
                and bool(qa_lines[0]["citations"])
                and qa_lines[-1]["event"] == "terminal"
                and qa_lines[-1]["first_text_preterminal"] is True
            ),
            "LOCAL_RESEARCH_PERSISTED": (
                artifact.is_file()
                and artifact_sha == research["artifact_sha256"]
                and research["checkpoint_count"] == 2
            ),
            "ACT_LOCAL_FIXTURE_ONLY": (
                oracle["posts_by_run"].get("actNative") == 1
                and oracle["effects_by_run"].get("actNative") == 1
                and oracle["posts_by_run"].get("actLost") == 1
                and oracle["effects_by_run"].get("actLost") == 1
                and oracle["posts_by_run"].get("actUnknown") == 1
                and oracle["effects_by_run"].get("actUnknown") == 1
                and json.loads(receipts["unknown"]["body"])["status"]
                == "UNKNOWN_EFFECT_NO_AUTORETRY"
                and oracle["posts_by_run"].get("actRevoke", 0) == 0
            ),
            "NEGATIVE_HTTP_DENIAL": all(
                v["status"] == 403 for v in negatives.values()
            ),
            "NO_NONLOOPBACK_CONNECTIONS": not any(
                v["kind"] == "nonloopback_denied" for v in connects
            ),
            "FEATURE_DISABLED_DENIED": disabled.returncode != 0,
            "NONLOOPBACK_LISTENER_DENIED": nonloopback.returncode != 0,
        }
        machine = {
            "task": "N31", "host_scope": "local_os_processes_only",
            "ports": {"asgi_loopback": port, "effect_loopback": effect},
            "pids": {"acceptance": os.getpid(), "asgi": children["asgi"].pid,
                     "effect": children["effect"].pid},
            "steps": steps, "all_local_gates": all(steps.values()),
            "qa_stream_events": qa_lines,
            "research_artifact_sha256": artifact_sha,
            "research_artifact_path": str(artifact),
            "observer": oracle,
            "socket_connections": connects,
            "negative_http_status": {
                key: value["status"] for key, value in negatives.items()
            },
            "original_i28_denominator_reference": 10,
            "original_act_local_denominator_reference": 12,
            "n31_new_positive_http_cases": 5,
            "n31_new_negative_http_cases": len(negatives),
            "ar09": "ORACLE_UNAVAILABLE", "ar10": "DRAFT",
            "code_l_persisted_patch": False,
            "external_auth": False, "default_authentic_app_ready": False,
            "production": False,
            "feature_disabled_exit": disabled.returncode,
            "nonloopback_exit": nonloopback.returncode,
        }
        (base / "n31_raw_http_receipts.json").write_text(
            json.dumps({"positive": receipts, "negative": negatives},
                       indent=2, ensure_ascii=False),
        )
        (base / "n31_os_acceptance.json").write_text(
            json.dumps(machine, indent=2, ensure_ascii=False),
        )
        print(json.dumps(machine, indent=2, ensure_ascii=False))
        return 0 if all(steps.values()) else 1
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for handle in logs.values():
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
