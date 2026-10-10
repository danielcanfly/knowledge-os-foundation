"""Inert AR02 single-writer contract/fault oracle: NO durable store or dispatch.

Checks desired transaction invariants against caller-supplied immutable mock
snapshots. None of these fixtures authenticates a provider, acquires a lease,
persists a byte, grants a permit, or implements the refused AR02B-R SQLite edit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OutcomePhase = Literal[
    "NONE", "T3_UNKNOWN_EFFECT", "T4_APPLIED", "T4_NOT_APPLIED"
]
CrashPoint = Literal[
    "BEFORE_INTENT_COMMIT",
    "AFTER_INTENT_COMMIT_BEFORE_CLAIM",
    "AFTER_CLAIM_BEFORE_SEND",
    "LOST_COMMIT_ACK_BEFORE_DISPATCH",
    "POST_REMOTE_EFFECT_PRE_OBSERVER",
    "AFTER_OBSERVER_BEFORE_TERMINAL",
]
CRASH_POINTS: tuple[CrashPoint, ...] = (
    "BEFORE_INTENT_COMMIT",
    "AFTER_INTENT_COMMIT_BEFORE_CLAIM",
    "AFTER_CLAIM_BEFORE_SEND",
    "LOST_COMMIT_ACK_BEFORE_DISPATCH",
    "POST_REMOTE_EFFECT_PRE_OBSERVER",
    "AFTER_OBSERVER_BEFORE_TERMINAL",
)


@dataclass(frozen=True, slots=True)
class TransactionIntentContract:
    """Required T1/RunEvent/budget binding, not an executable intent."""

    tenant_id: str
    run_id: str
    task_id: str
    task_version: int
    attempt: int
    intent_id: str
    intent_digest: str
    approval_id: str
    expected_head: int
    lease_epoch: int
    reserve_id: str
    reserved_microunits: int
    charge_id: str
    charged_microunits: int | None
    claim_id: str
    idempotency_key: str
    consent_generation: int
    exclusion_generation: int
    source_revision: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class WriterSnapshotFixture:
    """Test input only. No source of truth, persistence or authenticated CAS."""

    tenant_id: str
    run_id: str
    task_id: str
    task_version: int
    head: int
    head_hash: str
    epoch: int
    budget_microunits: int
    spent_microunits: int
    reservations: tuple[tuple[str, int], ...]
    charges: tuple[tuple[str, str, int], ...]
    intents: tuple[tuple[str, str, str], ...]
    claims: tuple[tuple[str, str, int, str], ...]
    unknown_effects: tuple[str, ...]
    outcome_phase: OutcomePhase
    source_revision: str
    consent_generation: int
    exclusion_generation: int
    source_revoked: bool
    terminal: bool


@dataclass(frozen=True, slots=True)
class OutboxClaimContract:
    """Required T1/T2/dispatch-ACK snapshot; booleans are NOT verified ACKs."""

    claim_id: str
    intent_id: str
    intent_digest: str
    expected_head: int
    lease_epoch: int
    idempotency_key: str
    intent_commit_ack: bool
    claim_commit_ack: bool
    attempt_marked_in_journal: bool


@dataclass(frozen=True, slots=True)
class DurabilityObligation:
    """Normative API obligations. True says REQUIRED, never IMPLEMENTED."""

    one_authoritative_ar02_writer: bool = True
    serializable_event_budget_permit_outbox_commit: bool = True
    atomic_t4_verification_terminal_head_cas: bool = True
    durable_commit_ack_fence_before_dispatch: bool = True
    crash_safe_outbox_and_replay_fencing: bool = True
    independent_observer_and_verifier: bool = True
    no_blind_remote_retry_on_unknown: bool = True
    native_source_consent_revocation_freshness: bool = True


@dataclass(frozen=True, slots=True)
class ReconciliationObligation:
    """Observed T4 details, fixture-asserted NOT attested by this module."""

    tenant_id: str
    run_id: str
    task_id: str
    task_version: int
    observation_id: str
    observed_status: Literal["CONFIRMED_APPLIED", "CONFIRMED_NOT_APPLIED"]
    independent_observer: bool
    verified_head: int
    verified_head_hash: str
    lease_epoch: int
    expires_at: int
    binding_intent_id: str
    original_t1_digest: str


@dataclass(frozen=True, slots=True)
class ContractDecision:
    issues: tuple[str, ...]
    mock_policy_contract_pass: bool
    durability_obligations: DurabilityObligation
    requires_independent_t4: bool = True
    durable_verified: bool = False
    backend_writer_present: bool = False
    provider_dispatch_authorized: bool = False
    AR02_STAGE_DONE: bool = False


@dataclass(frozen=True, slots=True)
class CrashPointResult:
    point: CrashPoint
    next_step: str
    effect_state: Literal["NOT_DISPATCHED", "T3_UNKNOWN_EFFECT", "T4_PENDING_CAS"]
    original_charge_count: int
    may_dispatch: bool = False
    double_charge_allowed: bool = False
    durable_verified: bool = False
    backend_writer_present: bool = False
    provider_dispatch_authorized: bool = False
    AR02_STAGE_DONE: bool = False


def _duplicate_first_field(items: tuple[tuple, ...]) -> bool:
    return len({row[0] for row in items}) != len(items)


def assess_contract(
    intent: TransactionIntentContract,
    state: WriterSnapshotFixture,
    claim: OutboxClaimContract,
    proof: ReconciliationObligation,
    *,
    now: int,
) -> ContractDecision:
    """Pure, fail-closed fixture contract inspection; NO dispatch decision API."""
    issues: list[str] = []

    def deny(when: bool, reason: str) -> None:
        if when and reason not in issues:
            issues.append(reason)

    deny(
        not intent.tenant_id or not intent.run_id
        or (intent.tenant_id, intent.run_id) != (state.tenant_id, state.run_id)
        or (proof.tenant_id, proof.run_id) != (state.tenant_id, state.run_id),
        "TENANT_RUN_BINDING",
    )
    deny(intent.task_id != state.task_id or proof.task_id != state.task_id,
         "TASK_ID_MISMATCH")
    deny(
        intent.task_version != state.task_version
        or proof.task_version != state.task_version or intent.task_version < 1,
        "TASK_VERSION_MISMATCH",
    )
    deny(intent.attempt < 1, "INVALID_ATTEMPT")
    deny(intent.expected_head != state.head or claim.expected_head != state.head,
         "STALE_CAS_HEAD")
    deny(
        intent.lease_epoch != state.epoch or claim.lease_epoch != state.epoch
        or proof.lease_epoch != state.epoch or state.epoch < 1,
        "STALE_LEASE_EPOCH",
    )
    deny(
        not intent.intent_digest
        or (intent.intent_id, intent.intent_digest, intent.approval_id)
        not in state.intents or claim.intent_digest != intent.intent_digest
        or proof.original_t1_digest != intent.intent_digest,
        "INTENT_DIGEST_MISMATCH",
    )
    deny(
        not intent.intent_id or not intent.approval_id
        or (intent.intent_id, intent.intent_digest, intent.approval_id)
        not in state.intents,
        "MISSING_COMMITTED_INTENT",
    )
    deny(_duplicate_first_field(state.intents), "DUPLICATE_INTENT")
    deny(
        not intent.claim_id or not claim.claim_id
        or claim.claim_id != intent.claim_id
        or claim.intent_id != intent.intent_id
        or claim.idempotency_key != intent.idempotency_key,
        "CLAIM_BINDING_MISMATCH",
    )
    deny(
        (claim.claim_id, intent.intent_id, state.epoch, intent.idempotency_key)
        not in state.claims, "MISSING_COMMITTED_CLAIM",
    )
    deny(_duplicate_first_field(state.claims), "DUPLICATE_CLAIM")
    deny(
        not claim.intent_commit_ack or not claim.claim_commit_ack,
        "MISSING_DURABLE_ACK",
    )
    deny(not claim.attempt_marked_in_journal, "NO_COMMITTED_ATTEMPT_MARKER")
    deny(
        type(intent.reserved_microunits) is not int
        or intent.reserved_microunits < 0
        or type(intent.charged_microunits) is not int
        or intent.charged_microunits < 0,
        "INVALID_COST",
    )
    deny(
        type(intent.charged_microunits) is int
        and type(intent.reserved_microunits) is int
        and intent.charged_microunits > intent.reserved_microunits,
        "CHARGE_EXCEEDS_RESERVATION",
    )
    deny(
        (intent.charge_id, intent.reserve_id, intent.charged_microunits)
        not in state.charges or not intent.charge_id,
        "MISSING_OR_CONFLICTING_CHARGE",
    )
    deny(_duplicate_first_field(state.charges), "DUPLICATE_CHARGE")
    deny(_duplicate_first_field(state.reservations), "DUPLICATE_RESERVATION")
    deny(
        type(state.budget_microunits) is not int
        or type(state.spent_microunits) is not int
        or state.budget_microunits < 0
        or state.spent_microunits < 0
        or any(type(value) is not int or value < 0 for _, value in state.reservations)
        or state.spent_microunits + sum(
            value for _, value in state.reservations
            if type(value) is int
        ) > state.budget_microunits,
        "BUDGET_OVERCOMMITTED",
    )
    deny(intent.expires_at <= now, "EXPIRED_INTENT")
    deny(state.source_revoked, "REVOKED_SOURCE")
    deny(intent.exclusion_generation != state.exclusion_generation,
         "EXCLUSION_DRIFT")
    deny(intent.consent_generation != state.consent_generation,
         "CONSENT_GENERATION_DRIFT")
    deny(intent.source_revision != state.source_revision, "SOURCE_REVISION_DRIFT")
    deny(state.terminal, "TERMINAL_IMMUTABLE")
    deny(
        state.outcome_phase == "T3_UNKNOWN_EFFECT" or bool(state.unknown_effects),
        "UNKNOWN_EFFECT_NOT_T4",
    )
    deny(
        state.outcome_phase != "T4_APPLIED"
        or proof.observed_status != "CONFIRMED_APPLIED",
        "NO_SUCCESS_WITHOUT_APPLIED",
    )
    deny(
        not proof.independent_observer or not proof.observation_id
        or proof.binding_intent_id != intent.intent_id,
        "UNVERIFIED_T4",
    )
    deny(proof.expires_at <= now, "EXPIRED_RECONCILIATION_PROOF")
    deny(
        proof.verified_head != state.head
        or proof.verified_head_hash != state.head_hash
        or len(state.head_hash) != 64,
        "FORGED_OR_STALE_HEAD",
    )
    return ContractDecision(
        issues=tuple(issues), mock_policy_contract_pass=not issues,
        durability_obligations=DurabilityObligation(),
    )


def assess_crash(
    point: CrashPoint, *, original_charge_count: int = 0,
) -> CrashPointResult:
    """Adversarial expected recovery; no action is executed or authorized."""
    if type(original_charge_count) is not int or original_charge_count < 0:
        raise ValueError("invalid original charge count")
    scenario: dict[CrashPoint, tuple[str, str]] = {
        "BEFORE_INTENT_COMMIT": (
            "NOT_DISPATCHED", "DENY_UNCOMMITTED_INTENT_AND_ROLL_BACK",
        ),
        "AFTER_INTENT_COMMIT_BEFORE_CLAIM": (
            "NOT_DISPATCHED", "RELOAD_HEAD_AND_REEVALUATE_CLAIM",
        ),
        "AFTER_CLAIM_BEFORE_SEND": (
            "NOT_DISPATCHED", "REVALIDATE_ACK_LEASE_AND_ATTEMPT_NO_AUTO_SEND",
        ),
        "LOST_COMMIT_ACK_BEFORE_DISPATCH": (
            "NOT_DISPATCHED", "DENY_AND_REVALIDATE_DURABLE_COMMIT",
        ),
        "POST_REMOTE_EFFECT_PRE_OBSERVER": (
            "T3_UNKNOWN_EFFECT", "INDEPENDENT_T4_RECONCILIATION_NO_RETRY",
        ),
        "AFTER_OBSERVER_BEFORE_TERMINAL": (
            "T4_PENDING_CAS", "REVERIFY_T4_CURRENT_HEAD_THEN_TERMINAL_CAS",
        ),
    }
    if point not in scenario:
        raise ValueError("unknown crash point")
    state, next_step = scenario[point]
    return CrashPointResult(
        point=point, next_step=next_step, effect_state=state,
        original_charge_count=original_charge_count,
    )


def minimal_durable_writer_api() -> tuple[str, ...]:
    """Contractual next-package method surface ONLY, not implemented here."""
    return (
        "begin_serializable_run_transaction",
        "compare_and_append_event_head",
        "atomic_reserve_charge_intent_claim",
        "verify_durable_commit_ack_before_dispatch",
        "recover_pending_outbox_without_blind_redispatch",
        "commit_t4_and_terminal_with_head_cas",
        "query_revocation_consent_and_source_revision",
        "seal_immutable_terminal_and_sidecar_notice",
    )
