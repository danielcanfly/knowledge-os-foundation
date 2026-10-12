#!/usr/bin/env python3
"""Prepare isolated build from P28's Git-proven T27 source plus explicit P28R delta."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

T27 = "8604752934fb43a3441055d33c01940028cc5938"
P28 = "b90ff73399f4ff187c3a5a8a7327ec57e117cbe1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--p28r", required=True, type=Path)
    p.add_argument("--p28", required=True, type=Path)
    p.add_argument("--t27", required=True, type=Path)
    p.add_argument("--original-context", required=True, type=Path)
    p.add_argument("--original-manifest", required=True, type=Path)
    p.add_argument("--output-context", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args()
    for root, head in ((a.p28, P28), (a.t27, T27)):
        got = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        if got != head:
            raise ValueError(f"REJECT wrong original ancestry {got} != {head}")
    if a.output_context.exists():
        raise ValueError("REJECT existing build context: do not overwrite")
    # Run P28's full 857-byte-identity verifier before staging, with original T27 Git authority.
    subprocess.run(
        [
            "python3.11",
            str(a.p28 / "scripts/p28_nonprod_source_chain.py"),
            "--source",
            str(a.t27),
            "--context",
            str(a.original_context),
            "--manifest",
            str(a.original_manifest),
            "--verify-only",
        ],
        check=True,
    )
    shutil.copytree(a.original_context, a.output_context, symlinks=False)
    healthfile = "src/knowledge_engine/p28r_local_healthcheck.py"
    overlay = {
        healthfile: a.p28r / healthfile,
        "Dockerfile": a.p28r / "docker/nonprod/Dockerfile.p28r",
    }
    for rel, src in overlay.items():
        dest = a.output_context / rel
        if rel == healthfile and dest.exists():
            raise ValueError("REJECT would overwrite original T27 code")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    old = json.loads(a.original_manifest.read_text())
    actual = {}
    for rel, src in overlay.items():
        actual[rel] = {"bytes": src.stat().st_size, "sha256": sha256(src.read_bytes())}
    inventory = {
        "schema": "P28R_LOCAL_SOURCE_PLUS_NONPROD_DOCKER_RECIPE_V1",
        "t27_git_head": T27,
        "t27_git_tree": "123578f9e1059d1b554fc3fdc011bdc171033afd",
        "p28_parent": P28,
        "original_t27_source_count": old["scoped_source_file_count"],
        "original_t27_source_bytes": old["scoped_source_bytes"],
        "original_source_manifest_sha256": old["scoped_manifest_sha256"],
        "original_source_manifest_file_sha256": sha256(a.original_manifest.read_bytes()),
        "p28r_overlay": actual,
        "source_plus_overlay_provenance": "local Git bytes, not signed external OCI",
    }
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print(json.dumps(inventory, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
