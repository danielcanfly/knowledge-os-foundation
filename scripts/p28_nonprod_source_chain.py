#!/usr/bin/env python3
"""P28 local-only, fail-closed committed-source-to-build-context byte-chain."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

T27_HEAD = "8604752934fb43a3441055d33c01940028cc5938"
T27_TREE = "123578f9e1059d1b554fc3fdc011bdc171033afd"
COPIED_PATHS = ("src", "pilot", "pyproject.toml", "README.md")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--context", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--verify-only", action="store_true")
    a = p.parse_args()
    head = git(a.source, "rev-parse", "HEAD").decode().strip()
    tree = git(a.source, "rev-parse", "HEAD^{tree}").decode().strip()
    if head != T27_HEAD or tree != T27_TREE:
        raise ValueError("REJECT WRONG GIT HEAD/TREE " + head + "/" + tree)
    if git(a.source, "status", "--porcelain").strip():
        raise ValueError("REJECT DIRTY T27 SOURCE")
    paths = [
        x.decode() for x in git(a.source, "ls-files", "-z", "--", *COPIED_PATHS).split(b"\0") if x
    ]
    records = []
    total_bytes = 0
    for rel in paths:
        value = git(a.source, "show", f"{head}:{rel}")
        candidate = a.context / rel
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("REJECT MISSING/SYMLINKED CONTEXT PATH " + rel)
        content = candidate.read_bytes()
        if value != content:
            raise ValueError("REJECT SOURCE BYTE MISMATCH " + rel)
        records.append(
            {
                "path": rel,
                "sha256": sha(content),
                "git_blob_sha1": git(a.source, "rev-parse", f"{head}:{rel}").decode().strip(),
                "bytes": len(content),
            }
        )
        total_bytes += len(content)
    present = {
        str(x.relative_to(a.context))
        for top in ("src", "pilot")
        for x in (a.context / top).rglob("*")
        if x.is_file()
    }
    present.update(x for x in ("README.md", "pyproject.toml") if (a.context / x).is_file())
    extra = present.difference(paths)
    if extra:
        raise ValueError("REJECT EXTRA SOURCE BYTES " + ",".join(sorted(extra)[:5]))
    result = {
        "schema": "P28_T27_GIT_SOURCE_COPY_BYTE_CHAIN_V1",
        "source_head": head,
        "source_tree": tree,
        "scoped_source_file_count": len(paths),
        "scoped_source_bytes": total_bytes,
        "scoped_manifest_sha256": sha(
            json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
        ),
        "files": records,
    }
    if a.verify_only:
        expected = json.loads(a.manifest.read_text())
        if result != expected:
            raise ValueError("REJECT SOURCE MANIFEST CHANGED")
    else:
        a.manifest.parent.mkdir(parents=True, exist_ok=True)
        a.manifest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps({key: value for key, value in result.items() if key != "files"}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"P28 SOURCE CONTRACT FAIL: {exc}", file=sys.stderr)
        sys.exit(23)
