from __future__ import annotations

from pathlib import Path

from tests.test_m26_aq_canonical_semantic_contract_convergence import (
    SEGMENT_SCHEMA_VERSION,
    _TypedCompactProvider,
)
from tests.test_m27_production_evidence_bridge import (
    ProductionKnowledgeProvider,
    _harness,
    _input,
    _production_bridge_material,
    _request,
)


def test_pinned_evidence_does_not_validate_unentailed_model_claim(tmp_path: Path):
    evidence, authority = _production_bridge_material()
    provider = _TypedCompactProvider({
        "schema_version": SEGMENT_SCHEMA_VERSION,
        "status": "answer",
        "segments": [{
            "segment_id": "s1", "semantic_role": "material_claim",
            "claim_id": "claim_1", "claim_type": "EVIDENCE_FACT",
            "text": "Graphology guarantees profits for stock market investors.",
            "evidence_labels": ["e1"], "covers": ["graphology_storage"],
        }],
        "unanswered_dimensions": [], "abstention_reason": None,
    })
    result = _harness(tmp_path, ProductionKnowledgeProvider(evidence)).run(
        _input(_request(provider, evidence, authority))
    )
    # The canonical verifier may recover a DIFFERENT, independently supported
    # deterministic citation after rejecting the provider's unsupported claim.
    # Either safe-abstain or publish only a verified replacement.  A composed
    # result must not echo the injected unentailed surface.
    assert result.status_code in {"M27_RUNTIME_SAFE_TERMINAL", "M27_RUNTIME_COMPOSED"}
    assert provider.calls >= 1
    if result.status_code == "M27_RUNTIME_COMPOSED":
        assert result.verification is not None
        assert result.verification["material_claim_support_verified"] is True
        assert result.verification["citation_locator_valid"] is True
        assert result.verification["unsupported_accepted_claims"] == 0
        assert result.verification["citations"]
        assert result.verification["production_evidence_authority"] is True
        assert "profits" not in str(result.answer).casefold()
        assert "investors" not in str(result.answer).casefold()
    else:
        assert not result.answer


class UnknownEffectProvider:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, payload, call_class):
        self.calls += 1
        raise TimeoutError("provider outcome unknown")


def test_pinned_bridge_unknown_effect_never_retries(tmp_path: Path):
    evidence, authority = _production_bridge_material()
    provider = UnknownEffectProvider()
    result = _harness(tmp_path, ProductionKnowledgeProvider(evidence)).run(
        _input(_request(provider, evidence, authority))
    )
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert provider.calls == 1
    assert not result.answer
    assert result.production_touched is False


def test_pinned_bridge_zero_provider_budget_denied_without_call(tmp_path: Path):
    evidence, authority = _production_bridge_material()
    provider = UnknownEffectProvider()
    result = _harness(tmp_path, ProductionKnowledgeProvider(evidence)).run(
        _input(_request(provider, evidence, authority), attempts=0)
    )
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert provider.calls == 0
    assert not result.answer
