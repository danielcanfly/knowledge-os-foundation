"""Offline cross-module ABI gate for M27 X01-X09 engineering proofs.

This module is deliberately inert: it has no network, provider, production,
credential, filesystem, or publication adapter.  It models the conservative
Master ADR decisions and keeps externally-owned authority visibly unresolved.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from types import MappingProxyType
from typing import Literal

from knowledge_engine.m27_ar04_safe_action_experimental import VerificationProposal
from knowledge_engine.m27_ar05_verification_experimental import (
    JournalSnapshot,
    PublicationEligibility,
)
from knowledge_engine.m27_ar09_oracle_experimental import (
    EXPECTED_ACCEPT_FIXTURE_ONLY,
    NativeSourceFixture,
    compare_native_source,
)

Effect = Literal[
    "NOT_DISPATCHED",
    "POSSIBLY_SENT",
    "CONFIRMED_APPLIED",
    "CONFIRMED_NOT_APPLIED",
    "UNKNOWN_EFFECT",
]


class AbiGateDenied(ValueError):
    """Fail-closed rejection at a named ABI or transaction boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


@dataclass(frozen=True, slots=True)
class LegacyBoundEnvelope:
    """External wrapper that never rewrites the stored AR01D v1 bytes."""

    envelope_id: str
    tenant_id: str
    run_id: str
    legacy_type: str
    legacy_raw_sha256: str
    raw_byte_length: int
    required_sidecar_digests: tuple[str, ...]
    policy_generation: int
    revocation_generation: int
    namespace: Literal["ar01v.envelope"] = "ar01v.envelope"
    version: Literal["1.0.0"] = "1.0.0"
    record_type: Literal["legacy-bound"] = "legacy-bound"


@dataclass(frozen=True, slots=True)
class NewRecordEnvelope:
    """Envelope for new-only records; it cannot carry a forged legacy ref."""

    record_id: str
    tenant_id: str
    run_id: str
    new_record_namespace: str
    body_sha256: str
    policy_generation: int
    revocation_generation: int
    namespace: Literal["ar01z.new-record"] = "ar01z.new-record"
    version: Literal["1.0.0"] = "1.0.0"
    record_type: Literal["new-record"] = "new-record"


@dataclass(frozen=True, slots=True)
class EffectiveAuthorization:
    """Synthetic signed authority input backed by a configured fake trust root."""

    auth_id: str
    issuer_key_id: str
    tenant_id: str
    run_id: str
    principal_id: str
    delegated_by: str | None
    audience: str
    purpose: str
    issued_at: int
    expires_at: int
    policy_generation: int
    revocation_generation: int
    consent_required: bool
    consent_ref: str | None
    signature: str

    def unsigned(self) -> EffectiveAuthorization:
        return replace(self, signature="")


def authorization_message(auth: EffectiveAuthorization) -> bytes:
    """Return deterministic bytes used only by the offline HMAC fixture."""

    return _canonical(asdict(auth.unsigned()))


def sign_authorization(auth: EffectiveAuthorization, key: bytes) -> EffectiveAuthorization:
    """Sign an offline fixture; this is not a production signature scheme."""

    signature = hmac.new(key, authorization_message(auth), hashlib.sha256).hexdigest()
    return replace(auth, signature=signature)


@dataclass(frozen=True, slots=True)
class ConsentAuthoritySnapshot:
    """Separate synthetic policy-origin consent/revocation statement."""

    key_id: str
    consent_ref: str
    tenant_id: str
    run_id: str
    principal_id: str
    purpose: str
    policy_generation: int
    revocation_generation: int
    issued_at: int
    expires_at: int
    signature: str = ""


def sign_consent(
    grant: ConsentAuthoritySnapshot, key: bytes
) -> ConsentAuthoritySnapshot:
    payload = _canonical(asdict(replace(grant, signature="")))
    return replace(grant, signature=hmac.new(key, payload, hashlib.sha256).hexdigest())


class OfflineAuthorityGate:
    """Validates bytes, expected identity, and independently signed fake consent."""

    def __init__(
        self,
        *,
        trusted_keys: Mapping[str, bytes],
        trusted_consent_keys: Mapping[str, bytes] | None = None,
    ) -> None:
        self._trusted_keys = MappingProxyType(dict(trusted_keys))
        self._consent_keys = MappingProxyType(dict(trusted_consent_keys or {}))

    def validate_legacy(
        self,
        *,
        envelope: LegacyBoundEnvelope,
        raw_bytes: bytes,
        supplied_sidecar_digests: tuple[str, ...],
    ) -> None:
        if envelope.namespace != "ar01v.envelope" or envelope.version != "1.0.0":
            raise AbiGateDenied("X01_UNSUPPORTED_LEGACY_ENVELOPE")
        if envelope.raw_byte_length != len(raw_bytes):
            raise AbiGateDenied("X01_LEGACY_LENGTH_MISMATCH")
        if envelope.legacy_raw_sha256 != _sha(raw_bytes):
            raise AbiGateDenied("X01_LEGACY_RAW_BYTES_MISMATCH")
        if not envelope.required_sidecar_digests:
            raise AbiGateDenied("X01_REQUIRED_SIDECAR_MISSING")
        if envelope.required_sidecar_digests != supplied_sidecar_digests:
            raise AbiGateDenied("X01_SIDECAR_BINDING_MISMATCH")

    def validate_new_record(self, *, envelope: NewRecordEnvelope, body: bytes) -> None:
        if envelope.namespace != "ar01z.new-record" or envelope.version != "1.0.0":
            raise AbiGateDenied("X01_UNSUPPORTED_NEW_RECORD_ENVELOPE")
        if not envelope.new_record_namespace:
            raise AbiGateDenied("X01_NEW_RECORD_NAMESPACE_MISSING")
        if envelope.body_sha256 != _sha(body):
            raise AbiGateDenied("X01_NEW_RECORD_BODY_MISMATCH")

    def validate_authorization(
        self,
        *,
        auth: EffectiveAuthorization,
        tenant_id: str,
        run_id: str,
        audience: str,
        purpose: str,
        policy_generation: int,
        revocation_generation: int,
        now: int,
        expected_principal_id: str | None = None,
        expected_delegated_by: str | None = None,
        consent_policy: ConsentAuthoritySnapshot | None = None,
    ) -> None:
        if not expected_principal_id or not expected_delegated_by:
            raise AbiGateDenied("X02_EXPECTED_PRINCIPAL_UNBOUND")
        if auth.delegated_by is None:
            raise AbiGateDenied("X02_DELEGATION_ABSENT")
        if (auth.principal_id, auth.delegated_by) != (
            expected_principal_id, expected_delegated_by
        ):
            raise AbiGateDenied("X02_EXPECTED_PRINCIPAL_MISMATCH")
        key = self._trusted_keys.get(auth.issuer_key_id)
        if key is None:
            raise AbiGateDenied("X02_UNKNOWN_TRUST_ROOT")
        expected = hmac.new(key, authorization_message(auth), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(auth.signature, expected):
            raise AbiGateDenied("X02_AUTH_SIGNATURE_INVALID")
        if (auth.tenant_id, auth.run_id, auth.audience, auth.purpose) != (
            tenant_id,
            run_id,
            audience,
            purpose,
        ):
            raise AbiGateDenied("X02_AUTH_SCOPE_MISMATCH")
        if auth.issued_at > now or auth.expires_at <= now:
            raise AbiGateDenied("X02_AUTH_EXPIRED_OR_FROM_FUTURE")
        if auth.policy_generation != policy_generation:
            raise AbiGateDenied("X02_POLICY_GENERATION_STALE")
        if auth.revocation_generation != revocation_generation:
            raise AbiGateDenied("X02_REVOCATION_GENERATION_STALE")
        if auth.delegated_by is None:
            raise AbiGateDenied("X02_DELEGATION_ABSENT")
        if auth.consent_required:
            if not auth.consent_ref:
                raise AbiGateDenied("X02_CONSENT_ABSENT")
            if consent_policy is None:
                raise AbiGateDenied("X02_CONSENT_POLICY_UNBOUND")
            consent_key = self._consent_keys.get(consent_policy.key_id)
            if consent_key is None:
                raise AbiGateDenied("X02_CONSENT_ISSUER_UNTRUSTED")
            expected = sign_consent(consent_policy, consent_key).signature
            if not hmac.compare_digest(consent_policy.signature, expected):
                raise AbiGateDenied("X02_CONSENT_SIGNATURE_INVALID")
            if (
                consent_policy.consent_ref,
                consent_policy.tenant_id,
                consent_policy.run_id,
                consent_policy.principal_id,
                consent_policy.purpose,
                consent_policy.policy_generation,
                consent_policy.revocation_generation,
            ) != (
                auth.consent_ref,
                tenant_id,
                run_id,
                expected_principal_id,
                purpose,
                policy_generation,
                revocation_generation,
            ):
                raise AbiGateDenied("X02_CONSENT_POLICY_STALE_OR_MISMATCH")
            if consent_policy.issued_at > now or consent_policy.expires_at <= now:
                raise AbiGateDenied("X02_CONSENT_POLICY_EXPIRED")


@dataclass(frozen=True, slots=True)
class CommitReceipt:
    command_id: str
    command_digest: str
    version: int
    head_seq: int
    head_hash: str
    reserved_microunits: int


@dataclass(frozen=True, slots=True)
class PermitReceipt:
    permit_id: str
    tenant_id: str
    run_id: str
    command_id: str
    intent_id: str
    approval_id: str
    intent_digest: str
    lease_epoch: int
    version: int
    consumed: bool = False


@dataclass(frozen=True, slots=True)
class RegisteredIntent:
    """T1 identity, never reconstructed from caller-supplied approval strings."""

    tenant_id: str
    run_id: str
    command_id: str
    intent_id: str
    intent_digest: str
    lease_epoch: int
    quoted_cost_microunits: int


@dataclass(frozen=True, slots=True)
class IndependentApprovalEvidence:
    """Fixture authority record injected at construction, not in claim request."""

    approval_id: str
    tenant_id: str
    run_id: str
    command_id: str
    intent_id: str
    intent_digest: str
    lease_epoch: int
    approver_id: str
    issuer_id: str


@dataclass(frozen=True, slots=True)
class IndependentActionEvidence:
    """Configured T4 mock source binding, not a provider acknowledgment."""

    tenant_id: str
    run_id: str
    command_id: str
    intent_id: str
    intent_digest: str
    permit_id: str
    lease_epoch: int
    observation_digest: str
    effect: Effect
    observer_id: str


@dataclass(frozen=True, slots=True)
class IndependentPublicationEvidence:
    """Configured, separately evaluated AR05 fake-verifier outcome."""

    tenant_id: str
    run_id: str
    intent_id: str
    intent_digest: str
    outcome_id: str
    outcome_digest: str
    head_seq: int
    head_hash: str
    lease_epoch: int
    verification_id: str
    first_verified_frame_id: str
    content_sha256: str
    effect: Effect
    verifier_id: str


@dataclass(frozen=True, slots=True)
class IndependentNativeOracleEvidence:
    """Source/citation bytes in a separate synthetic oracle fixture."""

    oracle_id: str
    tenant_id: str
    run_id: str
    verification_id: str
    verified_content_sha256: str
    original: NativeSourceFixture
    observed: NativeSourceFixture


@dataclass(frozen=True, slots=True)
class OfflineIndependentEvidencePort:
    """Immutable, independently configured test-only source evidence port.

    Fixture records are outside the terminal caller. This is not production
    authority, native Product Q&A access, or a real signing root.
    """

    action: IndependentActionEvidence
    publication: IndependentPublicationEvidence
    native: IndependentNativeOracleEvidence
    trusted_observer_ids: frozenset[str]
    trusted_verifier_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class ChargeReceipt:
    tenant_id: str
    run_id: str
    charge_id: str
    command_id: str
    usage_version: str
    source_id: str
    actual_microunits: int | None
    charge_digest: str


@dataclass(frozen=True, slots=True)
class PostTerminalNotice:
    notice_id: str
    tenant_id: str
    run_id: str
    revision: int
    cursor: int
    kind: Literal["correction", "retraction", "privacy_suppression"]
    supersedes_segment_id: str
    body_sha256: str
    original_terminal_head_hash: str


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    version: int
    head_seq: int
    head_hash: str
    lease_epoch: int
    budget_cap_microunits: int
    reserved_microunits: int
    spent_microunits: int
    billing_unknown: bool
    effect: Effect
    terminal: bool
    terminal_state: str | None
    exclusion_generation: int
    revoked_dependencies: frozenset[str]
    economic_incident: bool


class OfflineSerializableLedger:
    """Single-writer CAS model for X04-X08; it never persists or dispatches."""

    def __init__(
        self,
        *,
        tenant_id: str,
        run_id: str,
        lease_epoch: int,
        budget_cap_microunits: int,
        trusted_approvals: Mapping[str, IndependentApprovalEvidence] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id
        self._trusted_approvals = MappingProxyType(dict(trusted_approvals or {}))
        self._state = LedgerSnapshot(
            version=0,
            head_seq=0,
            head_hash="0" * 64,
            lease_epoch=lease_epoch,
            budget_cap_microunits=budget_cap_microunits,
            reserved_microunits=0,
            spent_microunits=0,
            billing_unknown=False,
            effect="NOT_DISPATCHED",
            terminal=False,
            terminal_state=None,
            exclusion_generation=0,
            revoked_dependencies=frozenset(),
            economic_incident=False,
        )
        self._commands: dict[str, CommitReceipt] = {}
        self._intents: dict[str, RegisteredIntent] = {}
        self._permits: dict[str, PermitReceipt] = {}
        self._permit_by_intent: dict[str, str] = {}
        self._sent_intent_id: str | None = None
        self._observed_digest: str | None = None
        self._observed_effect: Effect | None = None
        self._unsettled_reservations: dict[str, int] = {}
        self._charge_ids: dict[str, ChargeReceipt] = {}
        self._terminal_fingerprint: str | None = None
        self._evidence_port: OfflineIndependentEvidencePort | None = None
        self._notices: tuple[PostTerminalNotice, ...] = ()

    @property
    def snapshot(self) -> LedgerSnapshot:
        return self._state

    @property
    def notices(self) -> tuple[PostTerminalNotice, ...]:
        return self._notices

    def register_intent(
        self,
        *,
        command_id: str,
        intent_digest: str,
        quoted_cost_microunits: int | None,
        expected_version: int,
        intent_id: str | None = None,
        lease_epoch: int | None = None,
    ) -> CommitReceipt:
        if not intent_id or lease_epoch is None:
            raise AbiGateDenied("X03_T1_IDENTITY_UNBOUND")
        if lease_epoch != self._state.lease_epoch:
            raise AbiGateDenied("X03_T1_LEASE_EPOCH_MISMATCH")
        prior = self._commands.get(command_id)
        command_digest = _sha(
            _canonical([
                intent_id, intent_digest, lease_epoch,
                quoted_cost_microunits, self.tenant_id, self.run_id
            ])
        )
        if prior is not None:
            if prior.command_digest != command_digest:
                raise AbiGateDenied("X04_COMMAND_DIGEST_CONFLICT")
            return prior
        self._require_version(expected_version)
        if intent_id in self._intents or any(
            existing.intent_digest == intent_digest for existing in self._intents.values()
        ):
            raise AbiGateDenied("X03_DUPLICATE_INTENT_IDENTITY")
        if self._state.terminal:
            raise AbiGateDenied("X04_TERMINAL_IMMUTABLE")
        if quoted_cost_microunits is None:
            raise AbiGateDenied("X07_PRICE_UNKNOWN")
        if quoted_cost_microunits < 0:
            raise AbiGateDenied("X07_PRICE_INVALID")
        projected = (
            self._state.spent_microunits
            + self._state.reserved_microunits
            + quoted_cost_microunits
        )
        if projected > self._state.budget_cap_microunits:
            raise AbiGateDenied("X07_BUDGET_DENIED")
        self._advance(
            "intent_registered",
            command_digest,
            reserved_microunits=self._state.reserved_microunits
            + quoted_cost_microunits,
        )
        receipt = CommitReceipt(
            command_id=command_id,
            command_digest=command_digest,
            version=self._state.version,
            head_seq=self._state.head_seq,
            head_hash=self._state.head_hash,
            reserved_microunits=self._state.reserved_microunits,
        )
        self._commands[command_id] = receipt
        self._intents[intent_id] = RegisteredIntent(
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            command_id=command_id,
            intent_id=intent_id,
            intent_digest=intent_digest,
            lease_epoch=lease_epoch,
            quoted_cost_microunits=quoted_cost_microunits,
        )
        self._unsettled_reservations[command_id] = quoted_cost_microunits
        return receipt

    def lookup_command(self, command_id: str) -> CommitReceipt | None:
        return self._commands.get(command_id)

    def acquire_permit(
        self,
        *,
        permit_id: str,
        intent_digest: str,
        approval_intent_digest: str,
        lease_epoch: int,
        expected_version: int,
        command_id: str | None = None,
        intent_id: str | None = None,
        approval_tenant_id: str | None = None,
        approval_run_id: str | None = None,
        approval_lease_epoch: int | None = None,
        approval_id: str | None = None,
    ) -> PermitReceipt:
        self._require_version(expected_version)
        registered = self._intents.get(intent_id or "")
        if registered is None:
            raise AbiGateDenied("X03_INTENT_NOT_REGISTERED")
        if (
            registered.command_id != command_id
            or registered.intent_digest != intent_digest
            or registered.tenant_id != approval_tenant_id
            or registered.run_id != approval_run_id
            or registered.lease_epoch != approval_lease_epoch
            or self._commands.get(command_id or "") is None
        ):
            raise AbiGateDenied("X03_T1_APPROVAL_BINDING_MISMATCH")
        if self._state.terminal:
            raise AbiGateDenied("X03_TERMINAL_IMMUTABLE")
        if lease_epoch != self._state.lease_epoch:
            raise AbiGateDenied("X03_TAKEOVER_REQUIRES_NEW_AUTHORITY")
        if approval_intent_digest != intent_digest:
            raise AbiGateDenied("X03_APPROVAL_DIGEST_MISMATCH")
        approval = self._trusted_approvals.get(approval_id or "")
        if (
            approval is None or not approval.approver_id or not approval.issuer_id
            or (
                approval.approval_id, approval.tenant_id, approval.run_id,
                approval.command_id, approval.intent_id, approval.intent_digest,
                approval.lease_epoch,
            ) != (
                approval_id, self.tenant_id, self.run_id, command_id,
                intent_id, registered.intent_digest, lease_epoch,
            )
        ):
            raise AbiGateDenied("X03_APPROVAL_AUTHORITY_UNBOUND")
        if permit_id in self._permits or intent_digest in self._permit_by_intent:
            raise AbiGateDenied("X03_ONE_TIME_PERMIT_ALREADY_CLAIMED")
        self._advance(
            "permit_claimed",
            _sha(_canonical([permit_id, intent_digest, approval.approval_id])),
        )
        receipt = PermitReceipt(
            permit_id=permit_id,
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            command_id=registered.command_id,
            intent_id=registered.intent_id,
            approval_id=approval.approval_id,
            intent_digest=intent_digest,
            lease_epoch=lease_epoch,
            version=self._state.version,
        )
        self._permits[permit_id] = receipt
        self._permit_by_intent[intent_digest] = permit_id
        return receipt

    def start_send(self, *, permit_id: str, expected_version: int) -> PermitReceipt:
        self._require_version(expected_version)
        receipt = self._permits.get(permit_id)
        if receipt is None:
            raise AbiGateDenied("X04_UNKNOWN_PERMIT")
        if receipt.consumed:
            raise AbiGateDenied("X04_PERMIT_CONSUMED")
        registered = next(
            (intent for intent in self._intents.values()
             if intent.intent_digest == receipt.intent_digest),
            None,
        )
        if (
            registered is None
            or receipt.lease_epoch != self._state.lease_epoch
            or (
                receipt.tenant_id, receipt.run_id, receipt.command_id,
                receipt.intent_id, receipt.intent_digest,
            ) != (
                self.tenant_id, self.run_id, registered.command_id,
                registered.intent_id, registered.intent_digest,
            )
        ):
            raise AbiGateDenied("X04_PERMIT_T1_OR_LEASE_INVALID")
        if self._sent_intent_id is not None:
            raise AbiGateDenied("X04_AMBIGUOUS_ACTIVE_INTENT")
        self._sent_intent_id = registered.intent_id
        consumed = replace(receipt, consumed=True)
        self._permits[permit_id] = consumed
        self._advance(
            "send_may_have_started",
            _sha(_canonical([permit_id, receipt.intent_digest])),
            effect="POSSIBLY_SENT",
        )
        return consumed

    def record_observation(
        self,
        *,
        effect: Effect,
        independent: bool,
        observed_digest: str,
        expected_version: int,
    ) -> None:
        self._require_version(expected_version)
        if effect not in {"CONFIRMED_APPLIED", "CONFIRMED_NOT_APPLIED", "UNKNOWN_EFFECT"}:
            raise AbiGateDenied("X04_OBSERVATION_EFFECT_INVALID")
        if not independent and effect != "UNKNOWN_EFFECT":
            raise AbiGateDenied("X04_OBSERVER_NOT_INDEPENDENT")
        if self._sent_intent_id is None:
            raise AbiGateDenied("X04_OBSERVATION_WITHOUT_T3")
        self._observed_digest = observed_digest
        self._observed_effect = effect
        self._advance("observation", observed_digest, effect=effect)

    def install_offline_evidence_port(
        self, port: OfflineIndependentEvidencePort
    ) -> None:
        """One-time external test harness injection, no caller labels trusted."""
        if self._evidence_port is not None:
            raise AbiGateDenied("X08_EVIDENCE_PORT_IMMUTABLE")
        self._evidence_port = port

    def settle_budget(
        self,
        *,
        actual_microunits: int | None,
        charge_id: str,
        expected_version: int,
        command_id: str | None = None,
        usage_version: str | None = None,
        source_id: str | None = None,
    ) -> None:
        if not charge_id or not command_id or not usage_version or not source_id:
            raise AbiGateDenied("X07_CHARGE_PROVENANCE_UNBOUND")
        if command_id not in self._commands:
            raise AbiGateDenied("X07_CHARGE_COMMAND_UNREGISTERED")
        fingerprint = _sha(_canonical([
            self.tenant_id, self.run_id, charge_id, command_id,
            usage_version, source_id, actual_microunits,
        ]))
        prior = self._charge_ids.get(charge_id)
        if prior is not None:
            if prior.charge_digest != fingerprint:
                raise AbiGateDenied("X07_CHARGE_ID_CONFLICT")
            return  # Identical invoice replay, including after an old CAS head.
        self._require_version(expected_version)
        if self._state.terminal:
            raise AbiGateDenied("X07_TERMINAL_BILLING_REQUIRES_SIDECAR")
        if actual_microunits is not None and actual_microunits < 0:
            raise AbiGateDenied("X07_USAGE_INVALID")
        receipt = ChargeReceipt(
            tenant_id=self.tenant_id, run_id=self.run_id,
            charge_id=charge_id, command_id=command_id,
            usage_version=usage_version, source_id=source_id,
            actual_microunits=actual_microunits, charge_digest=fingerprint,
        )
        if actual_microunits is None:
            self._advance("billing_unknown", fingerprint, billing_unknown=True)
        else:
            reserved = self._unsettled_reservations[command_id]
            remaining = self._state.reserved_microunits - reserved
            new_spent = self._state.spent_microunits + actual_microunits
            self._advance(
                "budget_settled",
                fingerprint,
                reserved_microunits=remaining,
                spent_microunits=new_spent,
                # Earlier missing-price charges do not silently resolve.
                economic_incident=self._state.economic_incident
                or actual_microunits > reserved
                or new_spent + remaining > self._state.budget_cap_microunits,
            )
            self._unsettled_reservations[command_id] = 0
        self._charge_ids[charge_id] = receipt

    def commit_terminal(
        self,
        *,
        snapshot: JournalSnapshot,
        action_proposal: VerificationProposal,
        publication: PublicationEligibility,
        oracle_label: str,
        expected_version: int,
        oracle_evidence_id: str | None = None,
    ) -> None:
        # A result label supplied by the terminal caller is never proof.
        port = self._evidence_port
        if port is None or not oracle_evidence_id:
            raise AbiGateDenied("X09_NATIVE_ORACLE_EVIDENCE_UNBOUND")
        native = port.native
        if native.oracle_id != oracle_evidence_id:
            raise AbiGateDenied("X09_NATIVE_ORACLE_EVIDENCE_UNBOUND")
        oracle = compare_native_source(native.original, native.observed)
        if oracle.label != EXPECTED_ACCEPT_FIXTURE_ONLY:
            raise AbiGateDenied("X09_INDEPENDENT_ORACLE_REJECTED")
        if oracle_label != EXPECTED_ACCEPT_FIXTURE_ONLY:
            raise AbiGateDenied("X09_INDEPENDENT_ORACLE_REJECTED")
        fingerprint = _sha(_canonical([
            asdict(snapshot), asdict(action_proposal), asdict(publication),
            oracle_evidence_id,
        ]))
        if self._state.terminal:
            if self._terminal_fingerprint == fingerprint:
                return
            raise AbiGateDenied("X05_TERMINAL_IMMUTABLE")
        self._require_version(expected_version)
        if (snapshot.tenant_id, snapshot.run_id) != (self.tenant_id, self.run_id):
            raise AbiGateDenied("X08_SNAPSHOT_SCOPE_MISMATCH")
        if snapshot.head_seq != self._state.head_seq or snapshot.head_hash != self._state.head_hash:
            raise AbiGateDenied("X08_STALE_VERIFIER_HEAD")
        if snapshot.lease_epoch != self._state.lease_epoch:
            raise AbiGateDenied("X08_STALE_VERIFIER_EPOCH")
        if snapshot.unknown_effect or self._state.effect == "UNKNOWN_EFFECT":
            raise AbiGateDenied("X08_UNKNOWN_EFFECT")
        if action_proposal.effect not in {
            "CONFIRMED_APPLIED", "CONFIRMED_NOT_APPLIED",
        }:
            raise AbiGateDenied("X08_ACTION_EFFECT_UNRESOLVED")
        if action_proposal.effect != self._state.effect:
            raise AbiGateDenied("X08_ACTION_LEDGER_EFFECT_MISMATCH")
        if self._state.effect != "CONFIRMED_APPLIED":
            raise AbiGateDenied("X08_NOT_APPLIED_CANNOT_SUCCEED")
        if publication.status != "ELIGIBLE_PROPOSAL" or publication.terminal_committed:
            raise AbiGateDenied("X08_PUBLICATION_PROPOSAL_INVALID")
        registered = self._intents.get(action_proposal.intent_id)
        if registered is None or self._sent_intent_id != action_proposal.intent_id:
            raise AbiGateDenied("X08_ACTION_LEDGER_BINDING_MISMATCH")
        permit_id = self._permit_by_intent.get(registered.intent_digest)
        permit = self._permits.get(permit_id or "")
        if permit is None or not permit.consumed or permit.lease_epoch != snapshot.lease_epoch:
            raise AbiGateDenied("X08_SEND_CLAIM_UNPROVEN")
        action = port.action
        if (
            action.tenant_id, action.run_id, action.command_id, action.intent_id,
            action.intent_digest, action.permit_id, action.lease_epoch,
            action.observation_digest, action.effect,
        ) != (
            self.tenant_id, self.run_id, registered.command_id, registered.intent_id,
            registered.intent_digest, permit_id, snapshot.lease_epoch,
            self._observed_digest, self._observed_effect,
        ) or action.observer_id not in port.trusted_observer_ids:
            raise AbiGateDenied("X08_ACTION_LEDGER_BINDING_MISMATCH")
        proof = port.publication
        if (
            proof.tenant_id, proof.run_id, proof.intent_id, proof.intent_digest,
            proof.outcome_id, proof.outcome_digest, proof.head_seq, proof.head_hash,
            proof.lease_epoch, proof.verification_id, proof.first_verified_frame_id,
            proof.content_sha256, proof.effect,
        ) != (
            self.tenant_id, self.run_id, registered.intent_id,
            registered.intent_digest, snapshot.outcome_id, snapshot.outcome_digest,
            snapshot.head_seq, snapshot.head_hash, snapshot.lease_epoch,
            publication.verification_id, publication.first_verified_frame_id,
            publication.content_sha256, self._state.effect,
        ) or proof.verifier_id not in port.trusted_verifier_ids:
            raise AbiGateDenied("X08_PUBLICATION_OUTCOME_UNVERIFIED")
        if (
            native.tenant_id, native.run_id, native.verification_id,
            native.verified_content_sha256, native.original.tenant_id,
        ) != (
            self.tenant_id, self.run_id, publication.verification_id,
            publication.content_sha256, self.tenant_id,
        ):
            raise AbiGateDenied("X09_NATIVE_ORACLE_SOURCE_SCOPE_MISMATCH")
        if self._state.billing_unknown:
            raise AbiGateDenied("X07_BILLING_UNKNOWN")
        if self._state.economic_incident:
            raise AbiGateDenied("X07_ECONOMIC_INCIDENT")
        if self._state.reserved_microunits:
            raise AbiGateDenied("X07_UNSETTLED_RESERVATIONS")
        self._advance(
            "terminal_committed",
            _sha(_canonical([
                registered.command_id, registered.intent_digest,
                action.observation_digest, proof.verification_id, oracle_evidence_id,
            ])),
            terminal=True,
            terminal_state="SUCCEEDED",
        )
        self._terminal_fingerprint = fingerprint

    def revoke_dependency(
        self, *, dependency_id: str, expected_generation: int
    ) -> int:
        if expected_generation != self._state.exclusion_generation:
            raise AbiGateDenied("X06_REVOCATION_GENERATION_CONFLICT")
        generation = self._state.exclusion_generation + 1
        # The exclusion ledger is a separate control-plane stream.  In
        # particular, a post-terminal revocation must not rewrite the run head.
        self._state = replace(
            self._state,
            version=self._state.version + 1,
            exclusion_generation=generation,
            revoked_dependencies=self._state.revoked_dependencies | {dependency_id},
        )
        return generation

    def require_readable(self, *, dependency_id: str, proof_generation: int) -> None:
        if proof_generation != self._state.exclusion_generation:
            raise AbiGateDenied("X06_STALE_REVOCATION_GENERATION")
        if dependency_id in self._state.revoked_dependencies:
            raise AbiGateDenied("X06_DEPENDENCY_REVOKED")

    def append_post_terminal_notice(
        self,
        *,
        notice: PostTerminalNotice,
    ) -> None:
        if not self._state.terminal:
            raise AbiGateDenied("X05_NOTICE_REQUIRES_TERMINAL")
        if (notice.tenant_id, notice.run_id) != (self.tenant_id, self.run_id):
            raise AbiGateDenied("X05_NOTICE_SCOPE_MISMATCH")
        if notice.original_terminal_head_hash != self._state.head_hash:
            raise AbiGateDenied("X05_NOTICE_TERMINAL_BINDING_MISMATCH")
        expected = len(self._notices) + 1
        if notice.revision != expected or notice.cursor != expected:
            raise AbiGateDenied("X05_NOTICE_ORDER_CONFLICT")
        if any(item.notice_id == notice.notice_id for item in self._notices):
            raise AbiGateDenied("X05_NOTICE_ID_REUSED")
        self._notices += (notice,)

    def _require_version(self, expected_version: int) -> None:
        if expected_version != self._state.version:
            raise AbiGateDenied("X04_CAS_CONFLICT")

    def _advance(self, event_type: str, payload_digest: str, **changes: object) -> None:
        head_seq = self._state.head_seq + 1
        head_hash = _sha(
            _canonical(
                [self._state.head_hash, head_seq, event_type, payload_digest, self.run_id]
            )
        )
        self._state = replace(
            self._state,
            version=self._state.version + 1,
            head_seq=head_seq,
            head_hash=head_hash,
            **changes,
        )


OFFLINE_BLOCKER_DISPOSITION = MappingProxyType(
    {
        "X01": "OFFLINE_ENGINEERING_PROOF",
        "X02": "FAIL_CLOSED_PENDING_REAL_IDP_LEGAL_AUTHORITY",
        "X03": "OFFLINE_ENGINEERING_PROOF",
        "X04": "OFFLINE_MODEL_ONLY_PENDING_DURABLE_BACKEND_PROOF",
        "X05": "OFFLINE_ENGINEERING_PROOF_PENDING_CLIENT_POLICY",
        "X06": "FAIL_CLOSED_PENDING_LEGAL_STORE_AUTHORITY",
        "X07": "OFFLINE_ENGINEERING_PROOF_PENDING_PRICE_AUTHORITY",
        "X08": "OFFLINE_ENGINEERING_PROOF_PENDING_REAL_SIGNER",
        "X09": "OFFLINE_FIXTURE_ONLY_PENDING_NATIVE_PRODUCTION_EVIDENCE",
    }
)
