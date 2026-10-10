"""Synthetic adversarial AR10 candidate-only governance tests (no external effects)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from knowledge_engine.m27_w4_ar09_independent_harness_v1_experimental import DenominatorLedger
from knowledge_engine.m27_w4_e09b_blind_gate_v1_experimental import AdmissionDecision
from knowledge_engine.m27_w4_p09_external_evidence_v1_experimental import Admission
from knowledge_engine.m27_w4_t09_transport_evidence_v1_experimental import StreamVerdict
from knowledge_engine.m27_w5_l10_ar10_candidate_governance_v1_experimental import (
    NAMESPACE,
    AR10CandidateGovernanceV1,
    Denied,
    ImprovementProposal,
    MatchedOfflineCohort,
    OfflineCase,
    RightsSnapshot,
    W4FixtureSeams,
    digest,
    evaluate_matched_offline,
)

NOW = 10_000


def H(value):
    return digest(value)


@pytest.fixture
def proposal():
    return ImprovementProposal(
        namespace=NAMESPACE,
        proposal_id="candidate.1",
        tenant_id="tenant.a",
        principal_id="writer.a",
        origin_run_id="run.1",
        origin_source_id="source.1",
        origin_subject_id="subject.1",
        source_classification="SYNTHETIC",
        purpose="fixture.review",
        consent_ref="consent.fixture.1",
        consent_generation=4,
        exclusion_generation=2,
        tombstone_generation=0,
        retention_until_ms=30_000,
        created_ms=100,
        expires_ms=20_000,
        source_revision="rev.1",
        source_sha256=H("source"),
        base_artifact_sha256=H("base"),
        control_artifact_sha256=H("control"),
        runner_sha256=H("runner"),
        candidate_artifact_sha256=H("candidate"),
        candidate_type="routing",
        manifest_sha256=H("manifest"),
        rubric_sha256=H("rubric"),
        dataset_version="offline.v1",
        version_tag="candidate.v1",
        rollback_ref="baseline.known.1",
        reviewer_id="reviewer.external.fixture",
        proposed_effect="routing_rank_delta_only",
    )


@pytest.fixture
def rights(proposal):
    return RightsSnapshot(
        tenant_id=proposal.tenant_id,
        purpose=proposal.purpose,
        source_id=proposal.origin_source_id,
        subject_id=proposal.origin_subject_id,
        revision=proposal.source_revision,
        consent_generation=proposal.consent_generation,
        exclusion_generation=proposal.exclusion_generation,
        tombstone_generation=proposal.tombstone_generation,
        consent_active=True,
        source_revoked=False,
        valid_until_ms=25_000,
        fixture_only=True,
    )


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "scratch.sqlite3"


@pytest.fixture
def seams():
    return W4FixtureSeams(
        e09h=DenominatorLedger(
            assigned=2,
            eligible=2,
            not_eligible=0,
            accepted=0,
            rejected=1,
            partial=0,
            abstain=0,
            unknown=1,
            success_rate=0.0,
            missing_cases=(),
            duplicate_cases=(),
            duplicate_task_ids=(),
            unassigned_cases=(),
            cost_micros=None,
            cost_per_verified_outcome_micros=None,
            qa_interactive_p95_ms=None,
            long_task_p95_ms=None,
            latency_authority="LOCAL_ONLY",
            release_certification="NOT_CERTIFIED",
            receipts=(),
        ),
        d09={"verdict": "W4_D09_CORPUS_NOT_ADMITTED"},
        t09=StreamVerdict(
            status="LOCAL_ONLY",
            delivery="UNVERIFIED",
            product_ttft="UNVERIFIED",
            first_server_text_ms=None,
            first_cited_ms=None,
            final_request_ms=None,
            eligible_answer=False,
            client_ack_class="UNVERIFIED",
            event_count=0,
        ),
        p09=Admission(
            verdict="P09_AUTHORITY_EVIDENCE_NOT_ADMITTED",
            reasons=(),
            classifications={},
            cost_micros=None,
            accepted_outcome=False,
            evidence_digest=None,
        ),
        e09b=AdmissionDecision(
            status="E09B_PHASE_B_BLOCKED_EVIDENCE_DEBT",
            reasons=("SOURCE_BLOCKED",),
            candidate_commit="0" * 40,
            manifest_sha256=H("manifest"),
            decision_sha256=H("blocked"),
            official_evaluation_ran=False,
            release_certified=False,
        ),
    )


@pytest.fixture
def cohort(proposal):
    return MatchedOfflineCohort(
        version=proposal.dataset_version,
        rubric_sha256=proposal.rubric_sha256,
        source_sha256=proposal.source_sha256,
        control_sha256=proposal.control_artifact_sha256,
        candidate_sha256=proposal.candidate_artifact_sha256,
        assigned=("c1", "c2", "c3"),
        baseline=(
            OfflineCase("c1", "qa", "ACCEPTED", 12, attempts=2),
            OfflineCase("c2", "qa", "FAILED", 11),
            OfflineCase("c3", "coding", "TIMEOUT", 20),
        ),
        candidate=(
            OfflineCase("c1", "qa", "ACCEPTED", 10),
            OfflineCase("c2", "qa", "ACCEPTED", 13, attempts=3),
            OfflineCase("c3", "coding", "PARTIAL", 22),
        ),
    )


def test_synthetic_positive_restart_cas_and_inert_receipts(
    db_path, proposal, rights, seams, cohort
):
    with AR10CandidateGovernanceV1(db_path) as engine:
        d = engine.register(proposal, rights, NOW, "request.register")
        assert d.state == "DRAFT" and d.version == 0
        first = engine.lease(proposal.proposal_id, "worker.1", 0, NOW, NOW + 900)
        d = engine.advance(
            proposal.proposal_id, first, rights, NOW, "request.eligibility", "ELIGIBILITY_REVIEW"
        )
        assert d.state == "ELIGIBILITY_REVIEW"
        evidence = evaluate_matched_offline(proposal, cohort, seams)
        assert evidence.status == "LOCAL_FIXTURE_REVIEW"
        assert evidence.denominator == 3 and evidence.candidate_accepted == 2
        assert evidence.control_accepted == 1 and evidence.candidate_cost_micros == 45
        assert evidence.control_cost_micros == 43
        assert evidence.per_stratum == (("coding", 1, 0, 0), ("qa", 2, 1, 2))
        assert not evidence.promotion_eligible
        next_lease = engine.lease(proposal.proposal_id, "worker.1", 1, NOW, NOW + 900)
        d = engine.advance(
            proposal.proposal_id,
            next_lease,
            rights,
            NOW,
            "request.offline",
            "OFFLINE_REVIEW",
            evidence,
            proposal.reviewer_id,
        )
        assert d.state == "OFFLINE_REVIEW" and d.tool_effects == d.release_writes == 0
        expected_head = d.head
        assert len(engine.journal_rows()) == 3
    with AR10CandidateGovernanceV1(db_path) as reopened:
        got = reopened.inspect(proposal.proposal_id)
        assert got.state == "OFFLINE_REVIEW" and got.head == expected_head
        assert (
            reopened.advance(
                proposal.proposal_id,
                next_lease,
                rights,
                NOW,
                "request.offline",
                "OFFLINE_REVIEW",
                evidence,
                proposal.reviewer_id,
            ).reason
            == "IDEMPOTENT"
        )
        blocked_lease = reopened.lease(proposal.proposal_id, "worker.1", 2, NOW, NOW + 800)
        blocked = reopened.advance(
            proposal.proposal_id, blocked_lease, rights, NOW, "request.release", "REL02"
        )
        assert blocked.state == "OFFLINE_REVIEW"
        assert blocked.reason == "G09_EXTERNAL_BLOCKED"
        assert blocked.tool_effects == blocked.release_writes == 0
        assert len(reopened.journal_rows()) == 4


# Every named row is a distinct adversarial rejection fixture, not a repeated smoke test.
PROPOSAL_ATTACKS = [
    ("missing_consent", {"consent_ref": ""}, {}, "REJECTED"),
    ("explicit_none_consent", {"consent_ref": "none"}, {}, "REJECTED"),
    ("retention_expired", {"retention_until_ms": 9999}, {}, "EXPIRED"),
    ("proposal_expired", {"expires_ms": 9999}, {}, "EXPIRED"),
    ("future_creation", {"created_ms": 12000}, {}, "EXPIRED"),
    ("tenant_crossover", {}, {"tenant_id": "tenant.b"}, "REJECTED"),
    ("purpose_crossover", {}, {"purpose": "other"}, "REJECTED"),
    ("source_crossover", {}, {"source_id": "source.9"}, "REJECTED"),
    ("subject_crossover", {}, {"subject_id": "subject.9"}, "REJECTED"),
    ("revision_changed", {}, {"revision": "rev.2"}, "QUARANTINED"),
    ("consent_generation_stale", {}, {"consent_generation": 5}, "QUARANTINED"),
    ("exclusion_generation_stale", {}, {"exclusion_generation": 3}, "QUARANTINED"),
    ("tombstone_generation_stale", {}, {"tombstone_generation": 1}, "QUARANTINED"),
    ("revoked_consent", {}, {"consent_active": False}, "REJECTED"),
    ("revoked_source", {}, {"source_revoked": True}, "QUARANTINED"),
    ("source_rights_expired", {}, {"valid_until_ms": 9999}, "REJECTED"),
    ("untrusted_external_rights", {}, {"fixture_only": False}, "REJECTED"),
    ("contaminated_holdout", {"contaminated": True}, {}, "QUARANTINED"),
    ("tainted_source", {"tainted": True}, {}, "QUARANTINED"),
    ("revoked_proposal_source", {"source_revoked": True}, {}, "QUARANTINED"),
    ("real_user_content", {"source_classification": "USER_CONTENT"}, {}, "REJECTED"),
    ("real_source", {"source_classification": "REAL"}, {}, "REJECTED"),
    ("secret_source", {"source_classification": "SECRET"}, {}, "REJECTED"),
    ("hidden_holdout", {"source_classification": "HIDDEN_HOLDOUT"}, {}, "REJECTED"),
    ("cross_tenant_trace", {"source_classification": "CROSS_TENANT"}, {}, "REJECTED"),
    ("invalid_candidate_type", {"candidate_type": "grant"}, {}, "REJECTED"),
    ("schema_namespace_changed", {"namespace": "ar06.memory/v1"}, {}, "REJECTED"),
    ("missing_origin_principal", {"principal_id": ""}, {}, "REJECTED"),
    ("bad_artifact_digest", {"candidate_artifact_sha256": "forged"}, {}, "REJECTED"),
    ("bad_runner_digest", {"runner_sha256": "forged"}, {}, "REJECTED"),
    ("bad_source_digest", {"source_sha256": "forged"}, {}, "REJECTED"),
    ("bad_rubric_digest", {"rubric_sha256": "forged"}, {}, "REJECTED"),
    ("self_review", {"reviewer_id": "writer.a"}, {}, "REJECTED"),
    ("ACL_change", {"proposed_effect": "ACL_OVERRIDE"}, {}, "REJECTED"),
    ("journal_authority_change", {"proposed_effect": "AR02_JOURNAL_AUTHORITY"}, {}, "REJECTED"),
    ("ar04_tool_grant", {"proposed_effect": "AR04_TOOL_GRANT"}, {}, "REJECTED"),
    ("evaluator_grade_rewrite", {"proposed_effect": "REWRITE_INDEPENDENT_ORACLE"}, {}, "REJECTED"),
    ("source_consent_rewrite", {"proposed_effect": "CONSENT_OVERRIDE"}, {}, "REJECTED"),
    ("budget_limit_rewrite", {"proposed_effect": "COST_LIMIT_RELAXATION"}, {}, "REJECTED"),
    ("release_gate_override", {"proposed_effect": "REL02_OVERRIDE"}, {}, "REJECTED"),
    (
        "tool_privilege_escalation",
        {"candidate_type": "tool-policy", "proposed_effect": "tool_broaden_permission"},
        {},
        "REJECTED",
    ),
    (
        "tool_policy_wrong_type",
        {"candidate_type": "tool-policy", "proposed_effect": "routing_rank_delta_only"},
        {},
        "REJECTED",
    ),
    ("negative_consent_generation", {"consent_generation": -1}, {}, "REJECTED"),
    ("bad_rollback_pointer", {"rollback_ref": ""}, {}, "REJECTED"),
]


@pytest.mark.parametrize(
    ("attack", "proposal_patch", "rights_patch", "expected"),
    PROPOSAL_ATTACKS,
    ids=[x[0] for x in PROPOSAL_ATTACKS],
)
def test_adversarial_proposal_denied(
    tmp_path, proposal, rights, attack, proposal_patch, rights_patch, expected
):
    del attack
    p = replace(proposal, **proposal_patch)
    r = replace(rights, **rights_patch)
    with AR10CandidateGovernanceV1(tmp_path / "denied.db") as engine:
        decision = engine.register(p, r, NOW, "req.bad.1")
        assert decision.state == expected
        assert decision.tool_effects == decision.release_writes == 0
        assert engine.inspect(p.proposal_id).state == expected


def _tamper_result(cohort, update, part, index=0):
    changed = list(getattr(cohort, part))
    changed[index] = replace(changed[index], **update)
    return replace(cohort, **{part: tuple(changed)})


COMPARISON_ATTACKS = [
    "missing_candidate_case",
    "missing_baseline_case",
    "duplicated_candidate_case",
    "duplicate_assignments",
    "wrong_control_sha",
    "wrong_candidate_sha",
    "wrong_source_sha",
    "wrong_rubric_sha",
    "wrong_dataset_version",
    "hidden_labels",
    "external_custody",
    "nonfixture",
    "changed_weights",
    "self_scored",
    "unknown_cost",
    "missing_baseline_cost",
    "negative_cost",
    "zero_attempts",
    "safety_regression",
    "unknown_effect",
    "revoked_case_source",
    "changed_stratum",
    "adverse_unknown_status",
    "illegal_status",
    "empty_population",
    "unassigned_candidate",
    "forged_d09",
    "forged_e09b",
    "forged_e09b_release",
    "forged_ttft",
    "forged_billing",
    "forged_release",
    "untrusted_e09h_class",
]


@pytest.mark.parametrize("attack", COMPARISON_ATTACKS)
def test_matched_control_adversarial_fixture_ineligible(proposal, cohort, seams, attack):
    if attack == "missing_candidate_case":
        cohort = replace(cohort, candidate=cohort.candidate[:-1])
    elif attack == "missing_baseline_case":
        cohort = replace(cohort, baseline=cohort.baseline[:-1])
    elif attack == "duplicated_candidate_case":
        cohort = replace(cohort, candidate=cohort.candidate + (cohort.candidate[0],))
    elif attack == "duplicate_assignments":
        cohort = replace(cohort, assigned=("c1", "c1", "c3"))
    elif attack == "wrong_control_sha":
        cohort = replace(cohort, control_sha256=H("other"))
    elif attack == "wrong_candidate_sha":
        cohort = replace(cohort, candidate_sha256=H("other"))
    elif attack == "wrong_source_sha":
        cohort = replace(cohort, source_sha256=H("other"))
    elif attack == "wrong_rubric_sha":
        cohort = replace(cohort, rubric_sha256=H("other"))
    elif attack == "wrong_dataset_version":
        cohort = replace(cohort, version="changed")
    elif attack == "hidden_labels":
        cohort = replace(cohort, sealed_hidden_labels=True)
    elif attack == "external_custody":
        cohort = replace(cohort, independent_external_custody=True)
    elif attack == "nonfixture":
        cohort = replace(cohort, fixture_only=False)
    elif attack == "changed_weights":
        cohort = replace(cohort, changed_weights_after_outcome=True)
    elif attack == "self_scored":
        cohort = replace(cohort, self_scored=True)
    elif attack == "unknown_cost":
        cohort = _tamper_result(cohort, {"cost_micros": None}, "candidate")
    elif attack == "missing_baseline_cost":
        cohort = _tamper_result(cohort, {"cost_micros": None}, "baseline")
    elif attack == "negative_cost":
        cohort = _tamper_result(cohort, {"cost_micros": -10}, "candidate")
    elif attack == "zero_attempts":
        cohort = _tamper_result(cohort, {"attempts": 0}, "candidate")
    elif attack == "safety_regression":
        cohort = _tamper_result(cohort, {"safety_incident": True}, "candidate")
    elif attack == "unknown_effect":
        cohort = _tamper_result(cohort, {"unknown_effect": True}, "candidate")
    elif attack == "revoked_case_source":
        cohort = _tamper_result(cohort, {"rights_current": False}, "baseline")
    elif attack == "changed_stratum":
        cohort = _tamper_result(cohort, {"stratum": "other"}, "candidate")
    elif attack == "adverse_unknown_status":
        cohort = _tamper_result(cohort, {"status": "UNKNOWN_EFFECT"}, "candidate")
    elif attack == "illegal_status":
        cohort = _tamper_result(cohort, {"status": "INJECTED_PASS"}, "candidate")
    elif attack == "empty_population":
        cohort = replace(cohort, assigned=(), baseline=(), candidate=())
    elif attack == "unassigned_candidate":
        cohort = replace(
            cohort, candidate=cohort.candidate + (OfflineCase("injected", "qa", "ACCEPTED", 1),)
        )
    elif attack == "forged_d09":
        seams = replace(seams, d09={"verdict": "PASS"})
    elif attack == "forged_e09b":
        seams = replace(seams, e09b=replace(seams.e09b, official_evaluation_ran=True))
    elif attack == "forged_e09b_release":
        seams = replace(seams, e09b=replace(seams.e09b, release_certified=True))
    elif attack == "forged_ttft":
        seams = replace(seams, t09=replace(seams.t09, product_ttft="VERIFIED"))
    elif attack == "forged_billing":
        seams = replace(seams, p09=replace(seams.p09, accepted_outcome=True))
    elif attack == "forged_release":
        seams = replace(seams, e09h=replace(seams.e09h, release_certification="REL01_CERTIFIED"))
    elif attack == "untrusted_e09h_class":
        seams = replace(seams, e09h={"release_certification": "NOT_CERTIFIED"})
    result = evaluate_matched_offline(proposal, cohort, seams)
    assert result.status == "INELIGIBLE", attack
    assert result.reasons and not result.promotion_eligible
    assert result.denominator == len(cohort.assigned)


@pytest.mark.parametrize(
    "target",
    [
        "BLIND_EVAL",
        "SECURITY_PRIVACY_COST_APPROVAL",
        "SIGNED_IMMUTABLE_VERSION",
        "ISOLATED_CANARY",
        "RELEASE_PENDING_REL02",
        "RELEASED",
        "REL01",
        "REL02",
        "PRODUCTION",
        "GRANT",
        "ACL",
        "POLICY_ACTIVATION",
        "OTHER",
    ],
)
def test_later_transitions_blocked(db_path, proposal, rights, target):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        lease = engine.lease(proposal.proposal_id, "owner.worker", 0, NOW, NOW + 100)
        out = engine.advance(proposal.proposal_id, lease, rights, NOW, "later", target)
        assert out.state == "DRAFT" and out.reason == "G09_EXTERNAL_BLOCKED"
        assert out.tool_effects == out.release_writes == 0


def test_cas_concurrent_workers_fence(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as first:
        first.register(proposal, rights, NOW, "registration")
        first.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 100)
        with AR10CandidateGovernanceV1(db_path) as second:
            with pytest.raises(Denied, match="LEASE_HELD"):
                second.lease(proposal.proposal_id, "worker.b", 0, NOW, NOW + 99)
            with pytest.raises(Denied, match="STALE_CAS"):
                second.lease(proposal.proposal_id, "worker.b", 99, NOW, NOW + 99)


def test_crash_after_prepare_before_commit_reopen(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as first:
        first.register(proposal, rights, NOW, "registration")
        prepared = first.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 300)
        # Deliberately stop after lease acquisition, no admission write.
    with AR10CandidateGovernanceV1(db_path) as recovered:
        assert recovered.inspect(proposal.proposal_id).state == "DRAFT"
        result = recovered.advance(
            proposal.proposal_id, prepared, rights, NOW, "after.crash", "ELIGIBILITY_REVIEW"
        )
        assert result.state == "ELIGIBILITY_REVIEW"
        assert len(recovered.journal_rows()) == 2


def test_lease_expiry_stale_epoch_and_optimistic_version(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "registration")
        old = engine.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 1)
        with pytest.raises(Denied, match="STALE_CAS_OR_LEASE"):
            engine.advance(
                proposal.proposal_id, old, rights, NOW + 2, "stale", "ELIGIBILITY_REVIEW"
            )
        new = engine.lease(proposal.proposal_id, "worker.b", 0, NOW + 2, NOW + 100)
        with pytest.raises(Denied, match="STALE_CAS_OR_LEASE"):
            engine.advance(proposal.proposal_id, old, rights, NOW + 3, "old", "ELIGIBILITY_REVIEW")
        assert (
            engine.advance(
                proposal.proposal_id, new, rights, NOW + 3, "fresh", "ELIGIBILITY_REVIEW"
            ).version
            == 1
        )


def test_duplicate_run_and_cross_proposal_request_denied(tmp_path, proposal, rights):
    with AR10CandidateGovernanceV1(tmp_path / "unique.db") as engine:
        engine.register(proposal, rights, NOW, "same.key")
        assert engine.register(proposal, rights, NOW, "same.key").reason == "IDEMPOTENT"
        other = replace(proposal, proposal_id="candidate.2")
        with pytest.raises(Denied, match="REPLAY_CROSS_PROPOSAL"):
            engine.register(other, rights, NOW, "same.key")
        with pytest.raises(sqlite3.IntegrityError):
            engine.register(other, rights, NOW, "second.key")


def test_tombstone_and_all_derivatives_after_restart(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "p.register")
        secondary = replace(
            proposal,
            proposal_id="candidate.2",
            origin_run_id="run.2",
            derivative_of="candidate.1",
            candidate_artifact_sha256=H("child"),
        )
        engine.register(secondary, rights, NOW, "s.register")
        lease = engine.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 100)
        assert (
            engine.advance(
                proposal.proposal_id, lease, rights, NOW, "eligible", "ELIGIBILITY_REVIEW"
            ).state
            == "ELIGIBILITY_REVIEW"
        )
        assert (
            engine.record_fence(
                replace(rights, tombstone_generation=1, consent_active=False),
                "revocation.1",
                incident="REVOCATION",
            )
            == 2
        )
        assert engine.inspect(proposal.proposal_id).state == "QUARANTINED"
    with AR10CandidateGovernanceV1(db_path) as reopened:
        assert reopened.inspect("candidate.2").state == "QUARANTINED"
        assert (
            reopened.register(
                replace(secondary, proposal_id="candidate.3", origin_run_id="run.3"),
                rights,
                NOW,
                "replay.old",
            ).state
            == "QUARANTINED"
        )


@pytest.mark.parametrize(
    "incident",
    [
        "LEAK",
        "TAINT",
        "UNKNOWN_EFFECT",
        "SOURCE_REVISION",
        "REVOCATION",
    ],
)
def test_incident_quarantine_and_restart(db_path, proposal, rights, incident):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "registered")
        new_rights = (
            replace(rights, revision="rev.2")
            if incident == "SOURCE_REVISION"
            else (replace(rights, consent_active=False) if incident == "REVOCATION" else rights)
        )
        assert engine.record_fence(new_rights, "incident.1", incident=incident) == 1
        assert engine.record_fence(new_rights, "incident.1", incident=incident) == 0
    with AR10CandidateGovernanceV1(db_path) as recovered:
        assert recovered.inspect(proposal.proposal_id).state == "QUARANTINED"


def test_rollback_only_local_previous_status(db_path, proposal, rights, seams, cohort):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        lease = engine.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 300)
        engine.advance(proposal.proposal_id, lease, rights, NOW, "eligible", "ELIGIBILITY_REVIEW")
        lease = engine.lease(proposal.proposal_id, "worker.a", 1, NOW, NOW + 300)
        comp = evaluate_matched_offline(proposal, cohort, seams)
        engine.advance(
            proposal.proposal_id,
            lease,
            rights,
            NOW,
            "review",
            "OFFLINE_REVIEW",
            comp,
            proposal.reviewer_id,
        )
        lease = engine.lease(proposal.proposal_id, "worker.a", 2, NOW, NOW + 300)
        rolled = engine.rollback_local(proposal.proposal_id, lease, NOW, "rollback.local")
        assert rolled.state == "ELIGIBILITY_REVIEW"
        assert rolled.reason == "LOCAL_STATUS_ONLY"
        with pytest.raises(Denied, match="UNSIGNED_OR_STALE_ROLLBACK"):
            engine.rollback_local(proposal.proposal_id, lease, NOW, "rollback.old")


def test_forged_promotion_comparison_and_reviewer_denied(db_path, proposal, rights, seams, cohort):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        lease = engine.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 900)
        engine.advance(proposal.proposal_id, lease, rights, NOW, "eligible", "ELIGIBILITY_REVIEW")
        comp = evaluate_matched_offline(proposal, cohort, seams)
        forged = replace(comp, promotion_eligible=True)
        lease = engine.lease(proposal.proposal_id, "worker.a", 1, NOW, NOW + 900)
        result = engine.advance(
            proposal.proposal_id,
            lease,
            rights,
            NOW,
            "forged",
            "OFFLINE_REVIEW",
            forged,
            proposal.reviewer_id,
        )
        assert result.reason == "FORGED_PROMOTION" and result.state == "ELIGIBILITY_REVIEW"
        lease = engine.lease(proposal.proposal_id, "worker.a", 2, NOW, NOW + 900)
        result = engine.advance(
            proposal.proposal_id,
            lease,
            rights,
            NOW,
            "fakeowner",
            "OFFLINE_REVIEW",
            comp,
            "owner.ack.forged",
        )
        assert result.reason == "INDEPENDENT_REVIEWER_MISSING"
        assert result.state == "ELIGIBILITY_REVIEW"


def test_mismatched_review_and_unqualified_cohort_denied(db_path, proposal, rights, seams, cohort):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        lease = engine.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 900)
        engine.advance(proposal.proposal_id, lease, rights, NOW, "eligible", "ELIGIBILITY_REVIEW")
        lease = engine.lease(proposal.proposal_id, "worker.a", 1, NOW, NOW + 900)
        comp = evaluate_matched_offline(
            proposal, _tamper_result(cohort, {"cost_micros": None}, "candidate"), seams
        )
        assert (
            engine.advance(
                proposal.proposal_id,
                lease,
                rights,
                NOW,
                "unqualified",
                "OFFLINE_REVIEW",
                comp,
                proposal.reviewer_id,
            ).reason
            == "MATCHED_FIXTURE_NOT_ADMITTED"
        )


def test_fence_denies_expired_rights_after_review(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        lease = engine.lease(proposal.proposal_id, "worker.a", 0, NOW, NOW + 600)
        engine.advance(proposal.proposal_id, lease, rights, NOW, "eligible", "ELIGIBILITY_REVIEW")
        lease = engine.lease(proposal.proposal_id, "worker.a", 1, NOW, NOW + 600)
        out = engine.advance(
            proposal.proposal_id,
            lease,
            replace(rights, valid_until_ms=NOW),
            NOW,
            "stale.rights",
            "OFFLINE_REVIEW",
        )
        assert out.state == "QUARANTINED" and out.reason == "SOURCE_EXPIRED"


def test_journal_tamper_detects_replayed_or_modified_head(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        engine.db.execute("UPDATE journal SET head=? WHERE seq=1", (H("forged"),))
        with pytest.raises(Denied, match="JOURNAL_TAMPER"):
            engine.inspect(proposal.proposal_id)
    with pytest.raises(Denied, match="JOURNAL_TAMPER"):
        AR10CandidateGovernanceV1(db_path)


def test_no_policy_pointer_or_effect_tables(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        tables = {
            r[0] for r in engine.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not tables.intersection(
            {
                "acl",
                "grants",
                "live_runtime_policy",
                "production_pointer",
                "release_registry",
                "provider_calls",
                "external_effects",
            }
        )
        assert engine.inspect(proposal.proposal_id).tool_effects == 0


def test_invalid_fence_replay_and_generation_rollback(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "register")
        with pytest.raises(Denied, match="NO_FENCE_CHANGE"):
            engine.record_fence(rights, "nochange", incident="REVOCATION")
        engine.record_fence(
            replace(rights, tombstone_generation=2), "revoked", incident="REVOCATION"
        )
        with pytest.raises(Denied, match="GENERATION_ROLLBACK"):
            engine.record_fence(
                replace(rights, tombstone_generation=1), "rollback.fence", incident="REVOCATION"
            )


def test_no_cross_tenant_fence_propagation(db_path, proposal, rights):
    other = replace(
        proposal,
        proposal_id="candidate.other",
        origin_run_id="run.other",
        tenant_id="tenant.b",
        candidate_artifact_sha256=H("different"),
    )
    other_rights = replace(rights, tenant_id="tenant.b")
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "a")
        engine.register(other, other_rights, NOW, "b")
        engine.record_fence(
            replace(rights, consent_active=False), "revocation", incident="REVOCATION"
        )
        assert engine.inspect(other.proposal_id).state == "DRAFT"
        assert engine.inspect(proposal.proposal_id).state == "QUARANTINED"


def test_state_terminal_replay_never_resurrects(db_path, proposal, rights):
    bad = replace(proposal, tainted=True)
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(bad, rights, NOW, "register")
        lease = engine.lease(bad.proposal_id, "worker.a", 0, NOW, NOW + 500)
        out = engine.advance(bad.proposal_id, lease, rights, NOW, "resurrect", "ELIGIBILITY_REVIEW")
        assert out.state == "QUARANTINED"
        assert out.reason == "TERMINAL_IMMUTABLE"


def test_transitive_descendants_different_sources_and_purposes(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "root")
        child = replace(
            proposal,
            proposal_id="child.1",
            origin_run_id="child.run.1",
            origin_source_id="source.other",
            origin_subject_id="subject.other",
            purpose="fixture.other",
            derivative_of=proposal.proposal_id,
            candidate_artifact_sha256=H("child.artifact"),
        )
        child_rights = replace(
            rights,
            source_id="source.other",
            subject_id="subject.other",
            purpose="fixture.other",
        )
        assert engine.register(child, child_rights, NOW, "child").state == "DRAFT"
        grand = replace(
            child,
            proposal_id="grandchild.1",
            origin_run_id="grand.run.1",
            derivative_of=child.proposal_id,
            candidate_artifact_sha256=H("grand"),
        )
        engine.register(grand, child_rights, NOW, "grand")
        assert (
            engine.record_fence(
                replace(rights, tombstone_generation=1), "tombstone", incident="REVOCATION"
            )
            == 3
        )
    with AR10CandidateGovernanceV1(db_path) as restored:
        assert restored.inspect(child.proposal_id).state == "QUARANTINED"
        assert restored.inspect(grand.proposal_id).state == "QUARANTINED"
        new_child = replace(
            child,
            proposal_id="future.child",
            origin_run_id="future.run",
            candidate_artifact_sha256=H("future"),
        )
        got = restored.register(new_child, child_rights, NOW, "future")
        assert got.state == "QUARANTINED"
        assert got.reason == "DERIVATIVE_PARENT_BLOCKED"


def test_cross_tenant_derivative_and_cycle_denied(db_path, proposal, rights):
    with AR10CandidateGovernanceV1(db_path) as engine:
        engine.register(proposal, rights, NOW, "root")
        crossover = replace(
            proposal,
            proposal_id="tenant.other.child",
            origin_run_id="tenant.other.run",
            tenant_id="tenant.b",
            derivative_of=proposal.proposal_id,
        )
        outcome = engine.register(crossover, replace(rights, tenant_id="tenant.b"), NOW, "cross")
        assert outcome.state == "REJECTED"
        assert outcome.reason == "DERIVATIVE_CROSS_TENANT"
        cyclic = replace(
            proposal,
            proposal_id="cycle.1",
            origin_run_id="cycle.run.1",
            derivative_of="cycle.1",
        )
        outcome = engine.register(cyclic, rights, NOW, "cycle")
        assert outcome.state == "REJECTED"
        assert outcome.reason == "DERIVATIVE_CYCLE"
