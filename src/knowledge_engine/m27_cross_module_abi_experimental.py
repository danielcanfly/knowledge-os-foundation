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
from knowledge_engine.m27_ar09_oracle_experimental import EXPECTED_ACCEPT_FIXTURE_ONLY

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


class OfflineAuthorityGate:
    """Validates byte preservation and synthetic authority without label trust."""

    def __init__(self, *, trusted_keys: Mapping[str, bytes]) -> None:
        self._trusted_keys = MappingProxyType(dict(trusted_keys))

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
    ) -> None:
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
        if auth.consent_required and not auth.consent_ref:
            raise AbiGateDenied("X02_CONSENT_ABSENT")


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
    intent_digest: str
    lease_epoch: int
    version: int
    consumed: bool = False


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
    ) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id
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
        self._permits: dict[str, PermitReceipt] = {}
        self._permit_by_intent: dict[str, str] = {}
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
    ) -> CommitReceipt:
        prior = self._commands.get(command_id)
        command_digest = _sha(
            _canonical([intent_digest, quoted_cost_microunits, self.tenant_id, self.run_id])
        )
        if prior is not None:
            if prior.command_digest != command_digest:
                raise AbiGateDenied("X04_COMMAND_DIGEST_CONFLICT")
            return prior
        self._require_version(expected_version)
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
    ) -> PermitReceipt:
        self._require_version(expected_version)
        if self._state.terminal:
            raise AbiGateDenied("X03_TERMINAL_IMMUTABLE")
        if lease_epoch != self._state.lease_epoch:
            raise AbiGateDenied("X03_TAKEOVER_REQUIRES_NEW_AUTHORITY")
        if approval_intent_digest != intent_digest:
            raise AbiGateDenied("X03_APPROVAL_DIGEST_MISMATCH")
        if permit_id in self._permits or intent_digest in self._permit_by_intent:
            raise AbiGateDenied("X03_ONE_TIME_PERMIT_ALREADY_CLAIMED")
        self._advance("permit_claimed", _sha(_canonical([permit_id, intent_digest])))
        receipt = PermitReceipt(
            permit_id=permit_id,
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
        self._advance("observation", observed_digest, effect=effect)

    def settle_budget(
        self,
        *,
        actual_microunits: int | None,
        charge_id: str,
        expected_version: int,
    ) -> None:
        self._require_version(expected_version)
        if actual_microunits is None:
            self._advance("billing_unknown", charge_id, billing_unknown=True)
            return
        if actual_microunits < 0:
            raise AbiGateDenied("X07_USAGE_INVALID")
        incident = actual_microunits > self._state.reserved_microunits
        new_spent = self._state.spent_microunits + actual_microunits
        self._advance(
            "budget_settled",
            _sha(_canonical([charge_id, actual_microunits])),
            reserved_microunits=0,
            spent_microunits=new_spent,
            billing_unknown=False,
            economic_incident=self._state.economic_incident
            or incident
            or new_spent > self._state.budget_cap_microunits,
        )

    def commit_terminal(
        self,
        *,
        snapshot: JournalSnapshot,
        action_proposal: VerificationProposal,
        publication: PublicationEligibility,
        oracle_label: str,
        expected_version: int,
    ) -> None:
        self._require_version(expected_version)
        if self._state.terminal:
            raise AbiGateDenied("X05_TERMINAL_IMMUTABLE")
        if snapshot.head_seq != self._state.head_seq or snapshot.head_hash != self._state.head_hash:
            raise AbiGateDenied("X08_STALE_VERIFIER_HEAD")
        if snapshot.lease_epoch != self._state.lease_epoch:
            raise AbiGateDenied("X08_STALE_VERIFIER_EPOCH")
        if snapshot.unknown_effect or self._state.effect == "UNKNOWN_EFFECT":
            raise AbiGateDenied("X08_UNKNOWN_EFFECT")
        if action_proposal.effect not in {
            "CONFIRMED_APPLIED",
            "CONFIRMED_NOT_APPLIED",
        }:
            raise AbiGateDenied("X08_ACTION_EFFECT_UNRESOLVED")
        if publication.status != "ELIGIBLE_PROPOSAL" or publication.terminal_committed:
            raise AbiGateDenied("X08_PUBLICATION_PROPOSAL_INVALID")
        if oracle_label != EXPECTED_ACCEPT_FIXTURE_ONLY:
            raise AbiGateDenied("X09_INDEPENDENT_ORACLE_REJECTED")
        if self._state.billing_unknown:
            raise AbiGateDenied("X07_BILLING_UNKNOWN")
        if self._state.economic_incident:
            raise AbiGateDenied("X07_ECONOMIC_INCIDENT")
        self._advance(
            "terminal_committed",
            _sha(_canonical([action_proposal.intent_id, publication.verification_id])),
            terminal=True,
            terminal_state="SUCCEEDED",
        )

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
