from __future__ import annotations

import json
from dataclasses import dataclass

from knowledge_engine import m26_pa7_arbitrary_query_runtime as legacy
from knowledge_engine.m27_context_runtime_contracts import (
    STAGE3_UNAVAILABLE,
    EvidencePlanner,
)
from knowledge_engine.m27_evidence_planner import LegacyM26EvidencePlannerAdapter


@dataclass(frozen=True)
class _Requirement:
    requirement_id: str


def _selected_evidence() -> list[dict[str, object]]:
    return [
        {
            "evidence_id": "m26pa7ev_001",
            "passage_id": "passage_001",
            "source_identity": "source-A",
            "source_id": "source-A",
            "locator_id": "m26pa7loc_001",
            "evidence_type": "passage",
            "passage_text": "PRIVATE EVIDENCE BODY A",
            "provider_prompt": "PRIVATE PROVIDER PROMPT",
        },
        {
            "evidence_id": "m26pa7ev_002",
            "passage_id": "passage_002",
            "source_identity": "source-B",
            "source_id": "source-B",
            "locator_id": "m26pa7loc_002",
            "evidence_type": "passage",
            "passage_text": "PRIVATE EVIDENCE BODY B",
            "raw_answer": "PRIVATE ANSWER",
        },
    ]


def test_evidence_planner_preserves_existing_deterministic_identities() -> None:
    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=_selected_evidence(),
    )

    assert result.selected_evidence_count == 2
    assert result.selected_evidence_ids == ("m26pa7ev_001", "m26pa7ev_002")
    assert result.selected_passage_ids == ("passage_001", "passage_002")
    assert result.source_identities == ("source-A", "source-B")
    assert result.distinct_source_count == 2
    assert result.locator_ids == ("m26pa7loc_001", "m26pa7loc_002")
    assert tuple(item.evidence_type for item in result.selected_evidence) == (
        "passage",
        "passage",
    )


def test_evidence_planner_normalizes_only_existing_gap_and_sufficiency_signals() -> None:
    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=_selected_evidence(),
        requirements=[_Requirement("req-a"), _Requirement("req-b")],
        support_classification=[
            {
                "facet_id": "req-a",
                "support_state": "SUPPORTED",
                "supporting_evidence_ids": ["m26pa7ev_001"],
                "best_support_score": 2.0,
            },
            {
                "facet_id": "req-b",
                "support_state": "UNSUPPORTED",
                "supporting_evidence_ids": [],
                "best_support_score": 0.0,
            },
        ],
        endpoint_proof={
            "recovered_facets": ["req-b"],
            "bounded_authorized_corpus_recovery": True,
            "recovery_actions": [
                {
                    "requirement_id": "req-b",
                    "section_id": "PRIVATE-SECTION-NOT-FOR-BOUNDARY",
                }
            ],
        },
        sufficiency_status="partially_sufficient",
        reason_codes=[
            "SEMANTIC_SUPPORT_MISSING:req-b",
            "unsafe free form private reason",
        ],
    )

    assert result.requirement_ids == ("req-a", "req-b")
    assert result.gap.covered_requirement_ids == ("req-a",)
    assert result.gap.missing_requirement_ids == ("req-b",)
    assert result.gap.coverage_status == "gap_present"
    assert result.gap.sufficiency_status == "partially_sufficient"
    assert result.gap.recovered_requirement_ids == ("req-b",)
    assert result.gap.bounded_recovery_used is True
    assert result.gap.reason_codes == ("SEMANTIC_SUPPORT_MISSING:req-b",)


def test_evidence_planner_does_not_invent_missing_support_or_sufficiency_policy() -> None:
    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=_selected_evidence(),
        requirements=[_Requirement("req-a")],
    )

    assert result.gap.covered_requirement_ids == STAGE3_UNAVAILABLE
    assert result.gap.missing_requirement_ids == STAGE3_UNAVAILABLE
    assert result.gap.coverage_status == STAGE3_UNAVAILABLE
    assert result.gap.sufficiency_status == STAGE3_UNAVAILABLE
    assert result.gap.recovered_requirement_ids == STAGE3_UNAVAILABLE
    assert result.gap.bounded_recovery_used == STAGE3_UNAVAILABLE


def test_evidence_planner_marks_unavailable_identity_instead_of_fabricating_it() -> None:
    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=[
            {
                "passage_text": "body without an identity",
                "section_id": "section-only-is-not-enough-without-artifact",
            }
        ],
    )

    assert result.selected_evidence_count == 1
    assert result.selected_evidence_ids == STAGE3_UNAVAILABLE
    assert result.selected_passage_ids == STAGE3_UNAVAILABLE
    assert result.source_identities == STAGE3_UNAVAILABLE
    assert result.distinct_source_count == STAGE3_UNAVAILABLE
    assert result.locator_ids == STAGE3_UNAVAILABLE


def test_evidence_planner_reuses_m26_source_identity_fallback_exactly() -> None:
    evidence = {
        "evidence_id": "ev-1",
        "artifact_key": "artifact-A",
        "section_id": "section-1",
        "locator_id": "loc-1",
        "evidence_type": "passage",
    }
    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=[evidence],
    )

    assert result.source_identities == (legacy._source_identity(evidence),)
    assert result.source_identities == ("artifact-A#section-1",)


def test_evidence_planner_is_adapter_only_and_does_not_rerun_selection(
    monkeypatch,
) -> None:
    def _forbidden(*args, **kwargs):
        raise AssertionError("Stage 3 must not rerun M26 evidence selection")

    monkeypatch.setattr(legacy, "_select_evidence", _forbidden)
    monkeypatch.setattr(legacy, "_dynamic_evidence_budget", _forbidden)

    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=_selected_evidence(),
    )

    assert result.selected_evidence_count == 2


def test_evidence_planner_boundary_is_privacy_safe() -> None:
    result = LegacyM26EvidencePlannerAdapter().normalize(
        selected_evidence=_selected_evidence(),
        reason_codes=["SAFE_CODE"],
    )
    serialized = json.dumps(
        {
            "result": repr(result),
            "identities": [repr(item) for item in result.selected_evidence],
        },
        sort_keys=True,
    )

    assert "PRIVATE EVIDENCE BODY A" not in serialized
    assert "PRIVATE EVIDENCE BODY B" not in serialized
    assert "PRIVATE PROVIDER PROMPT" not in serialized
    assert "PRIVATE ANSWER" not in serialized
    assert "passage_text" not in serialized
    assert "provider_prompt" not in serialized
    assert "raw_answer" not in serialized


def test_evidence_planner_satisfies_stage3_protocol() -> None:
    assert isinstance(LegacyM26EvidencePlannerAdapter(), EvidencePlanner)
