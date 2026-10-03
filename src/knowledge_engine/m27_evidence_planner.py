from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from . import m26_pa7_arbitrary_query_runtime as legacy
from .m27_context_runtime_contracts import (
    STAGE3_UNAVAILABLE,
    EvidenceGapSummary,
    EvidenceIdentity,
    EvidencePlanningResult,
    Stage3Unavailable,
)

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_M26_SUFFICIENCY_STATES = frozenset(
    {
        "sufficient",
        "partially_sufficient",
        "conflicting",
        "insufficient",
        "no_match",
    }
)
_SUPPORTED = "SUPPORTED"
_MISSING_SUPPORT_STATES = frozenset({"UNSUPPORTED", "UNKNOWN"})


class LegacyM26EvidencePlannerAdapter:
    """Normalize already-produced M26 evidence planning outputs.

    This adapter never performs retrieval, evidence selection, evidence strengthening,
    reranking, support scoring, or policy decisions. It only exposes identities and
    existing coverage/gap signals in a privacy-safe Stage 3 contract.
    """

    def normalize(
        self,
        *,
        selected_evidence: Sequence[Mapping[str, object]],
        requirements: Sequence[object] = (),
        support_classification: Sequence[Mapping[str, object]] | None = None,
        endpoint_proof: Mapping[str, object] | None = None,
        sufficiency_status: str | None = None,
        reason_codes: Sequence[str] = (),
    ) -> EvidencePlanningResult:
        identities = tuple(_evidence_identity(item) for item in selected_evidence)
        requirement_ids = _requirement_ids(requirements)
        covered, missing, coverage_status = _coverage_summary(
            requirement_ids=requirement_ids,
            support_classification=support_classification,
        )
        recovered, bounded_recovery_used = _recovery_summary(endpoint_proof)

        return EvidencePlanningResult(
            selected_evidence=identities,
            selected_evidence_count=len(selected_evidence),
            selected_evidence_ids=_complete_identity_tuple(
                item.evidence_id for item in identities
            ),
            selected_passage_ids=_complete_identity_tuple(
                item.passage_id for item in identities
            ),
            source_identities=_complete_identity_tuple(
                item.source_identity for item in identities
            ),
            distinct_source_count=_distinct_source_count(identities),
            locator_ids=_complete_identity_tuple(item.locator_id for item in identities),
            requirement_ids=requirement_ids,
            gap=EvidenceGapSummary(
                covered_requirement_ids=covered,
                missing_requirement_ids=missing,
                coverage_status=coverage_status,
                sufficiency_status=_sufficiency_status(sufficiency_status),
                recovered_requirement_ids=recovered,
                bounded_recovery_used=bounded_recovery_used,
                reason_codes=_safe_reason_codes(reason_codes),
            ),
        )


def _evidence_identity(item: Mapping[str, object]) -> EvidenceIdentity:
    return EvidenceIdentity(
        evidence_id=_safe_identity(item.get("evidence_id")),
        passage_id=_safe_identity(item.get("passage_id")),
        source_identity=_source_identity(item),
        locator_id=_safe_identity(item.get("locator_id")),
        evidence_type=_safe_identity(item.get("evidence_type")),
    )


def _source_identity(item: Mapping[str, object]) -> str | Stage3Unavailable:
    explicit = _safe_identity(item.get("source_identity"))
    if explicit != STAGE3_UNAVAILABLE:
        return explicit

    source_id = _safe_identity(item.get("source_id"))
    if source_id != STAGE3_UNAVAILABLE:
        return source_id

    artifact_key = _safe_identity(item.get("artifact_key"))
    section_id = _safe_identity(item.get("section_id"))
    if (
        artifact_key == STAGE3_UNAVAILABLE
        or section_id == STAGE3_UNAVAILABLE
    ):
        return STAGE3_UNAVAILABLE

    # Reuse the current M26 deterministic source-identity rule rather than
    # creating a parallel Stage 3 identity implementation.
    resolved = legacy._source_identity(item)
    return _safe_identity(resolved)


def _safe_identity(value: object) -> str | Stage3Unavailable:
    if not isinstance(value, str):
        return STAGE3_UNAVAILABLE
    normalized = value.strip()
    return normalized if normalized else STAGE3_UNAVAILABLE


def _complete_identity_tuple(
    values: Sequence[str | Stage3Unavailable] | Any,
) -> tuple[str, ...] | Stage3Unavailable:
    materialized = tuple(values)
    if any(value == STAGE3_UNAVAILABLE for value in materialized):
        return STAGE3_UNAVAILABLE
    return tuple(str(value) for value in materialized)


def _distinct_source_count(
    identities: Sequence[EvidenceIdentity],
) -> int | Stage3Unavailable:
    sources = _complete_identity_tuple(item.source_identity for item in identities)
    if sources == STAGE3_UNAVAILABLE:
        return STAGE3_UNAVAILABLE
    return len(set(sources))


def _requirement_ids(
    requirements: Sequence[object],
) -> tuple[str, ...] | Stage3Unavailable:
    if not requirements:
        return ()
    result: list[str] = []
    for requirement in requirements:
        if isinstance(requirement, Mapping):
            value = requirement.get("requirement_id")
        else:
            value = getattr(requirement, "requirement_id", None)
        identity = _safe_identity(value)
        if identity == STAGE3_UNAVAILABLE:
            return STAGE3_UNAVAILABLE
        result.append(identity)
    return tuple(dict.fromkeys(result))


def _coverage_summary(
    *,
    requirement_ids: tuple[str, ...] | Stage3Unavailable,
    support_classification: Sequence[Mapping[str, object]] | None,
) -> tuple[
    tuple[str, ...] | Stage3Unavailable,
    tuple[str, ...] | Stage3Unavailable,
    str | Stage3Unavailable,
]:
    if requirement_ids == STAGE3_UNAVAILABLE:
        return STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE
    if not requirement_ids:
        return (), (), "not_applicable"
    if support_classification is None:
        return STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE

    states: dict[str, str] = {}
    for item in support_classification:
        requirement_id = _safe_identity(item.get("facet_id"))
        state = item.get("support_state")
        if requirement_id == STAGE3_UNAVAILABLE or not isinstance(state, str):
            continue
        states[requirement_id] = state

    if any(requirement_id not in states for requirement_id in requirement_ids):
        return STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE
    if any(
        states[requirement_id] not in {_SUPPORTED, *_MISSING_SUPPORT_STATES}
        for requirement_id in requirement_ids
    ):
        return STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE

    covered = tuple(
        requirement_id
        for requirement_id in requirement_ids
        if states[requirement_id] == _SUPPORTED
    )
    missing = tuple(
        requirement_id
        for requirement_id in requirement_ids
        if states[requirement_id] in _MISSING_SUPPORT_STATES
    )
    return covered, missing, "gap_present" if missing else "covered"


def _recovery_summary(
    endpoint_proof: Mapping[str, object] | None,
) -> tuple[tuple[str, ...] | Stage3Unavailable, bool | Stage3Unavailable]:
    if endpoint_proof is None:
        return STAGE3_UNAVAILABLE, STAGE3_UNAVAILABLE

    raw_recovered = endpoint_proof.get("recovered_facets")
    if not isinstance(raw_recovered, Sequence) or isinstance(raw_recovered, (str, bytes)):
        recovered: tuple[str, ...] | Stage3Unavailable = STAGE3_UNAVAILABLE
    else:
        normalized = tuple(_safe_identity(value) for value in raw_recovered)
        recovered = _complete_identity_tuple(normalized)

    raw_bounded = endpoint_proof.get("bounded_authorized_corpus_recovery")
    bounded = raw_bounded if isinstance(raw_bounded, bool) else STAGE3_UNAVAILABLE
    return recovered, bounded


def _sufficiency_status(value: str | None) -> str | Stage3Unavailable:
    if value in _M26_SUFFICIENCY_STATES:
        return str(value)
    return STAGE3_UNAVAILABLE


def _safe_reason_codes(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        value
        for value in values
        if isinstance(value, str) and _SAFE_CODE_RE.fullmatch(value)
    )
