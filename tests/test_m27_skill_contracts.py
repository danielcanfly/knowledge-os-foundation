from __future__ import annotations

import pytest

from knowledge_engine.m27_skill_contracts import (
    ForbiddenSkillError,
    SkillCategory,
    SkillDescriptor,
    SkillOutputKind,
    SkillRegistry,
    SkillStep,
    SkillStepKind,
    build_stage7_ops_skill_registry,
    deferred_stage7_skill_names,
)
from knowledge_engine.m27_tool_registry import (
    ForbiddenCapabilityError as ToolForbiddenCapabilityError,
)
from knowledge_engine.m27_tool_registry import (
    UnknownCapabilityError,
    build_stage5_readonly_registry,
    clone_descriptor,
)


def test_default_stage7_registry_contains_ops_skills_only() -> None:
    registry = build_stage7_ops_skill_registry()

    assert [skill.name for skill in registry.list()] == [
        "diagnose-latency",
        "investigate-answer-failure",
        "investigate-retrieval-failure",
        "run-quality-gate",
    ]
    assert len(registry) == 4
    assert all(skill.grants_authority is False for skill in registry.list())
    assert all(skill.can_execute_tools is False for skill in registry.list())
    assert all(skill.supports_mutation is False for skill in registry.list())
    assert all(skill.production_write is False for skill in registry.list())
    assert all(skill.answer_path is False for skill in registry.list())
    assert all(skill.mcp_exposed is False for skill in registry.list())


def test_skill_plan_is_descriptive_only_and_body_free() -> None:
    registry = build_stage7_ops_skill_registry()
    plan = registry.plan("investigate-answer-failure")
    data = plan.as_dict()

    assert data["authority_status"] == "NO_AUTHORITY_GRANTED"
    assert data["execution_status"] == "DESCRIPTIVE_ONLY"
    assert "invoke_tool" in data["prohibited_actions"]
    assert "promote_release" in data["prohibited_actions"]
    assert "store_raw_query_or_answer" in data["prohibited_actions"]
    assert all(step.report_only for step in plan.steps)
    assert all(not step.grants_authority for step in plan.steps)
    assert all(not step.supports_mutation for step in plan.steps)
    assert all(not step.production_write for step in plan.steps)
    assert "private question" not in repr(data).casefold()
    assert "answer_text" not in repr(data).casefold()
    assert "evidence body" not in repr(data).casefold()


def test_stage7_skills_use_stage5_readonly_capabilities_only() -> None:
    tool_registry = build_stage5_readonly_registry()
    skill_registry = build_stage7_ops_skill_registry(tool_registry=tool_registry)

    for skill in skill_registry.list():
        for capability in skill.allowed_capabilities:
            tool = tool_registry.resolve(capability)
            assert tool.read_only is True
            assert tool.supports_mutation is False
            assert tool.exposes_raw_infra is False
            assert tool.requires_authorization is True


def test_registry_has_no_execute_or_invoke_surface() -> None:
    registry = build_stage7_ops_skill_registry()

    assert not hasattr(registry, "execute")
    assert not hasattr(registry, "invoke")
    assert not hasattr(registry, "run")


def test_deferred_answer_and_write_skills_are_rejected() -> None:
    assert deferred_stage7_skill_names() == (
        "answer-from-knowledge",
        "deep-research",
        "ingest-and-update-knowledge",
        "promote-knowledge-release",
    )
    registry = SkillRegistry()

    for name in deferred_stage7_skill_names():
        descriptor = SkillDescriptor(
            name=name,
            description="deferred skill",
            category=SkillCategory.OPS_INVESTIGATION,
            allowed_capabilities=("runtime.get_trace",),
            outputs=(SkillOutputKind.INVESTIGATION_REPORT,),
            steps=(
                SkillStep(
                    "collect-runtime-trace",
                    "Collect sanitized trace metadata",
                    SkillStepKind.COLLECT_METADATA,
                    ("runtime.get_trace",),
                ),
            ),
        )
        with pytest.raises(ForbiddenSkillError):
            registry.register(descriptor)


def test_skill_descriptor_rejects_authority_execution_mutation_and_mcp() -> None:
    base = dict(
        name="investigate-test-failure",
        description="test descriptor",
        category=SkillCategory.OPS_INVESTIGATION,
        allowed_capabilities=("runtime.get_trace",),
        outputs=(SkillOutputKind.INVESTIGATION_REPORT,),
        steps=(
            SkillStep(
                "collect-runtime-trace",
                "Collect sanitized trace metadata",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_trace",),
            ),
        ),
    )
    for field in (
        "grants_authority",
        "can_execute_tools",
        "supports_mutation",
        "production_write",
        "answer_path",
        "mcp_exposed",
    ):
        with pytest.raises(ForbiddenSkillError):
            SkillDescriptor(**base, **{field: True})


def test_skill_step_rejects_mutating_or_authorizing_steps() -> None:
    for field in ("grants_authority", "supports_mutation", "production_write"):
        with pytest.raises(ForbiddenSkillError):
            SkillStep(
                "bad-step",
                "bad",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.get_trace",),
                **{field: True},
            )
    with pytest.raises(ForbiddenSkillError):
        SkillStep(
            "bad-step",
            "bad",
            SkillStepKind.COLLECT_METADATA,
            ("runtime.get_trace",),
            report_only=False,
        )


def test_skill_rejects_unknown_or_unsafe_tool_capability() -> None:
    registry = SkillRegistry()
    descriptor = SkillDescriptor(
        name="investigate-unknown-capability",
        description="unknown capability",
        category=SkillCategory.OPS_INVESTIGATION,
        allowed_capabilities=("runtime.unknown",),
        outputs=(SkillOutputKind.INVESTIGATION_REPORT,),
        steps=(
            SkillStep(
                "collect-unknown",
                "Collect unknown metadata",
                SkillStepKind.COLLECT_METADATA,
                ("runtime.unknown",),
            ),
        ),
    )
    with pytest.raises(UnknownCapabilityError):
        registry.register(descriptor)


def test_skill_rejects_tool_registry_mutating_descriptor() -> None:
    tool_registry = build_stage5_readonly_registry()
    unsafe = clone_descriptor(
        tool_registry.resolve("runtime.get_trace"),
        supports_mutation=True,
    )
    with pytest.raises(ToolForbiddenCapabilityError):
        tool_registry.register(unsafe)


def test_list_by_category() -> None:
    registry = build_stage7_ops_skill_registry()

    assert [skill.name for skill in registry.list(category=SkillCategory.OPS_DIAGNOSIS)] == [
        "diagnose-latency"
    ]
    assert [skill.name for skill in registry.list(category=SkillCategory.OPS_QUALITY_GATE)] == [
        "run-quality-gate"
    ]
