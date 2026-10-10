"""Independent C02 T4/terminal outcome falsification, mock fixtures only."""
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_ar05_reconciled_vertical_experimental import (
    complete_mock_loop,
    prepare_mock_loop,
    sign_observation,
    sign_verification,
)
from knowledge_engine.m27_ar02_kernel_experimental import Denied
from knowledge_engine.m27_ar09b_independent_eval_experimental import Charge
from knowledge_engine.m27_ar09c_c02_outcome_oracle_experimental import (
    MOCK_ONLY_FUNCTIONAL_SUCCESS,
    assess_c02,
    assess_manifest,
)


def successful():
    loop, terminal, notice = complete_mock_loop()
    signed = sign_verification(replace(
        loop.receipt, journal_head_seq=6,
        journal_head_hash=loop.v2.history[1].event_hash,
    ))
    return loop, terminal, notice, signed


def test_positive_real_public_c02_path_and_no_real_success():
    loop, terminal, notice, signed = successful()
    result = assess_c02(loop, terminal, signed_receipt=signed, notice=notice)
    assert result.label == MOCK_ONLY_FUNCTIONAL_SUCCESS
    assert result.ar09b.reason == "ACCEPTED_OFFLINE_FIXTURE_ONLY"
    assert result.ar09b.task_success
    assert result.mock_terminal_observed
    assert result.original_nonterminal_unknown
    assert result.no_provider and result.no_real_tool and result.no_durable
    assert not result.authorized_task_success
    assert result.real_grade == "UNVERIFIED"
    assert result.real_cost == "UNVERIFIED"
    assert result.independent_holdout == "UNVERIFIED"
    assert loop.kernel.network_requests == loop.action.provider_calls == 0
    assert loop.kernel.read("run-fixture", "tenant-fixture")["terminal"] is False


def test_original_unknown_alone_never_succeeds():
    loop = prepare_mock_loop()
    result = assess_c02(loop, None, signed_receipt=None)
    assert result.label != MOCK_ONLY_FUNCTIONAL_SUCCESS
    assert not result.ar09b.task_success
    assert result.original_nonterminal_unknown
    assert result.no_durable


@pytest.mark.parametrize("change", [
    {"signature": "0" * 64},
    {"tenant_id": "cross-tenant"},
    {"lease_epoch": 77},
    {"expires_at": 101},
    {"observation_id": "injected-duplicate"},
    {"expected_head": 6},
])
def test_tampered_observer_false_in_evaluator(change):
    loop, terminal, notice, signed = successful()
    loop.observation = replace(loop.observation, **change)
    result = assess_c02(loop, terminal, signed_receipt=signed, notice=notice)
    assert not result.ar09b.task_success
    assert result.label != MOCK_ONLY_FUNCTIONAL_SUCCESS


def test_duplicate_and_conflicting_observer_denied_by_c02():
    loop = prepare_mock_loop()
    receipt = loop.v2.record_verified_reconciliation(
        observation=loop.observation, expected_head=5, epoch=1, now=100,
    )
    assert receipt.head_seq == 6
    with pytest.raises(Denied, match="CONFLICTING_OBSERVATION"):
        loop.v2.record_verified_reconciliation(
            observation=sign_observation(replace(
                loop.observation, observation_id="conflict",
            )), expected_head=5, epoch=1, now=101,
        )
    with pytest.raises(Denied, match="DUPLICATE_STALE_REPLAY"):
        loop.v2.record_verified_reconciliation(
            observation=loop.observation, expected_head=6, epoch=1, now=101,
        )


@pytest.mark.parametrize("change", [
    {"signature": "0" * 64},
    {"task_id": "other-task"},
    {"journal_head_seq": 5},
    {"journal_head_hash": "0" * 64},
    {"outcome_id": "generator-controlled-other"},
    {"outcome_digest": "f" * 64},
])
def test_verifier_tampering_falsifies_oracle(change):
    loop, terminal, notice, signed = successful()
    result = assess_c02(
        loop, terminal, signed_receipt=replace(signed, **change),
        notice=notice,
    )
    assert not result.ar09b.task_success
    assert result.label != MOCK_ONLY_FUNCTIONAL_SUCCESS


@pytest.mark.parametrize("change", [
    {"revoked": True},
    {"revision": "stale"},
    {"exclusion_generation": 99},
    {"consent_expires_at": 100},
])
def test_source_revocation_revision_and_consent_falsified(change):
    loop, terminal, notice, signed = successful()
    loop.source.replace(**change)
    result = assess_c02(loop, terminal, signed_receipt=signed, notice=notice)
    assert not result.ar09b.task_success


def test_accepted_head_drift_falsified():
    loop, terminal, notice, signed = successful()
    loop.kernel.takeover("run-fixture", "tenant-fixture", 5)
    result = assess_c02(loop, terminal, signed_receipt=signed, notice=notice)
    assert not result.ar09b.task_success


def test_client_ack_removed_after_terminal_cannot_pass():
    loop, terminal, notice, signed = successful()
    claim, last = loop.publication.frames
    loop.publication = replace(
        loop.publication, frames=(replace(claim, client_ack_id=None), last),
    )
    result = assess_c02(loop, terminal, signed_receipt=signed, notice=notice)
    assert not result.ar09b.task_success
    assert result.ar09b.stream_ok is False or result.ar09b.evidence_valid is False


def test_progress_only_verified_claim_removed_cannot_pass():
    loop, terminal, notice, signed = successful()
    claim, last = loop.publication.frames
    loop.publication = replace(
        loop.publication, frames=(replace(claim, kind="progress"), last),
    )
    result = assess_c02(loop, terminal, signed_receipt=signed, notice=notice)
    assert not result.ar09b.task_success


def test_native_original_bytes_and_citation_tampering_falsified():
    loop, terminal, notice, signed = successful()
    observed = replace(
        loop.publication.observed_evidence, content_bytes=b"stale bytes",
    )
    loop.publication = replace(loop.publication, observed_evidence=observed)
    assert not assess_c02(
        loop, terminal, signed_receipt=signed, notice=notice,
    ).ar09b.task_success

    loop, terminal, notice, signed = successful()
    original = loop.publication.original_evidence
    cited = replace(original.citations[0], source_revision="rev-stale")
    loop.publication = replace(
        loop.publication,
        observed_evidence=replace(
            original, citations=(cited,),
        ),
    )
    assert not assess_c02(
        loop, terminal, signed_receipt=signed, notice=notice,
    ).ar09b.task_success


def test_charge_mismatch_duplicate_and_missing_price_falsified():
    loop, terminal, notice, signed = successful()
    for charges in [
        (Charge("1", "charge-fixture", 3),),
        (Charge("1", "charge-fixture", 2), Charge("2", "charge-fixture", 2)),
        (Charge("1", "charge-fixture", None),),
    ]:
        result = assess_c02(
            loop, terminal, signed_receipt=signed, notice=notice, charges=charges,
        )
        assert not result.ar09b.task_success
        assert result.label != MOCK_ONLY_FUNCTIONAL_SUCCESS


def test_forged_evaluator_not_approved():
    loop, terminal, notice, signed = successful()
    result = assess_c02(
        loop, terminal, signed_receipt=signed, notice=notice,
        evaluator_id="fixture-generator",
    )
    assert not result.ar09b.task_success


def test_postterminal_notice_mutation_falsifies():
    loop, terminal, notice, signed = successful()
    result = assess_c02(
        loop, terminal, signed_receipt=signed,
        notice=replace(notice, revision=300),
    )
    assert not result.ar09b.task_success


def test_terminal_receipt_or_event_chain_tamper_falsifies():
    loop, terminal, notice, signed = successful()
    forged = replace(terminal, head_hash="f" * 64)
    assert not assess_c02(
        loop, forged, signed_receipt=signed, notice=notice,
    ).ar09b.task_success


def test_manifest_counts_denied_unreported_and_forged_no_cherry_pick():
    loop, terminal, notice, signed = successful()
    passed = assess_c02(loop, terminal, signed_receipt=signed, notice=notice,
                        case_id="positive")
    denied = assess_c02(loop, terminal, signed_receipt=replace(
        signed, signature="0" * 64), notice=notice, case_id="denied",
        charges=())
    pending = assess_c02(prepare_mock_loop(), None, signed_receipt=None,
                         case_id="unknown", charges=())
    stats = assess_manifest(
        (passed, denied, pending),
        assigned_case_ids=frozenset({
            "positive", "denied", "unknown", "unreported",
        }),
    )
    assert stats.success_numerator == 1
    assert stats.success_denominator == 4
    assert stats.success_rate == .25
    assert stats.total_cost_microunits is None
    assert stats.quality_status == "BLOCKED_EXTERNAL_ORACLE"


def test_cross_case_charge_collision_is_real_batch_negative_control():
    left_loop, left_terminal, left_notice, left_signed = successful()
    right_loop, right_terminal, right_notice, right_signed = successful()
    left = assess_c02(left_loop, left_terminal, signed_receipt=left_signed,
                      notice=left_notice, case_id="case-1")
    right = assess_c02(right_loop, right_terminal, signed_receipt=right_signed,
                       notice=right_notice, case_id="case-2")
    assert left.ar09b.task_success and right.ar09b.task_success
    result = assess_manifest((left, right),
                             assigned_case_ids=frozenset({"case-1", "case-2"}))
    assert result.success_denominator == 2
    assert result.success_numerator == 0
    assert {d.reason for d in result.cases} == {"DUPLICATE_FEE"}


def test_confirmed_not_applied_does_not_masquerade_as_task_success():
    loop = prepare_mock_loop()
    negative = sign_observation(replace(
        loop.observation,
        evidence=replace(
            loop.observation.evidence,
            status="not_applied", authoritative_negative=True,
            visibility_complete=True,
        ),
    ))
    receipt = loop.v2.record_verified_reconciliation(
        observation=negative, expected_head=5, epoch=1, now=100,
    )
    assert receipt.effect == "CONFIRMED_NOT_APPLIED"
    loop.observation = negative
    signed = sign_verification(replace(
        loop.receipt, journal_head_seq=6, journal_head_hash=loop.v2.head_hash,
    ))
    with pytest.raises(Denied, match="SUCCESS_WITHOUT_APPLIED"):
        loop.v2.terminal_cas(
            expected_head=6, epoch=1, receipt=signed,
            publication=loop.publication, now=101, status="SUCCEEDED",
        )
    decision = assess_c02(loop, None, signed_receipt=signed)
    assert not decision.ar09b.task_success
    assert decision.no_provider and decision.no_durable
