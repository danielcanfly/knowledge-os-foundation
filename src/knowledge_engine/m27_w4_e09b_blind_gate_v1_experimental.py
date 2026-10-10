"""AR09 Phase B: candidate-opaque admission, one-shot ledger, offline receipt audit.

All metadata is public/redacted. No hidden prompts, answer keys, I02 imports,
network operations, provider calls, or automatic dispatch. A local mock signature,
fixture HMAC, claimed approval, or self-attestation cannot authorize Phase B.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BLOCKED = "E09B_PHASE_B_BLOCKED_EVIDENCE_DEBT"
SHA = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_I02 = "0cd2b74baa2c892b163ffe5138de2df863417889"
REQUIRED_AUTHORITIES = frozenset({
    "holdout_custodian", "source_rights", "consent", "scorer",
    "independent_reviewer", "billing", "client_observer", "ci_runner",
    "effect_observer", "execution_approver",
})
PREFLIGHT_DEPENDENCIES = ("D09", "T09", "P09")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def good_sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


@dataclass(frozen=True)
class CandidateFreeze:
    commit: str
    tree: str
    image_sha256: str
    build_sha256: str
    runner_sha256: str
    master_accepted_commit: str = EXPECTED_I02


@dataclass(frozen=True)
class IndependentCorpus:
    manifest_sha256: str
    signed_manifest_sha256: str
    snapshot_sha256: str
    dataset_version: str
    cases: int
    independent_intents: int
    source_records: int
    source_documents: int
    source_families: int
    long_tail: int
    paraphrase_probes: int
    negative_controls: int
    supported_positives: int
    distinct_reused: int
    max_document_share_pct: float
    max_family_share_pct: float
    graphology_share_pct: float
    historical_topic_share_pct: float
    separately_frozen_original_523: bool
    original_523_version_sha256: str
    original_523_distinct_questions: int
    includes_historical_182_replays: bool = False
    contains_direct100: bool = False
    contains_stage30p: bool = False
    contains_exposed_nine: bool = False


@dataclass(frozen=True)
class SourceClearance:
    rights_manifest_sha256: str
    acl_manifest_sha256: str
    consent_manifest_sha256: str
    license_id: str
    custodian_id: str
    snapshot_expires_utc: int
    retention_approved: bool
    revoked: bool
    permitted_evaluator_only: bool
    leaks_to_candidate: bool
    access_log_sha256: str


@dataclass(frozen=True)
class UpstreamReport:
    task_id: str
    status: str
    report_sha256: str
    master_acceptance_sha256: str
    independently_accepted: bool


@dataclass(frozen=True)
class AuthorityClaim:
    role: str
    signer_id: str
    key_id: str
    signature_sha256: str
    independently_custodied: bool
    authorized_for_dataset_sha256: str
    expires_utc: int
    executor_id: str = ""


@dataclass(frozen=True)
class PhaseBPacket:
    candidate: CandidateFreeze
    corpus: IndependentCorpus
    source: SourceClearance
    upstream: tuple[UpstreamReport, ...]
    authorities: tuple[AuthorityClaim, ...]
    reviewer_ids: tuple[str, ...]
    grader_version: str
    rubric_sha256: str
    scorer_build_sha256: str
    calibration_sha256: str
    frozen_case_ids_digest: str
    evaluator_id: str
    executor_id: str
    now_utc: int
    runtime_interface_sha256: str
    approval_sha256: str
    original_benchmark_gate_required: bool = True


@dataclass(frozen=True)
class AdmissionDecision:
    status: str
    reasons: tuple[str, ...]
    candidate_commit: str
    manifest_sha256: str
    decision_sha256: str
    official_evaluation_ran: bool = False
    release_certified: bool = False


class IndependentVerifier(Protocol):
    """Real verifier outside developer worktree, with independently held trust roots."""

    def __call__(self, claim: AuthorityClaim) -> bool: ...


class AdmissionGateV1:
    """Preflight only. Never executes or reads private cases or labels.

    Independent verifier and interface must be injected by an evaluator host,
    not constructed from worktree fixtures. Default is deliberately blocked.
    """

    def __init__(
        self,
        verifier: IndependentVerifier | None = None,
        *,
        independently_operated: bool = False,
        authorized_interface: Callable[..., object] | None = None,
    ) -> None:
        self.verifier = verifier
        self.independently_operated = independently_operated
        self.authorized_interface = authorized_interface

    def inspect(self, p: PhaseBPacket) -> AdmissionDecision:
        errors: set[str] = set()
        c, h, s = p.candidate, p.corpus, p.source
        if (
            not GIT_SHA.fullmatch(c.commit or "")
            or not GIT_SHA.fullmatch(c.tree or "")
            or c.commit != EXPECTED_I02
            or c.master_accepted_commit != EXPECTED_I02
            or not all(good_sha(v) for v in (
                c.image_sha256, c.build_sha256, c.runner_sha256,
            ))
        ):
            errors.add("CANDIDATE_DIGEST_OR_MASTER_MISMATCH")
        if not all(good_sha(v) for v in (
            h.manifest_sha256, h.signed_manifest_sha256, h.snapshot_sha256,
            h.original_523_version_sha256, p.frozen_case_ids_digest,
        )) or not h.dataset_version:
            errors.add("CORPUS_MANIFEST_OR_SIGNATURE_UNFROZEN")
        if not all(type(v) is int and v >= minimum for v, minimum in (
            (h.cases, 200), (h.independent_intents, 140),
            (h.source_records, 100), (h.source_documents, 20),
            (h.source_families, 5), (h.long_tail, 40),
            (h.paraphrase_probes, 60), (h.negative_controls, 30),
            (h.supported_positives, 20),
        )):
            errors.add("BLIND_COHORT_BREADTH_INSUFFICIENT")
        if (
            type(h.distinct_reused) is not int or h.distinct_reused != 0
            or h.includes_historical_182_replays or h.contains_direct100
            or h.contains_stage30p or h.contains_exposed_nine
        ):
            errors.add("HOLDOUT_CONTAMINATED_BY_KNOWN_QUESTIONS")
        if (
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (
                h.max_document_share_pct, h.max_family_share_pct,
                h.graphology_share_pct, h.historical_topic_share_pct,
            ))
            or not 0 <= h.max_document_share_pct <= 10
            or not 0 <= h.max_family_share_pct <= 20
            or not 0 <= h.graphology_share_pct <= 15
            or not 0 <= h.historical_topic_share_pct <= 20
        ):
            errors.add("BLIND_CONCENTRATION_CAP_EXCEEDED")
        if (
            not h.separately_frozen_original_523
            or type(h.original_523_distinct_questions) is not int
            or h.original_523_distinct_questions != 523
        ):
            errors.add("ORIGINAL_523_DISTINCT_BENCHMARK_UNPROVEN")
        if not all(good_sha(v) for v in (
            s.rights_manifest_sha256, s.acl_manifest_sha256,
            s.consent_manifest_sha256, s.access_log_sha256,
        )) or not s.license_id or not s.custodian_id:
            errors.add("SOURCE_RIGHTS_ACL_CONSENT_UNVERIFIED")
        if (
            type(p.now_utc) is not int or type(s.snapshot_expires_utc) is not int
            or s.snapshot_expires_utc <= p.now_utc
            or s.revoked or not s.retention_approved
            or not s.permitted_evaluator_only or s.leaks_to_candidate
        ):
            errors.add("SOURCE_EXPIRED_REVOKED_OR_LEAKED")
        reports: dict[str, UpstreamReport] = {}
        for u in p.upstream:
            if u.task_id in reports or u.task_id not in PREFLIGHT_DEPENDENCIES:
                errors.add("UPSTREAM_REPORT_SET_INVALID")
            reports[u.task_id] = u
        for task in PREFLIGHT_DEPENDENCIES:
            u = reports.get(task)
            if u is None:
                errors.add(f"{task}_REPORT_ABSENT")
            elif (
                u.status != "MASTER_ADMITTED"
                or not u.independently_accepted
                or not good_sha(u.report_sha256)
                or not good_sha(u.master_acceptance_sha256)
            ):
                errors.add(f"{task}_NOT_ADMITTED")
        if (
            len(p.reviewer_ids) < 2
            or len(set(p.reviewer_ids)) != len(p.reviewer_ids)
            or any(not v or v == p.executor_id for v in p.reviewer_ids)
            or not p.evaluator_id or p.evaluator_id == p.executor_id
        ):
            errors.add("INDEPENDENT_REVIEWER_CUSTODY_MISSING")
        if (
            not p.grader_version or not all(good_sha(v) for v in (
                p.rubric_sha256, p.scorer_build_sha256, p.calibration_sha256,
            ))
        ):
            errors.add("SCORER_RUBRIC_CALIBRATION_UNFROZEN")
        if (
            not good_sha(p.runtime_interface_sha256)
            or not good_sha(p.approval_sha256)
            or not self.independently_operated
            or self.authorized_interface is None
        ):
            errors.add("AUTHORIZED_INDEPENDENT_RUN_INTERFACE_MISSING")
        claims: dict[str, AuthorityClaim] = {}
        for a in p.authorities:
            if a.role in claims or a.role not in REQUIRED_AUTHORITIES:
                errors.add("AUTHORITY_ROLE_SET_INVALID")
            claims[a.role] = a
        for role in sorted(REQUIRED_AUTHORITIES):
            a = claims.get(role)
            if a is None:
                errors.add(f"AUTHORITY_{role.upper()}_MISSING")
            elif (
                not a.signer_id or a.signer_id in {p.executor_id, p.evaluator_id}
                or a.executor_id == a.signer_id
                or not a.key_id or not good_sha(a.signature_sha256)
                or a.authorized_for_dataset_sha256 != h.manifest_sha256
                or type(a.expires_utc) is not int or a.expires_utc <= p.now_utc
                or not a.independently_custodied
                or self.verifier is None
                or not self.verifier(a)
            ):
                errors.add(f"AUTHORITY_{role.upper()}_UNVERIFIED")
        if p.original_benchmark_gate_required is not True:
            errors.add("ORIGINAL_523_GATE_OMITTED")
        reasons = tuple(sorted(errors))
        public = {
            "candidate": c.commit, "manifest": h.manifest_sha256,
            "status": BLOCKED if reasons else "PRECONDITIONS_SATISFIED_NOT_EXECUTED",
            "reasons": reasons,
        }
        return AdmissionDecision(
            public["status"], reasons, c.commit, h.manifest_sha256,
            digest(json.dumps(public, sort_keys=True, separators=(",", ":"))),
        )


class TestOnceLedger:
    """Evaluator-custodied exclusive event file, never shared with candidate.

    Files contain ONLY opaque run ID digest, candidate/dataset digests and state.
    O_EXCL prevents retrying a run, including failed and interrupted runs.
    """

    def __init__(self, private_directory: Path):
        self.private_directory = private_directory

    def reserve(self, run_id: str, candidate_sha: str, corpus_sha: str) -> str:
        if not run_id or not all(good_sha(x) for x in (candidate_sha, corpus_sha)):
            raise ValueError("Invalid immutable run binding")
        if not self.private_directory.is_dir():
            raise PermissionError("Evaluator-only directory must preexist")
        event = {
            "event": "ONE_SHOT_RESERVED", "run_id_sha256": digest(run_id),
            "candidate_sha256": candidate_sha, "corpus_sha256": corpus_sha,
        }
        raw = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        path = self.private_directory / (digest(run_id) + ".jsonl")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
        except BaseException:
            # An ambiguous partial write still consumes the one-shot reservation.
            raise
        return digest(raw)


@dataclass(frozen=True)
class ClientTrace:
    clock_domain: str
    request_received_ns: int | None
    verified_substantive_received_ns: int | None
    cited_segment_received_ns: int | None
    terminal_received_ns: int | None
    client_receipt_sha256: str | None
    verified_bytes: int
    terminal_only: bool = False
    progress_only: bool = False


@dataclass(frozen=True)
class OpaqueCase:
    case_id: str
    label: str  # Independent frozen ANSWERABLE / SAFE_ABSTAIN only.
    eligible: bool = True


@dataclass(frozen=True)
class CaseReceipt:
    case_id: str
    result: str  # ANSWER / ABSTAIN / TIMEOUT / ERROR / PARTIAL / UNKNOWN
    score: int | None
    independent_grade_verified: bool
    evidence_and_original_citation_verified: bool
    supported: bool
    privacy_ok: bool
    false_safe: bool
    trace: ClientTrace | None
    attempts: tuple[str, ...]
    invoiced_attempts: tuple[str, ...]
    cost_micros: int | None
    billing_authority_verified: bool
    price_authority_verified: bool
    semantic_bad_published: bool = False


@dataclass(frozen=True)
class DiagnosticAudit:
    status: str
    denominator: int
    answerable: int
    answerable_success: int
    safe_count: int
    safe_correct: int
    missing_count: int
    failure_count: int
    false_safe_count: int
    unsupported_count: int
    streaming_failure_count: int
    billing_unknown_count: int
    answerable_success_rate: float | None
    p95_ms: float | None
    total_cost_micros: int | None
    reasons: tuple[str, ...]


def audit_opaque_offline(
    cohort: tuple[OpaqueCase, ...],
    submissions: tuple[CaseReceipt, ...],
    *,
    deadline_ms: int = 30_000,
) -> DiagnosticAudit:
    """Synthetic metadata diagnostic ONLY, cannot issue product release or GO.

    Any omitted eligible result remains in the denominator, with deadline penalty.
    A score is not independent merely because a model sets a boolean here.
    """
    errors: set[str] = set()
    if type(deadline_ms) is not int or deadline_ms < 15_000:
        raise ValueError("Hard timeout must be >= 15 seconds")
    declared = [c.case_id for c in cohort if c.eligible]
    if len(set(declared)) != len(declared) or not declared:
        errors.add("DUPLICATE_OR_EMPTY_ASSIGNED_CASES")
    if any(c.label not in {"ANSWERABLE", "SAFE_ABSTAIN"} for c in cohort):
        errors.add("INVALID_INDEPENDENT_LABEL")
    by_id: dict[str, CaseReceipt] = {}
    duplicate_ids: set[str] = set()
    for x in submissions:
        if x.case_id in by_id:
            duplicate_ids.add(x.case_id)
            errors.add("DUPLICATE_RESULT_OR_RETEST")
        if x.case_id not in declared:
            errors.add("UNASSIGNED_OR_INELIGIBLE_RESULT")
        by_id[x.case_id] = x
    success = safe_ok = missing = false_safe = unsupported = stream_fail = 0
    billing_unknown = failures = 0
    durations: list[float] = []
    costs: list[int] = []
    answerable = sum(c.eligible and c.label == "ANSWERABLE" for c in cohort)
    safe_count = sum(c.eligible and c.label == "SAFE_ABSTAIN" for c in cohort)
    for case in cohort:
        if not case.eligible:
            continue
        r = by_id.get(case.case_id)
        if r is None or case.case_id in duplicate_ids:
            missing += int(r is None)
            failures += 1
            billing_unknown += 1
            durations.append(deadline_ms)
            continue
        t = r.trace
        client_valid = (
            t is not None and bool(t.clock_domain)
            and all(type(v) is int and v >= 0 for v in (
                t.request_received_ns, t.terminal_received_ns,
            ))
            and t.request_received_ns <= t.terminal_received_ns
            and good_sha(t.client_receipt_sha256)
        )
        duration = (
            (t.terminal_received_ns - t.request_received_ns) / 1_000_000
            if client_valid else deadline_ms
        )
        if r.result in {"TIMEOUT", "UNKNOWN"}:
            duration = max(duration, deadline_ms)
        durations.append(duration)
        if not client_valid:
            errors.add("MISSING_TRUE_CLIENT_RECEIPT_OR_CLOCK")
        invoice_valid = (
            type(r.cost_micros) is int and r.cost_micros >= 0
            and bool(r.attempts) and len(set(r.attempts)) == len(r.attempts)
            and len(set(r.invoiced_attempts)) == len(r.invoiced_attempts)
            and set(r.attempts) == set(r.invoiced_attempts)
            and r.billing_authority_verified is True
            and r.price_authority_verified is True
        )
        if invoice_valid:
            costs.append(r.cost_micros)
        else:
            billing_unknown += 1
        if r.false_safe or (case.label == "ANSWERABLE" and r.result == "ABSTAIN"):
            false_safe += 1
        if r.semantic_bad_published or not r.supported or not r.privacy_ok:
            unsupported += 1
        if case.label == "ANSWERABLE":
            stream_ok = (
                client_valid and t.verified_substantive_received_ns is not None
                and t.cited_segment_received_ns is not None
                and type(t.verified_substantive_received_ns) is int
                and type(t.cited_segment_received_ns) is int
                and t.request_received_ns <= t.verified_substantive_received_ns
                <= t.cited_segment_received_ns < t.terminal_received_ns
                and type(t.verified_bytes) is int and t.verified_bytes > 0
                and not t.terminal_only and not t.progress_only
            )
            if not stream_ok:
                stream_fail += 1
            good = (
                r.result == "ANSWER" and type(r.score) is int
                and r.score >= 85 and r.score <= 100
                and r.independent_grade_verified
                and r.evidence_and_original_citation_verified
                and r.supported and r.privacy_ok and not r.false_safe
                and not r.semantic_bad_published and stream_ok
                and invoice_valid and duration < 15_000
            )
            success += int(good)
            failures += int(not good)
        else:
            good = (
                r.result == "ABSTAIN" and r.supported and r.privacy_ok
                and not r.semantic_bad_published and not r.false_safe
                and client_valid and invoice_valid and duration < 15_000
            )
            safe_ok += int(good)
            failures += int(not good)
    if len(submissions) != len(declared) or missing:
        errors.add("NONSELECTIVE_DENOMINATOR_INCOMPLETE")
    if false_safe:
        errors.add("FALSE_SAFE_SUPPORTED_CASE")
    if unsupported:
        errors.add("UNSUPPORTED_OR_UNSAFE_PUBLICATION")
    if stream_fail:
        errors.add("SUBSTANTIVE_CLIENT_STREAM_UNVERIFIED")
    if billing_unknown:
        errors.add("UNKNOWN_COST_NOT_ZERO")
    if failures:
        errors.add("OUTCOME_OR_SCORE_FAILURE")
    p95 = sorted(durations)[math.ceil(0.95 * len(durations)) - 1] if durations else None
    if p95 is None or p95 >= 15_000:
        errors.add("TRUE_CLIENT_P95_NOT_UNDER_15_SECONDS")
    rate = success / answerable if answerable else None
    if rate is None or rate <= 0.95:
        errors.add("ANSWERABLE_SUCCESS_NOT_ABOVE_95_PERCENT")
    if safe_ok != safe_count:
        errors.add("SAFE_ABSTENTION_NOT_100_PERCENT")
    # Every run through this helper is synthetic; never promote to official verdict.
    return DiagnosticAudit(
        "OFFLINE_DIAGNOSTIC_NOT_PRODUCT_SCORE", len(declared), answerable,
        success, safe_count, safe_ok, missing, failures, false_safe,
        unsupported, stream_fail, billing_unknown, rate, p95,
        sum(costs) if not billing_unknown else None, tuple(sorted(errors)),
    )
