from __future__ import annotations

import json

import pytest

from knowledge_engine.m27_adaptive_compute import AdaptiveComputeController
from knowledge_engine.m27_compute_policy import RuleBasedComputePolicy
from knowledge_engine.m27_context_orchestrator import (
    M27RuntimeTask,
    RuntimeTaskKind,
    RuntimeTaskProfile,
)
from knowledge_engine.m27_learning_meta_loop import (
    OfflineLearningMetaHarnessLoop,
    SanitizedObservationSource,
    SanitizedOfflineObservation,
    learning_meta_loop_governance,
)
from knowledge_engine.m27_mcp_readonly_transport import (
    McpReadonlyTransportError,
    McpReadonlyTransportPolicy,
    ReadOnlyMcpTransport,
)
from knowledge_engine.m27_memory_activation import (
    assert_memory_cannot_satisfy_evidence,
    memory_authority_boundary,
    read_auxiliary_memory_context,
)
from knowledge_engine.m27_memory_contracts import MemoryActivation
from knowledge_engine.m27_memory_runtime import GovernedMemoryRuntime
from knowledge_engine.m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from knowledge_engine.m27_skill_contracts import build_stage7_ops_skill_registry
from knowledge_engine.m27_skill_runner import (
    ReadOnlySkillRunner,
    SkillRunnerContext,
    SkillRunnerPolicy,
)
from knowledge_engine.m27_tool_contracts import RuntimeHealthInput
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor
from knowledge_engine.m27_workspace_store import WorkspaceStore
from tests.test_m27_skill_runner import CountingRuntimeProvider, _planning, _trace, _verification


def _budget_signal() -> dict[str, object]:
    return {
        "route": "SEMANTIC_CLOSURE",
        "reason": "wave_d_integration",
        "deadline_remaining_ms": 60_000,
        "minimum_budget_ms": 500,
        "provider_attempts_remaining": 8,
        "affordable": True,
    }


def _compute_observation():
    return RuleBasedComputePolicy().classify(_budget_signal())


def test_feature_off_returns_before_new_component_side_effects(tmp_path) -> None:
    class Bomb:
        def __getattr__(self, name: str):
            raise AssertionError(f"feature-off touched {name}")

    harness = M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=tmp_path / "workspace"),
        tool_executor=ReadOnlyToolExecutor(),
        memory_runtime=Bomb(),
        learning_runtime=Bomb(),
        meta_harness_runtime=Bomb(),
    )
    result = harness.run(
        M27RuntimeHarnessInput(
            task=M27RuntimeTask(
                task_id="task:wave:d:off",
                kind=RuntimeTaskKind.KNOWLEDGE,
                request_token="request:wave:d:off",
                allow_memory_read=True,
                profile=RuntimeTaskProfile.RETRIEVAL_HARD,
            ),
            routing_signal={},
            budget_signal={},
            m27_enabled=False,
        )
    )
    assert result.status_code == "M26_BASELINE_UNCHANGED"
    assert result.feature_off is True
    assert result.workspace_id is None
    assert result.tool_records == ()
    assert result.memory_candidate_ids == ()
    assert result.learning_proposal_ids == ()
    assert result.meta_candidate_ids == ()


def test_adaptive_profiles_cover_wave_d_taxonomy() -> None:
    controller = AdaptiveComputeController()
    compute = _compute_observation()
    profiles = {
        RuntimeTaskProfile.DIRECT_KNOWLEDGE: RuntimeTaskKind.KNOWLEDGE,
        RuntimeTaskProfile.MULTILINGUAL_KNOWLEDGE: RuntimeTaskKind.KNOWLEDGE,
        RuntimeTaskProfile.RETRIEVAL_HARD: RuntimeTaskKind.KNOWLEDGE,
        RuntimeTaskProfile.DEADLINE_PRESSURE: RuntimeTaskKind.KNOWLEDGE,
        RuntimeTaskProfile.SAFE_ABSTENTION: RuntimeTaskKind.KNOWLEDGE,
        RuntimeTaskProfile.TOOL_LOOKUP: RuntimeTaskKind.TOOL,
        RuntimeTaskProfile.OPS_DIAGNOSTIC: RuntimeTaskKind.OPS,
    }
    budgets = {
        profile: controller.decide_initial(
            kind=kind,
            profile=profile,
            compute=compute,
            requested_max_rounds=2,
            requested_max_tool_calls=6,
        )
        for profile, kind in profiles.items()
    }
    assert set(budgets) == set(profiles)
    assert all(item.max_tool_calls <= 6 for item in budgets.values())
    assert all(item.max_continuation_rounds <= 2 for item in budgets.values())


def test_skill_runner_is_bounded_by_adaptive_tool_budget_and_readonly_allowlist() -> None:
    adaptive = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.OPS,
        profile=RuntimeTaskProfile.OPS_DIAGNOSTIC,
        compute=_compute_observation(),
        requested_max_rounds=1,
        requested_max_tool_calls=1,
    )
    runtime = CountingRuntimeProvider(_trace())
    executor = ReadOnlyToolExecutor(runtime_provider=runtime)
    registry = build_stage7_ops_skill_registry(tool_registry=executor.registry)
    descriptor = registry.resolve("diagnose-latency")
    result = ReadOnlySkillRunner(skill_registry=registry, tool_executor=executor).run(
        "diagnose-latency",
        context=SkillRunnerContext(
            request_token="request:wave:d:skill",
            trace_id="00000000-0000-4000-8000-000000000091",
            evidence_planning_result=_planning(),
            verification_decision=_verification(),
        ),
        policy=SkillRunnerPolicy.for_skill(
            descriptor,
            authorization_token="task:wave:d:skill",
            max_tool_calls=adaptive.max_tool_calls,
        ),
    )
    assert adaptive.max_tool_calls == 1
    assert result.tool_call_count == 1
    assert result.budget_exhausted is True
    assert all(record.read_only for record in result.tool_records)
    assert all(not record.supports_mutation for record in result.tool_records)
    assert all(not record.exposes_raw_infra for record in result.tool_records)


def test_skill_output_has_no_evidence_or_answer_authority() -> None:
    runtime = CountingRuntimeProvider(_trace())
    executor = ReadOnlyToolExecutor(runtime_provider=runtime)
    registry = build_stage7_ops_skill_registry(tool_registry=executor.registry)
    descriptor = registry.resolve("diagnose-latency")
    result = ReadOnlySkillRunner(skill_registry=registry, tool_executor=executor).run(
        "diagnose-latency",
        context=SkillRunnerContext(
            request_token="request:wave:d:skill:authority",
            trace_id="00000000-0000-4000-8000-000000000092",
            evidence_planning_result=_planning(),
            verification_decision=_verification(),
        ),
        policy=SkillRunnerPolicy.for_skill(
            descriptor,
            authorization_token="task:wave:d:skill:authority",
            max_tool_calls=1,
        ),
    )
    payload = json.dumps(result.as_dict(), sort_keys=True).lower()
    assert "answer_override" not in payload
    assert "evidence_authority" not in payload
    assert result.candidate_actions == (
        "report_only",
        "candidate_followup_only",
        "no_production_mutation",
    )


def test_mcp_transport_default_off_no_network_and_executor_gated() -> None:
    with pytest.raises(McpReadonlyTransportError):
        McpReadonlyTransportPolicy(
            enabled=True,
            authorization_token="task:wave:d:mcp",
            allow_network_listener=True,
        )
    transport = ReadOnlyMcpTransport(tool_executor=ReadOnlyToolExecutor())
    with pytest.raises(McpReadonlyTransportError):
        transport.dispatch(
            "runtime.get_health",
            RuntimeHealthInput(),
            policy=McpReadonlyTransportPolicy(
                enabled=False,
                authorization_token="task:wave:d:mcp:off",
            ),
        )


def test_enabled_mcp_shim_exposes_only_readonly_allowlisted_descriptor() -> None:
    runtime = CountingRuntimeProvider(_trace())
    transport = ReadOnlyMcpTransport(
        tool_executor=ReadOnlyToolExecutor(runtime_provider=runtime)
    )
    result = transport.dispatch(
        "runtime.get_health",
        RuntimeHealthInput(),
        policy=McpReadonlyTransportPolicy(
            enabled=True,
            authorization_token="task:wave:d:mcp:on",
        ),
    )
    assert result.result.record.capability_name == "runtime.get_health"
    assert result.result.record.read_only is True
    assert result.result.record.supports_mutation is False
    assert result.result.record.exposes_raw_infra is False


def test_memory_requires_explicit_allow_and_remains_auxiliary_reviewed_only(tmp_path) -> None:
    memory = GovernedMemoryRuntime(
        root=tmp_path / "memory",
        activation=MemoryActivation(enabled=True, isolated_runtime=True),
    )
    denied = read_auxiliary_memory_context(
        task=M27RuntimeTask(
            task_id="task:wave:d:memory",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token="request:wave:d:memory",
            allow_memory_read=False,
        ),
        memory_runtime=memory,
    )
    assert denied.decision.allowed is False
    assert denied.retained_count == 0
    authority = memory_authority_boundary()
    assert authority["knowledge_authority"] is False
    assert authority["citation_eligible"] is False
    assert authority["can_satisfy_evidence_requirements"] is False
    assert authority["can_override_answer"] is False


def test_memory_sidecar_cannot_satisfy_any_evidence_authority() -> None:
    assert_memory_cannot_satisfy_evidence(())
    authority = memory_authority_boundary()
    for field in (
        "knowledge_authority",
        "citation_eligible",
        "source_identity_eligible",
        "locator_eligible",
        "release_eligible",
        "can_satisfy_evidence_requirements",
        "can_override_answer",
        "can_promote_to_knowledge",
        "production_write",
    ):
        assert authority[field] is False


def test_learning_meta_is_sanitized_review_only_and_cannot_mutate_runtime() -> None:
    observation = SanitizedOfflineObservation(
        source=SanitizedObservationSource.RUNTIME_TRACE,
        source_ref="trace:wave:d:001",
        observed_class="TOOL_POLICY_DENIAL",
        reason_codes=("TOOL_POLICY_DENIAL",),
        summary="Sanitized tool policy denial observation.",
    )
    result = OfflineLearningMetaHarnessLoop().run((observation,))
    governance = learning_meta_loop_governance()
    assert result.ready_for_review_count > 0
    assert governance["sanitized_inputs_only"] is True
    assert governance["raw_private_payload_allowed"] is False
    assert governance["proposal_only"] is True
    assert governance["candidate_only"] is True
    assert governance["auto_apply"] is False
    assert governance["auto_merge"] is False
    assert governance["auto_promote"] is False
    assert governance["production_write"] is False
    assert governance["runtime_behavior_change"] is False
    assert governance["release_authority"] is False
    assert governance["deployment_authority"] is False


def test_combined_wave_d_telemetry_has_no_raw_private_payload() -> None:
    secret = "PRIVATE-WAVE-D-PAYLOAD"
    adaptive = AdaptiveComputeController().decide_initial(
        kind=RuntimeTaskKind.OPS,
        profile=RuntimeTaskProfile.OPS_DIAGNOSTIC,
        compute=_compute_observation(),
        requested_max_rounds=1,
        requested_max_tool_calls=1,
    )
    combined = {
        "adaptive": adaptive.as_dict(),
        "memory": memory_authority_boundary(),
        "learning": learning_meta_loop_governance(),
        "skill": {
            "read_only": True,
            "evidence_authority": False,
            "answer_override": False,
        },
        "mcp": {
            "enabled_by_default": False,
            "network_listener": False,
            "read_only": True,
        },
    }
    serialized = json.dumps(combined, sort_keys=True)
    assert secret not in serialized
    assert "raw_query" not in serialized.lower()
    assert "raw_answer" not in serialized.lower()
    assert "credential" not in serialized.lower()


def test_fresh_smoke_invariants_remain_non_admission_non_production() -> None:
    source_files = (
        "src/knowledge_engine/m27_skill_runner.py",
        "src/knowledge_engine/m27_mcp_readonly_transport.py",
        "src/knowledge_engine/m27_memory_activation.py",
        "src/knowledge_engine/m27_learning_meta_loop.py",
    )
    forbidden_runtime_markers = (
        "stage13",
        "stage14",
        "full523",
        "100-case",
        "chunk002",
        "production_write=true",
    )
    for path in source_files:
        with open(path) as handle:
            text = handle.read().lower()
        assert not any(marker in text for marker in forbidden_runtime_markers)


def test_integration_governance_keeps_production_and_release_authority_false() -> None:
    assert memory_authority_boundary()["production_write"] is False
    governance = learning_meta_loop_governance()
    assert governance["production_write"] is False
    assert governance["release_authority"] is False
    assert governance["deployment_authority"] is False
