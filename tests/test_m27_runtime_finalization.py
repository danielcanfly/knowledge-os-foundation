from __future__ import annotations

import json
from pathlib import Path

from knowledge_engine.m26_aq_semantic_contract import SemanticRequirement
from knowledge_engine.m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from knowledge_engine.m27_runtime_execution import M27ExecutableRequest
from knowledge_engine.m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from knowledge_engine.m27_tool_contracts import KnowledgeItemRef, KnowledgeSearchOutput
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor
from knowledge_engine.m27_workspace_store import WorkspaceStore
from tests.test_m26_aq_canonical_semantic_contract_convergence import (
    SEGMENT_SCHEMA_VERSION,
    _passage,
    _TypedCompactProvider,
)

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "What does Graphology do for graph data?"
ANSWER = "Graphology keeps and analyzes graph data."


class KnowledgeProvider:
    def __init__(self) -> None:
        self.searches = 0

    def search(self, request: object) -> KnowledgeSearchOutput:
        self.searches += 1
        return KnowledgeSearchOutput(
            items=(
                KnowledgeItemRef("kid-1", "source-ev-graphology", "loc-ev-graphology", "passage"),
            ),
            total_count=1,
        )


def _provider() -> _TypedCompactProvider:
    return _TypedCompactProvider(
        {
            "schema_version": SEGMENT_SCHEMA_VERSION,
            "status": "answer",
            "segments": [
                {
                    "segment_id": "s1",
                    "semantic_role": "material_claim",
                    "claim_id": "claim_1",
                    "claim_type": "EVIDENCE_FACT",
                    "text": ANSWER,
                    "evidence_labels": ["e1"],
                    "covers": ["graphology_storage"],
                }
            ],
            "unanswered_dimensions": [],
            "abstention_reason": None,
        }
    )


def _harness(tmp_path: Path, knowledge: KnowledgeProvider) -> M27RuntimeHarness:
    return M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=tmp_path / "workspace"),
        tool_executor=ReadOnlyToolExecutor(knowledge_provider=knowledge),
    )


def _request(provider: object) -> M27ExecutableRequest:
    return M27ExecutableRequest(
        question=QUESTION,
        evidence_catalog={
            "kid-1": _passage(
                "ev-graphology",
                "Graphology stores graph data and supports graph analysis.",
                concept_id="Graphology",
            )
        },
        compiler_policy=json.loads((ROOT / "pilot/m26/m26-3-context-policy.json").read_text()),
        semantic_provider=provider,
        requirements=(
            SemanticRequirement(
                requirement_id="graphology_storage",
                instruction="Explain that Graphology stores and analyses graph data.",
                evidence_terms=("Graphology", "stores", "graph", "data", "analysis"),
                visible_patterns=(r"Graphology stores graph data exactly",),
            ),
        ),
    )


def _input(
    request: M27ExecutableRequest,
    *,
    kind: RuntimeTaskKind = RuntimeTaskKind.KNOWLEDGE,
    max_tool_calls: int = 3,
    max_rounds: int = 1,
    attempts: int = 8,
    m27_enabled: bool = True,
) -> M27RuntimeHarnessInput:
    return M27RuntimeHarnessInput(
        task=M27RuntimeTask(
            task_id="task:isolated:001",
            kind=kind,
            request_token="request:isolated:001",
            requested_capability="runtime.get_health" if kind is RuntimeTaskKind.TOOL else None,
            max_continuation_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
        ),
        routing_signal={"route": "SEMANTIC_CLOSURE", "reason": "evidence"},
        budget_signal={
            "route": "SEMANTIC_CLOSURE",
            "reason": "bounded_semantic_recovery",
            "deadline_remaining_ms": 60000,
            "minimum_budget_ms": 500,
            "provider_attempts_remaining": attempts,
            "affordable": True,
        },
        executable_request=request,
        m27_enabled=m27_enabled,
    )


def test_executes_real_m26_compiler_and_verifier_without_prefilled_results(
    tmp_path: Path,
) -> None:
    knowledge = KnowledgeProvider()
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(_input(_request(provider)))
    assert result.status_code == "M27_RUNTIME_COMPOSED", result.as_summary()
    assert result.answer is not None
    assert result.answer["answer_text"] == ANSWER
    assert provider.calls >= 2
    assert knowledge.searches == 1
    assert len(result.execution_rounds) == 1
    assert result.execution_rounds[0]["compiler_status"] in {"compiled", "compiled_with_warnings"}
    assert result.execution_rounds[0]["terminal_reason"] == "VERIFIED_CITED_ANSWER"


def test_budget_exhausted_prevents_all_calls(tmp_path: Path) -> None:
    knowledge = KnowledgeProvider()
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(_input(_request(provider), attempts=0))
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert result.execution_rounds == ()
    assert knowledge.searches == 0
    assert provider.calls == 0


def test_unapproved_tool_never_called(tmp_path: Path) -> None:
    knowledge = KnowledgeProvider()
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(
        _input(_request(provider), kind=RuntimeTaskKind.TOOL)
    )
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert result.terminal_reason == "NO_AUTHORIZED_EVIDENCE_CAPABILITY"
    assert knowledge.searches == 0
    assert provider.calls == 0


def test_feature_off_inert(tmp_path: Path) -> None:
    knowledge = KnowledgeProvider()
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(_input(_request(provider), m27_enabled=False))
    assert result.status_code == "M26_BASELINE_UNCHANGED"
    assert knowledge.searches == 0
    assert provider.calls == 0
    assert result.workspace_id is None


def test_no_second_round_when_tool_budget_exhausted(tmp_path: Path) -> None:
    knowledge = KnowledgeProvider()
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(
        _input(_request(provider), max_tool_calls=1, max_rounds=3)
    )
    assert knowledge.searches == 1
    assert len(result.execution_rounds) <= 1


def test_verifier_gap_executes_second_gather_compile_answer_verify(
    tmp_path: Path,
) -> None:
    from tests.test_m26_aq_canonical_semantic_contract_convergence import (
        _CompactAbstainingProvider,
    )

    knowledge = KnowledgeProvider()
    provider = _CompactAbstainingProvider()
    result = _harness(tmp_path, knowledge).run(
        _input(_request(provider), max_rounds=1, attempts=12)
    )
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert knowledge.searches == 2
    assert len(result.execution_rounds) == 2
    assert all(
        item["compiler_status"] in {"compiled", "compiled_with_warnings"}
        for item in result.execution_rounds
    )
    assert all(
        item["verification_status"] == "owner_only_safe_abstention"
        for item in result.execution_rounds
    )
    assert result.execution_rounds[1]["round_index"] == 1
    assert result.execution_rounds[1]["continuation_reason"] == "VERIFIER_GAP"
    assert result.execution_rounds[1]["terminal_reason"] == "VERIFIER_GAP_SAFE_TERMINAL"
    assert provider.calls >= 2
    assert result.trace_event is not None
    assert result.trace_event.evidence_count == 1
    assert result.production_touched is False


def test_no_unbounded_continuation_even_with_large_budget(tmp_path: Path) -> None:
    from tests.test_m26_aq_canonical_semantic_contract_convergence import (
        _CompactAbstainingProvider,
    )

    knowledge = KnowledgeProvider()
    result = _harness(tmp_path, knowledge).run(
        _input(_request(_CompactAbstainingProvider()), max_rounds=2, attempts=30)
    )
    assert knowledge.searches == 2
    assert len(result.execution_rounds) == 2
    assert result.execution_rounds[-1]["round_index"] == 1
    assert result.execution_rounds[-1]["terminal_reason"] == "VERIFIER_GAP_SAFE_TERMINAL"
    assert (
        result.execution_rounds[-1]["adaptive_continuation_reason"]
        == "TELEMETRY_NO_EVIDENCE_GAIN"
    )


def test_provider_budget_blocks_second_round(tmp_path: Path) -> None:
    from tests.test_m26_aq_canonical_semantic_contract_convergence import (
        _CompactAbstainingProvider,
    )

    knowledge = KnowledgeProvider()
    provider = _CompactAbstainingProvider()
    result = _harness(tmp_path, knowledge).run(_input(_request(provider), max_rounds=4, attempts=1))
    assert knowledge.searches == 1
    assert len(result.execution_rounds) == 1
    assert provider.calls == 1
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"


def test_unbound_evidence_cannot_create_citation(tmp_path: Path) -> None:
    knowledge = KnowledgeProvider()
    provider = _provider()
    request = _request(provider)
    request.evidence_catalog["kid-1"]["source_identity"] = "wrong-source"
    result = _harness(tmp_path, knowledge).run(_input(request))
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert not result.answer
    assert provider.calls == 0
    assert result.trace_event is not None
    assert result.trace_event.evidence_count == 0


def test_distinct_isolated_workspace_roots(tmp_path: Path) -> None:
    knowledge = KnowledgeProvider()
    first = _harness(tmp_path / "first", knowledge).run(_input(_request(_provider())))
    second = _harness(tmp_path / "second", knowledge).run(_input(_request(_provider())))
    assert first.workspace_id is not None
    assert second.workspace_id is not None
    assert (tmp_path / "first" / "workspace").exists()
    assert (tmp_path / "second" / "workspace").exists()
    assert first.production_touched is False
    assert second.production_touched is False


def test_candidate_memory_cannot_substitute_for_evidence(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from knowledge_engine.m27_memory_contracts import MemoryActivation
    from knowledge_engine.m27_memory_runtime import GovernedMemoryRuntime

    knowledge = KnowledgeProvider()
    provider = _provider()
    harness = M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=tmp_path / "workspace"),
        tool_executor=ReadOnlyToolExecutor(knowledge_provider=knowledge),
        memory_runtime=GovernedMemoryRuntime(
            root=tmp_path / "memory",
            activation=MemoryActivation(enabled=True, isolated_runtime=True),
        ),
    )
    request = replace(_request(provider), evidence_catalog={})
    input_ = _input(request)
    input_ = replace(input_, task=replace(input_.task, allow_memory_read=True))
    result = harness.run(input_)
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert provider.calls == 0
    assert result.memory_candidate_ids
    assert not result.answer
    assert result.production_touched is False


def test_deadline_budget_blocks_gather_and_answer(tmp_path: Path) -> None:
    from dataclasses import replace

    knowledge = KnowledgeProvider()
    provider = _provider()
    input_ = _input(_request(provider))
    input_ = replace(
        input_,
        budget_signal={**input_.budget_signal, "deadline_remaining_ms": 100},
    )
    result = _harness(tmp_path, knowledge).run(input_)
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert knowledge.searches == 0
    assert provider.calls == 0


def test_first_round_gap_then_real_second_round_cited_terminal(
    tmp_path: Path,
) -> None:
    from tests.test_m26_aq_canonical_semantic_contract_convergence import (
        _CompactAbstainingProvider,
    )

    class GapThenAnswerProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.abstain = _CompactAbstainingProvider()
            self.answer = _provider()

        def call(self, payload: dict[str, object], call_class: str) -> dict[str, object]:
            self.calls += 1
            if self.calls <= 2:
                return self.abstain.call(payload, call_class)
            return self.answer.call(payload, call_class)

    knowledge = KnowledgeProvider()
    provider = GapThenAnswerProvider()
    result = _harness(tmp_path, knowledge).run(
        _input(_request(provider), max_rounds=1, attempts=12)
    )
    assert result.status_code == "M27_RUNTIME_COMPOSED", result.as_summary()
    assert knowledge.searches == 2
    assert len(result.execution_rounds) == 2
    assert result.execution_rounds[0]["verification_status"] == "owner_only_safe_abstention"
    assert result.execution_rounds[1]["verification_status"] == "owner_only_cited_answer"
    assert result.execution_rounds[-1]["terminal_reason"] == "VERIFIED_CITED_ANSWER"
    assert result.answer is not None
    assert result.answer["answer_text"] == ANSWER


def test_new_evidence_on_continuation_can_produce_verified_terminal(
    tmp_path: Path,
) -> None:
    """The second round must consume fresh tool output, not reverify a cached answer."""

    class ProgressiveKnowledge(KnowledgeProvider):
        def search(self, request: object) -> KnowledgeSearchOutput:
            self.searches += 1
            if self.searches == 1:
                return KnowledgeSearchOutput(items=(), total_count=0)
            return KnowledgeSearchOutput(
                items=(
                    KnowledgeItemRef(
                        "kid-1", "source-ev-graphology", "loc-ev-graphology", "passage"
                    ),
                ),
                total_count=1,
            )

    knowledge = ProgressiveKnowledge()
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(_input(_request(provider), attempts=8, max_rounds=1))
    assert result.status_code == "M27_RUNTIME_COMPOSED"
    assert knowledge.searches == 2
    assert len(result.execution_rounds) == 2
    assert result.execution_rounds[0]["evidence_count"] == 0
    assert result.execution_rounds[0]["compiler_status"] == "abstain_required"
    assert result.execution_rounds[1]["evidence_count"] == 1
    assert result.execution_rounds[1]["evidence_delta"] == 1
    assert result.execution_rounds[1]["terminal_reason"] == "VERIFIED_CITED_ANSWER"
    assert result.answer is not None
    assert result.answer["answer_text"] == ANSWER
    assert provider.calls >= 2
