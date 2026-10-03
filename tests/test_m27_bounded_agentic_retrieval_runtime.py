from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from knowledge_engine import m27_bounded_agentic_retrieval_runtime as subject
from knowledge_engine.m27_bounded_agentic_retrieval import BoundedRetrievalFlags


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    evidence_terms: tuple[str, ...]
    exact_phrase: str = ""


REQUIREMENTS = (
    Requirement("core_answer", ("core", "answer")),
    Requirement("latency", ("latency", "deadline")),
)


def _bundle() -> SimpleNamespace:
    return SimpleNamespace(release_id="test-release")


def _evidence(evidence_id: str, support: tuple[str, ...]) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "section_id": evidence_id,
        "support": support,
    }


def _install_support_classifier(monkeypatch) -> None:
    def classify(*, requirements, evidence):
        supported = {
            facet
            for item in evidence
            for facet in item.get("support", ())
        }
        return [
            {
                "facet_id": requirement.requirement_id,
                "support_state": (
                    "SUPPORTED"
                    if requirement.requirement_id in supported
                    else "UNSUPPORTED"
                ),
            }
            for requirement in requirements
        ]

    monkeypatch.setattr(
        subject.semantic_runtime,
        "_facet_support_classification",
        classify,
    )


def test_disabled_flag_returns_round1_without_calling_retrieval(monkeypatch) -> None:
    def forbidden_support(**_kwargs):
        raise AssertionError("disabled Stage 6 must not classify evidence gaps")

    def forbidden(**_kwargs):
        raise AssertionError("second retrieval must not run")

    monkeypatch.setattr(
        subject.semantic_runtime,
        "_facet_support_classification",
        forbidden_support,
    )
    monkeypatch.setattr(subject.legacy, "_run_lexical_primary_retrieval", forbidden)
    first = _evidence("s1", ("core_answer",))
    result = subject.run_bounded_agentic_second_round(
        normalized_question="subject",
        retrieval_question="subject",
        intent_class="direct_grounded_knowledge",
        trace_id="trace",
        bundle=_bundle(),
        lexical_result={"results": [{"section_id": "s1"}]},
        dense_result={
            "candidates": [{"section_id": "s1"}],
            "backend_identity": {"provider": "test"},
        },
        evidence=[first],
        endpoint_proof={"round": 1},
        requirements=REQUIREMENTS,
        dense_channel=None,
        dense_fallback_channel=None,
        require_remote_dense=False,
        event_sink=None,
        deadline_remaining_ms=12_000,
        provider_attempts_remaining=2,
        post_retrieval_reserve_ms=4_500,
        flags=BoundedRetrievalFlags(False, True),
    )
    assert result.audit.rounds_executed == 1
    assert result.audit.second_round_executed is False
    assert result.evidence == (first,)


def test_second_round_runs_once_and_adopts_only_when_material_gap_improves(
    monkeypatch,
) -> None:
    _install_support_classifier(monkeypatch)
    calls: list[str] = []

    def retrieve(**kwargs):
        calls.append(kwargs["question"])
        return (
            {"results": [{"section_id": "s2"}]},
            {
                "candidates": [{"section_id": "s2"}],
                "backend_identity": {"provider": "test"},
            },
        )

    def select(**kwargs):
        assert [item["section_id"] for item in kwargs["lexical_result"]["results"]] == [
            "s1",
            "s2",
        ]
        assert kwargs["question"] == "subject"
        return [
            _evidence("s1", ("core_answer",)),
            _evidence("s2", ("latency",)),
        ]

    def strengthen(**kwargs):
        return list(kwargs["evidence"]), {"round": 2}

    monkeypatch.setattr(subject.legacy, "_run_lexical_primary_retrieval", retrieve)
    monkeypatch.setattr(subject.legacy, "_select_evidence", select)
    monkeypatch.setattr(subject.semantic_runtime, "_strengthen_evidence", strengthen)

    result = subject.run_bounded_agentic_second_round(
        normalized_question="subject",
        retrieval_question="subject",
        intent_class="direct_grounded_knowledge",
        trace_id="trace",
        bundle=_bundle(),
        lexical_result={"results": [{"section_id": "s1"}]},
        dense_result={
            "candidates": [{"section_id": "s1"}],
            "backend_identity": {"provider": "test"},
        },
        evidence=[_evidence("s1", ("core_answer",))],
        endpoint_proof={"round": 1},
        requirements=REQUIREMENTS,
        dense_channel=None,
        dense_fallback_channel=None,
        require_remote_dense=False,
        event_sink=None,
        deadline_remaining_ms=12_000,
        provider_attempts_remaining=2,
        post_retrieval_reserve_ms=4_500,
        flags=BoundedRetrievalFlags(True, True),
    )
    assert len(calls) == 1
    assert calls[0] != "subject"
    assert result.audit.rounds_executed == 2
    assert result.audit.second_round_executed is True
    assert result.audit.second_round_adopted is True
    assert result.audit.missing_before == ("latency",)
    assert result.audit.missing_after == ()
    assert [item["evidence_id"] for item in result.evidence] == ["s1", "s2"]
    assert result.endpoint_proof == {"round": 2}


def test_second_round_reverts_if_it_trades_one_gap_for_another(monkeypatch) -> None:
    _install_support_classifier(monkeypatch)

    monkeypatch.setattr(
        subject.legacy,
        "_run_lexical_primary_retrieval",
        lambda **_kwargs: (
            {"results": [{"section_id": "s2"}]},
            {
                "candidates": [{"section_id": "s2"}],
                "backend_identity": {"provider": "test"},
            },
        ),
    )
    monkeypatch.setattr(
        subject.legacy,
        "_select_evidence",
        lambda **_kwargs: [_evidence("s2", ("latency",))],
    )
    monkeypatch.setattr(
        subject.semantic_runtime,
        "_strengthen_evidence",
        lambda **kwargs: (list(kwargs["evidence"]), {"round": 2}),
    )

    first = _evidence("s1", ("core_answer",))
    result = subject.run_bounded_agentic_second_round(
        normalized_question="subject",
        retrieval_question="subject",
        intent_class="direct_grounded_knowledge",
        trace_id="trace",
        bundle=_bundle(),
        lexical_result={"results": [{"section_id": "s1"}]},
        dense_result={
            "candidates": [{"section_id": "s1"}],
            "backend_identity": {"provider": "test"},
        },
        evidence=[first],
        endpoint_proof={"round": 1},
        requirements=REQUIREMENTS,
        dense_channel=None,
        dense_fallback_channel=None,
        require_remote_dense=False,
        event_sink=None,
        deadline_remaining_ms=12_000,
        provider_attempts_remaining=2,
        post_retrieval_reserve_ms=4_500,
        flags=BoundedRetrievalFlags(True, True),
    )
    assert result.audit.second_round_adopted is False
    assert result.audit.missing_before == ("latency",)
    assert result.audit.missing_after == ("core_answer",)
    assert result.evidence == (first,)


def test_second_round_reverts_when_gap_does_not_improve(monkeypatch) -> None:
    _install_support_classifier(monkeypatch)
    calls = 0

    def retrieve(**_kwargs):
        nonlocal calls
        calls += 1
        return (
            {"results": [{"section_id": "s2"}]},
            {
                "candidates": [{"section_id": "s2"}],
                "backend_identity": {"provider": "test"},
            },
        )

    monkeypatch.setattr(subject.legacy, "_run_lexical_primary_retrieval", retrieve)
    monkeypatch.setattr(
        subject.legacy,
        "_select_evidence",
        lambda **_kwargs: [_evidence("s2", ())],
    )
    monkeypatch.setattr(
        subject.semantic_runtime,
        "_strengthen_evidence",
        lambda **kwargs: (list(kwargs["evidence"]), {"round": 2}),
    )

    first = _evidence("s1", ("core_answer",))
    result = subject.run_bounded_agentic_second_round(
        normalized_question="subject",
        retrieval_question="subject",
        intent_class="direct_grounded_knowledge",
        trace_id="trace",
        bundle=_bundle(),
        lexical_result={"results": [{"section_id": "s1"}]},
        dense_result={
            "candidates": [{"section_id": "s1"}],
            "backend_identity": {"provider": "test"},
        },
        evidence=[first],
        endpoint_proof={"round": 1},
        requirements=REQUIREMENTS,
        dense_channel=None,
        dense_fallback_channel=None,
        require_remote_dense=False,
        event_sink=None,
        deadline_remaining_ms=12_000,
        provider_attempts_remaining=2,
        post_retrieval_reserve_ms=4_500,
        flags=BoundedRetrievalFlags(True, True),
    )
    assert calls == 1
    assert result.audit.second_round_executed is True
    assert result.audit.second_round_adopted is False
    assert result.audit.decision_code == "NO_GAP_IMPROVEMENT"
    assert result.evidence == (first,)
    assert result.endpoint_proof == {"round": 1}


def test_budget_block_prevents_second_round_even_with_gap(monkeypatch) -> None:
    _install_support_classifier(monkeypatch)

    def forbidden(**_kwargs):
        raise AssertionError("budget-blocked second retrieval must not run")

    monkeypatch.setattr(subject.legacy, "_run_lexical_primary_retrieval", forbidden)
    result = subject.run_bounded_agentic_second_round(
        normalized_question="subject",
        retrieval_question="subject",
        intent_class="direct_grounded_knowledge",
        trace_id="trace",
        bundle=_bundle(),
        lexical_result={"results": []},
        dense_result={"candidates": [], "backend_identity": {"provider": "test"}},
        evidence=[],
        endpoint_proof={},
        requirements=REQUIREMENTS,
        dense_channel=None,
        dense_fallback_channel=None,
        require_remote_dense=False,
        event_sink=None,
        deadline_remaining_ms=5_999,
        provider_attempts_remaining=2,
        post_retrieval_reserve_ms=4_500,
        flags=BoundedRetrievalFlags(True, True),
    )
    assert result.audit.rounds_executed == 1
    assert result.audit.decision_code == "DEADLINE_BUDGET_BLOCKED"


def test_safe_audit_never_contains_query_or_evidence_body(monkeypatch) -> None:
    _install_support_classifier(monkeypatch)
    result = subject.run_bounded_agentic_second_round(
        normalized_question="private question",
        retrieval_question="private question",
        intent_class="direct_grounded_knowledge",
        trace_id="trace",
        bundle=_bundle(),
        lexical_result={"results": []},
        dense_result={"candidates": [], "backend_identity": {"provider": "test"}},
        evidence=[],
        endpoint_proof={},
        requirements=REQUIREMENTS,
        dense_channel=None,
        dense_fallback_channel=None,
        require_remote_dense=False,
        event_sink=None,
        deadline_remaining_ms=1,
        provider_attempts_remaining=1,
        post_retrieval_reserve_ms=4_500,
        flags=BoundedRetrievalFlags(True, True),
    )
    safe = result.audit.as_safe_dict()
    assert all("query" not in key and "question" not in key for key in safe)
    assert "private question" not in repr(safe)
    assert "evidence" not in repr(safe).casefold()
