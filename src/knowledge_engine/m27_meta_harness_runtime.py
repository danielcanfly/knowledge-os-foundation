from __future__ import annotations

from dataclasses import replace

from .m27_meta_harness_contracts import (
    META_HARNESS_SCHEMA_VERSION,
    MetaHarnessCandidate,
    MetaHarnessCandidateKind,
    MetaHarnessCandidateStatus,
    MetaHarnessGateRequirement,
    MetaHarnessInput,
    MetaHarnessReport,
    MetaHarnessRiskClass,
    report_from_candidate,
)


class MetaHarnessRuntimeError(RuntimeError):
    """Base error for the Stage 12 candidate-only lab."""


class UnknownMetaHarnessCandidateError(MetaHarnessRuntimeError):
    """Raised when a candidate id is not present in the in-memory store."""


class MetaHarnessCandidateConflictError(MetaHarnessRuntimeError):
    """Raised when one deterministic id maps to different candidate content."""


class InvalidMetaHarnessTransitionError(MetaHarnessRuntimeError):
    """Raised when a terminal candidate is asked to transition."""


class MetaHarnessCandidateStore:
    """Pure in-memory candidate store with no execution or persistence authority."""

    def __init__(self) -> None:
        self._candidates: dict[str, MetaHarnessCandidate] = {}

    def register(self, candidate: MetaHarnessCandidate) -> MetaHarnessCandidate:
        if not isinstance(candidate, MetaHarnessCandidate):
            raise MetaHarnessRuntimeError("candidate store accepts MetaHarnessCandidate only")
        existing = self._candidates.get(candidate.candidate_id)
        if existing is not None:
            if existing != candidate:
                raise MetaHarnessCandidateConflictError(
                    "deterministic candidate id already exists with different content"
                )
            return existing
        self._candidates[candidate.candidate_id] = candidate
        return candidate

    def inspect(self, candidate_id: str) -> MetaHarnessCandidate:
        try:
            return self._candidates[candidate_id]
        except KeyError as exc:
            raise UnknownMetaHarnessCandidateError(
                f"unknown meta-harness candidate: {candidate_id}"
            ) from exc

    def list(
        self,
        *,
        status: MetaHarnessCandidateStatus | None = None,
        kind: MetaHarnessCandidateKind | None = None,
        active_only: bool = False,
    ) -> tuple[MetaHarnessCandidate, ...]:
        if status is not None and not isinstance(status, MetaHarnessCandidateStatus):
            raise MetaHarnessRuntimeError("status filter must be MetaHarnessCandidateStatus")
        if kind is not None and not isinstance(kind, MetaHarnessCandidateKind):
            raise MetaHarnessRuntimeError("kind filter must be MetaHarnessCandidateKind")
        if not isinstance(active_only, bool):
            raise MetaHarnessRuntimeError("active_only filter must be bool")
        values = self._candidates.values()
        if status is not None:
            values = (item for item in values if item.status is status)
        if kind is not None:
            values = (item for item in values if item.kind is kind)
        if active_only:
            values = (item for item in values if item.active)
        return tuple(sorted(values, key=lambda item: item.candidate_id))

    def _replace_status(
        self,
        candidate_id: str,
        *,
        status: MetaHarnessCandidateStatus,
    ) -> MetaHarnessCandidate:
        current = self.inspect(candidate_id)
        updated = replace(current, status=status)
        self._candidates[candidate_id] = updated
        return updated

    def __len__(self) -> int:
        return len(self._candidates)


class MetaHarnessRuntime:
    """Isolated candidate harness/patch/eval proposal lab.

    This runtime creates metadata-only candidates and review reports. It cannot
    apply code, execute tests, merge branches, promote releases, call providers,
    expose MCP, write workspace state, or mutate production.
    """

    def __init__(self, *, candidate_store: MetaHarnessCandidateStore | None = None) -> None:
        self._candidate_store = (
            candidate_store if candidate_store is not None else MetaHarnessCandidateStore()
        )

    def draft_harness_plan(
        self,
        *,
        input_metadata: MetaHarnessInput,
        candidate_summary: str,
        expected_improvement_class: str,
        risk_class: MetaHarnessRiskClass,
        candidate_files: tuple[str, ...],
        test_names: tuple[str, ...],
        gate_names: tuple[str, ...],
    ) -> MetaHarnessCandidate:
        return self._draft(
            kind=MetaHarnessCandidateKind.HARNESS_PLAN,
            input_metadata=input_metadata,
            candidate_summary=candidate_summary,
            expected_improvement_class=expected_improvement_class,
            risk_class=risk_class,
            candidate_files=candidate_files,
            test_names=test_names,
            gate_names=gate_names,
        )

    def draft_patch_intent(
        self,
        *,
        input_metadata: MetaHarnessInput,
        candidate_summary: str,
        expected_improvement_class: str,
        risk_class: MetaHarnessRiskClass,
        candidate_files: tuple[str, ...],
        test_names: tuple[str, ...],
        gate_names: tuple[str, ...],
    ) -> MetaHarnessCandidate:
        return self._draft(
            kind=MetaHarnessCandidateKind.PATCH_INTENT,
            input_metadata=input_metadata,
            candidate_summary=candidate_summary,
            expected_improvement_class=expected_improvement_class,
            risk_class=risk_class,
            candidate_files=candidate_files,
            test_names=test_names,
            gate_names=gate_names,
        )

    def draft_eval_plan(
        self,
        *,
        input_metadata: MetaHarnessInput,
        candidate_summary: str,
        expected_improvement_class: str,
        risk_class: MetaHarnessRiskClass,
        candidate_files: tuple[str, ...],
        test_names: tuple[str, ...],
        gate_names: tuple[str, ...],
    ) -> MetaHarnessCandidate:
        return self._draft(
            kind=MetaHarnessCandidateKind.EVAL_PLAN,
            input_metadata=input_metadata,
            candidate_summary=candidate_summary,
            expected_improvement_class=expected_improvement_class,
            risk_class=risk_class,
            candidate_files=candidate_files,
            test_names=test_names,
            gate_names=gate_names,
        )

    def record_candidate_report(
        self,
        *,
        kind: MetaHarnessCandidateKind,
        input_metadata: MetaHarnessInput,
        candidate_summary: str,
        expected_improvement_class: str,
        risk_class: MetaHarnessRiskClass,
        candidate_files: tuple[str, ...],
        test_names: tuple[str, ...],
        gate_names: tuple[str, ...],
    ) -> MetaHarnessCandidate:
        allowed = {
            MetaHarnessCandidateKind.TEST_PLAN,
            MetaHarnessCandidateKind.VALIDATION_REPORT,
            MetaHarnessCandidateKind.PROMOTION_PROPOSAL,
            MetaHarnessCandidateKind.ROLLBACK_PLAN,
            MetaHarnessCandidateKind.RISK_MATRIX,
        }
        if kind not in allowed:
            raise MetaHarnessRuntimeError(
                "record_candidate_report accepts report/test/review proposal kinds only"
            )
        return self._draft(
            kind=kind,
            input_metadata=input_metadata,
            candidate_summary=candidate_summary,
            expected_improvement_class=expected_improvement_class,
            risk_class=risk_class,
            candidate_files=candidate_files,
            test_names=test_names,
            gate_names=gate_names,
        )

    def list_candidates(
        self,
        *,
        status: MetaHarnessCandidateStatus | None = None,
        kind: MetaHarnessCandidateKind | None = None,
        active_only: bool = False,
    ) -> tuple[MetaHarnessCandidate, ...]:
        return self._candidate_store.list(
            status=status,
            kind=kind,
            active_only=active_only,
        )

    def inspect_candidate(self, candidate_id: str) -> MetaHarnessCandidate:
        return self._candidate_store.inspect(candidate_id)

    def mark_candidate_rejected(self, candidate_id: str) -> MetaHarnessCandidate:
        return self._transition(
            candidate_id,
            target=MetaHarnessCandidateStatus.REJECTED,
        )

    def mark_candidate_superseded(self, candidate_id: str) -> MetaHarnessCandidate:
        return self._transition(
            candidate_id,
            target=MetaHarnessCandidateStatus.SUPERSEDED,
        )

    def mark_candidate_ready_for_review(
        self,
        candidate_id: str,
    ) -> MetaHarnessCandidate:
        return self._transition(
            candidate_id,
            target=MetaHarnessCandidateStatus.READY_FOR_REVIEW,
        )

    def render_meta_harness_report(self, candidate_id: str) -> dict[str, object]:
        candidate = self.inspect_candidate(candidate_id)
        report: MetaHarnessReport = report_from_candidate(candidate)
        return {
            "schema_version": META_HARNESS_SCHEMA_VERSION,
            "report": report.as_dict(),
            "supporting_source_refs": list(candidate.input_metadata.source_refs),
            "supporting_artifact_ids": list(candidate.input_metadata.artifact_ids),
            "reason_codes": list(candidate.input_metadata.reason_codes),
            "candidate_files": list(candidate.candidate_files),
            "test_names": list(candidate.test_names),
            "gate_names": [item.gate_name for item in candidate.gate_requirements],
            "governance": {
                "candidate_only": True,
                "requires_human_review": True,
                "requires_offline_gate": True,
                "auto_apply": False,
                "auto_merge": False,
                "auto_promote": False,
                "production_write": False,
                "runtime_behavior_change": False,
                "execution_authority": False,
            },
        }

    def _draft(
        self,
        *,
        kind: MetaHarnessCandidateKind,
        input_metadata: MetaHarnessInput,
        candidate_summary: str,
        expected_improvement_class: str,
        risk_class: MetaHarnessRiskClass,
        candidate_files: tuple[str, ...],
        test_names: tuple[str, ...],
        gate_names: tuple[str, ...],
    ) -> MetaHarnessCandidate:
        if not isinstance(gate_names, tuple) or not gate_names:
            raise MetaHarnessRuntimeError(
                "candidate drafting requires at least one offline gate name"
            )
        gates = tuple(
            MetaHarnessGateRequirement(gate_name=name) for name in sorted(set(gate_names))
        )
        candidate = MetaHarnessCandidate.create(
            kind=kind,
            input_metadata=input_metadata,
            candidate_summary=candidate_summary,
            expected_improvement_class=expected_improvement_class,
            risk_class=risk_class,
            candidate_files=candidate_files,
            test_names=test_names,
            gate_requirements=gates,
        )
        return self._candidate_store.register(candidate)

    def _transition(
        self,
        candidate_id: str,
        *,
        target: MetaHarnessCandidateStatus,
    ) -> MetaHarnessCandidate:
        current = self.inspect_candidate(candidate_id)
        if current.status in {
            MetaHarnessCandidateStatus.REJECTED,
            MetaHarnessCandidateStatus.SUPERSEDED,
        }:
            raise InvalidMetaHarnessTransitionError(
                f"terminal candidate cannot transition from {current.status.value}"
            )

        if target is MetaHarnessCandidateStatus.READY_FOR_REVIEW:
            if current.status is MetaHarnessCandidateStatus.READY_FOR_REVIEW:
                return current
            if current.status is not MetaHarnessCandidateStatus.PROPOSED:
                raise InvalidMetaHarnessTransitionError("only PROPOSED can become READY_FOR_REVIEW")
        elif target not in {
            MetaHarnessCandidateStatus.REJECTED,
            MetaHarnessCandidateStatus.SUPERSEDED,
        }:
            raise InvalidMetaHarnessTransitionError(
                f"unsupported Stage 12 lifecycle target: {target.value}"
            )

        if current.status is target:
            return current
        return self._candidate_store._replace_status(
            candidate_id,
            status=target,
        )


__all__ = [
    "MetaHarnessRuntimeError",
    "UnknownMetaHarnessCandidateError",
    "MetaHarnessCandidateConflictError",
    "InvalidMetaHarnessTransitionError",
    "MetaHarnessCandidateStore",
    "MetaHarnessRuntime",
]
