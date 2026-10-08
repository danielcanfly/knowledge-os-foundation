"""Fail-closed M27 narrow semantic entailment judge adapter.

The adapter performs at most one schema retry. It never repairs enum casing or
coerces malformed provider output into a legal verdict.
"""
import json
from .m27_semantic_entailment import EntailmentVerdict, SupportLabel

LABELS = {
    "DIRECT_SUPPORT": SupportLabel.DIRECT,
    "PARAPHRASE_SUPPORT": SupportLabel.PARAPHRASE,
    "CLUSTER_SUPPORT": SupportLabel.CLUSTERED,
    "TOPICAL_ONLY": SupportLabel.UNSUPPORTED,
    "UNSUPPORTED": SupportLabel.UNSUPPORTED,
    "THIN_CITED_NEGATIVE": SupportLabel.UNSUPPORTED,
    "CONTRADICTED": SupportLabel.CONTRADICTED,
    "INSUFFICIENT_PROVIDER_CAPABILITY": SupportLabel.INSUFFICIENT,
}
_POSITIVE = {SupportLabel.DIRECT, SupportLabel.PARAPHRASE, SupportLabel.CLUSTERED}


def parse_verdict(raw, allowed):
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict) or set(raw) != {
        "support_class", "confidence", "reason", "evidence_references"
    }:
        raise ValueError("schema_keys")
    kind = raw["support_class"]
    confidence = raw["confidence"]
    refs = raw["evidence_references"]
    reason = raw["reason"]
    if (
        kind not in LABELS
        or type(confidence) not in (float, int)
        or not 0 <= confidence <= 1
        or not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 500
        or not isinstance(refs, list)
        or len(set(refs)) != len(refs)
        or any(not isinstance(x, str) or x not in allowed for x in refs)
    ):
        raise ValueError("schema_fields")
    return raw


class M27NativeJudgeAdapter:
    def __init__(self, invoke, threshold=0.85):
        self.invoke = invoke
        self.threshold = float(threshold)

    def _schema_parse_with_one_retry(self, claim, evidence, allowed):
        attempts = 1
        raw = self.invoke(claim, evidence)
        try:
            return parse_verdict(raw, allowed), attempts, False
        except (ValueError, TypeError, json.JSONDecodeError):
            attempts = 2
            raw = self.invoke(claim, evidence)
            try:
                return parse_verdict(raw, allowed), attempts, True
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("schema_invalid_after_retry") from exc

    def verify(self, claim, evidence):
        allowed = [e.passage_id for e in evidence]
        try:
            result, attempts, retried = self._schema_parse_with_one_retry(
                claim, evidence, allowed
            )
        except ValueError as exc:
            return EntailmentVerdict(
                SupportLabel.INSUFFICIENT, False, (), "m27-minimax-nli",
                str(exc) or "schema_invalid_after_retry", 0.0, 2, True,
            )
        except Exception:
            return EntailmentVerdict(
                SupportLabel.INSUFFICIENT, False, (), "m27-minimax-nli",
                "provider_unavailable", 0.0, 1, False,
            )

        label = LABELS[result["support_class"]]
        confidence = float(result["confidence"])
        refs = tuple(result["evidence_references"])
        supported = (
            label in _POSITIVE
            and confidence >= self.threshold
            and bool(refs)
        )
        if label in _POSITIVE and not supported:
            return EntailmentVerdict(
                SupportLabel.INSUFFICIENT, False, (), "m27-minimax-nli",
                "low_confidence_or_missing_support_reference", confidence,
                attempts, retried,
            )
        return EntailmentVerdict(
            label, supported, refs if supported else (), "m27-minimax-nli",
            result["reason"], confidence, attempts, retried,
        )
