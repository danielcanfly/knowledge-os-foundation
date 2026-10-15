#!/usr/bin/env python3
"""Stage digest-pinned A04 model assets outside every Git checkout.

This command never downloads assets.  It accepts an operator-authorized local
asset directory, verifies the accepted model/archive and license pins, and
creates a new external runtime directory for a clean-checkout replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
MANIFEST_PATH = ROOT / "MODEL_RUNTIME_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: Path, *, size: int, digest: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"REGULAR_FILE_REQUIRED:{path.name}")
    if path.stat().st_size != size:
        raise ValueError(f"SIZE_MISMATCH:{path.name}")
    if sha256(path) != digest:
        raise ValueError(f"SHA256_MISMATCH:{path.name}")


def inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def verify_destination(destination: Path) -> None:
    resolved = destination.resolve(strict=False)
    if inside(resolved, REPO.resolve()):
        raise ValueError("RUNTIME_INSIDE_SOURCE_GIT_TREE")
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise ValueError("RUNTIME_INSIDE_ANY_GIT_TREE")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("DESTINATION_NOT_EMPTY")


def safe_extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        for member in members:
            target = (destination / member.name).resolve(strict=False)
            if not inside(target, root):
                raise ValueError("ARCHIVE_PATH_ESCAPE")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                if link.is_absolute() or not inside(
                    (target.parent / link).resolve(strict=False), root
                ):
                    raise ValueError("ARCHIVE_LINK_ESCAPE")
        package.extractall(destination, members=members)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model-mode", choices=("copy", "hardlink"), default="copy")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    model = manifest["model"]
    llama = manifest["llama_cpp"]
    asset_dir = args.asset_dir.expanduser().resolve()
    destination = args.destination.expanduser()
    verify_destination(destination)

    model_source = asset_dir / model["filename"]
    archive_source = asset_dir / llama["archive_filename"]
    qwen_license = ROOT / model["license_file"]
    require_file(model_source, size=model["bytes"], digest=model["sha256"])
    require_file(
        archive_source,
        size=llama["archive_bytes"],
        digest=llama["archive_sha256"],
    )
    require_file(
        qwen_license,
        size=qwen_license.stat().st_size,
        digest=model["license_sha256"],
    )

    created = not destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        model_target = destination / model["filename"]
        if args.model_mode == "hardlink":
            os.link(model_source, model_target)
        else:
            shutil.copyfile(model_source, model_target)
        safe_extract(archive_source, destination)
        cli = destination / llama["cli"]
        license_path = destination / llama["license_file"]
        require_file(cli, size=llama["cli_bytes"], digest=llama["cli_sha256"])
        require_file(
            license_path,
            size=license_path.stat().st_size,
            digest=llama["license_sha256"],
        )
        if not os.access(cli, os.X_OK):
            raise ValueError("LLAMA_CLI_NOT_EXECUTABLE")
        receipt = {
            "schema": "m27.a04.external-model-runtime-stage/v2",
            "manifest_sha256": sha256(MANIFEST_PATH),
            "scope": manifest["scope"],
            "model_mode": args.model_mode,
            "files": {
                model["filename"]: {
                    "bytes": model_target.stat().st_size,
                    "sha256": sha256(model_target),
                },
                llama["archive_filename"]: {
                    "source_bytes": archive_source.stat().st_size,
                    "source_sha256": sha256(archive_source),
                    "retained_in_runtime": False,
                },
                llama["cli"]: {
                    "bytes": cli.stat().st_size,
                    "sha256": sha256(cli),
                    "executable": True,
                },
                llama["license_file"]: {
                    "bytes": license_path.stat().st_size,
                    "sha256": sha256(license_path),
                    "spdx": llama["license"],
                },
                model["license_file"]: {
                    "bytes": qwen_license.stat().st_size,
                    "sha256": sha256(qwen_license),
                    "spdx": model["license"],
                    "tracked_source_license": True,
                },
            },
            "network_download": False,
            "runtime_outside_git": True,
            "production_authority": False,
            "native_q34": False,
        }
        receipt_path = destination / "STAGE_RECEIPT.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "status": "STAGED",
            "receipt": str(receipt_path),
            "receipt_sha256": sha256(receipt_path),
            "model_sha256": receipt["files"][model["filename"]]["sha256"],
            "archive_sha256": receipt["files"][llama["archive_filename"]]["source_sha256"],
            "cli_sha256": receipt["files"][llama["cli"]]["sha256"],
        }, sort_keys=True))
        return 0
    except Exception:
        if created and destination.exists():
            shutil.rmtree(destination)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
