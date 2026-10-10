"""K03V TEST_FIXTURE_ONLY: synthetic verifier, never Provider/IdP authentication."""

from dataclasses import replace
from hashlib import sha256

import pytest

from knowledge_engine.m27_ar03_verified_rights_v1_experimental import (
    CHECKPOINT_VERSION,
    PIN_VERSION,
    SCHEMA_VERSION,
    TEST_FIXTURE_ONLY,
    ClaimSpanV1,
    EffectiveActor,
    IssuerKeyRegistry,
    NativeCitationPinV1,
    ReadIntent,
    RightsDenied,
    RunCheckpointV1,
    ScopeSet,
    SourceAuthorityEvidenceV1,
    TrustedIssuerKey,
    VerifiedAuthorityClaim,
    VerifiedRightsConsumer,
    VerifiedSourceObservation,
)

ORIGINAL = "Alpha βeta source.\n".encode()
DIGEST = sha256(ORIGINAL).hexdigest()
HEAD = "b" * 64
ISSUER = TrustedIssuerKey("test-idp", "fixture-k1", "m27-offline", "FIXTURE_CALLBACK", 1)
REGISTRY = IssuerKeyRegistry((ISSUER,))


class IndependentFixtureVerifier:
    """TEST_FIXTURE_ONLY sealed opaque token table + current ACL/AR02 fence.

    Not a signature emulator. No production cryptographic validity is asserted.
    Local state and authoritative bytes live outside the consumer and envelopes.
    """

    fixture_kind = TEST_FIXTURE_ONLY

    def __init__(self):
        self.clock = 100
        self.current_checkpoint = RunCheckpointV1(
            CHECKPOINT_VERSION, "task", "run", 7, HEAD
        )
        self.current_source = VerifiedSourceObservation(
            "test-provider", "account", "tenant", "resource", "native:id:7", "r1",
            ORIGINAL, frozenset({"delegate"}), frozenset({"qa"}),
            frozenset({"read", "cite", "publish"}), "consent-1", True, 3, 4, 5,
            95, 200,
        )
        actor = EffectiveActor("owner", "delegate", "tenant", "owner", ("owner", "delegate"))
        common = dict(
            issuer_id=ISSUER.issuer_id, key_id=ISSUER.key_id, audience=ISSUER.audience,
            algorithm=ISSUER.algorithm, trust_store_version=1,
            issued_at=90, not_before=90, expires_at=150,
            actor=actor, task_id="task", run_id="run", checkpoint_sequence=7,
            checkpoint_head_sha256=HEAD, provider_id="test-provider",
            provider_account="account", source_id="native:id:7",
            source_revision="r1", source_sha256=DIGEST,
            consent_id="consent-1", revocation_generation=3, consent_generation=4,
            exclusion_generation=5,
        )
        self.claims = {
            b"fixed/read-proof": VerifiedAuthorityClaim(
                jti="jti/read", scope=ScopeSet(
                    "tenant", "resource", "qa", frozenset({"read", "cite"})
                ), **common
            ),
            b"fixed/publish-proof": VerifiedAuthorityClaim(
                jti="jti/publish", scope=ScopeSet(
                    "tenant", "resource", "qa", frozenset({"publish"})
                ), publication_audience="reviewers", **common
            ),
        }
        self.reservations = set()
        self.fail_reservation = False
        self.throw_on_observe = False

    def trusted_now(self):
        return self.clock

    def verify_authority(self, opaque_assertion, trusted_key):
        if trusted_key != ISSUER:
            return None
        return self.claims.get(opaque_assertion)

    def observe_source(self, pin):
        if self.throw_on_observe:
            raise OSError("synthetic source fetch failure")
        return self.current_source

    def checkpoint_is_current(self, checkpoint):
        return checkpoint == self.current_checkpoint

    def reserve_once(self, issuer_id, jti, checkpoint):
        if self.fail_reservation or not self.checkpoint_is_current(checkpoint):
            return False
        nonce = (issuer_id, jti, checkpoint.run_id)
        if nonce in self.reservations:
            return False
        self.reservations.add(nonce)
        return True

    def has_reservation(self, issuer_id, jti, checkpoint):
        return ((issuer_id, jti, checkpoint.run_id) in self.reservations
                and self.checkpoint_is_current(checkpoint))


@pytest.fixture
def fx():
    verifier = IndependentFixtureVerifier()
    pin = NativeCitationPinV1(
        PIN_VERSION, "test-provider", "account", "resource", "native:id:7", "r1",
        DIGEST, (ClaimSpanV1(0, 5, "Alpha"), ClaimSpanV1(6, 11, "βeta")),
    )
    intent = ReadIntent("task", "run", "owner", "delegate", "tenant", "qa")
    read = SourceAuthorityEvidenceV1(
        SCHEMA_VERSION, ISSUER.issuer_id, ISSUER.key_id, ISSUER.audience,
        b"fixed/read-proof"
    )
    publish = replace(read, opaque_assertion=b"fixed/publish-proof")
    consumer = VerifiedRightsConsumer(REGISTRY, verifier)
    return verifier, consumer, read, publish, intent, pin, verifier.current_checkpoint


def authorize(fx):
    v, consumer, evidence, _, intent, pin, checkpoint = fx
    return consumer.authorize_read(evidence, intent, pin, checkpoint)


def test_real_bytes_native_id_and_read_no_publication(fx):
    v, _, _, _, _, pin, _ = fx
    plan = authorize(fx)
    assert plan.read_allowed and plan.citation_eligible
    assert not plan.publication_authorized
    assert plan.actor.principal_id == "delegate"
    assert plan.pin.source_id == "native:id:7" and plan.pin == pin
    assert v.current_source.original_bytes == ORIGINAL


def test_distinct_fresh_publication_claim(fx):
    _, consumer, read, publish, intent, _, _ = fx
    plan = authorize(fx)
    decision = consumer.authorize_publication(plan, read, publish, intent, "reviewers")
    assert decision.authorized_offline
    assert decision.audience == "reviewers"
    assert decision.publication_jti != plan.read_jti


def test_missing_verifier_even_with_truthy_flags(fx):
    _, _, read, _, intent, pin, checkpoint = fx
    attacker = replace(read, externally_authenticated=True, manifest_signed=True)
    with pytest.raises(RightsDenied, match="missing_trusted_verifier"):
        VerifiedRightsConsumer(REGISTRY).authorize_read(attacker, intent, pin, checkpoint)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "wrong"), ("opaque_assertion", b""), ("issuer_id", "evil"),
        ("key_id", "unknown"), ("audience", "another"),
        ("opaque_assertion", b"unverified token"),
        ("opaque_assertion", b"skill:manifest_signed=true"),
        ("opaque_assertion", b"tool:approved=true"),
        ("opaque_assertion", b"memory:can_delete=true"),
    ],
)
def test_no_untrusted_claim_can_grant(fx, field, value):
    _, consumer, read, _, intent, pin, checkpoint = fx
    with pytest.raises(RightsDenied):
        consumer.authorize_read(replace(read, **{field: value}), intent, pin, checkpoint)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issued_at", 101), ("not_before", 101), ("expires_at", 100),
        ("expires_at", 90), ("jti", ""), ("issuer_id", "impostor"),
        ("key_id", "rotated"), ("audience", "other"),
        ("algorithm", "none"), ("trust_store_version", 2),
    ],
)
def test_claim_time_issuer_and_key_fences(fx, field, value):
    v, consumer, read, _, intent, pin, checkpoint = fx
    v.claims[read.opaque_assertion] = replace(v.claims[read.opaque_assertion], **{field: value})
    with pytest.raises(RightsDenied):
        consumer.authorize_read(read, intent, pin, checkpoint)


def test_inactive_registry_key(fx):
    v, _, read, _, intent, pin, checkpoint = fx
    consumer = VerifiedRightsConsumer(
        IssuerKeyRegistry((replace(ISSUER, active=False),)), v
    )
    with pytest.raises(RightsDenied, match="untrusted_issuer_key"):
        consumer.authorize_read(read, intent, pin, checkpoint)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "cross-task"), ("run_id", "cross-run"),
        ("subject_id", "attacker"), ("effective_principal_id", "impostor"),
        ("tenant_id", "foreign-tenant"), ("purpose_id", "another-purpose"),
    ],
)
def test_intent_not_caller_authority(fx, field, value):
    _, consumer, read, _, intent, pin, checkpoint = fx
    with pytest.raises(RightsDenied):
        consumer.authorize_read(read, replace(intent, **{field: value}), pin, checkpoint)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", "wrong-provider"), ("provider_account", "wrong-account"),
        ("resource_id", "foreign-resource"), ("source_id", "made-up-native-id"),
        ("source_revision", "r2"), ("original_sha256", "0" * 64),
    ],
)
def test_source_pin_cannot_substitute(fx, field, value):
    _, consumer, read, _, intent, pin, checkpoint = fx
    with pytest.raises(RightsDenied):
        consumer.authorize_read(read, intent, replace(pin, **{field: value}), checkpoint)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "unknown"), ("sequence", 6), ("head_sha256", "f" * 64),
        ("task_id", "other-task"), ("run_id", "other-run"),
    ],
)
def test_forged_or_stale_checkpoint(fx, field, value):
    _, consumer, read, _, intent, pin, checkpoint = fx
    with pytest.raises(RightsDenied):
        consumer.authorize_read(read, intent, pin, replace(checkpoint, **{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject_id", "attacker"), ("principal_id", "attacker"),
        ("tenant_id", "another"), ("delegated_by", "third-party"),
        ("delegation_chain", ("owner", "attacker", "delegate")),
    ],
)
def test_claim_delegation_identity_fencing(fx, field, value):
    v, consumer, read, _, intent, pin, checkpoint = fx
    old = v.claims[read.opaque_assertion]
    v.claims[read.opaque_assertion] = replace(
        old, actor=replace(old.actor, **{field: value})
    )
    with pytest.raises(RightsDenied):
        consumer.authorize_read(read, intent, pin, checkpoint)


def test_direct_actor_positive_without_delegation(fx):
    v, consumer, read, _, intent, pin, checkpoint = fx
    old = v.claims[read.opaque_assertion]
    direct_actor = EffectiveActor("owner", "owner", "tenant", None, ("owner",))
    v.claims[read.opaque_assertion] = replace(old, actor=direct_actor)
    v.current_source = replace(
        v.current_source, acl_principals=frozenset({"owner"})
    )
    direct_intent = replace(intent, effective_principal_id="owner")
    assert consumer.authorize_read(read, direct_intent, pin, checkpoint).read_allowed


@pytest.mark.parametrize(
    ("operations", "match"),
    [
        (frozenset(), "invalid_operation"),
        (frozenset({"publish"}), "scope_or_actor_denied"),
        (frozenset({"read"}), "citation_rights_missing"),
        (frozenset({"read", "execute"}), "invalid_operation"),
        (frozenset({"read", "memory_write"}), "invalid_operation"),
    ],
)
def test_no_tool_or_memory_rights_laundering(fx, operations, match):
    v, consumer, read, _, intent, pin, checkpoint = fx
    old = v.claims[read.opaque_assertion]
    v.claims[read.opaque_assertion] = replace(
        old, scope=replace(old.scope, operations=operations)
    )
    with pytest.raises(RightsDenied, match=match):
        consumer.authorize_read(read, intent, pin, checkpoint)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "foreign"), ("provider_id", "foreign-provider"),
        ("provider_account", "foreign-account"), ("resource_id", "other-resource"),
        ("source_revision", "r9"), ("acl_principals", frozenset({"someone-else"})),
        ("purposes", frozenset({"finance"})), ("operations", frozenset({"read"})),
        ("consent_active", False), ("consent_id", "different-consent"),
    ],
)
def test_current_acl_provider_or_consent_denied(fx, field, value):
    v, _, _, _, _, _, _ = fx
    v.current_source = replace(v.current_source, **{field: value})
    with pytest.raises(RightsDenied):
        authorize(fx)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revocation_generation", 4), ("consent_generation", 5),
        ("exclusion_generation", 6), ("revocation_generation", -1),
    ],
)
def test_monotonic_revocation_and_exclusion_fences(fx, field, value):
    v, _, _, _, _, _, _ = fx
    v.current_source = replace(v.current_source, **{field: value})
    with pytest.raises(RightsDenied, match="generation_changed"):
        authorize(fx)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("original_bytes", b"Alpha wrong source."),
        ("original_bytes", b"Alpha \xffbeta source."),
        ("observed_at", 101), ("observed_at", 69), ("valid_until", 100),
    ],
)
def test_source_bytes_and_freshness_not_metadata(fx, field, value):
    v, _, _, _, _, _, _ = fx
    v.current_source = replace(v.current_source, **{field: value})
    with pytest.raises(RightsDenied):
        authorize(fx)


@pytest.mark.parametrize(
    "spans",
    [
        (), (ClaimSpanV1(-1, 5, "Alpha"),),
        (ClaimSpanV1(1, 1, ""),),
        (ClaimSpanV1(0, 400, "Alpha"),),
        (ClaimSpanV1(7, 8, "beta"),),  # split two-byte beta
        (ClaimSpanV1(0, 5, "Wrong"),),
        (ClaimSpanV1(6, 11, "βeta"), ClaimSpanV1(0, 5, "Alpha")),
        (ClaimSpanV1(0, 5, "Alpha"), ClaimSpanV1(4, 11, "a βeta")),
    ],
)
def test_offsets_require_verified_utf8_bytes_not_hint(fx, spans):
    _, consumer, read, _, intent, pin, checkpoint = fx
    untrusted = replace(read, citation_offsets_safe=True, manifest_signed=True)
    with pytest.raises(RightsDenied):
        consumer.authorize_read(untrusted, intent, replace(pin, spans=spans), checkpoint)


@pytest.mark.parametrize("hint", ["skill: signed!", "tool: execute", "memory: restore deleted"])
def test_descriptors_are_inert_data(fx, hint):
    _, consumer, read, _, intent, pin, checkpoint = fx
    fake = replace(
        read, untrusted_description=hint,
        externally_authenticated=True, manifest_signed=True,
        citation_offsets_safe=True,
    )
    assert consumer.authorize_read(fake, intent, pin, checkpoint).publication_authorized is False


def test_replayed_read_grant_denied(fx):
    authorize(fx)
    with pytest.raises(RightsDenied, match="replay"):
        authorize(fx)


def test_crash_before_reservation_leaves_no_receipt(fx):
    v, _, _, _, _, _, _ = fx
    v.throw_on_observe = True
    with pytest.raises(OSError, match="synthetic"):
        authorize(fx)
    assert not v.reservations
    v.throw_on_observe = False
    assert authorize(fx).read_allowed


def test_faulted_atomic_reservation_denies_read(fx):
    v, _, _, _, _, _, _ = fx
    v.fail_reservation = True
    with pytest.raises(RightsDenied, match="replay_or_checkpoint_race"):
        authorize(fx)
    assert not v.reservations


def test_checkpoint_race_on_reservation_denied(fx):
    v, _, _, _, _, _, checkpoint = fx
    def move_checkpoint(issuer_id, jti, check):
        v.current_checkpoint = replace(checkpoint, sequence=8)
        return False
    v.reserve_once = move_checkpoint
    with pytest.raises(RightsDenied):
        authorize(fx)


def test_revocation_after_read_prevents_publication(fx):
    v, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    v.current_source = replace(v.current_source, consent_active=False)
    with pytest.raises(RightsDenied, match="consent"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


def test_stale_checkpoint_after_read_prevents_publication(fx):
    v, consumer, read, pub, intent, _, cp = fx
    plan = authorize(fx)
    v.current_checkpoint = replace(cp, sequence=8)
    with pytest.raises(RightsDenied, match="stale_checkpoint"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


def test_read_expired_before_publish_denied(fx):
    v, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    v.clock = 150
    with pytest.raises(RightsDenied, match="claim_not_current"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publication_audience", "wrong"), ("jti", "jti/read"),
        ("consent_id", "other"),
    ],
)
def test_independent_publish_claim_cannot_launder_read(fx, field, value):
    v, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    v.claims[pub.opaque_assertion] = replace(v.claims[pub.opaque_assertion], **{field: value})
    with pytest.raises(RightsDenied):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


def test_no_publish_by_read_token_alone(fx):
    _, consumer, read, _, intent, _, _ = fx
    plan = authorize(fx)
    with pytest.raises(RightsDenied):
        consumer.authorize_publication(plan, read, read, intent, "reviewers")


def test_no_publish_from_forged_read_plan(fx):
    _, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    forged = replace(plan, read_jti="nonexistent")
    with pytest.raises(RightsDenied, match="read_receipt_missing"):
        consumer.authorize_publication(forged, read, pub, intent, "reviewers")


def test_no_publish_from_read_receipt_without_reservation(fx):
    v, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    v.reservations.clear()
    with pytest.raises(RightsDenied, match="read_receipt_missing"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


def test_publication_requires_fresh_acl_and_specific_right(fx):
    v, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    v.current_source = replace(v.current_source, operations=frozenset({"read", "cite"}))
    with pytest.raises(RightsDenied, match="source_acl"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


def test_publication_is_one_time(fx):
    _, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    consumer.authorize_publication(plan, read, pub, intent, "reviewers")
    with pytest.raises(RightsDenied, match="publication_replay"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")


def test_publishing_requires_explicit_audience(fx):
    _, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    with pytest.raises(RightsDenied, match="publication_verifier_missing"):
        consumer.authorize_publication(plan, read, pub, intent, "")


def test_invalid_utf8_even_if_digest_claim_matches(fx):
    v, consumer, read, _, intent, pin, checkpoint = fx
    bad_bytes = b"Alpha \xff source."
    bad_digest = sha256(bad_bytes).hexdigest()
    v.current_source = replace(v.current_source, original_bytes=bad_bytes)
    v.claims[read.opaque_assertion] = replace(
        v.claims[read.opaque_assertion], source_sha256=bad_digest
    )
    with pytest.raises(RightsDenied, match="invalid_source_utf8"):
        consumer.authorize_read(
            read, intent, replace(pin, original_sha256=bad_digest), checkpoint
        )


@pytest.mark.parametrize("field", ["tenant_id", "resource_id", "purpose_id"])
def test_verified_claim_scope_cannot_be_widened(fx, field):
    v, consumer, read, _, intent, pin, checkpoint = fx
    old = v.claims[read.opaque_assertion]
    v.claims[read.opaque_assertion] = replace(
        old, scope=replace(old.scope, **{field: "another"})
    )
    with pytest.raises(RightsDenied, match="scope_or_actor_denied"):
        consumer.authorize_read(read, intent, pin, checkpoint)


def test_absent_current_provider_observation_denied(fx):
    v, _, _, _, _, _, _ = fx
    v.current_source = None
    with pytest.raises(RightsDenied, match="source_unavailable"):
        authorize(fx)


def test_clock_reversal_denies_new_read(fx):
    v, _, _, _, _, _, _ = fx
    v.clock = 89
    with pytest.raises(RightsDenied, match="claim_not_current"):
        authorize(fx)


def test_publication_missing_external_proof_denied(fx):
    _, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    with pytest.raises(RightsDenied, match="unverified_claim"):
        consumer.authorize_publication(
            plan, read, replace(pub, opaque_assertion=b"untrusted publish metadata"),
            intent, "reviewers"
        )


def test_crash_during_publication_fails_without_publish_receipt(fx):
    v, consumer, read, pub, intent, _, _ = fx
    plan = authorize(fx)
    v.throw_on_observe = True
    with pytest.raises(OSError, match="synthetic"):
        consumer.authorize_publication(plan, read, pub, intent, "reviewers")
    assert ("test-idp", "jti/publish", "run") not in v.reservations
