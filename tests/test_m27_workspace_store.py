from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from knowledge_engine.m27_workspace_contracts import (
    UnsafeWorkspacePathError,
    WorkspaceArtifactKind,
    WorkspaceId,
    WorkspaceScope,
)
from knowledge_engine.m27_workspace_store import (
    WorkspaceArtifactExistsError,
    WorkspaceStore,
)


def _workspace_id() -> WorkspaceId:
    return WorkspaceId.from_safe_token(
        scope=WorkspaceScope.TASK,
        task_token="task:stage8:test-fixture",
    )


def _store(tmp_path: Path) -> tuple[WorkspaceStore, WorkspaceId]:
    store = WorkspaceStore(root=tmp_path / "isolated")
    workspace_id = _workspace_id()
    store.create_workspace(workspace_id=workspace_id, scope=WorkspaceScope.TASK)
    return store, workspace_id


def test_store_uses_injected_root_only(tmp_path: Path) -> None:
    root = tmp_path / "custom-workspace-root"
    store = WorkspaceStore(root=root)

    assert store.root == root.resolve()
    assert store.root.is_dir()


def test_json_artifact_roundtrip_and_manifest_metadata_only(tmp_path: Path) -> None:
    store, workspace_id = _store(tmp_path)
    payload = {
        "status_code": "EVAL_OK",
        "counts": {"passed": 523, "failed": 0},
        "candidate_ids": ["candidate-a"],
    }

    ref = store.write_json_artifact(
        workspace_id=workspace_id,
        kind=WorkspaceArtifactKind.EVAL_SUMMARY,
        relative_path="eval/summary.json",
        payload=payload,
    )

    assert store.read_json_artifact(ref) == payload
    assert store.list_artifacts(workspace_id) == (ref,)

    manifest = store.describe_workspace(workspace_id)
    assert manifest.artifact_count == 1
    assert manifest.checkpoint_count == 0
    assert manifest.artifacts == (ref,)

    manifest_path = (
        store.root / workspace_id.value / ".m27" / "manifest.json"
    )
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_json = json.loads(manifest_text)
    assert "EVAL_OK" not in manifest_text
    assert "candidate-a" not in manifest_text
    assert "counts" not in manifest_json
    assert set(manifest_json) == {
        "schema_version",
        "workspace_id",
        "scope",
        "write_policy",
        "artifact_count",
        "checkpoint_count",
        "artifacts",
    }


def test_text_artifact_roundtrip(tmp_path: Path) -> None:
    store, workspace_id = _store(tmp_path)
    text = "Gate status: PASS\nCandidate action: review-only\n"

    ref = store.write_text_artifact(
        workspace_id=workspace_id,
        kind=WorkspaceArtifactKind.REPORT,
        relative_path="reports/gate-report.txt",
        text=text,
    )

    assert store.read_text_artifact(ref) == text
    assert ref.relative_path == "reports/gate-report.txt"
    assert ref.kind is WorkspaceArtifactKind.REPORT


def test_artifact_paths_are_immutable(tmp_path: Path) -> None:
    store, workspace_id = _store(tmp_path)

    store.write_text_artifact(
        workspace_id=workspace_id,
        kind=WorkspaceArtifactKind.REPORT,
        relative_path="reports/same.txt",
        text="first",
    )

    with pytest.raises(WorkspaceArtifactExistsError):
        store.write_text_artifact(
            workspace_id=workspace_id,
            kind=WorkspaceArtifactKind.REPORT,
            relative_path="reports/same.txt",
            text="second",
        )


def test_checkpoint_append_and_list(tmp_path: Path) -> None:
    store, workspace_id = _store(tmp_path)

    first = store.record_checkpoint(
        workspace_id=workspace_id,
        checkpoint_id="retrieval-gate",
        metadata={"status_code": "PASS", "round": 1},
    )
    second = store.record_checkpoint(
        workspace_id=workspace_id,
        checkpoint_id="verification-gate",
        metadata={"status_code": "PASS", "round": 2},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert store.list_checkpoints(workspace_id) == (first, second)
    assert store.describe_workspace(workspace_id).checkpoint_count == 2


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    store, workspace_id = _store(tmp_path)
    workspace_dir = store.root / workspace_id.value
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace_dir / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeWorkspacePathError):
        store.write_text_artifact(
            workspace_id=workspace_id,
            kind=WorkspaceArtifactKind.REPORT,
            relative_path="escape/leak.txt",
            text="sanitized",
        )

    assert not (outside / "leak.txt").exists()


def test_absolute_and_traversal_paths_are_rejected_before_write(tmp_path: Path) -> None:
    store, workspace_id = _store(tmp_path)

    for relative_path in ("../escape.txt", "/tmp/escape.txt", "~/escape.txt"):
        with pytest.raises(UnsafeWorkspacePathError):
            store.write_text_artifact(
                workspace_id=workspace_id,
                kind=WorkspaceArtifactKind.REPORT,
                relative_path=relative_path,
                text="sanitized",
            )


def test_workspace_modules_have_no_stage7_mcp_or_memory_import_dependency() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
    files = (
        root / "m27_workspace_contracts.py",
        root / "m27_workspace_store.py",
    )

    imported_modules: set[str] = set()
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    forbidden_fragments = (
        "m27_skill_contracts",
        "mcp",
        "memory",
        "qdrant",
        "r2",
        "sqlite",
        "production_promotion",
    )
    assert all(
        fragment not in module
        for module in imported_modules
        for fragment in forbidden_fragments
    )


def test_store_surface_has_no_execution_or_release_authority(tmp_path: Path) -> None:
    store = WorkspaceStore(root=tmp_path / "isolated")

    for name in (
        "execute",
        "invoke",
        "run_skill",
        "promote",
        "rollback",
        "finalize",
        "write_r2",
        "write_qdrant",
        "write_sqlite",
    ):
        assert not hasattr(store, name)
