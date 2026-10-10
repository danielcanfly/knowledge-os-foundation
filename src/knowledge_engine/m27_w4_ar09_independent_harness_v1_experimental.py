"""AR09 W4 independent offline harness: evidence-bound, fail-closed component.

No I02 import, network/Provider, production integration, or real holdout.
HMAC seals are deterministic *test trust roots*, NOT third-party attestations.
Caller claims alone never establish external authority or a release gate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

STATES = frozenset(
    {"ACCEPTED", "REJECTED", "PARTIAL", "ABSTAIN", "UNKNOWN", "NOT_ELIGIBLE"}
)
WORKLOADS = frozenset({"QA", "RESEARCH", "CODING", "ACTION"})
HEX = frozenset("0123456789abcdef")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_ok(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _json_ready(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"sha256": sha(value), "length": len(value)}
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_json_ready(v) for v in value]
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(
        _json_ready(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class Seal:
    role: str
    signer: str
    key_id: str
    signature: str


def claim(obj: Any) -> dict[str, Any]:
    value = asdict(obj)
    value.pop("seal", None)
    return value


def fixture_seal(obj: Any, role: str, signer: str, key_id: str, key: bytes) -> Seal:
    """Synthetic test signing helper; MUST NOT be used for real authority."""
    raw = role.encode() + b"\x00" + canonical(claim(obj))
    return Seal(role, signer, key_id, hmac.new(key, raw, "sha256").hexdigest())


@dataclass(frozen=True)
class TrustContext:
    # Keys provisioned *outside* candidate records; fixtures are NOT real trust.
    roots: Mapping[tuple[str, str, str], bytes]
    revoked_keys: frozenset[str] = frozenset()
    forbidden_signers: frozenset[str] = frozenset()
    now_ms: int = 1000
    authority_tier: str = "OFFLINE_FIXTURE_ONLY"
    i02_master_accepted_commit: str | None = None
    externally_sealed_holdout: bool = False
    external_score_custodian: bool = False
    real_source_and_billing_authority: bool = False

    def verify(self, obj: Any, role: str, executor: str) -> bool:
        stamp = getattr(obj, "seal", None)
        if not isinstance(stamp, Seal) or stamp.role != role:
            return False
        if (
            not stamp.signer or not stamp.key_id or stamp.signer == executor
            or stamp.signer in self.forbidden_signers
            or stamp.key_id in self.revoked_keys
            or not digest_ok(stamp.signature)
        ):
            return False
        key = self.roots.get((role, stamp.signer, stamp.key_id))
        if not isinstance(key, bytes) or not key:
            return False
        expected = fixture_seal(obj, role, stamp.signer, stamp.key_id, key)
        return hmac.compare_digest(expected.signature, stamp.signature)


@dataclass(frozen=True)
class Assignment:
    case_id: str
    task_id: str
    tenant_id: str
    version: int
    workload: str
    eligible: bool = True
    expected_output_sha256: str | None = None


@dataclass(frozen=True)
class Source:
    source_id: str
    tenant_id: str
    revision: str
    content: bytes
    content_sha256: str
    acl_tenants: tuple[str, ...]
    consent: bool
    revoked: bool
    issued_ms: int
    expires_ms: int
    seal: Seal | None = None


@dataclass(frozen=True)
class Citation:
    source_id: str
    revision: str
    source_sha256: str
    start: int
    end: int
    quoted: bytes


@dataclass(frozen=True)
class Artifact:
    task_id: str
    tenant_id: str
    content: bytes
    content_sha256: str
    citations: tuple[Citation, ...] = ()
    seal: Seal | None = None


@dataclass(frozen=True)
class Grade:
    task_id: str
    artifact_sha256: str
    fact_correct: bool
    quality_score: int
    grounding_ok: bool
    rubric_id: str
    seal: Seal | None = None


@dataclass(frozen=True)
class Stream:
    task_id: str
    artifact_sha256: str
    payload: bytes
    cited_source_ids: tuple[str, ...]
    started_ms: int
    server_flush_ms: int
    client_ack_ms: int | None
    terminal_ms: int
    seal: Seal | None = None


@dataclass(frozen=True)
class ResearchProof:
    task_id: str
    artifact_sha256: str
    checkpoint_sha256: str | None
    counterevidence_checked: bool
    tasks_unfinished: int
    source_ids_reviewed: tuple[str, ...]
    seal: Seal | None = None


@dataclass(frozen=True)
class RunnerProof:
    task_id: str
    artifact_sha256: str
    runner_id: str
    exit_code: int
    test_count: int
    real_subprocess: bool
    seal: Seal | None = None


@dataclass(frozen=True)
class Permit:
    task_id: str
    tenant_id: str
    action_id: str
    issued_ms: int
    expires_ms: int
    seal: Seal | None = None


@dataclass(frozen=True)
class Effect:
    task_id: str
    action_id: str
    observed: bool
    unknown_effect: bool
    resource_revision: str
    seal: Seal | None = None


@dataclass(frozen=True)
class Recovery:
    restart_checked: bool
    checkpoint_preserved: bool
    idempotency_checked: bool
    duplicate_accounting: bool
    unknown_effect: bool
    replay_count: int
    seal: Seal | None = None


@dataclass(frozen=True)
class Invoice:
    task_id: str
    attempt_id: str
    charge_id: str
    input_tokens: int
    output_tokens: int
    input_unit_micros: int
    output_unit_micros: int
    billed_micros: int
    complete: bool
    received_ms: int
    seal: Seal | None = None


@dataclass(frozen=True)
class Candidate:
    case_id: str
    task_id: str
    tenant_id: str
    version: int
    workload: str
    executor_id: str
    claimed_status: str
    attempts: tuple[str, ...]
    started_ms: int
    finished_ms: int
    artifact: Artifact | None = None
    sources: tuple[Source, ...] = ()
    grade: Grade | None = None
    stream: Stream | None = None
    research: ResearchProof | None = None
    runner: RunnerProof | None = None
    permit: Permit | None = None
    effect: Effect | None = None
    recovery: Recovery | None = None
    invoices: tuple[Invoice, ...] = ()
    synthetic_timing: bool = True
    dataset_provenance: str = "OFFLINE_FIXTURE"


@dataclass(frozen=True)
class EvidenceManifest:
    case_id: str
    artifact_sha256: str | None
    source_ids: tuple[str, ...]
    citation_count: int
    authority_checks: tuple[str, ...]
    sha256: str


@dataclass(frozen=True)
class EvaluationReceipt:
    case_id: str
    task_id: str
    workload: str
    outcome: str
    verified: bool
    reasons: tuple[str, ...]
    manifest: EvidenceManifest | None
    client_first_text_ms: int | None
    server_first_flush_ms: int | None
    task_latency_ms: int | None
    cost_micros: int | None
    receipt_sha256: str


@dataclass(frozen=True)
class DenominatorLedger:
    assigned: int
    eligible: int
    not_eligible: int
    accepted: int
    rejected: int
    partial: int
    abstain: int
    unknown: int
    success_rate: float | None
    missing_cases: tuple[str, ...]
    duplicate_cases: tuple[str, ...]
    duplicate_task_ids: tuple[str, ...]
    unassigned_cases: tuple[str, ...]
    cost_micros: int | None
    cost_per_verified_outcome_micros: float | None
    qa_interactive_p95_ms: int | None
    long_task_p95_ms: int | None
    latency_authority: str
    release_certification: str
    receipts: tuple[EvaluationReceipt, ...]


def nearest_rank(values: list[int], p: float) -> int | None:
    if not values:
        return None
    return sorted(values)[math.ceil(len(values) * p) - 1]


class IndependentOutcomeHarnessV1:
    """Evaluate external-assignment candidate records, never executor success labels.

    Phase A can exercise synthetically signed *offline* evidence only.
    Phase B and release eligibility cannot be switched on by candidate input.
    """

    def __init__(self, context: TrustContext):
        self.context = context

    def _sources(
        self, assignment: Assignment, candidate: Candidate, reasons: list[str],
    ) -> dict[str, Source]:
        found: dict[str, Source] = {}
        for src in candidate.sources:
            valid = (
                src.source_id not in found and bool(src.source_id)
                and src.tenant_id == assignment.tenant_id
                and src.tenant_id in src.acl_tenants
                and src.consent is True and src.revoked is False
                and bool(src.revision)
                and type(src.issued_ms) is int and type(src.expires_ms) is int
                and src.issued_ms <= candidate.started_ms
                and src.issued_ms <= self.context.now_ms < src.expires_ms
                and src.issued_ms <= candidate.finished_ms < src.expires_ms
                and sha(src.content) == src.content_sha256
                and self.context.verify(src, "source", candidate.executor_id)
            )
            if not valid:
                reasons.append("SOURCE_AUTHORITY_INVALID")
            else:
                found[src.source_id] = src
        return found

    def _artifact(
        self, assignment: Assignment, candidate: Candidate,
        sources: dict[str, Source], reasons: list[str],
    ) -> bool:
        art = candidate.artifact
        if art is None:
            reasons.append("ARTIFACT_MISSING")
            return False
        if (
            art.task_id != assignment.task_id
            or art.tenant_id != assignment.tenant_id
            or sha(art.content) != art.content_sha256
            or (assignment.expected_output_sha256 is not None
                and art.content_sha256 != assignment.expected_output_sha256)
            or not self.context.verify(art, "verifier", candidate.executor_id)
        ):
            reasons.append("ARTIFACT_BYTES_OR_VERIFIER_INVALID")
            return False
        citation_ids: set[tuple[str, int, int]] = set()
        for c in art.citations:
            src = sources.get(c.source_id)
            if (
                src is None or c.revision != src.revision
                or c.source_sha256 != src.content_sha256
                or type(c.start) is not int or type(c.end) is not int
                or not 0 <= c.start < c.end <= len(src.content)
                or not c.quoted or src.content[c.start:c.end] != c.quoted
                or (c.source_id, c.start, c.end) in citation_ids
            ):
                reasons.append("CITATION_SPAN_OR_REVISION_INVALID")
            citation_ids.add((c.source_id, c.start, c.end))
        return not any(
            e in reasons for e in (
                "ARTIFACT_BYTES_OR_VERIFIER_INVALID",
                "CITATION_SPAN_OR_REVISION_INVALID",
            )
        )

    def _grade(
        self, assignment: Assignment, candidate: Candidate, reasons: list[str],
    ) -> None:
        g, art = candidate.grade, candidate.artifact
        if (
            g is None or art is None or g.task_id != assignment.task_id
            or g.artifact_sha256 != art.content_sha256
            or g.fact_correct is not True or g.grounding_ok is not True
            or type(g.quality_score) is not int or not 0 <= g.quality_score <= 100
            or g.quality_score < 85 or not g.rubric_id
            or not self.context.verify(g, "grader", candidate.executor_id)
        ):
            reasons.append("INDEPENDENT_QUALITY_UNVERIFIED")

    def _stream(
        self, assignment: Assignment, candidate: Candidate, reasons: list[str],
    ) -> tuple[int | None, int | None]:
        s, a = candidate.stream, candidate.artifact
        if s is None or a is None:
            reasons.append("CLIENT_ACK_OR_VERIFIED_TEXT_MISSING")
            return None, None
        valid = (
            s.task_id == assignment.task_id
            and s.artifact_sha256 == a.content_sha256
            and isinstance(s.payload, bytes)
            and bool(s.payload.decode("utf-8", "replace").strip())
            and any(c.isalnum() for c in s.payload.decode("utf-8", "replace"))
            and s.payload in a.content
            and set(s.cited_source_ids) == {c.source_id for c in a.citations}
            and bool(s.cited_source_ids)
            and type(s.started_ms) is int
            and type(s.server_flush_ms) is int
            and type(s.client_ack_ms) is int
            and type(s.terminal_ms) is int
            and candidate.started_ms == s.started_ms
            and candidate.finished_ms == s.terminal_ms
            and s.started_ms <= s.server_flush_ms <= s.client_ack_ms < s.terminal_ms
            and self.context.verify(s, "client", candidate.executor_id)
        )
        if not valid:
            reasons.append("CLIENT_ACK_OR_VERIFIED_TEXT_MISSING")
            return None, None
        return s.client_ack_ms - s.started_ms, s.server_flush_ms - s.started_ms

    def _domain(
        self, a: Assignment, c: Candidate, reasons: list[str],
    ) -> tuple[int | None, int | None]:
        first, flush = None, None
        if a.workload == "QA":
            if c.artifact is None or not c.artifact.citations:
                reasons.append("QA_CITATION_GROUNDING_MISSING")
            first, flush = self._stream(a, c, reasons)
        if a.workload == "RESEARCH":
            r, art = c.research, c.artifact
            if (
                r is None or art is None or r.task_id != a.task_id
                or r.artifact_sha256 != art.content_sha256
                or not digest_ok(r.checkpoint_sha256)
                or r.counterevidence_checked is not True
                or type(r.tasks_unfinished) is not int or r.tasks_unfinished != 0
                or not r.source_ids_reviewed
                or not set(r.source_ids_reviewed) <= {s.source_id for s in c.sources}
                or not self.context.verify(r, "reviewer", c.executor_id)
            ):
                reasons.append("RESEARCH_OUTCOME_INCOMPLETE")
        if a.workload == "CODING":
            r, art = c.runner, c.artifact
            if (
                r is None or art is None or r.task_id != a.task_id
                or r.artifact_sha256 != art.content_sha256
                or not r.runner_id or r.runner_id == c.executor_id
                or type(r.exit_code) is not int or r.exit_code != 0
                or type(r.test_count) is not int or r.test_count <= 0
                or r.real_subprocess is not True
                or not self.context.verify(r, "runner", c.executor_id)
            ):
                reasons.append("RUNNER_EXIT_OR_SHA_UNVERIFIED")
        if a.workload in {"ACTION", "CODING"}:
            p, e = c.permit, c.effect
            if (
                p is None or e is None or p.task_id != a.task_id
                or e.task_id != a.task_id or p.tenant_id != a.tenant_id
                or not p.action_id or p.action_id != e.action_id
                or not p.issued_ms <= self.context.now_ms < p.expires_ms
                or e.observed is not True or e.unknown_effect is not False
                or not e.resource_revision
                or not self.context.verify(p, "permit", c.executor_id)
                or not self.context.verify(e, "observer", c.executor_id)
            ):
                reasons.append("PERMIT_EFFECT_UNKNOWN_OR_INVALID")
        return first, flush

    def _recovery(self, c: Candidate, reasons: list[str]) -> None:
        r = c.recovery
        if (
            r is None or not r.restart_checked
            or not r.checkpoint_preserved or not r.idempotency_checked
            or r.duplicate_accounting or r.unknown_effect
            or type(r.replay_count) is not int or r.replay_count < 0
            or not self.context.verify(r, "recovery", c.executor_id)
        ):
            reasons.append("RELIABILITY_RECOVERY_UNVERIFIED")

    def _cost(self, a: Assignment, c: Candidate) -> tuple[int | None, tuple[str, ...]]:
        ids = set()
        charges = set()
        amounts = []
        faults = []
        if not c.attempts or len(c.attempts) != len(set(c.attempts)):
            faults.append("DUPLICATE_OR_MISSING_ATTEMPT")
        for invoice in c.invoices:
            if invoice.attempt_id in ids or invoice.charge_id in charges:
                faults.append("DUPLICATE_CHARGE")
            ids.add(invoice.attempt_id)
            charges.add(invoice.charge_id)
            if (
                invoice.task_id != a.task_id
                or invoice.attempt_id not in c.attempts
                or not invoice.charge_id
                or any(type(x) is not int or x < 0 for x in (
                    invoice.input_tokens, invoice.output_tokens,
                    invoice.input_unit_micros, invoice.output_unit_micros,
                    invoice.billed_micros, invoice.received_ms,
                ))
                or invoice.billed_micros != (
                    invoice.input_tokens * invoice.input_unit_micros
                    + invoice.output_tokens * invoice.output_unit_micros
                )
                or not invoice.complete
                or invoice.received_ms > self.context.now_ms
                or not self.context.verify(invoice, "billing", c.executor_id)
            ):
                faults.append("INVOICE_USAGE_PRICE_UNVERIFIED")
            amounts.append(invoice.billed_micros)
        if set(c.attempts) != ids:
            faults.append("INVOICE_MISSING_OR_DELAYED")
        return (None if faults else sum(amounts)), tuple(sorted(set(faults)))

    def score(
        self, a: Assignment, c: Candidate | None, *,
        duplicate: bool = False, duplicate_charge: bool = False,
        duplicate_task: bool = False,
    ) -> EvaluationReceipt:
        reasons: list[str] = []
        manifest = None
        first = flush = latency = cost = None
        if not a.eligible:
            status = "NOT_ELIGIBLE"
            if c is not None:
                reasons.append("UNAUTHORIZED_INELIGIBLE_SUBMISSION")
        elif c is None:
            status = "UNKNOWN"
            reasons.append("ASSIGNED_NOT_REPORTED")
        else:
            if duplicate:
                reasons.append("DUPLICATE_CASE_ID")
            if duplicate_charge:
                reasons.append("DUPLICATE_CHARGE_ACROSS_TASKS")
            if duplicate_task:
                reasons.append("DUPLICATE_TASK_ID")
            if (
                not a.case_id or not a.task_id or not a.tenant_id
                or a.workload not in WORKLOADS or type(a.version) is not int
                or a.version < 0
                or (a.case_id, a.task_id, a.tenant_id, a.version, a.workload)
                != (c.case_id, c.task_id, c.tenant_id, c.version, c.workload)
            ):
                reasons.append("CASE_IDENTITY_MISMATCH")
            if c.claimed_status not in STATES:
                reasons.append("INVALID_EXECUTOR_STATUS")
            if c.dataset_provenance == "I02_WORKER_TEST_ANSWERS":
                reasons.append("HOLDOUT_CONTAMINATION")
            if (
                type(c.started_ms) is not int or type(c.finished_ms) is not int
                or c.started_ms < 0 or c.started_ms > c.finished_ms
                or c.finished_ms > self.context.now_ms
            ):
                reasons.append("CLOCK_INCONSISTENT")
            else:
                latency = c.finished_ms - c.started_ms
            sources = self._sources(a, c, reasons)
            self._artifact(a, c, sources, reasons)
            self._grade(a, c, reasons)
            first, flush = self._domain(a, c, reasons)
            self._recovery(c, reasons)
            cost, cost_faults = self._cost(a, c)
            # Missing / late billing is not proof of free service; maintain UNKNOWN.
            if cost_faults:
                reasons.extend(cost_faults)
            art = c.artifact
            data = {
                "case": a.case_id, "task": a.task_id,
                "artifact": art.content_sha256 if art else None,
                "sources": sorted(sources), "citations": [
                    asdict(x) for x in art.citations
                ] if art else [],
                "authority_checks": sorted(set(reasons)),
            }
            manifest = EvidenceManifest(
                a.case_id, art.content_sha256 if art else None,
                tuple(sorted(sources)), len(art.citations) if art else 0,
                tuple(sorted(set(reasons))), sha(canonical(data)),
            )
            if c.claimed_status in {"ABSTAIN", "PARTIAL", "REJECTED", "UNKNOWN"}:
                status = c.claimed_status
            elif c.claimed_status == "NOT_ELIGIBLE":
                status = "REJECTED"
                reasons.append("EXECUTOR_CANNOT_ASSERT_ELIGIBILITY")
            elif (
                (c.recovery is not None and c.recovery.unknown_effect)
                or (c.effect is not None and c.effect.unknown_effect)
            ):
                status = "UNKNOWN"
            elif reasons:
                status = "REJECTED"
            else:
                status = "ACCEPTED"
        if c is not None and status == "ACCEPTED" and reasons:
            status = "REJECTED"
        # Rejected invalid evidence is different from an intentional abstention.
        verified = status == "ACCEPTED" and not reasons
        receipt_data = {
            "case": a.case_id, "task": a.task_id, "outcome": status,
            "reasons": sorted(set(reasons)), "manifest": manifest.sha256 if manifest else None,
            "first": first, "flush": flush, "latency": latency, "cost": cost,
            "tier": self.context.authority_tier,
        }
        return EvaluationReceipt(
            a.case_id, a.task_id, a.workload, status, verified,
            tuple(sorted(set(reasons))), manifest, first, flush, latency, cost,
            sha(canonical(receipt_data)),
        )

    def evaluate(
        self, assignments: tuple[Assignment, ...], candidates: tuple[Candidate, ...],
    ) -> DenominatorLedger:
        # Frozen assignment catalog is the denominator; missing cases NEVER vanish.
        assigned = [a.case_id for a in assignments]
        if len(assigned) != len(set(assigned)):
            raise ValueError("DUPLICATE_ASSIGNMENT_DENOMINATOR")
        submitted: dict[str, list[Candidate]] = {}
        for item in candidates:
            submitted.setdefault(item.case_id, []).append(item)
        duplicates = tuple(sorted(k for k, v in submitted.items() if len(v) > 1))
        task_users: dict[str, set[str]] = {}
        for a in assignments:
            task_users.setdefault(a.task_id, set()).add(a.case_id)
        duplicate_tasks = tuple(sorted(
            task for task, cases in task_users.items() if len(cases) > 1
        ))
        repeated_task_cases = {
            case for task in duplicate_tasks for case in task_users[task]
        }
        unassigned = tuple(sorted(set(submitted) - set(assigned)))
        charge_users: dict[str, set[str]] = {}
        for item in candidates:
            for bill in item.invoices:
                charge_users.setdefault(bill.charge_id, set()).add(item.case_id)
        charge_collisions = {
            case for users in charge_users.values() if len(users) > 1
            for case in users
        }
        receipts = tuple(self.score(
            a, submitted.get(a.case_id, [None])[0],
            duplicate=a.case_id in duplicates,
            duplicate_charge=a.case_id in charge_collisions,
            duplicate_task=a.case_id in repeated_task_cases,
        ) for a in assignments)
        counts = {key: sum(r.outcome == key for r in receipts) for key in STATES}
        eligible = sum(a.eligible for a in assignments)
        accepted = counts["ACCEPTED"]
        valid_costs = all(
            r.cost_micros is not None
            for a, r in zip(assignments, receipts, strict=True)
            if a.eligible
        ) and not duplicates and not unassigned and not charge_collisions and not duplicate_tasks
        total = (
            sum(r.cost_micros for a, r in zip(assignments, receipts, strict=True)
                if a.eligible and r.cost_micros is not None)
            if valid_costs and eligible else None
        )
        qa_latencies = [
            r.client_first_text_ms for a, r in zip(assignments, receipts, strict=True)
            if a.workload == "QA" and r.verified and r.client_first_text_ms is not None
        ]
        long_latencies = [
            r.task_latency_ms for a, r in zip(assignments, receipts, strict=True)
            if a.workload != "QA" and r.task_latency_ms is not None
        ]
        real_gate = (
            self.context.authority_tier == "EXTERNALLY_AUTHENTICATED"
            and self.context.i02_master_accepted_commit is not None
            and self.context.externally_sealed_holdout
            and self.context.external_score_custodian
            and self.context.real_source_and_billing_authority
            and len(assignments) == 523
            and all(not c.synthetic_timing and c.dataset_provenance == "EXTERNAL_SEALED_HOLDOUT"
                    for c in candidates)
        )
        # Further original 523 cited/quality/p95 gates require a separate
        # trusted product bench and REL01 certificate, intentionally no PASS path.
        gate = "AWAITING_INDEPENDENT_523_RELEASE_CERTIFICATION" if real_gate else "NOT_CERTIFIED"
        return DenominatorLedger(
            assigned=len(assignments), eligible=eligible,
            not_eligible=counts["NOT_ELIGIBLE"], accepted=accepted,
            rejected=counts["REJECTED"], partial=counts["PARTIAL"],
            abstain=counts["ABSTAIN"], unknown=counts["UNKNOWN"],
            success_rate=accepted / eligible if eligible else None,
            missing_cases=tuple(sorted(set(assigned) - set(submitted))),
            duplicate_cases=duplicates, duplicate_task_ids=duplicate_tasks,
            unassigned_cases=unassigned,
            cost_micros=total,
            cost_per_verified_outcome_micros=(total / accepted if total is not None
                                             and accepted else None),
            qa_interactive_p95_ms=nearest_rank(qa_latencies, .95),
            long_task_p95_ms=nearest_rank(long_latencies, .95),
            latency_authority="SYNTHETIC_NOT_PRODUCT_P95",
            release_certification=gate, receipts=receipts,
        )
