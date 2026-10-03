from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

WORKSPACE_SCHEMA_VERSION = "m27-isolated-workspace/v1"

_SAFE_SEED_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,160}$")
_WORKSPACE_ID_RE = re.compile(r"^ws-[0-9a-f]{32}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,160}$")
_SAFE_PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_JSON_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")

_BLOCKED_ARTIFACT_KIND_VALUES = frozenset(
    {
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
)
_FORBIDDEN_PAYLOAD_FIELDS = frozenset(
    {
        "query",
        "raw_query",
        "answer",
        "raw_answer",
        "evidence_body",
        "evidence_text",
        "full_evidence_body",
        "full_evidence_text",
        "source_body",
        "source_text",
        "full_source_body",
        "full_source_text",
        "provider_prompt",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "api_key",
        "access_token",
        "auth_token",
        "environment_value",
        "env_value",
        "production_object_path",
        "raw_qdrant",
        "raw_r2",
        "raw_sql",
        "sqlite_path",
    }
)
_FORBIDDEN_LABEL_RE = re.compile(
    r"(?im)^\s*(?:raw[_ -]?query|raw[_ -]?answer|"
    r"(?:full[_ -]?)?evidence[_ -]?(?:body|text)|"
    r"(?:full[_ -]?)?source[_ -]?(?:body|text)|"
    r"provider[_ -]?prompt|credentials?|secrets?|api[_ -]?key|"
    r"access[_ -]?token|auth[_ -]?token|environment[_ -]?value|env[_ -]?value)"
    r"\s*[:=]"
)
_FORBIDDEN_SECRET_RE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk|rk|pk)_[A-Za-z0-9_-]{20,}\b)"
)
_FORBIDDEN_STORAGE_URI_RE = re.compile(
    r"(?i)\b(?:r2|qdrant|sqlite|file)://[^\s]+"
)
_FORBIDDEN_ABSOLUTE_FS_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:home|root|etc|var|srv|opt|mnt|tmp)/[^\s]+"
)
_FORBIDDEN_SENSITIVE_ENV_RE = re.compile(
    r"(?im)^\s*[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|DSN)"
    r"\s*=\s*\S+"
)

_MAX_TEXT_CHARS = 262_144
_MAX_JSON_DEPTH = 8
_MAX_JSON_ITEMS = 1_000


class WorkspaceContractError(ValueError):
    """Base error for Stage 8 workspace contract violations."""


class ForbiddenWorkspaceArtifactError(WorkspaceContractError):
    """Raised for production/raw/secret artifact kinds."""


class UnsafeWorkspacePathError(WorkspaceContractError):
    """Raised when an artifact reference can escape its workspace."""


class UnsafeWorkspacePayloadError(WorkspaceContractError):
    """Raised when a payload is not demonstrably sanitized."""


class WorkspaceScope(StrEnum):
    TASK = "TASK"
    EVAL = "EVAL"
    DIAGNOSTIC = "DIAGNOSTIC"
    HANDOFF = "HANDOFF"


class WorkspaceArtifactKind(StrEnum):
    REPORT = "REPORT"
    EVAL_SUMMARY = "EVAL_SUMMARY"
    CANDIDATE_PATCH = "CANDIDATE_PATCH"
    CHECKPOINT = "CHECKPOINT"
    HANDOFF = "HANDOFF"
    DIAGNOSTIC = "DIAGNOSTIC"


class WorkspaceArtifactFormat(StrEnum):
    JSON = "JSON"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class WorkspaceId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _WORKSPACE_ID_RE.fullmatch(self.value):
            raise WorkspaceContractError(
                "workspace id must be a generated ws-<32 lowercase hex> identifier"
            )

    @classmethod
    def from_safe_token(cls, *, scope: WorkspaceScope, task_token: str) -> WorkspaceId:
        if not isinstance(scope, WorkspaceScope):
            raise WorkspaceContractError("scope must be WorkspaceScope")
        if not isinstance(task_token, str) or not _SAFE_SEED_RE.fullmatch(task_token):
            raise WorkspaceContractError(
                "task_token must be a pre-sanitized opaque identifier, not raw task text"
            )
        digest = hashlib.sha256(
            f"{WORKSPACE_SCHEMA_VERSION}\x00{scope.value}\x00{task_token}".encode()
        ).hexdigest()[:32]
        return cls(f"ws-{digest}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class WorkspaceWritePolicy:
    isolated_task_workspace: bool = True
    production_write: bool = False
    r2_write: bool = False
    qdrant_write: bool = False
    production_sqlite_write: bool = False
    release_control: bool = False
    mcp_exposed: bool = False
    memory_runtime: bool = False
    skill_execution: bool = False
    answer_path_change: bool = False
    public_runtime_change: bool = False

    def __post_init__(self) -> None:
        values = {
            "isolated_task_workspace": self.isolated_task_workspace,
            "production_write": self.production_write,
            "r2_write": self.r2_write,
            "qdrant_write": self.qdrant_write,
            "production_sqlite_write": self.production_sqlite_write,
            "release_control": self.release_control,
            "mcp_exposed": self.mcp_exposed,
            "memory_runtime": self.memory_runtime,
            "skill_execution": self.skill_execution,
            "answer_path_change": self.answer_path_change,
            "public_runtime_change": self.public_runtime_change,
        }
        if any(not isinstance(value, bool) for value in values.values()):
            raise WorkspaceContractError("workspace policy values must be bool")
        if self.isolated_task_workspace is not True:
            raise WorkspaceContractError("Stage 8 workspace must remain isolated")
        forbidden_true = tuple(
            name
            for name, value in values.items()
            if name != "isolated_task_workspace" and value
        )
        if forbidden_true:
            raise WorkspaceContractError(
                f"Stage 8 workspace policy cannot grant: {', '.join(forbidden_true)}"
            )

    def as_dict(self) -> dict[str, bool]:
        return {
            "isolated_task_workspace": self.isolated_task_workspace,
            "production_write": self.production_write,
            "r2_write": self.r2_write,
            "qdrant_write": self.qdrant_write,
            "production_sqlite_write": self.production_sqlite_write,
            "release_control": self.release_control,
            "mcp_exposed": self.mcp_exposed,
            "memory_runtime": self.memory_runtime,
            "skill_execution": self.skill_execution,
            "answer_path_change": self.answer_path_change,
            "public_runtime_change": self.public_runtime_change,
        }


STAGE8_WRITE_POLICY = WorkspaceWritePolicy()


@dataclass(frozen=True, slots=True)
class WorkspaceArtifactRef:
    workspace_id: WorkspaceId
    kind: WorkspaceArtifactKind
    format: WorkspaceArtifactFormat
    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, WorkspaceId):
            raise WorkspaceContractError("workspace_id must be WorkspaceId")
        if not isinstance(self.kind, WorkspaceArtifactKind):
            raise WorkspaceContractError("kind must be WorkspaceArtifactKind")
        if not isinstance(self.format, WorkspaceArtifactFormat):
            raise WorkspaceContractError("format must be WorkspaceArtifactFormat")
        normalized = validate_relative_artifact_path(self.relative_path)
        if normalized != self.relative_path:
            raise UnsafeWorkspacePathError("artifact path must already be normalized")
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise WorkspaceContractError("sha256 must be lowercase hex digest")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise WorkspaceContractError("size_bytes must be a non-negative integer")

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id.value,
            "kind": self.kind.value,
            "format": self.format.value,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceCheckpoint:
    workspace_id: WorkspaceId
    checkpoint_id: str
    sequence: int
    metadata: dict[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, WorkspaceId):
            raise WorkspaceContractError("workspace_id must be WorkspaceId")
        validate_safe_identifier("checkpoint_id", self.checkpoint_id)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise WorkspaceContractError("checkpoint sequence must be a positive integer")
        if not isinstance(self.metadata, dict):
            raise WorkspaceContractError("checkpoint metadata must be a dict")
        validate_sanitized_json_payload(self.metadata)

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id.value,
            "checkpoint_id": self.checkpoint_id,
            "sequence": self.sequence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceManifest:
    workspace_id: WorkspaceId
    scope: WorkspaceScope
    write_policy: WorkspaceWritePolicy = STAGE8_WRITE_POLICY
    artifacts: tuple[WorkspaceArtifactRef, ...] = ()
    artifact_count: int = 0
    checkpoint_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, WorkspaceId):
            raise WorkspaceContractError("workspace_id must be WorkspaceId")
        if not isinstance(self.scope, WorkspaceScope):
            raise WorkspaceContractError("scope must be WorkspaceScope")
        if self.write_policy != STAGE8_WRITE_POLICY:
            raise WorkspaceContractError("manifest must use the fixed Stage 8 write policy")
        if any(not isinstance(item, WorkspaceArtifactRef) for item in self.artifacts):
            raise WorkspaceContractError("artifacts must contain WorkspaceArtifactRef only")
        if any(item.workspace_id != self.workspace_id for item in self.artifacts):
            raise WorkspaceContractError("artifact workspace_id must match manifest")
        if self.artifact_count != len(self.artifacts):
            raise WorkspaceContractError("artifact_count must match artifacts")
        if (
            isinstance(self.checkpoint_count, bool)
            or not isinstance(self.checkpoint_count, int)
            or self.checkpoint_count < 0
        ):
            raise WorkspaceContractError("checkpoint_count must be non-negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_id": self.workspace_id.value,
            "scope": self.scope.value,
            "write_policy": self.write_policy.as_dict(),
            "artifact_count": self.artifact_count,
            "checkpoint_count": self.checkpoint_count,
            "artifacts": [item.as_dict() for item in self.artifacts],
        }


def blocked_artifact_kind_values() -> frozenset[str]:
    return _BLOCKED_ARTIFACT_KIND_VALUES


def artifact_kind_from_value(value: WorkspaceArtifactKind | str) -> WorkspaceArtifactKind:
    if isinstance(value, WorkspaceArtifactKind):
        return value
    if not isinstance(value, str):
        raise WorkspaceContractError("artifact kind must be WorkspaceArtifactKind or string")
    normalized = value.strip().upper()
    if normalized in _BLOCKED_ARTIFACT_KIND_VALUES:
        raise ForbiddenWorkspaceArtifactError(
            f"artifact kind is forbidden in Stage 8 workspace: {normalized}"
        )
    try:
        return WorkspaceArtifactKind(normalized)
    except ValueError as exc:
        raise WorkspaceContractError(f"unknown workspace artifact kind: {value}") from exc


def validate_safe_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise WorkspaceContractError(f"{name} must be a sanitized opaque identifier")
    return value


def validate_relative_artifact_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise UnsafeWorkspacePathError("artifact path must be a non-empty string")
    if "\\" in value or value.startswith("~"):
        raise UnsafeWorkspacePathError("artifact path cannot use backslash or home expansion")
    path = PurePosixPath(value)
    if path.as_posix() != value:
        raise UnsafeWorkspacePathError("artifact path must be normalized")
    if path.is_absolute():
        raise UnsafeWorkspacePathError("artifact path must be workspace-relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeWorkspacePathError("artifact path cannot contain traversal components")
    if not path.parts:
        raise UnsafeWorkspacePathError("artifact path must name a file")
    for part in path.parts:
        if not _SAFE_PATH_COMPONENT_RE.fullmatch(part):
            raise UnsafeWorkspacePathError(
                "artifact path components must use safe alphanumeric/dot/dash/underscore names"
            )
    normalized = path.as_posix()
    if len(normalized) > 512:
        raise UnsafeWorkspacePathError("artifact path is too long")
    return normalized


def validate_sanitized_text(value: object) -> str:
    if not isinstance(value, str):
        raise UnsafeWorkspacePayloadError("text artifact must be a string")
    if len(value) > _MAX_TEXT_CHARS:
        raise UnsafeWorkspacePayloadError("text artifact exceeds Stage 8 size limit")
    if "\x00" in value:
        raise UnsafeWorkspacePayloadError("text artifact cannot contain NUL")
    for pattern, reason in (
        (_FORBIDDEN_LABEL_RE, "raw/private payload label"),
        (_FORBIDDEN_SECRET_RE, "credential/secret material"),
        (_FORBIDDEN_STORAGE_URI_RE, "raw storage/database URI"),
        (_FORBIDDEN_ABSOLUTE_FS_RE, "absolute filesystem path"),
        (_FORBIDDEN_SENSITIVE_ENV_RE, "sensitive environment assignment"),
    ):
        if pattern.search(value):
            raise UnsafeWorkspacePayloadError(
                f"text artifact contains forbidden {reason}"
            )
    return value


def validate_sanitized_json_payload(value: object) -> None:
    _validate_json_value(value, depth=0)


def _validate_json_value(value: object, *, depth: int) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise UnsafeWorkspacePayloadError("JSON artifact exceeds maximum nesting depth")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsafeWorkspacePayloadError("JSON artifact cannot contain NaN/Infinity")
        return
    if isinstance(value, str):
        validate_sanitized_text(value)
        return
    if isinstance(value, list):
        if len(value) > _MAX_JSON_ITEMS:
            raise UnsafeWorkspacePayloadError("JSON artifact collection is too large")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _MAX_JSON_ITEMS:
            raise UnsafeWorkspacePayloadError("JSON artifact object is too large")
        for key, item in value.items():
            if not isinstance(key, str) or not _JSON_KEY_RE.fullmatch(key):
                raise UnsafeWorkspacePayloadError("JSON keys must be sanitized identifiers")
            if key.casefold() in _FORBIDDEN_PAYLOAD_FIELDS:
                raise UnsafeWorkspacePayloadError(
                    f"JSON artifact field is forbidden in Stage 8: {key}"
                )
            _validate_json_value(item, depth=depth + 1)
        return
    raise UnsafeWorkspacePayloadError(
        f"JSON artifact contains unsupported value type: {type(value).__name__}"
    )


__all__ = [
    "WORKSPACE_SCHEMA_VERSION",
    "WorkspaceContractError",
    "ForbiddenWorkspaceArtifactError",
    "UnsafeWorkspacePathError",
    "UnsafeWorkspacePayloadError",
    "WorkspaceScope",
    "WorkspaceArtifactKind",
    "WorkspaceArtifactFormat",
    "WorkspaceId",
    "WorkspaceWritePolicy",
    "STAGE8_WRITE_POLICY",
    "WorkspaceArtifactRef",
    "WorkspaceCheckpoint",
    "WorkspaceManifest",
    "blocked_artifact_kind_values",
    "artifact_kind_from_value",
    "validate_safe_identifier",
    "validate_relative_artifact_path",
    "validate_sanitized_text",
    "validate_sanitized_json_payload",
]
