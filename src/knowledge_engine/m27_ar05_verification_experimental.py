"""Offline-only AR05 verification and publication proposal gate.

This module consumes immutable synthetic facts.  It cannot dispatch publication,
transition RunState, or authenticate a real signer/source.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from types import MappingProxyType
from typing import Literal

GateResult = Literal["pass", "fail", "indeterminate"]
FrameKind = Literal["progress", "verified_text", "provisional", "terminal"]


class VerificationDenied(ValueError):
    """A hard gate failed closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class JournalSnapshot:
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    attempt: int
    head_seq: int
    head_hash: str
    lease_epoch: int
    outcome_id: str
    outcome_digest: str
    unknown_effect: bool
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class HardGate:
    name: str
    result: GateResult


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    """Signed fake verifier input. There is deliberately no ``verified`` flag."""

    verification_id: str
    signer_id: str
    key_id: str
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    attempt: int
    outcome_id: str
    outcome_digest: str
    journal_head_seq: int
    journal_head_hash: str
    lease_epoch: int
    checked_at: int
    expires_at: int
    hard_gates: tuple[HardGate, ...]
    signature: str

    def unsigned(self) -> VerificationReceipt:
        return replace(self, signature="")


@dataclass(frozen=True, slots=True)
class CitationBinding:
    citation_id: str
    source_id: str
    source_revision: str
    source_bytes_sha256: str
    claim_start: int
    claim_end: int


@dataclass(frozen=True, slots=True)
class NativeEvidenceFixture:
    """Synthetic analogue of a non-mutating native EvidenceBundleRef view."""

    identity_kind: Literal["native", "synthetic"]
    content_bytes: bytes
    content_sha256: str
    citations: tuple[CitationBinding, ...]


@dataclass(frozen=True, slots=True)
class ContentFrame:
    frame_id: str
    kind: FrameKind
    payload: bytes
    citation_ids: tuple[str, ...]
    verification_id: str | None
    server_emitted: bool
    client_ack_id: str | None


@dataclass(frozen=True, slots=True)
class PublicationCandidate:
    publication_id: str
    segment_id: str
    revision: int
    irreversible: bool
    claim_client_delivered: bool
    original_evidence: NativeEvidenceFixture
    observed_evidence: NativeEvidenceFixture
    expected_citation_ids: tuple[str, ...]
    frames: tuple[ContentFrame, ...]


@dataclass(frozen=True, slots=True)
class PublicationEligibility:
    status: Literal["ELIGIBLE_PROPOSAL"]
    verification_id: str
    first_verified_frame_id: str
    content_sha256: str
    server_emission_observed: bool
    client_delivery_proven: bool
    terminal_committed: bool = False


@dataclass(frozen=True, slots=True)
class PublicationNotice:
    publication_id: str
    revision: int
    cursor: int
    kind: Literal["correction", "retraction"]
    supersedes_segment_id: str
    content_digest: str
    run_state_changed: bool = False


def _canonical(value: object) -> bytes:
    def default(item: object) -> object:
        if isinstance(item, bytes):
            return {"bytes_sha256": hashlib.sha256(item).hexdigest(), "length": len(item)}
        raise TypeError(type(item).__name__)

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=default,
    ).encode()


def verification_message(receipt: VerificationReceipt) -> bytes:
    """Return deterministic fake signature bytes without trusting receipt labels."""

    return _canonical(asdict(receipt.unsigned()))


class VerificationPublicationGate:
    """Fail-closed proposal service with trust roots fixed at construction."""

    def __init__(
        self,
        *,
        verifier_keys: Mapping[str, bytes],
        signer_for_key: Mapping[str, str],
        generator_id: str,
    ) -> None:
        self._verifier_keys = MappingProxyType(dict(verifier_keys))
        self._signer_for_key = MappingProxyType(dict(signer_for_key))
        self._generator_id = generator_id

    @property
    def provider_calls(self) -> int:
        return 0

    def evaluate(
        self,
        *,
        snapshot: JournalSnapshot,
        receipt: VerificationReceipt,
        publication: PublicationCandidate,
        now: int,
    ) -> PublicationEligibility:
        """Return an eligibility proposal; never mutate the supplied journal snapshot."""

        self._verify_identity(snapshot, receipt)
        self._verify_trust(receipt)
        if now >= receipt.expires_at or receipt.checked_at > now:
            raise VerificationDenied("PROOF_EXPIRED_OR_FROM_FUTURE")
        if snapshot.unknown_effect:
            raise VerificationDenied("UNKNOWN_EFFECT")
        if snapshot.terminal:
            raise VerificationDenied("TERMINAL_IMMUTABLE")
        if not receipt.hard_gates or any(gate.result != "pass" for gate in receipt.hard_gates):
            raise VerificationDenied("HARD_GATE_NOT_PASS")
        if len({gate.name for gate in receipt.hard_gates}) != len(receipt.hard_gates):
            raise VerificationDenied("DUPLICATE_HARD_GATE")
        self._verify_native_evidence(publication)
        frame = self._verify_frames(publication, receipt.verification_id)
        if publication.irreversible and any(
            item.kind == "provisional" for item in publication.frames
        ):
            raise VerificationDenied("IRREVERSIBLE_PROVISIONAL_DENIED")
        client_proven = frame.client_ack_id is not None
        if publication.claim_client_delivered and not client_proven:
            raise VerificationDenied("CLIENT_DELIVERY_UNPROVEN")
        return PublicationEligibility(
            status="ELIGIBLE_PROPOSAL",
            verification_id=receipt.verification_id,
            first_verified_frame_id=frame.frame_id,
            content_sha256=hashlib.sha256(frame.payload).hexdigest(),
            server_emission_observed=frame.server_emitted,
            client_delivery_proven=client_proven,
        )

    def append_terminal_notice(
        self,
        *,
        publication_id: str,
        prior_revision: int,
        prior_cursor: int,
        kind: Literal["correction", "retraction"],
        supersedes_segment_id: str,
        content: bytes,
    ) -> PublicationNotice:
        """Create an append-only post-terminal sidecar without reopening RunState."""

        if not supersedes_segment_id:
            raise VerificationDenied("NOTICE_MISSING_SUPERSEDED_SEGMENT")
        return PublicationNotice(
            publication_id=publication_id,
            revision=prior_revision + 1,
            cursor=prior_cursor + 1,
            kind=kind,
            supersedes_segment_id=supersedes_segment_id,
            content_digest=hashlib.sha256(content).hexdigest(),
        )

    def _verify_identity(
        self, snapshot: JournalSnapshot, receipt: VerificationReceipt
    ) -> None:
        expected = (
            snapshot.tenant_id,
            snapshot.task_id,
            snapshot.task_version,
            snapshot.run_id,
            snapshot.attempt,
            snapshot.outcome_id,
            snapshot.outcome_digest,
            snapshot.head_seq,
            snapshot.head_hash,
            snapshot.lease_epoch,
        )
        actual = (
            receipt.tenant_id,
            receipt.task_id,
            receipt.task_version,
            receipt.run_id,
            receipt.attempt,
            receipt.outcome_id,
            receipt.outcome_digest,
            receipt.journal_head_seq,
            receipt.journal_head_hash,
            receipt.lease_epoch,
        )
        if actual != expected:
            raise VerificationDenied("IDENTITY_DIGEST_OR_STALE_HEAD_MISMATCH")

    def _verify_trust(self, receipt: VerificationReceipt) -> None:
        if receipt.signer_id == self._generator_id:
            raise VerificationDenied("GENERATOR_SELF_SIGN_DENIED")
        secret = self._verifier_keys.get(receipt.key_id)
        expected_signer = self._signer_for_key.get(receipt.key_id)
        if secret is None or expected_signer != receipt.signer_id:
            raise VerificationDenied("UNTRUSTED_VERIFIER")
        expected = hmac.new(secret, verification_message(receipt), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, receipt.signature):
            raise VerificationDenied("INVALID_VERIFIER_SIGNATURE")

    def _verify_native_evidence(self, publication: PublicationCandidate) -> None:
        original = publication.original_evidence
        observed = publication.observed_evidence
        if original.identity_kind != "native" or observed.identity_kind != "native":
            raise VerificationDenied("NATIVE_SYNTHETIC_MIXUP")
        if hashlib.sha256(original.content_bytes).hexdigest() != original.content_sha256:
            raise VerificationDenied("ORIGINAL_SOURCE_BYTES_DIGEST_MISMATCH")
        if hashlib.sha256(observed.content_bytes).hexdigest() != observed.content_sha256:
            raise VerificationDenied("OBSERVED_SOURCE_BYTES_DIGEST_MISMATCH")
        if (
            original.content_bytes != observed.content_bytes
            or original.content_sha256 != observed.content_sha256
            or original.citations != observed.citations
        ):
            raise VerificationDenied("NATIVE_SOURCE_OR_CITATION_MUTATED")
        citation_ids = tuple(item.citation_id for item in original.citations)
        if citation_ids != publication.expected_citation_ids:
            raise VerificationDenied("CITATION_ORDER_CHANGED")
        for citation in original.citations:
            if (
                not citation.source_id
                or not citation.source_revision
                or citation.source_bytes_sha256 != original.content_sha256
                or citation.claim_start < 0
                or citation.claim_end <= citation.claim_start
                or citation.claim_end > len(original.content_bytes)
            ):
                raise VerificationDenied("CITATION_BINDING_OR_SPAN_INVALID")

    def _verify_frames(
        self, publication: PublicationCandidate, verification_id: str
    ) -> ContentFrame:
        terminal_index = next(
            (index for index, frame in enumerate(publication.frames) if frame.kind == "terminal"),
            None,
        )
        substantive: list[tuple[int, ContentFrame]] = [
            (index, frame)
            for index, frame in enumerate(publication.frames)
            if frame.kind == "verified_text" and bool(frame.payload.strip())
        ]
        if not substantive:
            raise VerificationDenied("NO_VERIFIED_SUBSTANTIVE_TEXT")
        index, first = substantive[0]
        if terminal_index is not None and index >= terminal_index:
            raise VerificationDenied("TERMINAL_ONLY_CONTENT")
        if first.verification_id != verification_id:
            raise VerificationDenied("FRAME_VERIFICATION_MISMATCH")
        if first.citation_ids != publication.expected_citation_ids:
            raise VerificationDenied("UNCITED_OR_REORDERED_VERIFIED_TEXT")
        if not first.server_emitted:
            raise VerificationDenied("SERVER_EMISSION_UNPROVEN")
        return first
