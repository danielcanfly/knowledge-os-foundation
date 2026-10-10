"""I02 true local AR02-AR08 integration and independent adversarial cases."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    RunIdentity,
)
from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    ApprovalDecision,
    AuthoritySnapshot,
    InProcessFixtureObserver,
)
from knowledge_engine.m27_ar06_governed_memory_experimental import (
    Candidate,
    GovernanceBoundary,
    ReadFixture,
    ReviewerDecisionFixture,
    Revocation,
)
from knowledge_engine.m27_ar07_compute_policy_experimental import (
    ComputeDecisionInput,
    PriceSnapshotFixture,
    ProviderCatalogFixture,
)
from knowledge_engine.m27_w3_ar06_durable_governance_v1_experimental import (
    DurableMemoryDenied,
    DurableMemoryExclusion,
)
from knowledge_engine.m27_w3_ar07_compute_budget_v1_experimental import (
    Attempt,
    BudgetFence,
    InvoiceFixture,
)
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
    ResearchDenied,
    ResearchPlan,
    ReviewReceipt,
    SourcePin,
)
from knowledge_engine.m27_w4_i02_local_runtime_v1_experimental import (
    I02Denied,
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
        tmp_path / (run + ".sqlite"), fixture_approval_mode=True,
        verifier_keys={"verifier_x": KEY},
    )
    head = writer.create_run(
        identity, budget=budget, source_revision="rev1",
        consent_generation=1, exclusion_generation=exclusion,
    )
    contract = TaskContract(
        identity, "principalA", None, "contract1", kind, "rev1", D,
        1, exclusion, head.epoch, head, "research", NOW, 100, 90,
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
        tenant_id=identity.tenant_id, task_id=identity.task_id,
        run_id=identity.run_id, task_version=identity.task_version,
        lease_epoch=head.epoch, workload_kind="QA-I", phase="generation",
        now_ms=100, deadline_at_ms=14000, residency="TW",
        privacy_class="restricted", currency="MICROUSD",
        approved_providers=("local-fixture",), source_revision="rev1",
        authorized_revision="rev1", source_grant_valid=True,
        source_expires_at_ms=20000, context_expires_at_ms=20000,
        budget_version=head.seq, max_cost_microunits=head.budget,
        spent_cost_microunits=0, reserved_cost_microunits=0,
        max_tokens=100, spent_tokens=0, reserved_tokens=0,
        max_wall_ms=12000, spent_wall_ms=0, reserved_wall_ms=0,
        max_tool_calls=0, spent_tool_calls=0, reserved_tool_calls=0,
        max_attempts=3, attempts_used=0, max_retries=1, retry_index=0,
        request_tokens=10, request_wall_ms=1000, request_tool_calls=0,
        qa_verification_reserve_ms=3000, retrieval_depth=0,
        max_retrieval_depth=2, reflection_steps=0, max_reflection_steps=1,
        agent_count=1, max_agent_count=2, failure_class=None,
        cancelled=False, unknown_effect=False, billing_uncertain=False,
        late_billing_overrun=False, actual_cost_microunits=None,
        expected_marginal_value=0, verified_stream_frame=None,
    )
    route = ProviderCatalogFixture(
        "local-route", "local-fixture", "fake-model", "v1",
        ("QA-I", "RES-L", "CODE-L"), ("TW",), ("restricted",),
        True, 90, 3000, 1000, True,
    )
    price = PriceSnapshotFixture(
        "fixture-price", "local-fixture", "fake-model", "v1",
        "MICROUSD", 2, 90, 3000, True,
    )
    return Attempt(
        identity, head, item, (route,), (price,), "fixture-price", 1, 0,
        "request-one", "reserve-one", "approval-one", "intent-one", "claim-one",
    )


def qa_bundle(runtime, contract):
    src = NativeSourceBytes(
        "tenantA", "principalA", "sourceA", "native:citation:A",
        "rev1", D, SOURCE, "independent-source-fixture", 2000,
    )
    pin = CitationByteSpan(
        src.native_citation_id, src.source_id, "rev1", D,
        0, len(SOURCE), SOURCE,
    )
    proposal = VerificationProposal(
        "tenantA", "principalA", contract.identity.run_id, "independent-proof",
        SOURCE, D, (AnswerEvidenceLink(0, len(SOURCE), pin),),
        900, 2000, "local-independent-fixture",
    )
    transport = Transport()
    invoice = InvoiceFixture(
        "usage-one", "fixture-price", "v1", "MICROUSD", "rev1", 1,
        18, 9, "local-usage-receipt",
    )
    return dict(
        attempt=attempt_for(contract), proposal=proposal, sources=(src,),
        authority=Authority(), verification=Verifier(), transport=transport,
        clock=Clock(), fragments=(SOURCE[:7], SOURCE[7:8], SOURCE[8:]),
        invoice=invoice, charge_id="charge-one",
    )


def research_bundle(contract):
    support, counter = b"Confirmed fact", b"Conflicting claim"
    pins = (
        SourcePin("support", "rev1", digest(support), "tenantA", 90, 1, 0,
                  ("principalA",), ("research",), 0, len(support),
                  "support", "hyp1"),
        SourcePin("counter", "rev1", digest(counter), "tenantA", 90, 1, 0,
                  ("principalA",), ("research",), 0, len(counter),
                  "counter", "hyp1"),
    )
    plan = ResearchPlan(
        contract.identity, "research", 1, "a" * 64, ("hyp1",),
        ("source-reviewed", "draft-checked"), pins, "reserve-research", 20, 100,
    )
    reviews = tuple(
        ReviewReceipt(
            pin.source_id, "rev1", pin.original_sha256, "reviewer_x", 5,
            "ACCEPTED", "fixture-review-" + pin.source_id,
        ) for pin in pins
    )
    return dict(
        plan=plan, sources={"support": support, "counter": counter},
        reviews=reviews, cursors=("cursor:review", "cursor:draft"),
        quoted_cost=20,
    )


def coding_bundle(runtime, contract, temp_root):
    left, right, expected = 2, 3, 5
    source = f"def compute():\n    return {left} + {right}\n".encode()
    head = contract.journal_head
    task = CodingTaskV1(
        contract.identity, "request_a", head.digest, "rev1", digest(source),
        left, right, "add", expected,
    )
    verifier = IndependentLocalFixtureVerifier("verifier_x", KEY)
    runner = CodingActionRunnerV1(runtime.writer, temp_root=temp_root)
    intent = runner.prepare(task)
    snapshot = AuthoritySnapshot(
        contract.identity.run_id, "tenantA", "principalA", None,
        "worker_a", head.epoch, 160, 160, 1, 0, head.digest, 3,
        "fixture-policy",
    )
    approval = ApprovalDecision(
        "approval_runA", "fixture-approver", True, intent.request.digest(),
        task.schema_version, contract.identity.run_id, "tenantA", head.epoch,
        1, 0, 160,
    )
    return dict(
        task=task, runner=runner, snapshot=snapshot, approval=approval,
        verifier=verifier,
        observer=InProcessFixtureObserver("observer_x", "fixture-observer", "grant_x"),
    ), digest(source)


def memory_bundle(runtime, contract):
    boundary = GovernanceBoundary()
    candidate = Candidate(
        "candidate1", "memoryA", "tenantA", "subjectA", "research", "agent",
        "rev1", contract.source_sha256, "synthetic://fixture-pointer", "b" * 64,
        "policy1", "consent1", None, "TW", 80,
    )
    review = ReviewerDecisionFixture(
        "candidate1", "reviewerA", "APPROVE", "tenantA", "subjectA",
        "research", "rev1", contract.source_sha256, "b" * 64, "policy1",
        "consent1", None, "TW", 1, 70, independently_reviewed=True,
    )
    accepted = boundary.propose(candidate, review, now=10)
    auth = ReadFixture(
        "tenantA", "subjectA", "research", "principalA", 10,
        "rev1", contract.source_sha256, "policy1", "consent1", None,
        "TW", True, True,
    )
    ledger = DurableMemoryExclusion(runtime.writer, boundary, contract.identity)
    ticket = ledger.register_reviewed(
        accepted, auth, consent_generation=1, source_pin="sourceA",
    )
    return ledger, ticket, auth


def test_qa_cross_module_sqlite_budget_native_exact_citations_and_flush(tmp_path):
    runtime, contract = make(tmp_path)
    memory = memory_bundle(runtime, contract)
    kwargs = qa_bundle(runtime, contract)
    outcome, state, budget = runtime.qa(contract, **kwargs, memory=memory)
    assert outcome.status == "QA_LOCAL_FLUSH_ONLY_CLIENT_ACK_OPEN"
    assert state.status == "terminal"
    assert state.client_delivery == "client_delivery_unverified"
    assert outcome.first_text_flushed_preterminal
    assert outcome.original_citation_sha256 == (digest(SOURCE),)
    assert budget.head.spent == 18 and budget.head.reserved == 0
    assert runtime.writer.recover(contract.identity)["outbox"][0]["state"] == "POSSIBLY_SENT"
    assert kwargs["transport"].events[0][0] == "enqueue"
    assert kwargs["transport"].events[1][0] == "flush"
    with pytest.raises(I02Denied, match="UNKNOWN_EFFECT"):
        I02LocalRuntimeV1(
            DurableWriterV1(runtime.writer.path, fixture_approval_mode=True)
        ).admit(replace(contract, journal_head=runtime.writer.read_head(contract.identity)))


def test_research_cross_module_sqlite_reservation_checkpoint_resume_artifact(tmp_path):
    runtime, contract = make(tmp_path, kind="RES-L")
    kwargs = research_bundle(contract)
    outcome, artifact, resumed = runtime.research_workflow(contract, **kwargs)
    assert outcome.status == "RESEARCH_LOCAL_ARTIFACT_ONLY"
    assert b"COUNTER" in artifact and b"SUPPORT" in artifact
    assert resumed["checkpoint_count"] == 2 and not resumed["dispatch_authorized"]
    assert outcome.artifact_sha256 == digest(artifact)
    assert runtime.writer.read_head(contract.identity).reserved == 20
    reopened = I02LocalRuntimeV1(
        DurableWriterV1(runtime.writer.path, fixture_approval_mode=True)
    )
    assert reopened.research.read_artifact(kwargs["plan"]) == artifact


def test_coding_cross_module_real_subprocess_permit_observer_verifier_journal(tmp_path):
    runtime, contract = make(tmp_path, kind="CODE-L", budget=3, exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    outcome, result = runtime.coding(contract, **kwargs)
    assert outcome.status == "CODING_LOCAL_VERIFIED_FIXTURE_ONLY"
    assert result.stdout_bytes == b"FIXTURE_OK\n" and result.exit_code == 0
    assert result.attempts == 1 and result.ephemeral_cleaned
    assert outcome.head.state == "LOCAL_VERIFIED_APPLIED" and outcome.head.spent == 1
    assert runtime.writer.recover(contract.identity)["outbox"][0]["state"] == "T4_RECORDED"


@pytest.mark.parametrize(("field", "replacement"), [
    ("actor_id", "other"),
    ("delegated_by", "principalA"),
    ("task_contract_id", ""),
    ("source_revision", "stale"),
    ("source_sha256", "wrong"),
    ("consent_generation", 2),
    ("exclusion_generation", 3),
    ("lease_epoch", 9),
    ("purpose", ""),
    ("now", -1),
    ("deadline", 10),
    ("source_acl_expires", 10),
    ("source_acl_current", False),
    ("fixture_only", False),
    ("workload", "UNKNOWN"),
])
def test_admission_rejects_broken_binding(tmp_path, field, replacement):
    runtime, contract = make(tmp_path)
    with pytest.raises(I02Denied):
        runtime.admit(replace(contract, **{field: replacement}))


@pytest.mark.parametrize(("field", "replacement"), [
    ("run_id", "other"),
    ("principal_id", "stranger"),
    ("tenant_id", "wrong"),
    ("task_version", 2),
])
def test_admission_rejects_cross_identity(tmp_path, field, replacement):
    runtime, contract = make(tmp_path)
    with pytest.raises((I02Denied, FenceError)):
        runtime.admit(replace(
            contract, identity=replace(contract.identity, **{field: replacement}),
        ))


@pytest.mark.parametrize(("field", "replacement"), [
    ("source_revision", "other"),
    ("consent_generation", 2),
    ("exclusion_generation", 3),
])
def test_durable_authority_drift_denied(tmp_path, field, replacement):
    runtime, contract = make(tmp_path)
    head = runtime.writer.update_authority(
        contract.identity, contract.journal_head,
        source_revision="other" if field == "source_revision" else "rev1",
        consent_generation=2 if field == "consent_generation" else 1,
        exclusion_generation=3 if field == "exclusion_generation" else 0,
    )
    with pytest.raises(I02Denied):
        runtime.admit(replace(contract, journal_head=head))


def test_qa_revocation_between_enqueue_and_flush_denies(tmp_path):
    runtime, contract = make(tmp_path)
    memory = memory_bundle(runtime, contract)
    kwargs = qa_bundle(runtime, contract)
    def revoke(_frame):
        memory[0].revoke(
            Revocation("revoked", "tenantA", "subjectA", "memoryA",
                       "CONSENT_WITHDRAWN", 20, True),
            consent_generation=2, expected_generation=0,
        )
    kwargs["transport"].on_enqueue = revoke
    with pytest.raises((I02Denied, DurableMemoryDenied)):
        runtime.qa(contract, **kwargs, memory=memory)
    assert not any(e[0] == "flush" for e in kwargs["transport"].events)
    assert runtime.writer.recover(contract.identity)["revoked"]
    assert not memory[0].restore_snapshot_allowed(
        "memoryA", memory[2], snapshot_generation=0
    )


def test_qa_invalid_original_citation_span_denied(tmp_path):
    runtime, contract = make(tmp_path)
    kwargs = qa_bundle(runtime, contract)
    proposal = kwargs["proposal"]
    link = proposal.links[0]
    kwargs["proposal"] = replace(proposal, links=(
        replace(link, citation=replace(
            link.citation, original_claim_bytes=b"fabrication"
        )),))
    with pytest.raises(StreamDenied):
        runtime.qa(contract, **kwargs)


def test_qa_missing_client_ack_never_claimed(tmp_path):
    runtime, contract = make(tmp_path)
    kwargs = qa_bundle(runtime, contract)
    outcome, state, _ = runtime.qa(contract, **kwargs)
    assert not outcome.client_ack and outcome.server_flush_only
    assert state.client_delivery == "client_delivery_unverified"


def test_qa_fault_after_enqueue_remains_unknown(tmp_path):
    runtime, contract = make(tmp_path)
    kwargs = qa_bundle(runtime, contract)
    kwargs["transport"].fail_flush = True
    with pytest.raises(OSError, match="ambiguous"):
        runtime.qa(contract, **kwargs)
    recovered = runtime.compute.recover(contract.identity, "request-one")
    assert recovered.status == "RECOVERY_PAUSE_NO_RETRY"
    with pytest.raises(I02Denied):
        runtime.admit(replace(
            contract, journal_head=runtime.writer.read_head(contract.identity)
        ))


@pytest.mark.parametrize(("stage", "mutation"), [
    ("expired", {"valid_until": 1}),
    ("acl", {"acl_principals": ("intruder",)}),
    ("purpose", {"purposes": ("other",)}),
    ("tainted", {"tainted": True}),
    ("consent", {"consent_generation": 3}),
    ("exclusion", {"exclusion_generation": 5}),
])
def test_research_external_source_drift_or_acl_denied(tmp_path, stage, mutation):
    runtime, contract = make(tmp_path, kind="RES-L")
    kwargs = research_bundle(contract)
    pins = kwargs["plan"].source_pins
    kwargs["plan"] = replace(kwargs["plan"], source_pins=(
        replace(pins[0], **mutation), pins[1],
    ))
    with pytest.raises((I02Denied, ResearchDenied)):
        runtime.research_workflow(contract, **kwargs)


def test_research_corrupted_checkpoint_denied_after_reopen(tmp_path):
    runtime, contract = make(tmp_path, kind="RES-L")
    kwargs = research_bundle(contract)
    runtime.research_workflow(contract, **kwargs)
    with sqlite3.connect(runtime.writer.path) as db:
        db.execute(
            "UPDATE research_checkpoints SET digest=? WHERE tenant=? AND run=?"
            " AND ordinal=1", ("f" * 64, "tenantA", "runA"),
        )
    with pytest.raises(ResearchDenied, match="CHECKPOINT_CHAIN_CORRUPT"):
        runtime.research.resume(kwargs["plan"], now=10)


def test_research_counterevidence_review_missing_denied(tmp_path):
    runtime, contract = make(tmp_path, kind="RES-L")
    kwargs = research_bundle(contract)
    kwargs["reviews"] = kwargs["reviews"][:1]
    with pytest.raises(ResearchDenied, match="SOURCE_OR_COUNTEREVIDENCE_MISSING"):
        runtime.research_workflow(contract, **kwargs)


def test_research_unknown_remote_claim_not_replayed(tmp_path):
    runtime, contract = make(tmp_path, kind="RES-L")
    kwargs = research_bundle(contract)
    runtime.research.admit(kwargs["plan"], now=10)
    runtime.research.claim_job(
        kwargs["plan"], job_id="maybe", intent_sha="a" * 64, now=10,
    )
    with pytest.raises(ResearchDenied, match="UNKNOWN_REMOTE_EFFECT"):
        runtime.research.resume(kwargs["plan"], now=10)


@pytest.mark.parametrize(("field", "value"), [
    ("idempotency_key", "../escape"),
    ("idempotency_key", "dup/permit"),
    ("program_id", "shell"),
    ("command_id", "not-fixed"),
    ("expected_source_sha256", "f" * 64),
])
def test_coding_path_escape_permit_and_source_denied(tmp_path, field, value):
    runtime, contract = make(tmp_path, kind="CODE-L", budget=3, exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    kwargs["task"] = replace(kwargs["task"], **{field: value})
    with pytest.raises((I02Denied, ValueError)):
        runtime.coding(contract, **kwargs)


def test_coding_forged_verifier_denied(tmp_path):
    runtime, contract = make(tmp_path, kind="CODE-L", budget=3, exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    kwargs["verifier"] = object()
    with pytest.raises((I02Denied, ValueError)):
        runtime.coding(contract, **kwargs)


def test_coding_snapshot_lease_takeover_denied(tmp_path):
    runtime, contract = make(tmp_path, kind="CODE-L", budget=3, exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    runtime.writer.takeover(contract.identity, contract.journal_head)
    with pytest.raises(I02Denied):
        runtime.coding(contract, **kwargs)


def test_coding_duplicate_permit_after_terminal_denied(tmp_path):
    runtime, contract = make(tmp_path, kind="CODE-L", budget=3, exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    runtime.coding(contract, **kwargs)
    with pytest.raises(I02Denied):
        runtime.coding(contract, **kwargs)


def test_coding_nonzero_exit_durable_unknown_not_success(tmp_path):
    runtime, contract = make(tmp_path, kind="CODE-L", budget=3, exclusion=1)
    kwargs, source_hash = coding_bundle(runtime, contract, tmp_path)
    contract = replace(contract, source_sha256=source_hash)
    kwargs["task"] = replace(kwargs["task"], expected_value=6)
    fresh_intent = kwargs["runner"].prepare(kwargs["task"])
    kwargs["approval"] = replace(
        kwargs["approval"], intent_digest=fresh_intent.request.digest(),
    )
    outcome, result = runtime.coding(contract, **kwargs)
    assert outcome.status == "UNKNOWN_EFFECT_NO_AUTORETRY"
    assert result.outcome == "TEST_FAILED_NONTERMINAL"
    assert runtime.writer.read_head(contract.identity).state == "OPEN"


def test_budget_multiworker_cas_race_fences_double_reserve(tmp_path):
    runtime, contract = make(tmp_path)
    a = attempt_for(contract)
    def reserve(_):
        writer = DurableWriterV1(runtime.writer.path, fixture_approval_mode=True)
        return I02LocalRuntimeV1(writer).compute.reserve_and_fence(a)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve, n) for n in range(2)]
    outcomes = []
    for future in futures:
        with suppress(BudgetFence, FenceError):
            outcomes.append(future.result())
    assert len(outcomes) == 1
    assert runtime.writer.read_head(contract.identity).reserved == 20


def test_double_invoice_conflicting_evidence_denied(tmp_path):
    runtime, contract = make(tmp_path)
    kwargs = qa_bundle(runtime, contract)
    runtime.qa(contract, **kwargs)
    with pytest.raises(BudgetFence):
        runtime.compute.settle(
            contract.identity, "request-one",
            replace(kwargs["invoice"], usage_id="different-usage"),
            charge_id="charge-two",
        )


def test_unknown_price_never_zero_cost(tmp_path):
    runtime, contract = make(tmp_path)
    kwargs = qa_bundle(runtime, contract)
    a = kwargs["attempt"]
    kwargs["attempt"] = replace(a, prices=())
    with pytest.raises(BudgetFence):
        runtime.qa(contract, **kwargs)
    assert runtime.writer.read_head(contract.identity).spent == 0


def test_research_crash_reopen_reserved_not_double_reserved(tmp_path):
    runtime, contract = make(tmp_path, kind="RES-L")
    kwargs = research_bundle(contract)
    runtime.research.admit(kwargs["plan"], now=10)
    runtime.research.reserve_budget(kwargs["plan"], now=10)
    recovered = I02LocalRuntimeV1(
        DurableWriterV1(runtime.writer.path, fixture_approval_mode=True)
    )
    recovered.research.reserve_budget(kwargs["plan"], now=10)
    assert recovered.writer.read_head(contract.identity).reserved == 20


def test_terminal_cas_race_does_not_grant_read(tmp_path):
    runtime, contract = make(tmp_path)
    current = runtime.writer.read_head(contract.identity)
    runtime.writer.takeover(contract.identity, current)
    with pytest.raises(I02Denied):
        runtime.admit(contract)
