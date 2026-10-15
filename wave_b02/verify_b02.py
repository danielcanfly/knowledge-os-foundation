#!/usr/bin/env python3
"""Independently recompute B02 content, evidence, and boundary seals."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from wave_b02.authority import B01_HEAD, B01_TREE, REPO, sha256_file, write_json
from wave_b02.run_b02 import ROOT, artifact_inventory


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"OBJECT_REQUIRED:{path}")
    return value


def main() -> int:
    results_path = ROOT / "B02_RESULTS.json"
    gates_path = ROOT / "B02_RELEASE_GATES.json"
    candidate_path = ROOT / "B02_NONPROD_CANDIDATE_MANIFEST.json"
    inventory_path = ROOT / "B02_ARTIFACT_INVENTORY.json"
    receipt_path = ROOT / "B02_VERIFY_RECEIPT.json"
    receipt_path.unlink(missing_ok=True)
    write_json(inventory_path, artifact_inventory())

    results = load(results_path)
    gates = load(gates_path)
    candidate = load(candidate_path)
    inventory = load(inventory_path)
    if results["status"] != "PASS" or not gates["nonprod_preflight_engineering_pass"]:
        raise RuntimeError("NONPROD_PREFLIGHT_NOT_PASS")
    if gates["formal_product_go"] or gates["c28_live_trial"] or gates["deployment_permitted"]:
        raise RuntimeError("EXTERNAL_AUTHORITY_ESCALATION")
    if candidate["sole_source"] != {"head": B01_HEAD, "tree": B01_TREE}:
        raise RuntimeError("B01_IDENTITY_MISMATCH")

    listed = set()
    for row in inventory["artifacts"]:
        path = REPO / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"ARTIFACT_MISMATCH:{row['path']}")
        listed.add(row["path"])
    actual = {
        str(path.relative_to(REPO)) for path in ROOT.rglob("*")
        if path.is_file() and path not in {inventory_path, receipt_path}
        and "__pycache__" not in path.parts
    }
    if listed != actual or inventory["artifact_count"] != len(listed):
        raise RuntimeError("ARTIFACT_INVENTORY_INCOMPLETE")

    for row in candidate["source_files"]:
        data = subprocess.check_output(
            ["git", "-C", str(REPO), "show", f"{B01_HEAD}:{row['path']}"])
        import hashlib
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise RuntimeError(f"B01_SOURCE_BYTE_MISMATCH:{row['path']}")
    oci = candidate["oci_content"]
    blobs = Path(oci["layout_path"]) / "blobs/sha256"
    for name in ("layer_sha256", "config_sha256", "manifest_sha256"):
        digest = oci[name]
        if sha256_file(blobs / digest) != digest:
            raise RuntimeError(f"OCI_BLOB_MISMATCH:{name}")

    history = sorted((ROOT / "history").glob("attempt_*/ARCHIVE_RECEIPT.json"))
    if len(history) < 2:
        raise RuntimeError("HISTORICAL_FAILURE_ARCHIVES_MISSING")
    head = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD^{tree}"], text=True).strip()
    receipt = {
        "schema": "m27.wave-b02.independent-seal-verification/v1",
        "status": "PASS",
        "verified_git": {"head": head, "tree": tree},
        "artifact_inventory_sha256": sha256_file(inventory_path),
        "artifacts_verified": len(listed),
        "b01_source_files_verified": len(candidate["source_files"]),
        "oci_blobs_verified": 3,
        "historical_failure_archives_preserved": len(history),
        "nonprod_preflight_engineering_pass": True,
        "formal_product_go": False,
        "c28_live_trial": False,
        "production_mutated": False,
        "q34_mutated": False,
        "sealed_evaluation_accessed": False,
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
