from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine.m27_learning_contracts import (
    LearningAuthority,
    LearningContractError,
    LearningEvidenceBinding,
    LearningPolicyArea,
    LearningProposal,
    LearningProposalKind,
    LearningProposalStatus,
    LearningRiskClass,
    LearningSignal,
    LearningSignalKind,
    LearningSignalSource,
    UnsafeLearningPayloadError,
    policy_area_for_proposal_kind,
)


def _signal() -> LearningSignal:
    return LearningSignal.create(
        kind=LearningSignalKind.FAILURE_CLASS_SUMMARY,
        source=LearningSignalSource.FAILURE_CLASS_SUMMARY,
        source_ref="failure:unsupported-claim",
        policy_area=LearningPolicyArea.GUARDRAIL,
        classification="UNSUPPORTED_CLAIM",
        count=3,
        reason_codes=("CLAIM_SUPPORT_GAP",),
        artifact_ids=("artifact:eval-001",),
    )


def _proposal() -> LearningProposal:
    signal = _signal()
    return LearningProposal.create(
        kind=LearningProposalKind.GUARDRAIL_HARDENING_CANDIDATE,
        observed_issue_class="UNSUPPORTED_CLAIM_CLUSTER",
        evidence_binding=LearningEvidenceBinding((signal.signal_id,)),
        candidate_change_summary=(
            "Tighten claim-support guard thresholds for an offline candidate evaluation."
        ),
        expected_benefit_class="LOWER_UNSUPPORTED_CLAIM_RATE",
        risk_class=LearningRiskClass.HIGH,
        required_gate="offline.guardrail.v1",
    )


def test_learning_authority_has_only_proposal_only() -> None:
    assert tuple(LearningAuthority) == (LearningAuthority.PROPOSAL_ONLY,)
    assert set(LearningAuthority.__members__) == {"PROPOSAL_ONLY"}


@pytest.mark.parametrize(
    "forbidden_name",
    ("AUTO_APPLY", "AUTO_PROMOTE", "AUTHORITATIVE_POLICY", "PRODUCTION_POLICY", "SOURCE_OF_TRUTH"),
)
def test_forbidden_authority_names_do_not_exist(forbidden_name: str) -> None:
    assert forbidden_name not in LearningAuthority.__members__


def test_all_required_proposal_kinds_exist() -> None:
    assert {item.value for item in LearningProposalKind} == {
        "SKILL_POLICY_CANDIDATE",
        "RETRIEVAL_POLICY_CANDIDATE",
        "COMPUTE_POLICY_CANDIDATE",
        "ROUTING_POLICY_CANDIDATE",
        "MEMORY_POLICY_CANDIDATE",
        "EVAL_GATE_CANDIDATE",
        "GUARDRAIL_HARDENING_CANDIDATE",
    }


def test_proposal_kind_has_fixed_policy_area() -> None:
    assert (
        policy_area_for_proposal_kind(
            LearningProposalKind.RETRIEVAL_POLICY_CANDIDATE
        )
        is LearningPolicyArea.RETRIEVAL
    )
    assert (
        policy_area_for_proposal_kind(
            LearningProposalKind.MEMORY_POLICY_CANDIDATE
        )
        is LearningPolicyArea.MEMORY
    )


def test_learning_signal_id_is_deterministic_and_safe() -> None:
    first = _signal()
    second = _signal()
    assert first == second
    assert first.signal_id == second.signal_id
    assert first.signal_id.startswith("lsig-")
    assert len(first.signal_id) == 37


def test_signal_direct_forged_id_rejected() -> None:
    signal = _signal()
    with pytest.raises(LearningContractError):
        replace(signal, signal_id="lsig-" + ("0" * 32))


def test_signal_create_canonicalizes_reason_and_artifact_ids() -> None:
    signal = LearningSignal.create(
        kind=LearningSignalKind.EVAL_SUMMARY,
        source=LearningSignalSource.EVAL_SUMMARY,
        source_ref="eval:523",
        policy_area=LearningPolicyArea.EVAL_GATE,
        classification="QUALITY_GATE_RESULT",
        count=523,
        reason_codes=("GATE_FAIL", "GATE_FAIL", "CITATION_GAP"),
        artifact_ids=("artifact:z", "artifact:a", "artifact:z"),
    )
    assert signal.reason_codes == ("CITATION_GAP", "GATE_FAIL")
    assert signal.artifact_ids == ("artifact:a", "artifact:z")


@pytest.mark.parametrize(
    "value",
    (
        "raw_query",
        "raw_answer",
        "full_evidence_body",
        "full_source_body",
        "provider_prompt",
        "secret",
        "credential",
        "api_key",
        "auth_token",
        "env",
        "environment",
        "qdrant",
        "sqlite",
        "postgres",
        "mysql",
        "production_path",
        "release_pointer",
    ),
)
def test_signal_rejects_forbidden_source_ref(value: str) -> None:
    with pytest.raises(UnsafeLearningPayloadError):
        LearningSignal.create(
            kind=LearningSignalKind.FAILURE_CLASS_SUMMARY,
            source=LearningSignalSource.FAILURE_CLASS_SUMMARY,
            source_ref=value,
            policy_area=LearningPolicyArea.GUARDRAIL,
            classification="SAFE_CLASS",
        )


def test_evidence_binding_requires_sorted_unique_signal_ids() -> None:
    first = _signal()
    second = LearningSignal.create(
        kind=LearningSignalKind.GATE_SUMMARY,
        source=LearningSignalSource.GATE_SUMMARY,
        source_ref="gate:quality-001",
        policy_area=LearningPolicyArea.GUARDRAIL,
        classification="GATE_FAILURE",
    )
    ordered = tuple(sorted((first.signal_id, second.signal_id)))
    assert LearningEvidenceBinding(ordered).signal_ids == ordered
    with pytest.raises(LearningContractError):
        LearningEvidenceBinding(tuple(reversed(ordered)))
    with pytest.raises(LearningContractError):
        LearningEvidenceBinding((first.signal_id, first.signal_id))


def test_learning_proposal_id_is_deterministic_and_status_independent() -> None:
    first = _proposal()
    second = _proposal()
    assert first.proposal_id == second.proposal_id
    assert first.proposal_id.startswith("learn-")
    ready = replace(first, status=LearningProposalStatus.READY_FOR_REVIEW)
    assert ready.proposal_id == first.proposal_id


def test_proposal_enforces_fixed_proposal_only_governance() -> None:
    proposal = _proposal()
    assert proposal.authority is LearningAuthority.PROPOSAL_ONLY
    assert proposal.proposal_only is True
    assert proposal.requires_human_review is True
    assert proposal.requires_offline_gate is True
    assert proposal.auto_apply is False
    assert proposal.production_write is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("proposal_only", False),
        ("requires_human_review", False),
        ("requires_offline_gate", False),
        ("auto_apply", True),
        ("production_write", True),
    ),
)
def test_proposal_governance_cannot_be_widened_or_weakened(
    field: str,
    value: bool,
) -> None:
    with pytest.raises(LearningContractError):
        replace(_proposal(), **{field: value})


def test_proposal_policy_area_cannot_be_mismatched() -> None:
    with pytest.raises(LearningContractError):
        replace(_proposal(), policy_area=LearningPolicyArea.COMPUTE)


@pytest.mark.parametrize(
    "forbidden_text",
    (
        "raw_query: private payload",
        "raw_answer: private payload",
        "full_evidence_body: private payload",
        "full_source_body: private payload",
        "provider_prompt: hidden",
        "secret: hidden",
        "credential: hidden",
        "api_key: hidden",
        "auth_token: hidden",
        "env: hidden",
        "environment: hidden",
        "inspect qdrant internals",
        "read r2://bucket/object",
        "open sqlite database",
        "connect postgres backend",
        "connect mysql backend",
        "read s3://bucket/object",
        "inspect /home/ubuntu/private",
        "read ../private",
        "set production_path",
        "change release_pointer",
    ),
)
def test_proposal_summary_rejects_forbidden_payloads(forbidden_text: str) -> None:
    proposal = _proposal()
    with pytest.raises(UnsafeLearningPayloadError):
        LearningProposal.create(
            kind=proposal.kind,
            observed_issue_class=proposal.observed_issue_class,
            evidence_binding=proposal.evidence_binding,
            candidate_change_summary=forbidden_text,
            expected_benefit_class=proposal.expected_benefit_class,
            risk_class=proposal.risk_class,
            required_gate=proposal.required_gate,
        )


def test_proposal_report_shape_contains_no_raw_payload_fields() -> None:
    payload = _proposal().as_dict()
    forbidden_keys = {
        "raw_query",
        "raw_answer",
        "full_evidence_body",
        "full_source_body",
        "provider_prompt",
        "secret",
        "credential",
        "api_key",
        "auth_token",
        "environment",
        "production_path",
        "release_pointer",
    }
    assert forbidden_keys.isdisjoint(payload)
    assert payload["auto_apply"] is False
    assert payload["production_write"] is False
