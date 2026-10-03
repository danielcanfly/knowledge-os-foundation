from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

from .m27_workspace_contracts import (
    STAGE8_WRITE_POLICY,
    WORKSPACE_SCHEMA_VERSION,
    UnsafeWorkspacePathError,
    WorkspaceArtifactFormat,
    WorkspaceArtifactKind,
    WorkspaceArtifactRef,
    WorkspaceCheckpoint,
    WorkspaceContractError,
    WorkspaceId,
    WorkspaceManifest,
    WorkspaceScope,
    WorkspaceWritePolicy,
    artifact_kind_from_value,
    validate_relative_artifact_path,
    validate_safe_identifier,
    validate_sanitized_json_payload,
    validate_sanitized_text,
)

_METADATA_DIR = ".m27"
_MANIFEST_FILE = "manifest.json"
_CHECKPOINT_DIR = "checkpoints"


class WorkspaceStoreError(RuntimeError):
    """Base error for isolated Stage 8 store failures."""


class WorkspaceAlreadyExistsError(WorkspaceStoreError):
    """Raised when create_workspace targets an existing workspace."""


class WorkspaceNotFoundError(WorkspaceStoreError):
    """Raised when a workspace does not exist."""


class WorkspaceArtifactExistsError(WorkspaceStoreError):
    """Raised because Stage 8 artifact writes are immutable."""


class WorkspaceIntegrityError(WorkspaceStoreError):
    """Raised when on-disk data does not match its sanitized manifest."""


class WorkspaceStore:
    """Filesystem-backed isolated task workspace.

    The injected root is the only filesystem authority this store receives.
    Public artifact references are workspace-relative and immutable. This class
    has no production backend, network, release, skill, or answer-path surface.
    """

    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path):
            raise WorkspaceStoreError("workspace root must be pathlib.Path")
        if root.exists() and root.is_symlink():
            raise UnsafeWorkspacePathError("workspace root cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve()
        if not self._root.is_dir():
            raise WorkspaceStoreError("workspace root must be a directory")

    @property
    def root(self) -> Path:
        return self._root

    def create_workspace(
        self,
        *,
        workspace_id: WorkspaceId,
        scope: WorkspaceScope,
    ) -> WorkspaceManifest:
        self._require_workspace_id(workspace_id)
        if not isinstance(scope, WorkspaceScope):
            raise WorkspaceContractError("scope must be WorkspaceScope")
        workspace_dir = self._root / workspace_id.value
        if workspace_dir.exists() or workspace_dir.is_symlink():
            raise WorkspaceAlreadyExistsError(
                f"workspace already exists: {workspace_id.value}"
            )
        workspace_dir.mkdir(mode=0o700)
        self._assert_contained(workspace_dir, self._root)
        metadata_dir = workspace_dir / _METADATA_DIR
        metadata_dir.mkdir(mode=0o700)
        (metadata_dir / _CHECKPOINT_DIR).mkdir(mode=0o700)
        manifest = WorkspaceManifest(workspace_id=workspace_id, scope=scope)
        self._persist_manifest(manifest)
        return manifest

    def describe_workspace(self, workspace_id: WorkspaceId) -> WorkspaceManifest:
        workspace_dir = self._require_workspace_dir(workspace_id)
        manifest_path = workspace_dir / _METADATA_DIR / _MANIFEST_FILE
        self._reject_symlink_chain(manifest_path, workspace_dir)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise WorkspaceIntegrityError("workspace manifest is missing") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceIntegrityError("workspace manifest is unreadable") from exc
        return self._manifest_from_dict(payload, expected_workspace_id=workspace_id)

    def write_json_artifact(
        self,
        *,
        workspace_id: WorkspaceId,
        kind: WorkspaceArtifactKind | str,
        relative_path: str,
        payload: object,
    ) -> WorkspaceArtifactRef:
        validate_sanitized_json_payload(payload)
        data = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return self._write_artifact(
            workspace_id=workspace_id,
            kind=artifact_kind_from_value(kind),
            artifact_format=WorkspaceArtifactFormat.JSON,
            relative_path=relative_path,
            data=data,
        )

    def read_json_artifact(self, ref: WorkspaceArtifactRef) -> object:
        data = self._read_artifact(ref, expected_format=WorkspaceArtifactFormat.JSON)
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceIntegrityError("registered JSON artifact is invalid") from exc
        validate_sanitized_json_payload(payload)
        return payload

    def write_text_artifact(
        self,
        *,
        workspace_id: WorkspaceId,
        kind: WorkspaceArtifactKind | str,
        relative_path: str,
        text: str,
    ) -> WorkspaceArtifactRef:
        validate_sanitized_text(text)
        return self._write_artifact(
            workspace_id=workspace_id,
            kind=artifact_kind_from_value(kind),
            artifact_format=WorkspaceArtifactFormat.TEXT,
            relative_path=relative_path,
            data=text.encode("utf-8"),
        )

    def read_text_artifact(self, ref: WorkspaceArtifactRef) -> str:
        data = self._read_artifact(ref, expected_format=WorkspaceArtifactFormat.TEXT)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceIntegrityError("registered text artifact is not UTF-8") from exc
        validate_sanitized_text(text)
        return text

    def list_artifacts(self, workspace_id: WorkspaceId) -> tuple[WorkspaceArtifactRef, ...]:
        return self.describe_workspace(workspace_id).artifacts

    def record_checkpoint(
        self,
        *,
        workspace_id: WorkspaceId,
        checkpoint_id: str,
        metadata: dict[str, object],
    ) -> WorkspaceCheckpoint:
        validate_safe_identifier("checkpoint_id", checkpoint_id)
        validate_sanitized_json_payload(metadata)
        manifest = self.describe_workspace(workspace_id)
        sequence = manifest.checkpoint_count + 1
        safe_copy = json.loads(
            json.dumps(
                metadata,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
        checkpoint = WorkspaceCheckpoint(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            sequence=sequence,
            metadata=safe_copy,
        )
        workspace_dir = self._require_workspace_dir(workspace_id)
        checkpoint_dir = workspace_dir / _METADATA_DIR / _CHECKPOINT_DIR
        self._reject_symlink_chain(checkpoint_dir, workspace_dir)
        checkpoint_path = checkpoint_dir / f"{sequence:06d}-{checkpoint_id}.json"
        self._assert_contained(checkpoint_path, workspace_dir)
        encoded = json.dumps(
            checkpoint.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self._write_exclusive(checkpoint_path, encoded)
        try:
            updated = replace(
                manifest,
                checkpoint_count=manifest.checkpoint_count + 1,
            )
            self._persist_manifest(updated)
        except Exception:
            checkpoint_path.unlink(missing_ok=True)
            raise
        return checkpoint

    def list_checkpoints(self, workspace_id: WorkspaceId) -> tuple[WorkspaceCheckpoint, ...]:
        manifest = self.describe_workspace(workspace_id)
        workspace_dir = self._require_workspace_dir(workspace_id)
        checkpoint_dir = workspace_dir / _METADATA_DIR / _CHECKPOINT_DIR
        self._reject_symlink_chain(checkpoint_dir, workspace_dir)
        items: list[WorkspaceCheckpoint] = []
        try:
            paths = sorted(checkpoint_dir.glob("*.json"))
        except OSError as exc:
            raise WorkspaceIntegrityError("cannot list checkpoints") from exc
        for path in paths:
            if path.is_symlink():
                raise UnsafeWorkspacePathError("checkpoint file cannot be a symlink")
            self._assert_contained(path, workspace_dir)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise WorkspaceIntegrityError("checkpoint file is unreadable") from exc
            items.append(self._checkpoint_from_dict(payload, workspace_id))
        items.sort(key=lambda item: item.sequence)
        if len(items) != manifest.checkpoint_count:
            raise WorkspaceIntegrityError(
                "checkpoint count does not match workspace manifest"
            )
        if [item.sequence for item in items] != list(range(1, len(items) + 1)):
            raise WorkspaceIntegrityError("checkpoint sequence is not contiguous")
        return tuple(items)

    def _write_artifact(
        self,
        *,
        workspace_id: WorkspaceId,
        kind: WorkspaceArtifactKind,
        artifact_format: WorkspaceArtifactFormat,
        relative_path: str,
        data: bytes,
    ) -> WorkspaceArtifactRef:
        manifest = self.describe_workspace(workspace_id)
        normalized_path = validate_relative_artifact_path(relative_path)
        workspace_dir = self._require_workspace_dir(workspace_id)
        target = self._artifact_target(
            workspace_dir=workspace_dir,
            relative_path=normalized_path,
            create_parents=True,
        )
        self._write_exclusive(target, data)
        ref = WorkspaceArtifactRef(
            workspace_id=workspace_id,
            kind=kind,
            format=artifact_format,
            relative_path=normalized_path,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )
        try:
            updated = replace(
                manifest,
                artifacts=manifest.artifacts + (ref,),
                artifact_count=manifest.artifact_count + 1,
            )
            self._persist_manifest(updated)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return ref

    def _read_artifact(
        self,
        ref: WorkspaceArtifactRef,
        *,
        expected_format: WorkspaceArtifactFormat,
    ) -> bytes:
        if not isinstance(ref, WorkspaceArtifactRef):
            raise WorkspaceContractError("artifact ref must be WorkspaceArtifactRef")
        if ref.format is not expected_format:
            raise WorkspaceContractError(
                f"artifact format is {ref.format.value}, expected {expected_format.value}"
            )
        manifest = self.describe_workspace(ref.workspace_id)
        if ref not in manifest.artifacts:
            raise WorkspaceIntegrityError("artifact ref is not registered in manifest")
        workspace_dir = self._require_workspace_dir(ref.workspace_id)
        target = self._artifact_target(
            workspace_dir=workspace_dir,
            relative_path=ref.relative_path,
            create_parents=False,
        )
        if target.is_symlink():
            raise UnsafeWorkspacePathError("artifact file cannot be a symlink")
        try:
            data = target.read_bytes()
        except FileNotFoundError as exc:
            raise WorkspaceIntegrityError("registered artifact is missing") from exc
        except OSError as exc:
            raise WorkspaceIntegrityError("registered artifact cannot be read") from exc
        if len(data) != ref.size_bytes:
            raise WorkspaceIntegrityError("artifact size does not match manifest")
        if hashlib.sha256(data).hexdigest() != ref.sha256:
            raise WorkspaceIntegrityError("artifact digest does not match manifest")
        return data

    def _artifact_target(
        self,
        *,
        workspace_dir: Path,
        relative_path: str,
        create_parents: bool,
    ) -> Path:
        validate_relative_artifact_path(relative_path)
        target = workspace_dir.joinpath(*relative_path.split("/"))
        parent = target.parent
        if create_parents:
            self._make_safe_parents(parent=parent, workspace_dir=workspace_dir)
        self._reject_symlink_chain(parent, workspace_dir)
        if target.is_symlink():
            raise UnsafeWorkspacePathError("artifact target cannot be a symlink")
        self._assert_contained(target, workspace_dir)
        return target

    def _make_safe_parents(self, *, parent: Path, workspace_dir: Path) -> None:
        relative = parent.relative_to(workspace_dir)
        current = workspace_dir
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise UnsafeWorkspacePathError("artifact parent cannot be a symlink")
            if current.exists() and not current.is_dir():
                raise UnsafeWorkspacePathError("artifact parent component is not a directory")
            current.mkdir(mode=0o700, exist_ok=True)
            self._assert_contained(current, workspace_dir)

    def _persist_manifest(self, manifest: WorkspaceManifest) -> None:
        workspace_dir = self._require_workspace_dir(manifest.workspace_id)
        metadata_dir = workspace_dir / _METADATA_DIR
        self._reject_symlink_chain(metadata_dir, workspace_dir)
        manifest_path = metadata_dir / _MANIFEST_FILE
        if manifest_path.is_symlink():
            raise UnsafeWorkspacePathError("manifest cannot be a symlink")
        encoded = json.dumps(
            manifest.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temp_path = metadata_dir / f".{_MANIFEST_FILE}.tmp"
        if temp_path.is_symlink():
            raise UnsafeWorkspacePathError("manifest temp file cannot be a symlink")
        self._assert_contained(temp_path, workspace_dir)
        self._assert_contained(manifest_path, workspace_dir)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(temp_path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        os.replace(temp_path, manifest_path)

    @staticmethod
    def _write_exclusive(path: Path, data: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise WorkspaceArtifactExistsError(
                f"immutable Stage 8 path already exists: {path.name}"
            ) from exc
        except OSError as exc:
            raise WorkspaceStoreError("artifact write failed") from exc
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def _require_workspace_dir(self, workspace_id: WorkspaceId) -> Path:
        self._require_workspace_id(workspace_id)
        workspace_dir = self._root / workspace_id.value
        if workspace_dir.is_symlink():
            raise UnsafeWorkspacePathError("workspace directory cannot be a symlink")
        if not workspace_dir.exists() or not workspace_dir.is_dir():
            raise WorkspaceNotFoundError(f"workspace not found: {workspace_id.value}")
        self._assert_contained(workspace_dir, self._root)
        metadata_dir = workspace_dir / _METADATA_DIR
        if metadata_dir.is_symlink():
            raise UnsafeWorkspacePathError("workspace metadata directory cannot be a symlink")
        return workspace_dir

    @staticmethod
    def _require_workspace_id(workspace_id: WorkspaceId) -> None:
        if not isinstance(workspace_id, WorkspaceId):
            raise WorkspaceContractError("workspace_id must be WorkspaceId")

    @staticmethod
    def _assert_contained(path: Path, base: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(base.resolve())
        except ValueError as exc:
            raise UnsafeWorkspacePathError("path escapes isolated workspace root") from exc

    def _reject_symlink_chain(self, path: Path, workspace_dir: Path) -> None:
        self._assert_contained(path, workspace_dir)
        try:
            relative = path.relative_to(workspace_dir)
        except ValueError as exc:
            raise UnsafeWorkspacePathError("path is outside workspace") from exc
        current = workspace_dir
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise UnsafeWorkspacePathError("symlink traversal is forbidden")
            if not current.exists():
                break

    @staticmethod
    def _manifest_from_dict(
        payload: object,
        *,
        expected_workspace_id: WorkspaceId,
    ) -> WorkspaceManifest:
        if not isinstance(payload, dict):
            raise WorkspaceIntegrityError("manifest must be an object")
        if payload.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
            raise WorkspaceIntegrityError("manifest schema version mismatch")
        try:
            workspace_id = WorkspaceId(str(payload["workspace_id"]))
            scope = WorkspaceScope(str(payload["scope"]))
            raw_policy = payload["write_policy"]
            raw_artifacts = payload["artifacts"]
            artifact_count = payload["artifact_count"]
            checkpoint_count = payload["checkpoint_count"]
        except (KeyError, TypeError, ValueError, WorkspaceContractError) as exc:
            raise WorkspaceIntegrityError("manifest contract is invalid") from exc
        if workspace_id != expected_workspace_id:
            raise WorkspaceIntegrityError("manifest workspace id mismatch")
        if not isinstance(raw_policy, dict):
            raise WorkspaceIntegrityError("manifest write_policy must be an object")
        try:
            policy = WorkspaceWritePolicy(**raw_policy)
        except (TypeError, WorkspaceContractError) as exc:
            raise WorkspaceIntegrityError("manifest write policy is invalid") from exc
        if policy != STAGE8_WRITE_POLICY:
            raise WorkspaceIntegrityError("manifest write policy was widened")
        if not isinstance(raw_artifacts, list):
            raise WorkspaceIntegrityError("manifest artifacts must be a list")
        artifacts = tuple(
            WorkspaceStore._artifact_ref_from_dict(item, workspace_id)
            for item in raw_artifacts
        )
        try:
            return WorkspaceManifest(
                workspace_id=workspace_id,
                scope=scope,
                write_policy=policy,
                artifacts=artifacts,
                artifact_count=artifact_count,
                checkpoint_count=checkpoint_count,
            )
        except WorkspaceContractError as exc:
            raise WorkspaceIntegrityError("manifest values are invalid") from exc

    @staticmethod
    def _artifact_ref_from_dict(
        payload: object,
        workspace_id: WorkspaceId,
    ) -> WorkspaceArtifactRef:
        if not isinstance(payload, dict):
            raise WorkspaceIntegrityError("artifact ref must be an object")
        try:
            embedded_id = WorkspaceId(str(payload["workspace_id"]))
            if embedded_id != workspace_id:
                raise WorkspaceIntegrityError("artifact ref workspace id mismatch")
            return WorkspaceArtifactRef(
                workspace_id=embedded_id,
                kind=artifact_kind_from_value(str(payload["kind"])),
                format=WorkspaceArtifactFormat(str(payload["format"])),
                relative_path=str(payload["relative_path"]),
                sha256=str(payload["sha256"]),
                size_bytes=payload["size_bytes"],
            )
        except (KeyError, TypeError, ValueError, WorkspaceContractError) as exc:
            if isinstance(exc, WorkspaceIntegrityError):
                raise
            raise WorkspaceIntegrityError("artifact ref is invalid") from exc

    @staticmethod
    def _checkpoint_from_dict(
        payload: object,
        workspace_id: WorkspaceId,
    ) -> WorkspaceCheckpoint:
        if not isinstance(payload, dict):
            raise WorkspaceIntegrityError("checkpoint must be an object")
        try:
            embedded_id = WorkspaceId(str(payload["workspace_id"]))
            if embedded_id != workspace_id:
                raise WorkspaceIntegrityError("checkpoint workspace id mismatch")
            metadata = payload["metadata"]
            if not isinstance(metadata, dict):
                raise WorkspaceIntegrityError("checkpoint metadata must be an object")
            return WorkspaceCheckpoint(
                workspace_id=embedded_id,
                checkpoint_id=str(payload["checkpoint_id"]),
                sequence=payload["sequence"],
                metadata=metadata,
            )
        except (KeyError, TypeError, ValueError, WorkspaceContractError) as exc:
            if isinstance(exc, WorkspaceIntegrityError):
                raise
            raise WorkspaceIntegrityError("checkpoint is invalid") from exc


__all__ = [
    "WorkspaceStore",
    "WorkspaceStoreError",
    "WorkspaceAlreadyExistsError",
    "WorkspaceNotFoundError",
    "WorkspaceArtifactExistsError",
    "WorkspaceIntegrityError",
]
