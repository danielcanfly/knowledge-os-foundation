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
    ConsentAuthoritySnapshot,
    EffectiveAuthorization,
    IndependentActionEvidence,
    IndependentApprovalEvidence,
    IndependentNativeOracleEvidence,
    IndependentPublicationEvidence,
    LegacyBoundEnvelope,
    NewRecordEnvelope,
    OfflineAuthorityGate,
    OfflineIndependentEvidencePort,
    OfflineSerializableLedger,
    PostTerminalNotice,
    authorization_message,
    sign_authorization,
    sign_consent,
)

AUTH_KEY = b"offline-auth-key"
VERIFIER_KEY = b"offline-verifier-key"
SOURCE = b"native source bytes for a supported answer"
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()


def authority_gate() -> OfflineAuthorityGate:
    return OfflineAuthorityGate(
        trusted_keys={"auth-key": AUTH_KEY},
        trusted_consent_keys={"consent-key": b"separate-consent-fixture-key"},
    )


def current_consent(**changes: object) -> ConsentAuthoritySnapshot:
    grant = ConsentAuthoritySnapshot(
        key_id="consent-key", consent_ref="consent-1", tenant_id="tenant-a",
        run_id="run-a", principal_id="principal-a", purpose="task-execution",
        policy_generation=4, revocation_generation=0, issued_at=95,
        expires_at=200,
    )
    return sign_consent(
        replace(grant, **changes), b"separate-consent-fixture-key"
    )


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
        expected_principal_id="principal-a",
        expected_delegated_by="owner-a",
        consent_policy=current_consent(),
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


def native_source() -> NativeSourceFixture:
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
    return native


def native_oracle_label() -> str:
    native = native_source()
    return compare_native_source(native, native).label


def trusted_approval(digest: str, epoch: int = 3) -> IndependentApprovalEvidence:
    return IndependentApprovalEvidence(
        approval_id="approval-1", tenant_id="tenant-a", run_id="run-a",
        command_id="command-1", intent_id="intent-1",
        intent_digest=digest, lease_epoch=epoch,
        approver_id="approver-a", issuer_id="separate-approval-root",
    )


def ready_ledger(
    *,
    registered_digest: str | None = None,
    action_overrides: dict[str, object] | None = None,
    publication_overrides: dict[str, object] | None = None,
    native_overrides: dict[str, object] | None = None,
    extra_reservation_microunits: int = 0,
) -> tuple[OfflineSerializableLedger, str]:
    _, independently_sourced_digest, action = action_proposal()
    digest = registered_digest or independently_sourced_digest
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a",
        run_id="run-a",
        lease_epoch=3,
        budget_cap_microunits=100,
        trusted_approvals={"approval-1": trusted_approval(digest)},
    )
    ledger.register_intent(
        command_id="command-1", intent_id="intent-1",
        intent_digest=digest, lease_epoch=3,
        quoted_cost_microunits=10, expected_version=0,
    )
    ledger.acquire_permit(
        permit_id="permit-1", command_id="command-1", intent_id="intent-1",
        intent_digest=digest, approval_intent_digest=digest, lease_epoch=3,
        approval_tenant_id="tenant-a", approval_run_id="run-a",
        approval_lease_epoch=3, approval_id="approval-1", expected_version=1,
    )
    ledger.start_send(permit_id="permit-1", expected_version=2)
    ledger.record_observation(
        effect="CONFIRMED_APPLIED", independent=True,
        observed_digest="e" * 64, expected_version=3,
    )
    ledger.settle_budget(
        actual_microunits=10, charge_id="charge-1", command_id="command-1",
        usage_version="v1", source_id="mock-billing-root", expected_version=4,
    )
    if extra_reservation_microunits:
        ledger.register_intent(
            command_id="command-2", intent_id="intent-2", lease_epoch=3,
            intent_digest="b" * 64,
            quoted_cost_microunits=extra_reservation_microunits,
            expected_version=5,
        )
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    native = native_source()
    ledger.install_offline_evidence_port(
        OfflineIndependentEvidencePort(
            action=replace(
                IndependentActionEvidence(
                    tenant_id="tenant-a", run_id="run-a", command_id="command-1",
                    intent_id=action.intent_id,
                    # Independent AR04 candidate digest, not rewritten to suit Ledger.
                    intent_digest=independently_sourced_digest,
                    permit_id="permit-1", lease_epoch=3,
                    observation_digest="e" * 64, effect=action.effect,
                    observer_id="observer-root",
                ),
                **(action_overrides or {}),
            ),
            publication=replace(
                IndependentPublicationEvidence(
                    tenant_id="tenant-a", run_id="run-a", intent_id=action.intent_id,
                    intent_digest=independently_sourced_digest,
                    outcome_id=snapshot.outcome_id,
                    outcome_digest=snapshot.outcome_digest,
                    head_seq=snapshot.head_seq, head_hash=snapshot.head_hash,
                    lease_epoch=snapshot.lease_epoch,
                    verification_id=publication.verification_id,
                    first_verified_frame_id=publication.first_verified_frame_id,
                    content_sha256=publication.content_sha256,
                    effect=action.effect, verifier_id="independent-verifier",
                ),
                **(publication_overrides or {}),
            ),
            native=replace(
                IndependentNativeOracleEvidence(
                    oracle_id="oracle-native-1", tenant_id="tenant-a", run_id="run-a",
                    verification_id=publication.verification_id,
                    verified_content_sha256=publication.content_sha256,
                    original=native, observed=native,
                ),
                **(native_overrides or {}),
            ),
            trusted_observer_ids=frozenset({"observer-root"}),
            trusted_verifier_ids=frozenset({"independent-verifier"}),
        )
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
    digest = "a" * 64
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=3, budget_cap_microunits=20,
        trusted_approvals={"approval-1": trusted_approval(digest)},
    )
    committed = ledger.register_intent(
        command_id="command-1", intent_id="intent-1", lease_epoch=3,
        intent_digest=digest,
        quoted_cost_microunits=10,
        expected_version=0,
    )
    assert ledger.lookup_command("command-1") == committed
    assert (
        ledger.register_intent(
            command_id="command-1", intent_id="intent-1", lease_epoch=3,
            intent_digest=digest,
            quoted_cost_microunits=10,
            expected_version=0,
        )
        == committed
    )
    with pytest.raises(AbiGateDenied, match="X04_COMMAND_DIGEST_CONFLICT"):
        ledger.register_intent(
            command_id="command-1", intent_id="intent-1", lease_epoch=3,
            intent_digest="b" * 64,
            quoted_cost_microunits=10,
            expected_version=1,
        )
    with pytest.raises(AbiGateDenied, match="X03_TAKEOVER_REQUIRES_NEW_AUTHORITY"):
        ledger.acquire_permit(
            permit_id="permit-stale", command_id="command-1", intent_id="intent-1",
            intent_digest=digest, approval_intent_digest=digest, lease_epoch=4,
            approval_tenant_id="tenant-a", approval_run_id="run-a",
            approval_lease_epoch=3, approval_id="approval-1", expected_version=1,
        )
    ledger.acquire_permit(
        permit_id="permit-1", command_id="command-1", intent_id="intent-1",
        intent_digest=digest, approval_intent_digest=digest, lease_epoch=3,
        approval_tenant_id="tenant-a", approval_run_id="run-a",
        approval_lease_epoch=3, approval_id="approval-1", expected_version=1,
    )
    with pytest.raises(AbiGateDenied, match="X03_ONE_TIME_PERMIT_ALREADY_CLAIMED"):
        ledger.acquire_permit(
            permit_id="permit-2", command_id="command-1", intent_id="intent-1",
            intent_digest=digest, approval_intent_digest=digest, lease_epoch=3,
            approval_tenant_id="tenant-a", approval_run_id="run-a",
            approval_lease_epoch=3, approval_id="approval-1", expected_version=2,
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
        oracle_evidence_id="oracle-native-1",
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
            command_id="unknown", intent_id="unknown", lease_epoch=1,
            intent_digest="a" * 64, quoted_cost_microunits=None, expected_version=0,
        )
    ledger.register_intent(
        command_id="one", intent_id="intent-one", lease_epoch=1,
        intent_digest="a" * 64, quoted_cost_microunits=10, expected_version=0,
    )
    with pytest.raises(AbiGateDenied, match="X07_BUDGET_DENIED"):
        ledger.register_intent(
            command_id="two", intent_id="intent-two", lease_epoch=1,
            intent_digest="b" * 64, quoted_cost_microunits=1, expected_version=1,
        )
    ledger.settle_budget(
        actual_microunits=12, charge_id="late", command_id="one",
        usage_version="v1", source_id="mock-billing-root", expected_version=1,
    )
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
    assert intent_digest == ledger_digest  # Identical immutable T1/AR04 identity.
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    oracle = native_oracle_label()
    assert oracle == EXPECTED_ACCEPT_FIXTURE_ONLY
    ledger.commit_terminal(
        snapshot=snapshot,
        action_proposal=action,
        publication=publication,
        oracle_label=oracle,
        oracle_evidence_id="oracle-native-1",
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
            oracle_evidence_id="oracle-native-1",
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
            oracle_evidence_id="oracle-native-1",
            expected_version=5,
        )
    with pytest.raises(AbiGateDenied, match="X09_INDEPENDENT_ORACLE_REJECTED"):
        ledger.commit_terminal(
            snapshot=snapshot,
            action_proposal=action,
            publication=publication,
            oracle_label=EXPECTED_DENY,
            oracle_evidence_id="oracle-native-1",
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


# P0 regression tests are written before implementation; initial RED is required.
def test_p0_ghost_permit_cannot_claim_unregistered_intent() -> None:
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=3, budget_cap_microunits=100
    )
    with pytest.raises(AbiGateDenied, match="X03_INTENT_NOT_REGISTERED"):
        ledger.acquire_permit(
            permit_id="ghost", intent_digest="a" * 64,
            approval_intent_digest="a" * 64, lease_epoch=3, expected_version=0,
        )


def test_p0_action_and_ledger_digest_mismatch_must_deny_terminal() -> None:
    ledger, ledger_digest = ready_ledger(registered_digest="d" * 64)
    _, action_digest, action = action_proposal()
    assert ledger_digest != action_digest
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X08_ACTION_LEDGER_BINDING_MISMATCH"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=native_oracle_label(),
            oracle_evidence_id="oracle-native-1", expected_version=5,
        )


def test_p0_duplicate_charge_id_is_idempotent_and_conflicts_if_amount_changes() -> None:
    ledger, _ = ready_ledger()
    spent = ledger.snapshot.spent_microunits
    ledger.settle_budget(
        actual_microunits=10, charge_id="charge-1", command_id="command-1",
        usage_version="v1", source_id="mock-billing-root",
        expected_version=ledger.snapshot.version,
    )
    assert ledger.snapshot.spent_microunits == spent
    with pytest.raises(AbiGateDenied, match="X07_CHARGE_ID_CONFLICT"):
        ledger.settle_budget(
            actual_microunits=11, charge_id="charge-1", command_id="command-1",
            usage_version="v1", source_id="mock-billing-root",
            expected_version=ledger.snapshot.version,
        )


def test_p0_signed_wrong_effective_principal_requires_external_binding() -> None:
    with pytest.raises(AbiGateDenied, match="X02_EXPECTED_PRINCIPAL_MISMATCH"):
        authority_gate().validate_authorization(
            auth=signed_auth(principal_id="wrong-principal"),
            tenant_id="tenant-a", run_id="run-a", audience="m27.offline",
            purpose="task-execution", policy_generation=4,
            revocation_generation=0, now=100,
            expected_principal_id="principal-a", expected_delegated_by="owner-a",
        )


def test_p0_caller_owned_oracle_label_is_not_native_source_evidence() -> None:
    ledger, _ = ready_ledger()
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X09_NATIVE_ORACLE_EVIDENCE_UNBOUND"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=EXPECTED_ACCEPT_FIXTURE_ONLY, expected_version=5,
        )


@pytest.mark.parametrize("scope_change", [
    {"tenant_id": "tenant-b"}, {"run_id": "run-b"},
])
def test_p0_cross_scope_snapshot_never_commits(scope_change: dict[str, str]) -> None:
    ledger, _ = ready_ledger()
    _, _, action = action_proposal()
    snapshot = journal_for(ledger, **scope_change)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X08_SNAPSHOT_SCOPE_MISMATCH"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=native_oracle_label(), oracle_evidence_id="oracle-native-1",
            expected_version=5,
        )


@pytest.mark.parametrize(("kind", "changes", "denial"), [
    ("action", {"tenant_id": "tenant-b"}, "X08_ACTION_LEDGER_BINDING_MISMATCH"),
    ("action", {"run_id": "run-b"}, "X08_ACTION_LEDGER_BINDING_MISMATCH"),
    ("action", {"intent_digest": "f" * 64}, "X08_ACTION_LEDGER_BINDING_MISMATCH"),
    ("action", {"permit_id": "other-claim"}, "X08_ACTION_LEDGER_BINDING_MISMATCH"),
    ("action", {"observation_digest": "0" * 64}, "X08_ACTION_LEDGER_BINDING_MISMATCH"),
    ("publication", {"outcome_digest": "0" * 64},
     "X08_PUBLICATION_OUTCOME_UNVERIFIED"),
    ("publication", {"verification_id": "forged-verification"},
     "X08_PUBLICATION_OUTCOME_UNVERIFIED"),
    ("publication", {"head_hash": "0" * 64},
     "X08_PUBLICATION_OUTCOME_UNVERIFIED"),
    ("publication", {"lease_epoch": 99},
     "X08_PUBLICATION_OUTCOME_UNVERIFIED"),
    ("native", {"tenant_id": "tenant-b"},
     "X09_NATIVE_ORACLE_SOURCE_SCOPE_MISMATCH"),
    ("native", {"verified_content_sha256": "0" * 64},
     "X09_NATIVE_ORACLE_SOURCE_SCOPE_MISMATCH"),
])
def test_p0_independent_evidence_binding_must_match(
    kind: str, changes: dict[str, object], denial: str
) -> None:
    kwargs = {f"{kind}_overrides": changes}
    ledger, _ = ready_ledger(**kwargs)
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match=denial):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=native_oracle_label(), oracle_evidence_id="oracle-native-1",
            expected_version=5,
        )


def test_p0_native_bytes_and_citations_are_independently_checked() -> None:
    native = native_source()
    altered = replace(native, source_bytes=b"other bytes")
    ledger, _ = ready_ledger(native_overrides={"observed": altered})
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X09_INDEPENDENT_ORACLE_REJECTED"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=EXPECTED_ACCEPT_FIXTURE_ONLY, oracle_evidence_id="oracle-native-1",
            expected_version=5,
        )
    changed_citation = replace(native.citations[0], source_revision="evil")
    ledger2, _ = ready_ledger(
        native_overrides={"observed": replace(native, citations=(changed_citation,))}
    )
    with pytest.raises(AbiGateDenied, match="X09_INDEPENDENT_ORACLE_REJECTED"):
        ledger2.commit_terminal(
            snapshot=journal_for(ledger2), action_proposal=action, publication=publication,
            oracle_label=EXPECTED_ACCEPT_FIXTURE_ONLY, oracle_evidence_id="oracle-native-1",
            expected_version=5,
        )


def test_p0_unknown_effect_and_forged_action_cannot_terminal() -> None:
    ledger, _ = ready_ledger()
    _, _, action = action_proposal()
    ledger.record_observation(
        effect="UNKNOWN_EFFECT", independent=False,
        observed_digest="unknown-observation", expected_version=5,
    )
    snapshot = journal_for(ledger)
    # Forge an eligibility proposal by evaluating a falsified safe snapshot.
    _, publication = publication_proposal(replace(snapshot, unknown_effect=False))
    with pytest.raises(AbiGateDenied, match="X08_UNKNOWN_EFFECT"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=native_oracle_label(), oracle_evidence_id="oracle-native-1",
            expected_version=6,
        )

    pristine, _ = ready_ledger()
    actual_snapshot = journal_for(pristine)
    _, valid_publication = publication_proposal(actual_snapshot)
    with pytest.raises(AbiGateDenied, match="X08_ACTION_LEDGER_EFFECT_MISMATCH"):
        pristine.commit_terminal(
            snapshot=actual_snapshot,
            action_proposal=replace(action, effect="CONFIRMED_NOT_APPLIED"),
            publication=valid_publication, oracle_label=native_oracle_label(),
            oracle_evidence_id="oracle-native-1", expected_version=5,
        )


def test_p0_not_dispatched_cannot_terminal_on_ar04_proposal() -> None:
    source, digest = ready_ledger()
    assert source.snapshot.effect == "CONFIRMED_APPLIED"
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=3,
        budget_cap_microunits=100,
    )
    ledger.register_intent(
        command_id="command-1", intent_id="intent-1", intent_digest=digest,
        lease_epoch=3, quoted_cost_microunits=10, expected_version=0,
    )
    assert source._evidence_port is not None
    ledger.install_offline_evidence_port(source._evidence_port)
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X08_ACTION_LEDGER_EFFECT_MISMATCH"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=native_oracle_label(), oracle_evidence_id="oracle-native-1",
            expected_version=1,
        )


def test_p0_invoice_replay_distinct_late_charge_and_conflicts() -> None:
    ledger, _ = ready_ledger()
    first_head = ledger.snapshot
    ledger.settle_budget(
        command_id="command-1", charge_id="charge-1", actual_microunits=10,
        usage_version="v1", source_id="mock-billing-root", expected_version=0,
    )
    assert ledger.snapshot == first_head
    with pytest.raises(AbiGateDenied, match="X07_CHARGE_ID_CONFLICT"):
        ledger.settle_budget(
            command_id="command-1", charge_id="charge-1", actual_microunits=10,
            usage_version="v2", source_id="mock-billing-root",
            expected_version=ledger.snapshot.version,
        )
    ledger.settle_budget(
        command_id="command-1", charge_id="late-charge-2", actual_microunits=2,
        usage_version="v2", source_id="mock-billing-root",
        expected_version=ledger.snapshot.version,
    )
    assert ledger.snapshot.spent_microunits == 12
    assert ledger.snapshot.economic_incident is True
    assert ledger.snapshot.reserved_microunits == 0


def test_p0_terminal_exact_replay_idempotent_but_changed_receipt_conflicts() -> None:
    ledger, _ = ready_ledger()
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    request = dict(
        snapshot=snapshot, action_proposal=action, publication=publication,
        oracle_label=native_oracle_label(), oracle_evidence_id="oracle-native-1",
        expected_version=5,
    )
    ledger.commit_terminal(**request)
    immutable = ledger.snapshot
    ledger.commit_terminal(**request)
    assert ledger.snapshot == immutable
    with pytest.raises(AbiGateDenied, match="X05_TERMINAL_IMMUTABLE"):
        ledger.commit_terminal(
            **{**request, "publication": replace(publication, verification_id="altered")}
        )


@pytest.mark.parametrize(("policy", "code"), [
    (current_consent(revocation_generation=1), "X02_CONSENT_POLICY_STALE_OR_MISMATCH"),
    (current_consent(expires_at=99), "X02_CONSENT_POLICY_EXPIRED"),
    (replace(current_consent(), signature="bad"), "X02_CONSENT_SIGNATURE_INVALID"),
])
def test_p0_signed_consent_is_independently_current(policy, code: str) -> None:
    with pytest.raises(AbiGateDenied, match=code):
        authority_gate().validate_authorization(
            auth=signed_auth(), tenant_id="tenant-a", run_id="run-a",
            audience="m27.offline", purpose="task-execution",
            policy_generation=4, revocation_generation=0, now=100,
            expected_principal_id="principal-a", expected_delegated_by="owner-a",
            consent_policy=policy,
        )


def test_p0_missing_trusted_principal_and_consent_policy_deny() -> None:
    with pytest.raises(AbiGateDenied, match="X02_EXPECTED_PRINCIPAL_UNBOUND"):
        authority_gate().validate_authorization(
            auth=signed_auth(), tenant_id="tenant-a", run_id="run-a",
            audience="m27.offline", purpose="task-execution",
            policy_generation=4, revocation_generation=0, now=100,
        )
    with pytest.raises(AbiGateDenied, match="X02_CONSENT_POLICY_UNBOUND"):
        authority_gate().validate_authorization(
            auth=signed_auth(), tenant_id="tenant-a", run_id="run-a",
            audience="m27.offline", purpose="task-execution",
            policy_generation=4, revocation_generation=0, now=100,
            expected_principal_id="principal-a", expected_delegated_by="owner-a",
        )


def test_p0_permit_approval_scope_and_epoch_must_bind_t1() -> None:
    digest = action_proposal()[1]
    ledger = OfflineSerializableLedger(
        tenant_id="tenant-a", run_id="run-a", lease_epoch=3,
        budget_cap_microunits=100,
        trusted_approvals={"approval-1": trusted_approval(digest)},
    )
    ledger.register_intent(
        command_id="command-1", intent_id="intent-1", lease_epoch=3,
        intent_digest=digest, quoted_cost_microunits=10, expected_version=0,
    )
    for unexpected in (
        {"command_id": "ghost"},
        {"approval_run_id": "run-b"},
        {"approval_tenant_id": "tenant-b"},
        {"approval_lease_epoch": 4},
        {"intent_id": "other-intent"},
        {"intent_digest": "a" * 64, "approval_intent_digest": "a" * 64},
    ):
        request = dict(
            permit_id="permit-1", command_id="command-1", intent_id="intent-1",
            intent_digest=digest, approval_intent_digest=digest,
            approval_run_id="run-a", approval_tenant_id="tenant-a",
            approval_lease_epoch=3, lease_epoch=3,
            approval_id="approval-1", expected_version=1,
        )
        request.update(unexpected)
        with pytest.raises(AbiGateDenied):
            ledger.acquire_permit(**request)
    assert ledger.snapshot.version == 1


def test_p0_unsettled_reservation_blocks_success_terminal() -> None:
    ledger, _ = ready_ledger(extra_reservation_microunits=1)
    _, _, action = action_proposal()
    snapshot = journal_for(ledger)
    _, publication = publication_proposal(snapshot)
    with pytest.raises(AbiGateDenied, match="X07_UNSETTLED_RESERVATIONS"):
        ledger.commit_terminal(
            snapshot=snapshot, action_proposal=action, publication=publication,
            oracle_label=native_oracle_label(), oracle_evidence_id="oracle-native-1",
            expected_version=ledger.snapshot.version,
        )


def test_p0_distinct_run_mock_ledgers_do_not_share_commands_or_permits() -> None:
    for tenant, run in (("tenant-a", "run-a"), ("tenant-b", "run-b")):
        approval = replace(trusted_approval("a" * 64), tenant_id=tenant, run_id=run)
        ledger = OfflineSerializableLedger(
            tenant_id=tenant, run_id=run, lease_epoch=3,
            budget_cap_microunits=10,
            trusted_approvals={"approval-1": approval},
        )
        ledger.register_intent(
            command_id="command-1", intent_id="intent-1", intent_digest="a" * 64,
            lease_epoch=3, quoted_cost_microunits=1, expected_version=0,
        )
        receipt = ledger.acquire_permit(
            permit_id="permit-1", command_id="command-1", intent_id="intent-1",
            approval_id="approval-1", approval_tenant_id=tenant,
            approval_run_id=run, approval_lease_epoch=3,
            intent_digest="a" * 64, approval_intent_digest="a" * 64,
            lease_epoch=3, expected_version=1,
        )
        assert receipt.consumed is False
        assert ledger.snapshot.reserved_microunits == 1
