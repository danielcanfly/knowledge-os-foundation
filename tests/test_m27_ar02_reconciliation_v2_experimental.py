"""C02 in-memory successor negative matrix; never an attested trust test."""
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_ar05_reconciled_vertical_experimental import (
    prepare_mock_loop,
    sign_observation,
)
from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel
from knowledge_engine.m27_ar02_reconciliation_v2_experimental import (
    REAL_ATTESTED_AUTHORITY,
    TEST_TRUSTED_OBSERVER_FIXTURE,
    ReconciliationKernelV2,
)


def reconcile(loop, observation=None, head=5, epoch=1, now=100):
    return loop.v2.record_verified_reconciliation(
        observation=observation or loop.observation,
        expected_head=head, epoch=epoch, now=now,
    )


def test_red_first_accepted_public_kernel_terminal_is_blocked():
    k = Kernel(4)
    k.create("r", "t")
    k.intent("r", "t", 0, 1, "i", "digest", "approval", trusted=True)
    k.claim("r", "t", 1, 1, "i", "digest", trusted=True)
    assert k.possible_send("r", "t", 2, 1, "i") == "UNKNOWN_EFFECT"
    with pytest.raises(Denied, match="unknown effect"):
        k.terminal("r", "t", 3, 1, 3, trusted=True)


def test_positive_reconciliation_keeps_original_unknown_event_and_digest():
    loop = prepare_mock_loop()
    previous = loop.v2.history[0]
    result = reconcile(loop)
    assert result.trust_grade == TEST_TRUSTED_OBSERVER_FIXTURE
    assert not REAL_ATTESTED_AUTHORITY
    assert result.effect == "CONFIRMED_APPLIED"
    assert result.original_t1_digest == previous.original_t1_digest
    assert loop.v2.head == 6 and len(loop.v2.history) == 2
    assert loop.v2.history[0] == previous
    assert loop.kernel.read("run-fixture", "tenant-fixture")["unknown"]
    assert loop.kernel.read("run-fixture", "tenant-fixture")["head"] == 5
    assert loop.kernel.network_requests == loop.action.provider_calls == 0
    assert loop.kernel.read("run-fixture", "tenant-fixture")["charges"] == {
        "charge-fixture": ("reserve-fixture", 2)
    }


def test_same_observation_idempotent_but_conflicting_observation_denied():
    loop = prepare_mock_loop()
    first = reconcile(loop)
    assert reconcile(loop) == first
    assert len(loop.v2.history) == 2
    other = sign_observation(replace(loop.observation, observation_id="obs-other"))
    with pytest.raises(Denied, match="CONFLICTING_OBSERVATION"):
        reconcile(loop, other)
    assert len(loop.v2.history) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observation_id", ""),
        ("run_id", "other-run"),
        ("tenant_id", "other-tenant"),
        ("intent_id", "other-intent"),
        ("original_t1_digest", "tampered"),
        ("expected_head", 4),
        ("lease_epoch", 2),
        ("source_id", "other-source"),
        ("source_revision", "revoked-revision"),
        ("source_digest", "f" * 64),
        ("exclusion_generation", 0),
        ("captured_at", 101),
        ("expires_at", 100),
        ("observer_key_id", "unknown-observer"),
    ],
)
def test_observation_binding_matrix_fail_closed(field, value):
    loop = prepare_mock_loop()
    obs = sign_observation(replace(loop.observation, **{field: value}))
    with pytest.raises(Denied):
        reconcile(loop, obs)
    assert loop.v2.head == 5 and len(loop.v2.history) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observer_id", "fake"),
        ("tenant_id", "wrong"),
        ("intent_id", "wrong"),
        ("resource_id", "wrong"),
        ("status", "absent_uncertain"),
        ("independent", False),
        ("observation_digest", ""),
        ("status", "not_applied"),
    ],
)
def test_adversarial_ar04_evidence_rejected(field, value):
    loop = prepare_mock_loop()
    e = replace(loop.observation.evidence, **{field: value})
    obs = sign_observation(replace(loop.observation, evidence=e))
    with pytest.raises(Denied):
        reconcile(loop, obs)
    assert loop.v2.head == 5


@pytest.mark.parametrize("now,head,epoch", [
    (100, 4, 1), (100, 6, 1), (100, 5, 0),
    (100, 5, 2), (99, 5, 1), (141, 5, 1),
])
def test_stale_epoch_head_clock_consent(now, head, epoch):
    loop = prepare_mock_loop()
    with pytest.raises(Denied):
        reconcile(loop, head=head, epoch=epoch, now=now)
    assert len(loop.v2.history) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": "rev-2"}, {"digest": "c" * 64},
        {"exclusion_generation": 2}, {"excluded": True},
        {"revoked": True}, {"consent_expires_at": 99},
        {"source_expires_at": 99}, {"retrieved_at": 120},
    ],
)
def test_source_consent_exclusion_authority_freshness(changes):
    loop = prepare_mock_loop()
    loop.source.replace(**changes)
    with pytest.raises(Denied):
        reconcile(loop)
    assert loop.v2.head == 5


def test_forged_signature_and_missing_observer_denied():
    loop = prepare_mock_loop()
    with pytest.raises(Denied, match="FORGED_OBSERVER"):
        reconcile(loop, replace(loop.observation, signature="0" * 64))
    with pytest.raises(Denied):
        reconcile(loop, replace(loop.observation, signature=""))


def test_negative_proof_requires_independent_visibility_and_cannot_succeed():
    loop = prepare_mock_loop()
    e = replace(
        loop.observation.evidence, status="not_applied",
        authoritative_negative=True, visibility_complete=True,
    )
    obs = sign_observation(replace(loop.observation, evidence=e))
    result = reconcile(loop, obs)
    assert result.effect == "CONFIRMED_NOT_APPLIED"
    assert loop.v2.head == 6


def test_accepted_legacy_drift_fences_successor_without_mutating_legacy():
    loop = prepare_mock_loop()
    loop.kernel.takeover("run-fixture", "tenant-fixture", 5)
    with pytest.raises(Denied, match="KERNEL_DRIFT"):
        reconcile(loop)
    assert loop.v2.head == 5


def test_misbound_legacy_original_digest_fails_constructor():
    loop = prepare_mock_loop()
    old = loop.v2
    with pytest.raises(Denied, match="ORIGINAL_T3"):
        ReconciliationKernelV2(
            kernel=loop.kernel, run_id=old.run_id, tenant_id=old.tenant_id,
            intent_id=old.intent_id, original_t1_digest="forged",
            ar04=loop.action, request=old._request, candidate=old._candidate,
            grant=old._grant, context_authority=loop.source,
            observer_keys={"fixture-observer": b"key"},
            verifier_keys={"fixture-verifier-key": b"key"},
            signer_for_key={"fixture-verifier-key": "fixture-verifier"},
            generator_id="generator", task_id="task-fixture",
            task_version=1, attempt=1, outcome_id="outcome-fixture",
            outcome_digest="b" * 64, now=100,
        )


def test_reconciliation_duplicate_replay_with_changed_head_epoch_denied():
    loop = prepare_mock_loop()
    reconcile(loop)
    for head, epoch, now in [(6, 1, 101), (5, 2, 101), (5, 1, 99)]:
        with pytest.raises(Denied, match="DUPLICATE_STALE_REPLAY"):
            reconcile(loop, head=head, epoch=epoch, now=now)
    assert loop.v2.head == 6
