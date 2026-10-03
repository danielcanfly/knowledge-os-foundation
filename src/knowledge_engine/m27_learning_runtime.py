from __future__ import annotations

from dataclasses import replace

from .m27_learning_contracts import (
    LEARNING_SCHEMA_VERSION,
    LearningEvidenceBinding,
    LearningProposal,
    LearningProposalKind,
    LearningProposalStatus,
    LearningRiskClass,
    LearningSignal,
)


class LearningRuntimeError(RuntimeError):
    """Base error for Stage 11 proposal-plane runtime failures."""


class UnknownLearningSignalError(LearningRuntimeError):
    """Raised when a proposal references an unobserved signal."""


class UnknownLearningProposalError(LearningRuntimeError):
    """Raised when a proposal id is not present in the in-memory store."""


class LearningProposalConflictError(LearningRuntimeError):
    """Raised if the same deterministic proposal id maps to different content."""


class InvalidLearningTransitionError(LearningRuntimeError):
    """Raised when a proposal lifecycle attempts to leave a terminal state."""


class LearningProposalStore:
    """Pure in-memory candidate proposal store.

    The store intentionally has no filesystem, workspace, MCP, skill, memory,
    provider, release, or production backend integration.
    """

    def __init__(self) -> None:
        self._proposals: dict[str, LearningProposal] = {}

    def register(self, proposal: LearningProposal) -> LearningProposal:
        if not isinstance(proposal, LearningProposal):
            raise LearningRuntimeError("proposal store accepts LearningProposal only")
        existing = self._proposals.get(proposal.proposal_id)
        if existing is not None:
            if existing != proposal:
                raise LearningProposalConflictError(
                    "deterministic proposal id already exists with different content"
                )
            return existing
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    def inspect(self, proposal_id: str) -> LearningProposal:
        try:
            return self._proposals[proposal_id]
        except KeyError as exc:
            raise UnknownLearningProposalError(
                f"unknown learning proposal: {proposal_id}"
            ) from exc

    def list(
        self,
        *,
        status: LearningProposalStatus | None = None,
        active_only: bool = False,
    ) -> tuple[LearningProposal, ...]:
        if status is not None and not isinstance(status, LearningProposalStatus):
            raise LearningRuntimeError("status filter must be LearningProposalStatus")
        if not isinstance(active_only, bool):
            raise LearningRuntimeError("active_only filter must be bool")
        proposals = self._proposals.values()
        if status is not None:
            proposals = (item for item in proposals if item.status is status)
        if active_only:
            proposals = (item for item in proposals if item.active)
        return tuple(sorted(proposals, key=lambda item: item.proposal_id))

    def _replace_status(
        self,
        proposal_id: str,
        *,
        status: LearningProposalStatus,
    ) -> LearningProposal:
        current = self.inspect(proposal_id)
        updated = replace(current, status=status)
        self._proposals[proposal_id] = updated
        return updated

    def __len__(self) -> int:
        return len(self._proposals)


class LearningRuntime:
    """Candidate-only autonomous learning proposal plane.

    Stage 11 observes already-sanitized LearningSignal values, derives
    deterministic candidate proposals, and manages review-oriented lifecycle
    state only. It has no execution or mutation authority outside its in-memory
    signal/proposal collections.
    """

    def __init__(self, *, proposal_store: LearningProposalStore | None = None) -> None:
        self._signals: dict[str, LearningSignal] = {}
        self._proposal_store = proposal_store or LearningProposalStore()

    def observe_signal(self, signal: LearningSignal) -> LearningSignal:
        if not isinstance(signal, LearningSignal):
            raise LearningRuntimeError(
                "observe_signal accepts already-sanitized LearningSignal only"
            )
        existing = self._signals.get(signal.signal_id)
        if existing is not None and existing != signal:
            raise LearningRuntimeError(
                "deterministic signal id already exists with different content"
            )
        self._signals[signal.signal_id] = signal
        return signal

    def propose_from_signals(
        self,
        *,
        signal_ids: tuple[str, ...],
        kind: LearningProposalKind,
        observed_issue_class: str,
        candidate_change_summary: str,
        expected_benefit_class: str,
        risk_class: LearningRiskClass,
        required_gate: str,
    ) -> LearningProposal:
        if not isinstance(signal_ids, tuple) or not signal_ids:
            raise LearningRuntimeError("proposal requires at least one observed signal")
        normalized_ids = tuple(sorted(set(signal_ids)))
        for signal_id in normalized_ids:
            if signal_id not in self._signals:
                raise UnknownLearningSignalError(
                    f"proposal references unobserved signal: {signal_id}"
                )
        evidence = LearningEvidenceBinding(signal_ids=normalized_ids)
        proposal = LearningProposal.create(
            kind=kind,
            observed_issue_class=observed_issue_class,
            evidence_binding=evidence,
            candidate_change_summary=candidate_change_summary,
            expected_benefit_class=expected_benefit_class,
            risk_class=risk_class,
            required_gate=required_gate,
        )
        return self._proposal_store.register(proposal)

    def list_proposals(
        self,
        *,
        status: LearningProposalStatus | None = None,
        active_only: bool = False,
    ) -> tuple[LearningProposal, ...]:
        return self._proposal_store.list(status=status, active_only=active_only)

    def inspect_proposal(self, proposal_id: str) -> LearningProposal:
        return self._proposal_store.inspect(proposal_id)

    def mark_proposal_rejected(self, proposal_id: str) -> LearningProposal:
        return self._transition(
            proposal_id,
            target=LearningProposalStatus.REJECTED,
        )

    def mark_proposal_superseded(self, proposal_id: str) -> LearningProposal:
        return self._transition(
            proposal_id,
            target=LearningProposalStatus.SUPERSEDED,
        )

    def mark_proposal_ready_for_review(self, proposal_id: str) -> LearningProposal:
        return self._transition(
            proposal_id,
            target=LearningProposalStatus.READY_FOR_REVIEW,
        )

    def render_proposal_report(self, proposal_id: str) -> dict[str, object]:
        """Render proposal metadata only; signal payloads are never embedded."""

        proposal = self.inspect_proposal(proposal_id)
        return {
            "schema_version": LEARNING_SCHEMA_VERSION,
            "proposal": proposal.as_dict(),
            "supporting_signal_ids": list(proposal.evidence_binding.signal_ids),
            "governance": {
                "proposal_only": True,
                "requires_human_review": True,
                "requires_offline_gate": True,
                "auto_apply": False,
                "production_write": False,
                "runtime_behavior_change": False,
            },
        }

    def _transition(
        self,
        proposal_id: str,
        *,
        target: LearningProposalStatus,
    ) -> LearningProposal:
        current = self.inspect_proposal(proposal_id)
        if current.status in {
            LearningProposalStatus.REJECTED,
            LearningProposalStatus.SUPERSEDED,
        }:
            raise InvalidLearningTransitionError(
                f"terminal proposal cannot transition from {current.status.value}"
            )

        if target is LearningProposalStatus.READY_FOR_REVIEW:
            if current.status is not LearningProposalStatus.PROPOSED:
                if current.status is LearningProposalStatus.READY_FOR_REVIEW:
                    return current
                raise InvalidLearningTransitionError(
                    "only PROPOSED can become READY_FOR_REVIEW"
                )
        elif target not in {
            LearningProposalStatus.REJECTED,
            LearningProposalStatus.SUPERSEDED,
        }:
            raise InvalidLearningTransitionError(
                f"unsupported Stage 11 lifecycle target: {target.value}"
            )

        if current.status is target:
            return current
        return self._proposal_store._replace_status(
            proposal_id,
            status=target,
        )


__all__ = [
    "LearningRuntimeError",
    "UnknownLearningSignalError",
    "UnknownLearningProposalError",
    "LearningProposalConflictError",
    "InvalidLearningTransitionError",
    "LearningProposalStore",
    "LearningRuntime",
]
