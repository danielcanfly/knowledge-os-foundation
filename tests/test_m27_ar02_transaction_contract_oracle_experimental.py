"""T02 inert single-writer protocol oracle; no database, Provider or dispatch."""
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_ar05_reconciled_vertical_experimental import (
    complete_mock_loop,
    prepare_mock_loop,
)
from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel
from knowledge_engine.m27_ar02_transaction_contract_oracle_experimental import (
    CRASH_POINTS,
    CrashPoint,
    DurabilityObligation,
    OutboxClaimContract,
    ReconciliationObligation,
    TransactionIntentContract,
    WriterSnapshotFixture,
    assess_contract,
    assess_crash,
    minimal_durable_writer_api,
)


def fixture():
    intent = TransactionIntentContract(
        tenant_id="tenant-fixture", run_id="run-fixture", task_id="task-fixture",
        task_version=1, attempt=1, intent_id="intent-fixture",
        intent_digest="d" * 64, approval_id="approval-fixture",
        expected_head=5, lease_epoch=1, reserve_id="reserve-fixture",
        reserved_microunits=3, charge_id="charge-fixture",
        charged_microunits=2, claim_id="claim-fixture",
        idempotency_key="idempotency-fixture", consent_generation=4,
        exclusion_generation=2, source_revision="source-rev-1", expires_at=200,
    )
    state = WriterSnapshotFixture(
        tenant_id="tenant-fixture", run_id="run-fixture",
        task_id="task-fixture", task_version=1, head=5,
        head_hash="a" * 64, epoch=1, budget_microunits=10,
        spent_microunits=2, reservations=(("reserve-other", 1),),
        charges=(("charge-fixture", "reserve-fixture", 2),),
        intents=(("intent-fixture", "d" * 64, "approval-fixture"),),
        claims=(("claim-fixture", "intent-fixture", 1, "idempotency-fixture"),),
        unknown_effects=(), outcome_phase="T4_APPLIED",
        source_revision="source-rev-1", consent_generation=4,
        exclusion_generation=2, source_revoked=False, terminal=False,
    )
    claim = OutboxClaimContract(
        claim_id="claim-fixture", intent_id="intent-fixture",
        intent_digest="d" * 64, expected_head=5, lease_epoch=1,
        idempotency_key="idempotency-fixture", intent_commit_ack=True,
        claim_commit_ack=True, attempt_marked_in_journal=True,
    )
    proof = ReconciliationObligation(
        tenant_id="tenant-fixture", run_id="run-fixture",
        task_id="task-fixture", task_version=1,
        observation_id="observation-fixture", observed_status="CONFIRMED_APPLIED",
        independent_observer=True, verified_head=5,
        verified_head_hash="a" * 64, lease_epoch=1, expires_at=150,
        binding_intent_id="intent-fixture", original_t1_digest="d" * 64,
    )
    return intent, state, claim, proof


def eval_change(which, **changes):
    objects = list(fixture())
    idx = {"intent": 0, "state": 1, "claim": 2, "proof": 3}[which]
    objects[idx] = replace(objects[idx], **changes)
    return assess_contract(*objects, now=100)


def test_full_mock_policy_contract_only_passes_without_claiming_durability():
    decision = assess_contract(*fixture(), now=100)
    assert decision.mock_policy_contract_pass
    assert not decision.issues
    assert decision.durability_obligations == DurabilityObligation()
    assert decision.durable_verified is False
    assert decision.backend_writer_present is False
    assert decision.provider_dispatch_authorized is False
    assert decision.AR02_STAGE_DONE is False
    assert decision.requires_independent_t4


@pytest.mark.parametrize(("which", "change", "issue"), [
    ("intent", {"tenant_id": "evil"}, "TENANT_RUN_BINDING"),
    ("state", {"tenant_id": "evil"}, "TENANT_RUN_BINDING"),
    ("proof", {"tenant_id": "evil"}, "TENANT_RUN_BINDING"),
    ("intent", {"run_id": "wrong"}, "TENANT_RUN_BINDING"),
    ("state", {"task_version": 2}, "TASK_VERSION_MISMATCH"),
    ("proof", {"task_version": 2}, "TASK_VERSION_MISMATCH"),
    ("intent", {"task_id": "wrong"}, "TASK_ID_MISMATCH"),
    ("intent", {"attempt": 0}, "INVALID_ATTEMPT"),
    ("intent", {"expected_head": 4}, "STALE_CAS_HEAD"),
    ("state", {"epoch": 2}, "STALE_LEASE_EPOCH"),
    ("claim", {"lease_epoch": 2}, "STALE_LEASE_EPOCH"),
    ("claim", {"expected_head": 4}, "STALE_CAS_HEAD"),
    ("intent", {"intent_digest": "0" * 64}, "INTENT_DIGEST_MISMATCH"),
    ("claim", {"intent_digest": "0" * 64}, "INTENT_DIGEST_MISMATCH"),
    ("state", {"head_hash": "b" * 64}, "FORGED_OR_STALE_HEAD"),
    ("proof", {"verified_head_hash": "0" * 64}, "FORGED_OR_STALE_HEAD"),
    ("proof", {"verified_head": 4}, "FORGED_OR_STALE_HEAD"),
    ("proof", {"independent_observer": False}, "UNVERIFIED_T4"),
    ("proof", {"expires_at": 99}, "EXPIRED_RECONCILIATION_PROOF"),
    ("intent", {"expires_at": 99}, "EXPIRED_INTENT"),
    ("state", {"source_revoked": True}, "REVOKED_SOURCE"),
    ("state", {"exclusion_generation": 3}, "EXCLUSION_DRIFT"),
    ("state", {"consent_generation": 5}, "CONSENT_GENERATION_DRIFT"),
    ("state", {"source_revision": "revision-2"}, "SOURCE_REVISION_DRIFT"),
    ("state", {"terminal": True}, "TERMINAL_IMMUTABLE"),
    ("state", {"outcome_phase": "T3_UNKNOWN_EFFECT"}, "UNKNOWN_EFFECT_NOT_T4"),
    ("state", {"outcome_phase": "T4_NOT_APPLIED"}, "NO_SUCCESS_WITHOUT_APPLIED"),
    ("proof", {"observed_status": "CONFIRMED_NOT_APPLIED"}, "NO_SUCCESS_WITHOUT_APPLIED"),
    ("claim", {"claim_commit_ack": False}, "MISSING_DURABLE_ACK"),
    ("claim", {"intent_commit_ack": False}, "MISSING_DURABLE_ACK"),
    ("claim", {"attempt_marked_in_journal": False}, "NO_COMMITTED_ATTEMPT_MARKER"),
    ("state", {"charges": ()}, "MISSING_OR_CONFLICTING_CHARGE"),
    ("state", {"intents": ()}, "MISSING_COMMITTED_INTENT"),
    ("state", {"claims": ()}, "MISSING_COMMITTED_CLAIM"),
    ("state", {"unknown_effects": ("intent-fixture",)}, "UNKNOWN_EFFECT_NOT_T4"),
    ("intent", {"reserved_microunits": 1}, "CHARGE_EXCEEDS_RESERVATION"),
    ("state", {"budget_microunits": 2}, "BUDGET_OVERCOMMITTED"),
    ("intent", {"charged_microunits": -1}, "INVALID_COST"),
    ("intent", {"charged_microunits": None}, "INVALID_COST"),
    ("claim", {"idempotency_key": "other"}, "CLAIM_BINDING_MISMATCH"),
    ("claim", {"claim_id": "replay"}, "CLAIM_BINDING_MISMATCH"),
])
def test_adversarial_contract_denies(which, change, issue):
    result = eval_change(which, **change)
    assert not result.mock_policy_contract_pass
    assert issue in result.issues
    assert result.provider_dispatch_authorized is False


def test_concurrent_cas_single_winner_real_kernel_fixture():
    kernel = Kernel(budget=4)
    kernel.create("run", "tenant")
    kernel.reserve("run", "tenant", 0, 1, "r1", 3)
    with pytest.raises(Denied, match="stale"):
        kernel.reserve("run", "tenant", 0, 1, "r2", 1)
    assert kernel.read("run", "tenant")["head"] == 1
    assert kernel.read("run", "tenant")["reserved"] == {"r1": 3}


def test_overlapping_reservation_budget_denied_on_fresh_head():
    kernel = Kernel(budget=4)
    kernel.create("run", "tenant")
    kernel.reserve("run", "tenant", 0, 1, "r1", 3)
    with pytest.raises(Denied, match="reservation"):
        kernel.reserve("run", "tenant", 1, 1, "r2", 2)
    assert kernel.read("run", "tenant")["spent"] == 0


def test_takeover_fences_stale_epoch():
    kernel = Kernel(budget=4)
    kernel.create("run", "tenant")
    kernel.takeover("run", "tenant", 0)
    with pytest.raises(Denied, match="stale"):
        kernel.reserve("run", "tenant", 1, 1, "r1", 1)
    assert kernel.read("run", "tenant")["epoch"] == 2


def test_charge_replay_does_not_charge_twice():
    kernel = Kernel(budget=5)
    kernel.create("run", "tenant")
    kernel.reserve("run", "tenant", 0, 1, "r", 3)
    assert kernel.charge("run", "tenant", 1, 1, "r", "c", 2)
    assert not kernel.charge("run", "tenant", 2, 1, "r", "c", 2)
    assert kernel.read("run", "tenant")["spent"] == 2


def test_conflicting_charge_replay_denied():
    kernel = Kernel(budget=5)
    kernel.create("run", "tenant")
    kernel.reserve("run", "tenant", 0, 1, "r", 3)
    kernel.charge("run", "tenant", 1, 1, "r", "c", 2)
    with pytest.raises(Denied, match="charge id conflict"):
        kernel.charge("run", "tenant", 2, 1, "r", "c", 3)


def test_duplicate_claim_replay_is_rejected():
    _, state, claim, proof = fixture()
    intent, *_ = fixture()
    repeated = replace(state, claims=state.claims + state.claims)
    assert "DUPLICATE_CLAIM" in assess_contract(
        intent, repeated, claim, proof, now=100,
    ).issues


def test_duplicate_charge_replay_in_snapshot_rejected():
    intent, state, claim, proof = fixture()
    repeated = replace(state, charges=state.charges + state.charges)
    assert "DUPLICATE_CHARGE" in assess_contract(
        intent, repeated, claim, proof, now=100,
    ).issues


@pytest.mark.parametrize("point", CRASH_POINTS)
def test_each_crash_point_never_implies_dispatch_or_double_charge(point: CrashPoint):
    result = assess_crash(point, original_charge_count=1)
    assert not result.may_dispatch
    assert not result.double_charge_allowed
    assert not result.durable_verified
    assert not result.backend_writer_present
    assert not result.provider_dispatch_authorized
    assert not result.AR02_STAGE_DONE
    assert result.next_step


def test_ack_loss_before_physical_send_is_hard_denial():
    result = assess_crash("LOST_COMMIT_ACK_BEFORE_DISPATCH")
    assert result.next_step == "DENY_AND_REVALIDATE_DURABLE_COMMIT"
    assert not result.may_dispatch


def test_remote_effect_before_observer_is_unknown_not_blind_retry():
    result = assess_crash("POST_REMOTE_EFFECT_PRE_OBSERVER")
    assert result.effect_state == "T3_UNKNOWN_EFFECT"
    assert result.next_step == "INDEPENDENT_T4_RECONCILIATION_NO_RETRY"


def test_observer_after_crash_requires_new_current_head_and_proof():
    result = assess_crash("AFTER_OBSERVER_BEFORE_TERMINAL")
    assert result.next_step == "REVERIFY_T4_CURRENT_HEAD_THEN_TERMINAL_CAS"
    assert not result.may_dispatch


def test_unknown_effect_provider_no_deduplication_assumption():
    intent, state, claim, proof = fixture()
    uncertain = replace(state, outcome_phase="T3_UNKNOWN_EFFECT",
                        unknown_effects=("intent-fixture",))
    result = assess_contract(intent, uncertain, claim, proof, now=100)
    assert "UNKNOWN_EFFECT_NOT_T4" in result.issues
    assert not result.mock_policy_contract_pass
    assert not result.provider_dispatch_authorized


def test_v2_memory_restart_falls_back_to_t3_not_persisted_terminal():
    done, committed_terminal, _ = complete_mock_loop()
    assert committed_terminal.head_seq == 7
    assert done.v2.terminal_receipt == committed_terminal
    legacy = done.kernel.read("run-fixture", "tenant-fixture")
    assert legacy["terminal"] is False
    assert legacy["unknown"] == {"intent-fixture"}
    replayed_from_same_t3_fixture = prepare_mock_loop()
    assert replayed_from_same_t3_fixture.v2.head == 5
    assert replayed_from_same_t3_fixture.v2.terminal_receipt is None
    assert replayed_from_same_t3_fixture.kernel.read(
        "run-fixture", "tenant-fixture",
    ) == legacy
    assert replayed_from_same_t3_fixture.kernel.network_requests == 0
    # Deterministic in-memory fixture recreation, NOT actual crash-durable recovery.


def test_contract_requires_atomic_authoritative_storage_api_not_sqlite():
    names = minimal_durable_writer_api()
    assert "begin_serializable_run_transaction" in names
    assert "compare_and_append_event_head" in names
    assert "atomic_reserve_charge_intent_claim" in names
    assert "commit_t4_and_terminal_with_head_cas" in names
    assert "recover_pending_outbox_without_blind_redispatch" in names
    assert "verify_durable_commit_ack_before_dispatch" in names
    assert all("sqlite" not in name.lower() for name in names)
