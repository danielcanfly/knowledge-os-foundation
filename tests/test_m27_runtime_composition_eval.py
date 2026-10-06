from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_engine.m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from knowledge_engine.m27_learning_runtime import LearningRuntime
from knowledge_engine.m27_memory_contracts import MemoryActivation
from knowledge_engine.m27_memory_runtime import GovernedMemoryRuntime
from knowledge_engine.m27_meta_harness_runtime import MetaHarnessRuntime
from knowledge_engine.m27_readonly_tools import ExistingResultEvidenceProvider
from knowledge_engine.m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from knowledge_engine.m27_tool_contracts import (
    KnowledgeExpandInput,
    KnowledgeExpandOutput,
    KnowledgeItemRef,
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
)
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor
from knowledge_engine.m27_workspace_store import WorkspaceStore


class FakeKnowledgeProvider:
    def __init__(self) -> None:
        self.search_count = 0
        self.expand_count = 0

    def search(self, request: KnowledgeSearchInput) -> KnowledgeSearchOutput:
        self.search_count += 1
        return KnowledgeSearchOutput(
            items=(KnowledgeItemRef("kid-1", "source-A", "loc-1", "passage"),),
            total_count=1,
        )

    def expand(self, request: KnowledgeExpandInput) -> KnowledgeExpandOutput:
        self.expand_count += 1
        return KnowledgeExpandOutput(
            items=(KnowledgeItemRef("kid-2", "source-B", "loc-2", "passage"),),
            total_count=1,
        )


def _budget(attempts: int = 2, remaining_ms: int = 2000) -> dict[str, object]:
    return {
        "route": "SEMANTIC_CLOSURE",
        "reason": "bounded_semantic_recovery",
        "deadline_remaining_ms": remaining_ms,
        "minimum_budget_ms": 500,
        "provider_attempts_remaining": attempts,
        "affordable": True,
    }


def _verification(status: str = "verified_answer") -> dict[str, object]:
    return {
        "status": status,
        "terminal_status": "answered",
        "safe_abstention": False,
        "reason_codes": ("SUPPORT_VERIFIED",),
        "provider_call_count": 1,
        "material_claim_support_verified": status == "verified_answer",
        "citation_locator_valid": True,
        "unsupported_accepted_claims": 0,
        "repair_attempted": False,
        "citations": ("c1", "c2"),
        "answer_source": "strict_evidence_bound",
    }


def _harness(
    tmp_path: Path,
    *,
    knowledge: FakeKnowledgeProvider | None = None,
) -> M27RuntimeHarness:
    executor = ReadOnlyToolExecutor(
        knowledge_provider=knowledge or FakeKnowledgeProvider(),
        evidence_provider=ExistingResultEvidenceProvider(),
    )
    return M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=tmp_path / "workspace"),
        tool_executor=executor,
        memory_runtime=GovernedMemoryRuntime(
            root=tmp_path / "memory",
            activation=MemoryActivation(enabled=True, isolated_runtime=True),
        ),
        learning_runtime=LearningRuntime(),
        meta_harness_runtime=MetaHarnessRuntime(),
    )


def _input(
    task: M27RuntimeTask,
    *,
    m27_enabled: bool = True,
    verification_status: str = "verified_answer",
    budget: dict[str, object] | None = None,
) -> M27RuntimeHarnessInput:
    return M27RuntimeHarnessInput(
        task=task,
        routing_signal={"route": "SEMANTIC_CLOSURE", "reason": "evidence_gap"},
        budget_signal=budget or _budget(),
        selected_evidence=(
            {
                "evidence_id": "ev-1",
                "passage_id": "p-1",
                "source_identity": "src-1",
                "locator_id": "loc-1",
                "evidence_type": "passage",
            },
        ),
        requirements=({"requirement_id": "req-1"},),
        support_classification=({"requirement_id": "req-1", "support_status": "supported"},),
        sufficiency_status="sufficient",
        compiled_output={
            "status": "compiled",
            "safe_for_provider_mock": True,
            "context_manifest": {
                "selected_passage_ids": ("p-1",),
                "token_budget": 1024,
                "measured_token_estimate": 400,
            },
            "citations": ("c1", "c2"),
            "diagnostics": {"reason_codes": ("COMPILED",)},
        },
        verification_output=_verification(verification_status),
        health_payload={"freshness": "snapshot", "data": {"overall_status": "healthy"}},
        m27_enabled=m27_enabled,
    )


def test_no_context_task_uses_no_tool_or_memory_context(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:no-context:001",
                kind=RuntimeTaskKind.NO_CONTEXT,
                request_token="request:no-context:001",
            )
        )
    )

    assert result.status_code == "M27_RUNTIME_COMPOSED"
    assert result.plan is not None
    assert result.plan.context_sources == ()
    assert result.tool_records == ()
    assert result.memory_candidate_ids == ()


def test_knowledge_task_selects_knowledge_and_invokes_search(tmp_path: Path) -> None:
    knowledge = FakeKnowledgeProvider()
    result = _harness(tmp_path, knowledge=knowledge).run(
        _input(
            M27RuntimeTask(
                task_id="task:knowledge:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:knowledge:001",
            )
        )
    )

    assert knowledge.search_count == 1
    assert [record.capability_name for record in result.tool_records] == ["knowledge.search"]


def test_tool_task_invokes_only_requested_readonly_tool(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:tool:001",
                kind=RuntimeTaskKind.TOOL,
                request_token="request:tool:001",
                requested_capability="runtime.get_health",
            )
        )
    )

    assert [record.capability_name for record in result.tool_records] == ["runtime.get_health"]


def test_ops_task_selects_skill_and_uses_readonly_skill_capabilities(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:ops:001",
                kind=RuntimeTaskKind.OPS,
                request_token="request:ops:001",
                ops_intent="latency",
            )
        )
    )

    assert result.plan is not None
    assert result.plan.selected_skill_name == "diagnose-latency"
    assert tuple(record.capability_name for record in result.tool_records) == (
        "runtime.get_budget",
        "runtime.get_health",
        "runtime.get_trace",
    )


def test_workspace_is_isolated_per_task(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    first = harness.run(
        _input(
            M27RuntimeTask(
                task_id="task:workspace:001",
                kind=RuntimeTaskKind.NO_CONTEXT,
                request_token="request:workspace:001",
            )
        )
    )
    second = harness.run(
        _input(
            M27RuntimeTask(
                task_id="task:workspace:002",
                kind=RuntimeTaskKind.NO_CONTEXT,
                request_token="request:workspace:002",
            )
        )
    )

    assert first.workspace_id is not None
    assert second.workspace_id is not None
    assert first.workspace_id != second.workspace_id


def test_memory_candidate_is_non_authoritative_and_explicit(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:memory:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:memory:001",
                allow_memory_read=True,
            )
        )
    )

    assert result.memory_candidate_ids
    assert result.plan is not None
    assert "knowledge.search" in result.plan.tool_capabilities
    assert result.production_touched is False


def test_verifier_gap_gets_at_most_one_bounded_continuation(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:continue:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:continue:001",
                max_continuation_rounds=1,
            ),
            verification_status="needs_repair",
        )
    )

    assert result.continuation_decision is not None
    assert result.continuation_decision.allowed is True
    assert result.continuation_decision.max_rounds == 1


def test_budget_exhaustion_blocks_continuation(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:budget:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:budget:001",
            ),
            verification_status="needs_repair",
            budget=_budget(attempts=0),
        )
    )

    assert result.continuation_decision is not None
    assert result.continuation_decision.allowed is False


def test_unauthorized_tool_capability_fails_closed(tmp_path: Path) -> None:
    with pytest.raises((KeyError, ValueError, RuntimeError)):
        _harness(tmp_path).run(
            _input(
                M27RuntimeTask(
                    task_id="task:badtool:001",
                    kind=RuntimeTaskKind.TOOL,
                    request_token="request:badtool:001",
                    requested_capability="admin.mutate",
                )
            )
        )


def test_mutation_style_tool_is_not_executable(tmp_path: Path) -> None:
    with pytest.raises((KeyError, ValueError, RuntimeError)):
        _harness(tmp_path).run(
            _input(
                M27RuntimeTask(
                    task_id="task:badtool:002",
                    kind=RuntimeTaskKind.TOOL,
                    request_token="request:badtool:002",
                    requested_capability="release.promote",
                )
            )
        )


def test_trace_summary_does_not_store_raw_query_answer_or_evidence(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:sanitize:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:sanitize:001",
            )
        )
    )
    serialized = json.dumps(result.as_summary(), sort_keys=True)

    for forbidden in (
        "PRIVATE QUERY",
        "PRIVATE ANSWER",
        "PRIVATE EVIDENCE",
        "raw_query",
        "raw_answer",
    ):
        assert forbidden not in serialized


def test_learning_candidate_is_proposal_only(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:learning:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:learning:001",
            )
        )
    )

    assert result.learning_proposal_ids
    assert result.production_touched is False


def test_meta_harness_candidate_is_review_only(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:meta:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:meta:001",
            )
        )
    )

    assert result.meta_candidate_ids
    assert result.production_touched is False


def test_feature_off_leaves_m26_baseline_unchanged(tmp_path: Path) -> None:
    knowledge = FakeKnowledgeProvider()
    result = _harness(tmp_path, knowledge=knowledge).run(
        _input(
            M27RuntimeTask(
                task_id="task:off:001",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:off:001",
            ),
            m27_enabled=False,
        )
    )

    assert result.status_code == "M26_BASELINE_UNCHANGED"
    assert result.feature_off is True
    assert result.trace_event is None
    assert result.tool_records == ()
    assert knowledge.search_count == 0


def test_runtime_composition_does_not_expose_production_authority(tmp_path: Path) -> None:
    result = _harness(tmp_path).run(
        _input(
            M27RuntimeTask(
                task_id="task:prod:001",
                kind=RuntimeTaskKind.NO_CONTEXT,
                request_token="request:prod:001",
            )
        )
    )

    assert result.production_touched is False
    assert not hasattr(_harness(tmp_path), "promote")
    assert not hasattr(_harness(tmp_path), "rollback")
