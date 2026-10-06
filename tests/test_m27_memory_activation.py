from __future__ import annotations

import hashlib

import pytest

from knowledge_engine.m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from knowledge_engine.m27_memory_activation import (
    GovernedMemoryReadPolicy,
    MemoryActivationError,
    MemoryReadTraceReason,
    answer_with_auxiliary_memory,
    assert_memory_cannot_satisfy_evidence,
    decide_memory_read,
    memory_authority_boundary,
    read_auxiliary_memory_context,
)
from knowledge_engine.m27_memory_contracts import (
    MemoryActivation,
    MemoryClass,
    MemoryOriginKind,
    MemoryProvenance,
    MemoryReviewDecision,
    UnsafeMemoryPayloadError,
)
from knowledge_engine.m27_memory_runtime import GovernedMemoryRuntime


def _activation() -> MemoryActivation:
    return MemoryActivation(enabled=True, isolated_runtime=True)


def _runtime(tmp_path) -> GovernedMemoryRuntime:
    return GovernedMemoryRuntime(root=tmp_path / "memory", activation=_activation())


def _provenance(ref: str = "task:memory:activation") -> MemoryProvenance:
    return MemoryProvenance(
        origin_kind=MemoryOriginKind.TASK_SUMMARY,
        origin_ref=ref,
        source_sha256=hashlib.sha256(ref.encode()).hexdigest(),
    )


def _task(
    task_id: str = "task:memory:alpha",
    *,
    kind: RuntimeTaskKind = RuntimeTaskKind.KNOWLEDGE,
    allow_memory_read: bool = True,
) -> M27RuntimeTask:
    return M27RuntimeTask(
        task_id=task_id,
        kind=kind,
        request_token=f"request:{task_id.split(':')[-1]}",
        allow_memory_read=allow_memory_read,
    )


def _retain(
    runtime: GovernedMemoryRuntime,
    *,
    scope_token: str = "task:memory:alpha",
    memory_class: MemoryClass = MemoryClass.PROJECT,
    summary: str = "Reviewed project memory may guide retrieval framing only.",
):
    candidate = runtime.propose_candidate(
        memory_class=memory_class,
        scope_token=scope_token,
        summary=summary,
        provenance=_provenance(scope_token),
        tags=("activation", "memory"),
    )
    runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.RETAIN_CANDIDATE,
        reviewer_token="reviewer:m27",
        reason_codes=("SANITIZED_CONTENT",),
    )
    return candidate


def test_memory_read_policy_requires_explicit_task_allowance_and_isolation(tmp_path) -> None:
    runtime = _runtime(tmp_path)

    denied = decide_memory_read(task=_task(allow_memory_read=False), memory_runtime=runtime)
    assert denied.allowed is False
    assert denied.trace_reason is MemoryReadTraceReason.TASK_POLICY_DENIED
    assert denied.reason_codes == ("TASK_DID_NOT_ALLOW_MEMORY_READ",)

    allowed = decide_memory_read(task=_task(), memory_runtime=runtime)
    assert allowed.allowed is True
    assert allowed.scope_token == "task:memory:alpha"
    assert allowed.allowed_memory_classes == (MemoryClass.PROJECT, MemoryClass.EPISODIC)
    assert allowed.trace_reason is MemoryReadTraceReason.EXPLICIT_TASK_MEMORY_READ
    assert "NO_CITATION_AUTHORITY" in allowed.reason_codes


def test_memory_read_policy_denies_non_eligible_task_kinds_even_when_flagged(tmp_path) -> None:
    runtime = _runtime(tmp_path)

    for kind in (RuntimeTaskKind.NO_CONTEXT, RuntimeTaskKind.TOOL):
        denied = decide_memory_read(
            task=_task(kind=kind, allow_memory_read=True),
            memory_runtime=runtime,
        )
        assert denied.allowed is False
        assert denied.reason_codes == ("TASK_KIND_NOT_MEMORY_ELIGIBLE",)


def test_memory_context_reads_reviewed_task_scope_only_without_evidence_authority(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    retained = _retain(runtime)
    _retain(
        runtime,
        scope_token="task:memory:beta",
        summary="Other task memory must remain outside the alpha scope.",
    )

    result = read_auxiliary_memory_context(task=_task(), memory_runtime=runtime)

    assert result.decision.allowed is True
    assert result.retained_count == 1
    assert result.auxiliary_context[0].memory_id == retained.memory_id.value
    assert result.auxiliary_context[0].scope_token == "task:memory:alpha"
    assert_memory_cannot_satisfy_evidence(result.auxiliary_context)
    payload = result.auxiliary_context[0].as_dict()
    assert "source_identity" not in payload
    assert "locator_id" not in payload
    assert "release_id" not in payload
    assert payload["authority"] == memory_authority_boundary()


def test_stale_or_incorrect_memory_latest_reject_is_not_read(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    stale = _retain(
        runtime,
        summary="Incorrect older project memory says the evidence answer should change.",
    )
    runtime.record_review(
        memory_id=stale.memory_id,
        decision=MemoryReviewDecision.REJECT_CANDIDATE,
        reviewer_token="reviewer:m27",
        reason_codes=("SUPERSEDED_CANDIDATE",),
    )

    result = read_auxiliary_memory_context(task=_task(), memory_runtime=runtime)

    assert result.decision.allowed is True
    assert result.retained_count == 0
    assert result.auxiliary_context == ()


def test_private_payload_rejection_remains_fail_closed(tmp_path) -> None:
    runtime = _runtime(tmp_path)

    with pytest.raises(UnsafeMemoryPayloadError):
        runtime.propose_candidate(
            memory_class=MemoryClass.PROJECT,
            scope_token="task:memory:alpha",
            summary="raw query: private user payload must not enter memory context",
            provenance=_provenance(),
            tags=("activation", "memory"),
        )


def test_auxiliary_memory_cannot_override_evidence_answer(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    _retain(
        runtime,
        summary="Incorrect project memory says the final answer should be stale.",
    )
    context = read_auxiliary_memory_context(task=_task(), memory_runtime=runtime)
    evidence_answer = {
        "final_answer": "Evidence backed answer wins.",
        "citations": ["citation:primary"],
    }

    merged = answer_with_auxiliary_memory(
        answer=evidence_answer,
        memory_context=context.auxiliary_context,
    )

    assert merged["final_answer"] == evidence_answer["final_answer"]
    assert merged["citations"] == evidence_answer["citations"]
    assert merged["auxiliary_memory"]["used_for_authority"] is False
    assert merged["auxiliary_memory"]["answer_overridden"] is False
    assert merged["auxiliary_memory"]["retained_count"] == 1


def test_policy_cannot_widen_memory_classes_scope_or_item_budget() -> None:
    with pytest.raises(MemoryActivationError):
        GovernedMemoryReadPolicy(scope_binding="PROJECT_ID")
    with pytest.raises(MemoryActivationError):
        GovernedMemoryReadPolicy(max_items=0)
    with pytest.raises(MemoryActivationError):
        GovernedMemoryReadPolicy(allowed_memory_classes=())
