from __future__ import annotations

from knowledge_engine.m27_admission_metric_contract import summarize_admission_metrics


def _verified(case_id: str, *, cited: bool = True) -> dict[str, object]:
    return {
        "case_id": case_id,
        "expectation": "verified_cited_answer",
        "citation_count": 1 if cited else 0,
        "answer_leaked": False,
        "status_code": "M27_RUNTIME_COMPOSED",
        "terminal_reason": "VERIFIED_CITED_ANSWER",
        "round_terminal_reason": "VERIFIED_CITED_ANSWER",
        "provider_calls": 1,
        "production_touched": False,
        "feature_off": False,
    }


def _safe(
    case_id: str,
    expectation: str,
    *,
    answer_leaked: bool = False,
    citation_count: int = 0,
) -> dict[str, object]:
    terminal_reason = "VERIFIER_GAP_SAFE_TERMINAL"
    round_terminal_reason: str | None = "VERIFIER_GAP_SAFE_TERMINAL"
    provider_calls = 0
    if expectation == "budget_terminal":
        terminal_reason = "BUDGET_NOT_AUTHORITATIVE"
        round_terminal_reason = None
    return {
        "case_id": case_id,
        "expectation": expectation,
        "citation_count": citation_count,
        "answer_leaked": answer_leaked,
        "answer_present": True,
        "status_code": "M27_RUNTIME_SAFE_TERMINAL",
        "terminal_reason": terminal_reason,
        "round_terminal_reason": round_terminal_reason,
        "provider_calls": provider_calls,
        "production_touched": False,
        "feature_off": False,
    }


def _five_safe() -> list[dict[str, object]]:
    return [
        _safe("S1", "safe_abstention"),
        _safe("S2", "safe_abstention"),
        _safe("S3", "rejected_before_provider"),
        _safe("S4", "rejected_before_provider"),
        _safe("S5", "budget_terminal"),
    ]


def _feature_off() -> dict[str, object]:
    return {
        "case_id": "F1",
        "expectation": "m26_invariant",
        "citation_count": 0,
        "answer_present": False,
        "status_code": "M26_BASELINE_UNCHANGED",
        "production_touched": False,
        "feature_off": True,
    }


def test_nine_cited_verified_plus_five_safe_terminals_is_one_not_nine_fourteenths() -> None:
    rows = [_verified(f"V{i}") for i in range(9)] + _five_safe() + [_feature_off()]
    metrics = summarize_admission_metrics(rows)

    assert metrics["verified_answer_expected_count"] == 9
    assert metrics["verified_answer_cited_count"] == 9
    assert metrics["cited_final_answer_rate"] == 1.0
    assert metrics["safe_terminal_expected_count"] == 5
    assert metrics["safe_terminal_correctness"] == 1.0
    assert metrics["gate_pass"] is True


def test_uncited_verified_answer_stays_in_denominator_and_fails_95_percent_gate() -> None:
    rows = [_verified(f"V{i}") for i in range(8)]
    rows += [_verified("V9", cited=False)] + _five_safe() + [_feature_off()]
    metrics = summarize_admission_metrics(rows)

    assert metrics["cited_final_answer_rate"] == 8 / 9
    assert metrics["safe_terminal_correctness"] == 1.0
    assert metrics["gate_pass"] is False


def test_safe_terminal_zero_citations_and_no_visible_answer_leak_passes() -> None:
    metrics = summarize_admission_metrics(_five_safe())

    assert metrics["safe_terminal_correctness"] == 1.0
    assert metrics["safe_abstention_correctness"] == 1.0
    assert metrics["drift_rejection_correctness"] == 1.0
    assert metrics["budget_terminal_correctness"] == 1.0
    assert metrics["unexpected_answer_on_safe_terminal_count"] == 0


def test_safe_terminal_visible_answer_or_citation_leak_fails() -> None:
    rows = [
        _safe("S1", "safe_abstention", answer_leaked=True),
        _safe("S2", "rejected_before_provider", citation_count=1),
    ]
    metrics = summarize_admission_metrics(rows)

    assert metrics["safe_terminal_correctness"] == 0.0
    assert metrics["unexpected_answer_on_safe_terminal_count"] == 1
    assert metrics["gate_pass"] is False


def test_safe_terminal_missing_explicit_leakage_signal_fails_closed() -> None:
    row = _safe("S1", "safe_abstention")
    row.pop("answer_leaked")
    metrics = summarize_admission_metrics([row])

    assert metrics["safe_terminal_correctness"] == 0.0
    assert metrics["safe_terminal_missing_leakage_signal_count"] == 1
    assert metrics["gate_pass"] is False


def test_overall_gate_requires_both_citation_coverage_and_safe_terminal_correctness() -> None:
    good_answer = [_verified("V1")]
    good_safe = [_safe("S1", "safe_abstention")]

    assert summarize_admission_metrics(good_answer + good_safe)["gate_pass"] is True
    assert (
        summarize_admission_metrics([_verified("V1", cited=False)] + good_safe)["gate_pass"]
        is False
    )
    assert (
        summarize_admission_metrics(
            good_answer + [_safe("S1", "safe_abstention", answer_leaked=True)]
        )["gate_pass"]
        is False
    )


def test_feature_off_and_production_no_mutation_invariants_remain_gate_inputs() -> None:
    rows = [_verified("V1"), _safe("S1", "safe_abstention"), _feature_off()]
    metrics = summarize_admission_metrics(rows)
    assert metrics["feature_off_invariant"] is True
    assert metrics["production_no_mutation"] is True
    assert metrics["gate_pass"] is True

    touched = dict(rows[0], production_touched=True)
    touched_metrics = summarize_admission_metrics([touched, rows[1], rows[2]])
    assert touched_metrics["production_no_mutation"] is False
    assert touched_metrics["gate_pass"] is False

    feature_broken = dict(_feature_off(), feature_off=False)
    feature_metrics = summarize_admission_metrics([rows[0], rows[1], feature_broken])
    assert feature_metrics["feature_off_invariant"] is False
    assert feature_metrics["gate_pass"] is False
