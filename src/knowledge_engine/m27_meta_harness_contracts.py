from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

META_HARNESS_SCHEMA_VERSION = "m27-meta-harness-candidate/v1"

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,256}$")
_SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_SAFE_FILE_LABEL_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}(?:/[A-Za-z0-9][A-Za-z0-9_.-]{0,127})*$"
)
_CANDIDATE_ID_RE = re.compile(r"^mhc-[0-9a-f]{32}$")
_MAX_SUMMARY_CHARS = 2048
_MAX_ITEMS = 256

_FORBIDDEN_TEXT_RE = re.compile(
    r"(?i)(?:"
    r"raw[_ -]?query|raw[_ -]?answer|"
    r"full[_ -]?evidence[_ -]?(?:body|text)|"
    r"full[_ -]?source[_ -]?(?:body|text)|"
    r"provider[_ -]?prompt|private[_ -]?payload|"
    r"credentials?|secrets?|api[_ -]?key|auth[_ -]?token|access[_ -]?token|"
    r"\benv\b|\benvironment\b|"
    r"\bqdrant\b|\br2://|\bsqlite\b|\bpostgres\b|\bmysql\b|\bs3://|"
    r"/home/ubuntu/|(?:^|[\s/])\.\./|"
    r"production[_ -]?path|production[_ -]?object[_ -]?path|release[_ -]?pointer"
    r")"
)


class MetaHarnessContractError(ValueError):
    """Base error for Stage 12 candidate-only contract violations."""


class UnsafeMetaHarnessPayloadError(MetaHarnessContractError):
    """Raised when candidate metadata is not demonstrably sanitized."""


class MetaHarnessAuthority(StrEnum):
    CANDIDATE_ONLY = "CANDIDATE_ONLY"


class MetaHarnessCandidateKind(StrEnum):
    HARNESS_PLAN = "HARNESS_PLAN"
    TEST_PLAN = "TEST_PLAN"
    PATCH_INTENT = "PATCH_INTENT"
    EVAL_PLAN = "EVAL_PLAN"
    VALIDATION_REPORT = "VALIDATION_REPORT"
    PROMOTION_PROPOSAL = "PROMOTION_PROPOSAL"
    ROLLBACK_PLAN = "ROLLBACK_PLAN"
    RISK_MATRIX = "RISK_MATRIX"


class MetaHarnessRiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MetaHarnessCandidateStatus(StrEnum):
    PROPOSED = "PROPOSED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class MetaHarnessGateRequirement:
    gate_name: str
    required: bool = True
    offline_only: bool = True
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        validate_safe_token("gate_name", self.gate_name)
        for name, value in (
            ("required", self.required),
            ("offline_only", self.offline_only),
            ("requires_human_review", self.requires_human_review),
        ):
            if not isinstance(value, bool):
                raise MetaHarnessContractError(f"{name} must be bool")
        if not self.required or not self.offline_only or not self.requires_human_review:
            raise MetaHarnessContractError(
                "Stage 12 gates must remain required, offline-only, and human-reviewed"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "gate_name": self.gate_name,
            "required": self.required,
            "offline_only": self.offline_only,
            "requires_human_review": self.requires_human_review,
        }


@dataclass(frozen=True, slots=True)
class MetaHarnessInput:
    source_refs: tuple[str, ...]
    target_failure_class: str
    reason_codes: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    eval_summary_count: int = 0
    gate_summary_count: int = 0

    def __post_init__(self) -> None:
        if (
            validate_safe_token_tuple("source_refs", self.source_refs, allow_empty=False)
            != self.source_refs
        ):
            raise MetaHarnessContractError("source_refs must already be unique and sorted")
        validate_safe_code("target_failure_class", self.target_failure_class)
        if validate_safe_code_tuple("reason_codes", self.reason_codes) != self.reason_codes:
            raise MetaHarnessContractError("reason_codes must already be unique and sorted")
        if validate_safe_token_tuple("artifact_ids", self.artifact_ids) != self.artifact_ids:
            raise MetaHarnessContractError("artifact_ids must already be unique and sorted")
        validate_nonnegative_int("eval_summary_count", self.eval_summary_count)
        validate_nonnegative_int("gate_summary_count", self.gate_summary_count)

    @classmethod
    def create(
        cls,
        *,
        source_refs: tuple[str, ...],
        target_failure_class: str,
        reason_codes: tuple[str, ...] = (),
        artifact_ids: tuple[str, ...] = (),
        eval_summary_count: int = 0,
        gate_summary_count: int = 0,
    ) -> MetaHarnessInput:
        return cls(
            source_refs=validate_safe_token_tuple("source_refs", source_refs, allow_empty=False),
            target_failure_class=validate_safe_code("target_failure_class", target_failure_class),
            reason_codes=validate_safe_code_tuple("reason_codes", reason_codes),
            artifact_ids=validate_safe_token_tuple("artifact_ids", artifact_ids),
            eval_summary_count=validate_nonnegative_int("eval_summary_count", eval_summary_count),
            gate_summary_count=validate_nonnegative_int("gate_summary_count", gate_summary_count),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_refs": list(self.source_refs),
            "target_failure_class": self.target_failure_class,
            "reason_codes": list(self.reason_codes),
            "artifact_ids": list(self.artifact_ids),
            "eval_summary_count": self.eval_summary_count,
            "gate_summary_count": self.gate_summary_count,
        }


@dataclass(frozen=True, slots=True)
class MetaHarnessPatchIntent:
    candidate_files: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        if validate_candidate_files(self.candidate_files) != self.candidate_files:
            raise MetaHarnessContractError("candidate_files must already be unique and sorted")
        validate_sanitized_meta_text("description", self.description)

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_files": list(self.candidate_files),
            "description": self.description,
            "patch_material_present": False,
        }


@dataclass(frozen=True, slots=True)
class MetaHarnessEvalPlan:
    test_names: tuple[str, ...]
    gate_requirements: tuple[MetaHarnessGateRequirement, ...]
    description: str

    def __post_init__(self) -> None:
        if validate_safe_token_tuple("test_names", self.test_names) != self.test_names:
            raise MetaHarnessContractError("test_names must already be unique and sorted")
        if validate_gate_requirements(self.gate_requirements) != self.gate_requirements:
            raise MetaHarnessContractError("gate_requirements must already be unique and sorted")
        validate_sanitized_meta_text("description", self.description)

    def as_dict(self) -> dict[str, object]:
        return {
            "test_names": list(self.test_names),
            "gate_requirements": [item.as_dict() for item in self.gate_requirements],
            "description": self.description,
            "execution_authority": False,
        }


@dataclass(frozen=True, slots=True)
class MetaHarnessPlan:
    patch_intent: MetaHarnessPatchIntent
    eval_plan: MetaHarnessEvalPlan
    rollback_plan: str
    risk_matrix: str

    def __post_init__(self) -> None:
        if not isinstance(self.patch_intent, MetaHarnessPatchIntent):
            raise MetaHarnessContractError("patch_intent must be MetaHarnessPatchIntent")
        if not isinstance(self.eval_plan, MetaHarnessEvalPlan):
            raise MetaHarnessContractError("eval_plan must be MetaHarnessEvalPlan")
        validate_sanitized_meta_text("rollback_plan", self.rollback_plan)
        validate_sanitized_meta_text("risk_matrix", self.risk_matrix)


@dataclass(frozen=True, slots=True)
class MetaHarnessCandidate:
    candidate_id: str
    kind: MetaHarnessCandidateKind
    input_metadata: MetaHarnessInput
    candidate_summary: str
    expected_improvement_class: str
    risk_class: MetaHarnessRiskClass
    candidate_files: tuple[str, ...]
    test_names: tuple[str, ...]
    gate_requirements: tuple[MetaHarnessGateRequirement, ...]
    status: MetaHarnessCandidateStatus = MetaHarnessCandidateStatus.PROPOSED
    authority: MetaHarnessAuthority = MetaHarnessAuthority.CANDIDATE_ONLY
    candidate_only: bool = True
    requires_human_review: bool = True
    requires_offline_gate: bool = True
    auto_apply: bool = False
    auto_merge: bool = False
    auto_promote: bool = False
    production_write: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID_RE.fullmatch(
            self.candidate_id
        ):
            raise MetaHarnessContractError(
                "candidate_id must be generated as mhc-<32 lowercase hex>"
            )
        if not isinstance(self.kind, MetaHarnessCandidateKind):
            raise MetaHarnessContractError("kind must be MetaHarnessCandidateKind")
        if not isinstance(self.input_metadata, MetaHarnessInput):
            raise MetaHarnessContractError("input_metadata must be MetaHarnessInput")
        validate_sanitized_meta_text("candidate_summary", self.candidate_summary)
        validate_safe_code("expected_improvement_class", self.expected_improvement_class)
        if not isinstance(self.risk_class, MetaHarnessRiskClass):
            raise MetaHarnessContractError("risk_class must be MetaHarnessRiskClass")
        if validate_candidate_files(self.candidate_files) != self.candidate_files:
            raise MetaHarnessContractError("candidate_files must already be unique and sorted")
        if validate_safe_token_tuple("test_names", self.test_names) != self.test_names:
            raise MetaHarnessContractError("test_names must already be unique and sorted")
        if validate_gate_requirements(self.gate_requirements) != self.gate_requirements:
            raise MetaHarnessContractError("gate_requirements must already be unique and sorted")
        if not self.gate_requirements:
            raise MetaHarnessContractError("Stage 12 candidates require at least one offline gate")
        if not isinstance(self.status, MetaHarnessCandidateStatus):
            raise MetaHarnessContractError("status must be MetaHarnessCandidateStatus")
        if self.authority is not MetaHarnessAuthority.CANDIDATE_ONLY:
            raise MetaHarnessContractError("Stage 12 authority is candidate-only")

        flags = {
            "candidate_only": self.candidate_only,
            "requires_human_review": self.requires_human_review,
            "requires_offline_gate": self.requires_offline_gate,
            "auto_apply": self.auto_apply,
            "auto_merge": self.auto_merge,
            "auto_promote": self.auto_promote,
            "production_write": self.production_write,
        }
        if any(not isinstance(value, bool) for value in flags.values()):
            raise MetaHarnessContractError("candidate governance flags must be bool")
        if self.candidate_only is not True:
            raise MetaHarnessContractError("Stage 12 artifacts must remain candidate-only")
        if self.requires_human_review is not True:
            raise MetaHarnessContractError("Stage 12 candidates require human review")
        if self.requires_offline_gate is not True:
            raise MetaHarnessContractError("Stage 12 candidates require offline gates")
        if self.auto_apply is not False:
            raise MetaHarnessContractError("Stage 12 candidates can never auto-apply")
        if self.auto_merge is not False:
            raise MetaHarnessContractError("Stage 12 candidates can never auto-merge")
        if self.auto_promote is not False:
            raise MetaHarnessContractError("Stage 12 candidates can never auto-promote")
        if self.production_write is not False:
            raise MetaHarnessContractError("Stage 12 candidates can never write production")

        expected = derive_meta_harness_candidate_id(
            kind=self.kind,
            input_metadata=self.input_metadata,
            candidate_summary=self.candidate_summary,
            expected_improvement_class=self.expected_improvement_class,
            risk_class=self.risk_class,
            candidate_files=self.candidate_files,
            test_names=self.test_names,
            gate_requirements=self.gate_requirements,
        )
        if expected != self.candidate_id:
            raise MetaHarnessContractError(
                "candidate_id does not match canonical candidate metadata"
            )

    @classmethod
    def create(
        cls,
        *,
        kind: MetaHarnessCandidateKind,
        input_metadata: MetaHarnessInput,
        candidate_summary: str,
        expected_improvement_class: str,
        risk_class: MetaHarnessRiskClass,
        candidate_files: tuple[str, ...],
        test_names: tuple[str, ...],
        gate_requirements: tuple[MetaHarnessGateRequirement, ...],
    ) -> MetaHarnessCandidate:
        if not isinstance(kind, MetaHarnessCandidateKind):
            raise MetaHarnessContractError("kind must be MetaHarnessCandidateKind")
        if not isinstance(input_metadata, MetaHarnessInput):
            raise MetaHarnessContractError("input_metadata must be MetaHarnessInput")
        if not isinstance(risk_class, MetaHarnessRiskClass):
            raise MetaHarnessContractError("risk_class must be MetaHarnessRiskClass")
        summary = validate_sanitized_meta_text("candidate_summary", candidate_summary)
        improvement = validate_safe_code("expected_improvement_class", expected_improvement_class)
        files = validate_candidate_files(candidate_files)
        tests = validate_safe_token_tuple("test_names", test_names)
        gates = validate_gate_requirements(gate_requirements)
        if not gates:
            raise MetaHarnessContractError("Stage 12 candidates require at least one offline gate")
        candidate_id = derive_meta_harness_candidate_id(
            kind=kind,
            input_metadata=input_metadata,
            candidate_summary=summary,
            expected_improvement_class=improvement,
            risk_class=risk_class,
            candidate_files=files,
            test_names=tests,
            gate_requirements=gates,
        )
        return cls(
            candidate_id=candidate_id,
            kind=kind,
            input_metadata=input_metadata,
            candidate_summary=summary,
            expected_improvement_class=improvement,
            risk_class=risk_class,
            candidate_files=files,
            test_names=tests,
            gate_requirements=gates,
        )

    @property
    def active(self) -> bool:
        return self.status in {
            MetaHarnessCandidateStatus.PROPOSED,
            MetaHarnessCandidateStatus.READY_FOR_REVIEW,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": META_HARNESS_SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "input_metadata": self.input_metadata.as_dict(),
            "candidate_summary": self.candidate_summary,
            "expected_improvement_class": self.expected_improvement_class,
            "risk_class": self.risk_class.value,
            "candidate_files": list(self.candidate_files),
            "test_names": list(self.test_names),
            "gate_requirements": [item.as_dict() for item in self.gate_requirements],
            "status": self.status.value,
            "active": self.active,
            "authority": self.authority.value,
            "candidate_only": self.candidate_only,
            "requires_human_review": self.requires_human_review,
            "requires_offline_gate": self.requires_offline_gate,
            "auto_apply": self.auto_apply,
            "auto_merge": self.auto_merge,
            "auto_promote": self.auto_promote,
            "production_write": self.production_write,
        }


@dataclass(frozen=True, slots=True)
class MetaHarnessReport:
    candidate_id: str
    kind: MetaHarnessCandidateKind
    status: MetaHarnessCandidateStatus
    active: bool
    target_failure_class: str
    source_ref_count: int
    artifact_count: int
    candidate_file_count: int
    test_count: int
    gate_count: int
    risk_class: MetaHarnessRiskClass
    candidate_summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID_RE.fullmatch(
            self.candidate_id
        ):
            raise MetaHarnessContractError("report candidate_id is invalid")
        if not isinstance(self.kind, MetaHarnessCandidateKind):
            raise MetaHarnessContractError("report kind is invalid")
        if not isinstance(self.status, MetaHarnessCandidateStatus):
            raise MetaHarnessContractError("report status is invalid")
        if not isinstance(self.active, bool):
            raise MetaHarnessContractError("report active must be bool")
        validate_safe_code("target_failure_class", self.target_failure_class)
        for name, value in (
            ("source_ref_count", self.source_ref_count),
            ("artifact_count", self.artifact_count),
            ("candidate_file_count", self.candidate_file_count),
            ("test_count", self.test_count),
            ("gate_count", self.gate_count),
        ):
            validate_nonnegative_int(name, value)
        if not isinstance(self.risk_class, MetaHarnessRiskClass):
            raise MetaHarnessContractError("report risk_class is invalid")
        validate_sanitized_meta_text("candidate_summary", self.candidate_summary)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": META_HARNESS_SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "active": self.active,
            "target_failure_class": self.target_failure_class,
            "source_ref_count": self.source_ref_count,
            "artifact_count": self.artifact_count,
            "candidate_file_count": self.candidate_file_count,
            "test_count": self.test_count,
            "gate_count": self.gate_count,
            "risk_class": self.risk_class.value,
            "candidate_summary": self.candidate_summary,
            "governance": {
                "candidate_only": True,
                "requires_human_review": True,
                "requires_offline_gate": True,
                "auto_apply": False,
                "auto_merge": False,
                "auto_promote": False,
                "production_write": False,
                "runtime_behavior_change": False,
            },
        }


def validate_safe_token(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN_RE.fullmatch(value):
        raise UnsafeMetaHarnessPayloadError(f"{name} must be a pre-sanitized opaque identifier")
    _reject_forbidden_meta_text(name, value)
    return value


def validate_safe_code(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_CODE_RE.fullmatch(value):
        raise UnsafeMetaHarnessPayloadError(f"{name} must use bounded SAFE_UPPER_SNAKE_CASE")
    _reject_forbidden_meta_text(name, value)
    return value


def validate_sanitized_meta_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise UnsafeMetaHarnessPayloadError(f"{name} must be non-empty text")
    if len(value) > _MAX_SUMMARY_CHARS:
        raise UnsafeMetaHarnessPayloadError(f"{name} exceeds Stage 12 bounded summary size")
    if "\\x00" in value:
        raise UnsafeMetaHarnessPayloadError(f"{name} cannot contain NUL")
    _reject_forbidden_meta_text(name, value)
    return value


def validate_nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MetaHarnessContractError(f"{name} must be a non-negative integer")
    return value


def validate_safe_token_tuple(
    name: str,
    values: object,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise MetaHarnessContractError(f"{name} must be a tuple")
    if not allow_empty and not values:
        raise MetaHarnessContractError(f"{name} must not be empty")
    if len(values) > _MAX_ITEMS:
        raise MetaHarnessContractError(f"too many {name}")
    for value in values:
        validate_safe_token(name, value)
    return tuple(sorted(set(values)))


def validate_safe_code_tuple(name: str, values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise MetaHarnessContractError(f"{name} must be a tuple")
    if len(values) > _MAX_ITEMS:
        raise MetaHarnessContractError(f"too many {name}")
    for value in values:
        validate_safe_code(name, value)
    return tuple(sorted(set(values)))


def validate_candidate_files(candidate_files: object) -> tuple[str, ...]:
    if not isinstance(candidate_files, tuple):
        raise MetaHarnessContractError("candidate_files must be a tuple")
    if len(candidate_files) > _MAX_ITEMS:
        raise MetaHarnessContractError("too many candidate_files")
    normalized: list[str] = []
    for value in candidate_files:
        if (
            not isinstance(value, str)
            or not _SAFE_FILE_LABEL_RE.fullmatch(value)
            or value.startswith("/")
            or ".." in value.split("/")
        ):
            raise UnsafeMetaHarnessPayloadError(
                "candidate_files must be sanitized repository-relative labels"
            )
        _reject_forbidden_meta_text("candidate_file", value)
        normalized.append(value)
    return tuple(sorted(set(normalized)))


def validate_gate_requirements(
    requirements: object,
) -> tuple[MetaHarnessGateRequirement, ...]:
    if not isinstance(requirements, tuple):
        raise MetaHarnessContractError("gate_requirements must be a tuple")
    if len(requirements) > _MAX_ITEMS:
        raise MetaHarnessContractError("too many gate_requirements")
    if any(not isinstance(item, MetaHarnessGateRequirement) for item in requirements):
        raise MetaHarnessContractError(
            "gate_requirements must contain MetaHarnessGateRequirement only"
        )
    by_name = {item.gate_name: item for item in requirements}
    return tuple(by_name[name] for name in sorted(by_name))


def derive_meta_harness_candidate_id(
    *,
    kind: MetaHarnessCandidateKind,
    input_metadata: MetaHarnessInput,
    candidate_summary: str,
    expected_improvement_class: str,
    risk_class: MetaHarnessRiskClass,
    candidate_files: tuple[str, ...],
    test_names: tuple[str, ...],
    gate_requirements: tuple[MetaHarnessGateRequirement, ...],
) -> str:
    if not isinstance(kind, MetaHarnessCandidateKind):
        raise MetaHarnessContractError("kind must be MetaHarnessCandidateKind")
    if not isinstance(input_metadata, MetaHarnessInput):
        raise MetaHarnessContractError("input_metadata must be MetaHarnessInput")
    if not isinstance(risk_class, MetaHarnessRiskClass):
        raise MetaHarnessContractError("risk_class must be MetaHarnessRiskClass")
    summary = validate_sanitized_meta_text("candidate_summary", candidate_summary)
    improvement = validate_safe_code("expected_improvement_class", expected_improvement_class)
    files = validate_candidate_files(candidate_files)
    tests = validate_safe_token_tuple("test_names", test_names)
    gates = validate_gate_requirements(gate_requirements)
    summary_sha256 = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    canonical = "\\x00".join(
        (
            META_HARNESS_SCHEMA_VERSION,
            kind.value,
            ",".join(input_metadata.source_refs),
            input_metadata.target_failure_class,
            ",".join(input_metadata.reason_codes),
            ",".join(input_metadata.artifact_ids),
            str(input_metadata.eval_summary_count),
            str(input_metadata.gate_summary_count),
            summary_sha256,
            improvement,
            risk_class.value,
            ",".join(files),
            ",".join(tests),
            ",".join(item.gate_name for item in gates),
        )
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"mhc-{digest}"


def report_from_candidate(candidate: MetaHarnessCandidate) -> MetaHarnessReport:
    if not isinstance(candidate, MetaHarnessCandidate):
        raise MetaHarnessContractError("candidate must be MetaHarnessCandidate")
    return MetaHarnessReport(
        candidate_id=candidate.candidate_id,
        kind=candidate.kind,
        status=candidate.status,
        active=candidate.active,
        target_failure_class=candidate.input_metadata.target_failure_class,
        source_ref_count=len(candidate.input_metadata.source_refs),
        artifact_count=len(candidate.input_metadata.artifact_ids),
        candidate_file_count=len(candidate.candidate_files),
        test_count=len(candidate.test_names),
        gate_count=len(candidate.gate_requirements),
        risk_class=candidate.risk_class,
        candidate_summary=candidate.candidate_summary,
    )


def _reject_forbidden_meta_text(name: str, value: str) -> None:
    if _FORBIDDEN_TEXT_RE.search(value):
        raise UnsafeMetaHarnessPayloadError(
            f"{name} contains a Stage 12 forbidden raw/private/backend marker"
        )


__all__ = [
    "META_HARNESS_SCHEMA_VERSION",
    "MetaHarnessContractError",
    "UnsafeMetaHarnessPayloadError",
    "MetaHarnessAuthority",
    "MetaHarnessCandidateKind",
    "MetaHarnessRiskClass",
    "MetaHarnessCandidateStatus",
    "MetaHarnessGateRequirement",
    "MetaHarnessInput",
    "MetaHarnessPatchIntent",
    "MetaHarnessEvalPlan",
    "MetaHarnessPlan",
    "MetaHarnessCandidate",
    "MetaHarnessReport",
    "validate_safe_token",
    "validate_safe_code",
    "validate_sanitized_meta_text",
    "validate_nonnegative_int",
    "validate_safe_token_tuple",
    "validate_safe_code_tuple",
    "validate_candidate_files",
    "validate_gate_requirements",
    "derive_meta_harness_candidate_id",
    "report_from_candidate",
]
