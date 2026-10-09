from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine.m27_ar04_safe_action_experimental import (
    ActionDenied,
    ActionIntent,
    ApprovalFixture,
    InertSafeActionBoundary,
    ObserverEvidence,
    PolicyFixture,
)

NOW = 100
DIGEST = "a" * 64


def intent(**changes: object) -> ActionIntent:
    base = ActionIntent(
        intent_id="intent-1",
        run_id="run-1",
        tenant_id="tenant-a",
        principal_id="principal-a",
        delegated_by="owner-a",
        capability_id="cap.write",
        capability_version="1",
        operation="update",
        resource_id="resource-a",
        arguments_ref="opaque:args",
        arguments_digest=DIGEST,
        idempotency_key="logical-action-1",
        side_effect="reversible_write",
        approval_id="approval-1",
        requested_at=90,
        expires_at=200,
        policy_version="policy-v1",
        lease_epoch=7,
        attempt=1,
    )
    return replace(base, **changes)


def policy(**changes: object) -> PolicyFixture:
    base = PolicyFixture(
        issuer="policy-root",
        tenant_id="tenant-a",
        principal_id="principal-a",
        delegated_by="owner-a",
        auth_expires_at=200,
        allowed_capabilities=frozenset({"cap.write"}),
        allowed_resources=frozenset({"resource-a"}),
        lease_epoch=7,
        budget_cap_microunits=5,
        price_microunits=5,
    )
    return replace(base, **changes)


def boundary() -> InertSafeActionBoundary:
    return InertSafeActionBoundary(
        trusted_policy_issuer="policy-root",
        trusted_approval_issuers=frozenset({"approval-root"}),
        trusted_observers=frozenset({"observer-root"}),
        trusted_verifier_keys=frozenset({"verifier-key"}),
    )


def approval(value: ActionIntent, **changes: object) -> ApprovalFixture:
    base = ApprovalFixture(
        approval_id="approval-1",
        intent_digest=value.digest(),
        tenant_id="tenant-a",
        approver_principal="human-approver",
        issuer="approval-root",
        expires_at=200,
    )
    return replace(base, **changes)


def registered() -> tuple[InertSafeActionBoundary, ActionIntent]:
    service = boundary()
    value = intent()
    service.register_intent(command_id="command-1", intent=value, policy=policy(), now=NOW)
    return service, value


def crossed() -> tuple[InertSafeActionBoundary, ActionIntent]:
    service, value = registered()
    service.claim_dispatch(
        intent_id=value.intent_id,
        claim_id="claim-1",
        approval=approval(value),
        expected_epoch=7,
        physical_attempt=1,
        now=NOW,
    )
    service.cross_send_boundary(claim_id="claim-1", current_epoch=7)
    return service, value


@pytest.mark.parametrize(
    ("changed_intent", "changed_policy", "code"),
    [
        ({"tenant_id": "tenant-b"}, {}, "T1_IDENTITY_OR_DELEGATION_MISMATCH"),
        ({"delegated_by": "intruder"}, {}, "T1_IDENTITY_OR_DELEGATION_MISMATCH"),
        ({"resource_id": "resource-b"}, {}, "T1_RESOURCE_SCOPE_DENIED"),
        ({"lease_epoch": 6}, {}, "T1_STALE_EPOCH"),
        ({}, {"price_microunits": None}, "T1_PRICE_UNKNOWN"),
        ({}, {"budget_cap_microunits": 0}, "T1_BUDGET_DENIED"),
    ],
)
def test_t1_fails_closed_before_any_provider_call(
    changed_intent: dict[str, object],
    changed_policy: dict[str, object],
    code: str,
) -> None:
    service = boundary()
    with pytest.raises(ActionDenied, match=code):
        service.register_intent(
            command_id="command-1",
            intent=intent(**changed_intent),
            policy=policy(**changed_policy),
            now=NOW,
        )
    assert service.provider_calls == 0


def test_t1_ack_loss_is_idempotent_but_changed_digest_conflicts() -> None:
    service = boundary()
    value = intent()
    first = service.register_intent(
        command_id="command-1", intent=value, policy=policy(), now=NOW
    )
    assert service.register_intent(
        command_id="command-1", intent=value, policy=policy(), now=NOW
    ) is first
    with pytest.raises(ActionDenied, match="T1_COMMAND_DIGEST_CONFLICT"):
        service.register_intent(
            command_id="command-1",
            intent=replace(value, arguments_digest="b" * 64),
            policy=policy(),
            now=NOW,
        )


def test_t2_rejects_changed_digest_consumed_approval_and_reused_claim() -> None:
    service, value = registered()
    with pytest.raises(ActionDenied, match="T2_APPROVAL_DIGEST_MISMATCH"):
        service.claim_dispatch(
            intent_id=value.intent_id,
            claim_id="claim-bad",
            approval=approval(value, intent_digest="b" * 64),
            expected_epoch=7,
            physical_attempt=1,
            now=NOW,
        )
    service.claim_dispatch(
        intent_id=value.intent_id,
        claim_id="claim-1",
        approval=approval(value),
        expected_epoch=7,
        physical_attempt=1,
        now=NOW,
    )
    with pytest.raises(ActionDenied, match="T2_CLAIM_ALREADY_EXISTS"):
        service.claim_dispatch(
            intent_id=value.intent_id,
            claim_id="claim-1",
            approval=approval(value),
            expected_epoch=7,
            physical_attempt=2,
            now=NOW,
        )
    other = replace(value, intent_id="intent-2", idempotency_key="logical-action-2")
    service.register_intent(command_id="command-2", intent=other, policy=policy(), now=NOW)
    with pytest.raises(ActionDenied, match="T2_APPROVAL_CONSUMED"):
        service.claim_dispatch(
            intent_id=other.intent_id,
            claim_id="claim-2",
            approval=replace(approval(other), approval_id="approval-1"),
            expected_epoch=7,
            physical_attempt=1,
            now=NOW,
        )


def test_crash_cut_points_do_not_infer_effect_or_blind_retry() -> None:
    service, value = registered()
    assert service.recovery_effect(value.intent_id) == "NOT_DISPATCHED"
    service.claim_dispatch(
        intent_id=value.intent_id,
        claim_id="claim-1",
        approval=approval(value),
        expected_epoch=7,
        physical_attempt=1,
        now=NOW,
    )
    assert service.recovery_effect(value.intent_id) == "NOT_DISPATCHED"
    boundary_marker = service.cross_send_boundary(claim_id="claim-1", current_epoch=7)
    assert boundary_marker.effect == "POSSIBLY_SENT"
    assert service.recovery_effect(value.intent_id) == "UNKNOWN_EFFECT"
    with pytest.raises(ActionDenied, match="RETRY_EFFECT_NOT_NEGATIVELY_PROVEN"):
        service.authorize_retry(intent_id=value.intent_id, idempotency_mode="none")
    assert service.provider_calls == 0


def test_t3_rejects_stale_epoch_duplicate_and_cancel_races() -> None:
    service, value = registered()
    service.claim_dispatch(
        intent_id=value.intent_id,
        claim_id="claim-1",
        approval=approval(value),
        expected_epoch=7,
        physical_attempt=1,
        now=NOW,
    )
    with pytest.raises(ActionDenied, match="T3_STALE_EPOCH"):
        service.cross_send_boundary(claim_id="claim-1", current_epoch=8)
    service.cross_send_boundary(claim_id="claim-1", current_epoch=7)
    with pytest.raises(ActionDenied, match="T3_CLAIM_CONSUMED"):
        service.cross_send_boundary(claim_id="claim-1", current_epoch=7)
    assert service.cancel(value.intent_id).effect == "UNKNOWN_EFFECT"

    before, before_intent = registered()
    before.claim_dispatch(
        intent_id=before_intent.intent_id,
        claim_id="claim-before",
        approval=approval(before_intent),
        expected_epoch=7,
        physical_attempt=1,
        now=NOW,
    )
    assert before.cancel(before_intent.intent_id).effect == "NOT_DISPATCHED"
    with pytest.raises(ActionDenied, match="T3_CANCELLED"):
        before.cross_send_boundary(claim_id="claim-before", current_epoch=7)


def test_independent_observer_overrides_executor_echo_and_requires_strong_negative() -> None:
    service, value = crossed()
    contradiction = service.reconcile(
        evidence=ObserverEvidence(
            observer_id="observer-root",
            tenant_id="tenant-a",
            intent_id=value.intent_id,
            resource_id="resource-a",
            status="not_applied",
            observation_digest="c" * 64,
            independent=True,
            authoritative_negative=True,
            visibility_complete=True,
        ),
        executor_claimed_applied=True,
    )
    assert contradiction.effect == "CONFIRMED_NOT_APPLIED"
    assert service.authorize_retry(
        intent_id=value.intent_id, idempotency_mode="read_reconcile"
    )

    uncertain, uncertain_intent = crossed()
    result = uncertain.reconcile(
        evidence=ObserverEvidence(
            observer_id="observer-root",
            tenant_id="tenant-a",
            intent_id=uncertain_intent.intent_id,
            resource_id="resource-a",
            status="absent_uncertain",
            observation_digest="d" * 64,
            independent=True,
        )
    )
    assert result.effect == "UNKNOWN_EFFECT"
    with pytest.raises(ActionDenied, match="RETRY_EFFECT_NOT_NEGATIVELY_PROVEN"):
        uncertain.authorize_retry(intent_id=uncertain_intent.intent_id, idempotency_mode="none")


def test_observer_binding_compensation_and_forged_verifier_fail_closed() -> None:
    service, value = crossed()
    result = service.reconcile(
        evidence=ObserverEvidence(
            observer_id="executor-echo",
            tenant_id="tenant-a",
            intent_id=value.intent_id,
            resource_id="resource-a",
            status="applied",
            observation_digest="e" * 64,
            independent=False,
        )
    )
    assert result.effect == "UNKNOWN_EFFECT"
    assert service.compensation_result(
        intent_id=value.intent_id, observer_verified_restored=False
    ) == "COMPENSATION_UNVERIFIED"
    with pytest.raises(ActionDenied, match="T5_FORGED_OR_SELF_VERIFIER"):
        service.propose_verification(
            intent_id=value.intent_id,
            verifier_id="ar04-executor",
            verifier_key_id="verifier-key",
        )


def test_t5_is_only_a_nonterminal_proposal() -> None:
    service, value = crossed()
    service.reconcile(
        evidence=ObserverEvidence(
            observer_id="observer-root",
            tenant_id="tenant-a",
            intent_id=value.intent_id,
            resource_id="resource-a",
            status="applied",
            observation_digest="f" * 64,
            independent=True,
        )
    )
    proposal = service.propose_verification(
        intent_id=value.intent_id,
        verifier_id="ar05-independent",
        verifier_key_id="verifier-key",
    )
    assert proposal.effect == "CONFIRMED_APPLIED"
    assert proposal.terminal_committed is False
    assert service.provider_calls == 0
