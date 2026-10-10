"""Adversarial in-process K04P permit sandbox tests. No external effects."""

from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    ActionRequest,
    ApprovalDecision,
    AuthoritySnapshot,
    CapabilityRule,
    Denied,
    DurableWriterReceipt,
    InProcessFixtureObserver,
    MockWriterPort,
    PermitSandboxV1,
    Registry,
)

NOW = 100


def fixture():
    rule = CapabilityRule(
        "cap.items", "1", "update", "/tenants/t1/items/", "fake-items-v1", 20
    )
    registry = Registry(
        "fixture-policy", frozenset({"fixture-approver"}),
        frozenset({"fixture-observer-issuer"}), "real-writer-unavailable",
        frozenset({"fake-items-v1"}), (rule,),
    )
    request = ActionRequest(
        "request-1", "run-1", "t1", "actor-1", "delegator-1", "cap.items", "1",
        "update", "/tenants/t1/items/one", "recipient-1", "a" * 64, "key-1", "1",
        7,
    )
    snapshot = AuthoritySnapshot(
        "run-1", "t1", "actor-1", "delegator-1", "worker-1", 7, 200, 200,
        3, 0, "head-123", 15, "fixture-policy",
    )
    sandbox = PermitSandboxV1(registry, MockWriterPort())
    return sandbox, registry, request, snapshot


def approve(request: ActionRequest, snapshot: AuthoritySnapshot) -> ApprovalDecision:
    return ApprovalDecision(
        "approval-1", "fixture-approver", True, request.digest(), request.intent_version,
        request.run_id, request.tenant_id, request.lease_epoch,
        snapshot.consent_generation, snapshot.revocation_generation, 180,
    )


def prepared():
    sandbox, registry, request, snapshot = fixture()
    sandbox.request(request, snapshot, now=NOW)
    permit = sandbox.issue_permit(
        request.request_id, approve(request, snapshot), snapshot, now=NOW, quoted_cost=5,
    )
    return sandbox, registry, request, snapshot, permit


def claimed():
    sandbox, registry, request, snapshot, permit = prepared()
    claim = sandbox.freeze_claim(
        permit, snapshot, claim_id="claim-1", sender_id="worker-1",
        physical_attempt=1, now=NOW,
    )
    return sandbox, registry, request, snapshot, permit, claim


def simulated(effect="applied", receipt="fixture-provider-receipt"):
    sandbox, registry, request, snapshot, permit, claim = claimed()
    attempt = sandbox.simulate_fixture(
        claim, snapshot, now=NOW, adapter_id="fake-items-v1",
        synthetic_effect=effect, provider_receipt_id=receipt,
    )
    observer = InProcessFixtureObserver(
        "fixture-independent-observer", "fixture-observer-issuer", "fixture-read-grant"
    )
    return sandbox, registry, request, snapshot, permit, claim, attempt, observer


def test_positive_pure_fixture_pipeline():
    sandbox, _, request, _, permit, claim, attempt, observer = simulated()
    observation = observer.observe(claim, effect="applied")
    outcome = sandbox.reconcile_fixture(claim, attempt, observation)
    assert permit.intent_digest == request.digest()
    assert not claim.writer_receipt.durable_verified
    assert claim.writer_receipt.outbox_ack is None
    assert attempt.status == "SIMULATED_NOT_DISPATCHED"
    assert outcome.state == "CONFIRMED_APPLIED_FIXTURE"
    assert not outcome.terminal_authorized
    assert outcome.provider_calls == 0
    assert sandbox.aggregate((outcome,)) == "ALL_APPLIED_FIXTURE_ONLY"


def test_compile_rejects_enabled_features():
    _, registry, _, _ = fixture()
    for change in ({"feature_enabled": True}, {"real_dispatch_authorized": True}):
        with pytest.raises(Denied, match="FEATURE_MUST_REMAIN_OFF"):
            PermitSandboxV1(replace(registry, **change), MockWriterPort())


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "send"},
        {"capability_id": "cap.something-else"},
        {"capability_version": "2"},
    ],
)
def test_unmapped_operation_denied(change):
    sandbox, _, request, snapshot = fixture()
    with pytest.raises(Denied, match="UNMAPPED_OPERATION"):
        sandbox.request(replace(request, **change), snapshot, now=NOW)


@pytest.mark.parametrize(
    "path",
    [
        "/tenants/t1/items/../outside",
        "/tenants/t1/items/./two",
        "/tenants/t1/items//two",
        "/tenants/t1/items/%2e%2e/secret",
        "/tenants/t1/items/two\\three",
        "/tenants/t2/items/one",
        "/tenants/t1/items/",
        "/tenants/t1/items/é",
    ],
)
def test_resource_escapes_denied(path):
    sandbox, _, request, snapshot = fixture()
    with pytest.raises(Denied, match="RESOURCE_SCOPE_ESCAPE"):
        sandbox.request(replace(request, resource_id=path), snapshot, now=NOW)


@pytest.mark.parametrize(
    "req_patch,snap_patch,code",
    [
        ({"actor_id": "someone-else"}, {}, "WRONG_EFFECTIVE_PRINCIPAL"),
        ({"delegated_by": None}, {}, "WRONG_EFFECTIVE_PRINCIPAL"),
        ({"tenant_id": "t2"}, {}, "WRONG_EFFECTIVE_PRINCIPAL"),
        ({"run_id": "run-2"}, {}, "WRONG_EFFECTIVE_PRINCIPAL"),
        ({"lease_epoch": 8}, {}, "LEASE_STALE"),
        ({}, {"lease_until": 100}, "LEASE_STALE"),
        ({}, {"consent_until": 100}, "CONSENT_REVOKED_OR_EXPIRED"),
        ({}, {"revocation_generation": 1}, "CONSENT_REVOKED_OR_EXPIRED"),
        ({}, {"budget_available": 0}, "CONSENT_OR_BUDGET_MISSING"),
        ({}, {"consent_generation": 0}, "CONSENT_OR_BUDGET_MISSING"),
        ({}, {"issuer": "forged"}, "POLICY_ISSUER"),
        ({}, {"head_hash": ""}, "HEAD_MISSING"),
    ],
)
def test_snapshot_fail_closed(req_patch, snap_patch, code):
    sandbox, _, request, snapshot = fixture()
    with pytest.raises(Denied, match=code):
        sandbox.request(
            replace(request, **req_patch), replace(snapshot, **snap_patch), now=NOW,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"arguments_digest": ""},
        {"recipient_id": ""},
        {"idempotency_key": ""},
        {"intent_version": ""},
    ],
)
def test_invalid_intent_request(change):
    sandbox, _, request, snapshot = fixture()
    with pytest.raises(Denied, match="INVALID_INTENT"):
        sandbox.request(replace(request, **change), snapshot, now=NOW)


def test_same_request_id_exact_replay_is_digest_stable_but_no_resend():
    sandbox, _, request, snapshot = fixture()
    a = sandbox.request(request, snapshot, now=NOW)
    assert sandbox.request(request, snapshot, now=NOW) == a
    with pytest.raises(Denied, match="REQUEST_CONFLICT"):
        sandbox.request(replace(request, arguments_digest="b" * 64), snapshot, now=NOW)


def test_reused_idempotency_key_different_request_id():
    sandbox, _, request, snapshot = fixture()
    sandbox.request(request, snapshot, now=NOW)
    with pytest.raises(Denied, match="REUSED_IDEMPOTENCY_KEY"):
        sandbox.request(replace(request, request_id="another"), snapshot, now=NOW)


@pytest.mark.parametrize(
    "approval_patch,snapshot_patch,quoted_cost,code",
    [
        ({"issuer": "forged"}, {}, 5, "UNTRUSTED_OR_REUSED_APPROVAL"),
        ({"approved": False}, {}, 5, "UNTRUSTED_OR_REUSED_APPROVAL"),
        ({"intent_digest": "deadbeef"}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({"intent_version": "2"}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({"run_id": "another"}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({"tenant_id": "another"}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({"lease_epoch": 8}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({"consent_generation": 2}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({"expires_at": 99}, {}, 5, "APPROVAL_BINDING_OR_EXPIRY"),
        ({}, {"revocation_generation": 1}, 5, "CONSENT_REVOKED_OR_EXPIRED"),
        ({}, {"consent_until": 99}, 5, "CONSENT_REVOKED_OR_EXPIRED"),
        ({}, {"lease_epoch": 8}, 5, "LEASE_STALE"),
        ({}, {}, 0, "BUDGET_DENIED"),
        ({}, {}, 21, "BUDGET_DENIED"),
        ({}, {}, 16, "BUDGET_DENIED"),
    ],
)
def test_approval_and_budget_fail_closed(approval_patch, snapshot_patch, quoted_cost, code):
    sandbox, _, request, snapshot = fixture()
    sandbox.request(request, snapshot, now=NOW)
    with pytest.raises(Denied, match=code):
        sandbox.issue_permit(
            request.request_id,
            replace(approve(request, snapshot), **approval_patch),
            replace(snapshot, **snapshot_patch),
            now=NOW, quoted_cost=quoted_cost,
        )


def test_changed_args_or_recipient_cannot_use_old_approval():
    sandbox, _, request, snapshot = fixture()
    sandbox.request(request, snapshot, now=NOW)
    decision = approve(request, snapshot)
    assert decision.intent_digest != replace(request, arguments_digest="b" * 64).digest()
    assert decision.intent_digest != replace(request, recipient_id="recipient-2").digest()


def test_approval_cannot_be_consumed_twice():
    sandbox, _, request, snapshot, _ = prepared()
    with pytest.raises(Denied, match="UNTRUSTED_OR_REUSED_APPROVAL"):
        sandbox.issue_permit(
            request.request_id, approve(request, snapshot), snapshot, now=NOW,
            quoted_cost=5,
        )


def test_missing_request_fails():
    sandbox, _, request, snapshot = fixture()
    with pytest.raises(Denied, match="UNKNOWN_REQUEST"):
        sandbox.issue_permit(
            "missing", approve(request, snapshot), snapshot, now=NOW, quoted_cost=5
        )


@pytest.mark.parametrize(
    "snap_patch,code",
    [
        ({"worker_id": "competing-worker"}, "SPLIT_BRAIN_WORKER"),
        ({"lease_epoch": 8}, "LEASE_STALE"),
        ({"lease_until": 99}, "LEASE_STALE"),
        ({"consent_until": 99}, "CONSENT_REVOKED_OR_EXPIRED"),
        ({"revocation_generation": 2}, "CONSENT_REVOKED_OR_EXPIRED"),
        ({"consent_generation": 4}, "PERMIT_STALE_OR_MUTATED"),
        ({"head_hash": "head-changed"}, "PERMIT_STALE_OR_MUTATED"),
    ],
)
def test_claim_rechecks_current_authority(snap_patch, code):
    sandbox, _, _, snapshot, permit = prepared()
    with pytest.raises(Denied, match=code):
        sandbox.freeze_claim(
            permit, replace(snapshot, **snap_patch), claim_id="claim",
            sender_id="worker-1", physical_attempt=1, now=NOW,
        )


def test_permit_tamper_denied():
    sandbox, _, _, snapshot, permit = prepared()
    for change in ({"intent_digest": "forged"}, {"approval_id": "new"}):
        with pytest.raises(Denied, match="PERMIT_STALE_OR_MUTATED"):
            sandbox.freeze_claim(
                replace(permit, **change), snapshot, claim_id="claim",
                sender_id="worker-1", physical_attempt=1, now=NOW,
            )


def test_claim_wrong_sender_denied():
    sandbox, _, _, snapshot, permit = prepared()
    with pytest.raises(Denied, match="SPLIT_BRAIN_WORKER"):
        sandbox.freeze_claim(
            permit, snapshot, claim_id="claim",
            sender_id="not-the-worker", physical_attempt=1, now=NOW,
        )


@pytest.mark.parametrize("attempt", [0, 2, 3])
def test_claim_physical_attempt_must_be_one(attempt):
    sandbox, _, _, snapshot, permit = prepared()
    with pytest.raises(Denied, match="DUPLICATE_OR_INVALID_CLAIM"):
        sandbox.freeze_claim(
            permit, snapshot, claim_id="claim", sender_id="worker-1",
            physical_attempt=attempt, now=NOW,
        )


def test_double_claim_or_racing_sender_fails():
    sandbox, _, _, snapshot, permit, _ = claimed()
    with pytest.raises(Denied, match="DUPLICATE_OR_INVALID_CLAIM"):
        sandbox.freeze_claim(
            permit, snapshot, claim_id="other", sender_id="worker-1",
            physical_attempt=1, now=NOW,
        )


class WrongReceiptPort:
    def prepare_claim(self, permit, claim_id):
        receipt = MockWriterPort().prepare_claim(permit, claim_id)
        return replace(receipt, tenant_id="wrong")


class BooleanPort:
    def prepare_claim(self, permit, claim_id):
        return True


@pytest.mark.parametrize("port,code", [
    (WrongReceiptPort(), "WRITER_RECEIPT_BINDING"),
    (BooleanPort(), "WRITER_RECEIPT_TYPE"),
])
def test_no_untyped_or_forged_writer_receipt(port, code):
    sandbox, registry, request, snapshot = fixture()
    sandbox = PermitSandboxV1(registry, port)
    sandbox.request(request, snapshot, now=NOW)
    permit = sandbox.issue_permit(
        request.request_id, approve(request, snapshot), snapshot, now=NOW, quoted_cost=5
    )
    with pytest.raises(Denied, match=code):
        sandbox.freeze_claim(
            permit, snapshot, claim_id="claim", sender_id="worker-1",
            physical_attempt=1, now=NOW,
        )


def test_t3_requires_authentic_durable_ack_even_in_mock():
    sandbox, _, _, snapshot, _, claim = claimed()
    with pytest.raises(Denied, match="NO_AUTHENTIC_DURABLE_OUTBOX_ACK"):
        sandbox.attempt_external(claim, snapshot, now=NOW)


class ForgedAckPort:
    def prepare_claim(self, permit, claim_id):
        return replace(
            MockWriterPort().prepare_claim(permit, claim_id),
            writer_issuer="real-writer-unavailable", outbox_ack="forged",
            durable_verified=True, mock_only=False,
        )


def test_even_forged_writer_ack_cannot_enable_real_dispatch():
    sandbox, registry, request, snapshot = fixture()
    sandbox = PermitSandboxV1(registry, ForgedAckPort())
    sandbox.request(request, snapshot, now=NOW)
    permit = sandbox.issue_permit(
        request.request_id, approve(request, snapshot), snapshot, now=NOW, quoted_cost=5
    )
    claim = sandbox.freeze_claim(
        permit, snapshot, claim_id="claim", sender_id="worker-1",
        physical_attempt=1, now=NOW,
    )
    with pytest.raises(Denied, match="REAL_DISPATCH_DISABLED"):
        sandbox.attempt_external(claim, snapshot, now=NOW)


def test_unknown_claim_never_t3():
    sandbox, _, _, snapshot, _, claim = claimed()
    with pytest.raises(Denied, match="UNKNOWN_OR_MUTATED_CLAIM"):
        sandbox.attempt_external(replace(claim, claim_id="not-present"), snapshot, now=NOW)


@pytest.mark.parametrize(
    "snap_patch,code",
    [
        ({"worker_id": "other"}, "SPLIT_BRAIN_WORKER"),
        ({"lease_epoch": 8}, "LEASE_STALE"),
        ({"consent_until": 100}, "CONSENT_REVOKED_OR_EXPIRED"),
        ({"revocation_generation": 1}, "CONSENT_REVOKED_OR_EXPIRED"),
        ({"head_hash": "new-head"}, "FENCE_OR_CONSENT_CHANGED"),
        ({"consent_generation": 4}, "FENCE_OR_CONSENT_CHANGED"),
    ],
)
def test_mock_attempt_current_lease_consent_and_head(snap_patch, code):
    sandbox, _, _, snapshot, _, claim = claimed()
    with pytest.raises(Denied, match=code):
        sandbox.simulate_fixture(
            claim, replace(snapshot, **snap_patch), now=NOW,
            adapter_id="fake-items-v1", synthetic_effect="applied",
        )


def test_unauthorized_fake_adapter_cannot_execute():
    sandbox, _, _, snapshot, _, claim = claimed()
    with pytest.raises(Denied, match="ADAPTER_NOT_ALLOWLISTED"):
        sandbox.simulate_fixture(
            claim, snapshot, now=NOW, adapter_id="shell", synthetic_effect="applied",
        )


def test_no_double_simulated_send():
    sandbox, _, _, snapshot, _, claim = claimed()
    sandbox.simulate_fixture(
        claim, snapshot, now=NOW, adapter_id="fake-items-v1", synthetic_effect="applied",
    )
    with pytest.raises(Denied, match="DOUBLE_SEND"):
        sandbox.simulate_fixture(
            claim, snapshot, now=NOW, adapter_id="fake-items-v1",
            synthetic_effect="applied",
        )


def test_crash_after_claim_missing_ack_no_t3_and_no_replay():
    sandbox, _, _, snapshot, permit, claim = claimed()
    assert claim.writer_receipt.outbox_ack is None
    with pytest.raises(Denied, match="NO_AUTHENTIC_DURABLE_OUTBOX_ACK"):
        sandbox.attempt_external(claim, snapshot, now=NOW)
    with pytest.raises(Denied, match="DUPLICATE_OR_INVALID_CLAIM"):
        sandbox.freeze_claim(
            permit, snapshot, claim_id="claim-again", sender_id="worker-1",
            physical_attempt=1, now=NOW,
        )


@pytest.mark.parametrize(
    "obs_patch,code",
    [
        ({"claim_id": "other"}, "EFFECT_BINDING"),
        ({"intent_digest": "forged"}, "EFFECT_BINDING"),
        ({"tenant_id": "another"}, "EFFECT_BINDING"),
        ({"resource_id": "/tenants/t2/items/x"}, "EFFECT_BINDING"),
        ({"observer_id": "fake-items-v1"}, "OBSERVER_NOT_INDEPENDENT_OR_GRANTED"),
        ({"observer_issuer": "executor"}, "OBSERVER_NOT_INDEPENDENT_OR_GRANTED"),
        ({"observer_grant_id": ""}, "OBSERVER_NOT_INDEPENDENT_OR_GRANTED"),
        ({"citation_ids": ("source-id-from-nowhere",)}, "SOURCE_CITATION_LAUNDERING"),
    ],
)
def test_observer_tamper_or_citation_laundering(obs_patch, code):
    sandbox, _, _, _, _, claim, attempt, observer = simulated()
    obs = replace(observer.observe(claim, effect="applied"), **obs_patch)
    with pytest.raises(Denied, match=code):
        sandbox.reconcile_fixture(claim, attempt, obs)


@pytest.mark.parametrize(
    "observed,complete,receipt,expected",
    [
        ("absent_uncertain", True, "receipt", "UNKNOWN_EFFECT"),
        ("not_applied", False, "receipt", "UNKNOWN_EFFECT"),
        ("applied", False, "receipt", "UNKNOWN_EFFECT"),
        ("applied", True, None, "UNKNOWN_EFFECT"),
        ("not_applied", True, None, "UNKNOWN_EFFECT"),
        ("not_applied", True, "receipt", "CONFIRMED_NOT_APPLIED_FIXTURE"),
        ("applied", True, "receipt", "CONFIRMED_APPLIED_FIXTURE"),
    ],
)
def test_independent_observation_visibility_and_ack_loss(observed, complete, receipt, expected):
    sandbox, _, _, _, _, claim, attempt, observer = simulated(
        "unknown", receipt,
    )
    outcome = sandbox.reconcile_fixture(
        claim, attempt, observer.observe(claim, effect=observed, visibility_complete=complete),
    )
    assert outcome.state == expected
    assert outcome.terminal_authorized is False
    assert outcome.provider_calls == 0


def test_executor_success_cannot_attest_without_observer():
    sandbox, _, _, _, _, claim, attempt, observer = simulated("applied")
    with pytest.raises(Denied, match="EFFECT_BINDING"):
        sandbox.reconcile_fixture(
            claim, replace(attempt, intent_digest="tampered"),
            observer.observe(claim, effect="applied"),
        )
    assert sandbox.aggregate(()) == "INCOMPLETE_OR_UNKNOWN_FIXTURE"


def test_reconcile_once_and_no_blind_retries():
    sandbox, _, _, _, _, claim, attempt, observer = simulated("unknown", None)
    outcome = sandbox.reconcile_fixture(
        claim, attempt, observer.observe(claim, effect="absent_uncertain"),
    )
    assert outcome.state == "UNKNOWN_EFFECT"
    with pytest.raises(Denied, match="RECONCILIATION_REPLAY"):
        sandbox.reconcile_fixture(
            claim, attempt, observer.observe(claim, effect="not_applied"),
        )
    with pytest.raises(Denied, match="NO_AUTHENTIC_PROVIDER_IDEMPOTENCY"):
        sandbox.retry(outcome)


def test_partial_actions_cannot_be_marked_success():
    sandbox, _, _, _, _, claim, attempt, observer = simulated()
    applied = sandbox.reconcile_fixture(claim, attempt, observer.observe(claim, effect="applied"))
    unknown = replace(applied, state="UNKNOWN_EFFECT")
    assert sandbox.aggregate((applied, unknown)) == "INCOMPLETE_OR_UNKNOWN_FIXTURE"


def test_no_source_citations_are_minted_by_fixture():
    sandbox, _, _, _, _, claim, attempt, observer = simulated()
    with pytest.raises(Denied, match="SOURCE_CITATION_LAUNDERING"):
        sandbox.reconcile_fixture(
            claim, attempt,
            observer.observe(claim, effect="applied", citation_ids=("fake:line1",)),
        )


def test_writer_receipt_type_explicitly_nondurable():
    _, _, _, _, _, claim = claimed()
    assert isinstance(claim.writer_receipt, DurableWriterReceipt)
    assert not claim.writer_receipt.durable_verified
    assert claim.writer_receipt.mock_only
    assert not claim.writer_receipt.outbox_ack
