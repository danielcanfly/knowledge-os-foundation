"""Cross-module acceptance-negative proofs for the approved inert AR02/AR03 sources.

These tests are GREEN when the absence of a trustworthy T3->AR02
reconciliation/terminal handoff is correctly rejected; they do not certify an
end-to-end runtime or real authority.
"""

from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_ar05_core_vertical_experimental import (
    MOCK_ONLY_UNAUTHORIZED_FOR_REAL_EFFECT,
    probe_observed_t3_cannot_terminal,
)
from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel
from knowledge_engine.m27_ar03_context_broker_experimental import (
    Candidate,
    GrantFixture,
    Request,
    preserve_native_pin,
    select,
)
from knowledge_engine.m27_ar05_verification_experimental import (
    VerificationDenied,
    VerificationPublicationGate,
)
from knowledge_engine.m27_ar09_oracle_experimental import (
    remote_unknown_oracle,
    two_writer_cas_oracle,
)


def request(now=100, **changes):
    fixture = Request(
        "tenant", "principal", "qa", frozenset({"source"}), now, 3, 2, 20,
    )
    return replace(fixture, **changes)


def candidate(**changes):
    fixture = Candidate(
        "source", "source-1", "revision-1", "a" * 64, "tenant",
        frozenset({"principal"}), "qa", 150, 95, 3, 2,
        consent_expires=120,
    )
    return replace(fixture, **changes)


def grant(**changes):
    fixture = GrantFixture(
        "tenant", "principal", "qa", frozenset({"source"}), 125, True,
    )
    return replace(fixture, **changes)


def test_red_proven_immutable_ar02_unknown_effect_blocks_terminal():
    result = probe_observed_t3_cannot_terminal()
    assert result.label == "BLOCKED_INTERFACE_GAP"
    assert result.selected_revision == "revision-1"
    assert result.observer_effect == "CONFIRMED_APPLIED"
    assert result.action_proposal_terminal is False
    assert result.ar05_denial == "UNKNOWN_EFFECT"
    assert "unknown effect" in result.ar02_denial
    assert result.head == 5 and result.terminal is False
    assert result.provider_calls == 0 and not result.real_admission_authorized
    assert MOCK_ONLY_UNAUTHORIZED_FOR_REAL_EFFECT is True
    assert not hasattr(Kernel, "reconcile_effect")


@pytest.mark.parametrize(
    ("req_change", "grant_change", "candidate_change"),
    [
        ({"tenant": "other"}, {}, {}),
        ({"principal": "other"}, {}, {}),
        ({}, {"principal": "other"}, {}),
        ({}, {}, {"tenant": "other"}),
        ({}, {}, {"principals": frozenset({"other"})}),
        ({}, {}, {"scope": "other"}),
        ({}, {"externally_authenticated": False}, {}),
        ({}, {"expires": 100}, {}),
    ],
)
def test_scoped_context_denies_untrusted_or_wrong_identity(
    req_change, grant_change, candidate_change
):
    actual = select(
        request(**req_change),
        (candidate(**candidate_change),),
        grant(**grant_change),
    )
    assert actual.selected == () and actual.omissions


@pytest.mark.parametrize(
    "change",
    [
        {"revoked": True},
        {"consent_expires": 100},
        {"revision": ""},
        {"digest": "not-a-sha"},
        {"expires": 100},
        {"retrieved": 70},
    ],
)
def test_consume_rejects_revocation_revision_and_stale_context(change):
    assert not select(request(), (candidate(**change),), grant()).selected


def test_revocation_between_resolution_and_consume_is_denied():
    selected = select(request(now=100), (candidate(),), grant())
    assert len(selected.selected) == 1
    assert not select(request(now=120), selected.selected, grant()).selected


def test_source_identity_pin_caller_boolean_is_not_real_authority():
    same = "a" * 64
    assert preserve_native_pin("source-1", same, "source-1", same, True) == "source-1"
    assert preserve_native_pin("source-1", same, "source-1", same) is None
    assert not probe_observed_t3_cannot_terminal().real_admission_authorized


def test_epoch_tenant_and_intent_digest_fences_in_same_ar02_kernel():
    kernel = Kernel(3)
    kernel.create("run", "tenant")
    kernel.intent("run", "tenant", 0, 1, "intent", "digest-1", "approval", trusted=True)
    with pytest.raises(Denied):
        kernel.claim("run", "tenant", 1, 1, "intent", "wrong-digest", trusted=True)
    with pytest.raises(Denied):
        kernel.claim("run", "other", 1, 1, "intent", "digest-1", trusted=True)
    kernel.takeover("run", "tenant", 1)
    with pytest.raises(Denied):
        kernel.claim("run", "tenant", 2, 1, "intent", "digest-1", trusted=True)
    assert kernel.read("run", "tenant")["epoch"] == 2


def test_budget_reservation_inconsistent_and_duplicate_billing():
    kernel = Kernel(3)
    kernel.create("run", "tenant")
    kernel.reserve("run", "tenant", 0, 1, "reserve", 3)
    with pytest.raises(Denied):
        kernel.reserve("run", "tenant", 1, 1, "another", 1)
    assert kernel.charge("run", "tenant", 1, 1, "reserve", "charge", 3) is True
    assert kernel.charge("run", "tenant", 2, 1, "reserve", "charge", 3) is False
    with pytest.raises(Denied):
        kernel.charge("run", "tenant", 2, 1, "reserve", "charge", 2)
    assert kernel.read("run", "tenant")["spent"] == 3


def test_duplicate_claim_and_unknown_outcome_never_silently_resend():
    kernel = Kernel(3)
    kernel.create("run", "tenant")
    kernel.intent("run", "tenant", 0, 1, "intent", "digest", "approval", trusted=True)
    kernel.claim("run", "tenant", 1, 1, "intent", "digest", trusted=True)
    with pytest.raises(Denied):
        kernel.claim("run", "tenant", 2, 1, "intent", "digest", trusted=True)
    assert kernel.possible_send("run", "tenant", 2, 1, "intent") == "UNKNOWN_EFFECT"
    with pytest.raises(Denied):
        kernel.terminal("run", "tenant", 3, 1, 3, trusted=True)
    assert remote_unknown_oracle(t3_crossed=True, ack_lost=True).send_count == 0


def test_independent_oracle_and_no_client_ack_are_not_real_delivery():
    oracle = two_writer_cas_oracle(42)
    assert oracle.commit_count == 1 and oracle.send_count == 0
    result = probe_observed_t3_cannot_terminal()
    assert result.ar05_denial == "UNKNOWN_EFFECT"
    assert result.real_admission_authorized is False


def test_append_only_notice_does_not_reopen_terminal():
    kernel = Kernel(1)
    kernel.create("run", "tenant")
    kernel.terminal("run", "tenant", 0, 1, 0, trusted=True)
    gate = VerificationPublicationGate(
        verifier_keys={}, signer_for_key={}, generator_id="generator-fixture"
    )
    notice = gate.append_terminal_notice(
        publication_id="publication", prior_revision=1, prior_cursor=3,
        kind="retraction", supersedes_segment_id="segment", content=b"withdrawn"
    )
    assert notice.revision == 2 and notice.cursor == 4
    assert notice.run_state_changed is False
    assert kernel.read("run", "tenant")["terminal"] is True
    with pytest.raises(Denied):
        kernel.cas("run", "tenant", 1, 1)
    with pytest.raises(VerificationDenied):
        gate.append_terminal_notice(
            publication_id="publication", prior_revision=1, prior_cursor=3,
            kind="retraction", supersedes_segment_id="", content=b"withdrawn",
        )
