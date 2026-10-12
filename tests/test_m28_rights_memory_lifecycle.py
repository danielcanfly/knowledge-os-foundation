"""M28 negative cross-process rights/Mem lifecycle and actual I02 wiring tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from knowledge_engine.m27_m28_local_rights_memory_fence import (
    LifecycleDenied, LocalLease, LocalRightsMemoryFence,
)
from knowledge_engine.m27_w4_i02_local_runtime_v1_experimental import (
    I02Denied, I02LocalRuntimeV1,
)
from test_m27_w4_i02_local_runtime_v1_experimental import (
    make, qa_bundle, coding_bundle,
)

PAYLOAD = b"PRIVATE_TENANT_A_SENTINEL_NEVER_ECHOED"
B_PAYLOAD = b"PRIVATE_TENANT_B_SENTINEL_NEVER_ECHOED"


def setup_fence(tmp_path):
    db_path, root = tmp_path / "lifecycle.sqlite", tmp_path / "owned-blobs"
    fence = LocalRightsMemoryFence(db_path, root, fixture_only=True)
    a = fence.grant(tenant="tenantA", run="runA", principal="principalA",
                    purpose="research", revision="rev1", lease_id="leaseA")
    b = fence.grant(tenant="tenantB", run="runB", principal="principalB",
                    purpose="research", revision="revB", lease_id="leaseB",
                    consent_generation=3, policy_generation=9)
    for item, kind in [
        ("source1", "source"), ("citation1", "citation"),
        ("cache1", "cache"), ("memory1", "memory"),
        ("trace1", "trace"), ("checkpoint1", "checkpoint"),
        ("backup1", "backup"),
    ]:
        fence.put(a, item, kind, PAYLOAD + item.encode())
    fence.issue_tool_permit(a, "permit1")
    fence.put(b, "bsource", "source", B_PAYLOAD)
    return fence, a, b, db_path, root


def denied(operation):
    with pytest.raises(LifecycleDenied):
        operation()


def test_local_positive_and_tenant_isolation(tmp_path):
    fence, a, b, _, root = setup_fence(tmp_path)
    assert fence.read(a, "source1") == PAYLOAD + b"source1"
    assert fence.query_cache(a, "cache1") == PAYLOAD + b"cache1"
    assert fence.replay(a, "checkpoint1") == PAYLOAD + b"checkpoint1"
    assert fence.dispatch_local_tool(a, "permit1") == "LOCAL_TOOL_ONLY_NO_EXTERNAL_EFFECT"
    assert fence.publish_queued(a, "citation1") == PAYLOAD + b"citation1"
    assert fence.read(b, "bsource") == B_PAYLOAD
    denied(lambda: fence.read(a, "bsource"))
    denied(lambda: fence.read(b, "source1"))
    denied(lambda: fence.query_cache(b, "cache1"))
    denied(lambda: fence.read(replace(a, tenant_id="tenantB"), "bsource"))
    denied(lambda: fence.read(replace(b, principal_id="principalA"), "bsource"))
    denied(lambda: fence.read(replace(b, policy_generation=8), "bsource"))
    denied(lambda: fence.dispatch_local_tool(b, "permit1"))
    assert (root / "derived" / "tenantA" / "runA" / "source1.bin").exists()
    assert (root / "derived" / "tenantB" / "runB" / "bsource.bin").exists()


def test_live_os_pause_revoke_resume_deny_eight_surfaces(tmp_path):
    fence, a, b, db_path, root = setup_fence(tmp_path)
    lease_file = tmp_path / "lease.json"
    lease_file.write_text(json.dumps(asdict(a), sort_keys=True))
    ready, resume = tmp_path / "child.ready", tmp_path / "child.resume"
    helper = Path(__file__).with_name("m28_rights_memory_child.py")
    process = subprocess.Popen(
        [sys.executable, "-B", str(helper), str(db_path), str(root),
         str(lease_file), str(ready), str(resume)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        deadline = time.monotonic() + 12
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists() and process.poll() is None
        assert int(ready.read_text()) == process.pid
        outcome = fence.revoke(a, reason="CONSENT_WITHDRAWN")
        assert outcome["tombstoned"] and outcome["local_unlinked"] == 6
        assert outcome["backup_quarantined"] == 1
        assert outcome["cleanup_pending"] == ()
        assert not outcome["external_backup_erased"]
        assert not outcome["sqlite_physical_erasure_proven"]
        resume.touch()
        stdout, stderr = process.communicate(timeout=12)
        assert process.returncode == 0, (stdout, stderr)
        assert f"CHILD_DENY_ALL pid={process.pid} cases=8" in stdout
        print(f"M28_OS_WITNESS CHILD_PID={process.pid} EXIT={process.returncode} "
              "PAUSE_REVOKE_RESUME_DENIED=8 TENANT_B_PRESERVED=true")
        assert PAYLOAD.decode() not in stdout + stderr
        assert B_PAYLOAD.decode() not in stdout + stderr
        assert not (root / "derived" / "tenantA" / "runA" / "memory1.bin").exists()
        assert (root / "quarantine" / "tenantA" / "runA" / "backup1.bin").exists()
        assert fence.read(b, "bsource") == B_PAYLOAD
        denied(lambda: fence.grant(tenant="tenantA", run="runA",
                                   principal="principalA", purpose="research",
                                   revision="rev1", lease_id="leaseNew"))
        reopened = LocalRightsMemoryFence(db_path, root, fixture_only=True)
        denied(lambda: reopened.require(a, "read"))
        denied(lambda: reopened.publish_queued(a, "citation1"))
        denied(lambda: reopened.restore_quarantined(a, "backup1"))
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_cleanup_crash_recovery_idempotent_without_regrant(tmp_path, monkeypatch):
    fence, a, b, db_path, root = setup_fence(tmp_path)
    original = fence._file
    failure = {"once": True}
    def interrupted(lease, item, *, quarantine=False):
        if item == "memory1" and failure["once"]:
            failure["once"] = False
            raise OSError("fixture simulated unlink failure")
        return original(lease, item, quarantine=quarantine)
    monkeypatch.setattr(fence, "_file", interrupted)
    receipt = fence.revoke(a, reason="SUBJECT_ERASURE")
    assert receipt["cleanup_pending"] == ("memory1",)
    denied(lambda: fence.read(a, "memory1", kind="memory"))
    assert (root / "derived" / "tenantA" / "runA" / "memory1.bin").exists()
    new_process_view = LocalRightsMemoryFence(db_path, root, fixture_only=True)
    repaired = new_process_view.recover_local_cleanup(a)
    assert repaired["cleanup_pending"] == ()
    assert not (root / "derived" / "tenantA" / "runA" / "memory1.bin").exists()
    again = new_process_view.recover_local_cleanup(a)
    assert again["local_unlinked"] == 0
    assert again["backup_quarantined"] == 1
    denied(lambda: new_process_view.restore_quarantined(a, "backup1"))
    assert new_process_view.read(b, "bsource") == B_PAYLOAD


def test_tenant_policy_generations_and_deleted_derived_stores(tmp_path):
    fence, a, b, db_path, root = setup_fence(tmp_path)
    outcome = fence.revoke(b, reason="POLICY_CHANGE")
    assert outcome["tombstoned"] and outcome["local_unlinked"] == 1
    denied(lambda: fence.read(b, "bsource"))
    denied(lambda: fence.read(replace(b, policy_generation=10), "bsource"))
    b2 = fence.grant(tenant="tenantB", run="runB2", principal="principalB",
                     purpose="research", revision="revB2", lease_id="leaseB2",
                     consent_generation=4, policy_generation=10)
    fence.put(b2, "newsource", "source", b"NEW_SCOPE")
    assert LocalRightsMemoryFence(db_path, root, fixture_only=True).read(
        b2, "newsource") == b"NEW_SCOPE"
    denied(lambda: fence.read(replace(b, run_id="runB2"), "newsource"))
    assert fence.read(a, "source1").startswith(PAYLOAD)


def make_runtime_fenced(tmp_path, *, run="runA", kind="QA-I", exclusion=0):
    baseline, contract = make(tmp_path, kind=kind, run=run,
                              budget=(3 if kind == "CODE-L" else 100),
                              exclusion=exclusion)
    fence = LocalRightsMemoryFence(tmp_path / "fence.db",
                                   tmp_path / "blobs", fixture_only=True)
    lease = fence.grant(tenant="tenantA", run=run, principal="principalA",
                        purpose="research", revision="rev1", lease_id="lease_" + run)
    contract = replace(contract, lifecycle_lease=lease)
    return I02LocalRuntimeV1(baseline.writer, lifecycle=fence), contract, fence, lease


def test_i02_positive_real_local_native_qa_wire(tmp_path):
    runtime, contract, fence, lease = make_runtime_fenced(tmp_path)
    args = qa_bundle(runtime, contract)
    outcome, state, _ = runtime.qa(contract, **args)
    assert outcome.first_text_flushed_preterminal
    assert state.status == "terminal"
    assert len([e for e in args["transport"].events if e[0] == "flush"]) >= 1
    assert not outcome.client_ack
    assert fence.require(lease, "publish") is None


def test_i02_revoke_after_queue_before_flush_no_publication(tmp_path):
    runtime, contract, fence, lease = make_runtime_fenced(tmp_path)
    args = qa_bundle(runtime, contract)
    args["transport"].on_enqueue = lambda frame: fence.revoke(lease)
    with pytest.raises(I02Denied, match="LOCAL_LIFECYCLE_REVOKED_OR_STALE"):
        runtime.qa(contract, **args)
    assert args["transport"].events[0][0] == "enqueue"
    assert not any(event[0] == "flush" for event in args["transport"].events)
    reopened = I02LocalRuntimeV1(runtime.writer,
                                lifecycle=LocalRightsMemoryFence(
                                    fence.db_path, fence.blob_root, fixture_only=True))
    with pytest.raises(I02Denied):
        reopened.admit(contract)


def test_i02_rejects_missing_stale_and_wrong_tenant_lease(tmp_path):
    runtime, contract, fence, lease = make_runtime_fenced(tmp_path)
    with pytest.raises(I02Denied, match="LIFECYCLE_SCOPE_OR_LEASE"):
        runtime.admit(replace(contract, lifecycle_lease=None))
    with pytest.raises(I02Denied, match="LIFECYCLE_SCOPE_OR_LEASE"):
        runtime.admit(replace(contract, lifecycle_lease=replace(lease, tenant_id="tenantB")))
    with pytest.raises(I02Denied, match="LIFECYCLE_REVOKED_OR_STALE"):
        runtime.admit(replace(contract, lifecycle_lease=replace(lease, policy_generation=0)))
    assert runtime.admit(contract) == contract.journal_head


def test_i02_coding_final_subprocess_send_fence(tmp_path, monkeypatch):
    import knowledge_engine.m27_w3_ar08_coding_action_v1_experimental as module
    runtime, contract, fence, lease = make_runtime_fenced(
        tmp_path, kind="CODE-L", exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    original = module._owned_file
    state = {"revoked": False, "process_launch": 0}
    def write_then_revoke(folder, name, data):
        value = original(folder, name, data)
        if name == "test_fixture.py" and not state["revoked"]:
            fence.revoke(lease)
            state["revoked"] = True
        return value
    def forbidden_subprocess(*args, **kwargs):
        state["process_launch"] += 1
        raise AssertionError("revoked: subprocess must not launch")
    monkeypatch.setattr(module, "_owned_file", write_then_revoke)
    monkeypatch.setattr(module.subprocess, "run", forbidden_subprocess)
    outcome, receipt = runtime.coding(contract, **kwargs)
    assert state["revoked"]
    assert state["process_launch"] == 0
    assert receipt.attempts == 0
    assert outcome.status == "UNKNOWN_EFFECT_NO_AUTORETRY"
    assert runtime.writer.recover(contract.identity)["outbox"][0]["state"] == "POSSIBLY_SENT"
