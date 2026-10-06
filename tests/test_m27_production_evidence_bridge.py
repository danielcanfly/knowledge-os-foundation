from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from knowledge_engine import m26_pa7_arbitrary_query_runtime as legacy
from knowledge_engine.m26_aq_semantic_contract import SemanticRequirement
from knowledge_engine.m26_production_answer_bundle import ProductionAnswerBundle
from knowledge_engine.m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from knowledge_engine.m27_memory_contracts import MemoryActivation
from knowledge_engine.m27_memory_runtime import GovernedMemoryRuntime
from knowledge_engine.m27_production_evidence_bridge import (
    ProductionEvidenceAuthority,
    production_evidence_binding_sha256,
)
from knowledge_engine.m27_runtime_execution import M27ExecutableRequest
from knowledge_engine.m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from knowledge_engine.m27_tool_contracts import KnowledgeItemRef, KnowledgeSearchOutput
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor
from knowledge_engine.m27_workspace_store import WorkspaceStore
from tests.test_m26_aq_canonical_semantic_contract_convergence import (
    SEGMENT_SCHEMA_VERSION,
    _TypedCompactProvider,
)

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "What does Graphology do for graph data?"
ANSWER = "Graphology keeps and analyzes graph data."


class ProductionKnowledgeProvider:
    def __init__(
        self, evidence: dict[str, Any], *, source: str | None = None, locator: str | None = None
    ) -> None:
        self.evidence = evidence
        self.source = source
        self.locator = locator
        self.searches = 0

    def search(self, request: object) -> KnowledgeSearchOutput:
        self.searches += 1
        return KnowledgeSearchOutput(
            items=(
                KnowledgeItemRef(
                    "kid-prod",
                    self.source or self.evidence["source_identity"],
                    self.locator or self.evidence["locator_id"],
                    self.evidence.get("evidence_type", "passage"),
                ),
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


def _production_bridge_material() -> tuple[dict[str, Any], ProductionEvidenceAuthority]:
    release_id = "m27-prod-bridge-release"
    body = "Graphology stores graph data and supports graph analysis."
    document = {
        "concept_id": "Graphology",
        "section_id": "Graphology#overview",
        "source_id": "source-graphology",
        "audience": "internal",
        "title": "Graphology",
        "section_title": "Overview",
        "description": body,
        "body": body,
        "excerpt": body,
        "terms": body.lower().replace(".", "").split(),
    }
    lexical_index = {
        "schema_version": "knowledge-engine-lexical-index/v1",
        "release_id": release_id,
        "documents": [document],
    }
    provenance = {
        "schema_version": "knowledge-engine-provenance/v1",
        "release_id": release_id,
        "records": [
            {
                "subject": {"concept_id": "Graphology"},
                "source_id": "source-graphology",
                "origin": {"path": "synthetic://graphology"},
                "claims": [
                    {
                        "claim_id": "claim_graphology",
                        "text": body,
                    }
                ],
            }
        ],
    }
    graph_v2 = {
        "schema_version": "knowledge-os-graph/v2",
        "release": {"release_id": release_id},
        "nodes": [{"concept_id": "Graphology", "title": "Graphology", "audience": "internal"}],
        "edges": [],
    }
    graph = {
        "schema_version": "knowledge-engine-graph/v1",
        "release_id": release_id,
        "nodes": [],
        "edges": [],
    }
    artifact_sha256 = {
        "graph": "d" * 64,
        "graph_v2": "c" * 64,
        "lexical_index": "a" * 64,
        "provenance": "b" * 64,
    }
    artifact_keys = {
        "graph": f"releases/{release_id}/artifacts/graph.json",
        "graph_v2": f"releases/{release_id}/artifacts/graph-v2.json",
        "lexical_index": f"releases/{release_id}/artifacts/lexical-index.json",
        "provenance": f"releases/{release_id}/artifacts/provenance.json",
    }
    manifest = {
        "schema_version": "knowledge-engine-release/v1",
        "release_id": release_id,
        "status": "production",
        "artifacts": [
            {"kind": kind, "key": artifact_keys[kind], "sha256": digest}
            for kind, digest in sorted(artifact_sha256.items())
        ],
    }
    bundle = ProductionAnswerBundle(
        manifest=manifest,
        graph=graph,
        graph_v2=graph_v2,
        lexical_index=lexical_index,
        provenance=provenance,
        manifest_sha256="5" * 64,
        artifact_sha256=artifact_sha256,
        artifact_keys=artifact_keys,
        loaded_at="2026-10-06T00:00:00Z",
    )
    evidence = legacy._evidence_item(
        bundle=bundle,
        document=document,
        lexical_result={},
        trace_id="m27-production-evidence-bridge",
        ordinal=1,
        channels=["lexical", "production_equivalent_bridge"],
        retrieval_metadata={"bridge_fixture": True},
    )
    authority = ProductionEvidenceAuthority(
        bundle=bundle,
        release_id=bundle.release_id,
        manifest_sha256=bundle.manifest_sha256,
        allowed_audiences=frozenset({"internal"}),
        evidence_binding_sha256_by_id={
            evidence["evidence_id"]: production_evidence_binding_sha256(evidence)
        },
    )
    return evidence, authority


def _request(
    provider: object,
    evidence: dict[str, Any],
    authority: ProductionEvidenceAuthority | None,
) -> M27ExecutableRequest:
    return M27ExecutableRequest(
        question=QUESTION,
        evidence_catalog={"kid-prod": evidence},
        compiler_policy=json.loads((ROOT / "pilot/m26/m26-3-context-policy.json").read_text()),
        semantic_provider=provider,
        production_evidence_authority=authority,
        requirements=(
            SemanticRequirement(
                requirement_id="graphology_storage",
                instruction="Explain that Graphology stores and analyses graph data.",
                evidence_terms=("Graphology", "stores", "graph", "data", "analysis"),
                visible_patterns=(r"Graphology stores graph data exactly",),
            ),
        ),
    )


def _input(request: M27ExecutableRequest, *, attempts: int = 8) -> M27RuntimeHarnessInput:
    return M27RuntimeHarnessInput(
        task=M27RuntimeTask(
            task_id="task:prod-bridge:001",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:prod-bridge:001",
            max_continuation_rounds=0,
            max_tool_calls=3,
        ),
        routing_signal={"route": "SEMANTIC_CLOSURE", "reason": "production_evidence_bridge"},
        budget_signal={
            "route": "SEMANTIC_CLOSURE",
            "reason": "bounded_semantic_recovery",
            "deadline_remaining_ms": 60000,
            "minimum_budget_ms": 500,
            "provider_attempts_remaining": attempts,
            "affordable": True,
        },
        executable_request=request,
    )


def _harness(tmp_path: Path, knowledge: ProductionKnowledgeProvider) -> M27RuntimeHarness:
    return M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=tmp_path / "workspace"),
        tool_executor=ReadOnlyToolExecutor(knowledge_provider=knowledge),
    )


def test_valid_production_equivalent_evidence_compiles_and_verifies_through_m27_runtime(
    tmp_path: Path,
) -> None:
    evidence, authority = _production_bridge_material()
    knowledge = ProductionKnowledgeProvider(evidence)
    provider = _provider()
    result = _harness(tmp_path, knowledge).run(_input(_request(provider, evidence, authority)))

    assert result.status_code == "M27_RUNTIME_COMPOSED", result.as_summary()
    assert result.answer is not None
    assert result.verification is not None
    assert result.verification["production_evidence_authority"] is True
    assert result.verification["evidence_authority"] == "production_equivalent"
    assert (
        result.execution_rounds[0]["compiler_authority"]
        == "m26_3_synthetic_selector_non_authoritative"
    )
    assert result.production_touched is False
    assert knowledge.searches == 1
    assert provider.calls >= 1


def test_source_locator_and_release_mismatch_are_rejected_before_publication(
    tmp_path: Path,
) -> None:
    evidence, authority = _production_bridge_material()

    source_mismatch_provider = _provider()
    source_mismatch = _harness(
        tmp_path / "source",
        ProductionKnowledgeProvider(evidence, source="wrong-source"),
    ).run(_input(_request(source_mismatch_provider, evidence, authority)))
    assert source_mismatch.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert source_mismatch_provider.calls == 0
    assert not source_mismatch.answer

    locator_mismatch_provider = _provider()
    locator_mismatch = _harness(
        tmp_path / "locator",
        ProductionKnowledgeProvider(evidence, locator="wrong-locator"),
    ).run(_input(_request(locator_mismatch_provider, evidence, authority)))
    assert locator_mismatch.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert locator_mismatch_provider.calls == 0
    assert not locator_mismatch.answer

    drifted = {**evidence, "release_id": "drifted-release"}
    release_mismatch_provider = _provider()
    release_mismatch = _harness(
        tmp_path / "release",
        ProductionKnowledgeProvider(drifted),
    ).run(_input(_request(release_mismatch_provider, drifted, authority)))
    assert release_mismatch.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert release_mismatch.terminal_reason == "PRODUCTION_EVIDENCE_AUTHORITY_REJECTED"
    assert release_mismatch_provider.calls == 0
    assert not release_mismatch.answer


def test_missing_provenance_digest_is_rejected(tmp_path: Path) -> None:
    evidence, authority = _production_bridge_material()
    missing = {**evidence, "provenance_record_sha256": ""}
    provider = _provider()
    result = _harness(tmp_path, ProductionKnowledgeProvider(missing)).run(
        _input(_request(provider, missing, authority))
    )
    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert provider.calls == 0
    assert not result.answer


def test_memory_cannot_supply_production_evidence_authority(tmp_path: Path) -> None:
    evidence, authority = _production_bridge_material()
    provider = _provider()
    knowledge = ProductionKnowledgeProvider(evidence)
    harness = M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=tmp_path / "workspace"),
        tool_executor=ReadOnlyToolExecutor(knowledge_provider=knowledge),
        memory_runtime=GovernedMemoryRuntime(
            root=tmp_path / "memory",
            activation=MemoryActivation(enabled=True, isolated_runtime=True),
        ),
    )
    request = _request(provider, evidence, authority)
    request = replace(request, evidence_catalog={})
    runtime_input = _input(request)
    runtime_input = replace(runtime_input, task=replace(runtime_input.task, allow_memory_read=True))
    result = harness.run(runtime_input)

    assert result.status_code == "M27_RUNTIME_SAFE_TERMINAL"
    assert result.memory_candidate_ids
    assert provider.calls == 0
    assert not result.answer
    assert result.verification is not None
    assert result.verification["production_evidence_authority"] is True


def test_synthetic_path_remains_explicitly_not_production_authority(tmp_path: Path) -> None:
    evidence, _authority = _production_bridge_material()
    provider = _provider()
    result = _harness(tmp_path, ProductionKnowledgeProvider(evidence)).run(
        _input(_request(provider, evidence, authority=None))
    )

    assert result.status_code == "M27_RUNTIME_COMPOSED", result.as_summary()
    assert result.verification is not None
    assert result.verification["production_evidence_authority"] is False
    assert result.verification["evidence_authority"] == "synthetic_only"
    assert result.execution_rounds[0]["compiler_authority"] == "m26_3_synthetic_only"
    assert result.production_touched is False
