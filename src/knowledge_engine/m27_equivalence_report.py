from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from .m27_replay_harness import (
    EquivalenceClassification,
    ReplayCaseResult,
)


@dataclass(frozen=True, slots=True)
class EquivalenceReport:
    case_count: int
    overall_classification_counts: tuple[tuple[str, int], ...]
    field_classification_counts: tuple[tuple[str, int], ...]
    unsafe_drift_fields: tuple[str, ...]
    normalization_drift_fields: tuple[str, ...]
    legacy_expectation_drift_fields: tuple[str, ...]
    expected_unavailable_stage1_fields: tuple[str, ...]
    missing_signal_fields: tuple[str, ...]
    available_signals_equivalent: bool

    @property
    def threatens_production_invariants(self) -> bool:
        return bool(self.unsafe_drift_fields)

    @property
    def ready_for_next_stage_review(self) -> bool:
        return (
            self.available_signals_equivalent
            and not self.threatens_production_invariants
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "overall_classification_counts": dict(
                self.overall_classification_counts
            ),
            "field_classification_counts": dict(self.field_classification_counts),
            "unsafe_drift_fields": list(self.unsafe_drift_fields),
            "normalization_drift_fields": list(self.normalization_drift_fields),
            "legacy_expectation_drift_fields": list(
                self.legacy_expectation_drift_fields
            ),
            "expected_unavailable_stage1_fields": list(
                self.expected_unavailable_stage1_fields
            ),
            "missing_signal_fields": list(self.missing_signal_fields),
            "available_signals_equivalent": self.available_signals_equivalent,
            "threatens_production_invariants": self.threatens_production_invariants,
            "ready_for_next_stage_review": self.ready_for_next_stage_review,
        }

    def render_markdown(self) -> str:
        """Render a privacy-safe summary without replay values or raw payloads."""

        lines = [
            "# M27 Replay / Equivalence Summary",
            "",
            f"- cases: {self.case_count}",
            f"- available signals equivalent: {str(self.available_signals_equivalent).lower()}",
            (
                "- threatens production invariants: "
                f"{str(self.threatens_production_invariants).lower()}"
            ),
            (
                "- ready for next-stage review: "
                f"{str(self.ready_for_next_stage_review).lower()}"
            ),
            "",
            "## Overall classifications",
        ]
        lines.extend(
            f"- {name}: {count}"
            for name, count in self.overall_classification_counts
        )
        lines.extend(["", "## Field classifications"])
        lines.extend(
            f"- {name}: {count}" for name, count in self.field_classification_counts
        )
        _append_named_fields(lines, "Unsafe drift", self.unsafe_drift_fields)
        _append_named_fields(
            lines,
            "Normalization drift",
            self.normalization_drift_fields,
        )
        _append_named_fields(
            lines,
            "Legacy expectation drift",
            self.legacy_expectation_drift_fields,
        )
        _append_named_fields(
            lines,
            "Expected unavailable in Stage 1",
            self.expected_unavailable_stage1_fields,
        )
        _append_named_fields(lines, "Missing signals", self.missing_signal_fields)
        return "\n".join(lines) + "\n"



def build_equivalence_report(
    results: Sequence[ReplayCaseResult],
) -> EquivalenceReport:
    overall_counts = Counter(
        result.overall_classification.value for result in results
    )
    field_counts: Counter[str] = Counter()
    unsafe: list[str] = []
    normalization: list[str] = []
    legacy_drift: list[str] = []
    unavailable: list[str] = []
    missing: list[str] = []

    for result in results:
        for comparison in result.comparisons:
            field_counts[comparison.classification.value] += 1
            qualified = f"{result.case_id}:{comparison.field}"
            if comparison.classification is EquivalenceClassification.UNSAFE_DRIFT:
                unsafe.append(qualified)
            elif (
                comparison.classification
                is EquivalenceClassification.NORMALIZATION_DRIFT
            ):
                normalization.append(qualified)
            elif (
                comparison.classification
                is EquivalenceClassification.LEGACY_EXPECTATION_DRIFT
            ):
                legacy_drift.append(qualified)
            elif (
                comparison.classification
                is EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
            ):
                unavailable.append(qualified)
            elif comparison.classification is EquivalenceClassification.MISSING_SIGNAL:
                missing.append(qualified)

    available_signals_equivalent = not unsafe and not normalization
    return EquivalenceReport(
        case_count=len(results),
        overall_classification_counts=tuple(sorted(overall_counts.items())),
        field_classification_counts=tuple(sorted(field_counts.items())),
        unsafe_drift_fields=tuple(unsafe),
        normalization_drift_fields=tuple(normalization),
        legacy_expectation_drift_fields=tuple(legacy_drift),
        expected_unavailable_stage1_fields=tuple(unavailable),
        missing_signal_fields=tuple(missing),
        available_signals_equivalent=available_signals_equivalent,
    )


def _append_named_fields(
    lines: list[str],
    heading: str,
    fields: tuple[str, ...],
) -> None:
    lines.extend(["", f"## {heading}"])
    if not fields:
        lines.append("- none")
        return
    lines.extend(f"- {field}" for field in fields)
