"""I01 experimental AR02→AR03→AR04→AR05 local-only vertical.

No Provider/IdP calls, arbitrary executor, OS sandbox, outbound publication, or
real Client ACK. Only independently validated TEST_FIXTURE_ONLY evidence may
close the local SQLite journal, never mark actual Provider success.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    Head,
    RunIdentity,
)
from knowledge_engine.m27_ar03_verified_rights_v1_experimental import (
    CHECKPOINT_VERSION,
    NativeCitationPinV1,
    ProviderAuthorityVerifier,
    ReadIntent,
    RunCheckpointV1,
    SourceAuthorityEvidenceV1,
    VerifiedRightsConsumer,
)
from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    ActionRequest,
    ApprovalDecision,
    AuthoritySnapshot,
    DispatchClaim,
    DurableWriterReceipt,
    InProcessFixtureObserver,
    Permit,
    PermitSandboxV1,
    ReconciledOutcome,
    Registry,
)
from knowledge_engine.m27_ar05_independent_verifier_v1_experimental import (
    AuthenticatingTrust,
    EvidenceBundle,
    VerificationContext,
    propose_eligibility,
    sha,
)

VERSION = "I01CoreVerticalV1/TEST_FIXTURE_ONLY"
TEST_FIXTURE_SUCCESS = "I01_LOCAL_TEST_VERTICAL_PASS"
EXTERNAL_AUTHORITY_REQUIRED = "EXTERNAL_AUTHORITY_REQUIRED"
UNKNOWN_EFFECT = "UNKNOWN_EFFECT_TEST_FIXTURE"


class I01Denied(ValueError):
    """Reject an unbound inter-module seam before local terminal authority."""


@dataclass(frozen=True)
class LocalRequest:
    identity: RunIdentity
    intent: ReadIntent
    evidence: SourceAuthorityEvidenceV1
    pin: NativeCitationPinV1
    checkpoint: RunCheckpointV1
    request_id: str
    approval_id: str
    claim_id: str
    reserve_id: str
    charge_id: str
    resource_id: str
    recipient_id: str
    idempotency_key: str
    cost: int
    now: int
    expires_at: int
    effect: Literal["applied", "not_applied", "unknown"] = "applied"


@dataclass(frozen=True)
class LocalResult:
    status: str
    head: Head
    trace: tuple[str, ...]
    failure_codes: tuple[str, ...] = ()
    provider_calls: int = 0
    published: bool = False


# The independent fixture factory signs / supplies AR05 material outside this module.
# Neither callback constitutes a real signer, IdP, Provider, or ACK custodian.
FixtureBundleFactory = Callable[
    [Head, bytes, ReconciledOutcome, str],
    tuple[EvidenceBundle, VerificationContext, AuthenticatingTrust],
]
LocalTerminalSigner = Callable[[RunIdentity, Head, str, str, str], str]
StageProbe = Callable[[str, Head], None]


class _DurableAR02Port:
    """Adapter that creates and ACKs the *actual* durable SQLite T1/T2 claim."""

    def __init__(self, writer: DurableWriterV1, identity: RunIdentity,
                 head: Head, reserve_id: str, intent_id: str, now: int,
                 writer_issuer: str):
        self.writer = writer
        self.identity = identity
        self.head = head
        self.reserve_id = reserve_id
        self.intent_id = intent_id
        self.now = now
        self.writer_issuer = writer_issuer
        self.local_ack = ""

    def prepare_claim(self, permit: Permit, claim_id: str) -> DurableWriterReceipt:
        request = permit.request
        if (self.head.digest != permit.frozen_head_hash
                or self.head.epoch != request.lease_epoch
                or request.run_id != self.identity.run_id
                or request.tenant_id != self.identity.tenant_id
                or request.actor_id != self.identity.principal_id):
            raise I01Denied("AR02_AR04_FROZEN_HEAD_MISMATCH")
        self.head = self.writer.commit_intent_and_claim(
            self.identity, self.head, intent_id=self.intent_id,
            intent_digest=permit.intent_digest, approval_id=permit.approval_id,
            claim_id=claim_id, reserve_id=self.reserve_id,
            idempotency_key=request.idempotency_key, now=self.now,
        )
        self.head, self.local_ack = self.writer.claim_outbox(
            self.identity, self.head, claim_id=claim_id,
        )
        durable = self.writer.recover(self.identity)
        if (durable["head"] != self.head
                or not any(x["claim_id"] == claim_id and x["state"] == "CLAIMED"
                           for x in durable["outbox"])):
            raise I01Denied("LOCAL_OUTBOX_NOT_DURABLE")
        return DurableWriterReceipt(
            self.writer_issuer, claim_id, permit.permit_id, permit.intent_digest,
            request.run_id, request.tenant_id, permit.worker_id,
            request.lease_epoch, permit.frozen_head_hash, self.local_ack,
            True, True,  # SQLite durable, but still a fixture-only non-dispatch receipt.
        )


class I01CoreVerticalV1:
    """Feature-off composition. AR02 alone owns every durable mutation."""

    def __init__(
        self, *, writer: DurableWriterV1, rights: VerifiedRightsConsumer,
        source_verifier: ProviderAuthorityVerifier, registry: Registry,
        worker_id: str, observer: InProcessFixtureObserver,
        fixture_bundle: FixtureBundleFactory | None = None,
        local_signer: LocalTerminalSigner | None = None,
        verifier_id: str = "fixture-terminal-verifier",
        stage_probe: StageProbe | None = None,
    ):
        if (registry.feature_enabled or registry.real_dispatch_authorized
                or getattr(source_verifier, "fixture_kind", None) != "TEST_FIXTURE_ONLY"):
            raise I01Denied("FEATURE_OFF_FIXTURE_ONLY_REQUIRED")
        if (not worker_id or not verifier_id or observer.observer_id in {
            worker_id, verifier_id,
        } or observer.issuer not in registry.observer_issuers):
            raise I01Denied("INDEPENDENT_FIXTURE_ROLES_REQUIRED")
        self.writer = writer
        self.rights = rights
        self.source_verifier = source_verifier
        self.registry = registry
        self.worker_id = worker_id
        self.observer = observer
        self.fixture_bundle = fixture_bundle
        self.local_signer = local_signer
        self.verifier_id = verifier_id
        self.stage_probe = stage_probe

    def prepare(self, identity: RunIdentity, *, budget: int,
                source_revision: str, consent_generation: int,
                exclusion_generation: int) -> Head:
        """Persist a real initial journal. Caller builds checkpoint against this head."""
        return self.writer.create_run(
            identity, budget=budget, source_revision=source_revision,
            consent_generation=consent_generation,
            exclusion_generation=exclusion_generation,
        )

    def _probe(self, stage: str, identity: RunIdentity, head: Head) -> None:
        if self.stage_probe:
            self.stage_probe(stage, head)
        if self.writer.read_head(identity) != head:
            raise I01Denied("STALE_OR_CANCELLED_AR02_HEAD")

    def _source_bytes(self, r: LocalRequest, expected: bytes | None = None) -> bytes:
        observation = self.source_verifier.observe_source(r.pin)
        recovery = self.writer.recover(r.identity)
        now = self.source_verifier.trusted_now()
        if (observation is None or not isinstance(observation.original_bytes, bytes)
                or observation.source_id != r.pin.source_id
                or observation.source_revision != r.pin.source_revision
                or observation.resource_id != r.pin.resource_id
                or observation.provider_id != r.pin.provider_id
                or observation.provider_account != r.pin.provider_account
                or observation.tenant_id != r.identity.tenant_id
                or r.identity.principal_id not in observation.acl_principals
                or r.intent.purpose_id not in observation.purposes
                or not {"read", "cite"} <= observation.operations
                or not observation.consent_active
                or observation.valid_until <= now
                or observation.observed_at > now or now - observation.observed_at > 30
                or observation.consent_generation != recovery["consent_generation"]
                or observation.exclusion_generation != recovery["exclusion_generation"]
                or observation.revocation_generation < 0
                or recovery["revoked"]
                or recovery["source_revision"] != observation.source_revision
                or hashlib.sha256(observation.original_bytes).hexdigest()
                != r.pin.original_sha256
                or (expected is not None and observation.original_bytes != expected)):
            raise I01Denied("SOURCE_REVOKED_OR_BYTES_DRIFTED")
        return observation.original_bytes

    def execute(self, r: LocalRequest) -> LocalResult:
        identity = r.identity
        head = self.writer.read_head(identity)
        trace = ["AR02_DURABLE_HEAD"]
        if (identity.tenant_id != r.intent.tenant_id
                or identity.task_id != r.intent.task_id
                or identity.run_id != r.intent.run_id
                or identity.principal_id != r.intent.effective_principal_id
                or r.checkpoint != RunCheckpointV1(
                    CHECKPOINT_VERSION, identity.task_id, identity.run_id,
                    head.seq, head.digest,
                ) or head.state != "OPEN"):
            raise I01Denied("RUN_CHECKPOINT_OR_IDENTITY_MISMATCH")
        if not self.fixture_bundle or not self.local_signer:
            return LocalResult(EXTERNAL_AUTHORITY_REQUIRED, head, tuple(trace),
                               ("NO_INDEPENDENT_FIXTURE_PROOFS",))
        read_plan = self.rights.authorize_read(
            r.evidence, r.intent, r.pin, r.checkpoint,
        )
        if (not read_plan.read_allowed or not read_plan.citation_eligible
                or read_plan.publication_authorized
                or read_plan.actor.principal_id != identity.principal_id):
            raise I01Denied("AR03_AUTHORITY_NOT_EFFECTIVE")
        # No original source bytes admitted prior to independently verified read.
        original = self._source_bytes(r)
        trace.append("AR03_VERIFIED_NATIVE_READ")
        self._probe("after_read", identity, head)
        if not 0 < r.cost <= head.budget - head.spent - head.reserved:
            raise I01Denied("LOCAL_BUDGET_CAP")
        if r.now >= r.expires_at:
            raise I01Denied("EXPIRED_LOCAL_CONSENT")
        request = ActionRequest(
            r.request_id, identity.run_id, identity.tenant_id,
            identity.principal_id, read_plan.actor.delegated_by, "cap.items",
            "1", "update", r.resource_id, r.recipient_id,
            sha(original + r.pin.original_sha256.encode()), r.idempotency_key,
            "1", head.epoch,
        )
        head = self.writer.reserve(identity, head, reserve_id=r.reserve_id,
                                   amount=r.cost)
        head = self.writer.provision_fixture_approval(
            identity, head, approval_id=r.approval_id,
            intent_digest=request.digest(), expires_at=r.expires_at,
        )
        snapshot = AuthoritySnapshot(
            identity.run_id, identity.tenant_id, identity.principal_id,
            read_plan.actor.delegated_by, self.worker_id, head.epoch,
            r.expires_at, r.expires_at,
            self.writer.recover(identity)["consent_generation"], 0,
            head.digest, r.cost, self.registry.policy_issuer,
        )
        port = _DurableAR02Port(
            self.writer, identity, head, r.reserve_id, r.request_id,
            r.now, self.registry.writer_issuer,
        )
        sandbox = PermitSandboxV1(self.registry, port)
        sandbox.request(request, snapshot, now=r.now)
        approval = ApprovalDecision(
            r.approval_id, next(iter(sorted(self.registry.approval_issuers))),
            True, request.digest(), request.intent_version, identity.run_id,
            identity.tenant_id, head.epoch, snapshot.consent_generation,
            snapshot.revocation_generation, r.expires_at,
        )
        permit = sandbox.issue_permit(
            r.request_id, approval, snapshot, now=r.now, quoted_cost=r.cost,
        )
        self._probe("before_claim", identity, head)
        claim: DispatchClaim = sandbox.freeze_claim(
            permit, snapshot, claim_id=r.claim_id, sender_id=self.worker_id,
            physical_attempt=1, now=r.now,
        )
        head = port.head
        trace.append("AR04_POLICY_AND_AR02_T1_T2_DURABLE_CLAIM")
        self._probe("after_claim", identity, head)
        self._source_bytes(r, expected=original)
        head = self.writer.mark_possible_send(
            identity, head, claim_id=r.claim_id,
            local_ack_token=port.local_ack,
        )
        trace.append("AR02_T3_UNKNOWN_FENCE_LOCAL_ONLY")
        self._probe("after_t3", identity, head)
        attempt = sandbox.simulate_fixture(
            claim, snapshot, now=r.now,
            adapter_id=self.registry.rules[0].executor_adapter_id,
            synthetic_effect=r.effect,
        )
        observation = self.observer.observe(
            claim, effect=("absent_uncertain" if r.effect == "unknown"
                           else r.effect),
            source_revision=r.pin.source_revision,
        )
        outcome = sandbox.reconcile_fixture(claim, attempt, observation)
        trace.append("AR04_IN_PROCESS_FIXTURE_OBSERVER")
        if outcome.state != "CONFIRMED_APPLIED_FIXTURE":
            return LocalResult(UNKNOWN_EFFECT, head, tuple(trace),
                               (outcome.state,))
        self._source_bytes(r, expected=original)
        self._probe("before_t4", identity, head)
        observation_ref = "fixture-t4:" + r.claim_id
        head = self.writer.record_observer_reconciliation(
            identity, head, intent_id=r.request_id,
            original_t1_digest=request.digest(), observer_id=self.observer.observer_id,
            evidence_ref=observation_ref,
            evidence_sha256=sha(r.claim_id.encode() + original),
            outcome="CONFIRMED_APPLIED", source_revision=r.pin.source_revision,
            consent_generation=snapshot.consent_generation,
            exclusion_generation=self.writer.recover(identity)["exclusion_generation"],
            expires_at=r.expires_at, now=r.now,
        )
        trace.append("AR02_T4_OBSERVER_REFERENCE_UNATTESTED")
        head = self.writer.charge(
            identity, head, reserve_id=r.reserve_id,
            charge_id=r.charge_id, amount=r.cost,
        )
        self._probe("before_ar05", identity, head)
        # The independently supplied bundle must pin this exact post-T4+charge
        # journal head and *unchanged* original source and actual artifact bytes.
        outcome_digest = sha(
            (r.claim_id + "|" + outcome.state + "|" + head.digest).encode()
        )
        bundle, ctx, trust = self.fixture_bundle(
            head, original, outcome, outcome_digest,
        )
        if (ctx.tenant_id != identity.tenant_id or ctx.task_id != identity.task_id
                or ctx.run_id != identity.run_id or ctx.task_version != identity.task_version
                or ctx.principal != identity.principal_id
                or ctx.journal_epoch != head.epoch
                or ctx.journal_head_sha256 != head.digest
                or ctx.current_journal_head_sha256 != head.digest
                or ctx.outcome_sha256 != outcome_digest
                or bundle.operation is None
                or bundle.operation.requested_ids != (r.claim_id,)
                or bundle.operation.completed_ids != (r.claim_id,)
                or bundle.operation.resource_revision != r.pin.source_revision
                or bundle.cost.charge_ids != (r.charge_id,)
                or bundle.cost.actual_microunits != r.cost
                or bundle.cost.reserved_microunits != r.cost
                or not any(
                    s.source_id == r.pin.source_id
                    and s.revision == r.pin.source_revision
                    and s.original_bytes == original
                    and s.bytes_sha256 == r.pin.original_sha256
                    for s in bundle.sources
                ) or not all(any(
                    c.source_id == r.pin.source_id
                    and c.source_revision == r.pin.source_revision
                    and c.claim_start == span.start_byte and c.claim_end == span.end_byte
                    and c.quoted_original_bytes
                    == original[span.start_byte:span.end_byte]
                    for c in bundle.citations
                ) for span in r.pin.spans)):
            raise I01Denied("AR05_PIN_SOURCE_ARTIFACT_OR_JOURNAL_MISMATCH")
        decision = propose_eligibility(bundle, ctx, trust=trust)
        trace.append("AR05_INDEPENDENT_FIXTURE_PROPOSAL")
        if decision.status != "ELIGIBLE_TEST_FIXTURE_ONLY" or decision.failures:
            return LocalResult(EXTERNAL_AUTHORITY_REQUIRED, head, tuple(trace),
                               decision.failures or ("AR05_DENIED",))
        self._source_bytes(r, expected=original)
        self._probe("before_terminal", identity, head)
        signature = self.local_signer(
            identity, head, observation_ref, bundle.terminal_id,
            "LOCAL_VERIFIED_APPLIED",
        )
        final = self.writer.commit_terminal(
            identity, head, evidence_ref=observation_ref,
            verification_ref=bundle.terminal_id, verifier_id=self.verifier_id,
            signature_hex=signature, status="LOCAL_VERIFIED_APPLIED", now=r.now,
        )
        trace.append("AR02_LOCAL_TEST_TERMINAL_CAS")
        return LocalResult(TEST_FIXTURE_SUCCESS, final, tuple(trace))
