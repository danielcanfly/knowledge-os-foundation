"""K02D independent disk-backed fault oracle. NO provider or production access."""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import subprocess
import sys
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    RunIdentity,
)

KEY = b"k02d-synthetic-unique-verifier-key"
EVIDENCE_SHA = hashlib.sha256(b"separately supplied mock observer blob").hexdigest()
IDENTITY = RunIdentity("tenant-a", "run-1", "task-1", 1, "worker-a")


@pytest.fixture
def case(tmp_path):
    path = tmp_path / "actual_disk.db"
    writer = DurableWriterV1(
        path, fixture_approval_mode=True, verifier_keys={"verifier-a": KEY}
    )
    head = writer.create_run(
        IDENTITY, budget=100, source_revision="source-v1",
        consent_generation=1, exclusion_generation=1,
    )
    assert path.exists() and path.stat().st_size > 0
    return writer, head, path


def prepared(writer, head, *, intent_id="intent-1", claim_id="claim-1",
             reserve_id="reserve-1", approval_id="approval-1",
             idempotency_key="idem-1", digest="digest-1", now=10):
    head = writer.reserve(IDENTITY, head, reserve_id=reserve_id, amount=25)
    head = writer.provision_fixture_approval(
        IDENTITY, head, approval_id=approval_id, intent_digest=digest, expires_at=50,
    )
    head = writer.commit_intent_and_claim(
        IDENTITY, head, intent_id=intent_id, intent_digest=digest,
        approval_id=approval_id, claim_id=claim_id,
        reserve_id=reserve_id, idempotency_key=idempotency_key, now=now,
    )
    return head


def unknown(writer, head):
    head = prepared(writer, head)
    head, ack = writer.claim_outbox(IDENTITY, head, claim_id="claim-1")
    head = writer.mark_possible_send(
        IDENTITY, head, claim_id="claim-1", local_ack_token=ack,
    )
    return head


def observed(writer, head, *, now=20, outcome="CONFIRMED_APPLIED"):
    return writer.record_observer_reconciliation(
        IDENTITY, head, intent_id="intent-1", original_t1_digest="digest-1",
        observer_id="observer-a", evidence_ref="evidence-1",
        evidence_sha256=EVIDENCE_SHA, outcome=outcome,
        source_revision="source-v1", consent_generation=1,
        exclusion_generation=1, expires_at=50, now=now,
    )


def sign(head, *, status="LOCAL_VERIFIED_APPLIED", verification_ref="verification-1",
         evidence_ref="evidence-1", identity=IDENTITY):
    message = DurableWriterV1.verification_message(
        identity, head, evidence_ref=evidence_ref,
        verification_ref=verification_ref, status=status,
    )
    return hmac.new(KEY, message, hashlib.sha256).hexdigest()


def terminal(writer, head, **override):
    kwargs = {
        "evidence_ref": "evidence-1",
        "verification_ref": "verification-1",
        "verifier_id": "verifier-a",
        "signature_hex": sign(head),
        "status": "LOCAL_VERIFIED_APPLIED",
        "now": 30,
    }
    kwargs.update(override)
    return writer.commit_terminal(IDENTITY, head, **kwargs)


def test_acid_positive_cross_process_and_postterminal_sidecar(case):
    writer, head, path = case
    head = unknown(writer, head)
    assert writer.recover(IDENTITY)["outbox"][0]["state"] == "POSSIBLY_SENT"
    head = observed(writer, head)
    head = terminal(writer, head)
    assert head.state == "LOCAL_VERIFIED_APPLIED"
    before = head
    writer2 = DurableWriterV1(path, verifier_keys={"verifier-a": KEY})
    assert writer2.read_head(IDENTITY) == head
    assert writer2.recover(IDENTITY)["dispatch_authorized"] is False
    assert writer2.recover(IDENTITY)["AR02_STAGE_DONE"] is False
    assert writer2.read_head(IDENTITY) == before
    cmd = (
        "from knowledge_engine.m27_ar02_durable_writer_v1_experimental "
        "import DurableWriterV1,RunIdentity; "
        "import sys,json; "
        "w=DurableWriterV1(sys.argv[1]);"
        "i=RunIdentity('tenant-a','run-1','task-1',1,'worker-a');"
        "s=w.recover(i);print(json.dumps([s['head'].seq,s['head'].digest,"
        "s['head'].state,len(s['outbox'])]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", cmd, str(path)],
        check=True, capture_output=True, text=True,
    )
    assert result.stdout.strip() == (
        f'[{head.seq}, "{head.digest}", "LOCAL_VERIFIED_APPLIED", 1]'
    )


def test_positive_reserve_charge_adjustment_after_terminal(case):
    writer, head, path = case
    head = writer.reserve(IDENTITY, head, reserve_id="fee-reservation", amount=20)
    head = writer.charge(
        IDENTITY, head, reserve_id="fee-reservation", charge_id="charge-1", amount=14,
    )
    assert head.spent == 14 and head.reserved == 0
    head = unknown(writer, head)
    head = observed(writer, head)
    head = terminal(writer, head)
    writer.audit_charge_adjustment(
        adjustment_id="adjust-1", charge_id="charge-1",
        delta=3, evidence_ref="late-invoice-1",
    )
    restarted = DurableWriterV1(path)
    assert restarted.recover(IDENTITY)["corrected_spent"] == 17
    assert restarted.read_head(IDENTITY) == head
    assert restarted.read_head(IDENTITY).state == "LOCAL_VERIFIED_APPLIED"
    with pytest.raises(sqlite3.IntegrityError):
        writer.audit_charge_adjustment(
            adjustment_id="adjust-1", charge_id="charge-1",
            delta=3, evidence_ref="late-invoice-1",
        )


def test_verified_negative_t4_is_not_success(case):
    writer, head, _ = case
    head = observed(writer, unknown(writer, head),
                    outcome="CONFIRMED_NOT_APPLIED")
    with pytest.raises(FenceError):
        terminal(writer, head)
    status = "LOCAL_VERIFIED_NOT_APPLIED"
    updated = writer.commit_terminal(
        IDENTITY, head, evidence_ref="evidence-1",
        verification_ref="verification-1", verifier_id="verifier-a",
        signature_hex=sign(head, status=status), status=status, now=30,
    )
    assert updated.state == status


def test_duplicate_claim_and_unknown_send_remain_fenced(case):
    writer, head, path = case
    head = prepared(writer, head)
    head, ack = writer.claim_outbox(IDENTITY, head, claim_id="claim-1")
    with pytest.raises(FenceError):
        writer.claim_outbox(IDENTITY, head, claim_id="claim-1")
    assert DurableWriterV1(path).recover(IDENTITY)["outbox"][0]["state"] == "CLAIMED"
    with pytest.raises(FenceError):
        writer.mark_possible_send(IDENTITY, head, claim_id="claim-1",
                                  local_ack_token="lost-ack")
    head = writer.mark_possible_send(
        IDENTITY, head, claim_id="claim-1", local_ack_token=ack,
    )
    with pytest.raises(FenceError):
        writer.mark_possible_send(IDENTITY, head, claim_id="claim-1",
                                  local_ack_token=ack)
    assert DurableWriterV1(path).recover(IDENTITY)["outbox"][0]["state"] == "POSSIBLY_SENT"


def test_durable_commit_ack_loss_never_returns_second_token(case):
    writer, head, path = case
    head = prepared(writer, head)
    head, _lost_ack = writer.claim_outbox(IDENTITY, head, claim_id="claim-1")
    writer2 = DurableWriterV1(path)
    with pytest.raises(FenceError):
        writer2.claim_outbox(IDENTITY, head, claim_id="claim-1")
    assert writer2.recover(IDENTITY)["outbox"][0]["state"] == "CLAIMED"


def test_process_crash_before_commit_rolls_back_and_after_commit_persists(case):
    writer, head, path = case
    # Separate Python PID intentionally dies without committing a physical write.
    code = (
        "import sqlite3,sys,os;"
        "d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA foreign_keys=ON');"
        "d.execute('BEGIN IMMEDIATE');"
        "d.execute(\"INSERT INTO reservations VALUES("
        "'tenant-a','run-1','uncommitted',1,0)\");"
        "os._exit(29)"
    )
    killed = subprocess.run([sys.executable, "-c", code, str(path)], check=False)
    assert killed.returncode == 29
    assert writer.read_head(IDENTITY) == head
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM reservations WHERE reserve_id='uncommitted'"
        ).fetchone()[0] == 0
    code_after = (
        "import sys,os;"
        "from knowledge_engine.m27_ar02_durable_writer_v1_experimental "
        "import DurableWriterV1,RunIdentity;"
        "w=DurableWriterV1(sys.argv[1]);"
        "i=RunIdentity('tenant-a','run-1','task-1',1,'worker-a');"
        "w.reserve(i,w.read_head(i),reserve_id='committed',amount=7);"
        "os._exit(29)"
    )
    after = subprocess.run(
        [sys.executable, "-c", code_after, str(path)], check=False
    )
    assert after.returncode == 29
    assert DurableWriterV1(path).read_head(IDENTITY).seq == head.seq + 1
    assert DurableWriterV1(path).read_head(IDENTITY).reserved == 7


def test_cross_process_competing_budget_and_cas_only_one_wins(case):
    writer, head, path = case
    # Two independent processes competing on the SAME preflight head.
    cmd = (
        "import sys;"
        "from knowledge_engine.m27_ar02_durable_writer_v1_experimental "
        "import DurableWriterV1,RunIdentity,Head;"
        "w=DurableWriterV1(sys.argv[1]);"
        "i=RunIdentity('tenant-a','run-1','task-1',1,'worker-a');"
        "h=Head(1,sys.argv[2],1,'OPEN',100,0,0);"
        "w.reserve(i,h,reserve_id=sys.argv[3],amount=90)"
    )
    a = subprocess.Popen(
        [sys.executable, "-c", cmd, str(path), head.digest, "race-a"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    b = subprocess.Popen(
        [sys.executable, "-c", cmd, str(path), head.digest, "race-b"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    a.communicate(timeout=15)
    b.communicate(timeout=15)
    assert sorted([a.returncode, b.returncode])[0] == 0
    assert sorted([a.returncode, b.returncode])[1] != 0
    assert writer.read_head(IDENTITY).reserved == 90
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 1


def test_second_connection_cas_and_tenant_isolation(case):
    writer, head, path = case
    other = DurableWriterV1(path)
    h = other.reserve(IDENTITY, head, reserve_id="first", amount=50)
    with pytest.raises(FenceError, match="STALE_HEAD"):
        writer.reserve(IDENTITY, head, reserve_id="second", amount=50)
    twin = replace(IDENTITY, tenant_id="tenant-b")
    other_head = other.create_run(
        twin, budget=10, source_revision="rev", consent_generation=1,
        exclusion_generation=1,
    )
    assert twin.run_id == IDENTITY.run_id
    assert other_head.seq == 1
    assert writer.read_head(IDENTITY) == h


def test_chain_integrity_detects_corrupt_event_and_head(case):
    writer, head, path = case
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("UPDATE events SET payload='{}' WHERE seq=1")
        db.execute("UPDATE runs SET digest=? WHERE tenant=? AND run=?",
                   ("0" * 64, IDENTITY.tenant_id, IDENTITY.run_id))
    with pytest.raises(FenceError, match="CORRUPT_EVENT_HEAD"):
        writer.read_head(IDENTITY)
    with pytest.raises(FenceError, match="CORRUPT_EVENT_HEAD"):
        writer.reserve(IDENTITY, head, reserve_id="refuse", amount=1)


def test_uncommitted_budget_change_rollback_and_reopen(case):
    writer, head, path = case
    with pytest.raises(RuntimeError), writer._write() as db:
        db.execute(
            "UPDATE runs SET spent=99 WHERE tenant=? AND run=?",
            (IDENTITY.tenant_id, IDENTITY.run_id),
        )
        raise RuntimeError("fault at precommit")
    assert DurableWriterV1(path).read_head(IDENTITY) == head


@pytest.mark.parametrize(
    "fault",
    [
        "empty_tenant", "bad_version", "duplicate_run", "wrong_tenant",
        "wrong_task", "wrong_version", "wrong_principal", "overspend",
        "zero_reserve", "negative_reserve", "duplicate_reserve", "stale_seq",
        "stale_hash", "stale_epoch", "wrong_approval_digest", "expired_approval",
        "missing_approval", "duplicate_intent", "duplicate_claim",
        "duplicate_idempotency", "approval_replay", "stale_takeover",
        "charge_unknown", "charge_negative", "charge_overcap",
        "charge_duplicate", "wrong_reserve", "premature_send", "wrong_ack",
        "terminal_missing_observer", "fake_terminal_signature", "fake_success",
        "self_observer", "wrong_original_digest", "expired_evidence",
        "wrong_source", "wrong_consent", "wrong_exclusion", "bad_evidence_sha",
        "wrong_outcome", "t4_without_t3", "self_verifier",
        "missing_verifier_key", "wrong_verification_ref", "double_terminal",
        "revocation_denies", "authority_generation_rollback", "source_drift",
        "consent_drift", "exclusion_drift",
    ],
)
def test_independent_fail_closed_faults(case, fault):
    writer, head, path = case
    with pytest.raises((FenceError, sqlite3.IntegrityError, ValueError)):
        if fault == "empty_tenant":
            writer.create_run(
                replace(IDENTITY, tenant_id=""), budget=1, source_revision="v",
                consent_generation=1, exclusion_generation=1,
            )
        elif fault == "bad_version":
            writer.create_run(
                replace(IDENTITY, task_version=0), budget=1, source_revision="v",
                consent_generation=1, exclusion_generation=1,
            )
        elif fault == "duplicate_run":
            writer.create_run(
                IDENTITY, budget=1, source_revision="v",
                consent_generation=1, exclusion_generation=1,
            )
        elif fault in {"wrong_tenant", "wrong_task", "wrong_version", "wrong_principal"}:
            key = {
                "wrong_tenant": ("tenant_id", "tenant-b"),
                "wrong_task": ("task_id", "task-b"),
                "wrong_version": ("task_version", 3),
                "wrong_principal": ("principal_id", "outsider"),
            }[fault]
            writer.read_head(replace(IDENTITY, **{key[0]: key[1]}))
        elif fault in {"overspend", "zero_reserve", "negative_reserve"}:
            amount = {"overspend": 101, "zero_reserve": 0,
                      "negative_reserve": -1}[fault]
            writer.reserve(IDENTITY, head, reserve_id="bad", amount=amount)
        elif fault == "duplicate_reserve":
            head = writer.reserve(IDENTITY, head, reserve_id="dup", amount=1)
            writer.reserve(IDENTITY, head, reserve_id="dup", amount=1)
        elif fault in {"stale_seq", "stale_hash", "stale_epoch"}:
            changes = {
                "stale_seq": {"seq": head.seq + 1},
                "stale_hash": {"digest": "deadbeef"},
                "stale_epoch": {"epoch": head.epoch + 1},
            }
            writer.reserve(IDENTITY, replace(head, **changes[fault]),
                           reserve_id="bad", amount=1)
        elif fault in {"wrong_approval_digest", "expired_approval",
                       "missing_approval"}:
            head = writer.reserve(IDENTITY, head, reserve_id="reserve-1", amount=25)
            if fault != "missing_approval":
                head = writer.provision_fixture_approval(
                    IDENTITY, head, approval_id="approval-1",
                    intent_digest=("wrong" if fault == "wrong_approval_digest"
                                   else "digest-1"),
                    expires_at=(5 if fault == "expired_approval" else 50),
                )
            writer.commit_intent_and_claim(
                IDENTITY, head, intent_id="intent-1", intent_digest="digest-1",
                approval_id="approval-1", claim_id="claim-1",
                reserve_id="reserve-1", idempotency_key="idem-1", now=10,
            )
        elif fault in {"duplicate_intent", "duplicate_claim",
                       "duplicate_idempotency", "approval_replay"}:
            head = prepared(writer, head)
            head = writer.reserve(IDENTITY, head, reserve_id="reserve-2", amount=1)
            head = writer.provision_fixture_approval(
                IDENTITY, head, approval_id="approval-2", intent_digest="digest-2",
                expires_at=50,
            )
            writer.commit_intent_and_claim(
                IDENTITY, head, intent_id=("intent-1" if fault == "duplicate_intent"
                                     else "intent-2"),
                intent_digest="digest-2",
                approval_id=("approval-1" if fault == "approval_replay"
                             else "approval-2"),
                claim_id=("claim-1" if fault == "duplicate_claim"
                          else "claim-2"),
                reserve_id="reserve-2",
                idempotency_key=("idem-1" if fault == "duplicate_idempotency"
                                 else "idem-2"), now=10,
            )
        elif fault == "stale_takeover":
            old = head
            writer.takeover(IDENTITY, head)
            writer.reserve(IDENTITY, old, reserve_id="stale", amount=1)
        elif fault in {"charge_unknown", "charge_negative",
                       "charge_overcap", "wrong_reserve", "charge_duplicate"}:
            head = writer.reserve(IDENTITY, head, reserve_id="reserve-1", amount=10)
            if fault == "charge_duplicate":
                head = writer.charge(
                    IDENTITY, head, reserve_id="reserve-1", charge_id="charge-1", amount=5,
                )
            writer.charge(
                IDENTITY, head,
                reserve_id=("no-reservation" if fault == "wrong_reserve"
                            else "reserve-1"),
                charge_id="charge-1",
                amount={"charge_unknown": -1, "charge_negative": -10,
                        "charge_overcap": 11}.get(fault, 5),
            )
        elif fault in {"premature_send", "wrong_ack"}:
            head = prepared(writer, head)
            if fault == "wrong_ack":
                head, _ = writer.claim_outbox(IDENTITY, head, claim_id="claim-1")
            writer.mark_possible_send(
                IDENTITY, head, claim_id="claim-1", local_ack_token="forged",
            )
        elif fault in {"terminal_missing_observer", "fake_terminal_signature",
                       "fake_success", "self_observer", "wrong_original_digest",
                       "expired_evidence", "wrong_source", "wrong_consent",
                       "wrong_exclusion", "bad_evidence_sha", "wrong_outcome",
                       "t4_without_t3", "self_verifier", "missing_verifier_key",
                       "wrong_verification_ref", "double_terminal"}:
            head = (prepared(writer, head) if fault == "t4_without_t3"
                    else unknown(writer, head))
            if fault in {"self_observer", "wrong_original_digest",
                         "expired_evidence", "wrong_source", "wrong_consent",
                         "wrong_exclusion", "bad_evidence_sha", "wrong_outcome",
                         "t4_without_t3"}:
                kw = {
                    "self_observer": {"observer_id": IDENTITY.principal_id},
                    "wrong_original_digest": {"original_t1_digest": "altered"},
                    "expired_evidence": {"expires_at": 1},
                    "wrong_source": {"source_revision": "source-v2"},
                    "wrong_consent": {"consent_generation": 2},
                    "wrong_exclusion": {"exclusion_generation": 2},
                    "bad_evidence_sha": {"evidence_sha256": "not-a-hash"},
                    "wrong_outcome": {"outcome": "INFERRED_APPLIED"},
                    "t4_without_t3": {},
                }[fault]
                args = {
                    "intent_id": "intent-1", "original_t1_digest": "digest-1",
                    "observer_id": "observer-a", "evidence_ref": "evidence-1",
                    "evidence_sha256": EVIDENCE_SHA, "outcome": "CONFIRMED_APPLIED",
                    "source_revision": "source-v1", "consent_generation": 1,
                    "exclusion_generation": 1, "expires_at": 50, "now": 20,
                }
                writer.record_observer_reconciliation(IDENTITY, head, **(args | kw))
            else:
                if fault != "terminal_missing_observer":
                    head = observed(writer, head)
                if fault == "fake_terminal_signature":
                    terminal(writer, head, signature_hex="00" * 32)
                elif fault == "fake_success":
                    terminal(writer, head, status="SUCCEEDED")
                elif fault == "self_verifier":
                    terminal(writer, head, verifier_id=IDENTITY.principal_id)
                elif fault == "missing_verifier_key":
                    DurableWriterV1(path).commit_terminal(
                        IDENTITY, head, evidence_ref="evidence-1",
                        verification_ref="verification-1",
                        verifier_id="verifier-a",
                        signature_hex=sign(head), status="LOCAL_VERIFIED_APPLIED",
                        now=30,
                    )
                elif fault == "wrong_verification_ref":
                    terminal(writer, head, verification_ref="different")
                elif fault == "double_terminal":
                    head = terminal(writer, head)
                    terminal(writer, head, signature_hex=sign(head))
                else:
                    terminal(writer, head)
        elif fault in {"revocation_denies", "authority_generation_rollback",
                       "source_drift", "consent_drift", "exclusion_drift"}:
            if fault == "authority_generation_rollback":
                writer.update_authority(
                    IDENTITY, head, source_revision="v2", consent_generation=0,
                    exclusion_generation=1,
                )
            elif fault == "revocation_denies":
                head = writer.update_authority(
                    IDENTITY, head, source_revision="v2", consent_generation=2,
                    exclusion_generation=2, revoked=True,
                )
                writer.reserve(IDENTITY, head, reserve_id="revoked", amount=1)
            else:
                head = writer.reserve(IDENTITY, head, reserve_id="reserve-1", amount=25)
                head = writer.provision_fixture_approval(
                    IDENTITY, head, approval_id="approval-1",
                    intent_digest="digest-1", expires_at=50,
                )
                head = writer.update_authority(
                    IDENTITY, head,
                    source_revision=("source-v2" if fault == "source_drift"
                                     else "source-v1"),
                    consent_generation=(2 if fault == "consent_drift" else 1),
                    exclusion_generation=(2 if fault == "exclusion_drift" else 1),
                )
                writer.commit_intent_and_claim(
                    IDENTITY, head, intent_id="intent-1", intent_digest="digest-1",
                    approval_id="approval-1", claim_id="claim-1",
                    reserve_id="reserve-1", idempotency_key="idem-1", now=10,
                )


def test_source_revocation_between_t4_and_t5_never_terminal(case):
    writer, head, _ = case
    head = observed(writer, unknown(writer, head))
    head = writer.update_authority(
        IDENTITY, head, source_revision="source-v2", consent_generation=2,
        exclusion_generation=3, revoked=True,
    )
    with pytest.raises(FenceError):
        terminal(writer, head, signature_hex=sign(head))
    assert writer.read_head(IDENTITY).state == "OPEN"


def test_stale_pre_takeover_approval_cannot_be_rebound(case):
    writer, head, _ = case
    head = writer.reserve(IDENTITY, head, reserve_id="reserve-1", amount=10)
    head = writer.provision_fixture_approval(
        IDENTITY, head, approval_id="approve-old", intent_digest="digest-1", expires_at=50,
    )
    head = writer.takeover(IDENTITY, head)
    with pytest.raises(FenceError):
        writer.commit_intent_and_claim(
            IDENTITY, head, intent_id="new", intent_digest="digest-1",
            approval_id="approve-old", claim_id="new-claim",
            reserve_id="reserve-1", idempotency_key="idem-new", now=10,
        )


def test_cross_run_charge_id_uniqueness(case):
    writer, head, _ = case
    head = writer.reserve(IDENTITY, head, reserve_id="fee", amount=5)
    writer.charge(IDENTITY, head, reserve_id="fee", charge_id="globally-unique", amount=2)
    twin = replace(IDENTITY, run_id="run-2")
    head2 = writer.create_run(
        twin, budget=100, source_revision="source-v1",
        consent_generation=1, exclusion_generation=1,
    )
    head2 = writer.reserve(twin, head2, reserve_id="fee", amount=5)
    with pytest.raises(sqlite3.IntegrityError):
        writer.charge(
            twin, head2, reserve_id="fee", charge_id="globally-unique", amount=2,
        )


def test_no_fixture_approval_unless_mode_enabled(case):
    _, head, path = case
    restricted = DurableWriterV1(path)
    with pytest.raises(FenceError, match="NO_AUTHENTIC_APPROVAL_ISSUER"):
        restricted.provision_fixture_approval(
            IDENTITY, head, approval_id="forged", intent_digest="x", expires_at=100,
        )
