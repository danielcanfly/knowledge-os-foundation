"""C02 AR02–05 v2 terminal and adversarial handshakes, fake only."""
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_ar05_reconciled_vertical_experimental import (
    complete_mock_loop,
    prepare_mock_loop,
    sign_observation,
    sign_verification,
)
from knowledge_engine.m27_ar02_kernel_experimental import Denied
from knowledge_engine.m27_ar05_verification_experimental import (
    HardGate,
    VerificationDenied,
    VerificationPublicationGate,
)


def prepared_reconciled():
    loop = prepare_mock_loop()
    loop.v2.record_verified_reconciliation(
        observation=loop.observation, expected_head=5, epoch=1, now=100,
    )
    signed = sign_verification(replace(
        loop.receipt, journal_head_seq=loop.v2.head,
        journal_head_hash=loop.v2.head_hash,
    ))
    return loop, signed


def terminal(loop, signed, publication=None, *, head=6, epoch=1, now=101,
             status="SUCCEEDED"):
    return loop.v2.terminal_cas(
        expected_head=head, epoch=epoch, receipt=signed,
        publication=publication or loop.publication, now=now, status=status,
    )


def test_full_mock_closed_loop_real_accepted_public_apis_and_v2_commit():
    loop, committed, notice = complete_mock_loop()
    assert committed.status == "SUCCEEDED"
    assert committed.publication.status == "ELIGIBLE_PROPOSAL"
    assert committed.publication.client_delivery_proven
    assert committed.publication.server_emission_observed
    assert loop.v2.head == 7 and len(loop.v2.history) == 3
    assert [x.kind for x in loop.v2.history] == [
        "T3_UNKNOWN_EFFECT", "T4_VERIFIED_CONFIRMED_APPLIED", "TERMINAL_SUCCEEDED",
    ]
    assert notice.revision == 2 and not notice.run_state_changed
    assert loop.v2.head == committed.head_seq
    assert loop.v2.terminal_receipt == committed
    assert loop.kernel.read("run-fixture", "tenant-fixture")["spent"] == 2
    assert loop.kernel.network_requests == loop.action.provider_calls == 0


def test_public_ar05_gate_sees_post_reconcile_head_and_valid_proposal():
    loop, signed = prepared_reconciled()
    current = loop.v2.current_snapshot(
        task_id=signed.task_id, task_version=signed.task_version,
        attempt=signed.attempt, outcome_id=signed.outcome_id,
        outcome_digest=signed.outcome_digest,
    )
    gate = VerificationPublicationGate(
        verifier_keys={"fixture-verifier-key":
                       b"C02-fixture-verifier-key-NOT-REAL-IDENTITY"},
        signer_for_key={"fixture-verifier-key": "fixture-verifier"},
        generator_id="fixture-generator",
    )
    proposal = gate.evaluate(
        snapshot=current, receipt=signed, publication=loop.publication, now=101
    )
    assert proposal.status == "ELIGIBLE_PROPOSAL"
    assert current.head_seq == 6 and not current.unknown_effect
    committed = terminal(loop, signed)
    assert committed.prior_head_seq == current.head_seq
    stale = loop.v2.current_snapshot(
        task_id=signed.task_id, task_version=signed.task_version,
        attempt=signed.attempt, outcome_id=signed.outcome_id,
        outcome_digest=signed.outcome_digest,
    )
    with pytest.raises(VerificationDenied, match="TERMINAL_IMMUTABLE"):
        gate.evaluate(
            snapshot=stale, receipt=sign_verification(replace(
                signed, journal_head_seq=stale.head_seq,
                journal_head_hash=stale.head_hash,
            )), publication=loop.publication, now=101,
        )


def test_terminal_stale_head_epoch_and_replay_denied():
    loop, signed = prepared_reconciled()
    for head, epoch in [(5, 1), (7, 1), (6, 2), (6, 0)]:
        with pytest.raises(Denied, match="STALE_HEAD"):
            terminal(loop, signed, head=head, epoch=epoch)
        assert loop.v2.head == 6
    terminal(loop, signed)
    with pytest.raises(Denied, match="TERMINAL_IMMUTABLE"):
        terminal(loop, signed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verification_id", "other-id"),
        ("signer_id", "generator-fixture"),
        ("signer_id", "unknown-signer"),
        ("key_id", "missing-key"),
        ("tenant_id", "other-tenant"),
        ("task_id", "other-task"),
        ("run_id", "other-run"),
        ("attempt", 2),
        ("journal_head_seq", 5),
        ("journal_head_hash", "0" * 64),
        ("lease_epoch", 2),
        ("outcome_digest", "z" * 64),
        ("expires_at", 101),
        ("checked_at", 102),
        ("signature", "f" * 64),
    ],
)
def test_tampered_receipt_denied_with_no_terminal(field, value):
    loop, signed = prepared_reconciled()
    changed = replace(signed, **{field: value})
    # A signature for modified facts is still only a fake fixture; evaluator
    # must check current head and configured verifier identity.
    if field != "signature":
        changed = sign_verification(changed)
    with pytest.raises((Denied, VerificationDenied)):
        terminal(loop, changed)
    assert loop.v2.head == 6 and loop.v2.terminal_receipt is None


@pytest.mark.parametrize("missing", [
    "source", "policy", "effect", "approval", "client_ack",
])
def test_mandatory_gate_missing_denied(missing):
    loop, signed = prepared_reconciled()
    gates = tuple(g for g in signed.hard_gates if g.name != missing)
    invalid = sign_verification(replace(signed, hard_gates=gates))
    with pytest.raises(Denied, match="HARD_GATES"):
        terminal(loop, invalid)
    assert loop.v2.terminal_receipt is None


def test_hard_gate_fail_indeterminate_and_duplicate_denied():
    for gates in [
        (HardGate("source", "indeterminate"),),
        (HardGate("source", "fail"),),
        (HardGate("source", "pass"), HardGate("source", "pass")),
    ]:
        loop, signed = prepared_reconciled()
        if len(gates) != 2:
            extras = tuple(x for x in signed.hard_gates if x.name != "source")
            gates += extras
        changed = sign_verification(replace(signed, hard_gates=gates))
        with pytest.raises((Denied, VerificationDenied)):
            terminal(loop, changed)
        assert loop.v2.head == 6


@pytest.mark.parametrize("change", [
    {"claim_client_delivered": False},
    {"expected_citation_ids": ("other-cite",)},
    {"irreversible": True},
])
def test_publication_mutations_fail_closed(change):
    loop, signed = prepared_reconciled()
    publication = replace(loop.publication, **change)
    if "irreversible" in change:
        frames = (
            replace(publication.frames[0], kind="provisional"),
            publication.frames[1],
        )
        publication = replace(publication, frames=frames)
    with pytest.raises((Denied, VerificationDenied)):
        terminal(loop, signed, publication)
    assert loop.v2.head == 6


@pytest.mark.parametrize("frame_change", [
    {"client_ack_id": None},
    {"citation_ids": ("not-original",)},
    {"verification_id": "forged"},
    {"server_emitted": False},
    {"kind": "progress"},
    {"payload": b""},
])
def test_claimed_client_delivery_and_verified_text_required(frame_change):
    loop, signed = prepared_reconciled()
    publication = replace(loop.publication, frames=(
        replace(loop.publication.frames[0], **frame_change),
        loop.publication.frames[1],
    ))
    with pytest.raises((Denied, VerificationDenied)):
        terminal(loop, signed, publication)
    assert loop.v2.terminal_receipt is None


@pytest.mark.parametrize("change", [
    {"exclusion_generation": 2}, {"revoked": True}, {"excluded": True},
    {"revision": "new"}, {"consent_expires_at": 101},
])
def test_revalidation_at_terminal_catches_source_policy_changes(change):
    loop, signed = prepared_reconciled()
    loop.source.replace(**change)
    with pytest.raises(Denied, match="SOURCE_CONSENT_EXCLUSION"):
        terminal(loop, signed)
    assert loop.v2.head == 6


def test_client_ack_cannot_be_inferred_from_server_emission():
    loop, signed = prepared_reconciled()
    frame = replace(loop.publication.frames[0], client_ack_id=None)
    publication = replace(loop.publication, frames=(frame, loop.publication.frames[1]))
    with pytest.raises(VerificationDenied, match="CLIENT_DELIVERY_UNPROVEN"):
        terminal(loop, signed, publication)


def test_negative_observation_is_not_success_and_no_blind_retry():
    loop = prepare_mock_loop()
    e = replace(
        loop.observation.evidence, status="not_applied",
        authoritative_negative=True, visibility_complete=True,
    )
    negative = sign_observation(replace(loop.observation, evidence=e))
    loop.v2.record_verified_reconciliation(
        observation=negative, expected_head=5, epoch=1, now=100
    )
    signed = sign_verification(replace(
        loop.receipt, journal_head_seq=6, journal_head_hash=loop.v2.head_hash,
    ))
    with pytest.raises(Denied, match="SUCCESS_WITHOUT_APPLIED"):
        terminal(loop, signed)
    assert loop.kernel.network_requests == 0
    assert loop.v2.terminal_receipt is None


def test_terminal_sidecar_is_append_only_with_no_reopening():
    loop, committed, first = complete_mock_loop()
    second = loop.v2.append_postterminal_notice(
        kind="retraction", content=b"withdraw mock fixture text",
    )
    assert (first.revision, first.cursor) == (2, 1)
    assert (second.revision, second.cursor) == (3, 2)
    assert not second.run_state_changed
    assert loop.v2.head == committed.head_seq
    assert loop.v2.terminal_receipt == committed
    assert len(loop.v2.history) == 3
    assert len(loop.v2.notices) == 2


def test_no_post_terminal_reconciliation_and_no_double_charge():
    loop, _, _ = complete_mock_loop()
    with pytest.raises(Denied, match="CONFLICTING_OBSERVATION"):
        loop.v2.record_verified_reconciliation(
            observation=sign_observation(replace(
                loop.observation, observation_id="new",
            )), expected_head=7, epoch=1, now=102,
        )
    before = loop.kernel.read("run-fixture", "tenant-fixture")
    assert not loop.kernel.charge(
        "run-fixture", "tenant-fixture", 5, 1, "reserve-fixture",
        "charge-fixture", 2,
    )
    assert loop.kernel.read("run-fixture", "tenant-fixture") == before


def test_terminal_without_reconciliation_denied():
    loop = prepare_mock_loop()
    with pytest.raises(Denied):
        terminal(loop, loop.receipt, head=5)


def test_reconciliation_duplicate_after_terminal_is_read_only_idempotent():
    loop, committed, _ = complete_mock_loop()
    result = loop.v2.record_verified_reconciliation(
        observation=loop.observation, expected_head=5, epoch=1, now=102,
    )
    assert result.head_seq == 6
    assert loop.v2.terminal_receipt == committed
    assert loop.v2.head == 7


def test_observer_proof_expires_before_terminal_even_if_verifier_extended():
    loop = prepare_mock_loop()
    short = sign_observation(replace(loop.observation, expires_at=105))
    loop.v2.record_verified_reconciliation(
        observation=short, expected_head=5, epoch=1, now=100,
    )
    signed = sign_verification(replace(
        loop.receipt, journal_head_seq=6,
        journal_head_hash=loop.v2.head_hash, expires_at=150,
    ))
    with pytest.raises(Denied, match="OBSERVER_PROOF_EXPIRED"):
        terminal(loop, signed, now=106)
    assert loop.v2.head == 6


def test_terminal_cannot_rebind_task_or_outcome_with_fresh_fake_signature():
    for field, value in [
        ("task_id", "task-changed"), ("task_version", 3),
        ("attempt", 3), ("outcome_id", "outcome-other"),
        ("outcome_digest", "f" * 64),
    ]:
        loop, signed = prepared_reconciled()
        changed = sign_verification(replace(signed, **{field: value}))
        with pytest.raises(Denied, match="OUTCOME_BINDING"):
            terminal(loop, changed)
        assert loop.v2.terminal_receipt is None
