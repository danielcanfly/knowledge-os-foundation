"""K04P: fixture-only, feature-off permit policy and effect boundary.

Local component, not an OS sandbox, AR02 durable writer, issuer or provider adapter.
No network, subprocess, filesystem mutation, or production dispatch is implemented.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

SANDBOX_BOUNDARY_LOCAL_COMPONENT_ONLY = True
FEATURE_ENABLED = False
REAL_DISPATCH_AUTHORIZED = False
CONTRACT_VERSION = "PermitSandboxV1"


class Denied(ValueError):
    """Typed, fail-closed denial; not an external authorization verdict."""

    def __init__(self, stage: str, code: str):
        self.stage = stage
        self.code = code
        super().__init__(f"{stage}:{code}")


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _safe_namespace(path: str) -> bool:
    """Byte-conservative namespace: no traversal, normalization or encoded escapes."""
    return (
        path.startswith("/")
        and not path.endswith("/")
        and "//" not in path
        and "\\" not in path
        and "%" not in path
        and all(part not in ("", ".", "..") for part in path[1:].split("/"))
        and all(32 <= ord(ch) < 127 for ch in path)
    )


@dataclass(frozen=True, slots=True)
class CapabilityRule:
    capability_id: str
    version: str
    operation: str
    namespace_prefix: str
    executor_adapter_id: str
    max_cost: int


@dataclass(frozen=True, slots=True)
class Registry:
    policy_issuer: str
    approval_issuers: frozenset[str]
    observer_issuers: frozenset[str]
    writer_issuer: str
    fake_adapter_ids: frozenset[str]
    rules: tuple[CapabilityRule, ...]
    feature_enabled: bool = False
    real_dispatch_authorized: bool = False


@dataclass(frozen=True, slots=True)
class ActionRequest:
    request_id: str
    run_id: str
    tenant_id: str
    actor_id: str
    delegated_by: str | None
    capability_id: str
    capability_version: str
    operation: str
    resource_id: str
    recipient_id: str
    arguments_digest: str
    idempotency_key: str
    intent_version: str
    lease_epoch: int

    def digest(self) -> str:
        return _digest({"domain": "k04p.intent.v1", "body": asdict(self)})


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    run_id: str
    tenant_id: str
    actor_id: str
    delegated_by: str | None
    worker_id: str
    lease_epoch: int
    lease_until: int
    consent_until: int
    consent_generation: int
    revocation_generation: int
    head_hash: str
    budget_available: int
    issuer: str


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approval_id: str
    issuer: str
    approved: bool
    intent_digest: str
    intent_version: str
    run_id: str
    tenant_id: str
    lease_epoch: int
    consent_generation: int
    revocation_generation: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class Permit:
    permit_id: str
    request: ActionRequest
    intent_digest: str
    approval_id: str
    approval_issuer: str
    worker_id: str
    frozen_head_hash: str
    consent_generation: int
    revocation_generation: int
    expires_at: int
    quoted_cost: int
    issuer: str
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class DurableWriterReceipt:
    """Required typed AR02 seam. Synthetic port never grants durable authority."""

    writer_issuer: str
    claim_id: str
    permit_id: str
    intent_digest: str
    run_id: str
    tenant_id: str
    worker_id: str
    lease_epoch: int
    expected_head_hash: str
    outbox_ack: str | None
    durable_verified: bool
    mock_only: bool


@dataclass(frozen=True, slots=True)
class DispatchClaim:
    claim_id: str
    permit: Permit
    writer_receipt: DurableWriterReceipt
    sender_id: str
    physical_attempt: int


@dataclass(frozen=True, slots=True)
class MockAttempt:
    claim_id: str
    intent_digest: str
    adapter_id: str
    provider_receipt_id: str | None
    synthetic_effect: Literal["applied", "not_applied", "unknown"]
    status: Literal["SIMULATED_NOT_DISPATCHED"] = "SIMULATED_NOT_DISPATCHED"


@dataclass(frozen=True, slots=True)
class ObservedEffect:
    claim_id: str
    tenant_id: str
    resource_id: str
    intent_digest: str
    observer_id: str
    observer_issuer: str
    observer_grant_id: str
    effect: Literal["applied", "not_applied", "absent_uncertain"]
    visibility_complete: bool
    source_revision: str
    citation_ids: tuple[str, ...] = ()
    evidence_grade: Literal["FIXTURE_ONLY"] = "FIXTURE_ONLY"


@dataclass(frozen=True, slots=True)
class ReconciledOutcome:
    claim_id: str
    state: Literal[
        "CONFIRMED_APPLIED_FIXTURE",
        "CONFIRMED_NOT_APPLIED_FIXTURE",
        "UNKNOWN_EFFECT",
    ]
    terminal_authorized: bool = False
    provider_calls: int = 0


class WriterPort(Protocol):
    def prepare_claim(self, permit: Permit, claim_id: str) -> DurableWriterReceipt: ...


class MockWriterPort:
    """Explicitly nondurable adapter; cannot ACK an outbox or permit a real T3."""

    def prepare_claim(self, permit: Permit, claim_id: str) -> DurableWriterReceipt:
        req = permit.request
        return DurableWriterReceipt(
            "fixture-ar02", claim_id, permit.permit_id, permit.intent_digest, req.run_id,
            req.tenant_id, permit.worker_id, req.lease_epoch, permit.frozen_head_hash,
            None, False, True,
        )


class InProcessFixtureObserver:
    """Independent instance/identity from fake executor; evidence is never production grade."""

    def __init__(self, observer_id: str, issuer: str, grant_id: str):
        self.observer_id = observer_id
        self.issuer = issuer
        self.grant_id = grant_id

    def observe(
        self, claim: DispatchClaim, *, effect: Literal[
            "applied", "not_applied", "absent_uncertain"
        ], visibility_complete: bool = True, source_revision: str = "synthetic-r1",
        citation_ids: tuple[str, ...] = (),
    ) -> ObservedEffect:
        return ObservedEffect(
            claim.claim_id, claim.permit.request.tenant_id,
            claim.permit.request.resource_id, claim.permit.intent_digest,
            self.observer_id, self.issuer, self.grant_id, effect, visibility_complete,
            source_revision, citation_ids,
        )


class PermitSandboxV1:
    """No external executor: policy validates, fixture simulates, real dispatch always denies."""

    def __init__(self, registry: Registry, writer: WriterPort):
        self._registry = registry
        self._writer = writer
        self._requests: dict[str, ActionRequest] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._permits: dict[str, Permit] = {}
        self._consumed_approvals: set[str] = set()
        self._claims: dict[str, DispatchClaim] = {}
        self._claimed_permits: set[str] = set()
        self._attempted_claims: set[str] = set()
        self._outcomes: dict[str, ReconciledOutcome] = {}
        self._rules = self.compile_policy(registry)

    @staticmethod
    def compile_policy(registry: Registry) -> dict[tuple[str, str, str], CapabilityRule]:
        if registry.feature_enabled or registry.real_dispatch_authorized:
            raise Denied("COMPILE", "FEATURE_MUST_REMAIN_OFF")
        if not registry.policy_issuer or not registry.writer_issuer:
            raise Denied("COMPILE", "MISSING_TRUST_REGISTRY")
        result = {}
        for rule in registry.rules:
            key = (rule.capability_id, rule.version, rule.operation)
            prefix = rule.namespace_prefix
            if (
                key in result or any(not x or x == "*" for x in key)
                or rule.max_cost <= 0 or not _safe_namespace(prefix + "item")
                or not prefix.endswith("/")
                or rule.executor_adapter_id not in registry.fake_adapter_ids
            ):
                raise Denied("COMPILE", "INVALID_OR_DUPLICATE_RULE")
            result[key] = rule
        if not result:
            raise Denied("COMPILE", "EMPTY_POLICY")
        return result

    def _fresh(
        self, request: ActionRequest, snapshot: AuthoritySnapshot, now: int,
        worker_id: str,
    ) -> None:
        if snapshot.issuer != self._registry.policy_issuer:
            raise Denied("AUTH", "POLICY_ISSUER")
        if (request.run_id, request.tenant_id, request.actor_id, request.delegated_by) != (
            snapshot.run_id, snapshot.tenant_id, snapshot.actor_id, snapshot.delegated_by
        ):
            raise Denied("AUTH", "WRONG_EFFECTIVE_PRINCIPAL")
        if worker_id != snapshot.worker_id:
            raise Denied("AUTH", "SPLIT_BRAIN_WORKER")
        if request.lease_epoch != snapshot.lease_epoch or now >= snapshot.lease_until:
            raise Denied("AUTH", "LEASE_STALE")
        if now >= snapshot.consent_until or snapshot.revocation_generation != 0:
            raise Denied("AUTH", "CONSENT_REVOKED_OR_EXPIRED")
        if snapshot.consent_generation < 1 or snapshot.budget_available <= 0:
            raise Denied("AUTH", "CONSENT_OR_BUDGET_MISSING")
        if not snapshot.head_hash:
            raise Denied("AUTH", "HEAD_MISSING")

    def request(
        self, request: ActionRequest, snapshot: AuthoritySnapshot, *, now: int
    ) -> str:
        self._fresh(request, snapshot, now, snapshot.worker_id)
        rule = self._rules.get((
            request.capability_id, request.capability_version, request.operation
        ))
        if rule is None:
            raise Denied("T1", "UNMAPPED_OPERATION")
        if (
            not _safe_namespace(request.resource_id)
            or not request.resource_id.startswith(rule.namespace_prefix)
            or request.tenant_id not in request.resource_id.split("/")
        ):
            raise Denied("T1", "RESOURCE_SCOPE_ESCAPE")
        if (
            not request.arguments_digest or not request.recipient_id
            or not request.intent_version or not request.idempotency_key
        ):
            raise Denied("T1", "INVALID_INTENT")
        digest = request.digest()
        prior = self._requests.get(request.request_id)
        if prior is not None:
            if prior != request:
                raise Denied("T1", "REQUEST_CONFLICT")
            return digest
        key = (request.tenant_id, request.idempotency_key)
        if key in self._idempotency:
            raise Denied("T1", "REUSED_IDEMPOTENCY_KEY")
        self._requests[request.request_id] = request
        self._idempotency[key] = digest
        return digest

    def issue_permit(
        self, request_id: str, decision: ApprovalDecision, snapshot: AuthoritySnapshot,
        *, now: int, quoted_cost: int,
    ) -> Permit:
        request = self._requests.get(request_id)
        if request is None:
            raise Denied("T2", "UNKNOWN_REQUEST")
        self._fresh(request, snapshot, now, snapshot.worker_id)
        rule = self._rules[(
            request.capability_id, request.capability_version, request.operation
        )]
        if (
            decision.issuer not in self._registry.approval_issuers or not decision.approved
            or decision.approval_id in self._consumed_approvals
        ):
            raise Denied("T2", "UNTRUSTED_OR_REUSED_APPROVAL")
        if (
            decision.intent_digest != request.digest()
            or decision.intent_version != request.intent_version
            or decision.run_id != request.run_id or decision.tenant_id != request.tenant_id
            or decision.lease_epoch != request.lease_epoch
            or decision.consent_generation != snapshot.consent_generation
            or decision.revocation_generation != snapshot.revocation_generation
            or now >= decision.expires_at
        ):
            raise Denied("T2", "APPROVAL_BINDING_OR_EXPIRY")
        if (
            quoted_cost <= 0
            or quoted_cost > rule.max_cost
            or quoted_cost > snapshot.budget_available
        ):
            raise Denied("T2", "BUDGET_DENIED")
        permit = Permit(
            _digest({"approval_id": decision.approval_id, "intent": request.digest()}),
            request, request.digest(), decision.approval_id, decision.issuer,
            snapshot.worker_id, snapshot.head_hash, snapshot.consent_generation,
            snapshot.revocation_generation, min(decision.expires_at, snapshot.consent_until),
            quoted_cost, self._registry.policy_issuer,
        )
        self._permits[permit.permit_id] = permit
        self._consumed_approvals.add(decision.approval_id)
        return permit

    def freeze_claim(
        self, permit: Permit, snapshot: AuthoritySnapshot, *, claim_id: str,
        sender_id: str, physical_attempt: int, now: int,
    ) -> DispatchClaim:
        req = permit.request
        self._fresh(req, snapshot, now, sender_id)
        if (
            self._permits.get(permit.permit_id) != permit
            or permit.intent_digest != req.digest() or now >= permit.expires_at
            or permit.worker_id != sender_id or snapshot.head_hash != permit.frozen_head_hash
            or permit.consent_generation != snapshot.consent_generation
            or permit.revocation_generation != snapshot.revocation_generation
        ):
            raise Denied("CLAIM", "PERMIT_STALE_OR_MUTATED")
        if (
            permit.permit_id in self._claimed_permits
            or claim_id in self._claims or physical_attempt != 1 or not claim_id
        ):
            raise Denied("CLAIM", "DUPLICATE_OR_INVALID_CLAIM")
        receipt = self._writer.prepare_claim(permit, claim_id)
        if not isinstance(receipt, DurableWriterReceipt):
            raise Denied("CLAIM", "WRITER_RECEIPT_TYPE")
        if (
            receipt.claim_id != claim_id or receipt.permit_id != permit.permit_id
            or receipt.intent_digest != permit.intent_digest
            or receipt.run_id != req.run_id or receipt.tenant_id != req.tenant_id
            or receipt.worker_id != sender_id or receipt.lease_epoch != req.lease_epoch
            or receipt.expected_head_hash != snapshot.head_hash
        ):
            raise Denied("CLAIM", "WRITER_RECEIPT_BINDING")
        claim = DispatchClaim(claim_id, permit, receipt, sender_id, physical_attempt)
        self._claims[claim_id] = claim
        self._claimed_permits.add(permit.permit_id)
        return claim

    def attempt_external(
        self, claim: DispatchClaim, snapshot: AuthoritySnapshot, *, now: int
    ) -> None:
        """No external T3 exists here: mock or even forged verified receipts cannot bypass."""
        if self._claims.get(claim.claim_id) != claim:
            raise Denied("T3", "UNKNOWN_OR_MUTATED_CLAIM")
        self._fresh(claim.permit.request, snapshot, now, claim.sender_id)
        receipt = claim.writer_receipt
        if (
            not receipt.durable_verified or not receipt.outbox_ack or receipt.mock_only
            or receipt.writer_issuer != self._registry.writer_issuer
        ):
            raise Denied("T3", "NO_AUTHENTIC_DURABLE_OUTBOX_ACK")
        raise Denied("T3", "REAL_DISPATCH_DISABLED")

    def simulate_fixture(
        self, claim: DispatchClaim, snapshot: AuthoritySnapshot, *, now: int,
        adapter_id: str, synthetic_effect: Literal["applied", "not_applied", "unknown"],
        provider_receipt_id: str | None = "fixture-provider-receipt",
    ) -> MockAttempt:
        """Deterministic in-process record, expressly not T3 or an OS sandbox."""
        if self._claims.get(claim.claim_id) != claim:
            raise Denied("FIXTURE", "UNKNOWN_OR_MUTATED_CLAIM")
        self._fresh(claim.permit.request, snapshot, now, claim.sender_id)
        if (
            snapshot.head_hash != claim.permit.frozen_head_hash
            or snapshot.consent_generation != claim.permit.consent_generation
            or snapshot.revocation_generation != claim.permit.revocation_generation
            or now >= claim.permit.expires_at
        ):
            raise Denied("FIXTURE", "FENCE_OR_CONSENT_CHANGED")
        rule = self._rules[(
            claim.permit.request.capability_id, claim.permit.request.capability_version,
            claim.permit.request.operation,
        )]
        if (
            adapter_id != rule.executor_adapter_id
            or adapter_id not in self._registry.fake_adapter_ids
        ):
            raise Denied("FIXTURE", "ADAPTER_NOT_ALLOWLISTED")
        if synthetic_effect not in ("applied", "not_applied", "unknown"):
            raise Denied("FIXTURE", "INVALID_EFFECT")
        if claim.claim_id in self._attempted_claims:
            raise Denied("FIXTURE", "DOUBLE_SEND")
        self._attempted_claims.add(claim.claim_id)
        return MockAttempt(
            claim.claim_id, claim.permit.intent_digest, adapter_id,
            provider_receipt_id, synthetic_effect,
        )

    def reconcile_fixture(
        self, claim: DispatchClaim, attempt: MockAttempt, observation: ObservedEffect
    ) -> ReconciledOutcome:
        """Mock observation is distinct from executor assertion; never terminal proof."""
        if (
            self._claims.get(claim.claim_id) != claim
            or claim.claim_id not in self._attempted_claims
            or attempt.claim_id != claim.claim_id
            or attempt.intent_digest != claim.permit.intent_digest
            or observation.claim_id != claim.claim_id
            or observation.intent_digest != claim.permit.intent_digest
            or observation.tenant_id != claim.permit.request.tenant_id
            or observation.resource_id != claim.permit.request.resource_id
        ):
            raise Denied("T4", "EFFECT_BINDING")
        if (
            observation.observer_id == attempt.adapter_id
            or observation.observer_issuer not in self._registry.observer_issuers
            or not observation.observer_grant_id
        ):
            raise Denied("T4", "OBSERVER_NOT_INDEPENDENT_OR_GRANTED")
        if observation.citation_ids:
            raise Denied("T4", "SOURCE_CITATION_LAUNDERING")
        if claim.claim_id in self._outcomes:
            raise Denied("T4", "RECONCILIATION_REPLAY")
        state: Literal[
            "CONFIRMED_APPLIED_FIXTURE", "CONFIRMED_NOT_APPLIED_FIXTURE", "UNKNOWN_EFFECT"
        ] = "UNKNOWN_EFFECT"
        if (
            attempt.provider_receipt_id and observation.source_revision
            and observation.visibility_complete
        ):
            if observation.effect == "applied":
                state = "CONFIRMED_APPLIED_FIXTURE"
            elif observation.effect == "not_applied":
                state = "CONFIRMED_NOT_APPLIED_FIXTURE"
        outcome = ReconciledOutcome(claim.claim_id, state)
        self._outcomes[claim.claim_id] = outcome
        return outcome

    @staticmethod
    def aggregate(outcomes: tuple[ReconciledOutcome, ...]) -> str:
        if not outcomes or any(x.state != "CONFIRMED_APPLIED_FIXTURE" for x in outcomes):
            return "INCOMPLETE_OR_UNKNOWN_FIXTURE"
        return "ALL_APPLIED_FIXTURE_ONLY"

    @staticmethod
    def retry(outcome: ReconciledOutcome) -> None:
        """Never blindly replay unknown, negative, or even positive fixture evidence."""
        raise Denied("RETRY", "NO_AUTHENTIC_PROVIDER_IDEMPOTENCY_OR_OBSERVER_PROOF")
