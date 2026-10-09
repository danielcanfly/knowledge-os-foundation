from __future__ import annotations

import hashlib
import hmac
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar04_safe_action_experimental import (
    ActionIntent,
    ApprovalFixture,
    InertSafeActionBoundary,
    ObserverEvidence,
    PolicyFixture,
)
from knowledge_engine.m27_ar05_verification_experimental import (
    CitationBinding,
    ContentFrame,
    HardGate,
    JournalSnapshot,
    NativeEvidenceFixture,
    PublicationCandidate,
    VerificationPublicationGate,
    VerificationReceipt,
    verification_message,
)
from knowledge_engine.m27_ar09_oracle_experimental import (
    EXPECTED_ACCEPT_FIXTURE_ONLY,
    EXPECTED_DENY,
    NativeCitation,
    NativeSourceFixture,
    compare_native_source,
)
from knowledge_engine.m27_cross_module_abi_experimental import (
    OFFLINE_BLOCKER_DISPOSITION,
    AbiGateDenied,
    EffectiveAuthorization,
    LegacyBoundEnvelope,
    NewRecordEnvelope,
    OfflineAuthorityGate,
    OfflineSerializableLedger,
    PostTerminalNotice,
    authorization_message,
    sign_authorization,
)

AUTH_KEY = b"offline-auth-key"
VERIFIER_KEY = b"offline-verifier-key"
SOURCE = b"native source bytes for a supported answer"
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()


def authority_gate() -> OfflineAuthorityGate:
    return OfflineAuthorityGate(trusted_keys={"auth-key": AUTH_KEY})


def unsigned_auth(**changes: object) -> EffectiveAuthorization:
    base = EffectiveAuthorization(
        auth_id="auth-1",
        issuer_key_id="auth-key",
        tenant_id="tenant-a",
        run_id="run-a",
        principal_id="principal-a",
        delegated_by="owner-a",
        audience="m27.offline",
        purpose="task-execution",
        issued_at=90,
        expires_at=200,
        policy_generation=4,
        revocation_generation=0,
        consent_required=True,
        consent_ref="consent-1",
        signature="",
    )
    return replace(base, **changes)


def signed_auth(**changes: object) -> EffectiveAuthorization:
    return sign_authorization(unsigned_auth(**changes), AUTH_KEY)


def validate_auth(auth: EffectiveAuthorization) -> None:
    authority_gate().validate_authorization(
        auth=auth,
        tenant_id="tenant-a",
        run_id="run-a",
        audience="m27.offline",
        purpose="task-execution",
        policy_generation=4,
        revocation_generation=0,
        now=100,
    )


def action_proposal():
    boundary = InertSafeActionBoundary(
        trusted_policy_issuer="policy-root",
        trusted_approval_issuers=frozenset({"approval-root"}),
        trusted_observers=frozenset({"observer-root"}),
        trusted_verifier_keys=frozenset({"action-verifier-key"}),
    )
    intent = ActionIntent(
        intent_id="intent-1",
        run_id="run-a",
        tenant_id="tenant-a",
        principal_id="principal-a",
        delegated_by="owner-a",
        capability_id="mock-write",
        capability_version="1",
        operation="write",
        resource_id="mock-resource",
        arguments_ref="args-1",
        arguments_digest="1" * 64,
        idempotency_key="idem-1",
        side_effect="reversible",
        approval_id="approval-1",
        requested_at=90,
        expires_at=200,
        policy_version="p4",
        lease_epoch=3,
        attempt=1,
    )
    candidate = boundary.register_intent(
        command_id="command-1",
        intent=intent,
        policy=PolicyFixture(
            issuer="policy-root",
            tenant_id="tenant-a",
            principal_id="principal-a",
            delegated_by="owner-a",
            auth_expires_at=200,
            allowed_capabilities=frozenset({"mock-write"}),
            allowed_resources=frozenset({"mock-resource"}),
            lease_epoch=3,
            budget_cap_microunits=100,
            price_microunits=10,
        ),
        now=100,
    )
    boundary.claim_dispatch(
        intent_id=intent.intent_id,
        claim_id="claim-1",
        approval=ApprovalFixture(
            approval_id="approval-1",
            intent_digest=candidate.intent_digest,
            tenant_id="tenant-a",
            approver_principal="approver-a",
            issuer="approval-root",
            expires_at=200,
        ),
        expected_epoch=3,
        physical_attempt=1,
        now=100,
    )
    boundary.cross_send_boundary(claim_id="claim-1", current_epoch=3)
    reconciled = boundary.reconcile(
        evidence=ObserverEvidence(
            observer_id="observer-root",
            tenant_id="tenant-a",
            intent_id="intent-1",
            resource_id="mock-resource",
            status="applied",
            observation_digest="2" * 64,
            independent=True,
        )
    )
    assert reconciled.effect == "CONFIRMED_APPLIED"
    proposal = boundary.propose_verification(
        intent_id="intent-1",
        verifier_id="independent-action-verifier",
        verifier_key_id="action-verifier-key",
    )
    return boundary, candidate.intent_digest, proposal


def publication_proposal(snapshot: JournalSnapshot):
    citation = CitationBinding(
        citation_id="citation-1",
        source_id="source-1",
        source_revision="revision-1",
        source_bytes_sha256=SOURCE_SHA,
        claim_start=0,
        claim_end=12,
    )
    evidence = NativeEvidenceFixture(
        identity_kind="native",
        content_bytes=SOURCE,
        content_sha256=SOURCE_SHA,
        citations=(citation,),
    )
    candidate = PublicationCandidate(
        publication_id="publication-1",
        segment_id="segment-1",
        revision=1,
        irreversible=False,
        claim_client_delivered=False,
        original_evidence=evidence,
        observed_evidence=evidence,
        expected_citation_ids=("citation-1",),
        frames=(
            ContentFrame(
                "frame-1",
                "verified_text",
                b"supported answer",
                ("citation-1",),
                "verification-1",
                True,
                None,
            ),
            ContentFrame("frame-2", "terminal", b"done", (), None, True, None),
        ),
    )
    receipt = VerificationReceipt(
        verification_id="verification-1",
        signer_id="independent-verifier",
        key_id="verifier-key",
        tenant_id=snapshot.tenant_id,
        task_id=snapshot.task_id,
        task_version=snapshot.task_version,
        run_id=snapshot.run_id,
        attempt=snapshot.attempt,
        outcome_id=snapshot.outcome_id,
        outcome_digest=snapshot.outcome_digest,
        journal_head_seq=snapshot.head_seq,
        journal_head_hash=snapshot.head_hash,
        lease_epoch=snapshot.lease_epoch,
        checked_at=100,
        expires_at=200,
        hard_gates=(
            HardGate("policy", "pass"),
            HardGate("source", "pass"),
            HardGate("citation", "pass"),
        ),
        signature="",
    )
    receipt = replace(
        receipt,
        signature=hmac.new(
            VERIFIER_KEY, verification_message(receipt), hashlib.sha256
        ).hexdigest(),
    )
    gate = VerificationPublicationGate(
        verifier_keys={"verifier-key": VERIFIER_KEY},
        signer_for_key={"verifier-key": "independent-verifier"},
        generator_id="answer-generator",
    )
    return gate, gate.evaluate(
        snapshot=snapshot, receipt=receipt, publication=candidate, now=110
    )


def native_oracle_label() -> str:
    citation = NativeCitation(
        citation_id="citation-1",
        source_id="source-1",
        source_revision="revision-1",
        source_digest=SOURCE_SHA,
        start=0,
        end=12,
    )
    native = NativeSourceFixture(
        kind="native",
        tenant_id="tenant-a",
        snapshot_id="snapshot-1",
        source_bytes=SOURCE,
        source_digest=SOURCE_SHA,
        citations=(citation,),
    )
    return compare_native_source(native, native).label


def ready_ledger() -> tuple[OfflineSerializableLedger, str]:
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a",
        run_id="run-a",
        lease_epoch=3,
        budget_cap_microunits=100,
    )
    digest = "d" * 64
    ledger.register_intent(
        command_id="command-1",
        intent_digest=digest,
        quoted_cost_microunits=10,
        expected_version=0,
    )
    ledger.acquire_permit(
        permit_id="permit-1",
        intent_digest=digest,
        approval_intent_digest=digest,
        lease_epoch=3,
        expected_version=1,
    )
    ledger.start_send(permit_id="permit-1", expected_version=2)
    ledger.record_observation(
        effect="CONFIRMED_APPLIED",
        independent=True,
        observed_digest="e" * 64,
        expected_version=3,
    )
    ledger.settle_budget(
        actual_microunits=10, charge_id="charge-1", expected_version=4
    )
    return ledger, digest


def journal_for(ledger: OfflineSerializableLedger, **changes: object) -> JournalSnapshot:
    state = ledger.snapshot
    base = JournalSnapshot(
        tenant_id="tenant-a",
        task_id="task-a",
        task_version=1,
        run_id="run-a",
        attempt=1,
        head_seq=state.head_seq,
        head_hash=state.head_hash,
        lease_epoch=state.lease_epoch,
        outcome_id="outcome-1",
        outcome_digest="f" * 64,
        unknown_effect=state.effect == "UNKNOWN_EFFECT",
    )
    return replace(base, **changes)


def test_x01_preserves_legacy_bytes_and_separates_new_records() -> None:
    raw = b'{"legacy": true, "spacing": "is preserved"}'
    sidecars = (hashlib.sha256(b"authority-sidecar").hexdigest(),)
    legacy = LegacyBoundEnvelope(
        envelope_id="envelope-1",
        tenant_id="tenant-a",
        run_id="run-a",
        legacy_type="RunEvent",
        legacy_raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_byte_length=len(raw),
        required_sidecar_digests=sidecars,
        policy_generation=4,
        revocation_generation=0,
    )
    authority_gate().validate_legacy(
        envelope=legacy, raw_bytes=raw, supplied_sidecar_digests=sidecars
    )
    with pytest.raises(AbiGateDenied, match="X01_LEGACY_RAW_BYTES_MISMATCH"):
        authority_gate().validate_legacy(
            envelope=legacy,
            raw_bytes=raw.replace(b"true", b"null"),
            supplied_sidecar_digests=sidecars,
        )

    body = b'{"notice":"new only"}'
    new = NewRecordEnvelope(
        record_id="notice-1",
        tenant_id="tenant-a",
        run_id="run-a",
        new_record_namespace="ar05r.notice",
        body_sha256=hashlib.sha256(body).hexdigest(),
        policy_generation=4,
        revocation_generation=0,
    )
    authority_gate().validate_new_record(envelope=new, body=body)
    assert not hasattr(new, "legacy_raw_sha256")
    with pytest.raises(AbiGateDenied, match="X01_REQUIRED_SIDECAR_MISSING"):
        authority_gate().validate_legacy(
            envelope=replace(legacy, required_sidecar_digests=()),
            raw_bytes=raw,
            supplied_sidecar_digests=(),
        )


@pytest.mark.parametrize(
    ("auth", "code"),
    [
        (lambda: signed_auth(consent_ref=None), "X02_CONSENT_ABSENT"),
        (lambda: signed_auth(delegated_by=None), "X02_DELEGATION_ABSENT"),
        (lambda: signed_auth(expires_at=100), "X02_AUTH_EXPIRED_OR_FROM_FUTURE"),
        (lambda: signed_auth(policy_generation=3), "X02_POLICY_GENERATION_STALE"),
        (
            lambda: replace(signed_auth(), signature="0" * 64),
            "X02_AUTH_SIGNATURE_INVALID",
        ),
    ],
)
def test_x02_authority_is_signed_scoped_current_and_fail_closed(auth, code: str) -> None:
    with pytest.raises(AbiGateDenied, match=code):
        validate_auth(auth())
    validate_auth(signed_auth())
    assert authorization_message(unsigned_auth())


def test_x03_x04_command_cas_takeover_and_one_time_permit() -> None:
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=3, budget_cap_microunits=20
    )
    digest = "a" * 64
    committed = ledger.register_intent(
        command_id="command-1",
        intent_digest=digest,
        quoted_cost_microunits=10,
        expected_version=0,
    )
    assert ledger.lookup_command("command-1") == committed
    assert (
        ledger.register_intent(
            command_id="command-1",
            intent_digest=digest,
            quoted_cost_microunits=10,
            expected_version=0,
        )
        == committed
    )
    with pytest.raises(AbiGateDenied, match="X04_COMMAND_DIGEST_CONFLICT"):
        ledger.register_intent(
            command_id="command-1",
            intent_digest="b" * 64,
            quoted_cost_microunits=10,
            expected_version=1,
        )
    with pytest.raises(AbiGateDenied, match="X03_TAKEOVER_REQUIRES_NEW_AUTHORITY"):
        ledger.acquire_permit(
            permit_id="permit-stale",
            intent_digest=digest,
            approval_intent_digest=digest,
            lease_epoch=4,
            expected_version=1,
        )
    ledger.acquire_permit(
        permit_id="permit-1",
        intent_digest=digest,
        approval_intent_digest=digest,
        lease_epoch=3,
        expected_version=1,
    )
    with pytest.raises(AbiGateDenied, match="X03_ONE_TIME_PERMIT_ALREADY_CLAIMED"):
        ledger.acquire_permit(
            permit_id="permit-2",
            intent_digest=digest,
            approval_intent_digest=digest,
            lease_epoch=3,
            expected_version=2,
        )
    with pytest.raises(AbiGateDenied, match="X04_CAS_CONFLICT"):
        ledger.start_send(permit_id="permit-1", expected_version=1)


def test_x06_revocation_is_deny_first_and_does_not_reopen_terminal() -> None:
    ledger, _ = ready_ledger()
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    ledger.commit_terminal(
        snapshot=snapshot,
        action_proposal=action,
        publication=publication,
        oracle_label=native_oracle_label(),
        expected_version=5,
    )
    terminal_head = ledger.snapshot.head_hash
    generation = ledger.revoke_dependency(
        dependency_id="source-1", expected_generation=0
    )
    assert generation == 1
    assert ledger.snapshot.terminal is True
    assert ledger.snapshot.head_hash == terminal_head
    with pytest.raises(AbiGateDenied, match="X06_STALE_REVOCATION_GENERATION"):
        ledger.require_readable(dependency_id="source-2", proof_generation=0)
    with pytest.raises(AbiGateDenied, match="X06_DEPENDENCY_REVOKED"):
        ledger.require_readable(dependency_id="source-1", proof_generation=1)


def test_x07_budget_denies_unknown_double_reserve_and_records_late_overrun() -> None:
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=1, budget_cap_microunits=10
    )
    with pytest.raises(AbiGateDenied, match="X07_PRICE_UNKNOWN"):
        ledger.register_intent(
            command_id="unknown",
            intent_digest="a" * 64,
            quoted_cost_microunits=None,
            expected_version=0,
        )
    ledger.register_intent(
        command_id="one",
        intent_digest="a" * 64,
        quoted_cost_microunits=10,
        expected_version=0,
    )
    with pytest.raises(AbiGateDenied, match="X07_BUDGET_DENIED"):
        ledger.register_intent(
            command_id="two",
            intent_digest="b" * 64,
            quoted_cost_microunits=1,
            expected_version=1,
        )
    ledger.settle_budget(actual_microunits=12, charge_id="late", expected_version=1)
    assert ledger.snapshot.spent_microunits == 12
    assert ledger.snapshot.economic_incident is True


def test_x05_notice_requires_terminal_and_monotonic_cursor() -> None:
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=1, budget_cap_microunits=10
    )
    notice = PostTerminalNotice(
        notice_id="notice-1",
        tenant_id="tenant-a",
        run_id="run-a",
        revision=2,
        cursor=2,
        kind="retraction",
        supersedes_segment_id="segment-1",
        body_sha256=hashlib.sha256(b"retract").hexdigest(),
        original_terminal_head_hash=ledger.snapshot.head_hash,
    )
    with pytest.raises(AbiGateDenied, match="X05_NOTICE_REQUIRES_TERMINAL"):
        ledger.append_post_terminal_notice(notice=notice)


def test_x05_x08_x09_end_to_end_terminal_and_notice_are_separate() -> None:
    validate_auth(signed_auth())
    boundary, intent_digest, action = action_proposal()
    ledger, ledger_digest = ready_ledger()
    assert intent_digest != ledger_digest  # Independent models bind their own fixture bytes.
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    oracle = native_oracle_label()
    assert oracle == EXPECTED_ACCEPT_FIXTURE_ONLY
    ledger.commit_terminal(
        snapshot=snapshot,
        action_proposal=action,
        publication=publication,
        oracle_label=oracle,
        expected_version=5,
    )
    terminal = ledger.snapshot
    notice = PostTerminalNotice(
        notice_id="notice-1",
        tenant_id="tenant-a",
        run_id="run-a",
        revision=1,
        cursor=1,
        kind="correction",
        supersedes_segment_id="segment-1",
        body_sha256=hashlib.sha256(b"correction").hexdigest(),
        original_terminal_head_hash=terminal.head_hash,
    )
    ledger.append_post_terminal_notice(notice=notice)
    assert ledger.snapshot == terminal
    assert ledger.notices == (notice,)
    assert boundary.provider_calls == 0
    with pytest.raises(AbiGateDenied, match="X05_TERMINAL_IMMUTABLE"):
        ledger.commit_terminal(
            snapshot=journal_for(ledger),
            action_proposal=action,
            publication=publication,
            oracle_label=oracle,
            expected_version=6,
        )


def test_x08_stale_head_and_x09_oracle_rejection_block_terminal() -> None:
    ledger, _ = ready_ledger()
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X08_STALE_VERIFIER_HEAD"):
        ledger.commit_terminal(
            snapshot=replace(snapshot, head_seq=snapshot.head_seq - 1),
            action_proposal=action,
            publication=publication,
            oracle_label=EXPECTED_ACCEPT_FIXTURE_ONLY,
            expected_version=5,
        )
    with pytest.raises(AbiGateDenied, match="X09_INDEPENDENT_ORACLE_REJECTED"):
        ledger.commit_terminal(
            snapshot=snapshot,
            action_proposal=action,
            publication=publication,
            oracle_label=EXPECTED_DENY,
            expected_version=5,
        )


def test_external_authority_blockers_remain_explicit_not_mock_closed() -> None:
    assert OFFLINE_BLOCKER_DISPOSITION == {
        "X01": "OFFLINE_ENGINEERING_PROOF",
        "X02": "FAIL_CLOSED_PENDING_REAL_IDP_LEGAL_AUTHORITY",
        "X03": "OFFLINE_ENGINEERING_PROOF",
        "X04": "OFFLINE_MODEL_ONLY_PENDING_DURABLE_BACKEND_PROOF",
        "X05": "OFFLINE_ENGINEERING_PROOF_PENDING_CLIENT_POLICY",
        "X06": "FAIL_CLOSED_PENDING_LEGAL_STORE_AUTHORITY",
        "X07": "OFFLINE_ENGINEERING_PROOF_PENDING_PRICE_AUTHORITY",
        "X08": "OFFLINE_ENGINEERING_PROOF_PENDING_REAL_SIGNER",
        "X09": "OFFLINE_FIXTURE_ONLY_PENDING_NATIVE_PRODUCTION_EVIDENCE",
    }
