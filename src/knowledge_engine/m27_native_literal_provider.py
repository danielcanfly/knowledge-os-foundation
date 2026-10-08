"""Conservative literal-only baseline; NEVER a calibrated semantic provider.

Exact evidence identity is the sole positive path. All paraphrase, translation,
cluster synthesis, and ambiguous support abstain. Calibration must reject release.
"""
from .m27_semantic_entailment import EntailmentVerdict, SupportLabel

class LiteralBaselineProvider:
    provider_id = "m27-native-literal-baseline"
    provider_version = "0.1.0-uncalibrated"

    def verify(self, claim, evidence):
        if not claim.text.strip() or not evidence:
            return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), self.provider_id, "empty_claim_or_evidence")
        if any(not x.text.strip() or not x.locator_id or not x.source_id for x in evidence):
            return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), self.provider_id, "missing_evidence_binding")
        if any(x.language != claim.language for x in evidence):
            return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), self.provider_id, "cross_language_not_implemented")
        matches = [x for x in evidence if claim.text.strip() == x.text.strip()]
        if len(matches) == 1:
            return EntailmentVerdict(SupportLabel.DIRECT, True, (matches[0].passage_id,), self.provider_id, "literal_identity_only")
        return EntailmentVerdict(SupportLabel.INSUFFICIENT, False, (), self.provider_id, "semantic_entailment_unavailable")
