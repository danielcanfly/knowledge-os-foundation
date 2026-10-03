from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine.m27_context_runtime_contracts import STAGE1_UNAVAILABLE
from knowledge_engine.m27_legacy_m26_adapters import (
    LegacyM26ContextCompilerAdapter,
    LegacyM26DeadlineBudgetAdapter,
    LegacyM26SemanticRoutingAdapter,
    LegacyM26VerifierAdapter,
)


@dataclass(frozen=True)
class _RoutingSignal:
    route: str
    reason: str
    deadline_remaining_ms: int
    minimum_budget_ms: int
    provider_attempts_remaining: int

    @property
    def affordable(self) -> bool:
        return (
            self.deadline_remaining_ms >= self.minimum_budget_ms
            and self.provider_attempts_remaining > 0
        )


def test_semantic_routing_adapter_reads_existing_decision_only() -> None:
    signal = _RoutingSignal(
        route="SEMANTIC_CLOSURE",
        reason="semantic_support_gap",
        deadline_remaining_ms=7000,
        minimum_budget_ms=4500,
        provider_attempts_remaining=1,
    )

    normalized = LegacyM26SemanticRoutingAdapter().normalize(signal)

    assert normalized.route == signal.route
    assert normalized.reason == signal.reason
    assert normalized.planning_mode == STAGE1_UNAVAILABLE
    assert normalized.evidence_plan.retrieval_round_count == STAGE1_UNAVAILABLE



def test_adapters_accept_the_real_m26_semantic_routing_decision_shape() -> None:
    from knowledge_engine.m26_aq_semantic_contract import SemanticRoutingDecision

    signal = SemanticRoutingDecision(
        route="SEMANTIC_CLOSURE",
        reason="semantic_support_gap",
        deadline_remaining_ms=7000,
        minimum_budget_ms=4500,
        provider_attempts_remaining=1,
    )

    context_plan = LegacyM26SemanticRoutingAdapter().normalize(signal)
    compute = LegacyM26DeadlineBudgetAdapter().normalize(signal)

    assert context_plan.route == "SEMANTIC_CLOSURE"
    assert context_plan.reason == "semantic_support_gap"
    assert compute.deadline_remaining_ms == 7000
    assert compute.minimum_budget_ms == 4500
    assert compute.provider_attempts_remaining == 1
    assert compute.affordable is True

def test_deadline_budget_adapter_preserves_existing_budget_signal() -> None:
    signal = _RoutingSignal(
        route="CLAIM_WEAKENING",
        reason="unsupported_claim",
        deadline_remaining_ms=3200,
        minimum_budget_ms=3000,
        provider_attempts_remaining=2,
    )

    normalized = LegacyM26DeadlineBudgetAdapter().normalize(signal)

    assert normalized.route == signal.route
    assert normalized.reason == signal.reason
    assert normalized.deadline_remaining_ms == 3200
    assert normalized.minimum_budget_ms == 3000
    assert normalized.provider_attempts_remaining == 2
    assert normalized.affordable is True
    assert normalized.compute_tier == STAGE1_UNAVAILABLE


def test_deadline_budget_adapter_marks_absent_signals_unavailable() -> None:
    normalized = LegacyM26DeadlineBudgetAdapter().normalize(
        {"route": "SAFE_ABSTENTION", "reason": "blocked"}
    )

    assert normalized.deadline_remaining_ms == STAGE1_UNAVAILABLE
    assert normalized.minimum_budget_ms == STAGE1_UNAVAILABLE
    assert normalized.provider_attempts_remaining == STAGE1_UNAVAILABLE
    assert normalized.affordable == STAGE1_UNAVAILABLE


def test_context_compiler_adapter_normalizes_existing_package_without_raw_context() -> None:
    package = {
        "status": "compiled",
        "context_manifest_sha256": "manifest-sha",
        "evidence_budget_sha256": "budget-sha",
        "safe_for_provider_mock": True,
        "context_manifest": {
            "token_budget": 4096,
            "measured_token_estimate": 2800,
            "selected_passage_ids": ["p1", "p2"],
            "derived_excerpts": [{"text": "raw evidence must not be copied"}],
        },
        "evidence_budget": {"token_budget": 4096},
        "citations": [{"citation_id": "C1"}, {"citation_id": "C2"}],
        "instruction_blocks": [{"text": "raw context must not be copied"}],
        "diagnostics": {
            "reason_codes": ["CONFLICT_PRESERVED"],
            "prompt_injection_quarantined": True,
        },
    }

    normalized = LegacyM26ContextCompilerAdapter().normalize(package)

    assert normalized.status == "compiled"
    assert normalized.context_manifest_sha256 == "manifest-sha"
    assert normalized.evidence_budget_sha256 == "budget-sha"
    assert normalized.token_budget == 4096
    assert normalized.measured_token_estimate == 2800
    assert normalized.selected_passage_ids == ("p1", "p2")
    assert normalized.citation_count == 2
    assert normalized.safe_for_provider is True
    assert normalized.prompt_injection_quarantined is True
    assert normalized.reason_codes == ("CONFLICT_PRESERVED",)
    assert not hasattr(normalized, "context_text")
    assert not hasattr(normalized, "instruction_blocks")


def test_context_compiler_adapter_preserves_explicit_abstain_none_hashes() -> None:
    package = {
        "status": "abstain_required",
        "context_manifest_sha256": None,
        "evidence_budget_sha256": None,
        "safe_for_provider_mock": False,
        "context_manifest": None,
        "evidence_budget": None,
        "citations": [],
        "diagnostics": {
            "reason_codes": ["CONTEXT_NOT_SAFE"],
            "prompt_injection_quarantined": False,
        },
    }

    normalized = LegacyM26ContextCompilerAdapter().normalize(package)

    assert normalized.context_manifest_sha256 is None
    assert normalized.evidence_budget_sha256 is None
    assert normalized.selected_passage_ids == STAGE1_UNAVAILABLE
    assert normalized.citation_count == 0
    assert normalized.safe_for_provider is False


def test_verifier_adapter_normalizes_final_decision_without_answer_or_evidence_text() -> None:
    response = {
        "status": "owner_only_verified_answer",
        "terminal_status": "verified_answer",
        "safe_abstention": False,
        "reason_codes": [],
        "provider_call_count": 2,
        "material_claim_support_verified": True,
        "citation_locator_valid": True,
        "unsupported_accepted_claims": 0,
        "repair_attempted": True,
        "answer_source": "provider_verified",
        "answer_text": "sensitive answer body",
        "citations": [
            {
                "citation_id": "C1",
                "exact_quote": "sensitive evidence body",
            }
        ],
    }

    normalized = LegacyM26VerifierAdapter().normalize(response)

    assert normalized.status == "owner_only_verified_answer"
    assert normalized.terminal_status == "verified_answer"
    assert normalized.safe_abstention is False
    assert normalized.provider_call_count == 2
    assert normalized.material_claim_support_verified is True
    assert normalized.citation_locator_valid is True
    assert normalized.unsupported_accepted_claims == 0
    assert normalized.repair_attempted is True
    assert normalized.citation_count == 1
    assert normalized.answer_source == "provider_verified"
    assert not hasattr(normalized, "answer_text")
    assert not hasattr(normalized, "citations")


def test_verifier_adapter_does_not_invent_missing_verification_signals() -> None:
    normalized = LegacyM26VerifierAdapter().normalize(
        {
            "status": "owner_only_safe_abstention",
            "terminal_status": "safe_abstention",
            "reason_codes": ["LOW_RETRIEVAL_SUPPORT"],
        }
    )

    assert normalized.safe_abstention == STAGE1_UNAVAILABLE
    assert normalized.provider_call_count == STAGE1_UNAVAILABLE
    assert normalized.material_claim_support_verified == STAGE1_UNAVAILABLE
    assert normalized.citation_locator_valid == STAGE1_UNAVAILABLE
    assert normalized.unsupported_accepted_claims == STAGE1_UNAVAILABLE
    assert normalized.repair_attempted == STAGE1_UNAVAILABLE
    assert normalized.citation_count == STAGE1_UNAVAILABLE
    assert normalized.answer_source == STAGE1_UNAVAILABLE
