from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

LEARNING_SCHEMA_VERSION = "m27-autonomous-learning-proposal/v1"

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:#-]{1,256}$")
_SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_PROPOSAL_ID_RE = re.compile(r"^learn-[0-9a-f]{32}$")
_SIGNAL_ID_RE = re.compile(r"^lsig-[0-9a-f]{32}$")
_MAX_SUMMARY_CHARS = 2048
_MAX_SIGNAL_IDS = 256
_MAX_REASON_CODES = 64
_MAX_ARTIFACT_IDS = 64

_FORBIDDEN_TEXT_RE = re.compile(
    r"(?i)(?:"
    r"raw[_ -]?query|raw[_ -]?answer|"
    r"full[_ -]?evidence[_ -]?(?:body|text)|"
    r"full[_ -]?source[_ -]?(?:body|text)|"
    r"provider[_ -]?prompt|"
    r"credentials?|secrets?|api[_ -]?key|auth[_ -]?token|access[_ -]?token|"
    r"\benv\b|\benvironment\b|"
    r"\bqdrant\b|\br2://|\bsqlite\b|\bpostgres\b|\bmysql\b|\bs3://|"
    r"/home/ubuntu/|(?:^|[\s/])\.\./|"
    r"production[_ -]?path|release[_ -]?pointer"
    r")"
)


class LearningContractError(ValueError):
    """Base error for Stage 11 proposal-plane contract violations."""


class UnsafeLearningPayloadError(LearningContractError):
    """Raised when learning material is not demonstrably sanitized."""


class LearningAuthority(StrEnum):
    PROPOSAL_ONLY = "PROPOSAL_ONLY"


class LearningSignalKind(StrEnum):
    TRACE_OBSERVATION = "TRACE_OBSERVATION"
    BUDGET_OBSERVATION = "BUDGET_OBSERVATION"
    HEALTH_OBSERVATION = "HEALTH_OBSERVATION"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    VERIFICATION_OUTCOME = "VERIFICATION_OUTCOME"
    MEMORY_CANDIDATE_METADATA = "MEMORY_CANDIDATE_METADATA"
    EVAL_SUMMARY = "EVAL_SUMMARY"
    GATE_SUMMARY = "GATE_SUMMARY"
    LATENCY_CLASS_SUMMARY = "LATENCY_CLASS_SUMMARY"
    FAILURE_CLASS_SUMMARY = "FAILURE_CLASS_SUMMARY"


class LearningSignalSource(StrEnum):
    DECISION_TRACE = "DECISION_TRACE"
    RUNTIME_TRACE = "RUNTIME_TRACE"
    RUNTIME_BUDGET = "RUNTIME_BUDGET"
    RUNTIME_HEALTH = "RUNTIME_HEALTH"
    EVIDENCE_INSPECT = "EVIDENCE_INSPECT"
    EVIDENCE_VERIFY = "EVIDENCE_VERIFY"
    MEMORY_CANDIDATE_METADATA = "MEMORY_CANDIDATE_METADATA"
    EVAL_SUMMARY = "EVAL_SUMMARY"
    GATE_SUMMARY = "GATE_SUMMARY"
    LATENCY_CLASS_SUMMARY = "LATENCY_CLASS_SUMMARY"
    FAILURE_CLASS_SUMMARY = "FAILURE_CLASS_SUMMARY"


class LearningPolicyArea(StrEnum):
    SKILL = "SKILL"
    RETRIEVAL = "RETRIEVAL"
    COMPUTE = "COMPUTE"
    ROUTING = "ROUTING"
    MEMORY = "MEMORY"
    EVAL_GATE = "EVAL_GATE"
    GUARDRAIL = "GUARDRAIL"


class LearningProposalKind(StrEnum):
    SKILL_POLICY_CANDIDATE = "SKILL_POLICY_CANDIDATE"
    RETRIEVAL_POLICY_CANDIDATE = "RETRIEVAL_POLICY_CANDIDATE"
    COMPUTE_POLICY_CANDIDATE = "COMPUTE_POLICY_CANDIDATE"
    ROUTING_POLICY_CANDIDATE = "ROUTING_POLICY_CANDIDATE"
    MEMORY_POLICY_CANDIDATE = "MEMORY_POLICY_CANDIDATE"
    EVAL_GATE_CANDIDATE = "EVAL_GATE_CANDIDATE"
    GUARDRAIL_HARDENING_CANDIDATE = "GUARDRAIL_HARDENING_CANDIDATE"


class LearningProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class LearningRiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class LearningDecision(StrEnum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REJECT = "REJECT"
    SUPERSEDE = "SUPERSEDE"


_PROPOSAL_POLICY_AREA = {
    LearningProposalKind.SKILL_POLICY_CANDIDATE: LearningPolicyArea.SKILL,
    LearningProposalKind.RETRIEVAL_POLICY_CANDIDATE: LearningPolicyArea.RETRIEVAL,
    LearningProposalKind.COMPUTE_POLICY_CANDIDATE: LearningPolicyArea.COMPUTE,
    LearningProposalKind.ROUTING_POLICY_CANDIDATE: LearningPolicyArea.ROUTING,
    LearningProposalKind.MEMORY_POLICY_CANDIDATE: LearningPolicyArea.MEMORY,
    LearningProposalKind.EVAL_GATE_CANDIDATE: LearningPolicyArea.EVAL_GATE,
    LearningProposalKind.GUARDRAIL_HARDENING_CANDIDATE: LearningPolicyArea.GUARDRAIL,
}


@dataclass(frozen=True, slots=True)
class LearningSignal:
    signal_id: str
    kind: LearningSignalKind
    source: LearningSignalSource
    source_ref: str
    policy_area: LearningPolicyArea
    classification: str
    count: int = 1
    reason_codes: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, str) or not _SIGNAL_ID_RE.fullmatch(
            self.signal_id
        ):
            raise LearningContractError(
                "signal_id must be generated as lsig-<32 lowercase hex>"
            )
        if not isinstance(self.kind, LearningSignalKind):
            raise LearningContractError("kind must be LearningSignalKind")
        if not isinstance(self.source, LearningSignalSource):
            raise LearningContractError("source must be LearningSignalSource")
        if not isinstance(self.policy_area, LearningPolicyArea):
            raise LearningContractError("policy_area must be LearningPolicyArea")
        validate_safe_token("source_ref", self.source_ref)
        validate_safe_code("classification", self.classification)
        validate_nonnegative_int("count", self.count)
        normalized_reasons = validate_reason_codes(self.reason_codes)
        normalized_artifacts = validate_artifact_ids(self.artifact_ids)
        if normalized_reasons != self.reason_codes:
            raise LearningContractError("reason_codes must already be canonical")
        if normalized_artifacts != self.artifact_ids:
            raise LearningContractError("artifact_ids must already be canonical")
        expected = derive_learning_signal_id(
            kind=self.kind,
            source=self.source,
            source_ref=self.source_ref,
            policy_area=self.policy_area,
            classification=self.classification,
            count=self.count,
            reason_codes=self.reason_codes,
            artifact_ids=self.artifact_ids,
        )
        if expected != self.signal_id:
            raise LearningContractError(
                "signal_id does not match canonical sanitized signal content"
            )

    @classmethod
    def create(
        cls,
        *,
        kind: LearningSignalKind,
        source: LearningSignalSource,
        source_ref: str,
        policy_area: LearningPolicyArea,
        classification: str,
        count: int = 1,
        reason_codes: tuple[str, ...] = (),
        artifact_ids: tuple[str, ...] = (),
    ) -> LearningSignal:
        validate_safe_token("source_ref", source_ref)
        validate_safe_code("classification", classification)
        validate_nonnegative_int("count", count)
        normalized_reasons = validate_reason_codes(reason_codes)
        normalized_artifacts = validate_artifact_ids(artifact_ids)
        signal_id = derive_learning_signal_id(
            kind=kind,
            source=source,
            source_ref=source_ref,
            policy_area=policy_area,
            classification=classification,
            count=count,
            reason_codes=normalized_reasons,
            artifact_ids=normalized_artifacts,
        )
        return cls(
            signal_id=signal_id,
            kind=kind,
            source=source,
            source_ref=source_ref,
            policy_area=policy_area,
            classification=classification,
            count=count,
            reason_codes=normalized_reasons,
            artifact_ids=normalized_artifacts,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": LEARNING_SCHEMA_VERSION,
            "signal_id": self.signal_id,
            "kind": self.kind.value,
            "source": self.source.value,
            "source_ref": self.source_ref,
            "policy_area": self.policy_area.value,
            "classification": self.classification,
            "count": self.count,
            "reason_codes": list(self.reason_codes),
            "artifact_ids": list(self.artifact_ids),
        }


@dataclass(frozen=True, slots=True)
class LearningEvidenceBinding:
    signal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.signal_ids, tuple) or not self.signal_ids:
            raise LearningContractError("evidence binding requires at least one signal_id")
        if len(self.signal_ids) > _MAX_SIGNAL_IDS:
            raise LearningContractError("too many signal_ids in proposal evidence binding")
        for signal_id in self.signal_ids:
            if not isinstance(signal_id, str) or not _SIGNAL_ID_RE.fullmatch(signal_id):
                raise LearningContractError("evidence binding contains invalid signal_id")
        if tuple(sorted(set(self.signal_ids))) != self.signal_ids:
            raise LearningContractError(
                "signal_ids must be unique and deterministically sorted"
            )

    def as_dict(self) -> dict[str, object]:
        return {"signal_ids": list(self.signal_ids)}


@dataclass(frozen=True, slots=True)
class LearningProposal:
    proposal_id: str
    kind: LearningProposalKind
    policy_area: LearningPolicyArea
    observed_issue_class: str
    evidence_binding: LearningEvidenceBinding
    candidate_change_summary: str
    expected_benefit_class: str
    risk_class: LearningRiskClass
    required_gate: str
    status: LearningProposalStatus = LearningProposalStatus.PROPOSED
    authority: LearningAuthority = LearningAuthority.PROPOSAL_ONLY
    proposal_only: bool = True
    requires_human_review: bool = True
    requires_offline_gate: bool = True
    auto_apply: bool = False
    production_write: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, str) or not _PROPOSAL_ID_RE.fullmatch(
            self.proposal_id
        ):
            raise LearningContractError(
                "proposal_id must be generated as learn-<32 lowercase hex>"
            )
        if not isinstance(self.kind, LearningProposalKind):
            raise LearningContractError("kind must be LearningProposalKind")
        if not isinstance(self.policy_area, LearningPolicyArea):
            raise LearningContractError("policy_area must be LearningPolicyArea")
        expected_area = policy_area_for_proposal_kind(self.kind)
        if self.policy_area is not expected_area:
            raise LearningContractError(
                "proposal kind must use its fixed Stage 11 policy area"
            )
        validate_safe_code("observed_issue_class", self.observed_issue_class)
        if not isinstance(self.evidence_binding, LearningEvidenceBinding):
            raise LearningContractError(
                "evidence_binding must be LearningEvidenceBinding"
            )
        validate_sanitized_learning_text(
            "candidate_change_summary", self.candidate_change_summary
        )
        validate_safe_code("expected_benefit_class", self.expected_benefit_class)
        if not isinstance(self.risk_class, LearningRiskClass):
            raise LearningContractError("risk_class must be LearningRiskClass")
        validate_safe_token("required_gate", self.required_gate)
        if not isinstance(self.status, LearningProposalStatus):
            raise LearningContractError("status must be LearningProposalStatus")
        if self.authority is not LearningAuthority.PROPOSAL_ONLY:
            raise LearningContractError("Stage 11 authority is proposal-only")
        for name, value in (
            ("proposal_only", self.proposal_only),
            ("requires_human_review", self.requires_human_review),
            ("requires_offline_gate", self.requires_offline_gate),
            ("auto_apply", self.auto_apply),
            ("production_write", self.production_write),
        ):
            if not isinstance(value, bool):
                raise LearningContractError(f"{name} must be bool")
        if self.proposal_only is not True:
            raise LearningContractError("Stage 11 proposals must remain proposal-only")
        if self.requires_human_review is not True:
            raise LearningContractError("Stage 11 proposals require human review")
        if self.requires_offline_gate is not True:
            raise LearningContractError("Stage 11 proposals require an offline gate")
        if self.auto_apply is not False:
            raise LearningContractError("Stage 11 proposals can never auto-apply")
        if self.production_write is not False:
            raise LearningContractError("Stage 11 proposals can never write production")

        expected = derive_learning_proposal_id(
            kind=self.kind,
            policy_area=self.policy_area,
            observed_issue_class=self.observed_issue_class,
            evidence_binding=self.evidence_binding,
            candidate_change_summary=self.candidate_change_summary,
            expected_benefit_class=self.expected_benefit_class,
            risk_class=self.risk_class,
            required_gate=self.required_gate,
        )
        if expected != self.proposal_id:
            raise LearningContractError(
                "proposal_id does not match canonical proposal content"
            )

    @classmethod
    def create(
        cls,
        *,
        kind: LearningProposalKind,
        observed_issue_class: str,
        evidence_binding: LearningEvidenceBinding,
        candidate_change_summary: str,
        expected_benefit_class: str,
        risk_class: LearningRiskClass,
        required_gate: str,
    ) -> LearningProposal:
        policy_area = policy_area_for_proposal_kind(kind)
        validate_safe_code("observed_issue_class", observed_issue_class)
        validate_sanitized_learning_text(
            "candidate_change_summary", candidate_change_summary
        )
        validate_safe_code("expected_benefit_class", expected_benefit_class)
        validate_safe_token("required_gate", required_gate)
        proposal_id = derive_learning_proposal_id(
            kind=kind,
            policy_area=policy_area,
            observed_issue_class=observed_issue_class,
            evidence_binding=evidence_binding,
            candidate_change_summary=candidate_change_summary,
            expected_benefit_class=expected_benefit_class,
            risk_class=risk_class,
            required_gate=required_gate,
        )
        return cls(
            proposal_id=proposal_id,
            kind=kind,
            policy_area=policy_area,
            observed_issue_class=observed_issue_class,
            evidence_binding=evidence_binding,
            candidate_change_summary=candidate_change_summary,
            expected_benefit_class=expected_benefit_class,
            risk_class=risk_class,
            required_gate=required_gate,
        )

    @property
    def active(self) -> bool:
        return self.status in {
            LearningProposalStatus.PROPOSED,
            LearningProposalStatus.READY_FOR_REVIEW,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": LEARNING_SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "kind": self.kind.value,
            "policy_area": self.policy_area.value,
            "observed_issue_class": self.observed_issue_class,
            "evidence_binding": self.evidence_binding.as_dict(),
            "candidate_change_summary": self.candidate_change_summary,
            "expected_benefit_class": self.expected_benefit_class,
            "risk_class": self.risk_class.value,
            "required_gate": self.required_gate,
            "status": self.status.value,
            "active": self.active,
            "authority": self.authority.value,
            "proposal_only": self.proposal_only,
            "requires_human_review": self.requires_human_review,
            "requires_offline_gate": self.requires_offline_gate,
            "auto_apply": self.auto_apply,
            "production_write": self.production_write,
        }


def policy_area_for_proposal_kind(
    kind: LearningProposalKind,
) -> LearningPolicyArea:
    if not isinstance(kind, LearningProposalKind):
        raise LearningContractError("kind must be LearningProposalKind")
    return _PROPOSAL_POLICY_AREA[kind]


def validate_safe_token(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN_RE.fullmatch(value):
        raise UnsafeLearningPayloadError(
            f"{name} must be a pre-sanitized opaque identifier"
        )
    _reject_forbidden_learning_text(name, value)
    return value


def validate_safe_code(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_CODE_RE.fullmatch(value):
        raise UnsafeLearningPayloadError(
            f"{name} must use bounded SAFE_UPPER_SNAKE_CASE"
        )
    _reject_forbidden_learning_text(name, value)
    return value


def validate_sanitized_learning_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise UnsafeLearningPayloadError(f"{name} must be non-empty text")
    if len(value) > _MAX_SUMMARY_CHARS:
        raise UnsafeLearningPayloadError(
            f"{name} exceeds Stage 11 bounded summary size"
        )
    if "\x00" in value:
        raise UnsafeLearningPayloadError(f"{name} cannot contain NUL")
    _reject_forbidden_learning_text(name, value)
    return value


def validate_nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LearningContractError(f"{name} must be a non-negative integer")
    return value


def validate_reason_codes(reason_codes: object) -> tuple[str, ...]:
    if not isinstance(reason_codes, tuple):
        raise LearningContractError("reason_codes must be a tuple")
    if len(reason_codes) > _MAX_REASON_CODES:
        raise LearningContractError("too many learning reason_codes")
    for code in reason_codes:
        validate_safe_code("reason_code", code)
    return tuple(sorted(set(reason_codes)))


def validate_artifact_ids(artifact_ids: object) -> tuple[str, ...]:
    if not isinstance(artifact_ids, tuple):
        raise LearningContractError("artifact_ids must be a tuple")
    if len(artifact_ids) > _MAX_ARTIFACT_IDS:
        raise LearningContractError("too many artifact_ids")
    for artifact_id in artifact_ids:
        validate_safe_token("artifact_id", artifact_id)
    return tuple(sorted(set(artifact_ids)))


def derive_learning_signal_id(
    *,
    kind: LearningSignalKind,
    source: LearningSignalSource,
    source_ref: str,
    policy_area: LearningPolicyArea,
    classification: str,
    count: int,
    reason_codes: tuple[str, ...],
    artifact_ids: tuple[str, ...],
) -> str:
    if not isinstance(kind, LearningSignalKind):
        raise LearningContractError("kind must be LearningSignalKind")
    if not isinstance(source, LearningSignalSource):
        raise LearningContractError("source must be LearningSignalSource")
    if not isinstance(policy_area, LearningPolicyArea):
        raise LearningContractError("policy_area must be LearningPolicyArea")
    validate_safe_token("source_ref", source_ref)
    validate_safe_code("classification", classification)
    validate_nonnegative_int("count", count)
    normalized_reasons = validate_reason_codes(reason_codes)
    normalized_artifacts = validate_artifact_ids(artifact_ids)
    canonical = "\x00".join(
        (
            LEARNING_SCHEMA_VERSION,
            kind.value,
            source.value,
            source_ref,
            policy_area.value,
            classification,
            str(count),
            ",".join(normalized_reasons),
            ",".join(normalized_artifacts),
        )
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"lsig-{digest}"


def derive_learning_proposal_id(
    *,
    kind: LearningProposalKind,
    policy_area: LearningPolicyArea,
    observed_issue_class: str,
    evidence_binding: LearningEvidenceBinding,
    candidate_change_summary: str,
    expected_benefit_class: str,
    risk_class: LearningRiskClass,
    required_gate: str,
) -> str:
    if not isinstance(kind, LearningProposalKind):
        raise LearningContractError("kind must be LearningProposalKind")
    if not isinstance(policy_area, LearningPolicyArea):
        raise LearningContractError("policy_area must be LearningPolicyArea")
    if not isinstance(evidence_binding, LearningEvidenceBinding):
        raise LearningContractError("evidence_binding must be LearningEvidenceBinding")
    if not isinstance(risk_class, LearningRiskClass):
        raise LearningContractError("risk_class must be LearningRiskClass")
    validate_safe_code("observed_issue_class", observed_issue_class)
    validate_sanitized_learning_text(
        "candidate_change_summary", candidate_change_summary
    )
    validate_safe_code("expected_benefit_class", expected_benefit_class)
    validate_safe_token("required_gate", required_gate)
    summary_sha256 = hashlib.sha256(
        candidate_change_summary.encode("utf-8")
    ).hexdigest()
    canonical = "\x00".join(
        (
            LEARNING_SCHEMA_VERSION,
            kind.value,
            policy_area.value,
            observed_issue_class,
            ",".join(evidence_binding.signal_ids),
            summary_sha256,
            expected_benefit_class,
            risk_class.value,
            required_gate,
        )
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"learn-{digest}"


def _reject_forbidden_learning_text(name: str, value: str) -> None:
    if _FORBIDDEN_TEXT_RE.search(value):
        raise UnsafeLearningPayloadError(
            f"{name} contains a Stage 11 forbidden raw/private/backend marker"
        )


__all__ = [
    "LEARNING_SCHEMA_VERSION",
    "LearningContractError",
    "UnsafeLearningPayloadError",
    "LearningAuthority",
    "LearningSignalKind",
    "LearningSignalSource",
    "LearningPolicyArea",
    "LearningProposalKind",
    "LearningProposalStatus",
    "LearningRiskClass",
    "LearningDecision",
    "LearningSignal",
    "LearningEvidenceBinding",
    "LearningProposal",
    "policy_area_for_proposal_kind",
    "validate_safe_token",
    "validate_safe_code",
    "validate_sanitized_learning_text",
    "validate_nonnegative_int",
    "validate_reason_codes",
    "validate_artifact_ids",
    "derive_learning_signal_id",
    "derive_learning_proposal_id",
]
