"""W4 I02 feature-off AR02-AR08 local runtime composition.

This is a reproducible *local fixture* integration, not authenticated provider
authority, client acknowledgement, economic settlement, or production runtime.
All external effects stay disabled. Do not replay unknown AR02 journal effects.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    Head,
    RunIdentity,
)
from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    ActionRequest,
    ApprovalDecision,
    AuthoritySnapshot,
    CapabilityRule,
    InProcessFixtureObserver,
    PermitSandboxV1,
    Registry,
)
from knowledge_engine.m27_ar06_governed_memory_experimental import ReadFixture
from knowledge_engine.m27_m28_local_rights_memory_fence import (
    LifecycleDenied,
    LocalLease,
    LocalRightsMemoryFence,
)
from knowledge_engine.m27_r29_local_action_v1_experimental import (
    R29Action,
    R29LocalActionVerifier,
    R29LocalFixtureAdapter,
)
from knowledge_engine.m27_r29_local_action_v1_experimental import (
    sha as action_sha,
)
from knowledge_engine.m27_w3_ar06_durable_governance_v1_experimental import (
    DurableMemoryExclusion,
    MemoryTicket,
)
from knowledge_engine.m27_w3_ar07_compute_budget_v1_experimental import (
    Attempt,
    BudgetReceipt,
    InvoiceFixture,
    LocalComputeBudget,
)
from knowledge_engine.m27_w3_ar08_coding_action_v1_experimental import (
    CodingActionRunnerV1,
    CodingReceiptV1,
    CodingTaskV1,
    IndependentReviewPort,
    _ClaimPort,
)
from knowledge_engine.m27_w3_ar08_qa_stream_v1_experimental import (
    ClockPort,
    NativeQATransportAdapter,
    NativeSourceBytes,
    SourceAuthorityPort,
    StreamSequenceState,
    TransportPort,
    VerificationPort,
    VerificationProposal,
)
from knowledge_engine.m27_w3_ar08_research_recovery_v1_experimental import (
    ResearchPlan,
    ResearchRecoveryV1,
    ReviewReceipt,
)

VERSION = "I02_LOCAL_CROSS_MODULE_V1"
PASS = "I02_LOCAL_CROSS_MODULE_PASS"


class I02Denied(ValueError):
    """Fail closed without leaking source or model content."""


@dataclass(frozen=True, slots=True)
class TaskContract:
    """Immutable ingress fence tying all local stages to an AR02 journal head."""

    identity: RunIdentity
    actor_id: str
    delegated_by: str | None
    task_contract_id: str
    workload: Literal["QA-I", "RES-L", "CODE-L", "ACT-LOCAL"]
    source_revision: str
    source_sha256: str
    consent_generation: int
    exclusion_generation: int
    lease_epoch: int
    journal_head: Head
    purpose: str
    now: int
    deadline: int
    source_acl_expires: int
    source_acl_current: bool = True
    fixture_only: bool = True
    lifecycle_lease: LocalLease | None = None


@dataclass(frozen=True, slots=True)
class LocalOutcome:
    workload: str
    run_id: str
    status: str
    head: Head
    artifact_sha256: str | None = None
    original_citation_sha256: tuple[str, ...] = ()
    first_text_flushed_preterminal: bool = False
    server_flush_only: bool = True
    client_ack: bool = False
    provider_calls: int = 0
    economic_certified: bool = False


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hex64(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


class _RuntimeAuthority:
    """Delegates to AR03's independently supplied fixture source authority."""

    def __init__(
        self, runtime: I02LocalRuntimeV1, contract: TaskContract,
        external: SourceAuthorityPort,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None,
    ) -> None:
        self.runtime = runtime
        self.contract = contract
        self.external = external
        self.memory = memory

    def assert_current(
        self, sources: tuple[NativeSourceBytes, ...],
        tenant_id: str, actor_id: str, wall_ms: int,
    ) -> None:
        self.runtime._fresh(self.contract, memory=self.memory, operation="read")
        if (tenant_id != self.contract.identity.tenant_id
                or actor_id != self.contract.actor_id
                or wall_ms >= self.contract.source_acl_expires * 1000):
            raise I02Denied("QA_SOURCE_SCOPE_OR_EXPIRED")
        for source in sources:
            if (source.revision != self.contract.source_revision
                    or source.sha256 != self.contract.source_sha256
                    or source.original_bytes != bytes(source.original_bytes)):
                raise I02Denied("QA_NATIVE_SOURCE_PIN_MISMATCH")
        self.external.assert_current(sources, tenant_id, actor_id, wall_ms)


class _RuntimeTransport:
    """Rechecks durable revocation on both sides of flush, never claims ACK."""

    def __init__(
        self, runtime: I02LocalRuntimeV1, contract: TaskContract,
        transport: TransportPort,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None,
    ) -> None:
        self.runtime = runtime
        self.contract = contract
        self.transport = transport
        self.memory = memory
        self.flush_count = 0

    def enqueue(self, frame: object) -> None:
        self.runtime._fresh(self.contract, memory=self.memory, operation="cite")
        self.transport.enqueue(frame)

    def flush(self, sequence: int) -> None:
        self.runtime._fresh(self.contract, memory=self.memory, operation="publish")
        self.transport.flush(sequence)
        self.flush_count += 1


class I02LocalRuntimeV1:
    """One local AR02 journal per Run and no implicit remote effects.

    The same immutable contract gates research checkpoint/replay, QA citations,
    and coding execution. AR07 owns a real SQLite CAS fence for model-budget
    attempts; AR08 research/coding reserve their own AR02 budget on the same
    ledger, so their own internal reservation must not be duplicated by AR07.
    """

    def __init__(
        self, writer: DurableWriterV1, *,
        lifecycle: LocalRightsMemoryFence | None = None,
    ) -> None:
        if not writer.fixture_approval_mode:
            raise I02Denied("LOCAL_FIXTURE_APPROVAL_MODE_REQUIRED")
        self.writer = writer
        self.lifecycle = lifecycle
        self.compute = LocalComputeBudget(writer)
        self.research = ResearchRecoveryV1(writer)
        self._inflight: set[tuple[str, str]] = set()
        self._attempted: set[tuple[str, str]] = set()

    @staticmethod
    def _key(contract: TaskContract) -> tuple[str, str]:
        return contract.identity.tenant_id, contract.identity.run_id

    def admit(
        self, contract: TaskContract,
        *,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None = None,
    ) -> Head:
        identity = contract.identity
        if (
            not contract.fixture_only
            or not all((identity.tenant_id, identity.run_id, identity.task_id,
                        identity.principal_id, contract.actor_id,
                        contract.task_contract_id, contract.purpose,
                        contract.source_revision))
            or identity.task_version <= 0
            or contract.actor_id != identity.principal_id
            or contract.delegated_by == contract.actor_id
            or not _hex64(contract.source_sha256)
            or type(contract.now) is not int
            or type(contract.deadline) is not int
            or not 0 <= contract.now < contract.deadline
            or type(contract.source_acl_expires) is not int
            or contract.source_acl_expires <= contract.now
            or not contract.source_acl_current
            or type(contract.consent_generation) is not int
            or type(contract.exclusion_generation) is not int
            or contract.consent_generation < 0 or contract.exclusion_generation < 0
            or type(contract.lease_epoch) is not int or contract.lease_epoch < 1
            or contract.workload not in {"QA-I", "RES-L", "CODE-L", "ACT-LOCAL"}
        ):
            raise I02Denied("INVALID_TASK_ADMISSION")
        rec = self.writer.recover(identity)
        head = rec["head"]
        if head != contract.journal_head or head.epoch != contract.lease_epoch:
            raise I02Denied("STALE_ADMISSION_JOURNAL_OR_LEASE")
        self._fresh(contract, memory=memory, operation="read")
        if any(row["state"] in {"POSSIBLY_SENT", "CLAIMED", "PENDING"}
               for row in rec["outbox"]):
            raise I02Denied("UNKNOWN_EFFECT_NO_REPLAY")
        if self._key(contract) in self._inflight or self._key(contract) in self._attempted:
            raise I02Denied("DUPLICATE_RUN_ADMISSION")
        return head

    def _fresh(
        self, contract: TaskContract, *,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None,
        operation: Literal[
            "read", "use", "cite", "publish", "tool", "checkpoint", "replay"
        ] = "use",
    ) -> Head:
        rec = self.writer.recover(contract.identity)
        head = rec["head"]
        if (
            rec["revoked"] or head.state != "OPEN"
            or head.epoch != contract.lease_epoch
            or rec["source_revision"] != contract.source_revision
            or rec["consent_generation"] != contract.consent_generation
            or rec["exclusion_generation"] != contract.exclusion_generation
            or not contract.source_acl_current
            or contract.now >= contract.source_acl_expires
            or contract.now >= contract.deadline
        ):
            raise I02Denied("REVOKED_STALE_AUTHORITY_LEASE_OR_TERMINAL")
        if self.lifecycle is not None:
            lease = contract.lifecycle_lease
            if (lease is None or
                    (lease.tenant_id, lease.run_id, lease.principal_id,
                     lease.purpose, lease.source_revision,
                     lease.consent_generation) !=
                    (contract.identity.tenant_id, contract.identity.run_id,
                     contract.actor_id, contract.purpose, contract.source_revision,
                     contract.consent_generation)):
                raise I02Denied("LOCAL_LIFECYCLE_SCOPE_OR_LEASE_MISSING")
            try:
                self.lifecycle.require(lease, operation)
            except LifecycleDenied as exc:
                raise I02Denied("LOCAL_LIFECYCLE_REVOKED_OR_STALE") from exc
        if memory is not None:
            ledger, ticket, auth = memory
            if (ledger.identity != contract.identity
                    or ticket.tenant != contract.identity.tenant_id
                    or ticket.source_revision != contract.source_revision
                    or ticket.source_digest != contract.source_sha256
                    or ticket.generation != contract.exclusion_generation
                    or ticket.consent_generation != contract.consent_generation
                    or auth.now != contract.now
                    or auth.principal != contract.actor_id
                    or auth.purpose != contract.purpose):
                raise I02Denied("MEMORY_PIN_OR_SCOPE_MISMATCH")
            ledger.consume(
                ticket, auth,
                operation=("cite" if operation == "publish" else
                           "use" if operation == "tool" else operation),
            )
        return head

    def _start(
        self, contract: TaskContract,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None,
    ) -> None:
        self.admit(contract, memory=memory)
        key = self._key(contract)
        self._attempted.add(key)
        self._inflight.add(key)

    def _end(self, contract: TaskContract) -> None:
        self._inflight.discard(self._key(contract))

    def qa(
        self, contract: TaskContract, attempt: Attempt, *,
        proposal: VerificationProposal,
        sources: tuple[NativeSourceBytes, ...],
        authority: SourceAuthorityPort,
        verification: VerificationPort,
        transport: TransportPort,
        clock: ClockPort,
        fragments: Sequence[bytes],
        invoice: InvoiceFixture | None,
        charge_id: str,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None = None,
    ) -> tuple[LocalOutcome, StreamSequenceState, BudgetReceipt]:
        """Real local AR07 CAS, native UTF-8 frames, local flush and invoice."""
        if (contract.workload != "QA-I" or attempt.identity != contract.identity
                or attempt.head != contract.journal_head
                or attempt.consent_generation != contract.consent_generation
                or attempt.exclusion_generation != contract.exclusion_generation
                or proposal.run_id != contract.identity.run_id
                or proposal.tenant_id != contract.identity.tenant_id
                or proposal.actor_id != contract.actor_id
                or proposal.verified_answer_sha256 != _sha(proposal.verified_answer_bytes)
                or not sources or not fragments):
            raise I02Denied("QA_CONTRACT_MISMATCH")
        self._start(contract, memory)
        try:
            budget = self.compute.reserve_and_fence(attempt)
            guarded_authority = _RuntimeAuthority(self, contract, authority, memory)
            guarded_transport = _RuntimeTransport(self, contract, transport, memory)
            stream = NativeQATransportAdapter(
                proposal=proposal, sources=sources,
                source_authority=guarded_authority,
                verification=verification, transport=guarded_transport, clock=clock,
            )
            offset = 0
            for fragment in fragments:
                stream.push(fragment, answer_offset=offset)
                offset += len(fragment)
            state = stream.terminal()
            first = stream.first_answer_receipt
            if (
                state.status != "terminal" or first is None
                or first.flushed_monotonic_ns > state.terminal_monotonic_ns
                or guarded_transport.flush_count == 0
            ):
                raise I02Denied("NO_SUBSTANTIVE_PRETERMINAL_SERVER_FLUSH")
            self._fresh(contract, memory=memory, operation="cite")
            if invoice is not None:
                budget = self.compute.settle(
                    contract.identity, attempt.request_key, invoice,
                    charge_id=charge_id,
                )
            else:
                budget = self.compute.recover(contract.identity, attempt.request_key)
            citations = tuple(
                _sha(link.citation.original_claim_bytes) for link in proposal.links
            )
            return (
                LocalOutcome(
                    contract.workload, contract.identity.run_id,
                    "QA_LOCAL_FLUSH_ONLY_CLIENT_ACK_OPEN", self.writer.read_head(
                        contract.identity
                    ), original_citation_sha256=citations,
                    first_text_flushed_preterminal=True,
                ),
                state, budget,
            )
        finally:
            self._end(contract)

    def research_workflow(
        self, contract: TaskContract, plan: ResearchPlan, *,
        sources: Mapping[str, bytes],
        reviews: Sequence[ReviewReceipt],
        cursors: Sequence[str],
        quoted_cost: int,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None = None,
    ) -> tuple[LocalOutcome, bytes, dict]:
        """Actual SQLite checkpoints and original source/artifact bytes after reopen."""
        if (
            contract.workload != "RES-L" or plan.identity != contract.identity
            or len(cursors) != len(plan.milestones)
            or quoted_cost != plan.reserved_microunits
            or set(sources) != {x.source_id for x in plan.source_pins}
            or plan.deadline_at != contract.deadline
            or plan.purpose_id != contract.purpose
            or any(x.source_revision != contract.source_revision
                   or x.exclusion_generation != contract.exclusion_generation
                   or x.consent_generation != contract.consent_generation
                   for x in plan.source_pins)
        ):
            raise I02Denied("RESEARCH_CONTRACT_MISMATCH")
        self._start(contract, memory)
        try:
            self.research.admit(plan, now=contract.now)
            self._fresh(contract, memory=memory, operation="read")
            self.research.reserve_budget(plan, now=contract.now)
            for pin in plan.source_pins:
                self._fresh(contract, memory=memory, operation="read")
                self.research.register_source(
                    plan, source_id=pin.source_id,
                    original_bytes=sources[pin.source_id], now=contract.now,
                )
            for receipt in reviews:
                self._fresh(contract, memory=memory, operation="cite")
                self.research.record_review(plan, receipt, now=contract.now)
            for milestone, cursor in zip(plan.milestones, cursors, strict=True):
                self._fresh(contract, memory=memory, operation="checkpoint")
                self.research.checkpoint(
                    plan, milestone=milestone, cursor=cursor, now=contract.now,
                )
            # Reconstruct via a fresh durable component instance against SQLite.
            reopened = ResearchRecoveryV1(
                DurableWriterV1(self.writer.path, fixture_approval_mode=True)
            )
            self._fresh(contract, memory=memory, operation="replay")
            resume = reopened.resume(plan, now=contract.now)
            if resume["cursor"] != cursors[-1] or resume["checkpoint_count"] != len(cursors):
                raise I02Denied("CHECKPOINT_REPLAY_DRIFT")
            reopened.propose_artifact(
                plan, now=contract.now, quoted_cost=quoted_cost,
            )
            self._fresh(contract, memory=memory, operation="cite")
            payload = reopened.read_artifact(plan)
            # The original artifact is a locally hash-checked SQLite BLOB.
            if not payload or not isinstance(payload, bytes):
                raise I02Denied("RESEARCH_ARTIFACT_MISSING")
            return (
                LocalOutcome(
                    contract.workload, contract.identity.run_id,
                    "RESEARCH_LOCAL_ARTIFACT_ONLY", self.writer.read_head(
                        contract.identity
                    ), artifact_sha256=_sha(payload),
                ),
                payload, resume,
            )
        finally:
            self._end(contract)


    def action_local(
        self, contract: TaskContract, action: R29Action, *,
        adapter: R29LocalFixtureAdapter,
        verifier: R29LocalActionVerifier,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None = None,
        after_enqueue: object = None,
        before_send: object = None,
        after_send: object = None,
    ) -> tuple[LocalOutcome, dict]:
        """R29 ACT-LOCAL: admitted I02 TaskContract with AR02/04/05 and M28.

        Only an injected, explicitly enabled, fixed 127.0.0.1 OS SQLite
        fixture service. Never calls AR04 real external dispatch. T3 UNKNOWN
        is written before one physical POST; uncertain responses are observed,
        never resent. Hooks exist exclusively for negative local OS faults.
        """
        if (
            contract.workload != "ACT-LOCAL" or not contract.fixture_only
            or type(adapter) is not R29LocalFixtureAdapter
            or type(verifier) is not R29LocalActionVerifier
            or (action.tenant_id, action.run_id, action.actor_id,
                action.source_revision) != (
                    contract.identity.tenant_id, contract.identity.run_id,
                    contract.actor_id, contract.source_revision)
            or action.mode not in {"normal", "lost_ack", "observer_unknown"}
            or not action.idempotency_key.isidentifier()
            or not action.effect_id.isidentifier()
            or verifier.verifier_id == contract.actor_id
            or contract.exclusion_generation != 0
        ):
            raise I02Denied("ACT_LOCAL_SCOPE_OR_FEATURE_DENIED")
        self._start(contract, memory)
        ident = contract.identity
        rule = CapabilityRule(
            "fixture.action", "1", "apply", "/fixture/",
            "r29-local-http-sqlite", 1,
        )
        registry = Registry(
            "fixture-policy", frozenset({"fixture-approver"}),
            frozenset({"fixture-observer"}), "local-ar02-writer",
            frozenset({"r29-local-http-sqlite"}), (rule,),
        )
        receipt = {}
        try:
            self._fresh(contract, memory=memory, operation="tool")
            request = ActionRequest(
                request_id="req-" + ident.run_id, run_id=ident.run_id,
                tenant_id=ident.tenant_id, actor_id=contract.actor_id,
                delegated_by=contract.delegated_by,
                capability_id=rule.capability_id, capability_version="1",
                operation="apply",
                resource_id=f"/fixture/{ident.tenant_id}/{ident.run_id}",
                recipient_id="fixture-os-sqlite-only",
                arguments_digest=action_sha([
                    action.effect_id, action.idempotency_key, action.source_revision,
                ]),
                idempotency_key=action.idempotency_key,
                intent_version="R29-ACT-LOCAL-FIXTURE-v1",
                lease_epoch=contract.lease_epoch,
            )
            snapshot = AuthoritySnapshot(
                ident.run_id, ident.tenant_id, contract.actor_id,
                contract.delegated_by, "r29-local-worker",
                contract.lease_epoch, contract.deadline, contract.source_acl_expires,
                contract.consent_generation, contract.exclusion_generation,
                contract.journal_head.digest, 1, registry.policy_issuer,
            )
            sandbox = PermitSandboxV1(registry, None)
            sandbox.request(request, snapshot, now=contract.now)
            decision = ApprovalDecision(
                "approval-" + ident.run_id, "fixture-approver", True,
                request.digest(), request.intent_version, ident.run_id,
                ident.tenant_id, contract.lease_epoch,
                contract.consent_generation, contract.exclusion_generation,
                contract.source_acl_expires,
            )
            permit = sandbox.issue_permit(
                request.request_id, decision, snapshot,
                now=contract.now, quoted_cost=1,
            )
            self._fresh(contract, memory=memory, operation="tool")
            reserve_id = "reserve-" + ident.run_id
            intent_id = "intent-" + ident.run_id
            claim_id = "claim-" + ident.run_id
            head = self.writer.reserve(
                ident, contract.journal_head, reserve_id=reserve_id, amount=1,
            )
            head = self.writer.provision_fixture_approval(
                ident, head, approval_id=decision.approval_id,
                intent_digest=request.digest(), expires_at=decision.expires_at,
            )
            # This final fence runs before durable outbox/intention commit.
            self._fresh(contract, memory=memory, operation="tool")
            head = self.writer.commit_intent_and_claim(
                ident, head, intent_id=intent_id, intent_digest=request.digest(),
                approval_id=decision.approval_id, claim_id=claim_id,
                reserve_id=reserve_id,
                idempotency_key=ident.tenant_id + "-" + ident.run_id + "-" +
                action.idempotency_key, now=contract.now,
            )
            if callable(after_enqueue):
                after_enqueue()
            self._fresh(contract, memory=memory, operation="tool")
            head, token = self.writer.claim_outbox(ident, head, claim_id=claim_id)
            sandbox._writer = _ClaimPort(token, claim_id, registry.writer_issuer)
            claim = sandbox.freeze_claim(
                permit, snapshot, claim_id=claim_id,
                sender_id=snapshot.worker_id, physical_attempt=1,
                now=contract.now,
            )
            if not claim.writer_receipt.durable_verified:
                raise I02Denied("ACT_LOCAL_DURABLE_ACK_MISSING")
            # Unknown before physical send. No implicit/automatic retries.
            head = self.writer.mark_possible_send(
                ident, head, claim_id=claim_id, local_ack_token=token,
            )
            if callable(before_send):
                before_send()
            self._fresh(contract, memory=memory, operation="tool")
            receipt["sent_attempted"] = True
            try:
                adapter.send_once(action, claim_id, request.digest())
            except (OSError, ValueError):
                receipt["ack_lost_or_unavailable"] = True
            if callable(after_send):
                after_send()
            # Separate service, separate SQLite evidence. Never infer APPLIED
            # from a successful POST acknowledgement alone.
            try:
                observed = adapter.observe(action, claim_id, request.digest())
                verified_hash = verifier.verify(
                    observed, action=action, claim=claim_id,
                    intent=request.digest(),
                )
            except (OSError, ValueError):
                observed = None
                verified_hash = None
            if observed is None or verified_hash is None:
                receipt.update(
                    observer="UNKNOWN", effect="UNKNOWN_EFFECT",
                    claim=claim_id, intent_sha256=request.digest(),
                )
                return LocalOutcome(
                    contract.workload, ident.run_id,
                    "UNKNOWN_EFFECT_NO_AUTORETRY", self.writer.read_head(ident),
                ), receipt
            self._fresh(contract, memory=memory, operation="tool")
            head = self.writer.record_observer_reconciliation(
                ident, self.writer.read_head(ident), intent_id=intent_id,
                original_t1_digest=request.digest(), observer_id="fixture-observer",
                evidence_ref="r29-" + ident.run_id,
                evidence_sha256=verified_hash,
                outcome=("CONFIRMED_APPLIED" if observed["effect"] == "applied"
                         else "CONFIRMED_NOT_APPLIED"),
                source_revision=contract.source_revision,
                consent_generation=contract.consent_generation,
                exclusion_generation=contract.exclusion_generation,
                expires_at=contract.deadline, now=contract.now,
            )
            head = self.writer.charge(
                ident, head, reserve_id=reserve_id,
                charge_id="charge-" + ident.run_id, amount=1,
            )
            status = ("LOCAL_VERIFIED_APPLIED" if observed["effect"] == "applied"
                      else "LOCAL_VERIFIED_NOT_APPLIED")
            message = self.writer.verification_message(
                ident, head, evidence_ref="r29-" + ident.run_id,
                verification_ref="ar05-r29-" + ident.run_id, status=status,
            )
            head = self.writer.commit_terminal(
                ident, head, evidence_ref="r29-" + ident.run_id,
                verification_ref="ar05-r29-" + ident.run_id,
                verifier_id=verifier.verifier_id,
                signature_hex=verifier.sign_local_terminal(message),
                status=status, now=contract.now,
            )
            receipt.update(
                observer=observed, effect=observed["effect"], claim=claim_id,
                intent_sha256=request.digest(), ar05_sha256=verified_hash,
            )
            return LocalOutcome(
                contract.workload, ident.run_id,
                status + "_FIXTURE_ONLY", head,
                artifact_sha256=verified_hash,
            ), receipt
        finally:
            self._end(contract)

    def coding(
        self, contract: TaskContract, task: CodingTaskV1, *,
        runner: CodingActionRunnerV1,
        snapshot: AuthoritySnapshot,
        approval: ApprovalDecision,
        verifier: IndependentReviewPort,
        observer: InProcessFixtureObserver,
        memory: tuple[DurableMemoryExclusion, MemoryTicket, ReadFixture] | None = None,
    ) -> tuple[LocalOutcome, CodingReceiptV1]:
        """Executes only accepted, fixed ephemeral Python fixture subprocess."""
        if (
            contract.workload != "CODE-L" or task.identity != contract.identity
            or runner.writer.path != self.writer.path
            or task.source_revision != contract.source_revision
            or task.expected_head != contract.journal_head.digest
            or snapshot.actor_id != contract.actor_id
            or snapshot.delegated_by != contract.delegated_by
            or snapshot.lease_epoch != contract.lease_epoch
            or snapshot.consent_generation != contract.consent_generation
            or snapshot.revocation_generation != contract.exclusion_generation - 1
            or not approval.approved
        ):
            raise I02Denied("CODING_CONTRACT_OR_PERMIT_MISMATCH")
        self._start(contract, memory)
        try:
            self._fresh(contract, memory=memory, operation="tool")
            result = runner.execute(
                task, snapshot=snapshot, approval=approval,
                verifier=verifier, observer=observer, now=contract.now,
                before_local_send=(
                    lambda: self._fresh(
                        contract, memory=memory, operation="tool",
                    )
                ),
            )
            head = self.writer.read_head(contract.identity)
            if result.outcome == "LOCAL_VERIFIED_APPLIED_TEST_FIXTURE_ONLY":
                if (
                    result.exit_code != 0 or result.attempts != 1
                    or not result.ephemeral_cleaned
                    or result.artifact_sha256 != task.expected_source_sha256
                    or result.stdout_bytes != b"FIXTURE_OK\n"
                    or result.stderr_bytes or head.state != "LOCAL_VERIFIED_APPLIED"
                    or head.spent != 1
                ):
                    raise I02Denied("CODING_EXECUTION_OR_JOURNAL_MISMATCH")
                state = "CODING_LOCAL_VERIFIED_FIXTURE_ONLY"
            else:
                if head.state != "OPEN":
                    raise I02Denied("UNKNOWN_EFFECT_MUST_NOT_BE_TERMINAL")
                state = "UNKNOWN_EFFECT_NO_AUTORETRY"
            return LocalOutcome(
                contract.workload, contract.identity.run_id, state, head,
                artifact_sha256=result.artifact_sha256,
            ), result
        finally:
            self._end(contract)
