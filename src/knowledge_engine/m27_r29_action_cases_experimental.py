"""R29 actual I28 entrypoint synthetic cases. Own OS HTTP service + SQLite."""

from __future__ import annotations

import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from knowledge_engine import m27_i28_local_fixture_inputs as fixture
from knowledge_engine.m27_r29_local_action_v1_experimental import (
    R29Action,
    R29LocalActionVerifier,
    R29LocalFixtureAdapter,
)
from knowledge_engine.m27_w4_i02_local_runtime_v1_experimental import I02Denied


def vacant_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def action_case(
    scratch: Path,
    runtime_for,
    *,
    run: str,
    port: int,
    token: str,
    mode: str = "normal",
    cut: str = "",
) -> dict:
    runtime, contract, fence, lease = runtime_for(scratch / run, "ACT-LOCAL", run)
    action = R29Action(
        "dedupe_" + run,
        "effect_" + run,
        "tenantA",
        run,
        "principalA",
        "rev1",
        mode,
    )
    adapter = R29LocalFixtureAdapter(port=port, token=token, enabled=True)
    verifier = R29LocalActionVerifier("verifier_x", fixture.KEY)
    callbacks = {}
    if cut == "kill_before":
        callbacks["before_send"] = lambda: os.kill(os.getpid(), signal.SIGKILL)
    if cut == "kill_after":
        callbacks["after_send"] = lambda: os.kill(os.getpid(), signal.SIGKILL)
    if cut == "revoke_enqueue":
        callbacks["after_enqueue"] = lambda: fence.revoke(lease)
    if cut == "cancel_enqueue":
        callbacks["after_enqueue"] = lambda: runtime.writer.update_authority(
            contract.identity,
            runtime.writer.read_head(contract.identity),
            source_revision="rev1",
            consent_generation=1,
            exclusion_generation=0,
            revoked=True,
        )
    try:
        outcome, receipt = runtime.action_local(
            contract,
            action,
            adapter=adapter,
            verifier=verifier,
            **callbacks,
        )
        return {
            "name": run,
            "status": outcome.status,
            "head": asdict(outcome.head),
            "receipt": receipt,
            "journal": runtime.writer.recover(contract.identity),
            "entry_pid": os.getpid(),
            "state": "RETURNED",
        }
    except Exception as exc:
        return {
            "name": run,
            "status": type(exc).__name__,
            "error_code": str(exc),
            "head": asdict(runtime.writer.read_head(contract.identity)),
            "journal": runtime.writer.recover(contract.identity),
            "entry_pid": os.getpid(),
            "state": "DENIED_OR_UNCERTAIN",
        }


def run_cases(scratch: Path, runtime_for) -> dict:
    root = scratch / "r29"
    root.mkdir(parents=True, exist_ok=True)
    port = vacant_port()
    token = os.urandom(24).hex()
    env = dict(os.environ, R29_SYNTHETIC_LOCAL_ONLY="1")
    service = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "knowledge_engine.m27_r29_local_action_v1_experimental",
            "--db",
            str(root / "effects.sqlite3"),
            "--port",
            str(port),
            "--token",
            token,
        ],
        env=env,
        stdout=(root / "service.stdout").open("w"),
        stderr=(root / "service.stderr").open("w"),
    )
    records: list[dict] = []
    try:
        adapter = R29LocalFixtureAdapter(port=port, token=token, enabled=True)
        for _ in range(70):
            if service.poll() is not None:
                raise RuntimeError("R29_SERVICE_EXIT")
            try:
                if adapter._call("GET", "/fixture/ready").get("ready"):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("R29_SERVICE_TIMEOUT")
        for run, mode, cut in [
            ("runActPositive", "normal", ""),
            ("runActLostAck", "lost_ack", ""),
            ("runActUnknown", "observer_unknown", ""),
            ("runActRevoke", "normal", "revoke_enqueue"),
            ("runActCancel", "normal", "cancel_enqueue"),
        ]:
            records.append(
                action_case(root, runtime_for, run=run, port=port, token=token, mode=mode, cut=cut)
            )
        # Negative ACT-LOCAL ingress examples use this exact I02 method,
        # never create a local action outbox or physical POST on denial.
        neg, contract, _, _ = runtime_for(
            root,
            "ACT-LOCAL",
            "runActDenied",
        )
        baseline = R29Action(
            "dedupe_runActDenied",
            "effect_runActDenied",
            "tenantA",
            "runActDenied",
            "principalA",
            "rev1",
        )
        verifier = R29LocalActionVerifier("verifier_x", fixture.KEY)
        for name, bad, candidate in [
            ("wrong_actor", replace(baseline, actor_id="principalB"), adapter),
            ("cross_tenant", replace(baseline, tenant_id="tenantB"), adapter),
            ("stale_revision", replace(baseline, source_revision="rev2"), adapter),
            ("unsafe_effect_id", replace(baseline, effect_id="../../etc"), adapter),
            ("nonfixture_adapter", baseline, object()),
        ]:
            try:
                neg.action_local(contract, bad, adapter=candidate, verifier=verifier)
                denied = False
            except I02Denied:
                denied = True
            records.append(
                {
                    "name": "negative_" + name,
                    "status": "DENIED" if denied else "FAIL",
                    "denied": denied,
                    "journal": neg.writer.recover(contract.identity),
                    "entry_pid": os.getpid(),
                }
            )
        for run, cut in [("runActKillBefore", "kill_before"), ("runActKillAfter", "kill_after")]:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "knowledge_engine.m27_r29_action_cases_experimental",
                    "--worker",
                    "--scratch",
                    str(root),
                    "--run",
                    run,
                    "--port",
                    str(port),
                    "--token",
                    token,
                    "--cut",
                    cut,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            child.communicate(timeout=20)
            from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
                DurableWriterV1,
                RunIdentity,
            )

            ident = RunIdentity("tenantA", run, "taskA", 1, "principalA")
            writer = DurableWriterV1(root / run / (run + ".sqlite"), fixture_approval_mode=True)
            rec = writer.recover(ident)
            # Restart is a new physical OS process and must NOT redispatch.
            restart = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "knowledge_engine.m27_r29_action_cases_experimental",
                    "--restart",
                    "--scratch",
                    str(root),
                    "--run",
                    run,
                ],
                capture_output=True,
                timeout=10,
                check=False,
            )
            records.append(
                {
                    "name": run,
                    "status": "KILLED",
                    "exit": child.returncode,
                    "pid": child.pid,
                    "head": asdict(rec["head"]),
                    "outbox": rec["outbox"],
                    "restart_exit": restart.returncode,
                    "restart_pid_evidence": restart.stdout.decode().strip(),
                    "restart_attempt_denied": restart.returncode == 0,
                }
            )
    finally:
        service.terminate()
        try:
            service.wait(timeout=3)
        except subprocess.TimeoutExpired:
            service.kill()
            service.wait(timeout=3)
    with sqlite3.connect(root / "effects.sqlite3") as db:
        counts = {}
        for run, posts, effects in db.execute(
            """SELECT r.run, COUNT(p.seq), COUNT(DISTINCT e.effect_id)
               FROM (SELECT run FROM posts UNION SELECT run FROM effects) r
               LEFT JOIN posts p ON p.run=r.run
               LEFT JOIN effects e ON e.run=r.run GROUP BY r.run"""
        ):
            counts[run] = {"posts": posts, "effects": effects}
    for r in records:
        r["independent_sqlite"] = counts.get(r["name"], {"posts": 0, "effects": 0})
        if isinstance(r.get("journal"), dict):
            r["journal"]["head"] = asdict(r["journal"]["head"])
    result = {
        "service_pid": service.pid,
        "entry_pid": os.getpid(),
        "service_exit": service.returncode,
        "records": records,
        "fixture_only": True,
        "provider_calls": 0,
    }
    path = root / "cases.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default="")
    parser.add_argument("--cut", default="")
    args = parser.parse_args()
    if args.worker:
        from knowledge_engine.m27_i28_local_candidate_v1_experimental import runtime_for

        action_case(
            args.scratch, runtime_for, run=args.run, port=args.port, token=args.token, cut=args.cut
        )
        return 21  # SIGKILL must prevent return
    if args.restart:
        from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
            DurableWriterV1,
            RunIdentity,
        )
        from knowledge_engine.m27_w4_i02_local_runtime_v1_experimental import (
            I02LocalRuntimeV1,
            TaskContract,
        )

        # Reopen the SAME SQLite journal, physically increment lease epoch,
        # then check the same I02 TaskContract path with unresolved outbox.
        root = args.scratch / args.run
        ident = RunIdentity("tenantA", args.run, "taskA", 1, "principalA")
        writer = DurableWriterV1(root / (args.run + ".sqlite"), fixture_approval_mode=True)
        prior = writer.recover(ident)
        head = writer.takeover(ident, prior["head"])
        contract = TaskContract(
            ident,
            "principalA",
            None,
            "contract1",
            "ACT-LOCAL",
            "rev1",
            fixture.D,
            1,
            0,
            head.epoch,
            head,
            "research",
            fixture.NOW,
            100,
            90,
        )
        rt = I02LocalRuntimeV1(writer)
        try:
            rt.admit(contract)
            return 23
        except I02Denied as exc:
            if str(exc) != "UNKNOWN_EFFECT_NO_REPLAY":
                return 24
            print(
                json.dumps(
                    {
                        "restart_pid": os.getpid(),
                        "denied": True,
                        "reason": str(exc),
                        "lease_epoch_before": prior["head"].epoch,
                        "lease_epoch_after": head.epoch,
                        "outbox_count": len(writer.recover(ident)["outbox"]),
                    }
                )
            )
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
