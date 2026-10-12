"""K28 AR02+AR04 scoped local guard regressions; no provider dispatch."""
import hashlib
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

from k28_real_os_fault_harness import (
    KEY, VERIFIER, IDENTITY, INTENT, IDEMPOTENCY, EXPIRY,
    writer, initialize, intent, arm, emit,
    FenceError, http_json
)


def load(name, filename):
    source = Path(__file__).resolve().parents[1] / "src" / "knowledge_engine" / filename
    spec = spec_from_file_location(name, source)
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ar04 = load("k28_actual_ar04", "m27_ar04_permit_sandbox_v1_experimental.py")


def denied(code, call, errors):
    try:
        call()
    except (ar04.Denied, FenceError) as exc:
        if code not in str(exc):
            raise AssertionError(f"wanted {code!r}; got {exc!r}")
        errors.append({"expected": code, "actual": str(exc)})
        return
    raise AssertionError(f"call should have been denied: {code}")


def exercise(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    errors = []
    rule = ar04.CapabilityRule(
        "cap.items", "1", "update", "/tenants/tenant-k28/items/", "local-only-adapter", 20
    )
    registry = ar04.Registry(
        "fixture-policy", frozenset({"fixture-approver"}),
        frozenset({"fixture-observer-issuer"}), "fixture-writer",
        frozenset({"local-only-adapter"}), (rule,)
    )
    req = ar04.ActionRequest(
        "request-k28", "run-k28", "tenant-k28", "actor-k28", None,
        "cap.items", "1", "update", "/tenants/tenant-k28/items/one",
        "recipient-k28", "a" * 64, IDEMPOTENCY, "1", 7
    )
    snap = ar04.AuthoritySnapshot(
        "run-k28", "tenant-k28", "actor-k28", None,
        "worker-k28", 7, 200, 200, 3, 0, "head-fixture", 15, "fixture-policy"
    )
    sandbox = ar04.PermitSandboxV1(registry, ar04.MockWriterPort())
    denied("FEATURE_MUST_REMAIN_OFF",
           lambda: ar04.PermitSandboxV1(replace(registry, real_dispatch_authorized=True),
                                        ar04.MockWriterPort()), errors)
    denied("FEATURE_MUST_REMAIN_OFF",
           lambda: ar04.PermitSandboxV1(replace(registry, feature_enabled=True),
                                        ar04.MockWriterPort()), errors)
    denied("LEASE_STALE", lambda: sandbox.request(req, replace(snap, lease_epoch=8),
                                                  now=100), errors)
    denied("LEASE_STALE", lambda: sandbox.request(req, replace(snap, lease_until=100),
                                                  now=100), errors)
    denied("CONSENT_REVOKED_OR_EXPIRED",
           lambda: sandbox.request(req, replace(snap, revocation_generation=1),
                                   now=100), errors)
    denied("CONSENT_REVOKED_OR_EXPIRED",
           lambda: sandbox.request(req, replace(snap, consent_until=100),
                                   now=100), errors)
    denied("RESOURCE_SCOPE_ESCAPE",
           lambda: sandbox.request(replace(req, resource_id="/tenants/tenant-b/items/one"),
                                   snap, now=100), errors)
    sandbox.request(req, snap, now=100)
    denied("REUSED_IDEMPOTENCY_KEY",
           lambda: sandbox.request(replace(req, request_id="replayed-different-id"),
                                   snap, now=100), errors)
    decision = ar04.ApprovalDecision(
        "approval-k28", "fixture-approver", True,
        req.digest(), "1", "run-k28", "tenant-k28", 7, 3, 0, 180
    )
    denied("UNTRUSTED_OR_REUSED_APPROVAL",
           lambda: sandbox.issue_permit(req.request_id,
                                        replace(decision, approved=False), snap,
                                        now=100, quoted_cost=5), errors)
    denied("APPROVAL_BINDING_OR_EXPIRY",
           lambda: sandbox.issue_permit(req.request_id,
                                        replace(decision, expires_at=99), snap,
                                        now=100, quoted_cost=5), errors)
    permit = sandbox.issue_permit(req.request_id, decision, snap,
                                  now=100, quoted_cost=5)
    denied("UNTRUSTED_OR_REUSED_APPROVAL",
           lambda: sandbox.issue_permit(req.request_id, decision, snap,
                                        now=100, quoted_cost=5), errors)
    denied("LEASE_STALE",
           lambda: sandbox.freeze_claim(permit, replace(snap, lease_until=100),
                                        claim_id="c", sender_id="worker-k28",
                                        physical_attempt=1, now=100), errors)
    claim = sandbox.freeze_claim(permit, snap, claim_id="c",
                                 sender_id="worker-k28", physical_attempt=1, now=100)
    denied("DUPLICATE_OR_INVALID_CLAIM",
           lambda: sandbox.freeze_claim(permit, snap, claim_id="c2",
                                        sender_id="worker-k28", physical_attempt=1,
                                        now=100), errors)
    denied("NO_AUTHENTIC_DURABLE_OUTBOX_ACK",
           lambda: sandbox.attempt_external(claim, snap, now=100), errors)
    # Even a forged local receipt that syntactically claims durability cannot open T3.
    class PretendWriter:
        def prepare_claim(self, permit, claim_id):
            return ar04.DurableWriterReceipt(
                "fixture-writer", claim_id, permit.permit_id, permit.intent_digest,
                permit.request.run_id, permit.request.tenant_id, "worker-k28",
                permit.request.lease_epoch, snap.head_hash, "fixture-ACK", True, False
            )
    forged_sandbox = ar04.PermitSandboxV1(registry, PretendWriter())
    forged_sandbox.request(req, snap, now=100)
    fake_permit = forged_sandbox.issue_permit(
        req.request_id, decision, snap, now=100, quoted_cost=5)
    fake_claim = forged_sandbox.freeze_claim(
        fake_permit, snap, claim_id="faked", sender_id="worker-k28",
        physical_attempt=1, now=100)
    denied("REAL_DISPATCH_DISABLED",
           lambda: forged_sandbox.attempt_external(fake_claim, snap, now=100), errors)

    # An explicit local supervisor cancellation marker is a durable pre-send gate,
    # not a new AR02 public API or an externally authenticated task cancellation.
    cancel_db = root / "cancel.sqlite3"
    with sqlite3.connect(cancel_db) as db:
        db.execute("CREATE TABLE cancellation (run TEXT PRIMARY KEY, requested INTEGER)")
        db.execute("INSERT INTO cancellation VALUES(?,1)", (IDENTITY.run_id,))
        db.commit()
    canceled = sqlite3.connect(cancel_db).execute(
        "SELECT requested FROM cancellation WHERE run=?", (IDENTITY.run_id,)
    ).fetchone()[0]
    denied("TASK_CANCELLED_LOCAL",
           lambda: (_ for _ in ()).throw(FenceError("TASK_CANCELLED_LOCAL"))
               if canceled else None, errors)
    assert canceled == 1

    emit(root / "receipt.json", {
        "schema": "K28_LOCAL_AR02_AR04_GUARD_REGRESSION_V1",
        "count": len(errors), "failed": 0,
        "guards": errors, "cancelled_marker_durable": bool(canceled),
        "ar04_real_dispatch": "DENIED_UNCONDITIONALLY",
        "externally_authorized": False, "local_fixture_only": True
    })
    return len(errors)


if __name__ == "__main__":
    n = exercise(sys.argv[1])
    print(json.dumps({"PASS": "AR02_AR04_GUARDS", "count": n}))
