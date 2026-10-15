"""Deterministic, unsigned, content-only B02 OCI-layout candidate builder."""
from __future__ import annotations

import hashlib
import io
import json
import platform
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from wave_b02.authority import B01_HEAD, B01_TREE, REPO, sha256_file


def _git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(REPO), "show", f"{B01_HEAD}:{path}"])


def source_paths() -> list[str]:
    raw = subprocess.check_output(
        ["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", B01_HEAD, "wave_b01"],
        text=True,
    )
    selected = []
    for path in raw.splitlines():
        if "/evidence/" in path or path.endswith(".pyc"):
            continue
        if path.startswith(("wave_b01/components/", "wave_b01/interfaces/", "wave_b01/evidence_inputs/")) \
                or path in {
                    "wave_b01/__init__.py", "wave_b01/integration.py",
                    "wave_b01/test_integration.py", "wave_b01/CANDIDATE_MANIFEST_V2.json",
                }:
            selected.append(path)
    if not selected:
        raise RuntimeError("EMPTY_B01_SOURCE_SELECTION")
    return sorted(selected)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def host_architecture() -> str:
    value = platform.machine().lower()
    return {"aarch64": "arm64", "x86_64": "amd64"}.get(value, value)


def validate_architecture(candidate_arch: str, expected_arch: str | None = None) -> None:
    expected = expected_arch or host_architecture()
    if candidate_arch != expected:
        raise ValueError(f"OCI_ARCH_MISMATCH:{candidate_arch}!={expected}")


def build_candidate(destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    blobs = destination / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    paths = source_paths()
    file_hashes = []
    layer_io = io.BytesIO()
    with tarfile.open(fileobj=layer_io, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in paths:
            data = _git_bytes(path)
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
            file_hashes.append({"path": path, "sha256": _digest(data), "bytes": len(data)})
    layer = layer_io.getvalue()
    layer_sha = _digest(layer)
    (blobs / layer_sha).write_bytes(layer)

    architecture = host_architecture()
    config = _json_bytes({
        "architecture": architecture,
        "os": "darwin",
        "rootfs": {"type": "layers", "diff_ids": [f"sha256:{layer_sha}"]},
        "config": {"Labels": {
            "m27.scope": "UNSIGNED_NONPROD_CONTENT_ONLY",
            "m27.runnable": "false",
            "m27.source.head": B01_HEAD,
            "m27.source.tree": B01_TREE,
        }},
    })
    config_sha = _digest(config)
    (blobs / config_sha).write_bytes(config)
    manifest = _json_bytes({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                   "digest": f"sha256:{config_sha}", "size": len(config)},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar",
                    "digest": f"sha256:{layer_sha}", "size": len(layer)}],
        "annotations": {"m27.classification": "NOT_SIGNED_RUNNABLE_PRODUCT"},
    })
    manifest_sha = _digest(manifest)
    (blobs / manifest_sha).write_bytes(manifest)
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": f"sha256:{manifest_sha}", "size": len(manifest),
            "platform": {"architecture": architecture, "os": "darwin"},
            "annotations": {"org.opencontainers.image.ref.name": "b02-content-only"},
        }],
    }
    (destination / "oci-layout").write_text(
        json.dumps({"imageLayoutVersion": "1.0.0"}, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_architecture(architecture)
    return {
        "schema": "m27.wave-b02.nonprod-candidate-manifest/v1",
        "classification": "UNSIGNED_NONPROD_CONTENT_ONLY",
        "signed_runnable_product": False,
        "deployable": False,
        "sole_source": {"head": B01_HEAD, "tree": B01_TREE},
        "platform": {"os": "darwin", "architecture": architecture},
        "source_file_count": len(file_hashes),
        "source_files": file_hashes,
        "oci_content": {
            "layout_path": str(destination),
            "layer_sha256": layer_sha,
            "config_sha256": config_sha,
            "manifest_sha256": manifest_sha,
            "index_sha256": sha256_file(destination / "index.json"),
        },
    }
