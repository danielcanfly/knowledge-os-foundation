"""MOCK_ONLY C02 synthetic AR02C→AR03A→AR04A→v2→AR05A→sidecar loop."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace

from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel
from knowledge_engine.m27_ar02_reconciliation_v2_experimental import (
    ObservationV2,
    ReconciliationKernelV2,
    SourceState,
    TestOnlyContextAuthority,
    observation_message,
)
from knowledge_engine.m27_ar03_context_broker_experimental import (
    Candidate,
    GrantFixture,
    Request,
    select,
)
from knowledge_engine.m27_ar04_safe_action_experimental import (
    ActionIntent,
    ApprovalFixture,
    InertSafeActionBoundary,
    ObserverEvidence,
    PolicyFixture,
)
from knowledge_engine.m27_ar05_verification_experimental import (
    CitationBinding,
    ContentFrame,
    HardGate,
    NativeEvidenceFixture,
    PublicationCandidate,
    VerificationReceipt,
    verification_message,
)
from knowledge_engine.m27_ar09_oracle_experimental import remote_unknown_oracle

MOCK_ONLY_UNAUTHORIZED_FOR_REAL_EFFECT = True
OBSERVER_SECRET = b"C02-fixture-observer-key-NOT-REAL-IDENTITY"
VERIFIER_SECRET = b"C02-fixture-verifier-key-NOT-REAL-IDENTITY"


@dataclass(slots=True)
class PreparedLoop:
    kernel: Kernel
    v2: ReconciliationKernelV2
    action: InertSafeActionBoundary
    source: TestOnlyContextAuthority
    observation: ObservationV2
    publication: PublicationCandidate
    receipt: VerificationReceipt


def sign_observation(obs: ObservationV2) -> ObservationV2:
    return replace(
        obs, signature=hmac.new(
            OBSERVER_SECRET, observation_message(obs), hashlib.sha256
        ).hexdigest(),
    )


def sign_verification(r: VerificationReceipt) -> VerificationReceipt:
    return replace(
        r, signature=hmac.new(
            VERIFIER_SECRET, verification_message(r), hashlib.sha256
        ).hexdigest(),
    )


def prepare_mock_loop(now: int = 100) -> PreparedLoop:
    """Exercise original public APIs; Kernel remains UNKNOWN after T3."""
    tenant, run, principal = "tenant-fixture", "run-fixture", "principal-fixture"
    raw = b"mock native source fixture original bytes"
    digest = hashlib.sha256(raw).hexdigest()
    request = Request(tenant, principal, "qa", frozenset({"source"}), now, 8, 4, 30)
    grant = GrantFixture(
        tenant, principal, "qa", frozenset({"source"}), 150, True
    )
    candidate = Candidate(
        "source", "source-id", "revision-1", digest, tenant,
        frozenset({principal}), "qa", 145, 95, 3, 2,
        consent_expires=140,
    )
    assert select(request, (candidate,), grant).selected == (candidate,)
    source = TestOnlyContextAuthority(SourceState(
        candidate.source_id, candidate.revision, candidate.digest, 1,
        140, 145, 95,
    ))
    kernel = Kernel(budget=4)
    kernel.create(run, tenant)
    kernel.reserve(run, tenant, 0, 1, "reserve-fixture", 2)
    assert kernel.charge(run, tenant, 1, 1, "reserve-fixture", "charge-fixture", 2)
    action = InertSafeActionBoundary(
        trusted_policy_issuer="fixture-policy",
        trusted_approval_issuers=frozenset({"fixture-approval"}),
        trusted_observers=frozenset({"fixture-observer"}),
        trusted_verifier_keys=frozenset({"fixture-verifier-key"}),
        executor_id="fixture-generator",
    )
    intent = ActionIntent(
        "intent-fixture", run, tenant, principal, None, "capability-fixture",
        "v1", "read-only-fixture", "resource-fixture", "arguments-ref",
        "0" * 64, "idempotency-fixture", "reversible", "approval-fixture",
        now, 150, "policy-fixture", 1, 1,
    )
    policy = PolicyFixture(
        "fixture-policy", tenant, principal, None, 150,
        frozenset({"capability-fixture"}), frozenset({"resource-fixture"}),
        1, 4, 2,
    )
    t1 = action.register_intent(
        command_id="command-fixture", intent=intent, policy=policy, now=now
    )
    kernel.intent(
        run, tenant, 2, 1, intent.intent_id, t1.intent_digest,
        intent.approval_id, trusted=True,
    )
    claim = action.claim_dispatch(
        intent_id=intent.intent_id, claim_id="claim-fixture",
        approval=ApprovalFixture(
            intent.approval_id, t1.intent_digest, tenant, "fixture-approver",
            "fixture-approval", 150,
        ),
        expected_epoch=1, physical_attempt=1, now=now,
    )
    kernel.claim(run, tenant, 3, 1, intent.intent_id, claim.intent_digest, trusted=True)
    action.cross_send_boundary(claim_id=claim.claim_id, current_epoch=1)
    assert kernel.possible_send(run, tenant, 4, 1, intent.intent_id) == "UNKNOWN_EFFECT"
    try:
        kernel.terminal(run, tenant, 5, 1, 5, trusted=True)
    except Denied:
        pass
    else:
        raise AssertionError("RED_EXPECTED: accepted AR02C must deny terminal")
    oracle = remote_unknown_oracle(t3_crossed=True, ack_lost=True)
    assert oracle.reason == "POSSIBLY_SENT_NO_BLIND_RETRY"

    v2 = ReconciliationKernelV2(
        kernel=kernel, run_id=run, tenant_id=tenant, intent_id=intent.intent_id,
        original_t1_digest=t1.intent_digest, ar04=action, request=request,
        candidate=candidate, grant=grant, context_authority=source,
        observer_keys={"fixture-observer": OBSERVER_SECRET},
        verifier_keys={"fixture-verifier-key": VERIFIER_SECRET},
        signer_for_key={"fixture-verifier-key": "fixture-verifier"},
        generator_id="fixture-generator", task_id="task-fixture",
        task_version=1, attempt=1, outcome_id="outcome-fixture",
        outcome_digest="b" * 64, now=now,
    )
    evidence = ObserverEvidence(
        "fixture-observer", tenant, intent.intent_id, intent.resource_id,
        "applied", digest, independent=True,
    )
    observation = sign_observation(ObservationV2(
        "observation-fixture", run, tenant, intent.intent_id,
        t1.intent_digest, 5, 1, candidate.source_id, candidate.revision,
        candidate.digest, 1, now, 130, "fixture-observer", evidence,
    ))
    source_evidence = NativeEvidenceFixture(
        "native", raw, digest,
        (CitationBinding("cite-fixture", candidate.source_id,
                         candidate.revision, digest, 0, 10),),
    )
    publication = PublicationCandidate(
        "publication-fixture", "segment-fixture", 1, False, True,
        source_evidence, source_evidence, ("cite-fixture",),
        (
            ContentFrame(
                "verified-fixture", "verified_text", b"cited fixture answer",
                ("cite-fixture",), "verification-fixture", True, "mock-client-ack",
            ),
            ContentFrame("terminal-fixture", "terminal", b"", (), None, True, None),
        ),
    )
    # Construct against the NEXT head, which only exists after reconciliation.
    unsigned = VerificationReceipt(
        "verification-fixture", "fixture-verifier", "fixture-verifier-key",
        tenant, "task-fixture", 1, run, 1, "outcome-fixture", "b" * 64,
        6, "", 1, now, 130,
        (
            HardGate("source", "pass"), HardGate("policy", "pass"),
            HardGate("effect", "pass"), HardGate("approval", "pass"),
            HardGate("client_ack", "pass"),
        ),
        "",
    )
    return PreparedLoop(kernel, v2, action, source, observation, publication, unsigned)


def complete_mock_loop() -> tuple[PreparedLoop, object, object]:
    loop = prepare_mock_loop()
    result = loop.v2.record_verified_reconciliation(
        observation=loop.observation, expected_head=5, epoch=1, now=100,
    )
    signed = sign_verification(replace(
        loop.receipt, journal_head_seq=loop.v2.head,
        journal_head_hash=loop.v2.head_hash,
    ))
    terminal = loop.v2.terminal_cas(
        expected_head=6, epoch=1, receipt=signed,
        publication=loop.publication, now=101, status="SUCCEEDED",
    )
    notice = loop.v2.append_postterminal_notice(kind="correction", content=b"revision")
    assert result.head_seq == 6 and terminal.head_seq == 7
    assert not loop.kernel.read("run-fixture", "tenant-fixture")["terminal"]
    assert loop.kernel.read("run-fixture", "tenant-fixture")["unknown"]
    return loop, terminal, notice
