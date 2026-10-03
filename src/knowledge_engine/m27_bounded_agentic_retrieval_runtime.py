from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import m26_pa7_arbitrary_query_runtime as legacy
from . import m26_pa7_semantic_closure_runtime as semantic_runtime
from .m26_production_answer_bundle import ProductionAnswerBundle
from .m27_bounded_agentic_retrieval import (
    BoundedRetrievalFlags,
    SecondRoundPlan,
    build_gap_retrieval_query,
    load_bounded_retrieval_flags,
    material_gap_requirement_ids,
    merge_retrieval_round_mapping,
    plan_second_retrieval_round,
)

DenseChannel = legacy.DenseChannel
RuntimeEventSink = legacy.RuntimeEventSink


@dataclass(frozen=True, slots=True)
class BoundedRetrievalAudit:
    rounds_executed: int
    second_round_executed: bool
    second_round_adopted: bool
    decision_code: str
    missing_before: tuple[str, ...]
    missing_after: tuple[str, ...]

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "rounds_executed": self.rounds_executed,
            "second_round_executed": self.second_round_executed,
            "second_round_adopted": self.second_round_adopted,
            "decision_code": self.decision_code,
            "missing_before": self.missing_before,
            "missing_after": self.missing_after,
        }


@dataclass(frozen=True, slots=True)
class BoundedRetrievalRuntimeResult:
    lexical_result: Mapping[str, Any]
    dense_result: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    endpoint_proof: Mapping[str, Any]
    audit: BoundedRetrievalAudit


def run_bounded_agentic_second_round(
    *,
    normalized_question: str,
    retrieval_question: str,
    intent_class: str,
    trace_id: str,
    bundle: ProductionAnswerBundle,
    lexical_result: Mapping[str, Any],
    dense_result: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    endpoint_proof: Mapping[str, Any],
    requirements: Sequence[object],
    dense_channel: DenseChannel | None,
    dense_fallback_channel: DenseChannel | None,
    require_remote_dense: bool,
    event_sink: RuntimeEventSink | None,
    deadline_remaining_ms: int,
    provider_attempts_remaining: int,
    post_retrieval_reserve_ms: int,
    flags: BoundedRetrievalFlags | None = None,
) -> BoundedRetrievalRuntimeResult:
    """Run at most one additional retrieval round and adopt only gap improvement.

    All retrieval/evidence bodies remain runtime-internal. The returned audit is
    deliberately body-free and query-free.
    """

    resolved_flags = flags or load_bounded_retrieval_flags()
    if not resolved_flags.enabled:
        return BoundedRetrievalRuntimeResult(
            lexical_result=lexical_result,
            dense_result=dense_result,
            evidence=tuple(dict(item) for item in evidence),
            endpoint_proof=dict(endpoint_proof),
            audit=BoundedRetrievalAudit(
                rounds_executed=1,
                second_round_executed=False,
                second_round_adopted=False,
                decision_code=(
                    "DISABLED"
                    if not resolved_flags.requested
                    else "NOT_ISOLATED_RUNTIME"
                ),
                missing_before=(),
                missing_after=(),
            ),
        )

    support_before = semantic_runtime._facet_support_classification(
        requirements=requirements,
        evidence=evidence,
    )
    missing_before = material_gap_requirement_ids(
        requirements=requirements,
        support_classification=support_before,
    )
    plan = plan_second_retrieval_round(
        flags=resolved_flags,
        requirements=requirements,
        support_classification=support_before,
        rounds_completed=1,
        deadline_remaining_ms=deadline_remaining_ms,
        provider_attempts_remaining=provider_attempts_remaining,
        post_retrieval_reserve_ms=post_retrieval_reserve_ms,
    )
    if not plan.should_run:
        return _unchanged_result(
            lexical_result=lexical_result,
            dense_result=dense_result,
            evidence=evidence,
            endpoint_proof=endpoint_proof,
            plan=plan,
            missing_before=missing_before,
        )

    second_query = build_gap_retrieval_query(
        base_query=retrieval_question,
        requirements=requirements,
        missing_requirement_ids=plan.missing_requirement_ids,
    )
    if not second_query or second_query == retrieval_question:
        return _unchanged_result(
            lexical_result=lexical_result,
            dense_result=dense_result,
            evidence=evidence,
            endpoint_proof=endpoint_proof,
            plan=plan,
            missing_before=missing_before,
            decision_code="NO_QUERY_EXPANSION",
        )

    second_lexical, second_dense = legacy._run_lexical_primary_retrieval(
        question=second_query,
        bundle=bundle,
        dense_channel=dense_channel,
        dense_fallback_channel=dense_fallback_channel,
        require_remote_dense=require_remote_dense,
        top_k=8,
        event_sink=event_sink,
    )
    merged_lexical = merge_retrieval_round_mapping(
        lexical_result,
        second_lexical,
        collection_field="results",
    )
    merged_dense = merge_retrieval_round_mapping(
        dense_result,
        second_dense,
        collection_field="candidates",
    )

    reselected = legacy._select_evidence(
        bundle=bundle,
        lexical_result=merged_lexical,
        dense_result=merged_dense,
        trace_id=trace_id,
        question=normalized_question,
        intent_class=intent_class,
    )
    strengthened, strengthened_endpoint_proof = semantic_runtime._strengthen_evidence(
        bundle=bundle,
        evidence=reselected,
        lexical_result=merged_lexical,
        trace_id=trace_id,
        question=normalized_question,
        intent_class=intent_class,
        requirements=requirements,
    )
    support_after = semantic_runtime._facet_support_classification(
        requirements=requirements,
        evidence=strengthened,
    )
    missing_after = material_gap_requirement_ids(
        requirements=requirements,
        support_classification=support_after,
    )

    if len(missing_after) >= len(missing_before):
        return BoundedRetrievalRuntimeResult(
            lexical_result=lexical_result,
            dense_result=dense_result,
            evidence=tuple(dict(item) for item in evidence),
            endpoint_proof=dict(endpoint_proof),
            audit=BoundedRetrievalAudit(
                rounds_executed=2,
                second_round_executed=True,
                second_round_adopted=False,
                decision_code="NO_GAP_IMPROVEMENT",
                missing_before=missing_before,
                missing_after=missing_after,
            ),
        )

    return BoundedRetrievalRuntimeResult(
        lexical_result=merged_lexical,
        dense_result=merged_dense,
        evidence=tuple(dict(item) for item in strengthened),
        endpoint_proof=dict(strengthened_endpoint_proof),
        audit=BoundedRetrievalAudit(
            rounds_executed=2,
            second_round_executed=True,
            second_round_adopted=True,
            decision_code="GAP_IMPROVED",
            missing_before=missing_before,
            missing_after=missing_after,
        ),
    )


def _unchanged_result(
    *,
    lexical_result: Mapping[str, Any],
    dense_result: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    endpoint_proof: Mapping[str, Any],
    plan: SecondRoundPlan,
    missing_before: tuple[str, ...],
    decision_code: str | None = None,
) -> BoundedRetrievalRuntimeResult:
    return BoundedRetrievalRuntimeResult(
        lexical_result=lexical_result,
        dense_result=dense_result,
        evidence=tuple(dict(item) for item in evidence),
        endpoint_proof=dict(endpoint_proof),
        audit=BoundedRetrievalAudit(
            rounds_executed=1,
            second_round_executed=False,
            second_round_adopted=False,
            decision_code=decision_code or plan.decision_code.value,
            missing_before=missing_before,
            missing_after=missing_before,
        ),
    )


__all__ = [
    "BoundedRetrievalAudit",
    "BoundedRetrievalRuntimeResult",
    "run_bounded_agentic_second_round",
]
