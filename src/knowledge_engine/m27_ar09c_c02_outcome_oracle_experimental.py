"""AR09C independent *offline* C02 fixture-byte and terminal-outcome probe.

C02 is an in-memory successor. This module does not authenticate an actual
observer, real provider, independent scorer, client delivery or durable commit.
AR09B's terminal_durable field is mapped ONLY to the committed synthetic
head-7 fixture, never to actual physical persistence. Every output explicitly
carries noProvider/noRealTool/noDurable; no release/authorized success possible.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from knowledge_engine.m27_ar02_ar05_reconciled_vertical_experimental import (
    OBSERVER_SECRET,
    VERIFIER_SECRET,
    PreparedLoop,
)
from knowledge_engine.m27_ar02_reconciliation_v2_experimental import (
    TerminalReceipt,
    digest_bytes,
    hex_digest,
    observation_message,
)
from knowledge_engine.m27_ar05_verification_experimental import (
    PublicationNotice,
    VerificationReceipt,
    verification_message,
)
from knowledge_engine.m27_ar09b_independent_eval_experimental import (
    BatchMetrics,
    CaseDecision,
    Charge,
    EvaluationContext,
    OutcomeEvidence,
    PreterminalSegment,
    TrustedObservation,
    evaluate_batch,
    evaluate_case,
)

MOCK_ONLY_FUNCTIONAL_SUCCESS = "MOCK_ONLY_FUNCTIONAL_SUCCESS"
MOCK_ONLY_REJECTED = "MOCK_ONLY_REJECTED"
FROZEN_NATIVE_BYTES = b"mock native source fixture original bytes"
FROZEN_FRAME_BYTES = b"cited fixture answer"
FROZEN_SOURCE_HASH = hashlib.sha256(FROZEN_NATIVE_BYTES).hexdigest()
FROZEN_FRAME_HASH = hashlib.sha256(FROZEN_FRAME_BYTES).hexdigest()
FIXTURE_EVALUATOR = "ar09c-offline-custodian"
FIXTURE_ORACLE = "fixture-verifier"
FIXTURE_EXECUTOR = "fixture-generator"
FIXTURE_ID = "c02-frozen-oracle-v1"
EXPECTED_HARD_GATES = frozenset({
    "source", "policy", "effect", "approval", "client_ack",
})


@dataclass(frozen=True, slots=True)
class C02Decision:
    label: str
    failures: tuple[str, ...]
    ar09b: CaseDecision
    candidate: OutcomeEvidence
    oracle: TrustedObservation
    original_nonterminal_unknown: bool
    mock_terminal_observed: bool
    no_provider: bool = True
    no_real_tool: bool = True
    no_durable: bool = True
    authorized_task_success: bool = False
    real_grade: str = "UNVERIFIED"
    real_cost: str = "UNVERIFIED"
    independent_holdout: str = "UNVERIFIED"


def _event_hash(previous: str, seq: int, kind: str, intent: str,
                t1: str, observation_id: str | None) -> str:
    return hex_digest(digest_bytes({
        "parent": previous, "seq": seq, "kind": kind,
        "intent": intent, "original_t1": t1,
        "observation": observation_id,
    }))


def _audit(loop: PreparedLoop, terminal: TerminalReceipt | None,
           signed: VerificationReceipt | None,
           notice: PublicationNotice | None,
           charges: tuple[Charge, ...]) -> tuple[tuple[str, ...], bool, bool]:
    """Recalculate source/observer, receipt, hash-chain and cost from C02 APIs.

    These are test *witnesses*, not real attestations. The separately frozen
    literal catalog is never populated from a worker-controlled outcome label.
    """
    faults: list[str] = []

    def require(ok: bool, reason: str) -> None:
        if not ok:
            faults.append(reason)

    run, tenant = "run-fixture", "tenant-fixture"
    try:
        original = loop.kernel.read(run, tenant)
    except Exception:
        original = {}
        faults.append("ACCEPTED_KERNEL_NOT_READABLE")
    original_unknown = (
        original.get("head") == 5 and original.get("epoch") == 1
        and original.get("terminal") is False
        and original.get("unknown") == {"intent-fixture"}
    )
    require(original_unknown, "ACCEPTED_KERNEL_DRIFT_OR_NON_UNKNOWN")
    require(
        original.get("charges") == {"charge-fixture": ("reserve-fixture", 2)}
        and original.get("spent") == 2,
        "ACCEPTED_KERNEL_CHARGE_MISMATCH",
    )
    require(
        loop.kernel.network_requests == 0 and loop.action.provider_calls == 0,
        "REAL_DISPATCH_FORBIDDEN",
    )
    v2 = loop.v2
    events = v2.history
    require(v2.run_id == run and v2.tenant_id == tenant and v2.epoch == 1,
            "V2_IDENTITY_EPOCH_MISMATCH")
    require(len(events) in (1, 2, 3), "V2_UNEXPECTED_EVENT_COUNT")
    require(
        bool(events) and events[0].seq == 5
        and events[0].kind == "T3_UNKNOWN_EFFECT",
        "V2_T3_NOT_ANCHORED",
    )
    previous = events[0].event_hash if events else ""
    for index, event in enumerate(events[1:], 1):
        ok = (
            event.seq == 5 + index
            and event.event_hash == _event_hash(
                previous, event.seq, event.kind, v2.intent_id,
                v2.original_t1_digest, event.observation_id,
            )
            and event.original_t1_digest == v2.original_t1_digest
        )
        require(ok, "V2_HASH_CHAIN_BROKEN")
        previous = event.event_hash
    require(
        bool(events) and v2.head == events[-1].seq
        and v2.head_hash == events[-1].event_hash,
        "V2_HEAD_EVENT_MISMATCH",
    )
    obs = loop.observation
    evid = obs.evidence
    source = loop.source.read()
    original_evidence = loop.publication.original_evidence
    observed = loop.publication.observed_evidence
    require(
        source.source_id == "source-id"
        and source.revision == "revision-1"
        and source.digest == FROZEN_SOURCE_HASH
        and source.exclusion_generation == 1
        and not source.revoked and not source.excluded
        and source.consent_expires_at > 101
        and source.source_expires_at > 101,
        "SOURCE_FRESHNESS_REVOCATION_OR_CONSENT",
    )
    require(
        original_evidence.identity_kind == "native"
        and observed.identity_kind == "native"
        and original_evidence.content_bytes == FROZEN_NATIVE_BYTES
        and observed == original_evidence
        and original_evidence.content_sha256 == FROZEN_SOURCE_HASH,
        "NATIVE_SOURCE_BYTES_OR_REVISION_CHANGED",
    )
    cite = original_evidence.citations
    require(
        len(cite) == 1 and cite[0].citation_id == "cite-fixture"
        and cite[0].source_revision == "revision-1"
        and cite[0].source_id == "source-id"
        and cite[0].source_bytes_sha256 == FROZEN_SOURCE_HASH
        and (cite[0].claim_start, cite[0].claim_end) == (0, 10)
        and loop.publication.expected_citation_ids == ("cite-fixture",),
        "NATIVE_CITATION_STALE_OR_MUTATED",
    )
    require(
        obs.tenant_id == tenant and obs.run_id == run
        and obs.intent_id == v2.intent_id
        and obs.original_t1_digest == v2.original_t1_digest
        and obs.expected_head == 5 and obs.lease_epoch == 1
        and obs.source_id == source.source_id
        and obs.source_revision == source.revision
        and obs.source_digest == FROZEN_SOURCE_HASH
        and obs.exclusion_generation == source.exclusion_generation
        and obs.observer_key_id == "fixture-observer"
        and evid.observer_id == "fixture-observer"
        and evid.tenant_id == tenant and evid.intent_id == v2.intent_id
        and evid.independent and evid.status == "applied"
        and evid.observation_digest == FROZEN_SOURCE_HASH
        and obs.captured_at <= 101 < obs.expires_at,
        "OBSERVER_BINDING_EXPIRED_OR_NOT_APPLIED",
    )
    expected_observer_signature = hmac.new(
        OBSERVER_SECRET, observation_message(obs), hashlib.sha256,
    ).hexdigest()
    require(
        hmac.compare_digest(obs.signature, expected_observer_signature),
        "OBSERVER_MOCK_HMAC_INVALID",
    )
    receipt = v2.terminal_receipt
    mock_terminal = (
        terminal is not None and receipt == terminal
        and terminal.status == "SUCCEEDED"
        and len(events) == 3
        and events[1].kind == "T4_VERIFIED_CONFIRMED_APPLIED"
        and events[1].observation_id == obs.observation_id
        and events[2].kind == "TERMINAL_SUCCEEDED"
        and events[2].observation_id == obs.observation_id
        and terminal.prior_head_seq == 6
        and terminal.head_seq == 7
        and terminal.head_hash == events[2].event_hash
        and terminal.publication.status == "ELIGIBLE_PROPOSAL"
        and terminal.publication.client_delivery_proven
        and terminal.publication.content_sha256 == FROZEN_FRAME_HASH
    )
    require(mock_terminal, "NO_SYNTHETIC_COMMITTED_HEAD7")
    require(
        len(events) < 2 or (
            events[1].observation_id == obs.observation_id
            and events[1].kind == "T4_VERIFIED_CONFIRMED_APPLIED"
        ),
        "NO_MATCHING_T4",
    )
    require(
        signed is not None and signed.key_id == "fixture-verifier-key"
        and signed.signer_id == FIXTURE_ORACLE
        and signed.verification_id == "verification-fixture"
        and signed.tenant_id == tenant
        and signed.task_id == "task-fixture"
        and signed.task_version == 1
        and signed.run_id == run
        and signed.attempt == 1
        and signed.outcome_id == "outcome-fixture"
        and signed.outcome_digest == "b" * 64
        and signed.journal_head_seq == 6
        and len(events) >= 2
        and signed.journal_head_hash == events[1].event_hash
        and signed.lease_epoch == 1
        and signed.checked_at <= 101 < signed.expires_at
        and len(signed.hard_gates) == len(EXPECTED_HARD_GATES)
        and {g.name for g in signed.hard_gates
             if g.result == "pass"} == EXPECTED_HARD_GATES
        and (terminal is None
             or terminal.verification_id == signed.verification_id),
        "VERIFIER_BINDING_OR_HARD_GATE_INVALID",
    )
    if signed is not None:
        expected_verifier_signature = hmac.new(
            VERIFIER_SECRET, verification_message(signed), hashlib.sha256,
        ).hexdigest()
        require(
            hmac.compare_digest(signed.signature, expected_verifier_signature),
            "VERIFIER_MOCK_HMAC_INVALID",
        )
    frames = loop.publication.frames
    substantive = [
        i for i, frame in enumerate(frames)
        if frame.kind == "verified_text" and frame.payload == FROZEN_FRAME_BYTES
        and frame.citation_ids == ("cite-fixture",)
        and frame.verification_id == "verification-fixture"
        and frame.server_emitted and frame.client_ack_id
    ]
    terminal_index = next(
        (i for i, f in enumerate(frames) if f.kind == "terminal"),
        len(frames),
    )
    require(
        bool(substantive) and substantive[0] < terminal_index
        and loop.publication.claim_client_delivered,
        "NO_VERIFIED_CLIENT_ACK_BEFORE_TERMINAL",
    )
    require(
        len(charges) == 1
        and charges[0].charge_id == "charge-fixture"
        and charges[0].amount_microunits == 2
        and not charges[0].late,
        "CHARGE_MISMATCH_OR_DUPLICATE",
    )
    if notice is not None:
        require(
            terminal is not None
            and notice in v2.notices
            and notice.publication_id == loop.publication.publication_id
            and notice.revision == 2 and notice.cursor == 1
            and notice.kind == "correction"
            and notice.supersedes_segment_id == loop.publication.segment_id
            and not notice.run_state_changed
            and terminal == v2.terminal_receipt
            and v2.head == terminal.head_seq,
            "POST_TERMINAL_NOTICE_TAMPER",
        )
    return tuple(faults), original_unknown, mock_terminal


def assess_c02(
    loop: PreparedLoop,
    terminal: TerminalReceipt | None,
    *,
    signed_receipt: VerificationReceipt | None,
    notice: PublicationNotice | None = None,
    charges: tuple[Charge, ...] | None = None,
    evaluator_id: str = FIXTURE_EVALUATOR,
    case_id: str = FIXTURE_ID,
) -> C02Decision:
    """Cross-stage probe; no caller success Boolean, no oracle from outcome_id."""
    if charges is None:
        recorded = loop.kernel.read("run-fixture", "tenant-fixture")["charges"]
        charges = tuple(Charge("attempt-1", key, entry[1])
                        for key, entry in sorted(recorded.items()))
    failures, original_unknown, mock_terminal = _audit(
        loop, terminal, signed_receipt, notice, charges,
    )
    frames = loop.publication.frames
    # C02 has only frame ordering, NOT timestamps or actual transport ACKs.
    # Index-derived values here are synthetic logical offsets exclusively.
    segments = tuple(
        PreterminalSegment(
            kind=("verified_claim" if f.kind == "verified_text" else f.kind),
            payload=f.payload,
            payload_sha256=hashlib.sha256(f.payload).hexdigest(),
            at_ms=1000 + index + 1,
            verified_by=(signed_receipt.signer_id if signed_receipt else ""),
            citation_ids=f.citation_ids,
            client_received=bool(f.client_ack_id),
        )
        for index, f in enumerate(frames)
        if f.kind in ("verified_text", "progress", "terminal")
    )
    first = next(
        (f for f in frames if f.kind == "verified_text"), None,
    )
    digest = hashlib.sha256(first.payload).hexdigest() if first else None
    head = loop.v2.history[-1]
    candidate = OutcomeEvidence(
        case_id=case_id, workload="QA",
        tenant_id=(signed_receipt.tenant_id if signed_receipt else "tenant-fixture"),
        task_id=(signed_receipt.task_id if signed_receipt else "task-fixture"),
        task_version=1, run_id="run-fixture", revision=1,
        journal_head_seq=head.seq, journal_head_sha256=head.event_hash,
        outcome_type="ANSWER",
        terminal_status=("SUCCEEDED" if terminal else "FAILED"),
        # True = SYNTHETIC in-process fixture terminal only.
        # See no_durable=True and authorized_task_success=False below.
        terminal_durable=bool(mock_terminal),
        executor_id=FIXTURE_EXECUTOR,
        evaluator_id=evaluator_id, claimed_oracle_id=FIXTURE_ORACLE,
        observed_digest=digest,
        rights_granted=not failures,
        unknown_effect=not mock_terminal or bool(failures),
        started_ms=1000, terminal_ms=1000 + len(frames) + 1,
        segments=segments, charges=charges,
    )
    # Literal frozen expected bytes are independent of the *submitted*
    # publication/outcome label. This is still only a synthetic T0/T1 catalog.
    oracle = TrustedObservation(
        case_id=case_id, tenant_id="tenant-fixture", task_id="task-fixture",
        task_version=1, run_id="run-fixture", revision=1,
        journal_head_seq=head.seq, journal_head_sha256=head.event_hash,
        oracle_id=FIXTURE_ORACLE, oracle_available=True,
        offline_observer_separate=True, expected_outcome="ANSWER",
        expected_digest=FROZEN_FRAME_HASH, expected_refusal=False,
        verified_segment_sha256=frozenset({FROZEN_FRAME_HASH}),
        source_rights_checked=True,
    )
    decision = evaluate_case(
        candidate, oracle, EvaluationContext(
            evaluator_id=FIXTURE_EVALUATOR, evaluator_version="ar09c-v1",
            approved_oracle_ids=frozenset({FIXTURE_ORACLE}),
            assigned_case_ids=frozenset({case_id}),
        ),
    )
    qualified_mock = (
        not failures and mock_terminal and original_unknown
        and decision.task_success and decision.stream_ok is True
    )
    return C02Decision(
        label=(MOCK_ONLY_FUNCTIONAL_SUCCESS if qualified_mock
               else MOCK_ONLY_REJECTED),
        failures=failures, ar09b=decision, candidate=candidate, oracle=oracle,
        original_nonterminal_unknown=original_unknown,
        mock_terminal_observed=mock_terminal,
    )


def assess_manifest(
    cases: tuple[C02Decision, ...], *,
    assigned_case_ids: frozenset[str],
) -> BatchMetrics:
    """Includes mock denied/failed/UNKNOWN and unreported planned cases."""
    entries = tuple(item.candidate for item in cases)
    catalog = {item.candidate.case_id: item.oracle for item in cases}
    return evaluate_batch(
        entries, catalog,
        EvaluationContext(
            evaluator_id=FIXTURE_EVALUATOR, evaluator_version="ar09c-v1",
            approved_oracle_ids=frozenset({FIXTURE_ORACLE}),
            assigned_case_ids=assigned_case_ids,
        ),
    )
