"""C02 source-bound semantic provider ABI.

This module is an admission boundary, not an entailment implementation.  It
accepts a provider decision only when source bytes, caller authority, provider
identity, budget, freshness, replay protection, and an external attestation
verifier all agree.  Deterministic fixtures can exercise the transport, but are
permanently ineligible for provider qualification.
"""

from __future__ import annotations

import hashlib
import json
import queue
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

C02_PROVIDER_ABI = "m27.c02.source-bound-semantic-provider/v1"
C02_RESPONSE_ABI = "m27.c02.semantic-provider-response/v1"


class SemanticDecision(StrEnum):
    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class TrustStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_PROVEN = "NOT_PROVEN"
    EXPLICITLY_REFUSED = "EXPLICITLY_REFUSED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class EvidenceClass(StrEnum):
    EXTERNAL_QUALIFICATION = "EXTERNAL_QUALIFICATION"
    DETERMINISTIC_FIXTURE = "DETERMINISTIC_FIXTURE"
    LOCAL_MODEL_CANDIDATE = "LOCAL_MODEL_CANDIDATE"


@dataclass(frozen=True, slots=True)
class SourceBinding:
    source_id: str
    title: str
    revision: str
    raw_bytes: bytes
    source_sha256: str
    byte_start: int
    byte_end: int
    excerpt_sha256: str
    language: str
    tenant_id: str
    allowed_principals: tuple[str, ...]
    expires_at_epoch_s: float
    revoked: bool = False
    license_id: str = "FIRST_PARTY_NONPROD"
    memory_citation_authority: bool = False

    @property
    def excerpt(self) -> str:
        return self.raw_bytes[self.byte_start : self.byte_end].decode("utf-8")

    def validate(self, *, tenant_id: str, principal: str, now: float) -> str | None:
        if not self.source_id or not self.title or not self.revision or not self.license_id:
            return "SOURCE_IDENTITY_INCOMPLETE"
        if hashlib.sha256(self.raw_bytes).hexdigest() != self.source_sha256:
            return "SOURCE_BYTES_TAMPERED"
        if not (0 <= self.byte_start < self.byte_end <= len(self.raw_bytes)):
            return "SOURCE_SPAN_INVALID"
        excerpt = self.raw_bytes[self.byte_start : self.byte_end]
        if hashlib.sha256(excerpt).hexdigest() != self.excerpt_sha256:
            return "SOURCE_SPAN_TAMPERED"
        try:
            excerpt.decode("utf-8")
        except UnicodeDecodeError:
            return "SOURCE_SPAN_NOT_UTF8"
        if self.revoked:
            return "SOURCE_REVOKED"
        if now >= self.expires_at_epoch_s:
            return "SOURCE_STALE"
        if tenant_id != self.tenant_id:
            return "TENANT_MISMATCH"
        if principal not in self.allowed_principals:
            return "ACL_DENIED"
        if self.memory_citation_authority:
            return "MEMORY_IS_NOT_CITATION_AUTHORITY"
        return None


@dataclass(frozen=True, slots=True)
class ProviderAuthority:
    provider_id: str
    model_identity: str
    model_version: str
    runtime_sha256: str
    license_id: str
    license_sha256: str
    signer_id: str
    qualification_receipt_sha256: str
    trust_status: TrustStatus
    evidence_class: EvidenceClass
    task_bounds: tuple[str, ...]
    languages: tuple[str, ...]
    authorized_principals: tuple[str, ...]
    valid_until_epoch_s: float
    max_attempts: int
    timeout_ms: int
    max_cost_units: float
    retry_safe: bool = False
    revoked: bool = False
    model_architecture: str = ""
    allowed_model_architectures: tuple[str, ...] = ()
    license_scope: str = ""
    approved_license_ids: tuple[str, ...] = ()

    @property
    def admission_eligible(self) -> bool:
        return (
            self.trust_status is TrustStatus.VERIFIED
            and self.evidence_class is EvidenceClass.EXTERNAL_QUALIFICATION
            and bool(self.qualification_receipt_sha256)
            and not self.revoked
        )


@dataclass(frozen=True, slots=True)
class SemanticRequest:
    request_id: str
    run_id: str
    nonce: str
    tenant_id: str
    principal: str
    task: str
    claim_text: str
    claim_language: str
    generator_model_identity: str
    sources: tuple[SourceBinding, ...]
    budget_units: float


@dataclass(frozen=True, slots=True)
class SemanticOutcome:
    decision: SemanticDecision
    verified: bool
    admission_eligible: bool
    reason: str
    confidence: float
    supporting_source_ids: tuple[str, ...]
    provider_id: str
    model_identity: str
    model_version: str
    request_sha256: str
    attempts: int
    duration_ms: float
    cost_units: float
    receipt: Mapping[str, Any]


Transport = Callable[[Mapping[str, Any]], Mapping[str, Any]]
AttestationVerifier = Callable[[Mapping[str, Any], Mapping[str, Any]], bool]
AuthorityVerifier = Callable[[ProviderAuthority], bool]
CancelCheck = Callable[[], bool]


def _canonical_sha(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _closed(
    reason: str,
    *,
    request_sha256: str = "",
    attempts: int = 0,
    duration_ms: float = 0.0,
    provider_id: str = "none",
    model_identity: str = "",
    model_version: str = "",
    receipt: Mapping[str, Any] | None = None,
) -> SemanticOutcome:
    return SemanticOutcome(
        SemanticDecision.UNKNOWN,
        False,
        False,
        reason,
        0.0,
        (),
        provider_id,
        model_identity,
        model_version,
        request_sha256,
        attempts,
        duration_ms,
        0.0,
        receipt or {"schema_version": C02_PROVIDER_ABI, "accepted": False, "reason": reason},
    )


def _call_with_timeout(transport: Transport, payload: Mapping[str, Any], timeout_ms: int):
    result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            result.put((True, transport(payload)))
        except BaseException as exc:  # converted to a fail-closed receipt below
            result.put((False, exc))

    worker = threading.Thread(target=invoke, name="m27-c02-semantic-provider", daemon=True)
    worker.start()
    try:
        ok, value = result.get(timeout=timeout_ms / 1000)
    except queue.Empty as exc:
        raise TimeoutError("PROVIDER_TIMEOUT") from exc
    if not ok:
        raise RuntimeError("PROVIDER_CRASH") from value
    return value


class SourceBoundSemanticProvider:
    """Fail-closed adapter for an independently attested semantic provider."""

    def __init__(
        self,
        authority: ProviderAuthority,
        transport: Transport,
        verify_attestation: AttestationVerifier | None,
        verify_authority: AuthorityVerifier | None = None,
    ) -> None:
        self.authority = authority
        self.transport = transport
        self.verify_attestation = verify_attestation
        try:
            self._authority_verified = bool(verify_authority and verify_authority(authority))
        except Exception:
            self._authority_verified = False
        self._seen_attestations: set[str] = set()

    def verify(
        self,
        request: SemanticRequest,
        *,
        now: float | None = None,
        cancelled: CancelCheck | None = None,
    ) -> SemanticOutcome:
        started = time.perf_counter_ns()
        observed_now = time.time() if now is None else float(now)
        authority = self.authority
        identity = (authority.provider_id, authority.model_identity, authority.model_version)

        if cancelled and cancelled():
            return _closed(
                "CANCELLED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if authority.trust_status is not TrustStatus.VERIFIED:
            return _closed(
                "PROVIDER_AUTHORITY_NOT_VERIFIED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if (
            authority.evidence_class is EvidenceClass.EXTERNAL_QUALIFICATION
            and not self._authority_verified
        ):
            return _closed(
                "PROVIDER_QUALIFICATION_RECEIPT_INVALID",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if authority.revoked:
            return _closed(
                "PROVIDER_POLICY_REVOKED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if observed_now >= authority.valid_until_epoch_s:
            return _closed(
                "PROVIDER_AUTHORITY_EXPIRED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if not all((authority.runtime_sha256, authority.license_id, authority.license_sha256)):
            return _closed(
                "PROVIDER_RUNTIME_OR_LICENSE_UNPROVEN",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if (
            not authority.model_architecture
            or authority.model_architecture not in authority.allowed_model_architectures
        ):
            return _closed(
                "PROVIDER_MODEL_ARCHITECTURE_UNSUPPORTED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if (
            authority.license_scope != "NONPROD_SEMANTIC_VERIFICATION"
            or authority.license_id not in authority.approved_license_ids
        ):
            return _closed(
                "PROVIDER_LICENSE_OR_RIGHT_DENIED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if request.principal not in authority.authorized_principals:
            return _closed(
                "PROVIDER_PRINCIPAL_DENIED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if request.task not in authority.task_bounds:
            return _closed(
                "PROVIDER_TASK_OUT_OF_SCOPE",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if request.claim_language not in authority.languages:
            return _closed(
                "PROVIDER_LANGUAGE_UNSUPPORTED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if request.budget_units <= 0 or request.budget_units > authority.max_cost_units:
            return _closed(
                "PROVIDER_BUDGET_DENIED",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if request.generator_model_identity == authority.model_identity:
            return _closed(
                "VERIFIER_NOT_INDEPENDENT_OF_GENERATOR",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if (
            not request.request_id
            or not request.run_id
            or not request.nonce
            or not request.claim_text.strip()
        ):
            return _closed(
                "MALFORMED_SEMANTIC_REQUEST",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if not request.sources:
            return _closed(
                "NO_BOUND_SOURCE",
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        source_ids: list[str] = []
        source_payload = []
        for source in request.sources:
            reason = source.validate(
                tenant_id=request.tenant_id, principal=request.principal, now=observed_now
            )
            if reason:
                return _closed(
                    reason,
                    provider_id=identity[0],
                    model_identity=identity[1],
                    model_version=identity[2],
                )
            if source.source_id in source_ids:
                return _closed(
                    "DUPLICATE_SOURCE_BINDING",
                    provider_id=identity[0],
                    model_identity=identity[1],
                    model_version=identity[2],
                )
            source_ids.append(source.source_id)
            source_payload.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "revision": source.revision,
                    "source_sha256": source.source_sha256,
                    "byte_start": source.byte_start,
                    "byte_end": source.byte_end,
                    "excerpt_sha256": source.excerpt_sha256,
                    "excerpt": source.excerpt,
                    "language": source.language,
                    "license_id": source.license_id,
                }
            )
        payload = {
            "schema_version": C02_PROVIDER_ABI,
            "request_id": request.request_id,
            "run_id": request.run_id,
            "nonce": request.nonce,
            "tenant_id": request.tenant_id,
            "principal": request.principal,
            "task": request.task,
            "claim": {"text": request.claim_text, "language": request.claim_language},
            "sources": source_payload,
            "provider": {
                "provider_id": authority.provider_id,
                "model_identity": authority.model_identity,
                "model_version": authority.model_version,
            },
            "budget_units": request.budget_units,
        }
        request_sha = _canonical_sha(payload)
        expected_keys = {
            "schema_version",
            "request_id",
            "run_id",
            "nonce",
            "provider_id",
            "model_identity",
            "model_version",
            "decision",
            "confidence",
            "reason",
            "supporting_source_ids",
            "cost_units",
            "issued_at_epoch_s",
            "expires_at_epoch_s",
            "signer_id",
            "attestation_id",
            "attestation",
        }
        attempts = 0
        for attempt in range(1, max(1, min(authority.max_attempts, 2)) + 1):
            attempts = attempt
            try:
                response = _call_with_timeout(self.transport, payload, authority.timeout_ms)
            except TimeoutError:
                duration = (time.perf_counter_ns() - started) / 1_000_000
                return _closed(
                    "PROVIDER_TIMEOUT_UNKNOWN",
                    request_sha256=request_sha,
                    attempts=attempts,
                    duration_ms=duration,
                    provider_id=identity[0],
                    model_identity=identity[1],
                    model_version=identity[2],
                )
            except Exception:
                if not authority.retry_safe or attempt >= authority.max_attempts:
                    duration = (time.perf_counter_ns() - started) / 1_000_000
                    return _closed(
                        "PROVIDER_CRASH",
                        request_sha256=request_sha,
                        attempts=attempts,
                        duration_ms=duration,
                        provider_id=identity[0],
                        model_identity=identity[1],
                        model_version=identity[2],
                    )
                continue
            if not isinstance(response, Mapping) or set(response) != expected_keys:
                if authority.retry_safe and attempt < authority.max_attempts:
                    continue
                return _closed(
                    "PROVIDER_MALFORMED_RESPONSE",
                    request_sha256=request_sha,
                    attempts=attempts,
                    provider_id=identity[0],
                    model_identity=identity[1],
                    model_version=identity[2],
                )
            break
        else:
            return _closed(
                "PROVIDER_ATTEMPTS_EXHAUSTED",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )

        if cancelled and cancelled():
            return _closed(
                "CANCELLED_AFTER_PROVIDER",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if (
            response["schema_version"] != C02_RESPONSE_ABI
            or response["request_id"] != request.request_id
            or response["run_id"] != request.run_id
            or response["nonce"] != request.nonce
        ):
            return _closed(
                "CROSS_RUN_OR_NONCE_REPLAY",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if (
            response["provider_id"],
            response["model_identity"],
            response["model_version"],
        ) != identity:
            return _closed(
                "PROVIDER_OR_MODEL_IDENTITY_MISMATCH",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if response["signer_id"] != authority.signer_id:
            return _closed(
                "PROVIDER_SIGNER_MISMATCH",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        attestation_id = response["attestation_id"]
        if (
            not isinstance(attestation_id, str)
            or not attestation_id
            or attestation_id in self._seen_attestations
        ):
            return _closed(
                "PROVIDER_ATTESTATION_REPLAY",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if not (
            isinstance(response["issued_at_epoch_s"], (int, float))
            and isinstance(response["expires_at_epoch_s"], (int, float))
            and response["issued_at_epoch_s"] <= observed_now < response["expires_at_epoch_s"]
            and response["expires_at_epoch_s"] <= authority.valid_until_epoch_s
        ):
            return _closed(
                "PROVIDER_RESPONSE_STALE_OR_INVALID",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        try:
            decision = SemanticDecision(response["decision"])
        except (ValueError, TypeError):
            return _closed(
                "PROVIDER_DECISION_UNKNOWN",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        confidence = response["confidence"]
        refs = response["supporting_source_ids"]
        cost = response["cost_units"]
        if (
            type(confidence) not in (int, float)
            or not 0 <= confidence <= 1
            or not isinstance(response["reason"], str)
            or not response["reason"].strip()
            or not isinstance(refs, list)
            or len(refs) != len(set(refs))
            or any(ref not in source_ids for ref in refs)
            or type(cost) not in (int, float)
            or cost < 0
            or cost > request.budget_units
            or cost > authority.max_cost_units
        ):
            return _closed(
                "PROVIDER_RESPONSE_FIELDS_INVALID",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        if self.verify_attestation is None or not self.verify_attestation(response, payload):
            return _closed(
                "PROVIDER_ATTESTATION_INVALID",
                request_sha256=request_sha,
                attempts=attempts,
                provider_id=identity[0],
                model_identity=identity[1],
                model_version=identity[2],
            )
        self._seen_attestations.add(attestation_id)
        supported = decision is SemanticDecision.ENTAILED and confidence >= 0.85 and bool(refs)
        if decision is SemanticDecision.ENTAILED and not supported:
            decision = SemanticDecision.UNKNOWN
        duration = round((time.perf_counter_ns() - started) / 1_000_000, 3)
        receipt = {
            "schema_version": C02_PROVIDER_ABI,
            "accepted": supported,
            "admission_eligible": authority.admission_eligible and self._authority_verified,
            "evidence_class": authority.evidence_class.value,
            "request_sha256": request_sha,
            "request_id": request.request_id,
            "run_id": request.run_id,
            "provider_id": authority.provider_id,
            "model_identity": authority.model_identity,
            "model_version": authority.model_version,
            "decision": decision.value,
            "confidence": float(confidence),
            "supporting_source_ids": list(refs if supported else []),
            "attempts": attempts,
            "duration_ms": duration,
            "cost_units": float(cost),
            "attestation_id": attestation_id,
            "qualification_receipt_sha256": authority.qualification_receipt_sha256,
        }
        return SemanticOutcome(
            decision,
            supported,
            supported and authority.admission_eligible and self._authority_verified,
            response["reason"],
            float(confidence),
            tuple(refs if supported else ()),
            authority.provider_id,
            authority.model_identity,
            authority.model_version,
            request_sha,
            attempts,
            duration,
            float(cost),
            receipt,
        )


def new_nonce() -> str:
    return secrets.token_hex(16)
