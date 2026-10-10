"""AR09B T0/T1 adversarial evaluator tests; no remote services or release oracle."""

from dataclasses import replace
from hashlib import sha256

import pytest

from knowledge_engine.m27_ar09b_independent_eval_experimental import (
    Charge,
    EvaluationContext,
    OutcomeEvidence,
    PreterminalSegment,
    TrustedObservation,
    evaluate_batch,
    evaluate_case,
    nearest_rank,
)

HEAD = "a" * 64
ARTIFACT = sha256(b"pinned artifact").hexdigest()
ANSWER = b"Cited verified fact."
TEXT_SHA = sha256(ANSWER).hexdigest()


def context():
    return EvaluationContext(
        evaluator_id="eval-independent",
        evaluator_version="offline-v1",
        approved_oracle_ids=frozenset({"separate-offline-oracle"}),
    )


def segment(**overrides):
    values = dict(
        kind="verified_claim",
        payload=ANSWER,
        payload_sha256=TEXT_SHA,
        at_ms=5,
        verified_by="separate-offline-oracle",
        citation_ids=("cite-a",),
        client_received=True,
    )
    values.update(overrides)
    return PreterminalSegment(**values)


def record(**overrides):
    values = dict(
        case_id="case-1",
        workload="QA",
        tenant_id="tenant-a",
        task_id="task-a",
        task_version=1,
        run_id="run-a",
        revision=2,
        journal_head_seq=12,
        journal_head_sha256=HEAD,
        outcome_type="ANSWER",
        terminal_status="SUCCEEDED",
        terminal_durable=True,
        executor_id="executor-a",
        evaluator_id="eval-independent",
        claimed_oracle_id="separate-offline-oracle",
        observed_digest=ARTIFACT,
        rights_granted=True,
        unknown_effect=False,
        started_ms=0,
        terminal_ms=10,
        segments=(segment(),),
        charges=(Charge("attempt-1", "charge-1", 40),),
    )
    values.update(overrides)
    return OutcomeEvidence(**values)


def truth(**overrides):
    values = dict(
        case_id="case-1",
        tenant_id="tenant-a",
        task_id="task-a",
        task_version=1,
        run_id="run-a",
        revision=2,
        journal_head_seq=12,
        journal_head_sha256=HEAD,
        oracle_id="separate-offline-oracle",
        oracle_available=True,
        offline_observer_separate=True,
        expected_outcome="ANSWER",
        expected_digest=ARTIFACT,
        expected_refusal=False,
        verified_segment_sha256=frozenset({TEXT_SHA}),
        source_rights_checked=True,
    )
    values.update(overrides)
    return TrustedObservation(**values)


def decision(e=None, o=None):
    return evaluate_case(e or record(), o or truth(), context())


def test_positive_qa_and_first_verified_client_text_precedes_terminal():
    r = decision()
    assert r.task_success is True
    assert r.terminal_correct is True
    assert r.denied is False
    assert r.first_verified_text_ms == 5
    assert r.cost_microunits == 40
    assert r.quality_score is None
    assert r.quality_status == "BLOCKED_EXTERNAL_ORACLE"
    assert r.reason == "ACCEPTED_OFFLINE_FIXTURE_ONLY"


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ({"tenant_id": "other-tenant"}, "IDENTITY_OR_HEAD_MISMATCH"),
        ({"task_id": "wrong-task"}, "IDENTITY_OR_HEAD_MISMATCH"),
        ({"run_id": "wrong-run"}, "IDENTITY_OR_HEAD_MISMATCH"),
        ({"revision": 1}, "IDENTITY_OR_HEAD_MISMATCH"),
        ({"journal_head_seq": 11}, "IDENTITY_OR_HEAD_MISMATCH"),
        ({"journal_head_sha256": "b" * 64}, "IDENTITY_OR_HEAD_MISMATCH"),
        ({"evaluator_id": "executor-a"}, "EVALUATOR_NOT_INDEPENDENT"),
        ({"claimed_oracle_id": "executor-a"}, "ORACLE_NOT_INDEPENDENT"),
        ({"observed_digest": "b" * 64}, "OUTCOME_DIGEST_MISMATCH"),
        ({"rights_granted": False}, "RIGHTS_WITHHELD"),
        ({"unknown_effect": True}, "UNKNOWN_EFFECT_UNRESOLVED"),
        ({"terminal_durable": False}, "TERMINAL_NOT_DURABLE"),
        ({"terminal_status": "FAILED"}, "TERMINAL_OUTCOME_MISMATCH"),
    ],
)
def test_fail_closed_identity_rights_unknown_and_terminal(tamper, reason):
    r = decision(e=record(**tamper))
    assert r.task_success is False
    assert r.reason == reason


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ({"oracle_available": False}, "ORACLE_UNAVAILABLE"),
        ({"offline_observer_separate": False}, "ORACLE_NOT_INDEPENDENT"),
        ({"oracle_id": "forged-oracle"}, "ORACLE_NOT_APPROVED"),
        ({"source_rights_checked": False}, "RIGHTS_NOT_INDEPENDENTLY_CHECKED"),
        ({"expected_digest": None}, "OUTCOME_PROOF_MISSING"),
        ({"journal_head_seq": 99}, "IDENTITY_OR_HEAD_MISMATCH"),
    ],
)
def test_oracle_evidence_cannot_be_self_asserted(tamper, reason):
    r = decision(o=truth(**tamper))
    assert r.task_success is False
    assert r.reason == reason


def test_missing_oracle_and_untrusted_fixture_labels_never_pass():
    r = evaluate_case(record(), None, context())
    assert r.task_success is False
    assert r.terminal_correct is None
    assert r.reason == "ORACLE_UNAVAILABLE"
    assert r.quality_status == "BLOCKED_EXTERNAL_ORACLE"


@pytest.mark.parametrize(
    "segments",
    [
        (),
        (segment(kind="progress"),),
        (segment(at_ms=10),),
        (segment(at_ms=12),),
        (segment(payload=b"  ", payload_sha256=sha256(b"  ").hexdigest()),),
        (segment(payload=b"!!!", payload_sha256=sha256(b"!!!").hexdigest()),),
        (segment(payload=bytes([255]), payload_sha256=sha256(bytes([255])).hexdigest()),),
        (segment(payload_sha256="b" * 64),),
        (segment(client_received=False),),
        (segment(citation_ids=()),),
        (segment(verified_by="executor-a"),),
        (segment(payload=b"terminal", payload_sha256=sha256(b"terminal").hexdigest()),),
    ],
)
def test_progress_terminal_only_unverified_or_unreceived_text_is_not_success(segments):
    r = decision(e=record(segments=segments))
    assert r.task_success is False
    assert r.stream_ok is False
    assert r.reason == "NO_VERIFIED_PRETERMINAL_TEXT"


@pytest.mark.parametrize("kind", ["ARTIFACT", "ACTION"])
def test_artifact_and_mock_remote_state_require_independent_digest(kind):
    e = record(workload="CODING" if kind == "ARTIFACT" else "ACTION",
               outcome_type=kind, segments=(),
               action_resource_version="fixture-rev-1" if kind == "ACTION" else None)
    o = truth(expected_outcome=kind,
              independently_observed_resource_version="fixture-rev-1" if kind == "ACTION" else None)
    assert decision(e, o).task_success
    assert not decision(e, replace(o, expected_digest="b" * 64)).task_success
    if kind == "ACTION":
        assert not decision(replace(e, action_resource_version=None), o).task_success
        without_proof = replace(o, independently_observed_resource_version=None)
        assert not decision(e, without_proof).task_success


@pytest.mark.parametrize(
    ("outcome", "terminal", "refused"),
    [("ABSTAIN", "SUCCEEDED", True), ("CANCELLED", "CANCELLED", False),
     ("FAILED", "FAILED", False)],
)
def test_terminal_correctness_is_not_task_success(outcome, terminal, refused):
    e = record(outcome_type=outcome, terminal_status=terminal,
               refused=refused, segments=(), observed_digest=None)
    o = truth(expected_outcome=outcome, expected_digest=None,
              expected_refusal=refused, verified_segment_sha256=frozenset())
    r = decision(e, o)
    assert r.terminal_correct is True
    assert r.task_success is False
    assert r.denied is refused
    assert r.reason == "NON_SUCCESS_TERMINAL"


def test_refusal_accuracy_is_separate_from_task_success():
    e = record(outcome_type="ABSTAIN", terminal_status="SUCCEEDED", refused=True,
               observed_digest=None, segments=())
    o = truth(expected_outcome="ABSTAIN", expected_digest=None, expected_refusal=True)
    e2 = replace(e, case_id="case-2", run_id="run-2", refused=False)
    o2 = replace(o, case_id="case-2", run_id="run-2")
    metrics = evaluate_batch((e, e2), {"case-1": o, "case-2": o2}, context())
    assert metrics.success_numerator == 0
    assert metrics.success_denominator == 2
    assert metrics.refusal_known == 2
    assert metrics.refusal_correct == 1
    assert metrics.refusal_accuracy == .5


def test_cost_success_denominator_contains_fail_cancel_unknown_and_duplicates():
    a = record()
    b = replace(a, case_id="case-2", run_id="run-2", unknown_effect=True,
                charges=(Charge("attempt-2", "charge-2", 10),))
    c = replace(a, case_id="case-3", run_id="run-3", outcome_type="CANCELLED",
                terminal_status="CANCELLED", segments=(), observed_digest=None,
                charges=(Charge("attempt-3", "charge-3", 30),))
    observations = {
        "case-1": truth(),
        "case-2": replace(truth(), case_id="case-2", run_id="run-2"),
        "case-3": replace(truth(), case_id="case-3", run_id="run-3",
                          expected_outcome="CANCELLED", expected_digest=None),
    }
    m = evaluate_batch((a, b, c), observations, context())
    assert (m.success_numerator, m.success_denominator) == (1, 3)
    assert m.total_cost_microunits == 80
    assert m.cost_per_success_microunits == 80
    assert m.by_workload["QA"].assigned == 3
    assert m.unknown_effect_count == 1


def test_missing_spend_or_no_success_cannot_be_reported_as_zero():
    m = evaluate_batch((record(charges=(Charge("a", "a", None),)),),
                       {"case-1": truth()}, context())
    assert m.cost_per_success_microunits is None
    assert m.total_cost_microunits is None
    m = evaluate_batch((record(unknown_effect=True),), {"case-1": truth()}, context())
    assert m.cost_per_success_microunits is None


def test_duplicate_fee_and_late_bill_are_not_hidden():
    e = record(charges=(Charge("a", "same", 5), Charge("a", "same", 5)))
    assert decision(e).reason == "DUPLICATE_FEE"
    e = record(charges=(Charge("a", "a", 5), Charge("b", "b", 7, late=True)),
               late_billing_reconciled=False)
    assert decision(e).reason == "LATE_BILLING_UNRECONCILED"
    r = decision(e=replace(e, late_billing_reconciled=True))
    assert r.task_success
    assert r.cost_microunits == 12


def test_cross_case_duplicate_charge_rejected_even_distinct_case_ids():
    first = record()
    second = replace(first, case_id="case-2", run_id="run-2")
    m = evaluate_batch((first, second), {"case-1": truth(),
        "case-2": replace(truth(), case_id="case-2", run_id="run-2")}, context())
    assert m.success_numerator == 0
    assert m.security_violations >= 2
    assert all(x.reason == "DUPLICATE_FEE" for x in m.cases)


def test_latency_buckets_nearest_rank_and_missing_text():
    assert nearest_rank((3, 11, 4, 18, 7), .95) == 18
    m = evaluate_batch((record(),), {"case-1": truth()}, context())
    assert m.latency_ms_p50 == 10
    assert m.latency_ms_p95 == 10
    assert m.latency_buckets == {"lt_1000": 1, "1000_4999": 0,
                                 "5000_14999": 0, "gte_15000": 0}
    assert m.first_verified_text_ms_p50 == 5


def test_non_negative_latency_and_cost_contract_enforced():
    for e in [record(terminal_ms=-1), record(started_ms=11),
              record(charges=(Charge("a", "a", -1),))]:
        r = decision(e)
        assert not r.task_success
        assert r.reason == "INVALID_MEASUREMENT"


def test_missing_observation_in_batch_stays_in_denominator():
    m = evaluate_batch((record(),), {}, context())
    assert m.success_denominator == 1
    assert m.success_numerator == 0
    assert m.evidence_invalidity_count == 1


def test_no_external_quality_scoring_even_if_fixture_label_claims_100():
    r = decision()
    assert r.quality_score is None
    assert r.quality_status == "BLOCKED_EXTERNAL_ORACLE"


def test_refusal_labels_from_untrusted_oracle_cannot_inflate_accuracy():
    e = record(outcome_type="ABSTAIN", terminal_status="SUCCEEDED",
               refused=True, observed_digest=None, segments=())
    fake = truth(oracle_available=False, expected_refusal=True)
    m = evaluate_batch((e,), {"case-1": fake}, context())
    assert m.refusal_known == 0
    assert m.refusal_accuracy is None
    assert m.success_numerator == 0


def test_missing_assigned_case_and_unmatched_catalog_remain_failures():
    ctx = replace(context(), assigned_case_ids=frozenset({"case-1", "case-2"}))
    m = evaluate_batch((record(),), {"case-1": truth()}, ctx)
    assert m.success_denominator == 2
    assert m.success_numerator == 1
    assert m.by_workload["UNREPORTED"].assigned == 1
    assert m.cost_per_success_microunits is None


def test_unassigned_case_from_candidate_is_blocked():
    ctx = replace(context(), assigned_case_ids=frozenset({"a-different-case"}))
    assert evaluate_case(record(), truth(), ctx).reason == "UNASSIGNED_CASE"
