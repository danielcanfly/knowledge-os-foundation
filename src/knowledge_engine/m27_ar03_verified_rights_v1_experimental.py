"""K03V: feature-off, independent authority verification seam (no live Provider).

This module does NOT authenticate a Provider/IdP itself. Trust is supplied solely
by a separately configured verifier and issuer registry. No metadata or caller
boolean ever serves as authorization. Never wire test fixtures to Production.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

EXPERIMENTAL_NO_LIVE_PROVIDER = True
SCHEMA_VERSION = "SourceAuthorityEvidence/v1"
PIN_VERSION = "NativeCitationPin/v1"
CHECKPOINT_VERSION = "AR02CheckpointPin/v1"
TEST_FIXTURE_ONLY = "TEST_FIXTURE_ONLY"
_ALLOWED_OPERATIONS = frozenset({"read", "cite", "publish"})
_MAX_OBSERVATION_AGE = 30


class RightsDenied(Exception):
    """Authorization failure: reason is a coarse code, not a secret-bearing value."""


@dataclass(frozen=True, slots=True)
class TrustedIssuerKey:
    issuer_id: str
    key_id: str
    audience: str
    algorithm: str
    trust_store_version: int
    active: bool = True


@dataclass(frozen=True, slots=True)
class IssuerKeyRegistry:
    """Trusted composition-root configuration, NOT taken from an agent/tool request."""

    trusted_keys: tuple[TrustedIssuerKey, ...]

    def resolve(self, issuer: str, key: str, audience: str) -> TrustedIssuerKey:
        matching = [
            item for item in self.trusted_keys
            if item.issuer_id == issuer and item.key_id == key
            and item.audience == audience and item.active
            and item.trust_store_version > 0 and item.algorithm
        ]
        if len(matching) != 1:
            raise RightsDenied("untrusted_issuer_key")
        return matching[0]


@dataclass(frozen=True, slots=True)
class SourceAuthorityEvidenceV1:
    """An untrusted envelope. Only opaque_assertion is handed to the trusted verifier."""

    version: str
    issuer_id: str
    key_id: str
    audience: str
    opaque_assertion: bytes
    externally_authenticated: bool = False
    manifest_signed: bool = False
    citation_offsets_safe: bool = True
    untrusted_description: str = ""


@dataclass(frozen=True, slots=True)
class EffectiveActor:
    subject_id: str
    principal_id: str
    tenant_id: str
    delegated_by: str | None
    delegation_chain: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScopeSet:
    tenant_id: str
    resource_id: str
    purpose_id: str
    operations: frozenset[str]


@dataclass(frozen=True, slots=True)
class ClaimSpanV1:
    start_byte: int
    end_byte: int
    expected_text: str


@dataclass(frozen=True, slots=True)
class NativeCitationPinV1:
    version: str
    provider_id: str
    provider_account: str
    resource_id: str
    source_id: str
    source_revision: str
    original_sha256: str
    spans: tuple[ClaimSpanV1, ...]


@dataclass(frozen=True, slots=True)
class RunCheckpointV1:
    version: str
    task_id: str
    run_id: str
    sequence: int
    head_sha256: str


@dataclass(frozen=True, slots=True)
class ReadIntent:
    task_id: str
    run_id: str
    subject_id: str
    effective_principal_id: str
    tenant_id: str
    purpose_id: str


@dataclass(frozen=True, slots=True)
class VerifiedAuthorityClaim:
    """Only a separately trusted verifier may originate this in normal deployment."""

    issuer_id: str
    key_id: str
    audience: str
    algorithm: str
    trust_store_version: int
    issued_at: int
    not_before: int
    expires_at: int
    jti: str
    actor: EffectiveActor
    scope: ScopeSet
    task_id: str
    run_id: str
    checkpoint_sequence: int
    checkpoint_head_sha256: str
    provider_id: str
    provider_account: str
    source_id: str
    source_revision: str
    source_sha256: str
    consent_id: str
    revocation_generation: int
    consent_generation: int
    exclusion_generation: int
    publication_audience: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedSourceObservation:
    """Bytes and ACL must come from independent Provider/source adapter, not caller."""

    provider_id: str
    provider_account: str
    tenant_id: str
    resource_id: str
    source_id: str
    source_revision: str
    original_bytes: bytes
    acl_principals: frozenset[str]
    purposes: frozenset[str]
    operations: frozenset[str]
    consent_id: str
    consent_active: bool
    revocation_generation: int
    consent_generation: int
    exclusion_generation: int
    observed_at: int
    valid_until: int


class ProviderAuthorityVerifier(Protocol):
    """All methods require independent trust. No self-attestation by the caller."""

    def trusted_now(self) -> int: ...

    def verify_authority(
        self, opaque_assertion: bytes, trusted_key: TrustedIssuerKey
    ) -> VerifiedAuthorityClaim | None: ...

    def observe_source(self, pin: NativeCitationPinV1) -> VerifiedSourceObservation | None: ...

    def checkpoint_is_current(self, checkpoint: RunCheckpointV1) -> bool: ...

    def reserve_once(
        self, issuer_id: str, jti: str, checkpoint: RunCheckpointV1
    ) -> bool: ...

    def has_reservation(
        self, issuer_id: str, jti: str, checkpoint: RunCheckpointV1
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class AuthorizedReadPlan:
    """Local read/cite decision only. Not a durable AR02 capability or publish permit."""

    version: str
    actor: EffectiveActor
    scope: ScopeSet
    pin: NativeCitationPinV1
    checkpoint: RunCheckpointV1
    issuer_id: str
    read_jti: str
    expires_at: int
    read_allowed: bool
    citation_eligible: bool
    publication_authorized: bool = False


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    """Fresh, separately attested publication decision; not a terminal AR02 commit."""

    pin: NativeCitationPinV1
    checkpoint: RunCheckpointV1
    audience: str
    publication_jti: str
    authorized_offline: bool


class VerifiedRightsConsumer:
    """Feature-off seam. Only trusted verifier + registry can establish authority."""

    def __init__(
        self,
        registry: IssuerKeyRegistry,
        verifier: ProviderAuthorityVerifier | None = None,
    ) -> None:
        self._registry = registry
        self._verifier = verifier

    def _authority(self, envelope: SourceAuthorityEvidenceV1) -> VerifiedAuthorityClaim:
        if self._verifier is None:
            raise RightsDenied("missing_trusted_verifier")
        if envelope.version != SCHEMA_VERSION or not envelope.opaque_assertion:
            raise RightsDenied("invalid_evidence_envelope")
        key = self._registry.resolve(envelope.issuer_id, envelope.key_id, envelope.audience)
        claim = self._verifier.verify_authority(envelope.opaque_assertion, key)
        if claim is None or not isinstance(claim, VerifiedAuthorityClaim):
            raise RightsDenied("unverified_claim")
        if (
            (claim.issuer_id, claim.key_id, claim.audience, claim.algorithm,
             claim.trust_store_version)
            != (key.issuer_id, key.key_id, key.audience, key.algorithm,
                key.trust_store_version)
        ):
            raise RightsDenied("claim_trust_mismatch")
        now = self._verifier.trusted_now()
        if (
            not isinstance(now, int) or now < 0 or
            claim.issued_at > now or claim.not_before > now or
            claim.expires_at <= now or
            claim.expires_at <= claim.not_before or not claim.jti
        ):
            raise RightsDenied("claim_not_current")
        if (
            not claim.scope.operations or
            not claim.scope.operations <= _ALLOWED_OPERATIONS
        ):
            raise RightsDenied("invalid_operation")
        actor = claim.actor
        if not actor.subject_id or not actor.principal_id or not actor.tenant_id:
            raise RightsDenied("invalid_actor")
        if actor.principal_id == actor.subject_id:
            if actor.delegated_by is not None or actor.delegation_chain != (actor.subject_id,):
                raise RightsDenied("invalid_delegation")
        elif (
            actor.delegated_by != actor.subject_id or
            actor.delegation_chain != (actor.subject_id, actor.principal_id)
        ):
            raise RightsDenied("invalid_delegation")
        return claim

    def _check_context(
        self,
        claim: VerifiedAuthorityClaim,
        intent: ReadIntent,
        pin: NativeCitationPinV1,
        checkpoint: RunCheckpointV1,
        required_op: str,
    ) -> None:
        if self._verifier is None:
            raise RightsDenied("missing_trusted_verifier")
        if (
            pin.version != PIN_VERSION or checkpoint.version != CHECKPOINT_VERSION
            or checkpoint.sequence < 0 or not checkpoint.task_id or not checkpoint.run_id
            or len(checkpoint.head_sha256) != 64
            or any(c not in "0123456789abcdef" for c in checkpoint.head_sha256)
            or not self._verifier.checkpoint_is_current(checkpoint)
        ):
            raise RightsDenied("stale_checkpoint")
        if (
            (claim.task_id, claim.run_id, claim.checkpoint_sequence,
             claim.checkpoint_head_sha256)
            != (checkpoint.task_id, checkpoint.run_id, checkpoint.sequence,
                checkpoint.head_sha256)
            or (intent.task_id, intent.run_id) != (checkpoint.task_id, checkpoint.run_id)
        ):
            raise RightsDenied("run_binding_mismatch")
        if (
            (intent.subject_id, intent.effective_principal_id, intent.tenant_id)
            != (claim.actor.subject_id, claim.actor.principal_id, claim.actor.tenant_id)
            or (claim.scope.tenant_id, claim.scope.resource_id, claim.scope.purpose_id)
            != (intent.tenant_id, pin.resource_id, intent.purpose_id)
            or required_op not in claim.scope.operations
        ):
            raise RightsDenied("scope_or_actor_denied")
        if (
            (claim.provider_id, claim.provider_account, claim.source_id,
             claim.source_revision, claim.source_sha256)
            != (pin.provider_id, pin.provider_account, pin.source_id,
                pin.source_revision, pin.original_sha256)
        ):
            raise RightsDenied("source_claim_mismatch")

    def _current_bytes(
        self, claim: VerifiedAuthorityClaim, pin: NativeCitationPinV1, required_op: str
    ) -> None:
        if self._verifier is None:
            raise RightsDenied("missing_trusted_verifier")
        obs = self._verifier.observe_source(pin)
        if obs is None or not isinstance(obs, VerifiedSourceObservation):
            raise RightsDenied("source_unavailable")
        if (
            (obs.provider_id, obs.provider_account, obs.tenant_id, obs.resource_id,
             obs.source_id, obs.source_revision)
            != (pin.provider_id, pin.provider_account, claim.actor.tenant_id,
                pin.resource_id, pin.source_id, pin.source_revision)
            or claim.actor.principal_id not in obs.acl_principals
            or claim.scope.purpose_id not in obs.purposes
            or required_op not in obs.operations
            or not obs.consent_active or not claim.consent_id
            or obs.consent_id != claim.consent_id
        ):
            raise RightsDenied("source_acl_or_consent_denied")
        if (
            min(claim.revocation_generation, claim.consent_generation,
                claim.exclusion_generation, obs.revocation_generation,
                obs.consent_generation, obs.exclusion_generation) < 0
            or (claim.revocation_generation, claim.consent_generation,
                claim.exclusion_generation)
            != (obs.revocation_generation, obs.consent_generation,
                obs.exclusion_generation)
        ):
            raise RightsDenied("generation_changed")
        now = self._verifier.trusted_now()
        if (
            obs.observed_at > now or now - obs.observed_at > _MAX_OBSERVATION_AGE
            or obs.valid_until <= now or not isinstance(obs.original_bytes, bytes)
        ):
            raise RightsDenied("stale_source_observation")
        if (
            len(pin.original_sha256) != 64 or
            sha256(obs.original_bytes).hexdigest() != pin.original_sha256
        ):
            raise RightsDenied("source_bytes_mismatch")
        try:
            obs.original_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RightsDenied("invalid_source_utf8") from exc
        if not pin.source_id or not pin.source_revision or not pin.spans:
            raise RightsDenied("missing_native_pin")
        previous_end = -1
        for span in pin.spans:
            if (
                not isinstance(span.start_byte, int) or
                not isinstance(span.end_byte, int) or
                span.start_byte < 0 or span.start_byte < previous_end or
                span.start_byte >= span.end_byte or span.end_byte > len(obs.original_bytes)
            ):
                raise RightsDenied("unsafe_citation_offsets")
            try:
                text = obs.original_bytes[span.start_byte:span.end_byte].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RightsDenied("unsafe_citation_offsets") from exc
            if text != span.expected_text or not text:
                raise RightsDenied("citation_bytes_mismatch")
            previous_end = span.end_byte

    def authorize_read(
        self,
        evidence: SourceAuthorityEvidenceV1,
        intent: ReadIntent,
        pin: NativeCitationPinV1,
        checkpoint: RunCheckpointV1,
    ) -> AuthorizedReadPlan:
        claim = self._authority(evidence)
        self._check_context(claim, intent, pin, checkpoint, "read")
        if "cite" not in claim.scope.operations:
            raise RightsDenied("citation_rights_missing")
        self._current_bytes(claim, pin, "read")
        self._current_bytes(claim, pin, "cite")
        if self._verifier is None or not self._verifier.reserve_once(
            claim.issuer_id, claim.jti, checkpoint
        ):
            raise RightsDenied("replay_or_checkpoint_race")
        return AuthorizedReadPlan(
            "AuthorizedReadPlan/v1", claim.actor, claim.scope, pin, checkpoint,
            claim.issuer_id, claim.jti, claim.expires_at, True, True, False,
        )

    def authorize_publication(
        self,
        read_plan: AuthorizedReadPlan,
        original_read_evidence: SourceAuthorityEvidenceV1,
        publication_evidence: SourceAuthorityEvidenceV1,
        intent: ReadIntent,
        publication_audience: str,
    ) -> PublicationDecision:
        if not publication_audience or self._verifier is None:
            raise RightsDenied("publication_verifier_missing")
        if (
            read_plan.version != "AuthorizedReadPlan/v1"
            or not read_plan.read_allowed or not read_plan.citation_eligible
            or read_plan.publication_authorized
        ):
            raise RightsDenied("invalid_read_plan")
        read_claim = self._authority(original_read_evidence)
        pin, checkpoint = read_plan.pin, read_plan.checkpoint
        self._check_context(read_claim, intent, pin, checkpoint, "read")
        if (
            "cite" not in read_claim.scope.operations or
            read_claim.jti != read_plan.read_jti or
            read_claim.issuer_id != read_plan.issuer_id or
            read_claim.actor != read_plan.actor or read_claim.scope != read_plan.scope or
            read_claim.expires_at != read_plan.expires_at or
            not self._verifier.has_reservation(read_claim.issuer_id, read_claim.jti, checkpoint)
        ):
            raise RightsDenied("read_receipt_missing")
        self._current_bytes(read_claim, pin, "read")
        self._current_bytes(read_claim, pin, "cite")
        publish_claim = self._authority(publication_evidence)
        self._check_context(publish_claim, intent, pin, checkpoint, "publish")
        if (
            publish_claim.actor != read_claim.actor
            or publish_claim.consent_id != read_claim.consent_id
            or publish_claim.publication_audience != publication_audience
            or publish_claim.jti == read_claim.jti
        ):
            raise RightsDenied("independent_publication_rights_missing")
        self._current_bytes(publish_claim, pin, "publish")
        if not self._verifier.reserve_once(publish_claim.issuer_id, publish_claim.jti, checkpoint):
            raise RightsDenied("publication_replay_or_checkpoint_race")
        return PublicationDecision(pin, checkpoint, publication_audience, publish_claim.jti, True)
