from __future__ import annotations

import hashlib

import pytest

from knowledge_engine.m27_memory_contracts import (
    STAGE10_MEMORY_POLICY,
    ForbiddenMemoryClassError,
    MemoryActivation,
    MemoryCandidate,
    MemoryCandidateId,
    MemoryClass,
    MemoryContractError,
    MemoryGovernancePolicy,
    MemoryOriginKind,
    MemoryProvenance,
    MemoryReviewDecision,
    MemoryReviewReceipt,
    UnsafeMemoryPayloadError,
    forbidden_memory_class_values,
    memory_class_from_value,
    validate_memory_summary,
    validate_reason_codes,
    validate_safe_token,
    validate_tags,
)


def _provenance() -> MemoryProvenance:
    return MemoryProvenance(
        origin_kind=MemoryOriginKind.TASK_SUMMARY,
        origin_ref="task:stage10:fixture",
        source_sha256=hashlib.sha256(b"sanitized-source").hexdigest(),
    )


def test_activation_is_default_off_and_enabled_requires_isolation() -> None:
    assert MemoryActivation().as_dict() == {
        "enabled": False,
        "isolated_runtime": False,
    }
    assert MemoryActivation(enabled=True, isolated_runtime=True).enabled is True

    with pytest.raises(MemoryContractError):
        MemoryActivation(enabled=True, isolated_runtime=False)


def test_stage10_policy_is_candidate_only_and_has_no_truth_authority() -> None:
    assert STAGE10_MEMORY_POLICY.candidate_only is True
    assert STAGE10_MEMORY_POLICY.candidate_store_write is True
    assert STAGE10_MEMORY_POLICY.episodic_allowed is True
    assert STAGE10_MEMORY_POLICY.project_allowed is True
    assert STAGE10_MEMORY_POLICY.semantic_user_memory_allowed is False
    assert STAGE10_MEMORY_POLICY.knowledge_authority is False
    assert STAGE10_MEMORY_POLICY.citation_eligible is False
    assert STAGE10_MEMORY_POLICY.answer_context_enabled is False
    assert STAGE10_MEMORY_POLICY.can_override_cited_knowledge is False
    assert STAGE10_MEMORY_POLICY.can_promote_to_knowledge is False
    assert STAGE10_MEMORY_POLICY.production_write is False
    assert STAGE10_MEMORY_POLICY.r2_write is False
    assert STAGE10_MEMORY_POLICY.qdrant_write is False
    assert STAGE10_MEMORY_POLICY.production_sqlite_write is False
    assert STAGE10_MEMORY_POLICY.release_control is False
    assert STAGE10_MEMORY_POLICY.mcp_exposed is False
    assert STAGE10_MEMORY_POLICY.workspace_read is False
    assert STAGE10_MEMORY_POLICY.skill_execution is False
    assert STAGE10_MEMORY_POLICY.network_access is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_only", False),
        ("candidate_store_write", False),
        ("episodic_allowed", False),
        ("project_allowed", False),
        ("semantic_user_memory_allowed", True),
        ("knowledge_authority", True),
        ("citation_eligible", True),
        ("answer_context_enabled", True),
        ("can_override_cited_knowledge", True),
        ("can_promote_to_knowledge", True),
        ("production_write", True),
        ("r2_write", True),
        ("qdrant_write", True),
        ("production_sqlite_write", True),
        ("release_control", True),
        ("mcp_exposed", True),
        ("workspace_read", True),
        ("skill_execution", True),
        ("network_access", True),
    ],
)
def test_stage10_policy_cannot_be_widened_or_weakened(
    field: str,
    value: bool,
) -> None:
    with pytest.raises(MemoryContractError):
        MemoryGovernancePolicy(**{field: value})


def test_memory_class_allowlist_is_exactly_episodic_and_project() -> None:
    assert memory_class_from_value("episodic") is MemoryClass.EPISODIC
    assert memory_class_from_value("PROJECT") is MemoryClass.PROJECT
    assert forbidden_memory_class_values() >= {
        "SEMANTIC_USER",
        "USER_PROFILE",
        "KNOWLEDGE",
        "EVIDENCE",
        "CITATION",
    }

    for value in forbidden_memory_class_values():
        with pytest.raises(ForbiddenMemoryClassError):
            memory_class_from_value(value)

    with pytest.raises(MemoryContractError):
        memory_class_from_value("NEW_UNGOVERNED_CLASS")


def test_safe_tokens_reject_raw_free_form_text() -> None:
    assert validate_safe_token("scope_token", "project:alpha-42") == "project:alpha-42"

    for value in (
        "this has spaces",
        "../escape",
        "/absolute/path",
        "raw project description with details",
    ):
        with pytest.raises(MemoryContractError):
            validate_safe_token("scope_token", value)


@pytest.mark.parametrize(
    "summary",
    [
        "raw query: private question",
        "provider_prompt = hidden prompt",
        "api_key: abc",
        "-----BEGIN PRIVATE KEY-----",
        "r2://bucket/private/object",
        "/home/ubuntu/private/file",
        "SERVICE_API_KEY=secret-value",
    ],
)
def test_memory_summary_rejects_raw_private_or_infra_material(summary: str) -> None:
    with pytest.raises(UnsafeMemoryPayloadError):
        validate_memory_summary(summary)


def test_memory_summary_accepts_sanitized_operational_memory() -> None:
    summary = (
        "Project retrieval diagnostics use the bounded two-round recovery path; "
        "retain this only as an unverified project-memory candidate."
    )
    assert validate_memory_summary(summary) == summary


def test_tags_are_bounded_sorted_unique_opaque_labels() -> None:
    assert validate_tags(("retrieval", "stage10")) == ("retrieval", "stage10")

    for tags in (
        ["retrieval"],
        ("stage10", "retrieval"),
        ("retrieval", "retrieval"),
        ("contains spaces",),
    ):
        with pytest.raises(MemoryContractError):
            validate_tags(tags)


def test_provenance_requires_opaque_ref_and_optional_sha256() -> None:
    provenance = _provenance()
    assert provenance.origin_ref == "task:stage10:fixture"

    with pytest.raises(MemoryContractError):
        MemoryProvenance(
            origin_kind=MemoryOriginKind.TASK_SUMMARY,
            origin_ref="raw free form source",
        )
    with pytest.raises(MemoryContractError):
        MemoryProvenance(
            origin_kind=MemoryOriginKind.TASK_SUMMARY,
            origin_ref="task:fixture",
            source_sha256="not-a-sha",
        )


def test_candidate_id_is_deterministic_and_bound_to_scope_content_and_class() -> None:
    first = MemoryCandidate.create(
        memory_class=MemoryClass.PROJECT,
        scope_token="project:alpha",
        summary="Project uses bounded retrieval diagnostics for gap analysis.",
        provenance=_provenance(),
        tags=("retrieval", "stage10"),
    )
    second = MemoryCandidate.create(
        memory_class=MemoryClass.PROJECT,
        scope_token="project:alpha",
        summary="Project uses bounded retrieval diagnostics for gap analysis.",
        provenance=_provenance(),
        tags=("retrieval", "stage10"),
    )
    other_scope = MemoryCandidate.create(
        memory_class=MemoryClass.PROJECT,
        scope_token="project:beta",
        summary="Project uses bounded retrieval diagnostics for gap analysis.",
        provenance=_provenance(),
        tags=("retrieval", "stage10"),
    )
    episodic = MemoryCandidate.create(
        memory_class=MemoryClass.EPISODIC,
        scope_token="project:alpha",
        summary="Project uses bounded retrieval diagnostics for gap analysis.",
        provenance=_provenance(),
        tags=("retrieval", "stage10"),
    )

    assert first == second
    assert first.memory_id == second.memory_id
    assert first.memory_id != other_scope.memory_id
    assert first.memory_id != episodic.memory_id
    assert first.memory_id.value.startswith("mem-")
    assert len(first.memory_id.value) == 36


def test_candidate_rejects_forged_id() -> None:
    with pytest.raises(MemoryContractError):
        MemoryCandidate(
            memory_id=MemoryCandidateId("mem-" + "0" * 32),
            memory_class=MemoryClass.PROJECT,
            scope_token="project:alpha",
            summary="Sanitized candidate summary.",
            provenance=_provenance(),
        )


def test_candidate_serialization_keeps_authority_explicitly_false() -> None:
    candidate = MemoryCandidate.create(
        memory_class=MemoryClass.EPISODIC,
        scope_token="project:alpha",
        summary="A sanitized task outcome is proposed for later memory review.",
        provenance=_provenance(),
    )
    payload = candidate.as_dict()

    assert payload["governance_policy"] == STAGE10_MEMORY_POLICY.as_dict()
    assert payload["authority"] == {
        "status": "UNVERIFIED_MEMORY_CANDIDATE",
        "knowledge_authority": False,
        "citation_eligible": False,
        "answer_context_enabled": False,
        "can_override_cited_knowledge": False,
    }


def test_review_receipt_is_candidate_only_and_reason_codes_are_canonical() -> None:
    candidate = MemoryCandidate.create(
        memory_class=MemoryClass.PROJECT,
        scope_token="project:alpha",
        summary="Retain a sanitized project convention as candidate memory.",
        provenance=_provenance(),
    )
    receipt = MemoryReviewReceipt(
        memory_id=candidate.memory_id,
        sequence=1,
        decision=MemoryReviewDecision.RETAIN_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("BOUNDED_PROJECT_CONTEXT", "SANITIZED_CONTENT"),
    )

    assert receipt.as_dict()["authority"] == {
        "candidate_only": True,
        "knowledge_authority": False,
        "citation_eligible": False,
        "can_promote_to_knowledge": False,
    }


def test_review_reason_codes_must_be_nonempty_sorted_unique_upper_snake_case() -> None:
    assert validate_reason_codes(("A_REASON", "SECOND_REASON")) == (
        "A_REASON",
        "SECOND_REASON",
    )

    for codes in (
        (),
        ("lowercase",),
        ("SECOND_REASON", "A_REASON"),
        ("A_REASON", "A_REASON"),
        ["A_REASON"],
    ):
        with pytest.raises(MemoryContractError):
            validate_reason_codes(codes)
