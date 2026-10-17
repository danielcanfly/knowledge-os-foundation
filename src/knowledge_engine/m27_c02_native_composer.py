"""C02 Native Composer candidate with explicit non-admission semantics."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from .m27_c02_semantic_provider import (
    SemanticRequest,
    SourceBinding,
    SourceBoundSemanticProvider,
    new_nonce,
)

C02_COMPOSER_ABI = "m27.c02.native-composer/v1"
C02_CLIENT_ACK_ABI = "m27.c02.client-ack/v1"


@dataclass(frozen=True, slots=True)
class GeneratedClaim:
    text: str
    cited_source_ids: tuple[str, ...]
    model_identity: str
    model_version: str
    actual_model_output: bool
    generation_duration_ms: float


@dataclass(frozen=True, slots=True)
class ComposerResult:
    status: str
    publishable: bool
    native_composer_admitted: bool
    provider_qualification_proven: bool
    terminal_reason: str
    events: tuple[Mapping[str, Any], ...]
    provider_receipt: Mapping[str, Any]
    client_receipt: Mapping[str, Any]
    citations: tuple[Mapping[str, Any], ...]
    timings_ms: Mapping[str, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


Generator = Callable[[str, Sequence[SourceBinding]], GeneratedClaim]
ClientPublisher = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ClientAckVerifier = Callable[[Mapping[str, Any], Mapping[str, Any]], bool]


def _sha(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _terminal(
    reason: str,
    events: list[Mapping[str, Any]],
    started: int,
    provider_receipt: Mapping[str, Any] | None = None,
    client_receipt: Mapping[str, Any] | None = None,
) -> ComposerResult:
    end_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    events.append(
        {"sequence": len(events) + 1, "type": "safe_terminal", "reason": reason, "event_ms": end_ms}
    )
    return ComposerResult(
        "SAFE_TERMINAL",
        False,
        False,
        False,
        reason,
        tuple(events),
        provider_receipt or {},
        client_receipt or {},
        (),
        {"total": end_ms},
    )


def compose_native_candidate(
    *,
    request_id: str,
    run_id: str,
    question: str,
    tenant_id: str,
    principal: str,
    sources: Sequence[SourceBinding],
    generator: Generator,
    semantic_provider: SourceBoundSemanticProvider | None,
    client_publisher: ClientPublisher | None,
    verify_client_ack: ClientAckVerifier | None,
    budget_units: float,
    now: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    allow_nonqualifying_fixture_delivery: bool = False,
) -> ComposerResult:
    started = time.perf_counter_ns()
    events: list[Mapping[str, Any]] = []
    if cancelled and cancelled():
        return _terminal("CANCELLED_BEFORE_GENERATION", events, started)
    if not request_id or not run_id or not question.strip() or not sources:
        return _terminal("COMPOSER_REQUEST_INVALID", events, started)
    events.append(
        {
            "sequence": 1,
            "type": "sources_bound",
            "source_ids": [s.source_id for s in sources],
            "source_sha256": [s.source_sha256 for s in sources],
            "event_ms": 0.0,
        }
    )
    generation_start = time.perf_counter_ns()
    try:
        claim = generator(question, sources)
    except Exception:
        return _terminal("GENERATOR_CRASH", events, started)
    generation_ms = round((time.perf_counter_ns() - generation_start) / 1_000_000, 3)
    if (
        not isinstance(claim, GeneratedClaim)
        or not claim.actual_model_output
        or not claim.text.strip()
        or not claim.cited_source_ids
        or any(
            sid not in {source.source_id for source in sources} for sid in claim.cited_source_ids
        )
    ):
        return _terminal("GENERATED_CLAIM_INVALID_OR_NOT_REAL_MODEL", events, started)
    events.append(
        {
            "sequence": len(events) + 1,
            "type": "generated_claim_candidate",
            "text_sha256": hashlib.sha256(claim.text.encode()).hexdigest(),
            "generator_model_identity": claim.model_identity,
            "generator_model_version": claim.model_version,
            "actual_model_output": True,
            "event_ms": generation_ms,
        }
    )
    if semantic_provider is None:
        return _terminal("PROVIDER_QUALIFICATION_NOT_PROVEN", events, started)
    bound = tuple(source for source in sources if source.source_id in claim.cited_source_ids)
    verification = semantic_provider.verify(
        SemanticRequest(
            request_id=request_id,
            run_id=run_id,
            nonce=new_nonce(),
            tenant_id=tenant_id,
            principal=principal,
            task="semantic_entailment",
            claim_text=claim.text,
            claim_language=bound[0].language if bound else "unknown",
            generator_model_identity=claim.model_identity,
            sources=bound,
            budget_units=budget_units,
        ),
        now=now,
        cancelled=cancelled,
    )
    events.append(
        {
            "sequence": len(events) + 1,
            "type": "semantic_verification",
            "decision": verification.decision.value,
            "verified": verification.verified,
            "admission_eligible": verification.admission_eligible,
            "provider_id": verification.provider_id,
            "event_ms": verification.duration_ms,
        }
    )
    if not verification.verified:
        return _terminal(
            verification.reason or "SEMANTIC_REJECTED", events, started, verification.receipt
        )
    fixture_delivery = not verification.admission_eligible
    if fixture_delivery and not allow_nonqualifying_fixture_delivery:
        return _terminal("PROVIDER_QUALIFICATION_NOT_PROVEN", events, started, verification.receipt)
    citations = tuple(
        {
            "source_id": source.source_id,
            "title": source.title,
            "revision": source.revision,
            "source_sha256": source.source_sha256,
            "byte_start": source.byte_start,
            "byte_end": source.byte_end,
            "excerpt_sha256": source.excerpt_sha256,
            "license_id": source.license_id,
            "memory_citation_authority": False,
        }
        for source in bound
        if source.source_id in verification.supporting_source_ids
    )
    if not citations:
        return _terminal(
            "VERIFIED_RESULT_HAS_NO_BOUND_CITATION", events, started, verification.receipt
        )
    event = {
        "sequence": len(events) + 1,
        "type": "verified_answer_text",
        "request_id": request_id,
        "run_id": run_id,
        "text": claim.text,
        "text_sha256": hashlib.sha256(claim.text.encode()).hexdigest(),
        "citations": list(citations),
        "qualification_class": semantic_provider.authority.evidence_class.value,
        "formal_admission_eligible": verification.admission_eligible,
        "event_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }
    event_sha = _sha(event)
    if client_publisher is None or verify_client_ack is None:
        return _terminal("CLIENT_ACK_PATH_MISSING", events, started, verification.receipt)
    try:
        ack = client_publisher(event)
    except Exception:
        return _terminal("CLIENT_PUBLICATION_FAILED", events, started, verification.receipt)
    if (
        not isinstance(ack, Mapping)
        or ack.get("schema_version") != C02_CLIENT_ACK_ABI
        or ack.get("request_id") != request_id
        or ack.get("run_id") != run_id
        or ack.get("event_sha256") != event_sha
        or not verify_client_ack(ack, event)
    ):
        return _terminal(
            "CLIENT_ACK_INVALID",
            events,
            started,
            verification.receipt,
            ack if isinstance(ack, Mapping) else {},
        )
    events.append(event)
    total_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    events.append(
        {
            "sequence": len(events) + 1,
            "type": "terminal",
            "status": "FIXTURE_ONLY" if fixture_delivery else "SUCCEEDED",
            "event_ms": total_ms,
        }
    )
    admitted = verification.admission_eligible and not fixture_delivery
    return ComposerResult(
        "FIXTURE_ONLY" if fixture_delivery else "SUCCEEDED",
        True,
        admitted,
        admitted,
        "NONQUALIFYING_FIXTURE_DELIVERY" if fixture_delivery else "VERIFIED_CLIENT_ACK",
        tuple(events),
        verification.receipt,
        dict(ack),
        citations,
        {"generation": generation_ms, "verification": verification.duration_ms, "total": total_ms},
    )
