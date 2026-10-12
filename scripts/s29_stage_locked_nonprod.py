"""Stage only immutable Git bytes and independently hashed offline wheel assets.

Deliberately refuses dirty source and never reads Production release/Provider keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from s29_verify_locked_wheels import verify


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if git(repo, "status", "--porcelain"):
        raise SystemExit("SOURCE_NOT_CLEAN")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").decode().strip()
    if not args.dest.exists():
        args.dest.mkdir(parents=True)
    elif any(args.dest.iterdir()):
        raise SystemExit("DEST_MUST_BE_EMPTY")

    paths = git(repo, "ls-files", "-z", "--", "src", "pilot", "pyproject.toml",
                "README.md", "docker/nonprod/Dockerfile.s29",
                "docker/nonprod/requirements-s29-linux-arm64.lock.txt",
                "docker/nonprod/build-backend-s29-linux-arm64.lock.txt",
                "scripts/s29_verify_locked_wheels.py").split(b"\0")
    files = []
    for encoded in paths:
        if not encoded:
            continue
        rel = encoded.decode("utf-8")
        b = git(repo, "show", f"{head}:{rel}")
        if (repo / rel).read_bytes() != b:
            raise SystemExit(f"DIRTY_GIT_SOURCE: {rel}")
        dest = args.dest / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b)
        files.append({"path": rel, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)})
    assert len(files) > 500, "too few source files"
    lock1 = repo / "docker/nonprod/requirements-s29-linux-arm64.lock.txt"
    lock2 = repo / "docker/nonprod/build-backend-s29-linux-arm64.lock.txt"
    witness = verify(args.wheelhouse, [lock1, lock2], repo)
    wh = args.dest / "wheelhouse"
    wh.mkdir()
    for record in witness["wheels"].values():
        name = record["wheel"]
        shutil.copyfile(args.wheelhouse / name, wh / name)
    manifest = {"schema": "S29_SOURCE_WHEEL_CHAIN_V1", "git_head": head, "git_tree": tree,
                "tracked_source_count": len(files), "tracked_source": files,
                "wheel_count": witness["wheel_count"],
                "project_source_members_verified": witness["tracked_package_source_files_equal"]}
    (args.dest / "S29_STAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "tracked_source"}))


if __name__ == "__main__":
    main()
