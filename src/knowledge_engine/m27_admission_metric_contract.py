from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

VERIFIED_ANSWER_EXPECTATION = "verified_cited_answer"

SAFE_TERMINAL_EXPECTATIONS = frozenset(
    {
        "safe_abstention",
        "rejected_before_provider",
        "drift_rejection",
        "budget_terminal",
        "deadline_terminal",
        "safe_terminal",
    }
)

_SAFE_ABSTENTION_EXPECTATIONS = frozenset({"safe_abstention", "safe_terminal"})
_DRIFT_REJECTION_EXPECTATIONS = frozenset({"rejected_before_provider", "drift_rejection"})
_BUDGET_TERMINAL_EXPECTATIONS = frozenset({"budget_terminal", "deadline_terminal"})


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _citation_count(row: Mapping[str, Any]) -> int:
    value = row.get("citation_count", 0)
    if isinstance(value, bool):
        return int(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_terminal_answer_leaked(row: Mapping[str, Any]) -> bool | None:
    """Return explicit visible-answer leakage state for a safe-terminal row.

    Legacy answer_present is deliberately ignored. In M27 admission receipts it
    means a terminal result object exists, including intentional safe terminals.
    New admission runners must record a semantically precise leakage field.
    """

    for key in (
        "answer_leaked",
        "visible_answer_leaked",
        "user_visible_answer_present",
        "verified_answer_present",
    ):
        if key in row:
            value = row[key]
            return value if isinstance(value, bool) else None
    return None


def _expected_safe_terminal_shape(row: Mapping[str, Any]) -> bool:
    expectation = str(row.get("expectation", ""))
    status = str(row.get("status_code", ""))
    terminal = str(row.get("terminal_reason", ""))
    round_terminal = str(row.get("round_terminal_reason", ""))

    if expectation in _SAFE_ABSTENTION_EXPECTATIONS:
        return (
            status == "M27_RUNTIME_SAFE_TERMINAL"
            and "SAFE_TERMINAL" in (round_terminal or terminal)
        )
    if expectation in _DRIFT_REJECTION_EXPECTATIONS:
        return (
            status == "M27_RUNTIME_SAFE_TERMINAL"
            and "SAFE_TERMINAL" in (round_terminal or terminal)
            and int(row.get("provider_calls", 0) or 0) == 0
        )
    if expectation in _BUDGET_TERMINAL_EXPECTATIONS:
        return (
            status == "M27_RUNTIME_SAFE_TERMINAL"
            and terminal in {"BUDGET_NOT_AUTHORITATIVE", "DEADLINE_NOT_AUTHORITATIVE"}
            and int(row.get("provider_calls", 0) or 0) == 0
        )
    return False


def _safe_terminal_row_correct(row: Mapping[str, Any]) -> bool:
    leaked = _safe_terminal_answer_leaked(row)
    return (
        leaked is False
        and _citation_count(row) == 0
        and _expected_safe_terminal_shape(row)
        and row.get("production_touched") is False
    )


def summarize_admission_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    verified_rows = [
        row for row in rows if row.get("expectation") == VERIFIED_ANSWER_EXPECTATION
    ]
    safe_rows = [
        row for row in rows if str(row.get("expectation", "")) in SAFE_TERMINAL_EXPECTATIONS
    ]

    cited_verified = sum(_citation_count(row) > 0 for row in verified_rows)
    safe_correct = sum(_safe_terminal_row_correct(row) for row in safe_rows)

    safe_abstention_rows = [
        row for row in safe_rows if row.get("expectation") in _SAFE_ABSTENTION_EXPECTATIONS
    ]
    drift_rows = [
        row for row in safe_rows if row.get("expectation") in _DRIFT_REJECTION_EXPECTATIONS
    ]
    budget_rows = [
        row for row in safe_rows if row.get("expectation") in _BUDGET_TERMINAL_EXPECTATIONS
    ]

    def safe_subrate(group: Sequence[Mapping[str, Any]]) -> float:
        return _ratio(sum(_safe_terminal_row_correct(row) for row in group), len(group))

    unexpected_answer_count = sum(
        _safe_terminal_answer_leaked(row) is True for row in safe_rows
    )
    missing_leakage_signal_count = sum(
        _safe_terminal_answer_leaked(row) is None for row in safe_rows
    )

    cited_final_answer_rate = _ratio(cited_verified, len(verified_rows))
    safe_terminal_correctness = _ratio(safe_correct, len(safe_rows))

    feature_off_rows = [row for row in rows if row.get("expectation") == "m26_invariant"]
    feature_off_invariant = all(
        row.get("feature_off") is True and row.get("production_touched") is False
        for row in feature_off_rows
    )
    production_no_mutation = not any(row.get("production_touched") is True for row in rows)

    return {
        "verified_answer_expected_count": len(verified_rows),
        "verified_answer_cited_count": cited_verified,
        "cited_final_answer_rate": cited_final_answer_rate,
        "safe_terminal_expected_count": len(safe_rows),
        "safe_terminal_correct_count": safe_correct,
        "safe_terminal_correctness": safe_terminal_correctness,
        "safe_abstention_correctness": safe_subrate(safe_abstention_rows),
        "drift_rejection_correctness": safe_subrate(drift_rows),
        "budget_terminal_correctness": safe_subrate(budget_rows),
        "unexpected_answer_on_safe_terminal_count": unexpected_answer_count,
        "safe_terminal_missing_leakage_signal_count": missing_leakage_signal_count,
        "feature_off_invariant": feature_off_invariant,
        "production_no_mutation": production_no_mutation,
        "gate_pass": (
            cited_final_answer_rate >= 0.95
            and safe_terminal_correctness == 1.0
            and feature_off_invariant
            and production_no_mutation
        ),
    }
