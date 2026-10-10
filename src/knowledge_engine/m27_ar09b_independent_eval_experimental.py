"""Bounded independent T0/T1 Task/Outcome evaluator, offline fixtures only.

Not an AR09/REL01 release oracle. The separate-observation input must be supplied
by a genuinely separate custodian in any future deployment. Python dataclass
fields, trusted strings and SHA-256 are NOT signatures, rights or real attestations.
No provider, tool, network, runtime, database, or production integration.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from typing import Literal

OutcomeType = Literal["ANSWER", "ARTIFACT", "ACTION", "ABSTAIN", "CANCELLED", "FAILED"]
Workload = Literal["QA", "RESEARCH", "CODING", "ACTION"]
Terminal = Literal["SUCCEEDED", "FAILED", "CANCELLED"]
SegmentKind = Literal["verified_claim", "progress", "terminal"]
HEX = frozenset("0123456789abcdef")
SUCCESS_TYPES = frozenset({"ANSWER", "ARTIFACT", "ACTION"})
TERMINALS = {
    "ANSWER": "SUCCEEDED",
    "ARTIFACT": "SUCCEEDED",
    "ACTION": "SUCCEEDED",
    "ABSTAIN": "SUCCEEDED",
    "CANCELLED": "CANCELLED",
    "FAILED": "FAILED",
}
SECURITY_REASONS = frozenset(
    {
        "IDENTITY_OR_HEAD_MISMATCH",
        "EVALUATOR_NOT_INDEPENDENT",
        "ORACLE_NOT_INDEPENDENT",
        "ORACLE_NOT_APPROVED",
        "RIGHTS_WITHHELD",
        "RIGHTS_NOT_INDEPENDENTLY_CHECKED",
        "UNKNOWN_EFFECT_UNRESOLVED",
        "DUPLICATE_FEE",
        "LATE_BILLING_UNRECONCILED",
        "UNASSIGNED_CASE",
        "DUPLICATE_CASE_ID",
    }
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_digest(value: str | None) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in HEX for character in value)
    )


@dataclass(frozen=True, slots=True)
class Charge:
    """An observed synthetic invoice entry; amount=None means unpriced."""

    attempt_id: str
    charge_id: str
    amount_microunits: int | None
    late: bool = False


@dataclass(frozen=True, slots=True)
class PreterminalSegment:
    """Transport-local client receipt (not server enqueue or event-name proof)."""

    kind: SegmentKind
    payload: bytes
    payload_sha256: str
    at_ms: int
    verified_by: str
    citation_ids: tuple[str, ...]
    client_received: bool


@dataclass(frozen=True, slots=True)
class OutcomeEvidence:
    """Executor-side candidate observation, never itself an oracle."""

    case_id: str
    workload: Workload
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    revision: int
    journal_head_seq: int
    journal_head_sha256: str
    outcome_type: OutcomeType
    terminal_status: Terminal
    terminal_durable: bool
    executor_id: str
    evaluator_id: str
    claimed_oracle_id: str | None
    observed_digest: str | None
    rights_granted: bool
    unknown_effect: bool
    started_ms: int
    terminal_ms: int
    segments: tuple[PreterminalSegment, ...]
    charges: tuple[Charge, ...]
    refused: bool = False
    action_resource_version: str | None = None
    duplicate_fee_detected: bool = False
    late_billing_reconciled: bool = True


@dataclass(frozen=True, slots=True)
class TrustedObservation:
    """Separate-input synthetic oracle catalog; NOT signed real-world authority.

    Never populate this from the executor's own labels or reported outcome.
    Future integration must independently authenticate the catalog and custodian.
    """

    case_id: str
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    revision: int
    journal_head_seq: int
    journal_head_sha256: str
    oracle_id: str
    oracle_available: bool
    offline_observer_separate: bool
    expected_outcome: OutcomeType
    expected_digest: str | None
    expected_refusal: bool | None
    verified_segment_sha256: frozenset[str]
    source_rights_checked: bool
    independently_observed_resource_version: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Immutable offline policy controlled separately from candidate receipts."""

    evaluator_id: str
    evaluator_version: str
    approved_oracle_ids: frozenset[str]
    assigned_case_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CaseDecision:
    case_id: str
    workload: str
    task_success: bool
    terminal_correct: bool | None
    denied: bool
    refusal_correct: bool | None
    evidence_valid: bool
    stream_ok: bool | None
    first_verified_text_ms: int | None
    latency_ms: int | None
    cost_microunits: int | None
    security_violation: bool
    reason: str
    quality_score: None = None
    quality_status: str = "BLOCKED_EXTERNAL_ORACLE"


@dataclass(frozen=True, slots=True)
class WorkloadStats:
    assigned: int
    successful: int
    terminal_correct: int
    refused: int
    unknown_or_invalid: int


@dataclass(frozen=True, slots=True)
class BatchMetrics:
    tier: str
    success_numerator: int
    success_denominator: int
    success_rate: float | None
    refusal_correct: int
    refusal_known: int
    refusal_accuracy: float | None
    evidence_invalidity_count: int
    security_violations: int
    unknown_effect_count: int
    latency_ms_p50: int | None
    latency_ms_p95: int | None
    latency_ms_p99: int | None
    first_verified_text_ms_p50: int | None
    latency_buckets: dict[str, int]
    total_cost_microunits: int | None
    cost_per_success_microunits: float | None
    cost_per_attempt_microunits: float | None
    by_workload: dict[str, WorkloadStats]
    cases: tuple[CaseDecision, ...]
    quality_status: str = "BLOCKED_EXTERNAL_ORACLE"


def nearest_rank(values: tuple[int, ...], percentile: float) -> int | None:
    """Predeclared nearest-rank percentile, ceil(p*n) - 1, no interpolation."""

    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    if not values:
        return None
    return sorted(values)[math.ceil(percentile * len(values)) - 1]


def _valid_measurements(e: OutcomeEvidence) -> bool:
    return (
        type(e.started_ms) is int
        and type(e.terminal_ms) is int
        and 0 <= e.started_ms <= e.terminal_ms
        and all(
            charge.attempt_id
            and charge.charge_id
            and (
                charge.amount_microunits is None
                or (
                    type(charge.amount_microunits) is int
                    and charge.amount_microunits >= 0
                )
            )
            for charge in e.charges
        )
    )


def _cost(e: OutcomeEvidence) -> int | None:
    if not _valid_measurements(e):
        return None
    if any(charge.amount_microunits is None for charge in e.charges):
        return None
    return sum(
        charge.amount_microunits
        for charge in e.charges
        if charge.amount_microunits is not None
    )


def _substantive_utf8(payload: bytes) -> bool:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return any(char.isalnum() for char in text)


def _first_verified_text(
    e: OutcomeEvidence, o: TrustedObservation
) -> int | None:
    """Do not mistake progress/server writes/terminal-only for delivered claims."""

    candidates: list[int] = []
    for part in e.segments:
        if (
            part.kind == "verified_claim"
            and isinstance(part.payload, bytes)
            and _substantive_utf8(part.payload)
            and _valid_digest(part.payload_sha256)
            and _digest(part.payload) == part.payload_sha256
            and part.payload_sha256 in o.verified_segment_sha256
            and part.verified_by == o.oracle_id
            and part.verified_by != e.executor_id
            and bool(part.citation_ids)
            and all(isinstance(cite, str) and cite for cite in part.citation_ids)
            and part.client_received is True
            and type(part.at_ms) is int
            and e.started_ms <= part.at_ms < e.terminal_ms
        ):
            candidates.append(part.at_ms - e.started_ms)
    return min(candidates) if candidates else None


def _identity(e: OutcomeEvidence) -> tuple[object, ...]:
    return (
        e.case_id, e.tenant_id, e.task_id, e.task_version, e.run_id,
        e.revision, e.journal_head_seq, e.journal_head_sha256,
    )


def _oracle_identity(o: TrustedObservation) -> tuple[object, ...]:
    return (
        o.case_id, o.tenant_id, o.task_id, o.task_version, o.run_id,
        o.revision, o.journal_head_seq, o.journal_head_sha256,
    )


def evaluate_case(
    evidence: OutcomeEvidence,
    observation: TrustedObservation | None,
    context: EvaluationContext,
) -> CaseDecision:
    """Independently compare candidate with separate *synthetic* T0/T1 evidence.

    A 'task_success' is only OFFLINE_FIXTURE success. Never promote to real task
    success, real signatures, owner qualification, or external quality score.
    """

    e, o = evidence, observation
    cost = _cost(e)
    latency = (
        e.terminal_ms - e.started_ms
        if _valid_measurements(e) else None
    )
    denied = e.refused is True
    # Refusal labels from unavailable/forged/unbound oracles are NOT ground truth.
    refusal_correct: bool | None = None
    terminal_correct: bool | None = None
    first_text = None
    stream_ok: bool | None = None

    def finish(reason: str, *, passed: bool = False) -> CaseDecision:
        return CaseDecision(
            case_id=e.case_id,
            workload=e.workload,
            task_success=passed,
            terminal_correct=terminal_correct,
            denied=denied,
            refusal_correct=refusal_correct,
            evidence_valid=passed or reason == "NON_SUCCESS_TERMINAL",
            stream_ok=stream_ok,
            first_verified_text_ms=first_text,
            latency_ms=latency,
            cost_microunits=cost,
            security_violation=reason in SECURITY_REASONS,
            reason=reason,
        )

    if not _valid_measurements(e):
        return finish("INVALID_MEASUREMENT")
    if context.assigned_case_ids and e.case_id not in context.assigned_case_ids:
        return finish("UNASSIGNED_CASE")
    if e.evaluator_id != context.evaluator_id or e.evaluator_id == e.executor_id:
        return finish("EVALUATOR_NOT_INDEPENDENT")
    if o is None or not o.oracle_available:
        return finish("ORACLE_UNAVAILABLE")
    if o.oracle_id not in context.approved_oracle_ids:
        return finish("ORACLE_NOT_APPROVED")
    if (
        e.claimed_oracle_id == e.executor_id
        or e.claimed_oracle_id != o.oracle_id
        or o.oracle_id == e.executor_id
    ):
        return finish("ORACLE_NOT_INDEPENDENT")
    if not o.offline_observer_separate:
        return finish("ORACLE_NOT_INDEPENDENT")
    if (
        _identity(e) != _oracle_identity(o)
        or not _valid_digest(e.journal_head_sha256)
        or type(e.task_version) is not int
        or type(e.revision) is not int
        or type(e.journal_head_seq) is not int
        or e.task_version < 0
        or e.revision < 0
        or e.journal_head_seq < 0
    ):
        return finish("IDENTITY_OR_HEAD_MISMATCH")
    if o.expected_refusal is not None:
        refusal_correct = denied == o.expected_refusal
    if not e.rights_granted:
        return finish("RIGHTS_WITHHELD")
    if not o.source_rights_checked:
        return finish("RIGHTS_NOT_INDEPENDENTLY_CHECKED")
    if e.unknown_effect:
        return finish("UNKNOWN_EFFECT_UNRESOLVED")
    ids = [charge.charge_id for charge in e.charges]
    if e.duplicate_fee_detected or len(ids) != len(set(ids)):
        return finish("DUPLICATE_FEE")
    if not e.late_billing_reconciled and any(c.late for c in e.charges):
        return finish("LATE_BILLING_UNRECONCILED")

    terminal_correct = (
        e.outcome_type == o.expected_outcome
        and e.terminal_status == TERMINALS.get(e.outcome_type)
        and e.terminal_durable is True
    )
    if not e.terminal_durable:
        return finish("TERMINAL_NOT_DURABLE")
    if not terminal_correct:
        return finish("TERMINAL_OUTCOME_MISMATCH")
    if e.outcome_type not in SUCCESS_TYPES:
        return finish("NON_SUCCESS_TERMINAL")
    if (
        not _valid_digest(o.expected_digest)
        or not _valid_digest(e.observed_digest)
    ):
        return finish("OUTCOME_PROOF_MISSING")
    if e.observed_digest != o.expected_digest:
        return finish("OUTCOME_DIGEST_MISMATCH")
    if e.outcome_type == "ACTION" and (
        not e.action_resource_version
        or not o.independently_observed_resource_version
        or e.action_resource_version != o.independently_observed_resource_version
    ):
        return finish("REMOTE_STATE_PROOF_MISSING_OR_MISMATCH")
    if e.outcome_type == "ANSWER":
        first_text = _first_verified_text(e, o)
        stream_ok = first_text is not None
        if not stream_ok:
            return finish("NO_VERIFIED_PRETERMINAL_TEXT")
    return finish("ACCEPTED_OFFLINE_FIXTURE_ONLY", passed=True)


def _charge_duplicates(entries: tuple[OutcomeEvidence, ...]) -> set[str]:
    """Detect charge identifier overlap between case IDs, including retries."""

    used: dict[str, set[str]] = {}
    for entry in entries:
        for charge in entry.charges:
            used.setdefault(charge.charge_id, set()).add(entry.case_id)
    return {case for cases in used.values() if len(cases) > 1 for case in cases}


def evaluate_batch(
    entries: tuple[OutcomeEvidence, ...],
    observations: dict[str, TrustedObservation],
    context: EvaluationContext,
) -> BatchMetrics:
    """No denominator cherry-picking: unknown, cancelled, unobserved are assigned."""

    duplicates = _charge_duplicates(entries)
    duplicate_cases = {
        entry.case_id for entry in entries
        if sum(other.case_id == entry.case_id for other in entries) > 1
    }
    cases = []
    for entry in entries:
        decision = evaluate_case(entry, observations.get(entry.case_id), context)
        if entry.case_id in duplicates or entry.case_id in duplicate_cases:
            code = "DUPLICATE_CASE_ID" if entry.case_id in duplicate_cases else "DUPLICATE_FEE"
            decision = replace(
                decision,
                task_success=False,
                evidence_valid=False,
                security_violation=True,
                reason=code,
            )
        cases.append(decision)

    grouped: dict[str, WorkloadStats] = {}
    for decision in cases:
        old = grouped.get(decision.workload, WorkloadStats(0, 0, 0, 0, 0))
        grouped[decision.workload] = WorkloadStats(
            assigned=old.assigned + 1,
            successful=old.successful + int(decision.task_success),
            terminal_correct=old.terminal_correct + int(decision.terminal_correct is True),
            refused=old.refused + int(decision.denied),
            unknown_or_invalid=old.unknown_or_invalid + int(not decision.evidence_valid),
        )
    missing_ids = context.assigned_case_ids - {e.case_id for e in entries}
    if missing_ids:
        old = grouped.get("UNREPORTED", WorkloadStats(0, 0, 0, 0, 0))
        grouped["UNREPORTED"] = replace(
            old, assigned=old.assigned + len(missing_ids),
            unknown_or_invalid=old.unknown_or_invalid + len(missing_ids),
        )

    denom = len(entries) + len(missing_ids)
    accepted = sum(d.task_success for d in cases)
    known = sum(d.refusal_correct is not None for d in cases)
    correct = sum(d.refusal_correct is True for d in cases)
    latency = tuple(d.latency_ms for d in cases if d.latency_ms is not None)
    ttft = tuple(
        d.first_verified_text_ms for d in cases if d.first_verified_text_ms is not None
    )
    buckets = {
        "lt_1000": sum(value < 1000 for value in latency),
        "1000_4999": sum(1000 <= value < 5000 for value in latency),
        "5000_14999": sum(5000 <= value < 15000 for value in latency),
        "gte_15000": sum(value >= 15000 for value in latency),
    }
    known_spend = all(case.cost_microunits is not None for case in cases)
    total = (
        sum(case.cost_microunits for case in cases if case.cost_microunits is not None)
        if known_spend and not missing_ids else None
    )
    return BatchMetrics(
        tier="T0_T1_SYNTHETIC_ONLY",
        success_numerator=accepted,
        success_denominator=denom,
        success_rate=accepted / denom if denom else None,
        refusal_correct=correct,
        refusal_known=known,
        refusal_accuracy=correct / known if known else None,
        evidence_invalidity_count=sum(not d.evidence_valid for d in cases) + len(missing_ids),
        security_violations=sum(d.security_violation for d in cases),
        unknown_effect_count=sum(e.unknown_effect for e in entries),
        latency_ms_p50=nearest_rank(latency, .5),
        latency_ms_p95=nearest_rank(latency, .95),
        latency_ms_p99=nearest_rank(latency, .99),
        first_verified_text_ms_p50=nearest_rank(ttft, .5),
        latency_buckets=buckets,
        total_cost_microunits=total,
        cost_per_success_microunits=total / accepted if total is not None and accepted else None,
        cost_per_attempt_microunits=total / denom if total is not None and denom else None,
        by_workload=grouped,
        cases=tuple(cases),
    )
