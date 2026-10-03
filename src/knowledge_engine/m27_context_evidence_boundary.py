from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .m27_context_runtime_contracts import (
    STAGE3_UNAVAILABLE,
    ContextCompileResult,
    EvidencePlanningResult,
    Stage3Unavailable,
)
from .m27_evidence_planner import LegacyM26EvidencePlannerAdapter
from .m27_legacy_m26_adapters import LegacyM26ContextCompilerAdapter


@dataclass(frozen=True, slots=True)
class ContextEvidenceBoundaryResult:
    """Privacy-safe normalized views on both sides of the Stage 3 boundary."""

    evidence_planning: EvidencePlanningResult
    context_compilation: ContextCompileResult
    planner_identity_available: bool
    compiler_manifest_identity_available: bool
    compiler_selected_passage_count: int | Stage3Unavailable


class LegacyM26ContextEvidenceBoundary:
    """Expose EvidencePlanner and ContextCompiler as separate M26 responsibilities.

    Inputs must already have been produced by the existing M26 path. This object
    neither selects evidence nor compiles context.
    """

    def __init__(self) -> None:
        self._evidence_planner = LegacyM26EvidencePlannerAdapter()
        self._context_compiler = LegacyM26ContextCompilerAdapter()

    def normalize(
        self,
        *,
        selected_evidence: Sequence[Mapping[str, object]],
        compiled_output: Mapping[str, object],
        requirements: Sequence[object] = (),
        support_classification: Sequence[Mapping[str, object]] | None = None,
        endpoint_proof: Mapping[str, object] | None = None,
        sufficiency_status: str | None = None,
        reason_codes: Sequence[str] = (),
    ) -> ContextEvidenceBoundaryResult:
        evidence_planning = self._evidence_planner.normalize(
            selected_evidence=selected_evidence,
            requirements=requirements,
            support_classification=support_classification,
            endpoint_proof=endpoint_proof,
            sufficiency_status=sufficiency_status,
            reason_codes=reason_codes,
        )
        context_compilation = self._context_compiler.normalize(compiled_output)

        compiler_selected_passage_count: int | Stage3Unavailable
        if isinstance(context_compilation.selected_passage_ids, tuple):
            compiler_selected_passage_count = len(
                context_compilation.selected_passage_ids
            )
        else:
            compiler_selected_passage_count = STAGE3_UNAVAILABLE

        return ContextEvidenceBoundaryResult(
            evidence_planning=evidence_planning,
            context_compilation=context_compilation,
            planner_identity_available=(
                evidence_planning.selected_evidence_ids != STAGE3_UNAVAILABLE
            ),
            compiler_manifest_identity_available=isinstance(
                context_compilation.context_manifest_sha256,
                str,
            ),
            compiler_selected_passage_count=compiler_selected_passage_count,
        )
