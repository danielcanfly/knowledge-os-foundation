from __future__ import annotations

from dataclasses import dataclass

import pytest

from knowledge_engine.m27_bounded_agentic_retrieval import (
    M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED,
    M27_ISOLATED_RUNTIME,
    MAX_GAP_QUERY_CHARS,
    MAX_RETRIEVAL_ROUNDS,
    BoundedRetrievalFlags,
    SecondRoundDecisionCode,
    build_gap_retrieval_query,
    load_bounded_retrieval_flags,
    material_gap_requirement_ids,
    merge_retrieval_round_mapping,
    plan_second_retrieval_round,
)


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    evidence_terms: tuple[str, ...]
    exact_phrase: str = ""


REQS = (
    Requirement("core_answer", ("agentic retrieval", "evidence gap")),
    Requirement("latency_boundary", ("deadline budget", "p95 latency")),
    Requirement("explanatory_answer", ("explain",)),
)


def _support(core: str, latency: str) -> list[dict[str, str]]:
    return [
        {"facet_id": "core_answer", "support_state": core},
        {"facet_id": "latency_boundary", "support_state": latency},
        {"facet_id": "explanatory_answer", "support_state": "UNSUPPORTED"},
    ]


def test_flags_default_off_and_require_isolated_runtime() -> None:
    flags = load_bounded_retrieval_flags(environ={})
    assert flags.requested is False
    assert flags.isolated_runtime is False
    assert flags.enabled is False

    requested_only = load_bounded_retrieval_flags(
        environ={M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED: "true"}
    )
    assert requested_only.requested is True
    assert requested_only.isolated_runtime is False
    assert requested_only.enabled is False

    enabled = load_bounded_retrieval_flags(
        environ={
            M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED: "true",
            M27_ISOLATED_RUNTIME: "true",
        }
    )
    assert enabled.enabled is True


def test_material_gap_uses_existing_support_and_excludes_structural_requirement() -> None:
    assert material_gap_requirement_ids(
        requirements=REQS,
        support_classification=_support("SUPPORTED", "UNKNOWN"),
    ) == ("latency_boundary",)

    assert material_gap_requirement_ids(
        requirements=REQS,
        support_classification=_support("SUPPORTED", "SUPPORTED"),
    ) == ()


@pytest.mark.parametrize(
    ("flags", "rounds", "deadline", "attempts", "expected"),
    [
        (
            BoundedRetrievalFlags(False, True),
            1,
            10_000,
            2,
            SecondRoundDecisionCode.DISABLED,
        ),
        (
            BoundedRetrievalFlags(True, False),
            1,
            10_000,
            2,
            SecondRoundDecisionCode.NOT_ISOLATED_RUNTIME,
        ),
        (
            BoundedRetrievalFlags(True, True),
            MAX_RETRIEVAL_ROUNDS,
            10_000,
            2,
            SecondRoundDecisionCode.MAX_ROUNDS_REACHED,
        ),
        (
            BoundedRetrievalFlags(True, True),
            1,
            10_000,
            0,
            SecondRoundDecisionCode.PROVIDER_BUDGET_BLOCKED,
        ),
        (
            BoundedRetrievalFlags(True, True),
            1,
            5_999,
            2,
            SecondRoundDecisionCode.DEADLINE_BUDGET_BLOCKED,
        ),
    ],
)
def test_plan_second_round_fail_closed_gates(
    flags: BoundedRetrievalFlags,
    rounds: int,
    deadline: int,
    attempts: int,
    expected: SecondRoundDecisionCode,
) -> None:
    plan = plan_second_retrieval_round(
        flags=flags,
        requirements=REQS,
        support_classification=_support("SUPPORTED", "UNKNOWN"),
        rounds_completed=rounds,
        deadline_remaining_ms=deadline,
        provider_attempts_remaining=attempts,
        post_retrieval_reserve_ms=4_500,
    )
    assert plan.should_run is False
    assert plan.decision_code is expected


def test_plan_runs_exactly_one_second_round_only_for_material_gap_and_budget() -> None:
    plan = plan_second_retrieval_round(
        flags=BoundedRetrievalFlags(True, True),
        requirements=REQS,
        support_classification=_support("SUPPORTED", "UNKNOWN"),
        rounds_completed=1,
        deadline_remaining_ms=8_000,
        provider_attempts_remaining=1,
        post_retrieval_reserve_ms=4_500,
    )
    assert plan.should_run is True
    assert plan.decision_code is SecondRoundDecisionCode.READY
    assert plan.missing_requirement_ids == ("latency_boundary",)
    assert plan.max_rounds == 2
    assert "query" not in plan.as_safe_dict()
    assert "answer" not in plan.as_safe_dict()


def test_no_gap_never_runs_second_round() -> None:
    plan = plan_second_retrieval_round(
        flags=BoundedRetrievalFlags(True, True),
        requirements=REQS,
        support_classification=_support("SUPPORTED", "SUPPORTED"),
        rounds_completed=1,
        deadline_remaining_ms=12_000,
        provider_attempts_remaining=3,
        post_retrieval_reserve_ms=4_500,
    )
    assert plan.should_run is False
    assert plan.decision_code is SecondRoundDecisionCode.NO_MATERIAL_GAP


def test_gap_query_is_deterministic_anchored_and_bounded() -> None:
    query = build_gap_retrieval_query(
        base_query="bounded agentic retrieval architecture",
        requirements=REQS,
        missing_requirement_ids=("latency_boundary",),
    )
    assert query == build_gap_retrieval_query(
        base_query="bounded agentic retrieval architecture",
        requirements=REQS,
        missing_requirement_ids=("latency_boundary",),
    )
    assert query.startswith("bounded agentic retrieval architecture")
    assert "deadline budget" in query
    assert "p95 latency" in query
    assert len(query) <= MAX_GAP_QUERY_CHARS


def test_gap_query_uses_evidence_terms_not_requirement_instruction() -> None:
    requirement = {
        "requirement_id": "material",
        "instruction": "PRIVATE FREE FORM INSTRUCTION MUST NOT BE COPIED",
        "evidence_terms": ("safe term", "second safe term"),
        "exact_phrase": "",
    }
    query = build_gap_retrieval_query(
        base_query="subject anchor",
        requirements=[requirement],
        missing_requirement_ids=["material"],
    )
    assert "safe term" in query
    assert "PRIVATE FREE FORM" not in query


def test_merge_retrieval_round_mapping_dedupes_by_domain_identity() -> None:
    primary = {
        "results": [
            {"section_id": "s1", "score": 1},
            {"section_id": "s2", "score": 2},
        ],
        "round": 1,
    }
    secondary = {
        "results": [
            {"section_id": "s2", "score": 99},
            {"section_id": "s3", "score": 3},
        ],
        "round": 2,
    }
    merged = merge_retrieval_round_mapping(
        primary,
        secondary,
        collection_field="results",
    )
    assert [item["section_id"] for item in merged["results"]] == ["s1", "s2", "s3"]
    assert merged["results"][1]["score"] == 2
    assert merged["round"] == 1


def test_merge_dense_candidates_preserves_primary_backend_identity() -> None:
    primary = {
        "candidates": [{"section_id": "s1"}],
        "backend_identity": {"provider": "primary"},
    }
    secondary = {
        "candidates": [{"section_id": "s2"}],
        "backend_identity": {"provider": "secondary"},
    }
    merged = merge_retrieval_round_mapping(
        primary,
        secondary,
        collection_field="candidates",
    )
    assert [item["section_id"] for item in merged["candidates"]] == ["s1", "s2"]
    assert merged["backend_identity"] == {"provider": "primary"}

def test_merge_preserves_opaque_items_without_stable_identity() -> None:
    primary = {"results": [{"score": 1, "kind": "opaque"}]}
    secondary = {"results": [{"score": 2, "kind": "opaque"}]}

    merged = merge_retrieval_round_mapping(
        primary,
        secondary,
        collection_field="results",
    )

    assert merged["results"] == [
        {"score": 1, "kind": "opaque"},
        {"score": 2, "kind": "opaque"},
    ]
