"""G05 isolated AR07 cost-policy accounting and AR10 governed candidate lifecycle.

Never connects to an external provider or Product. Unknown tariff/invoice stays unknown.
A fixture or pre-production evaluator is never an independently signed issuer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from threading import RLock
from typing import Literal

from .m27_b3_provider_router import FALLBACK, PRIMARY, RETRYABLE, Failure

ABI = "m27.g05.governed-cost-learning/v1"
_SUPPORTED_MODES = frozenset({"OFF", "BYPASS", "REFRESH", "AUTO"})


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _positive_decimal(value: str, *, allow_zero: bool = False) -> Decimal:
    try:
        n = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError("INVALID_MONETARY_VALUE") from None
    if not n.is_finite() or (n < 0 if allow_zero else n <= 0):
        raise ValueError("INVALID_MONETARY_VALUE")
    return n


def _digest(s: str) -> None:
    if not isinstance(s, str) or len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError("UNVERIFIED_OR_UNSAFE_DIGEST")


def _identity(s: str) -> None:
    if not isinstance(s, str) or not s or len(s) > 256 or any(c in s for c in "\r\n\0"):
        raise ValueError("INVALID_IDENTITY")


@dataclass(frozen=True)
class BudgetScope:
    task_sha256: str
    tenant: str
    principal: str
    source_sha256: str
    acl_epoch: str
    max_total_tokens: int
    max_attempts: int
    max_wall_ms: int
    max_reserved_usd: str
    fallback_consented: bool = False

    def __post_init__(self) -> None:
        for field_name in ("task_sha256", "tenant", "principal", "source_sha256", "acl_epoch"):
            _identity(getattr(self, field_name))
        if (
            not 1 <= self.max_total_tokens <= 100_000
            or not 1 <= self.max_attempts <= 4
            or not 1 <= self.max_wall_ms <= 120_000
        ):
            raise ValueError("UNBOUNDED_POLICY")
        _positive_decimal(self.max_reserved_usd)


@dataclass(frozen=True)
class Tariff:
    provider: str
    model_id: str
    version: str
    source_timestamp: str
    input_per_million_usd: str
    output_per_million_usd: str
    independently_verified: bool
    evidence_sha256: str

    def __post_init__(self) -> None:
        for v in (
            self.provider,
            self.model_id,
            self.version,
            self.source_timestamp,
            self.evidence_sha256,
        ):
            _identity(v)
        if self.provider not in (PRIMARY, FALLBACK):
            raise ValueError("UNKNOWN_PROVIDER")
        _positive_decimal(self.input_per_million_usd, allow_zero=True)
        _positive_decimal(self.output_per_million_usd, allow_zero=True)
        if self.independently_verified and (
            len(self.evidence_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.evidence_sha256)
        ):
            raise ValueError("UNVERIFIABLE_TARIFF")

    def quote(self, input_tokens: int, output_tokens: int) -> Decimal:
        if (
            type(input_tokens) is not int
            or type(output_tokens) is not int
            or input_tokens < 0
            or output_tokens < 0
        ):
            raise ValueError("INVALID_TOKEN_QUOTE")
        if not self.independently_verified:
            raise ValueError("UNVERIFIED_TARIFF")
        return (
            _positive_decimal(self.input_per_million_usd, allow_zero=True) * input_tokens
            + _positive_decimal(self.output_per_million_usd, allow_zero=True) * output_tokens
        ) / 1_000_000


@dataclass(frozen=True)
class MeterObservation:
    request_id: str
    task_sha256: str
    tenant: str
    principal: str
    provider: str
    model_id: str
    attempt: int
    timestamp: str
    source_revision: str
    origin: Literal["PROVIDER_RESPONSE", "FIXTURE", "INVOICE"]
    input_tokens: int | None
    output_tokens: int | None
    billed_usd: str | None
    invoice_verified: bool
    receipt_sha256: str
    first_text_ns: int | None = None
    terminal_ns: int | None = None
    request_start_ns: int | None = None

    def __post_init__(self) -> None:
        for v in (
            self.request_id,
            self.task_sha256,
            self.tenant,
            self.principal,
            self.provider,
            self.model_id,
            self.timestamp,
            self.source_revision,
            self.receipt_sha256,
        ):
            _identity(v)
        if self.provider not in (PRIMARY, FALLBACK) or self.attempt < 1:
            raise ValueError("INVALID_PROVIDER_ATTEMPT")
        for t in (self.input_tokens, self.output_tokens):
            if t is not None and (isinstance(t, bool) or not isinstance(t, int) or t < 0):
                raise ValueError("INVALID_TOKEN_USAGE")
        for t in (self.request_start_ns, self.first_text_ns, self.terminal_ns):
            if t is not None and (isinstance(t, bool) or not isinstance(t, int) or t < 0):
                raise ValueError("INVALID_LATENCY")
        if (
            self.first_text_ns is not None
            and self.terminal_ns is not None
            and self.first_text_ns > self.terminal_ns
        ):
            raise ValueError("INVALID_STREAM_CHRONOLOGY")
        if self.billed_usd is not None:
            _positive_decimal(self.billed_usd, allow_zero=True)
        if self.request_start_ns is not None:
            if self.first_text_ns is not None and self.request_start_ns > self.first_text_ns:
                raise ValueError("INVALID_REQUEST_FIRST_TEXT_ORDER")
            if self.terminal_ns is not None and self.request_start_ns > self.terminal_ns:
                raise ValueError("INVALID_REQUEST_TERMINAL_ORDER")
        _digest(self.receipt_sha256)
        if self.invoice_verified and (self.origin != "INVOICE" or self.billed_usd is None):
            raise ValueError("INVOICE_NOT_AUTHENTICATED")

    @property
    def actual_bill_usd(self) -> Decimal | None:
        if not self.invoice_verified or self.origin != "INVOICE":
            return None
        return _positive_decimal(self.billed_usd, allow_zero=True)

    @property
    def first_text_latency_ms(self) -> float | None:
        if self.request_start_ns is None or self.first_text_ns is None:
            return None
        return (self.first_text_ns - self.request_start_ns) / 1_000_000

    @property
    def request_latency_ms(self) -> float | None:
        if self.request_start_ns is None or self.terminal_ns is None:
            return None
        return (self.terminal_ns - self.request_start_ns) / 1_000_000

    @property
    def latency_ms(self) -> float | None:
        if self.first_text_ns is None or self.terminal_ns is None:
            return None
        return (self.terminal_ns - self.first_text_ns) / 1_000_000


@dataclass(frozen=True)
class Reservation:
    key: str
    provider: str
    model_id: str
    quoted_usd: Decimal
    reserved_tokens: int


class CostGovernor:
    """Thread-safe bounded local ledger. Reservation is a pre-dispatch fence, not billing."""

    def __init__(self, scope: BudgetScope) -> None:
        self.scope = scope
        self.lock = RLock()
        self.reservations: dict[str, Reservation] = {}
        self.observations: dict[str, MeterObservation] = {}
        self.circuit_open: set[str] = set()
        self.unreconciled_invoice_overrun = False
        self.primary_failure_receipts: dict[str, Failure] = {}
        self.fallback_failure_receipt_consumed = False

    def reserve(
        self,
        *,
        key: str,
        provider: str,
        model_id: str,
        tariff: Tariff | None,
        input_tokens: int,
        output_tokens: int,
        task_sha256: str,
        tenant: str,
        principal: str,
        source_sha256: str,
        acl_epoch: str,
        elapsed_ms: int,
        fallback_reason: Failure | None = None,
    ) -> Reservation:
        with self.lock:
            _identity(key)
            if key in self.reservations or key in self.observations:
                raise ValueError("REPLAYED_ATTEMPT")
            if self.unreconciled_invoice_overrun:
                raise PermissionError("UNRECONCILED_INVOICE_OVERSPEND")
            if (task_sha256, tenant, principal, source_sha256, acl_epoch) != (
                self.scope.task_sha256,
                self.scope.tenant,
                self.scope.principal,
                self.scope.source_sha256,
                self.scope.acl_epoch,
            ):
                raise PermissionError("SCOPE_ACL_OR_SOURCE_CHANGED")
            if provider not in (PRIMARY, FALLBACK):
                raise ValueError("INVALID_PROVIDER")
            if provider in self.circuit_open:
                raise PermissionError("CIRCUIT_OPEN")
            if provider == FALLBACK and (
                not self.scope.fallback_consented
                or fallback_reason is None
                or fallback_reason not in RETRYABLE
                or fallback_reason not in self.primary_failure_receipts.values()
                or self.fallback_failure_receipt_consumed
            ):
                raise PermissionError("ILLEGAL_FALLBACK")
            if (
                type(input_tokens) is not int
                or type(output_tokens) is not int
                or input_tokens < 0
                or output_tokens < 1
                or type(elapsed_ms) is not int
                or elapsed_ms < 0
            ):
                raise ValueError("INVALID_BUDGET_INPUT")
            if tariff is None or tariff.provider != provider or tariff.model_id != model_id:
                raise PermissionError("TARIFF_UNKNOWN_OR_MISMATCH")
            cost = tariff.quote(input_tokens, output_tokens)
            total_tokens = sum(x.reserved_tokens for x in self.reservations.values())
            total_cost = sum((x.quoted_usd for x in self.reservations.values()), Decimal(0))
            if (
                len(self.reservations) >= self.scope.max_attempts
                or total_tokens + input_tokens + output_tokens > self.scope.max_total_tokens
                or total_cost + cost > Decimal(self.scope.max_reserved_usd)
                or elapsed_ms >= self.scope.max_wall_ms
            ):
                raise PermissionError("QUOTA_OR_TOKEN_OR_DEADLINE_EXCEEDED")
            res = Reservation(key, provider, model_id, cost, input_tokens + output_tokens)
            self.reservations[key] = res
            if provider == FALLBACK:
                self.fallback_failure_receipt_consumed = True
            return res

    def register_primary_operational_failure(
        self,
        *,
        reservation_key: str,
        reason: Failure,
        answer_text_emitted: bool,
    ) -> None:
        """Source-side call only, after verified PRIMARY failure, never on partial text.

        This checks local lifecycle integrity but is not an external signed transport proof.
        """
        with self.lock:
            attempt = self.reservations.get(reservation_key)
            if (
                attempt is None
                or attempt.provider != PRIMARY
                or reservation_key in self.primary_failure_receipts
                or type(answer_text_emitted) is not bool
                or answer_text_emitted
                or reason not in RETRYABLE
            ):
                raise PermissionError("PRIMARY_FAILURE_PROOF_NOT_ELIGIBLE")
            self.primary_failure_receipts[reservation_key] = reason

    def record(self, key: str, observation: MeterObservation) -> None:
        with self.lock:
            reserved = self.reservations.get(key)
            if not reserved or key in self.observations:
                raise ValueError("MISSING_RESERVATION_OR_REPLAY")
            if (
                reserved.provider != observation.provider
                or reserved.model_id != observation.model_id
                or observation.source_revision != self.scope.source_sha256
                or observation.task_sha256 != self.scope.task_sha256
                or observation.tenant != self.scope.tenant
                or observation.principal != self.scope.principal
            ):
                raise PermissionError("CROSS_SCOPE_OR_PROVIDER_METER")
            self.observations[key] = observation
            reported_tokens = (
                observation.input_tokens + observation.output_tokens
                if observation.input_tokens is not None and observation.output_tokens is not None
                else None
            )
            if reported_tokens is not None and reported_tokens > reserved.reserved_tokens:
                self.unreconciled_invoice_overrun = True
            if observation.actual_bill_usd is not None and (
                observation.actual_bill_usd > reserved.quoted_usd
            ):
                self.unreconciled_invoice_overrun = True

    def trip_circuit(self, provider: str, fault: Failure) -> None:
        if provider not in (PRIMARY, FALLBACK) or fault not in RETRYABLE:
            raise ValueError("INELIGIBLE_CIRCUIT_TRIP")
        with self.lock:
            self.circuit_open.add(provider)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            bills = [o.actual_bill_usd for o in self.observations.values()]
            return {
                "abi": ABI,
                "attempts_reserved": len(self.reservations),
                "tokens_reserved": sum(x.reserved_tokens for x in self.reservations.values()),
                "quoted_usd": str(
                    sum((x.quoted_usd for x in self.reservations.values()), Decimal(0))
                ),
                "actual_bill_usd": str(sum(bills, Decimal(0)))
                if bills
                and all(b is not None for b in bills)
                and len(bills) == len(self.reservations)
                else None,
                "unknown_bill_count": len(self.reservations) - sum(x is not None for x in bills),
                "reserved_quote_by_provider_usd": {
                    p: str(
                        sum(
                            (x.quoted_usd for x in self.reservations.values() if x.provider == p),
                            Decimal(0),
                        )
                    )
                    for p in (PRIMARY, FALLBACK)
                },
                "invoice_overrun_hold": self.unreconciled_invoice_overrun,
                "fixture_not_bill": True,
            }


def cost_ablation(samples: dict[str, list[MeterObservation]]) -> dict[str, object]:
    """Only identical, independently billed complete workloads may support comparisons."""
    if set(samples) != _SUPPORTED_MODES or not all(samples.values()):
        return {"status": "HOLD", "reason": "MISSING_SAME_WORKLOAD_SAMPLES", "savings": None}

    def signature(x: MeterObservation) -> tuple[str, str, str, str, str, str]:
        return (x.task_sha256, x.tenant, x.principal, x.source_revision, x.provider, x.model_id)

    groups = [[signature(x) for x in arr] for arr in samples.values()]
    if any(group != groups[0] for group in groups[1:]):
        return {"status": "HOLD", "reason": "NOT_PAIRED_WORKLOADS", "savings": None}
    if any(
        x.actual_bill_usd is None or x.origin == "FIXTURE" for arr in samples.values() for x in arr
    ):
        return {"status": "HOLD", "reason": "MISSING_INDEPENDENT_BILLING", "savings": None}
    costs = {k: sum((x.actual_bill_usd for x in v), Decimal(0)) for k, v in samples.items()}
    base = costs["OFF"]
    if base <= 0:
        return {"status": "HOLD", "reason": "ZERO_BASELINE", "savings": None}
    # invoice_verified is a local caller assertion, not a verified external issuer.
    # Never describe synthetic price arithmetic as an authenticated cost ablation.
    return {
        "status": "HOLD",
        "reason": "INDEPENDENT_BILLING_ISSUER_AND_WORKLOAD_ADMISSION_MISSING",
        "savings": None,
        "hypothetical_claimed_costs_usd": {k: str(v) for k, v in costs.items()},
        "hypothetical_unadmitted_savings": {
            k: str((base - v) / base) for k, v in costs.items() if k != "OFF"
        },
    }


@dataclass
class LearningCandidate:
    candidate_id: str
    tenant: str
    principal: str
    source_revision: str
    evidence_sha256: str
    hypothesis_sha256: str
    author: str
    status: str = "DRAFT"
    evaluator: str | None = None
    reviewer: str | None = None
    evaluation_sha256: str | None = None
    approved_revision: str | None = None
    history: list[str] = field(default_factory=lambda: ["DRAFT"])


class GovernedLearning:
    """Nonprod candidate transitions only. Production mutation has no API."""

    def __init__(self) -> None:
        self.candidates: dict[str, LearningCandidate] = {}
        self.denied_sources: set[str] = set()
        self._seals: dict[str, str] = {}

    @staticmethod
    def _candidate_seal(c: LearningCandidate) -> str:
        return _hash(
            {
                "candidate_id": c.candidate_id,
                "tenant": c.tenant,
                "principal": c.principal,
                "source_revision": c.source_revision,
                "evidence_sha256": c.evidence_sha256,
                "hypothesis_sha256": c.hypothesis_sha256,
                "author": c.author,
                "status": c.status,
                "evaluator": c.evaluator,
                "reviewer": c.reviewer,
                "evaluation_sha256": c.evaluation_sha256,
                "approved_revision": c.approved_revision,
                "history": c.history,
            }
        )

    def _assert_current(self, c: LearningCandidate) -> None:
        if self.candidates.get(c.candidate_id) is not c or self._seals.get(
            c.candidate_id
        ) != self._candidate_seal(c):
            raise PermissionError("FORGED_OR_TAMPERED_LEARNING_CANDIDATE")

    def _reseal(self, c: LearningCandidate) -> None:
        self._seals[c.candidate_id] = self._candidate_seal(c)

    def draft(
        self,
        *,
        tenant: str,
        principal: str,
        source_revision: str,
        evidence_sha256: str,
        hypothesis_sha256: str,
        author: str,
    ) -> LearningCandidate:
        for v in (tenant, principal, source_revision, evidence_sha256, hypothesis_sha256, author):
            _identity(v)
        _digest(evidence_sha256)
        _digest(hypothesis_sha256)
        cid = _hash([tenant, principal, source_revision, evidence_sha256, hypothesis_sha256])
        if cid in self.candidates or source_revision in self.denied_sources:
            raise PermissionError("DUPLICATE_OR_REVOKED_CANDIDATE")
        c = LearningCandidate(
            cid, tenant, principal, source_revision, evidence_sha256, hypothesis_sha256, author
        )
        self.candidates[cid] = c
        self._reseal(c)
        return c

    def evaluate(
        self,
        c: LearningCandidate,
        *,
        evaluator: str,
        result_sha256: str,
        effect_verified: bool,
        negative_safe: bool,
    ) -> None:
        self._assert_current(c)
        _identity(evaluator)
        _digest(result_sha256)
        if c.status != "DRAFT" or evaluator == c.author or c.source_revision in self.denied_sources:
            raise PermissionError("NOT_INDEPENDENT_OR_STALE")
        c.evaluator, c.evaluation_sha256 = evaluator, result_sha256
        c.status = "EVALUATED" if effect_verified and negative_safe else "REJECTED"
        c.history.append(c.status)
        self._reseal(c)

    def approve_nonprod(
        self,
        c: LearningCandidate,
        *,
        reviewer: str,
        tenant: str,
        principal: str,
        source_revision: str,
        authentic_approval: bool,
    ) -> None:
        self._assert_current(c)
        _identity(reviewer)
        if (
            c.status != "EVALUATED"
            or not authentic_approval
            or reviewer in (c.author, c.evaluator)
            or (tenant, principal, source_revision) != (c.tenant, c.principal, c.source_revision)
            or source_revision in self.denied_sources
        ):
            raise PermissionError("APPROVAL_NOT_AUTHORIZED")
        c.status, c.reviewer, c.approved_revision = "NONPROD_APPROVED", reviewer, source_revision
        c.history.append(c.status)
        self._reseal(c)

    def rollback(self, c: LearningCandidate, *, tenant: str, principal: str) -> None:
        self._assert_current(c)
        if (tenant, principal) != (c.tenant, c.principal) or c.status != "NONPROD_APPROVED":
            raise PermissionError("INVALID_ROLLBACK")
        c.status, c.approved_revision = "ROLLED_BACK", None
        c.history.append(c.status)
        self._reseal(c)

    def revoke_source(self, revision: str) -> None:
        _identity(revision)
        self.denied_sources.add(revision)
        for c in self.candidates.values():
            self._assert_current(c)
            if c.source_revision == revision and c.status != "ROLLED_BACK":
                c.status, c.approved_revision = "SOURCE_REVOKED", None
                c.history.append(c.status)
                self._reseal(c)

    def promote_production(self, *_args: object, **_kwargs: object) -> None:
        raise PermissionError("G05_NEVER_AUTO_PROMOTES_PRODUCTION")
