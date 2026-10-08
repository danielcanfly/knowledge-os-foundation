"""M27 semantic publication policy over calibrated entailment verdicts."""
from __future__ import annotations
from typing import Sequence
from .m27_semantic_entailment import (
    EvidencePassage, MaterialClaim, SemanticEntailmentProvider,
    SupportLabel, verify_material_claim,
)

PUBLICATION_SUPPORTED_LABELS = frozenset(
    (SupportLabel.DIRECT, SupportLabel.PARAPHRASE, SupportLabel.CLUSTERED)
)


def verify_publication_claim(
    claim: MaterialClaim,
    passages: Sequence[EvidencePassage],
    provider: SemanticEntailmentProvider | None,
) -> tuple[bool, dict[str, object]]:
    verdict = verify_material_claim(claim, passages, provider)
    accepted = verdict.verified and verdict.label in PUBLICATION_SUPPORTED_LABELS
    if verdict.label is SupportLabel.CLUSTERED:
        accepted = accepted and len(set(verdict.supporting_passage_ids)) >= 2
    fail_reason = "" if accepted else verdict.reason or "semantic_support_rejected"
    receipt = {
        "claim_id": claim.claim_id,
        "evidence_ids": list(claim.cited_passage_ids),
        "supporting_evidence_ids": list(verdict.supporting_passage_ids),
        "support_class": verdict.label.value,
        "provider_status": verdict.provider_id or "none",
        "confidence": round(float(verdict.confidence), 4),
        "verified": bool(verdict.verified),
        "publication_accepted": bool(accepted),
        "provider_attempt_count": int(verdict.attempt_count),
        "schema_retry_used": bool(verdict.schema_retry_used),
        "fail_closed_reason": fail_reason,
    }
    return bool(accepted), receipt
