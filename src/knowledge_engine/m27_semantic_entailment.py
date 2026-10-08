"""M27-native semantic entailment interface. No lexical-overlap success fallback.

Only a separately configured, independently validated provider can mark claims
supported. A citation or a matching token is never sufficient by itself.
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


class SemanticEntailmentProvider(Protocol):
    def verify(self, claim: MaterialClaim, evidence: Sequence[EvidencePassage]) -> EntailmentVerdict: ...


MISSING_PROVIDER_STATE = "M27_SEMANTIC_ENTAILMENT_PROVIDER_MISSING"
SUPPORTED_LABELS = frozenset((SupportLabel.DIRECT, SupportLabel.PARAPHRASE, SupportLabel.CLUSTERED))


def verify_material_claim(claim: MaterialClaim,
                          passages: Sequence[EvidencePassage],
                          provider: SemanticEntailmentProvider | None = None) -> EntailmentVerdict:
    """Fail closed on missing provider, missing citation identity or unsupported output.

    Provider integration is intentionally not self-certified by a model string.
    External provider must establish reliability, multilingual performance,
    cluster rules and calibration before production use.
    """
    if provider is None:
        return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), "none", MISSING_PROVIDER_STATE)
    allowed = set(claim.cited_passage_ids)
    cluster = [e for e in passages if e.passage_id in allowed and e.source_id and e.locator_id]
    if not cluster or len(cluster) != len(allowed):
        return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), "none", "missing_bound_citation_evidence")
    try:
        verdict = provider.verify(claim, cluster)
    except Exception:
        return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), "none", "provider_error")
    if not isinstance(verdict, EntailmentVerdict):
        return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), "none", "invalid_provider_result")
    if verdict.label in SUPPORTED_LABELS and (
        not verdict.verified or not verdict.provider_id or
        not set(verdict.supporting_passage_ids).issubset(allowed) or
        not verdict.supporting_passage_ids
    ):
        return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), "none", "unverified_support_claim")
    return verdict
