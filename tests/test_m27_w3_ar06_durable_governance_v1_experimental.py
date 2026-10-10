"""Executable W3 local-only AR06/K02D ledger + fault injection tests."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Event

import pytest

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    RunIdentity,
)
from knowledge_engine.m27_ar03_verified_rights_v1_experimental import (
    CHECKPOINT_VERSION,
    PIN_VERSION,
    SCHEMA_VERSION,
    AuthorizedReadPlan,
    ClaimSpanV1,
    EffectiveActor,
    IssuerKeyRegistry,
    NativeCitationPinV1,
    ReadIntent,
    RunCheckpointV1,
    ScopeSet,
    SourceAuthorityEvidenceV1,
    TrustedIssuerKey,
    VerifiedAuthorityClaim,
    VerifiedRightsConsumer,
    VerifiedSourceObservation,
)
from knowledge_engine.m27_ar06_governed_memory_experimental import (
    Candidate,
    GovernanceBoundary,
    ReadFixture,
    ReviewerDecisionFixture,
    Revocation,
)
from knowledge_engine.m27_w3_ar06_durable_governance_v1_experimental import (
    PASS,
    DurableMemoryDenied,
    DurableMemoryExclusion,
)

SOURCE_BYTES = b"fixture source"
D = sha256(SOURCE_BYTES).hexdigest()
E = "b" * 64


def candidate(**kw):
    return replace(Candidate(
        candidate_id="cand", memory_id="mem", tenant="tenant-a",
        subject="subject-a", purpose="research", producer="agent",
        source_revision="r1", source_digest=D,
        proposed_ref="synthetic://pinned-pointer", proposed_digest=E,
        policy_version="policy1", consent_version="consent1",
        lawful_basis_ref=None, residency="zone", expires_at=100,
    ), **kw)


def reviewer(c, **kw):
    return replace(ReviewerDecisionFixture(
        candidate_id=c.candidate_id, reviewer="independent-reviewer",
        decision="APPROVE", tenant=c.tenant, subject=c.subject,
        purpose=c.purpose, source_revision=c.source_revision,
        source_digest=c.source_digest, proposed_digest=c.proposed_digest,
        policy_version=c.policy_version, consent_version=c.consent_version,
        lawful_basis_ref=c.lawful_basis_ref, residency=c.residency,
        approved_at=1, expires_at=90, independently_reviewed=True,
    ), **kw)


def auth(**kw):
    return replace(ReadFixture(
        tenant="tenant-a", subject="subject-a", purpose="research",
        principal="principal", now=10, source_revision="r1",
        source_digest=D, policy_version="policy1", consent_version="consent1",
        lawful_basis_ref=None, residency="zone", source_acl_current=True,
        effective_principal_test_authorized=True,
    ), **kw)


def revoke(**kw):
    return replace(Revocation(
        revocation_id="rev1", tenant="tenant-a", subject="subject-a",
        memory_id="mem", reason="CONSENT_WITHDRAWN", requested_at=20,
        authenticated_subject_fixture=True,
    ), **kw)


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "test-only.db"
    writer = DurableWriterV1(path, fixture_approval_mode=True)
    identity = RunIdentity("tenant-a", "run", "task", 1, "principal")
    writer.create_run(identity, budget=12, source_revision="r1",
                      consent_generation=2, exclusion_generation=0)
    boundary = GovernanceBoundary()
    c = candidate()
    accepted = boundary.propose(c, reviewer(c), now=10)
    ledger = DurableMemoryExclusion(writer, boundary, identity)
    ticket = ledger.register_reviewed(
        accepted, auth(), consent_generation=2, source_pin="source-id",
    )
    return ledger, writer, boundary, identity, ticket, accepted


def test_valid_registration_is_fixture_only(env):
    ledger, _, _, _, ticket, _ = env
    assert ticket.mock_only and ticket.generation == 0
    assert ticket.event_seq == 1 and ledger.consume(ticket, auth(), operation="use")


def test_restart_roundtrip_allows_only_rebound_inprocess_metadata(env):
    ledger, writer, boundary, identity, ticket, _ = env
    restored = DurableMemoryExclusion(DurableWriterV1(writer.path), boundary, identity)
    assert restored.consume(ticket, auth(), operation="read") == ticket


def test_true_restart_without_reviewer_context_fails_closed(env):
    ledger, writer, _, identity, ticket, _ = env
    fresh = DurableMemoryExclusion(DurableWriterV1(writer.path),
                                   GovernanceBoundary(), identity)
    with pytest.raises(DurableMemoryDenied):
        fresh.consume(ticket, auth(), operation="read")


def test_revocation_tombstone_is_durable_and_monotonic(env):
    ledger, _, _, _, ticket, _ = env
    receipt = ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    assert receipt.generation == 1 and receipt.event_seq == 2
    assert not receipt.actual_physical_purge
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(ticket, auth(now=21), operation="use")


def test_revocation_survives_real_sqlite_restart(env):
    ledger, writer, boundary, identity, ticket, _ = env
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    restarted = DurableMemoryExclusion(DurableWriterV1(writer.path),
                                       boundary, identity)
    with pytest.raises(DurableMemoryDenied):
        restarted.admit("mem", auth(), expected_generation=1)
    with pytest.raises(DurableMemoryDenied):
        restarted.consume(ticket, auth(), operation="replay")


def test_repeated_same_revocation_is_idempotent(env):
    ledger, _, _, _, _, _ = env
    first = ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    second = ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    assert first.generation == second.generation == 1
    assert first.event_digest == second.event_digest


def test_different_revocation_id_does_not_increment_again(env):
    ledger, _, _, _, _, _ = env
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    with pytest.raises(DurableMemoryDenied):
        ledger.revoke(revoke(revocation_id="rev2"),
                      consent_generation=3, expected_generation=1)


def test_consent_generation_cannot_rollback(env):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.revoke(revoke(), consent_generation=1, expected_generation=0)


def test_stale_expected_generation_cannot_revoke(env):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.revoke(revoke(), consent_generation=3, expected_generation=5)


@pytest.mark.parametrize("changes", [
    {"authenticated_subject_fixture": False},
    {"fixture_kind": "LIVE"},
    {"tenant": "tenant-b"},
    {"subject": "other"},
    {"revocation_id": ""},
    {"reason": "NOT_ALLOWED"},
])
def test_rejects_bad_revocation_authority(env, changes):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.revoke(revoke(**changes), consent_generation=3,
                      expected_generation=0)


@pytest.mark.parametrize("bad_auth", [
    {"tenant": "tenant-b"}, {"subject": "stranger"},
    {"purpose": "marketing"}, {"source_revision": "r2"},
    {"source_digest": E}, {"consent_version": "revoked"},
    {"source_acl_current": False}, {"policy_version": "old"},
    {"effective_principal_test_authorized": False},
    {"residency": "other"}, {"now": 90}, {"now": 101},
    {"ledger_available": False}, {"tokens": 0},
])
def test_each_authority_drift_fails_closed(env, bad_auth):
    ledger, _, _, _, ticket, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(ticket, auth(**bad_auth), operation="read")


@pytest.mark.parametrize("operation", ["use", "read", "checkpoint", "replay", "cite"])
def test_all_use_paths_require_fresh_ticket(env, operation):
    ledger, _, _, _, ticket, _ = env
    assert ledger.consume(ticket, auth(), operation=operation) == ticket
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(ticket, auth(), operation=operation)


def test_unrecognized_operation_must_fail(env):
    ledger, _, _, _, ticket, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(ticket, auth(), operation="physical-purge")


def test_descendant_inherits_tombstone(env):
    ledger, _, _, _, ticket, _ = env
    ledger.add_descendant("mem", "child-vector", kind="vector", residency="zone")
    fresh = ledger.admit("mem", auth(), expected_generation=0,
                         descendant_id="child-vector")
    assert fresh.event_seq == 2
    ledger.consume(fresh, auth(), operation="checkpoint",
                   descendant_id="child-vector")
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(fresh, auth(), operation="replay",
                       descendant_id="child-vector")


def test_unregistered_descendant_denied(env):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.admit("mem", auth(), expected_generation=0,
                     descendant_id="invented-child")


def test_old_ticket_invalidated_by_new_descendant_event(env):
    ledger, _, _, _, ticket, _ = env
    ledger.add_descendant("mem", "child", kind="cache", residency="zone")
    with pytest.raises(DurableMemoryDenied, match="STALE_TICKET"):
        ledger.consume(ticket, auth(), operation="use")


def test_held_backup_cannot_count_as_physical_erasure(env):
    ledger, _, boundary, _, _, _ = env
    ledger.add_descendant("mem", "backup", kind="backup", residency="zone")
    result = ledger.revoke(revoke(legal_hold_ref="legal-hold"),
                           consent_generation=3, expected_generation=0)
    assert result.actual_physical_purge is False
    assert boundary.cascade_status("tenant-a", "mem") == "EXCEPTION_HELD"
    with pytest.raises(DurableMemoryDenied):
        ledger.actual_physical_purge(external_receipt="fake")


def test_expired_reviewer_is_not_deletion_proof(env):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.admit("mem", auth(now=90), expected_generation=0)
    with pytest.raises(DurableMemoryDenied):
        ledger.actual_physical_purge(actual_physical_purge=True)


def test_snapshot_before_tombstone_possible_only_in_live_fixture(env):
    ledger, _, _, _, _, _ = env
    assert ledger.restore_snapshot_allowed("mem", auth(), snapshot_generation=0)
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    assert not ledger.restore_snapshot_allowed("mem", auth(), snapshot_generation=0)


def test_snapshot_restore_after_restart_never_resurrects(env):
    ledger, writer, boundary, identity, _, _ = env
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    restarted = DurableMemoryExclusion(DurableWriterV1(writer.path),
                                       boundary, identity)
    assert not restarted.restore_snapshot_allowed(
        "mem", auth(), snapshot_generation=0,
    )


def test_ar02_authority_revoked_after_tombstone(env):
    ledger, writer, _, identity, _, _ = env
    receipt = ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    recovered = writer.recover(identity)
    assert recovered["revoked"] is True
    assert recovered["exclusion_generation"] == receipt.generation


def test_ar02_divergence_before_revocation_blocks_reads(env):
    ledger, writer, _, identity, ticket, _ = env
    h = writer.read_head(identity)
    writer.update_authority(identity, h, source_revision="r2",
                            consent_generation=2, exclusion_generation=0)
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(ticket, auth(), operation="use")


def test_failure_in_ar02_propagation_retains_sqlite_tombstone(env, monkeypatch):
    ledger, writer, boundary, identity, ticket, _ = env
    def interrupted(*args, **kwargs):
        raise FenceError("simulated power loss between durable & AR02")
    monkeypatch.setattr(writer, "update_authority", interrupted)
    receipt = ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    assert receipt.ar02_synced is False
    restarted = DurableMemoryExclusion(DurableWriterV1(writer.path),
                                       boundary, identity)
    with pytest.raises(DurableMemoryDenied):
        restarted.consume(ticket, auth(), operation="read")


def test_sqlite_receipt_update_trigger_rejects_tamper(env):
    ledger, writer, _, _, _, _ = env
    with (sqlite3.connect(writer.path) as conn,
          pytest.raises(sqlite3.DatabaseError, match="append-only")):
        conn.execute("UPDATE m06_receipts SET kind='FAKE' WHERE seq=1")


def test_sqlite_receipt_delete_trigger_rejects_tamper(env):
    ledger, writer, _, _, _, _ = env
    with (sqlite3.connect(writer.path) as conn,
          pytest.raises(sqlite3.DatabaseError, match="append-only")):
        conn.execute("DELETE FROM m06_receipts WHERE seq=1")


def test_sqlite_control_row_drift_detected(env):
    ledger, writer, _, _, _, _ = env
    with sqlite3.connect(writer.path) as conn:
        conn.execute("UPDATE m06_control SET state='TOMBSTONED' WHERE memory='mem'")
    with pytest.raises(DurableMemoryDenied, match="CONTROL_HEAD_MISMATCH"):
        ledger.admit("mem", auth(), expected_generation=0)


def test_sqlite_control_metadata_drift_detected(env):
    ledger, writer, _, _, _, _ = env
    with sqlite3.connect(writer.path) as conn:
        conn.execute("UPDATE m06_control SET source_pin='fake' WHERE memory='mem'")
    with pytest.raises(DurableMemoryDenied, match="CONTROL_METADATA_DRIFT"):
        ledger.admit("mem", auth(), expected_generation=0)


def test_mock_auth_cannot_switch_tenant(env):
    ledger, _, _, _, ticket, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.consume(replace(ticket, tenant="tenant-b"), auth(), operation="read")


def test_proposal_must_be_independently_accepted_before_registration(env):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied, match="NOT_BOUNDARY_ACCEPTED"):
        ledger.register_reviewed(replace(env[5], reviewer_ref="forged"),
                                 auth(), consent_generation=2, source_pin="source-id")


def test_no_auto_second_registration(env):
    ledger, _, _, _, _, accepted = env
    with pytest.raises(DurableMemoryDenied, match="REGISTER_ONCE_ONLY"):
        ledger.register_reviewed(accepted, auth(), consent_generation=2,
                                 source_pin="source-id")


def test_no_admission_of_unregistered_memory(env):
    ledger, _, _, _, _, _ = env
    with pytest.raises(DurableMemoryDenied):
        ledger.admit("another-memory", auth(), expected_generation=0)


def test_wrong_ar02_tenant_writer_identity_fails(env):
    _, writer, boundary, _, _, _ = env
    with pytest.raises(FenceError):
        DurableMemoryExclusion(writer, boundary,
                               RunIdentity("other-tenant", "run", "task", 1,
                                           "principal"))


def plan_for(writer, identity, *, purpose="research", pin="source-id", revision="r1"):
    return AuthorizedReadPlan(
        "AR03_LOCAL_PLAN", EffectiveActor("subject-a", "principal", "tenant-a", None, ()),
        ScopeSet("tenant-a", "resource", purpose, frozenset({"read", "cite"})),
        NativeCitationPinV1("NativeCitationPin/v1", "mock-provider", "mock-acct",
                            "resource", pin, revision, D, ()),
        RunCheckpointV1("AR02CheckpointPin/v1", "task", "run",
                        writer.read_head(identity).seq, writer.read_head(identity).digest),
        "fixture-issuer", "fixture-jti", 100, True, True,
    )


def test_ar03_local_plan_citation_eligibility_not_native_publish(env):
    ledger, writer, _, identity, ticket, _ = env
    assert ledger.fixture_citation_eligible(plan_for(writer, identity), ticket, auth())


def test_revocation_after_ar03_plan_revokes_citation_eligibility(env):
    ledger, writer, _, identity, ticket, _ = env
    original_grant = plan_for(writer, identity)
    assert ledger.fixture_citation_eligible(original_grant, ticket, auth())
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    assert ledger.fixture_citation_eligible(original_grant, ticket, auth()) is False


@pytest.mark.parametrize("change", [
    {"purpose": "ads"}, {"pin": "wrong"}, {"revision": "r2"},
])
def test_ar03_plan_pin_scope_mismatch_is_not_eligible(env, change):
    ledger, writer, _, identity, ticket, _ = env
    assert ledger.fixture_citation_eligible(plan_for(writer, identity, **change),
                                            ticket, auth()) is False


def test_concurrent_revocation_read_linearized_or_stale(env):
    ledger, _, _, _, ticket, _ = env
    ready = Event()
    resume = Event()
    def reader():
        ready.set()
        assert resume.wait(3)
        with pytest.raises(DurableMemoryDenied):
            ledger.consume(ticket, auth(), operation="checkpoint")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(reader)
        assert ready.wait(3)
        ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
        resume.set()
        future.result(timeout=3)


def test_no_physical_purge_on_any_local_success(env):
    ledger, writer, _, _, _, _ = env
    assert PASS == "AR06_LOCAL_DURABLE_EXCLUSION_PASS"
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    with sqlite3.connect(writer.path) as conn:
        payload = conn.execute(
            "SELECT payload FROM m06_receipts WHERE kind='REVOKE'"
        ).fetchone()[0]
    assert '"actual_physical_purge":false' in payload
    assert '"external_erase_receipt":null' in payload

class IndependentSourceFixture:
    """Explicit in-process K03V mock. Never an IdP, ACL provider or real grant."""

    def __init__(self, checkpoint):
        self.checkpoint = checkpoint
        self.key = TrustedIssuerKey("fixture-issuer", "key", "aud", "TEST", 1)
        self.used = set()
        self.claim = VerifiedAuthorityClaim(
            "fixture-issuer", "key", "aud", "TEST", 1, 1, 1, 80,
            "fixture-read-jti",
            EffectiveActor("subject-a", "principal", "tenant-a",
                           "subject-a", ("subject-a", "principal")),
            ScopeSet("tenant-a", "resource", "research",
                     frozenset({"read", "cite"})),
            "task", "run", checkpoint.sequence, checkpoint.head_sha256,
            "fixture-provider", "acct", "source-id", "r1", D,
            "consent1", 0, 2, 0,
        )
        self.observation = VerifiedSourceObservation(
            "fixture-provider", "acct", "tenant-a", "resource", "source-id",
            "r1", SOURCE_BYTES, frozenset({"principal"}),
            frozenset({"research"}), frozenset({"read", "cite"}),
            "consent1", True, 0, 2, 0, 9, 80,
        )

    def trusted_now(self):
        return 10

    def verify_authority(self, opaque_assertion, trusted_key):
        if opaque_assertion == b"fixture-authority" and trusted_key == self.key:
            return self.claim
        return None

    def observe_source(self, pin):
        return self.observation

    def checkpoint_is_current(self, checkpoint):
        return self.checkpoint == checkpoint

    def reserve_once(self, issuer, jti, checkpoint):
        key = (issuer, jti, checkpoint.head_sha256)
        if key in self.used or not self.checkpoint_is_current(checkpoint):
            return False
        self.used.add(key)
        return True

    def has_reservation(self, issuer, jti, checkpoint):
        return (issuer, jti, checkpoint.head_sha256) in self.used


def independent_ar03(env):
    _, writer, _, identity, _, _ = env
    head = writer.read_head(identity)
    checkpoint = RunCheckpointV1(CHECKPOINT_VERSION, "task", "run",
                                 head.seq, head.digest)
    mock = IndependentSourceFixture(checkpoint)
    consumer = VerifiedRightsConsumer(IssuerKeyRegistry((mock.key,)), mock)
    pin = NativeCitationPinV1(
        PIN_VERSION, "fixture-provider", "acct", "resource", "source-id", "r1",
        D, (ClaimSpanV1(0, len(SOURCE_BYTES), SOURCE_BYTES.decode()),),
    )
    intent = ReadIntent("task", "run", "subject-a", "principal",
                        "tenant-a", "research")
    evidence = SourceAuthorityEvidenceV1(
        SCHEMA_VERSION, "fixture-issuer", "key", "aud", b"fixture-authority",
    )
    return consumer, evidence, intent, pin, checkpoint


def test_real_existing_ar03_consumer_invoked_before_fixture_citation(env):
    ledger, _, _, _, ticket, _ = env
    consumer, evidence, intent, pin, checkpoint = independent_ar03(env)
    fresh, plan = ledger.authorize_fixture_read(
        consumer, "mem", auth(), expected_generation=0, evidence=evidence,
        intent=intent, pin=pin, checkpoint=checkpoint,
    )
    assert fresh == ticket and plan.citation_eligible
    assert ledger.fixture_citation_eligible(plan, ticket, auth())
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    assert not ledger.fixture_citation_eligible(plan, ticket, auth())


def test_revocation_preflight_prevents_even_ar03_grant_reservation(env):
    ledger, _, _, _, _, _ = env
    consumer, evidence, intent, pin, checkpoint = independent_ar03(env)
    ledger.revoke(revoke(), consent_generation=3, expected_generation=0)
    with pytest.raises(DurableMemoryDenied):
        ledger.authorize_fixture_read(
            consumer, "mem", auth(), expected_generation=0, evidence=evidence,
            intent=intent, pin=pin, checkpoint=checkpoint,
        )
    assert consumer._verifier.used == set()
