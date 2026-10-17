"""D01 opt-in Nonprod integration for source, verifier, Client, and outcome.

This module is deliberately absent from every default Product entrypoint. It
binds the accepted C02 candidate behind an explicit D01 policy and keeps local
fixture delivery distinct from externally qualified publication.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .m27_c02_native_composer import (
    ClientAckVerifier,
    ClientPublisher,
    ComposerResult,
    Generator,
    compose_native_candidate,
)
from .m27_c02_semantic_provider import SourceBinding, SourceBoundSemanticProvider

D01_INTEGRATION_ABI = "m27.d01.nonprod-source-verifier-client-outcome/v1"
D01_POLICY_MODE = "D01_NONPROD_OPT_IN_CANDIDATE"


@dataclass(frozen=True, slots=True)
class D01Policy:
    opt_in_enabled: bool
    mode: str = D01_POLICY_MODE
    allow_ephemeral_fixture_client: bool = False
    provider_grant_independently_proven: bool = False
    real_client_authority_proven: bool = False
    product_release_authority_proven: bool = False


@dataclass(frozen=True, slots=True)
class D01SourceSpec:
    path: Path
    source_id: str
    title: str
    observed_revision: str
    expected_revision: str
    expected_source_sha256: str
    byte_start: int
    byte_end: int
    expected_excerpt_sha256: str
    language: str
    tenant_id: str
    allowed_principals: tuple[str, ...]
    expires_at_epoch_s: float
    license_id: str
    rights_grant_id: str
    rights_valid_until_epoch_s: float
    source_revoked: bool = False
    rights_revoked: bool = False


@dataclass(frozen=True, slots=True)
class D01Outcome:
    schema_version: str
    request_id: str
    run_id: str
    status: str
    terminal_reason: str
    source_receipt: Mapping[str, Any]
    stage_timings: Mapping[str, Mapping[str, int | float]]
    composer_result: Mapping[str, Any]
    fixture_transport_delivery: bool
    official_client_publication: bool
    c02_semantic_admission: bool
    native_composer_admission: bool
    formal_product_go: bool
    c28: bool
    f35: bool
    rel01: bool
    production: str
    cost: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stage(start_wall_ns: int, start_mono_ns: int) -> dict[str, int | float]:
    end_wall_ns = time.time_ns()
    end_mono_ns = time.monotonic_ns()
    return {
        "started_wall_epoch_ns": start_wall_ns,
        "ended_wall_epoch_ns": end_wall_ns,
        "started_monotonic_ns": start_mono_ns,
        "ended_monotonic_ns": end_mono_ns,
        "duration_ms": round((end_mono_ns - start_mono_ns) / 1_000_000, 3),
    }


def _closed(
    *,
    request_id: str,
    run_id: str,
    reason: str,
    source_receipt: Mapping[str, Any] | None = None,
    timings: Mapping[str, Mapping[str, int | float]] | None = None,
    composer: ComposerResult | None = None,
) -> D01Outcome:
    composer_value = composer.as_dict() if composer is not None else {}
    return D01Outcome(
        D01_INTEGRATION_ABI,
        request_id,
        run_id,
        "SAFE_TERMINAL",
        reason,
        source_receipt or {},
        timings or {},
        composer_value,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        "NO_GO",
        {
            "provider_cost_units": float(
                composer.provider_receipt.get("cost_units", 0.0) if composer else 0.0
            ),
            "external_billable_calls": 0,
            "local_compute_cost_claimed_zero": False,
        },
    )


def _load_source(
    spec: D01SourceSpec,
    *,
    tenant_id: str,
    principal: str,
    now: float,
) -> tuple[SourceBinding | None, dict[str, Any], str | None]:
    if not spec.path.is_file() or spec.path.is_symlink():
        return None, {}, "SOURCE_FILE_MISSING_OR_SYMLINK"
    raw = spec.path.read_bytes()
    source_sha = _sha(raw)
    if source_sha != spec.expected_source_sha256:
        return None, {}, "SOURCE_DATA_SHA_MISMATCH"
    if spec.observed_revision != spec.expected_revision:
        return None, {}, "SOURCE_REVISION_MISMATCH"
    if not spec.rights_grant_id:
        return None, {}, "SOURCE_RIGHTS_GRANT_MISSING"
    if spec.rights_revoked:
        return None, {}, "SOURCE_RIGHTS_REVOKED"
    if now >= spec.rights_valid_until_epoch_s:
        return None, {}, "SOURCE_RIGHTS_STALE"
    if not (0 <= spec.byte_start < spec.byte_end <= len(raw)):
        return None, {}, "SOURCE_SPAN_INVALID"
    excerpt = raw[spec.byte_start : spec.byte_end]
    excerpt_sha = _sha(excerpt)
    if excerpt_sha != spec.expected_excerpt_sha256:
        return None, {}, "SOURCE_EXCERPT_SHA_MISMATCH"
    binding = SourceBinding(
        source_id=spec.source_id,
        title=spec.title,
        revision=spec.observed_revision,
        raw_bytes=raw,
        source_sha256=source_sha,
        byte_start=spec.byte_start,
        byte_end=spec.byte_end,
        excerpt_sha256=excerpt_sha,
        language=spec.language,
        tenant_id=spec.tenant_id,
        allowed_principals=spec.allowed_principals,
        expires_at_epoch_s=spec.expires_at_epoch_s,
        revoked=spec.source_revoked,
        license_id=spec.license_id,
    )
    denial = binding.validate(tenant_id=tenant_id, principal=principal, now=now)
    receipt = {
        "path": str(spec.path.resolve()),
        "source_id": spec.source_id,
        "title": spec.title,
        "revision": spec.observed_revision,
        "source_sha256": source_sha,
        "byte_start": spec.byte_start,
        "byte_end": spec.byte_end,
        "excerpt_sha256": excerpt_sha,
        "tenant_id": spec.tenant_id,
        "allowed_principals": list(spec.allowed_principals),
        "license_id": spec.license_id,
        "rights_grant_id": spec.rights_grant_id,
        "rights_valid_until_epoch_s": spec.rights_valid_until_epoch_s,
    }
    return (None, receipt, denial) if denial else (binding, receipt, None)


class _TimedProvider:
    def __init__(
        self,
        provider: SourceBoundSemanticProvider,
        timings: dict[str, Mapping[str, int | float]],
    ) -> None:
        self._provider = provider
        self._timings = timings
        self.authority = provider.authority

    def verify(self, *args: Any, **kwargs: Any):
        start_wall = time.time_ns()
        start_mono = time.monotonic_ns()
        try:
            return self._provider.verify(*args, **kwargs)
        finally:
            self._timings["verifier"] = _stage(start_wall, start_mono)


def run_d01_nonprod_e2e(
    *,
    request_id: str,
    run_id: str,
    question: str,
    tenant_id: str,
    principal: str,
    source_specs: Sequence[D01SourceSpec],
    generator: Generator,
    semantic_provider: SourceBoundSemanticProvider | None,
    client_publisher: ClientPublisher | None,
    verify_client_ack: ClientAckVerifier | None,
    budget_units: float,
    policy: D01Policy,
    now: float | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> D01Outcome:
    """Run the optional candidate without changing any default Product route."""
    timings: dict[str, Mapping[str, int | float]] = {}
    if not policy.opt_in_enabled or policy.mode != D01_POLICY_MODE:
        return _closed(
            request_id=request_id,
            run_id=run_id,
            reason="C02_OPTIONAL_MODULE_NOT_EXPLICITLY_ENABLED",
        )
    if not request_id or not run_id or not question.strip() or not source_specs:
        return _closed(
            request_id=request_id,
            run_id=run_id,
            reason="D01_REQUEST_INVALID",
        )
    observed_now = time.time() if now is None else float(now)
    retrieval_wall = time.time_ns()
    retrieval_mono = time.monotonic_ns()
    bindings: list[SourceBinding] = []
    source_receipts: list[Mapping[str, Any]] = []
    for spec in source_specs:
        binding, receipt, denial = _load_source(
            spec,
            tenant_id=tenant_id,
            principal=principal,
            now=observed_now,
        )
        source_receipts.append(receipt)
        if denial or binding is None:
            timings["source_retrieval"] = _stage(retrieval_wall, retrieval_mono)
            return _closed(
                request_id=request_id,
                run_id=run_id,
                reason=denial or "SOURCE_BINDING_DENIED",
                source_receipt={"sources": source_receipts},
                timings=timings,
            )
        bindings.append(binding)
    timings["source_retrieval"] = _stage(retrieval_wall, retrieval_mono)

    def timed_generator(q: str, sources: Sequence[SourceBinding]):
        start_wall = time.time_ns()
        start_mono = time.monotonic_ns()
        try:
            return generator(q, sources)
        finally:
            timings["generator"] = _stage(start_wall, start_mono)

    timed_provider = _TimedProvider(semantic_provider, timings) if semantic_provider else None

    def timed_client(event: Mapping[str, Any]) -> Mapping[str, Any]:
        if client_publisher is None:
            return {}
        start_wall = time.time_ns()
        start_mono = time.monotonic_ns()
        try:
            return client_publisher(event)
        finally:
            timings["client"] = _stage(start_wall, start_mono)

    composer = compose_native_candidate(
        request_id=request_id,
        run_id=run_id,
        question=question,
        tenant_id=tenant_id,
        principal=principal,
        sources=tuple(bindings),
        generator=timed_generator,
        semantic_provider=timed_provider,
        client_publisher=timed_client if client_publisher else None,
        verify_client_ack=verify_client_ack,
        budget_units=budget_units,
        now=observed_now,
        cancelled=cancelled,
        allow_nonqualifying_fixture_delivery=policy.allow_ephemeral_fixture_client,
    )
    fixture_delivery = composer.status == "FIXTURE_ONLY" and bool(composer.client_receipt)
    provider_admitted = bool(
        composer.provider_qualification_proven
        and composer.native_composer_admitted
        and policy.provider_grant_independently_proven
    )
    official_publication = bool(
        composer.publishable
        and provider_admitted
        and policy.real_client_authority_proven
        and policy.product_release_authority_proven
    )
    if composer.native_composer_admitted and not provider_admitted:
        return _closed(
            request_id=request_id,
            run_id=run_id,
            reason="D01_AUTHORITY_LEDGER_DENIED_NATIVE_ADMISSION",
            source_receipt={"sources": source_receipts},
            timings=timings,
            composer=composer,
        )
    status = "OFFICIAL_PUBLICATION" if official_publication else composer.status
    return D01Outcome(
        D01_INTEGRATION_ABI,
        request_id,
        run_id,
        status,
        composer.terminal_reason,
        {"sources": source_receipts},
        timings,
        composer.as_dict(),
        fixture_delivery,
        official_publication,
        provider_admitted,
        provider_admitted,
        False,
        False,
        False,
        False,
        "NO_GO",
        {
            "provider_cost_units": float(composer.provider_receipt.get("cost_units", 0.0)),
            "external_billable_calls": 0,
            "local_compute_cost_claimed_zero": False,
        },
    )
