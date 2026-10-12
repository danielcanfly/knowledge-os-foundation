"""S29 offline Linux/arm64 wheel-hash and current source-to-wheel verifier.

Never contacts a registry, Provider, or CI. Rejects missing/extra/tampered wheels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path

REQ = re.compile(r"([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:([0-9a-f]{64})")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_locks(paths: list[Path]) -> dict[str, tuple[str, str]]:
    wanted = {}
    for path in paths:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = REQ.fullmatch(line)
            if match is None:
                raise ValueError(f"invalid hash-locked requirement: {path}: {line}")
            name, version, digest = match.groups()
            key = canonical(name)
            item = version, digest
            if key in wanted and wanted[key] != item:
                raise ValueError(f"conflicting lock for {key}")
            wanted[key] = item
    if not wanted:
        raise ValueError("empty lock")
    return wanted


def wheel_identity(path: Path) -> tuple[str, str, list[str]]:
    with zipfile.ZipFile(path) as wheel:
        metadata = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
        wheel_headers = [n for n in wheel.namelist() if n.endswith(".dist-info/WHEEL")]
        if len(metadata) != 1 or len(wheel_headers) != 1:
            raise ValueError(f"invalid wheel metadata count: {path.name}")
        msg = Parser().parsestr(wheel.read(metadata[0]).decode("utf-8"))
        wh = Parser().parsestr(wheel.read(wheel_headers[0]).decode("utf-8"))
        name, version = msg.get("Name"), msg.get("Version")
        tags = wh.get_all("Tag", [])
        if not name or not version or not tags:
            raise ValueError(f"wheel missing name/version/tags: {path.name}")
        if not any(tag.endswith("-any") or "aarch64" in tag for tag in tags):
            raise ValueError(f"not Linux arm64/pure wheel: {path.name}: {tags}")
        if wheel.testzip() is not None:
            raise ValueError(f"corrupt zip member: {path.name}")
        return canonical(name), version, tags


def verify(wheelhouse: Path, lock_paths: list[Path], source_root: Path | None) -> dict:
    expected = read_locks(lock_paths)
    wheels = sorted(wheelhouse.glob("*.whl"))
    actual = {}
    for path in wheels:
        name, version, tags = wheel_identity(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if name not in expected:
            raise ValueError(f"unlocked wheel: {path.name}")
        if name in actual:
            raise ValueError(f"duplicate distribution wheel: {name}")
        if (version, digest) != expected[name]:
            raise ValueError(f"hash/version mismatch: {path.name}")
        actual[name] = {"wheel": path.name, "sha256": digest,
                        "bytes": path.stat().st_size, "tags": tags}
    missing = set(expected) - set(actual)
    if missing:
        raise ValueError(f"missing wheels: {sorted(missing)}")
    compared = 0
    if source_root is not None:
        project_wheel = wheelhouse / actual["knowledge-engine"]["wheel"]
        tracked = subprocess.check_output(
            ["git", "-C", str(source_root), "ls-files", "-z", "--", "src/knowledge_engine"]
        ).split(b"\0")
        with zipfile.ZipFile(project_wheel) as wheel:
            entries = set(wheel.namelist())
            for name in tracked:
                if not name:
                    continue
                rel = name.decode()
                if not rel.startswith("src/knowledge_engine/"):
                    continue
                member = rel[len("src/"):]
                if member not in entries:
                    raise ValueError(f"missing project wheel member: {member}")
                if (source_root / rel).read_bytes() != wheel.read(member):
                    raise ValueError(f"source bytes differ in project wheel: {member}")
                compared += 1
    return {"status": "PASS", "wheel_count": len(actual),
            "tracked_package_source_files_equal": compared, "wheels": actual}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--lock", action="append", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.wheelhouse, args.lock, args.source_root)
    except Exception as exc:
        print(f"S29_WHEEL_LOCK_FAIL: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload)
    print(f"S29_WHEEL_LOCK_PASS wheels={result['wheel_count']} "
          f"source_files={result['tracked_package_source_files_equal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
