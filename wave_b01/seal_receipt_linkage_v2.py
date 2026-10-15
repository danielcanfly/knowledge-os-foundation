#!/usr/bin/env python3
"""Seal portable V2 receipt/log links without modifying V1 receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "wave_b01" / "evidence" / "acceptance"
OUTPUT = EVIDENCE / "RECEIPT_LOG_LINKAGE_V2.json"

PAIRS = {
    "b01_cross_module_10": None,
    "a01_a08_a09_targeted_78": None,
    "a05_component_31": None,
    "a06_component_25": None,
    "a07_component_21": None,
    "m27_85_modules": None,
    "m26_75_modules_historical": None,
    "m27_85_modules.initial_fail_tmp_inside_git":
        "m27_85_modules.initial_fail_tmp_inside_git.log",
    "m26_75_modules_historical.fail_model_runtime_symlink_copy":
        "m26_75_modules_historical.fail_model_runtime_symlink_copy.log",
    "m26_75_modules_historical.fail_recursive_pytest_scratch":
        "m26_75_modules_historical.fail_recursive_pytest_scratch.log",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    records = {}
    for name, override in PAIRS.items():
        receipt_path = EVIDENCE / f"{name}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        v1_pointer_name = Path(receipt["log"]).name
        v1_pointer = EVIDENCE / v1_pointer_name
        archive_name = override or v1_pointer_name
        archive = EVIDENCE / archive_name
        declared = receipt["log_sha256"]
        actual = sha256(archive)
        if actual != declared:
            raise ValueError(f"ARCHIVE_DIGEST_MISMATCH:{name}")
        records[name] = {
            "v1_receipt": receipt_path.relative_to(ROOT).as_posix(),
            "v1_receipt_sha256": sha256(receipt_path),
            "v1_log_pointer": v1_pointer.relative_to(ROOT).as_posix(),
            "v1_pointer_sha256": sha256(v1_pointer),
            "v1_pointer_matches_declared": sha256(v1_pointer) == declared,
            "v2_archived_log": archive.relative_to(ROOT).as_posix(),
            "v2_archived_log_sha256": actual,
            "declared_log_sha256": declared,
            "v2_archive_matches_declared": True,
            "exit_code": receipt["exit_code"],
            "expectation_met": receipt["expectation_met"],
            "summary": receipt["summary"],
            "historical_fail_preserved": bool(override),
        }
    mismatches = [
        name for name, item in records.items()
        if not item["v1_pointer_matches_declared"]
    ]
    if mismatches != [
        "m27_85_modules.initial_fail_tmp_inside_git",
        "m26_75_modules_historical.fail_model_runtime_symlink_copy",
        "m26_75_modules_historical.fail_recursive_pytest_scratch",
    ]:
        raise ValueError(f"UNEXPECTED_V1_MISMATCH_SET:{mismatches}")
    return {
        "schema": "m27.wave-b01.receipt-log-linkage/v2",
        "verification_phase": "AFTER_FINALIZER_INDEPENDENT_SHA256",
        "pair_count": len(records),
        "verified_pair_count": sum(
            item["v2_archive_matches_declared"] for item in records.values()
        ),
        "v1_receipts_modified": False,
        "historical_failures_reclassified": False,
        "known_v1_pointer_mismatches": mismatches,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    expected = build()
    if args.write == args.verify_only:
        parser.error("choose exactly one of --write or --verify-only")
    if args.write:
        OUTPUT.write_text(
            json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        actual = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if actual != expected:
            raise ValueError("LINKAGE_INDEX_DRIFT")
    print(json.dumps({
        "status": "PASS",
        "pairs": expected["pair_count"],
        "verified": expected["verified_pair_count"],
        "historical_v1_pointer_mismatches": len(
            expected["known_v1_pointer_mismatches"]
        ),
        "index": str(OUTPUT),
        "index_sha256": sha256(OUTPUT),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
