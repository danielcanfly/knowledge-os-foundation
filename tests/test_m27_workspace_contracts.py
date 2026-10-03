from __future__ import annotations

import pytest

from knowledge_engine.m27_workspace_contracts import (
    STAGE8_WRITE_POLICY,
    ForbiddenWorkspaceArtifactError,
    UnsafeWorkspacePathError,
    UnsafeWorkspacePayloadError,
    WorkspaceArtifactKind,
    WorkspaceContractError,
    WorkspaceId,
    WorkspaceScope,
    WorkspaceWritePolicy,
    artifact_kind_from_value,
    blocked_artifact_kind_values,
    validate_relative_artifact_path,
    validate_sanitized_json_payload,
    validate_sanitized_text,
)


def test_workspace_id_is_deterministic_and_scope_bound() -> None:
    first = WorkspaceId.from_safe_token(
        scope=WorkspaceScope.TASK,
        task_token="task:PASS186:attempt-1",
    )
    second = WorkspaceId.from_safe_token(
        scope=WorkspaceScope.TASK,
        task_token="task:PASS186:attempt-1",
    )
    eval_id = WorkspaceId.from_safe_token(
        scope=WorkspaceScope.EVAL,
        task_token="task:PASS186:attempt-1",
    )

    assert first == second
    assert first != eval_id
    assert first.value.startswith("ws-")
    assert len(first.value) == 35


def test_workspace_id_rejects_raw_text_and_arbitrary_ids() -> None:
    with pytest.raises(WorkspaceContractError):
        WorkspaceId.from_safe_token(
            scope=WorkspaceScope.TASK,
            task_token="What is the raw user question?",
        )
    with pytest.raises(WorkspaceContractError):
        WorkspaceId("customer-query")
    with pytest.raises(WorkspaceContractError):
        WorkspaceId("ws-../escape")


@pytest.mark.parametrize(
    "path",
    [
        "../escape.txt",
        "reports/../escape.txt",
        "/absolute/report.txt",
        "~/report.txt",
        "reports\\escape.txt",
        "C:/windows/path.txt",
        "./report.txt",
        ".hidden",
    ],
)
def test_relative_artifact_path_rejects_unsafe_forms(path: str) -> None:
    with pytest.raises(UnsafeWorkspacePathError):
        validate_relative_artifact_path(path)


def test_relative_artifact_path_accepts_safe_nested_ref() -> None:
    assert (
        validate_relative_artifact_path("reports/eval-summary.v1.json")
        == "reports/eval-summary.v1.json"
    )


def test_artifact_kind_allowlist_and_blocklist() -> None:
    assert artifact_kind_from_value("report") is WorkspaceArtifactKind.REPORT
    assert artifact_kind_from_value("candidate_patch") is WorkspaceArtifactKind.CANDIDATE_PATCH

    expected_blocked = {
        "PRODUCTION_RELEASE",
        "R2_OBJECT",
        "QDRANT_COLLECTION",
        "SQLITE_DB",
        "SECRET",
        "ENV_DUMP",
        "RAW_EVIDENCE",
        "RAW_ANSWER",
        "RAW_QUERY",
    }
    assert blocked_artifact_kind_values() == expected_blocked

    for value in expected_blocked:
        with pytest.raises(ForbiddenWorkspaceArtifactError):
            artifact_kind_from_value(value)

    with pytest.raises(WorkspaceContractError):
        artifact_kind_from_value("SOMETHING_NEW")


def test_write_policy_cannot_be_widened() -> None:
    assert STAGE8_WRITE_POLICY.isolated_task_workspace is True
    assert STAGE8_WRITE_POLICY.production_write is False
    assert STAGE8_WRITE_POLICY.r2_write is False
    assert STAGE8_WRITE_POLICY.qdrant_write is False
    assert STAGE8_WRITE_POLICY.production_sqlite_write is False
    assert STAGE8_WRITE_POLICY.release_control is False
    assert STAGE8_WRITE_POLICY.mcp_exposed is False
    assert STAGE8_WRITE_POLICY.memory_runtime is False
    assert STAGE8_WRITE_POLICY.skill_execution is False
    assert STAGE8_WRITE_POLICY.answer_path_change is False
    assert STAGE8_WRITE_POLICY.public_runtime_change is False

    for field in (
        "production_write",
        "r2_write",
        "qdrant_write",
        "production_sqlite_write",
        "release_control",
        "mcp_exposed",
        "memory_runtime",
        "skill_execution",
        "answer_path_change",
        "public_runtime_change",
    ):
        with pytest.raises(WorkspaceContractError):
            WorkspaceWritePolicy(**{field: True})


def test_json_payload_rejects_private_raw_fields() -> None:
    validate_sanitized_json_payload(
        {
            "status_code": "READY",
            "counts": {"passed": 12, "failed": 0},
            "candidate_ids": ["candidate-1", "candidate-2"],
        }
    )

    for field in (
        "raw_query",
        "raw_answer",
        "full_evidence_text",
        "source_body",
        "provider_prompt",
        "api_key",
        "environment_value",
        "production_object_path",
        "raw_qdrant",
        "raw_r2",
        "raw_sql",
        "sqlite_path",
    ):
        with pytest.raises(UnsafeWorkspacePayloadError):
            validate_sanitized_json_payload({field: "private-value"})


@pytest.mark.parametrize(
    "text",
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
def test_text_payload_rejects_private_or_raw_material(text: str) -> None:
    with pytest.raises(UnsafeWorkspacePayloadError):
        validate_sanitized_text(text)


def test_text_payload_allows_sanitized_report_language() -> None:
    text = (
        "Stage 8 gate: PASS\n"
        "Production writes: disabled\n"
        "Artifact count: 3\n"
        "No raw task payload is stored."
    )
    assert validate_sanitized_text(text) == text
