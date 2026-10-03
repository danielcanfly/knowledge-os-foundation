from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

MEMORY_SCHEMA_VERSION = "m27-governed-memory/v1"

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,160}$")
_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:#-]{0,63}$")
_SAFE_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_MEMORY_ID_RE = re.compile(r"^mem-[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_FORBIDDEN_MEMORY_CLASS_VALUES = frozenset(
    {
        "SEMANTIC_USER",
        "USER_PROFILE",
        "PERSONAL_PROFILE",
        "KNOWLEDGE",
        "PRODUCTION_KNOWLEDGE",
        "EVIDENCE",
        "CITATION",
    }
)

_FORBIDDEN_LABEL_RE = re.compile(
    r"(?im)^\s*(?:raw[_ -]?query|raw[_ -]?answer|"
    r"(?:full[_ -]?)?evidence[_ -]?(?:body|text)|"
    r"(?:full[_ -]?)?source[_ -]?(?:body|text)|"
    r"provider[_ -]?prompt|credentials?|secrets?|api[_ -]?key|"
    r"access[_ -]?token|auth[_ -]?token|environment[_ -]?value|env[_ -]?value|"
    r"password|private[_ -]?key)\s*[:=]"
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

_MAX_SUMMARY_CHARS = 4096
_MAX_TAGS = 16


class MemoryContractError(ValueError):
    """Base error for Stage 10 governed-memory contract violations."""


class ForbiddenMemoryClassError(MemoryContractError):
    """Raised when Stage 10 is asked to persist a forbidden memory class."""


class UnsafeMemoryPayloadError(MemoryContractError):
    """Raised when candidate memory text is not demonstrably sanitized."""


class MemoryClass(StrEnum):
    EPISODIC = "EPISODIC"
    PROJECT = "PROJECT"


class MemoryOriginKind(StrEnum):
    TASK_SUMMARY = "TASK_SUMMARY"
    PROJECT_SUMMARY = "PROJECT_SUMMARY"
    TRACE_SUMMARY = "TRACE_SUMMARY"
    EVAL_SUMMARY = "EVAL_SUMMARY"
    OPERATOR_PROPOSAL = "OPERATOR_PROPOSAL"


class MemoryReviewDecision(StrEnum):
    RETAIN_CANDIDATE = "RETAIN_CANDIDATE"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"


@dataclass(frozen=True, slots=True)
class MemoryActivation:
    enabled: bool = False
    isolated_runtime: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool) or not isinstance(self.isolated_runtime, bool):
            raise MemoryContractError("memory activation values must be bool")
        if self.enabled and not self.isolated_runtime:
            raise MemoryContractError(
                "Stage 10 memory may be enabled only inside an isolated runtime"
            )

    def as_dict(self) -> dict[str, bool]:
        return {
            "enabled": self.enabled,
            "isolated_runtime": self.isolated_runtime,
        }


@dataclass(frozen=True, slots=True)
class MemoryGovernancePolicy:
    candidate_only: bool = True
    candidate_store_write: bool = True
    episodic_allowed: bool = True
    project_allowed: bool = True
    semantic_user_memory_allowed: bool = False
    knowledge_authority: bool = False
    citation_eligible: bool = False
    answer_context_enabled: bool = False
    can_override_cited_knowledge: bool = False
    can_promote_to_knowledge: bool = False
    production_write: bool = False
    r2_write: bool = False
    qdrant_write: bool = False
    production_sqlite_write: bool = False
    release_control: bool = False
    mcp_exposed: bool = False
    workspace_read: bool = False
    skill_execution: bool = False
    network_access: bool = False

    def __post_init__(self) -> None:
        values = self.as_dict()
        if any(not isinstance(value, bool) for value in values.values()):
            raise MemoryContractError("memory governance policy values must be bool")

        required_true = {
            "candidate_only",
            "candidate_store_write",
            "episodic_allowed",
            "project_allowed",
        }
        required_false = set(values) - required_true

        invalid_true = tuple(name for name in required_true if values[name] is not True)
        invalid_false = tuple(name for name in required_false if values[name] is not False)
        if invalid_true or invalid_false:
            details = ", ".join((*invalid_true, *invalid_false))
            raise MemoryContractError(
                f"Stage 10 memory governance policy cannot be widened or weakened: {details}"
            )

    def as_dict(self) -> dict[str, bool]:
        return {
            "candidate_only": self.candidate_only,
            "candidate_store_write": self.candidate_store_write,
            "episodic_allowed": self.episodic_allowed,
            "project_allowed": self.project_allowed,
            "semantic_user_memory_allowed": self.semantic_user_memory_allowed,
            "knowledge_authority": self.knowledge_authority,
            "citation_eligible": self.citation_eligible,
            "answer_context_enabled": self.answer_context_enabled,
            "can_override_cited_knowledge": self.can_override_cited_knowledge,
            "can_promote_to_knowledge": self.can_promote_to_knowledge,
            "production_write": self.production_write,
            "r2_write": self.r2_write,
            "qdrant_write": self.qdrant_write,
            "production_sqlite_write": self.production_sqlite_write,
            "release_control": self.release_control,
            "mcp_exposed": self.mcp_exposed,
            "workspace_read": self.workspace_read,
            "skill_execution": self.skill_execution,
            "network_access": self.network_access,
        }


STAGE10_MEMORY_POLICY = MemoryGovernancePolicy()


@dataclass(frozen=True, slots=True)
class MemoryCandidateId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _MEMORY_ID_RE.fullmatch(self.value):
            raise MemoryContractError(
                "memory id must be a generated mem-<32 lowercase hex> identifier"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MemoryProvenance:
    origin_kind: MemoryOriginKind
    origin_ref: str
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin_kind, MemoryOriginKind):
            raise MemoryContractError("origin_kind must be MemoryOriginKind")
        validate_safe_token("origin_ref", self.origin_ref)
        if self.source_sha256 is not None and (
            not isinstance(self.source_sha256, str)
            or not _SHA256_RE.fullmatch(self.source_sha256)
        ):
            raise MemoryContractError("source_sha256 must be lowercase SHA-256 or None")

    def as_dict(self) -> dict[str, object]:
        return {
            "origin_kind": self.origin_kind.value,
            "origin_ref": self.origin_ref,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_id: MemoryCandidateId
    memory_class: MemoryClass
    scope_token: str
    summary: str
    provenance: MemoryProvenance
    tags: tuple[str, ...] = ()
    governance_policy: MemoryGovernancePolicy = STAGE10_MEMORY_POLICY

    def __post_init__(self) -> None:
        if not isinstance(self.memory_id, MemoryCandidateId):
            raise MemoryContractError("memory_id must be MemoryCandidateId")
        if not isinstance(self.memory_class, MemoryClass):
            raise MemoryContractError("memory_class must be MemoryClass")
        validate_safe_token("scope_token", self.scope_token)
        validate_memory_summary(self.summary)
        validate_tags(self.tags)
        if not isinstance(self.provenance, MemoryProvenance):
            raise MemoryContractError("provenance must be MemoryProvenance")
        if self.governance_policy != STAGE10_MEMORY_POLICY:
            raise MemoryContractError(
                "memory candidate must use the fixed Stage 10 governance policy"
            )

        expected = derive_memory_id(
            memory_class=self.memory_class,
            scope_token=self.scope_token,
            summary=self.summary,
            provenance=self.provenance,
            tags=self.tags,
        )
        if self.memory_id != expected:
            raise MemoryContractError("memory_id does not match canonical candidate content")

    @classmethod
    def create(
        cls,
        *,
        memory_class: MemoryClass | str,
        scope_token: str,
        summary: str,
        provenance: MemoryProvenance,
        tags: tuple[str, ...] = (),
    ) -> MemoryCandidate:
        normalized_class = memory_class_from_value(memory_class)
        validate_safe_token("scope_token", scope_token)
        validate_memory_summary(summary)
        normalized_tags = validate_tags(tags)
        memory_id = derive_memory_id(
            memory_class=normalized_class,
            scope_token=scope_token,
            summary=summary,
            provenance=provenance,
            tags=normalized_tags,
        )
        return cls(
            memory_id=memory_id,
            memory_class=normalized_class,
            scope_token=scope_token,
            summary=summary,
            provenance=provenance,
            tags=normalized_tags,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "memory_id": self.memory_id.value,
            "memory_class": self.memory_class.value,
            "scope_token": self.scope_token,
            "summary": self.summary,
            "tags": list(self.tags),
            "provenance": self.provenance.as_dict(),
            "governance_policy": self.governance_policy.as_dict(),
            "authority": {
                "status": "UNVERIFIED_MEMORY_CANDIDATE",
                "knowledge_authority": False,
                "citation_eligible": False,
                "answer_context_enabled": False,
                "can_override_cited_knowledge": False,
            },
        }


@dataclass(frozen=True, slots=True)
class MemoryReviewReceipt:
    memory_id: MemoryCandidateId
    sequence: int
    decision: MemoryReviewDecision
    reviewer_token: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.memory_id, MemoryCandidateId):
            raise MemoryContractError("memory_id must be MemoryCandidateId")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise MemoryContractError("review sequence must be a positive integer")
        if not isinstance(self.decision, MemoryReviewDecision):
            raise MemoryContractError("decision must be MemoryReviewDecision")
        validate_safe_token("reviewer_token", self.reviewer_token)
        validate_reason_codes(self.reason_codes)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "memory_id": self.memory_id.value,
            "sequence": self.sequence,
            "decision": self.decision.value,
            "reviewer_token": self.reviewer_token,
            "reason_codes": list(self.reason_codes),
            "authority": {
                "candidate_only": True,
                "knowledge_authority": False,
                "citation_eligible": False,
                "can_promote_to_knowledge": False,
            },
        }


def forbidden_memory_class_values() -> frozenset[str]:
    return _FORBIDDEN_MEMORY_CLASS_VALUES


def memory_class_from_value(value: MemoryClass | str) -> MemoryClass:
    if isinstance(value, MemoryClass):
        return value
    if not isinstance(value, str):
        raise MemoryContractError("memory class must be MemoryClass or string")
    normalized = value.strip().upper()
    if normalized in _FORBIDDEN_MEMORY_CLASS_VALUES:
        raise ForbiddenMemoryClassError(
            f"memory class is forbidden in Stage 10: {normalized}"
        )
    try:
        return MemoryClass(normalized)
    except ValueError as exc:
        raise MemoryContractError(f"unknown Stage 10 memory class: {value}") from exc


def validate_safe_token(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN_RE.fullmatch(value):
        raise MemoryContractError(
            f"{name} must be a pre-sanitized opaque identifier, not raw text"
        )
    return value


def validate_memory_summary(value: object) -> str:
    if not isinstance(value, str):
        raise UnsafeMemoryPayloadError("memory summary must be text")
    if not value or len(value) > _MAX_SUMMARY_CHARS:
        raise UnsafeMemoryPayloadError(
            f"memory summary must contain 1..{_MAX_SUMMARY_CHARS} characters"
        )
    if "\x00" in value:
        raise UnsafeMemoryPayloadError("memory summary cannot contain NUL")
    if _FORBIDDEN_LABEL_RE.search(value):
        raise UnsafeMemoryPayloadError("memory summary contains a forbidden raw/private label")
    if _FORBIDDEN_SECRET_RE.search(value):
        raise UnsafeMemoryPayloadError("memory summary appears to contain secret material")
    if _FORBIDDEN_STORAGE_URI_RE.search(value):
        raise UnsafeMemoryPayloadError("memory summary exposes a raw storage/database URI")
    if _FORBIDDEN_ABSOLUTE_FS_RE.search(value):
        raise UnsafeMemoryPayloadError("memory summary exposes an absolute server path")
    if _FORBIDDEN_SENSITIVE_ENV_RE.search(value):
        raise UnsafeMemoryPayloadError("memory summary appears to contain a sensitive env value")
    return value


def validate_tags(tags: object) -> tuple[str, ...]:
    if not isinstance(tags, tuple):
        raise MemoryContractError("tags must be a tuple")
    if len(tags) > _MAX_TAGS:
        raise MemoryContractError(f"at most {_MAX_TAGS} memory tags are allowed")
    if any(not isinstance(tag, str) or not _SAFE_TAG_RE.fullmatch(tag) for tag in tags):
        raise MemoryContractError("memory tags must be sanitized opaque labels")
    if tuple(sorted(set(tags))) != tags:
        raise MemoryContractError("memory tags must be unique and sorted")
    return tags


def validate_reason_codes(reason_codes: object) -> tuple[str, ...]:
    if not isinstance(reason_codes, tuple) or not reason_codes:
        raise MemoryContractError("review reason_codes must be a non-empty tuple")
    if any(
        not isinstance(code, str) or not _SAFE_REASON_RE.fullmatch(code)
        for code in reason_codes
    ):
        raise MemoryContractError("review reason codes must use SAFE_UPPER_SNAKE_CASE")
    if tuple(sorted(set(reason_codes))) != reason_codes:
        raise MemoryContractError("review reason codes must be unique and sorted")
    return reason_codes


def derive_memory_id(
    *,
    memory_class: MemoryClass,
    scope_token: str,
    summary: str,
    provenance: MemoryProvenance,
    tags: tuple[str, ...],
) -> MemoryCandidateId:
    if not isinstance(memory_class, MemoryClass):
        raise MemoryContractError("memory_class must be MemoryClass")
    validate_safe_token("scope_token", scope_token)
    validate_memory_summary(summary)
    validate_tags(tags)
    if not isinstance(provenance, MemoryProvenance):
        raise MemoryContractError("provenance must be MemoryProvenance")

    summary_sha256 = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    canonical = "\x00".join(
        (
            MEMORY_SCHEMA_VERSION,
            memory_class.value,
            scope_token,
            provenance.origin_kind.value,
            provenance.origin_ref,
            provenance.source_sha256 or "",
            summary_sha256,
            ",".join(tags),
        )
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return MemoryCandidateId(f"mem-{digest}")
