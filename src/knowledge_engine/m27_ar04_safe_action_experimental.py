"""Feature-off, in-memory AR04 action handshake used by synthetic tests only.

The types in this module are experimental sidecars.  They do not modify the
frozen AR01D wire records, persist an AR02 journal, or dispatch a provider.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

Effect = Literal[
    "NOT_DISPATCHED",
    "POSSIBLY_SENT",
    "CONFIRMED_APPLIED",
    "CONFIRMED_NOT_APPLIED",
    "UNKNOWN_EFFECT",
]


class ActionDenied(ValueError):
    """Fail-closed denial at a named handshake stage."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """Immutable local representation of the frozen AR01D ActionIntent fields."""

    intent_id: str
    run_id: str
    tenant_id: str
    principal_id: str
    delegated_by: str | None
    capability_id: str
    capability_version: str
    operation: str
    resource_id: str
    arguments_ref: str
    arguments_digest: str
    idempotency_key: str
    side_effect: str
    approval_id: str
    requested_at: int
    expires_at: int
    policy_version: str
    lease_epoch: int
    attempt: int

    def digest(self) -> str:
        payload = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyFixture:
    """Externally supplied fake policy facts; labels alone confer no authority."""

    issuer: str
    tenant_id: str
    principal_id: str
    delegated_by: str | None
    auth_expires_at: int
    allowed_capabilities: frozenset[str]
    allowed_resources: frozenset[str]
    lease_epoch: int
    budget_cap_microunits: int
    price_microunits: int | None


@dataclass(frozen=True, slots=True)
class ApprovalFixture:
    approval_id: str
    intent_digest: str
    tenant_id: str
    approver_principal: str
    issuer: str
    expires_at: int
    one_time: bool = True


@dataclass(frozen=True, slots=True)
class IntentCandidate:
    """T1 result: a fake durable-intent candidate, not a durable AR02 commit."""

    command_id: str
    intent: ActionIntent
    intent_digest: str
    stage: Literal["T1_INTENT_CANDIDATE"] = "T1_INTENT_CANDIDATE"


@dataclass(frozen=True, slots=True)
class DispatchClaim:
    """T2 result: a single-use, lease-fenced mock outbox claim."""

    claim_id: str
    intent_id: str
    intent_digest: str
    lease_epoch: int
    physical_attempt: int
    stage: Literal["T2_FENCED_CLAIM"] = "T2_FENCED_CLAIM"


@dataclass(frozen=True, slots=True)
class SendBoundary:
    """T3 marker. Crossing it means possibly sent; this module never sends."""

    claim_id: str
    intent_id: str
    effect: Literal["POSSIBLY_SENT"] = "POSSIBLY_SENT"
    stage: Literal["T3_SEND_MAY_HAVE_STARTED"] = "T3_SEND_MAY_HAVE_STARTED"


@dataclass(frozen=True, slots=True)
class ObserverEvidence:
    """T4 evidence supplied by a separately configured synthetic observer."""

    observer_id: str
    tenant_id: str
    intent_id: str
    resource_id: str
    status: Literal["applied", "not_applied", "absent_uncertain"]
    observation_digest: str
    independent: bool
    authoritative_negative: bool = False
    visibility_complete: bool = False


@dataclass(frozen=True, slots=True)
class Reconciliation:
    intent_id: str
    effect: Effect
    observer_id: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class VerificationProposal:
    """T5 proposal only; AR02 would own any terminal commit."""

    intent_id: str
    effect: Effect
    verifier_id: str
    verifier_key_id: str
    terminal_committed: bool = False
    stage: Literal["T5_VERIFICATION_PROPOSAL"] = "T5_VERIFICATION_PROPOSAL"


class InertSafeActionBoundary:
    """Deterministic mock T1-T5 state machine with zero dispatch capability."""

    def __init__(
        self,
        *,
        trusted_policy_issuer: str,
        trusted_approval_issuers: frozenset[str],
        trusted_observers: frozenset[str],
        trusted_verifier_keys: frozenset[str],
        executor_id: str = "ar04-executor",
    ) -> None:
        self._trusted_policy_issuer = trusted_policy_issuer
        self._trusted_approval_issuers = trusted_approval_issuers
        self._trusted_observers = trusted_observers
        self._trusted_verifier_keys = trusted_verifier_keys
        self._executor_id = executor_id
        self._candidates: dict[str, IntentCandidate] = {}
        self._commands: dict[str, str] = {}
        self._keys: dict[tuple[str, str], str] = {}
        self._claims: dict[str, DispatchClaim] = {}
        self._claims_by_intent: dict[str, str] = {}
        self._consumed_claims: set[str] = set()
        self._consumed_approvals: set[str] = set()
        self._cancelled: set[str] = set()
        self._reconciliations: dict[str, Reconciliation] = {}

    @property
    def provider_calls(self) -> int:
        """The experimental boundary has no provider adapter by construction."""

        return 0

    def register_intent(
        self,
        *,
        command_id: str,
        intent: ActionIntent,
        policy: PolicyFixture,
        now: int,
    ) -> IntentCandidate:
        """T1 validates immutable identity/scope/budget and records a candidate."""

        digest = intent.digest()
        previous = self._commands.get(command_id)
        if previous is not None:
            if previous != digest:
                raise ActionDenied("T1_COMMAND_DIGEST_CONFLICT")
            return self._candidates[intent.intent_id]
        if intent.intent_id in self._candidates:
            raise ActionDenied("T1_INTENT_ID_CONFLICT")
        if policy.issuer != self._trusted_policy_issuer:
            raise ActionDenied("T1_UNTRUSTED_POLICY_ISSUER")
        if (intent.tenant_id, intent.principal_id, intent.delegated_by) != (
            policy.tenant_id,
            policy.principal_id,
            policy.delegated_by,
        ):
            raise ActionDenied("T1_IDENTITY_OR_DELEGATION_MISMATCH")
        if now >= policy.auth_expires_at or now >= intent.expires_at:
            raise ActionDenied("T1_AUTH_OR_INTENT_EXPIRED")
        if intent.capability_id not in policy.allowed_capabilities:
            raise ActionDenied("T1_CAPABILITY_DENIED")
        if intent.resource_id not in policy.allowed_resources:
            raise ActionDenied("T1_RESOURCE_SCOPE_DENIED")
        if intent.lease_epoch != policy.lease_epoch:
            raise ActionDenied("T1_STALE_EPOCH")
        if policy.price_microunits is None:
            raise ActionDenied("T1_PRICE_UNKNOWN")
        if policy.price_microunits > policy.budget_cap_microunits:
            raise ActionDenied("T1_BUDGET_DENIED")
        key = (intent.tenant_id, intent.idempotency_key)
        prior_key_digest = self._keys.get(key)
        if prior_key_digest is not None and prior_key_digest != digest:
            raise ActionDenied("T1_IDEMPOTENCY_DIGEST_CONFLICT")
        candidate = IntentCandidate(command_id, intent, digest)
        self._candidates[intent.intent_id] = candidate
        self._commands[command_id] = digest
        self._keys[key] = digest
        return candidate

    def claim_dispatch(
        self,
        *,
        intent_id: str,
        claim_id: str,
        approval: ApprovalFixture,
        expected_epoch: int,
        physical_attempt: int,
        now: int,
    ) -> DispatchClaim:
        """T2 consumes one exact approval and produces one fenced claim."""

        candidate = self._candidate(intent_id)
        intent = candidate.intent
        if intent_id in self._cancelled:
            raise ActionDenied("T2_CANCELLED")
        if expected_epoch != intent.lease_epoch:
            raise ActionDenied("T2_STALE_EPOCH")
        if claim_id in self._claims or intent_id in self._claims_by_intent:
            raise ActionDenied("T2_CLAIM_ALREADY_EXISTS")
        if approval.issuer not in self._trusted_approval_issuers:
            raise ActionDenied("T2_UNTRUSTED_APPROVAL_ISSUER")
        if approval.approval_id != intent.approval_id:
            raise ActionDenied("T2_APPROVAL_ID_MISMATCH")
        if approval.tenant_id != intent.tenant_id:
            raise ActionDenied("T2_APPROVAL_TENANT_MISMATCH")
        if approval.intent_digest != candidate.intent_digest:
            raise ActionDenied("T2_APPROVAL_DIGEST_MISMATCH")
        if now >= approval.expires_at:
            raise ActionDenied("T2_APPROVAL_EXPIRED")
        if approval.one_time and approval.approval_id in self._consumed_approvals:
            raise ActionDenied("T2_APPROVAL_CONSUMED")
        claim = DispatchClaim(
            claim_id=claim_id,
            intent_id=intent_id,
            intent_digest=candidate.intent_digest,
            lease_epoch=expected_epoch,
            physical_attempt=physical_attempt,
        )
        self._claims[claim_id] = claim
        self._claims_by_intent[intent_id] = claim_id
        if approval.one_time:
            self._consumed_approvals.add(approval.approval_id)
        return claim

    def cross_send_boundary(
        self, *, claim_id: str, current_epoch: int
    ) -> SendBoundary:
        """T3 consumes a claim without performing any network or provider call."""

        claim = self._claims.get(claim_id)
        if claim is None:
            raise ActionDenied("T3_UNKNOWN_CLAIM")
        if claim_id in self._consumed_claims:
            raise ActionDenied("T3_CLAIM_CONSUMED")
        if claim.intent_id in self._cancelled:
            raise ActionDenied("T3_CANCELLED")
        if current_epoch != claim.lease_epoch:
            raise ActionDenied("T3_STALE_EPOCH")
        self._consumed_claims.add(claim_id)
        return SendBoundary(claim_id=claim_id, intent_id=claim.intent_id)

    def cancel(self, intent_id: str) -> Reconciliation:
        """Cancellation halts new T3 but never proves a crossed boundary had no effect."""

        self._candidate(intent_id)
        self._cancelled.add(intent_id)
        claim_id = self._claims_by_intent.get(intent_id)
        crossed = claim_id is not None and claim_id in self._consumed_claims
        effect: Effect = "UNKNOWN_EFFECT" if crossed else "NOT_DISPATCHED"
        return Reconciliation(intent_id, effect, None, "cancel_does_not_imply_undo")

    def reconcile(
        self,
        *,
        evidence: ObserverEvidence,
        executor_claimed_applied: bool = False,
    ) -> Reconciliation:
        """T4 trusts only separately configured observer evidence, never executor text."""

        del executor_claimed_applied
        candidate = self._candidate(evidence.intent_id)
        if (
            evidence.observer_id not in self._trusted_observers
            or not evidence.independent
            or evidence.tenant_id != candidate.intent.tenant_id
            or evidence.resource_id != candidate.intent.resource_id
        ):
            result = Reconciliation(
                evidence.intent_id,
                "UNKNOWN_EFFECT",
                evidence.observer_id,
                "observer_untrusted_or_binding_mismatch",
            )
        elif evidence.status == "applied":
            result = Reconciliation(
                evidence.intent_id,
                "CONFIRMED_APPLIED",
                evidence.observer_id,
                "independent_observer_applied",
            )
        elif (
            evidence.status == "not_applied"
            and evidence.authoritative_negative
            and evidence.visibility_complete
        ):
            result = Reconciliation(
                evidence.intent_id,
                "CONFIRMED_NOT_APPLIED",
                evidence.observer_id,
                "authoritative_negative_proof",
            )
        else:
            result = Reconciliation(
                evidence.intent_id,
                "UNKNOWN_EFFECT",
                evidence.observer_id,
                "absence_or_negative_proof_uncertain",
            )
        self._reconciliations[evidence.intent_id] = result
        return result

    def authorize_retry(self, *, intent_id: str, idempotency_mode: str) -> bool:
        """Unknown/non-idempotent effects are never blindly retried."""

        result = self._reconciliations.get(intent_id)
        if result is None or result.effect != "CONFIRMED_NOT_APPLIED":
            raise ActionDenied("RETRY_EFFECT_NOT_NEGATIVELY_PROVEN")
        if idempotency_mode not in {"provider_enforced", "read_reconcile"}:
            raise ActionDenied("RETRY_NONIDEMPOTENT_DENIED")
        return True

    def compensation_result(
        self, *, intent_id: str, observer_verified_restored: bool
    ) -> str:
        """An accepted compensation call is not restoration proof."""

        self._candidate(intent_id)
        return "COMPENSATED" if observer_verified_restored else "COMPENSATION_UNVERIFIED"

    def propose_verification(
        self,
        *,
        intent_id: str,
        verifier_id: str,
        verifier_key_id: str,
    ) -> VerificationProposal:
        """T5 emits a nonterminal proposal only from an independently trusted verifier."""

        self._candidate(intent_id)
        if verifier_id == self._executor_id or verifier_key_id not in self._trusted_verifier_keys:
            raise ActionDenied("T5_FORGED_OR_SELF_VERIFIER")
        result = self._reconciliations.get(intent_id)
        effect: Effect = result.effect if result is not None else "UNKNOWN_EFFECT"
        return VerificationProposal(intent_id, effect, verifier_id, verifier_key_id)

    def recovery_effect(self, intent_id: str) -> Effect:
        """Classify crash cut points without inferring provider outcome."""

        self._candidate(intent_id)
        claim_id = self._claims_by_intent.get(intent_id)
        if claim_id is None or claim_id not in self._consumed_claims:
            return "NOT_DISPATCHED"
        return "UNKNOWN_EFFECT"

    def _candidate(self, intent_id: str) -> IntentCandidate:
        candidate = self._candidates.get(intent_id)
        if candidate is None:
            raise ActionDenied("UNKNOWN_INTENT")
        return candidate
