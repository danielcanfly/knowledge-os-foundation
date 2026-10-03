from __future__ import annotations

import ast
from pathlib import Path

import pytest

from knowledge_engine.m27_meta_harness_contracts import (
    MetaHarnessCandidateKind,
    MetaHarnessCandidateStatus,
    MetaHarnessInput,
    MetaHarnessRiskClass,
    UnsafeMetaHarnessPayloadError,
)
from knowledge_engine.m27_meta_harness_runtime import (
    InvalidMetaHarnessTransitionError,
    MetaHarnessCandidateStore,
    MetaHarnessRuntime,
    MetaHarnessRuntimeError,
    UnknownMetaHarnessCandidateError,
)

_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_SOURCE = _ROOT / "src/knowledge_engine/m27_meta_harness_runtime.py"
_CONTRACT_SOURCE = _ROOT / "src/knowledge_engine/m27_meta_harness_contracts.py"

_FORBIDDEN_METHOD_NAMES = {
    "apply_patch",
    "auto_apply_patch",
    "merge_branch",
    "auto_merge",
    "promote_release",
    "auto_promote",
    "write_runtime_config",
    "patch_code",
    "write_to_qdrant",
    "write_to_r2",
    "write_to_production_sqlite",
    "execute_skill",
    "invoke_mcp",
    "write_workspace",
    "start_agent_loop",
    "apply_learning_proposal",
}


def _input(
    failure_class: str = "REPEATED_CITATION_GAP",
) -> MetaHarnessInput:
    return MetaHarnessInput.create(
        source_refs=("learn-opaque-a", "trace-opaque-a"),
        target_failure_class=failure_class,
        reason_codes=("OFFLINE_GATE_REQUIRED",),
        artifact_ids=("artifact-opaque-a",),
        eval_summary_count=20,
        gate_summary_count=2,
    )


def _kwargs(
    failure_class: str = "REPEATED_CITATION_GAP",
) -> dict[str, object]:
    return {
        "input_metadata": _input(failure_class),
        "candidate_summary": "Draft bounded candidate metadata for offline review.",
        "expected_improvement_class": "FAILURE_CLASS_REDUCTION",
        "risk_class": MetaHarnessRiskClass.MEDIUM,
        "candidate_files": (
            "src/knowledge_engine/candidate_module.py",
            "tests/test_candidate_module.py",
        ),
        "test_names": ("candidate.contracts", "candidate.regression"),
        "gate_names": ("offline.contracts", "offline.regression"),
    }


def test_draft_harness_plan_is_candidate_only() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    assert candidate.kind is MetaHarnessCandidateKind.HARNESS_PLAN
    assert candidate.status is MetaHarnessCandidateStatus.PROPOSED
    assert candidate.candidate_only is True
    assert candidate.requires_human_review is True
    assert candidate.requires_offline_gate is True
    assert candidate.auto_apply is False
    assert candidate.auto_merge is False
    assert candidate.auto_promote is False
    assert candidate.production_write is False


def test_draft_patch_intent_is_metadata_only() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_patch_intent(**_kwargs())
    assert candidate.kind is MetaHarnessCandidateKind.PATCH_INTENT
    assert candidate.candidate_files
    assert not hasattr(candidate, "patch")
    assert not hasattr(candidate, "diff")
    assert not hasattr(candidate, "patch_content")


def test_draft_eval_plan_does_not_execute() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_eval_plan(**_kwargs())
    assert candidate.kind is MetaHarnessCandidateKind.EVAL_PLAN
    assert candidate.test_names == ("candidate.contracts", "candidate.regression")
    assert tuple(item.gate_name for item in candidate.gate_requirements) == (
        "offline.contracts",
        "offline.regression",
    )


@pytest.mark.parametrize(
    "kind",
    (
        MetaHarnessCandidateKind.TEST_PLAN,
        MetaHarnessCandidateKind.VALIDATION_REPORT,
        MetaHarnessCandidateKind.PROMOTION_PROPOSAL,
        MetaHarnessCandidateKind.ROLLBACK_PLAN,
        MetaHarnessCandidateKind.RISK_MATRIX,
    ),
)
def test_record_candidate_report_supports_remaining_candidate_kinds(
    kind: MetaHarnessCandidateKind,
) -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.record_candidate_report(kind=kind, **_kwargs())
    assert candidate.kind is kind
    assert candidate.candidate_only is True
    assert candidate.production_write is False


@pytest.mark.parametrize(
    "kind",
    (
        MetaHarnessCandidateKind.HARNESS_PLAN,
        MetaHarnessCandidateKind.PATCH_INTENT,
        MetaHarnessCandidateKind.EVAL_PLAN,
    ),
)
def test_record_candidate_report_rejects_draft_specific_kinds(
    kind: MetaHarnessCandidateKind,
) -> None:
    runtime = MetaHarnessRuntime()
    with pytest.raises(MetaHarnessRuntimeError):
        runtime.record_candidate_report(kind=kind, **_kwargs())


def test_candidate_lifecycle_proposed_to_ready_for_review() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    ready = runtime.mark_candidate_ready_for_review(candidate.candidate_id)
    assert ready.status is MetaHarnessCandidateStatus.READY_FOR_REVIEW
    assert ready.active is True
    assert ready.candidate_id == candidate.candidate_id


def test_ready_for_review_is_idempotent() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    first = runtime.mark_candidate_ready_for_review(candidate.candidate_id)
    second = runtime.mark_candidate_ready_for_review(candidate.candidate_id)
    assert second == first


def test_rejected_candidate_cannot_return_to_ready_for_review() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    rejected = runtime.mark_candidate_rejected(candidate.candidate_id)
    assert rejected.status is MetaHarnessCandidateStatus.REJECTED
    assert rejected.active is False
    with pytest.raises(InvalidMetaHarnessTransitionError):
        runtime.mark_candidate_ready_for_review(candidate.candidate_id)


def test_superseded_candidate_is_inactive_and_terminal() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    superseded = runtime.mark_candidate_superseded(candidate.candidate_id)
    assert superseded.status is MetaHarnessCandidateStatus.SUPERSEDED
    assert superseded.active is False
    with pytest.raises(InvalidMetaHarnessTransitionError):
        runtime.mark_candidate_rejected(candidate.candidate_id)


def test_ready_candidate_can_be_rejected() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    runtime.mark_candidate_ready_for_review(candidate.candidate_id)
    rejected = runtime.mark_candidate_rejected(candidate.candidate_id)
    assert rejected.status is MetaHarnessCandidateStatus.REJECTED
    assert rejected.active is False


def test_ready_candidate_can_be_superseded() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    runtime.mark_candidate_ready_for_review(candidate.candidate_id)
    superseded = runtime.mark_candidate_superseded(candidate.candidate_id)
    assert superseded.status is MetaHarnessCandidateStatus.SUPERSEDED
    assert superseded.active is False


def test_list_candidates_is_deterministic_and_sorted() -> None:
    runtime = MetaHarnessRuntime()
    candidates = [
        runtime.draft_harness_plan(**_kwargs("Z_FAILURE")),
        runtime.draft_patch_intent(**_kwargs("A_FAILURE")),
        runtime.draft_eval_plan(**_kwargs("M_FAILURE")),
    ]
    listed = runtime.list_candidates()
    assert [item.candidate_id for item in listed] == sorted(
        item.candidate_id for item in candidates
    )


def test_list_candidates_can_filter_active_only() -> None:
    runtime = MetaHarnessRuntime()
    active = runtime.draft_harness_plan(**_kwargs("ACTIVE_FAILURE"))
    rejected = runtime.draft_patch_intent(**_kwargs("REJECTED_FAILURE"))
    runtime.mark_candidate_rejected(rejected.candidate_id)
    assert runtime.list_candidates(active_only=True) == (active,)


def test_list_candidates_can_filter_kind_and_status() -> None:
    runtime = MetaHarnessRuntime()
    harness = runtime.draft_harness_plan(**_kwargs("HARNESS_FAILURE"))
    runtime.draft_patch_intent(**_kwargs("PATCH_FAILURE"))
    assert runtime.list_candidates(kind=MetaHarnessCandidateKind.HARNESS_PLAN) == (harness,)
    assert (
        runtime.list_candidates(status=MetaHarnessCandidateStatus.PROPOSED)
        == runtime.list_candidates()
    )


def test_candidate_store_is_in_memory_and_idempotent() -> None:
    store = MetaHarnessCandidateStore()
    runtime = MetaHarnessRuntime(candidate_store=store)
    first = runtime.draft_harness_plan(**_kwargs())
    second = runtime.draft_harness_plan(**_kwargs())
    assert first == second
    assert len(store) == 1
    assert not hasattr(store, "root")
    assert not hasattr(store, "path")
    assert not hasattr(store, "persist")


def test_unknown_candidate_fails_closed() -> None:
    runtime = MetaHarnessRuntime()
    with pytest.raises(UnknownMetaHarnessCandidateError):
        runtime.inspect_candidate("mhc-" + ("0" * 32))


def test_candidate_report_contains_sanitized_metadata_only() -> None:
    runtime = MetaHarnessRuntime()
    candidate = runtime.draft_harness_plan(**_kwargs())
    report = runtime.render_meta_harness_report(candidate.candidate_id)
    assert report["supporting_source_refs"] == [
        "learn-opaque-a",
        "trace-opaque-a",
    ]
    assert report["supporting_artifact_ids"] == ["artifact-opaque-a"]
    assert report["governance"] == {
        "candidate_only": True,
        "requires_human_review": True,
        "requires_offline_gate": True,
        "auto_apply": False,
        "auto_merge": False,
        "auto_promote": False,
        "production_write": False,
        "runtime_behavior_change": False,
        "execution_authority": False,
    }
    forbidden_keys = {
        "raw_query",
        "raw_answer",
        "full_evidence_body",
        "full_source_body",
        "provider_prompt",
        "secret",
        "credential",
        "api_key",
        "auth_token",
        "environment",
        "production_path",
        "release_pointer",
        "private_payload",
    }
    assert not forbidden_keys.intersection(_all_mapping_keys(report))


def test_raw_payload_is_rejected_before_runtime_registration() -> None:
    runtime = MetaHarnessRuntime()
    kwargs = _kwargs()
    kwargs["candidate_summary"] = "raw_query: do not retain this"
    with pytest.raises(UnsafeMetaHarnessPayloadError):
        runtime.draft_harness_plan(**kwargs)
    assert runtime.list_candidates() == ()


def test_runtime_has_no_forbidden_authority_api() -> None:
    for name in _FORBIDDEN_METHOD_NAMES:
        assert not hasattr(MetaHarnessRuntime, name), name
        assert not hasattr(MetaHarnessCandidateStore, name), name


def test_stage12_modules_have_no_forbidden_integration_imports() -> None:
    forbidden_fragments = {
        "m27_skill",
        "m27_workspace",
        "m27_mcp",
        "m27_memory",
        "m27_learning",
        "qdrant",
        "boto",
        "sqlite",
        "requests",
        "httpx",
    }
    for path in (_CONTRACT_SOURCE, _RUNTIME_SOURCE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = _import_names(tree)
        assert not any(
            fragment in imported for fragment in forbidden_fragments for imported in imports
        ), (path, imports)


def test_stage12_modules_have_no_filesystem_or_process_imports() -> None:
    forbidden = {
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "shutil",
        "tempfile",
    }
    for path in (_CONTRACT_SOURCE, _RUNTIME_SOURCE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert forbidden.isdisjoint(_import_names(tree))


def test_existing_m27_source_does_not_import_stage12() -> None:
    source_dir = _ROOT / "src/knowledge_engine"
    for path in source_dir.glob("m27_*.py"):
        if path.name.startswith("m27_meta_harness"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "m27_meta_harness" not in text, path


def test_stage9_mcp_surface_does_not_expose_stage12() -> None:
    for name in ("m27_mcp_contracts.py", "m27_mcp_exposure.py"):
        text = (_ROOT / "src/knowledge_engine" / name).read_text(encoding="utf-8")
        assert "meta_harness" not in text
        assert "candidate_harness" not in text


def test_stage12_does_not_execute_stage7_or_promote_memory_or_learning() -> None:
    source = _RUNTIME_SOURCE.read_text(encoding="utf-8")
    assert "execute_skill" not in source
    assert "write_workspace" not in source
    assert "invoke_mcp" not in source
    assert "promote_to_knowledge" not in source
    assert "apply_learning_proposal" not in source


def _all_mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_all_mapping_keys(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            keys.update(_all_mapping_keys(nested))
    return keys


def _import_names(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
