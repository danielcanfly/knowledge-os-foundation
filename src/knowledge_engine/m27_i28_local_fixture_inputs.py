"""I28 bounded local synthetic fixture contracts. No third-party trust."""

from __future__ import annotations

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import DurableWriterV1, RunIdentity
from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    ApprovalDecision,
    AuthoritySnapshot,
    InProcessFixtureObserver,
)
from knowledge_engine.m27_ar07_compute_policy_experimental import (
    ComputeDecisionInput,
    PriceSnapshotFixture,
    ProviderCatalogFixture,
)
from knowledge_engine.m27_w3_ar07_compute_budget_v1_experimental import Attempt, InvoiceFixture
from knowledge_engine.m27_w3_ar08_coding_action_v1_experimental import (
    CodingActionRunnerV1,
    CodingTaskV1,
    IndependentLocalFixtureVerifier,
)
from knowledge_engine.m27_w3_ar08_qa_stream_v1_experimental import (
    AnswerEvidenceLink,
    CitationByteSpan,
    ClockSample,
    NativeSourceBytes,
    StreamDenied,
    VerificationProposal,
    digest,
)
from knowledge_engine.m27_w3_ar08_research_recovery_v1_experimental import (
    ResearchPlan,
    ReviewReceipt,
    SourcePin,
)
from knowledge_engine.m27_w4_i02_local_runtime_v1_experimental import (
    I02LocalRuntimeV1,
    TaskContract,
)

SOURCE = "Alpha βeta\n".encode()
D = digest(SOURCE)
KEY = b"independent-fixture-hmac-long-secure"
NOW = 10


def make(tmp_path, kind="QA-I", run="runA", budget=100, exclusion=0):
    identity = RunIdentity("tenantA", run, "taskA", 1, "principalA")
    writer = DurableWriterV1(
        tmp_path / (run + ".sqlite"),
        fixture_approval_mode=True,
        verifier_keys={"verifier_x": KEY},
    )
    head = writer.create_run(
        identity,
        budget=budget,
        source_revision="rev1",
        consent_generation=1,
        exclusion_generation=exclusion,
    )
    contract = TaskContract(
        identity,
        "principalA",
        None,
        "contract1",
        kind,
        "rev1",
        D,
        1,
        exclusion,
        head.epoch,
        head,
        "research",
        NOW,
        100,
        90,
    )
    return I02LocalRuntimeV1(writer), contract


class Clock:
    def __init__(self):
        self.value = 100

    def sample(self):
        self.value += 10
        return ClockSample("monotonic_ns", self.value, 1000)


class Authority:
    def __init__(self):
        self.revoked = False
        self.calls = 0

    def assert_current(self, sources, tenant_id, actor_id, wall_ms):
        self.calls += 1
        if self.revoked:
            raise StreamDenied("SOURCE_REVOKED")
        assert sources and tenant_id == "tenantA" and actor_id == "principalA"
        assert wall_ms == 1000


class Verifier:
    def assert_current(self, proposal, wall_ms):
        if proposal.proof_id != "independent-proof":
            raise StreamDenied("UNTRUSTED_PROPOSAL")


class Transport:
    def __init__(self):
        self.events = []
        self.on_enqueue = None
        self.fail_flush = False

    def enqueue(self, frame):
        self.events.append(("enqueue", frame.sequence, frame.data))
        if self.on_enqueue:
            self.on_enqueue(frame)

    def flush(self, sequence):
        self.events.append(("flush", sequence))
        if self.fail_flush:
            raise OSError("ambiguous flush")


def attempt_for(contract):
    identity, head = contract.identity, contract.journal_head
    item = ComputeDecisionInput(
        tenant_id=identity.tenant_id,
        task_id=identity.task_id,
        run_id=identity.run_id,
        task_version=identity.task_version,
        lease_epoch=head.epoch,
        workload_kind="QA-I",
        phase="generation",
        now_ms=100,
        deadline_at_ms=14000,
        residency="TW",
        privacy_class="restricted",
        currency="MICROUSD",
        approved_providers=("local-fixture",),
        source_revision="rev1",
        authorized_revision="rev1",
        source_grant_valid=True,
        source_expires_at_ms=20000,
        context_expires_at_ms=20000,
        budget_version=head.seq,
        max_cost_microunits=head.budget,
        spent_cost_microunits=0,
        reserved_cost_microunits=0,
        max_tokens=100,
        spent_tokens=0,
        reserved_tokens=0,
        max_wall_ms=12000,
        spent_wall_ms=0,
        reserved_wall_ms=0,
        max_tool_calls=0,
        spent_tool_calls=0,
        reserved_tool_calls=0,
        max_attempts=3,
        attempts_used=0,
        max_retries=1,
        retry_index=0,
        request_tokens=10,
        request_wall_ms=1000,
        request_tool_calls=0,
        qa_verification_reserve_ms=3000,
        retrieval_depth=0,
        max_retrieval_depth=2,
        reflection_steps=0,
        max_reflection_steps=1,
        agent_count=1,
        max_agent_count=2,
        failure_class=None,
        cancelled=False,
        unknown_effect=False,
        billing_uncertain=False,
        late_billing_overrun=False,
        actual_cost_microunits=None,
        expected_marginal_value=0,
        verified_stream_frame=None,
    )
    route = ProviderCatalogFixture(
        "local-route",
        "local-fixture",
        "fake-model",
        "v1",
        ("QA-I", "RES-L", "CODE-L"),
        ("TW",),
        ("restricted",),
        True,
        90,
        3000,
        1000,
        True,
    )
    price = PriceSnapshotFixture(
        "fixture-price",
        "local-fixture",
        "fake-model",
        "v1",
        "MICROUSD",
        2,
        90,
        3000,
        True,
    )
    return Attempt(
        identity,
        head,
        item,
        (route,),
        (price,),
        "fixture-price",
        1,
        0,
        "request-one",
        "reserve-one",
        "approval-one",
        "intent-one",
        "claim-one",
    )


def qa_bundle(runtime, contract):
    src = NativeSourceBytes(
        "tenantA",
        "principalA",
        "sourceA",
        "native:citation:A",
        "rev1",
        D,
        SOURCE,
        "independent-source-fixture",
        2000,
    )
    pin = CitationByteSpan(
        src.native_citation_id,
        src.source_id,
        "rev1",
        D,
        0,
        len(SOURCE),
        SOURCE,
    )
    proposal = VerificationProposal(
        "tenantA",
        "principalA",
        contract.identity.run_id,
        "independent-proof",
        SOURCE,
        D,
        (AnswerEvidenceLink(0, len(SOURCE), pin),),
        900,
        2000,
        "local-independent-fixture",
    )
    transport = Transport()
    invoice = InvoiceFixture(
        "usage-one",
        "fixture-price",
        "v1",
        "MICROUSD",
        "rev1",
        1,
        18,
        9,
        "local-usage-receipt",
    )
    return dict(
        attempt=attempt_for(contract),
        proposal=proposal,
        sources=(src,),
        authority=Authority(),
        verification=Verifier(),
        transport=transport,
        clock=Clock(),
        fragments=(SOURCE[:7], SOURCE[7:8], SOURCE[8:]),
        invoice=invoice,
        charge_id="charge-one",
    )


def research_bundle(contract):
    support, counter = b"Confirmed fact", b"Conflicting claim"
    pins = (
        SourcePin(
            "support",
            "rev1",
            digest(support),
            "tenantA",
            90,
            1,
            0,
            ("principalA",),
            ("research",),
            0,
            len(support),
            "support",
            "hyp1",
        ),
        SourcePin(
            "counter",
            "rev1",
            digest(counter),
            "tenantA",
            90,
            1,
            0,
            ("principalA",),
            ("research",),
            0,
            len(counter),
            "counter",
            "hyp1",
        ),
    )
    plan = ResearchPlan(
        contract.identity,
        "research",
        1,
        "a" * 64,
        ("hyp1",),
        ("source-reviewed", "draft-checked"),
        pins,
        "reserve-research",
        20,
        100,
    )
    reviews = tuple(
        ReviewReceipt(
            pin.source_id,
            "rev1",
            pin.original_sha256,
            "reviewer_x",
            5,
            "ACCEPTED",
            "fixture-review-" + pin.source_id,
        )
        for pin in pins
    )
    return dict(
        plan=plan,
        sources={"support": support, "counter": counter},
        reviews=reviews,
        cursors=("cursor:review", "cursor:draft"),
        quoted_cost=20,
    )


def coding_bundle(runtime, contract, temp_root):
    left, right, expected = 2, 3, 5
    source = f"def compute():\n    return {left} + {right}\n".encode()
    head = contract.journal_head
    task = CodingTaskV1(
        contract.identity,
        "request_a",
        head.digest,
        "rev1",
        digest(source),
        left,
        right,
        "add",
        expected,
    )
    verifier = IndependentLocalFixtureVerifier("verifier_x", KEY)
    runner = CodingActionRunnerV1(runtime.writer, temp_root=temp_root)
    intent = runner.prepare(task)
    snapshot = AuthoritySnapshot(
        contract.identity.run_id,
        "tenantA",
        "principalA",
        None,
        "worker_a",
        head.epoch,
        160,
        160,
        1,
        0,
        head.digest,
        3,
        "fixture-policy",
    )
    approval = ApprovalDecision(
        "approval_runA",
        "fixture-approver",
        True,
        intent.request.digest(),
        task.schema_version,
        contract.identity.run_id,
        "tenantA",
        head.epoch,
        1,
        0,
        160,
    )
    return dict(
        task=task,
        runner=runner,
        snapshot=snapshot,
        approval=approval,
        verifier=verifier,
        observer=InProcessFixtureObserver("observer_x", "fixture-observer", "grant_x"),
    ), digest(source)
