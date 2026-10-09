"""Offline cross-stage diagnostic: no real admission, provider or publication.

This module intentionally PROVES a blocked AR02 terminal transition; it is not
a functioning or authorized AR02–AR05 happy-path adapter.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel
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
    JournalSnapshot,
    NativeEvidenceFixture,
    PublicationCandidate,
    VerificationDenied,
    VerificationPublicationGate,
    VerificationReceipt,
    verification_message,
)
from knowledge_engine.m27_ar09_oracle_experimental import remote_unknown_oracle

MOCK_ONLY_UNAUTHORIZED_FOR_REAL_EFFECT = True
_FAKE_KEY = b"ar02-ar05-offline-test-key-not-authority"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    label: str
    selected_revision: str
    observer_effect: str
    action_proposal_terminal: bool
    ar05_denial: str
    ar02_denial: str
    head: int
    terminal: bool
    provider_calls: int
    real_admission_authorized: bool = False


def probe_observed_t3_cannot_terminal() -> Diagnostic:
    """Exercise real accepted public APIs, never bypassing the missing AR02 API.

    Even with a separately configured *fake* AR04 observer reporting applied,
    AR02 possible_send permanently fences terminal.  Neither the caller's
    test-grant boolean, AR02 trusted=True fixture, fake observer identity nor
    AR05 HMAC key is independent external authorization.
    """
    now = 100
    tenant, principal, run = "tenant-fixture", "principal-fixture", "run-fixture"
    source_bytes = b"synthetic source fixture bytes"
    digest = hashlib.sha256(source_bytes).hexdigest()
    request = Request(tenant, principal, "qa", frozenset({"source"}), now, 8, 4, 30)
    grant = GrantFixture(
        tenant, principal, "qa", frozenset({"source"}), 130,
        externally_authenticated=True,
    )
    candidate = Candidate(
        "source", "source-id", "revision-1", digest, tenant,
        frozenset({principal}), "qa", 125, 95, 3, 2,
        consent_expires=120,
    )
    selected = select(request, (candidate,), grant)
    assert selected.selected == (candidate,)
    # Re-check at consume; this is only a scoped synthetic grant.
    consume = select(request, selected.selected, grant)
    assert consume.selected == (candidate,)

    kernel = Kernel(budget=4)
    kernel.create(run, tenant)
    kernel.reserve(run, tenant, 0, 1, "reserve-fixture", 2)
    assert kernel.charge(run, tenant, 1, 1, "reserve-fixture", "charge-fixture", 2)
    action = InertSafeActionBoundary(
        trusted_policy_issuer="fixture-policy",
        trusted_approval_issuers=frozenset({"fixture-approval"}),
        trusted_observers=frozenset({"fixture-observer"}),
        trusted_verifier_keys=frozenset({"fixture-verifier-key"}),
        executor_id="generator-fixture",
    )
    intent = ActionIntent(
        "intent-fixture", run, tenant, principal, None,
        "capability-fixture", "v1", "read-only-fixture", "resource-fixture",
        "arguments-ref", "0" * 64, "idempotency-fixture", "reversible",
        "approval-fixture", now, 150, "policy-fixture", 1, 1,
    )
    policy = PolicyFixture(
        "fixture-policy", tenant, principal, None, 150,
        frozenset({"capability-fixture"}), frozenset({"resource-fixture"}),
        1, 4, 2,
    )
    intent_candidate = action.register_intent(
        command_id="command-fixture", intent=intent, policy=policy, now=now,
    )
    kernel.intent(
        run, tenant, 2, 1, intent.intent_id, intent_candidate.intent_digest,
        intent.approval_id, trusted=True,
    )
    approval = ApprovalFixture(
        intent.approval_id, intent_candidate.intent_digest, tenant,
        "independent-fixture-approver", "fixture-approval", 150,
    )
    claim = action.claim_dispatch(
        intent_id=intent.intent_id, claim_id="claim-fixture", approval=approval,
        expected_epoch=1, physical_attempt=1, now=now,
    )
    kernel.claim(run, tenant, 3, 1, intent.intent_id, claim.intent_digest, trusted=True)
    action.cross_send_boundary(claim_id=claim.claim_id, current_epoch=1)
    assert kernel.possible_send(run, tenant, 4, 1, intent.intent_id) == "UNKNOWN_EFFECT"
    observed = action.reconcile(evidence=ObserverEvidence(
        "fixture-observer", tenant, intent.intent_id, intent.resource_id,
        "applied", digest, independent=True,
    ))
    proposal = action.propose_verification(
        intent_id=intent.intent_id, verifier_id="fixture-verifier",
        verifier_key_id="fixture-verifier-key",
    )
    state = kernel.read(run, tenant)
    snapshot = JournalSnapshot(
        tenant, "task-fixture", 1, run, 1, state["head"], "a" * 64,
        state["epoch"], "outcome-fixture", "b" * 64,
        unknown_effect=bool(state["unknown"]),
        terminal=state["terminal"],
    )
    original = NativeEvidenceFixture(
        "native", source_bytes, digest,
        (CitationBinding("citation-fixture", candidate.source_id, candidate.revision,
                         digest, 0, 9),),
    )
    publication = PublicationCandidate(
        "publication-fixture", "segment-fixture", 1, False, True,
        original, original, ("citation-fixture",),
        (
            ContentFrame("frame-verified", "verified_text", b"fixture text",
                         ("citation-fixture",), "verification-fixture", True,
                         "client-ack-fixture"),
            ContentFrame("frame-terminal", "terminal", b"", (), None, True, None),
        ),
    )
    unsigned = VerificationReceipt(
        "verification-fixture", "fixture-verifier", "fixture-verifier-key",
        tenant, "task-fixture", 1, run, 1, "outcome-fixture", "b" * 64,
        state["head"], "a" * 64, state["epoch"], now, 130,
        (HardGate("source", "pass"), HardGate("policy", "pass")), "",
    )
    receipt = VerificationReceipt(
        *tuple(getattr(unsigned, field) for field in unsigned.__dataclass_fields__
               if field != "signature"),
        hmac.new(_FAKE_KEY, verification_message(unsigned), hashlib.sha256).hexdigest(),
    )
    gate = VerificationPublicationGate(
        verifier_keys={"fixture-verifier-key": _FAKE_KEY},
        signer_for_key={"fixture-verifier-key": "fixture-verifier"},
        generator_id="generator-fixture",
    )
    try:
        gate.evaluate(snapshot=snapshot, receipt=receipt, publication=publication, now=now)
    except VerificationDenied as exc:
        ar05_denial = exc.code
    else:
        ar05_denial = "UNEXPECTED_ACCEPTANCE"
    try:
        kernel.terminal(
            run, tenant, state["head"], state["epoch"], state["head"], trusted=True
        )
    except Denied as exc:
        ar02_denial = str(exc)
    else:
        ar02_denial = "UNEXPECTED_TERMINAL"

    oracle = remote_unknown_oracle(t3_crossed=True, ack_lost=True)
    assert oracle.reason == "POSSIBLY_SENT_NO_BLIND_RETRY"
    after = kernel.read(run, tenant)
    return Diagnostic(
        label="BLOCKED_INTERFACE_GAP",
        selected_revision=selected.selected[0].revision,
        observer_effect=observed.effect,
        action_proposal_terminal=proposal.terminal_committed,
        ar05_denial=ar05_denial,
        ar02_denial=ar02_denial,
        head=after["head"],
        terminal=after["terminal"],
        provider_calls=kernel.network_requests + action.provider_calls + gate.provider_calls,
    )
