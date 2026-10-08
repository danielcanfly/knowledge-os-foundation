"""M27-native semantic entailment interface.

Publication support is established only by a calibrated semantic provider over
explicitly bound citation evidence. Citation presence and lexical overlap are
never sufficient.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence


class SupportLabel(str, Enum):
    DIRECT = "direct_support"
    PARAPHRASE = "paraphrase_support"
    CLUSTERED = "clustered_support"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient_evidence"


@dataclass(frozen=True)
class EvidencePassage:
    source_id: str
    locator_id: str
    passage_id: str
    text: str
    language: str


@dataclass(frozen=True)
class MaterialClaim:
    claim_id: str
    text: str
    answer_start: int
    answer_end: int
    language: str
    cited_passage_ids: tuple[str, ...]


@dataclass(frozen=True)
class EntailmentVerdict:
    label: SupportLabel
    verified: bool
    supporting_passage_ids: tuple[str, ...]
    provider_id: str
    reason: str
    confidence: float = 0.0
    attempt_count: int = 0
    schema_retry_used: bool = False


class SemanticEntailmentProvider(Protocol):
    def verify(self, claim: MaterialClaim, evidence: Sequence[EvidencePassage]) -> EntailmentVerdict: ...


MISSING_PROVIDER_STATE = "M27_SEMANTIC_ENTAILMENT_PROVIDER_MISSING"
SUPPORTED_LABELS = frozenset((SupportLabel.DIRECT, SupportLabel.PARAPHRASE, SupportLabel.CLUSTERED))


def _closed(reason: str, provider_id: str = "none", *, confidence: float = 0.0,
            attempt_count: int = 0, schema_retry_used: bool = False) -> EntailmentVerdict:
    return EntailmentVerdict(
        SupportLabel.INSUFFICIENT, False, (), provider_id, reason,
        confidence, attempt_count, schema_retry_used,
    )


def verify_material_claim(
    claim: MaterialClaim,
    passages: Sequence[EvidencePassage],
    provider: SemanticEntailmentProvider | None = None,
) -> EntailmentVerdict:
    """Verify one material claim against exactly its cited evidence, fail closed."""
    if provider is None:
        return _closed(MISSING_PROVIDER_STATE)

    cited = tuple(claim.cited_passage_ids)
    if not cited or len(set(cited)) != len(cited):
        return _closed("invalid_citation_binding")

    allowed = set(cited)
    cluster = [
        e for e in passages
        if e.passage_id in allowed and e.source_id and e.locator_id and e.text.strip()
    ]
    if len(cluster) != len(allowed) or {e.passage_id for e in cluster} != allowed:
        return _closed("missing_bound_citation_evidence")

    try:
        verdict = provider.verify(claim, cluster)
    except Exception:
        return _closed("provider_error")

    if not isinstance(verdict, EntailmentVerdict):
        return _closed("invalid_provider_result")

    confidence = float(verdict.confidence) if isinstance(verdict.confidence, (int, float)) else 0.0
    if not 0.0 <= confidence <= 1.0:
        return _closed(
            "invalid_provider_confidence", verdict.provider_id or "none",
            attempt_count=verdict.attempt_count, schema_retry_used=verdict.schema_retry_used,
        )

    if verdict.label in SUPPORTED_LABELS:
        refs = tuple(verdict.supporting_passage_ids)
        if (
            not verdict.verified
            or not verdict.provider_id
            or not refs
            or len(set(refs)) != len(refs)
            or not set(refs).issubset(allowed)
        ):
            return _closed(
                "unverified_support_claim", verdict.provider_id or "none",
                confidence=confidence, attempt_count=verdict.attempt_count,
                schema_retry_used=verdict.schema_retry_used,
            )
        if verdict.label is SupportLabel.CLUSTERED and len(set(refs)) < 2:
            return _closed(
                "cluster_support_requires_multiple_evidence", verdict.provider_id,
                confidence=confidence, attempt_count=verdict.attempt_count,
                schema_retry_used=verdict.schema_retry_used,
            )
    return verdict
