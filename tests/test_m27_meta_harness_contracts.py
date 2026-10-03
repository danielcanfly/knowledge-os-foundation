from __future__ import annotations

from dataclasses import replace

import pytest

from knowledge_engine.m27_meta_harness_contracts import (
    MetaHarnessAuthority,
    MetaHarnessCandidate,
    MetaHarnessCandidateKind,
    MetaHarnessCandidateStatus,
    MetaHarnessContractError,
    MetaHarnessEvalPlan,
    MetaHarnessGateRequirement,
    MetaHarnessInput,
    MetaHarnessPatchIntent,
    MetaHarnessPlan,
    MetaHarnessRiskClass,
    UnsafeMetaHarnessPayloadError,
    derive_meta_harness_candidate_id,
    report_from_candidate,
    validate_candidate_files,
    validate_safe_token,
    validate_sanitized_meta_text,
)


def _input() -> MetaHarnessInput:
    return MetaHarnessInput.create(
        source_refs=("learn-a1", "trace-a1"),
        target_failure_class="CITATION_BINDING_GAP",
        reason_codes=("EVAL_REGRESSION", "REPEATED_FAILURE"),
        artifact_ids=("artifact-a1",),
        eval_summary_count=12,
        gate_summary_count=3,
    )


def _gates() -> tuple[MetaHarnessGateRequirement, ...]:
    return (
        MetaHarnessGateRequirement("offline.contracts"),
        MetaHarnessGateRequirement("offline.regression"),
    )


def _candidate(
    kind: MetaHarnessCandidateKind = MetaHarnessCandidateKind.HARNESS_PLAN,
) -> MetaHarnessCandidate:
    return MetaHarnessCandidate.create(
        kind=kind,
        input_metadata=_input(),
        candidate_summary="Draft a candidate-only harness around the repeated failure class.",
        expected_improvement_class="FAILURE_CLASS_REDUCTION",
        risk_class=MetaHarnessRiskClass.MEDIUM,
        candidate_files=(
            "src/knowledge_engine/candidate_policy.py",
            "tests/test_candidate_policy.py",
        ),
        test_names=("candidate.contracts", "candidate.regression"),
        gate_requirements=_gates(),
    )


def test_authority_has_only_candidate_only() -> None:
    assert tuple(MetaHarnessAuthority) == (MetaHarnessAuthority.CANDIDATE_ONLY,)
    assert {item.value for item in MetaHarnessAuthority} == {"CANDIDATE_ONLY"}


def test_candidate_kinds_cover_required_stage12_outputs() -> None:
    assert {item.value for item in MetaHarnessCandidateKind} == {
        "HARNESS_PLAN",
        "TEST_PLAN",
        "PATCH_INTENT",
        "EVAL_PLAN",
        "VALIDATION_REPORT",
        "PROMOTION_PROPOSAL",
        "ROLLBACK_PLAN",
        "RISK_MATRIX",
    }


def test_input_canonicalizes_safe_metadata() -> None:
    value = MetaHarnessInput.create(
        source_refs=("trace-b", "trace-a", "trace-a"),
        target_failure_class="LATENCY_CLASS_GAP",
        reason_codes=("Z_REASON", "A_REASON", "A_REASON"),
        artifact_ids=("artifact-b", "artifact-a", "artifact-a"),
    )
    assert value.source_refs == ("trace-a", "trace-b")
    assert value.reason_codes == ("A_REASON", "Z_REASON")
    assert value.artifact_ids == ("artifact-a", "artifact-b")


def test_candidate_id_is_deterministic_and_safe() -> None:
    first = _candidate()
    second = _candidate()
    assert first == second
    assert first.candidate_id == second.candidate_id
    assert first.candidate_id.startswith("mhc-")
    assert len(first.candidate_id) == 36
    int(first.candidate_id.removeprefix("mhc-"), 16)


def test_candidate_id_binds_candidate_kind() -> None:
    first = _candidate(MetaHarnessCandidateKind.HARNESS_PLAN)
    second = _candidate(MetaHarnessCandidateKind.EVAL_PLAN)
    assert first.candidate_id != second.candidate_id


def test_candidate_status_does_not_change_identity() -> None:
    candidate = _candidate()
    ready = replace(candidate, status=MetaHarnessCandidateStatus.READY_FOR_REVIEW)
    assert ready.candidate_id == candidate.candidate_id
    assert ready != candidate


def test_candidate_identity_helper_matches_created_candidate() -> None:
    candidate = _candidate()
    assert candidate.candidate_id == derive_meta_harness_candidate_id(
        kind=candidate.kind,
        input_metadata=candidate.input_metadata,
        candidate_summary=candidate.candidate_summary,
        expected_improvement_class=candidate.expected_improvement_class,
        risk_class=candidate.risk_class,
        candidate_files=candidate.candidate_files,
        test_names=candidate.test_names,
        gate_requirements=candidate.gate_requirements,
    )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("candidate_only", False),
        ("requires_human_review", False),
        ("requires_offline_gate", False),
        ("auto_apply", True),
        ("auto_merge", True),
        ("auto_promote", True),
        ("production_write", True),
    ),
)
def test_candidate_governance_cannot_be_widened_or_weakened(
    field_name: str,
    field_value: bool,
) -> None:
    candidate = _candidate()
    with pytest.raises(MetaHarnessContractError):
        replace(candidate, **{field_name: field_value})


def test_candidate_authority_cannot_be_widened() -> None:
    candidate = _candidate()
    with pytest.raises((MetaHarnessContractError, TypeError)):
        replace(candidate, authority="AUTO_APPLY")


def test_gate_requirement_cannot_be_weakened() -> None:
    with pytest.raises(MetaHarnessContractError):
        MetaHarnessGateRequirement("offline.contracts", required=False)
    with pytest.raises(MetaHarnessContractError):
        MetaHarnessGateRequirement("offline.contracts", offline_only=False)
    with pytest.raises(MetaHarnessContractError):
        MetaHarnessGateRequirement(
            "offline.contracts",
            requires_human_review=False,
        )


def test_candidate_requires_at_least_one_offline_gate() -> None:
    with pytest.raises(MetaHarnessContractError):
        MetaHarnessCandidate.create(
            kind=MetaHarnessCandidateKind.HARNESS_PLAN,
            input_metadata=_input(),
            candidate_summary="Candidate-only plan.",
            expected_improvement_class="FAILURE_CLASS_REDUCTION",
            risk_class=MetaHarnessRiskClass.LOW,
            candidate_files=(),
            test_names=(),
            gate_requirements=(),
        )


def test_candidate_active_state_is_lifecycle_bounded() -> None:
    proposed = _candidate()
    ready = replace(proposed, status=MetaHarnessCandidateStatus.READY_FOR_REVIEW)
    rejected = replace(proposed, status=MetaHarnessCandidateStatus.REJECTED)
    superseded = replace(proposed, status=MetaHarnessCandidateStatus.SUPERSEDED)
    assert proposed.active is True
    assert ready.active is True
    assert rejected.active is False
    assert superseded.active is False


@pytest.mark.parametrize(
    "marker",
    (
        "raw_query: hidden",
        "raw_answer: hidden",
        "full_evidence_body: hidden",
        "full_source_body: hidden",
        "provider_prompt: hidden",
        "secret: hidden",
        "credential: hidden",
        "api_key: hidden",
        "auth_token: hidden",
        "env: hidden",
        "environment: hidden",
        "qdrant collection",
        "r2://bucket/key",
        "sqlite store",
        "postgres backend",
        "mysql backend",
        "s3://bucket/key",
        "/home/ubuntu/project/file",
        "../escape",
        "production_path: hidden",
        "release_pointer: hidden",
        "private_payload: hidden",
    ),
)
def test_forbidden_payload_markers_are_rejected(marker: str) -> None:
    with pytest.raises(UnsafeMetaHarnessPayloadError):
        validate_sanitized_meta_text("summary", marker)


@pytest.mark.parametrize(
    "marker",
    (
        "raw_query",
        "raw_answer",
        "provider_prompt",
        "private_payload",
        "environment",
        "qdrant",
        "sqlite",
        "production_path",
        "release_pointer",
    ),
)
def test_forbidden_markers_are_rejected_in_safe_tokens(marker: str) -> None:
    with pytest.raises(UnsafeMetaHarnessPayloadError):
        validate_safe_token("source_ref", marker)


@pytest.mark.parametrize(
    "path",
    (
        "/home/ubuntu/project/file.py",
        "../candidate.py",
        "src/../candidate.py",
        "src//candidate.py",
        "./candidate.py",
    ),
)
def test_candidate_file_labels_reject_unsafe_paths(path: str) -> None:
    with pytest.raises(UnsafeMetaHarnessPayloadError):
        validate_candidate_files((path,))


def test_candidate_file_labels_are_repo_relative_metadata_only() -> None:
    assert validate_candidate_files(
        (
            "tests/test_candidate.py",
            "src/knowledge_engine/candidate.py",
        )
    ) == (
        "src/knowledge_engine/candidate.py",
        "tests/test_candidate.py",
    )


def test_patch_intent_is_description_only() -> None:
    intent = MetaHarnessPatchIntent(
        candidate_files=("src/knowledge_engine/candidate.py",),
        description="Describe a bounded candidate change without patch material.",
    )
    assert intent.as_dict()["patch_material_present"] is False
    assert "diff" not in intent.as_dict()


def test_eval_plan_has_no_execution_authority() -> None:
    plan = MetaHarnessEvalPlan(
        test_names=("candidate.contracts",),
        gate_requirements=(MetaHarnessGateRequirement("offline.contracts"),),
        description="Offline evaluation plan metadata only.",
    )
    assert plan.as_dict()["execution_authority"] is False


def test_meta_harness_plan_composes_metadata_only_contracts() -> None:
    patch = MetaHarnessPatchIntent(
        candidate_files=("src/knowledge_engine/candidate.py",),
        description="Candidate intent metadata only.",
    )
    eval_plan = MetaHarnessEvalPlan(
        test_names=("candidate.contracts",),
        gate_requirements=(MetaHarnessGateRequirement("offline.contracts"),),
        description="Offline evaluation metadata only.",
    )
    plan = MetaHarnessPlan(
        patch_intent=patch,
        eval_plan=eval_plan,
        rollback_plan="Describe the review-time rollback checks.",
        risk_matrix="LOW impact surface with human review required.",
    )
    assert plan.patch_intent is patch
    assert plan.eval_plan is eval_plan


def test_report_contains_counts_and_governance_not_raw_bodies() -> None:
    candidate = _candidate()
    report = report_from_candidate(candidate).as_dict()
    assert report["source_ref_count"] == 2
    assert report["artifact_count"] == 1
    assert report["candidate_file_count"] == 2
    assert report["test_count"] == 2
    assert report["gate_count"] == 2
    assert report["governance"] == {
        "candidate_only": True,
        "requires_human_review": True,
        "requires_offline_gate": True,
        "auto_apply": False,
        "auto_merge": False,
        "auto_promote": False,
        "production_write": False,
        "runtime_behavior_change": False,
    }


def test_forged_candidate_id_is_rejected() -> None:
    candidate = _candidate()
    with pytest.raises(MetaHarnessContractError):
        replace(candidate, candidate_id="mhc-" + ("0" * 32))
