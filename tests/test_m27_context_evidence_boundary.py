from __future__ import annotations

import json

from knowledge_engine.m27_context_evidence_boundary import (
    LegacyM26ContextEvidenceBoundary,
)
from knowledge_engine.m27_context_runtime_contracts import STAGE3_UNAVAILABLE
from knowledge_engine.m27_replay_harness import (
    EquivalenceClassification,
    capture_sanitized_replay_input,
    run_replay_equivalence,
)


def _evidence() -> list[dict[str, object]]:
    return [
        {
            "evidence_id": "ev-01",
            "passage_id": "p-01",
            "source_identity": "source-A",
            "locator_id": "loc-01",
            "evidence_type": "passage",
            "passage_text": "PRIVATE EVIDENCE ONE",
        },
        {
            "evidence_id": "ev-02",
            "passage_id": "p-02",
            "source_identity": "source-B",
            "locator_id": "loc-02",
            "evidence_type": "passage",
            "passage_text": "PRIVATE EVIDENCE TWO",
        },
    ]


def _compiled_package(
    *,
    selected_passage_ids: list[str] | None = None,
) -> dict[str, object]:
    selected = selected_passage_ids or ["p-01", "p-02"]
    return {
        "status": "compiled_with_warnings",
        "context_manifest_sha256": "manifest-sha-001",
        "evidence_budget_sha256": "budget-sha-001",
        "safe_for_provider_mock": True,
        "context_manifest": {
            "token_budget": 4096,
            "measured_token_estimate": 1220,
            "selected_passage_ids": selected,
            "derived_excerpts": [{"text": "PRIVATE COMPILED EXCERPT"}],
        },
        "evidence_budget": {
            "token_budget": 4096,
            "measured_token_estimate": 1220,
        },
        "citations": [
            {
                "citation_id": "C1",
                "passage_id": selected[0],
                "exact_quote": "PRIVATE QUOTE ONE",
            },
            {
                "citation_id": "C2",
                "passage_id": selected[-1],
                "exact_quote": "PRIVATE QUOTE TWO",
            },
        ],
        "instruction_blocks": [{"text": "PRIVATE PROVIDER CONTEXT"}],
        "diagnostics": {
            "reason_codes": ["CONFLICT_PRESERVED"],
            "prompt_injection_quarantined": True,
        },
    }


def _comparison(result, field: str):
    return next(item for item in result.comparisons if item.field == field)


def test_boundary_preserves_planner_and_compiler_identities_without_crossing_domains() -> None:
    package = _compiled_package()
    result = LegacyM26ContextEvidenceBoundary().normalize(
        selected_evidence=_evidence(),
        compiled_output=package,
        sufficiency_status="conflicting",
        reason_codes=["CONFLICTING_EVIDENCE"],
    )

    assert result.evidence_planning.selected_evidence_ids == ("ev-01", "ev-02")
    assert result.evidence_planning.selected_passage_ids == ("p-01", "p-02")
    assert result.evidence_planning.selected_evidence_count == 2

    compiled = result.context_compilation
    assert compiled.status == package["status"]
    assert compiled.context_manifest_sha256 == package["context_manifest_sha256"]
    assert compiled.evidence_budget_sha256 == package["evidence_budget_sha256"]
    assert compiled.selected_passage_ids == ("p-01", "p-02")
    assert compiled.citation_count == 2
    assert compiled.safe_for_provider is True
    assert compiled.prompt_injection_quarantined is True
    assert result.compiler_selected_passage_count == 2
    assert result.planner_identity_available is True
    assert result.compiler_manifest_identity_available is True


def test_boundary_allows_compiler_budget_subset_without_becoming_second_planner() -> None:
    package = _compiled_package(selected_passage_ids=["p-01"])
    package["citations"] = [{"citation_id": "C1", "passage_id": "p-01"}]

    result = LegacyM26ContextEvidenceBoundary().normalize(
        selected_evidence=_evidence(),
        compiled_output=package,
    )

    assert result.evidence_planning.selected_evidence_count == 2
    assert result.evidence_planning.selected_evidence_ids == ("ev-01", "ev-02")
    assert result.context_compilation.selected_passage_ids == ("p-01",)
    assert result.compiler_selected_passage_count == 1
    assert result.context_compilation.citation_count == 1


def test_boundary_keeps_unavailable_signals_explicit() -> None:
    result = LegacyM26ContextEvidenceBoundary().normalize(
        selected_evidence=[
            {
                "evidence_id": "ev-01",
                "source_identity": "source-A",
                "locator_id": "loc-01",
                "evidence_type": "passage",
            }
        ],
        compiled_output={
            "status": "abstain_required",
            "context_manifest_sha256": None,
            "evidence_budget_sha256": None,
            "context_manifest": None,
            "evidence_budget": None,
            "citations": [],
            "safe_for_provider_mock": False,
            "diagnostics": {
                "reason_codes": ["CONTEXT_NOT_SAFE"],
                "prompt_injection_quarantined": False,
            },
        },
    )

    assert result.evidence_planning.selected_passage_ids == STAGE3_UNAVAILABLE
    assert result.context_compilation.status == "abstain_required"
    assert result.context_compilation.context_manifest_sha256 is None
    assert result.context_compilation.evidence_budget_sha256 is None
    assert result.context_compilation.citation_count == 0
    assert result.context_compilation.safe_for_provider is False
    assert result.compiler_selected_passage_count == STAGE3_UNAVAILABLE
    assert result.compiler_manifest_identity_available is False


def test_boundary_normalization_does_not_copy_evidence_or_context_bodies() -> None:
    result = LegacyM26ContextEvidenceBoundary().normalize(
        selected_evidence=_evidence(),
        compiled_output=_compiled_package(),
    )
    serialized = json.dumps({"boundary": repr(result)}, sort_keys=True)

    for forbidden in (
        "PRIVATE EVIDENCE ONE",
        "PRIVATE EVIDENCE TWO",
        "PRIVATE COMPILED EXCERPT",
        "PRIVATE QUOTE ONE",
        "PRIVATE QUOTE TWO",
        "PRIVATE PROVIDER CONTEXT",
    ):
        assert forbidden not in serialized


def test_stage2_replay_lens_remains_equivalent_for_same_compiled_output() -> None:
    package = _compiled_package()
    boundary = LegacyM26ContextEvidenceBoundary().normalize(
        selected_evidence=_evidence(),
        compiled_output=package,
    )
    replay = capture_sanitized_replay_input(
        case_id="stage3-boundary-equivalence",
        compiled_output=package,
    )
    replay_result = run_replay_equivalence(replay)

    assert boundary.context_compilation.status == "compiled_with_warnings"
    assert _comparison(
        replay_result,
        "selected_evidence_count",
    ).classification is EquivalenceClassification.EQUIVALENT
    assert _comparison(
        replay_result,
        "selected_evidence_ids",
    ).classification is EquivalenceClassification.EQUIVALENT
    assert _comparison(
        replay_result,
        "context_compiler_status",
    ).classification is EquivalenceClassification.EQUIVALENT
    assert _comparison(
        replay_result,
        "context_compiler_citation_count",
    ).classification is EquivalenceClassification.EQUIVALENT
