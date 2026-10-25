"""Make NEW-C1-HEAD exact dual 14-file Gitless UNSIGNED intake evidence.

Reads the clean current C1 commit and source bytes, writes ONLY to a caller's
new output directory outside the repository. No private keys, signatures,
independent Controller claims, Provider calls or Product admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"))
import m27_c1_f04_external_authority_consumer as c
import m27_c1_gitless_source_proof as gitless

ABI = "m27.c1.f04-dual-source-unsigned-intake/v1"


def run(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(("git", "-C", str(repo), *args),
                          capture_output=True, check=False, timeout=10)
    if proc.returncode != 0:
        raise ValueError("F04_CURRENT_GIT_SOURCE_COMMAND_FAILED")
    return proc.stdout


def source_file(repo: Path, head: str, source_path: str):
    line = run(repo, "ls-tree", head, "--", source_path).strip()
    try:
        meta, path = line.split(b"\t", 1)
        mode, kind, oid = meta.split()
    except ValueError as exc:
        raise ValueError("F04_SOURCE_TREE_PATH_NOT_PINNED") from exc
    if (kind != b"blob" or path.decode() != source_path or
        mode not in (b"100644", b"100755")):
        raise ValueError("F04_SOURCE_TREE_ITEM_INVALID")
    raw = run(repo, "show", head + ":" + source_path)
    calculated_oid = hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if calculated_oid != oid.decode():
        raise ValueError("F04_SOURCE_GIT_OID_MISMATCH")
    return raw, mode.decode(), calculated_oid


def generate(repo: Path, output: Path):
    repo = repo.resolve(strict=True)
    if output.exists() or output.is_relative_to(repo):
        raise ValueError("F04_UNIQUE_OUTPUT_OUTSIDE_REPO_REQUIRED")
    if not (repo / ".git").exists():
        raise ValueError("F04_EXACT_GIT_REPOSITORY_REQUIRED")
    if run(repo, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("F04_C1_HEAD_NOT_CLEAN")
    head = run(repo, "rev-parse", "HEAD").decode().strip()
    tree = run(repo, "rev-parse", "HEAD^{tree}").decode().strip()
    if not (c.hex_digest(head, 40) and c.hex_digest(tree, 40)):
        raise ValueError("F04_GIT_VECTOR_INVALID")
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    expiry = int(time.time()) + 1800
    inventories = {}
    for kind, names in (
        ("c1", c.C1_MODULES),
        ("f03", c.f03.F03_GITLESS_ALLOWED_A05),
    ):
        stage = output / (kind + "_exact_unsigned_bytes")
        stage.mkdir(mode=0o700)
        files = []
        for target in sorted(names):
            in_tree = "src/" + target if kind == "c1" else target
            raw, mode, oid = source_file(repo, head, in_tree)
            path = stage / target
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
            path.chmod(0o555 if mode == "100755" else 0o444)
            files.append({"path": target, "sha256": c.digest(raw),
                          "git_blob_oid": oid, "git_mode": mode})
        manifest = {
            "schema": gitless.ABI, "head": head, "tree": tree,
            "source_controller": "PENDING_AUTHENTIC_SOURCE_CONTROLLER",
            "expires_at": expiry, "files": files,
            "tenant": "owner-internal",
            "source_release_id": c.f03.A05_RELEASE_ID}
        proof = gitless.inspect_exact_bundle(
            stage, manifest, expected_head=head, expected_tree=tree)
        if proof["files_verified"] != 14 or proof["signed_source_admitted"]:
            raise ValueError("F04_UNSIGNED_STRUCTURAL_CHECK_INVALID")
        file_name = "UNSIGNED_" + kind.upper() + "_14_SOURCE_CONTROLLER_REQUEST.json"
        path = output / file_name
        path.write_bytes(c.canonical(manifest) + b"\n")
        path.chmod(0o600)
        inventories[kind] = {
            "sha256": c.digest(c.canonical(manifest)),
            "structural_proof": proof,
            "path": str(path),
            "staging_dir": str(stage)}
    receipt = {
        "schema": ABI, "head": head, "tree": tree,
        "source_release_id": c.f03.A05_RELEASE_ID,
        "source_manifest_sha256": c.CORPUS, "expires_at": expiry,
        "inventories": inventories,
        "file_count": sum(v["structural_proof"]["files_verified"]
                          for v in inventories.values()),
        "signed": False,
        "release_controller_approved": False,
        "source_controller_identity_qualified": False,
        "formal_product_pass": False,
        "stage": "UNSIGNED_BYTE_INVENTORY_ONLY_NOT_RIGHTS_OR_AUTHORITY"}
    result = output / "00_UNSIGNED_DUAL_SOURCE_EVIDENCE.json"
    result.write_bytes(json.dumps(receipt, sort_keys=True, indent=2).encode() + b"\n")
    result.chmod(0o600)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    data = generate(args.repo, args.out)
    print(json.dumps({"head": data["head"], "tree": data["tree"],
                      "file_count": data["file_count"],
                      "signed": data["signed"], "formal_product_pass": False},
                     sort_keys=True))
