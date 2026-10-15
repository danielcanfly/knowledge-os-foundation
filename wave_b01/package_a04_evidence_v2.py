#!/usr/bin/env python3
"""Package safe, content-addressed A04 client/server/model evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
A04 = ROOT / "wave_b01" / "components" / "a04"
FORBIDDEN_KEY = re.compile(
    r"^(authorization|password|secret|credential|api[_-]?key|access[_-]?token|refresh[_-]?token|tokens?)$",
    re.IGNORECASE,
)
FORBIDDEN_TEXT = re.compile(
    rb"(-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer [A-Za-z0-9._~-]{16,}|sk-[A-Za-z0-9_-]{20,})"
)
SELECTED = (
    "acceptance_results.json",
    "return_model_test_results.json",
    "REPRO_RUN_RECEIPT_V2.json",
    "bootstrap.stdout.log",
    "bootstrap.stderr.log",
    "runtime_warmup.stdout.log",
    "runtime_warmup.stderr.log",
    "server.stdout.log",
    "server.stderr.log",
    "client_21.stdout.log",
    "client_21.stderr.log",
    "client_real_model_8.stdout.log",
    "client_real_model_8.stderr.log",
)
SELECTED_DIRS = ("client_cases", "return_model_cases", "journals", "model_generation")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_json(value, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if FORBIDDEN_KEY.match(key):
                raise ValueError(f"SENSITIVE_KEY:{path}.{key}")
            inspect_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            inspect_json(child, f"{path}[{index}]")


def inspect_file(path: Path) -> None:
    data = path.read_bytes()
    if FORBIDDEN_TEXT.search(data):
        raise ValueError(f"SENSITIVE_TEXT_PATTERN:{path.name}")
    if path.suffix == ".json":
        inspect_json(json.loads(data))
    elif path.suffix == ".jsonl":
        for line in data.splitlines():
            if line.strip():
                inspect_json(json.loads(line))


def copy_one(source: Path, destination: Path) -> None:
    inspect_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256(source) != sha256(destination):
        raise ValueError("COPY_DIGEST_MISMATCH")


def relative_case_index(aggregate: dict, group: str) -> list[dict]:
    rows = aggregate.get("cases", aggregate.get("tests", []))
    result = []
    for row in rows:
        name = row.get("case", row.get("name"))
        pointer = row.get("receipt", row.get("receipt_path"))
        relative = f"{group}/{Path(pointer).name}"
        target = Path(relative)
        result.append({
            "name": name,
            "pass": row["pass"],
            "receipt": relative,
            "receipt_sha256": sha256(_CASE_ROOT / target),
        })
    return result


_CASE_ROOT = Path("/")


def main() -> int:
    global _CASE_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-stage-receipt", type=Path, required=True)
    args = parser.parse_args()
    source = args.evidence_root.resolve()
    output = args.output.resolve()
    stage_receipt = args.runtime_stage_receipt.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_NOT_EMPTY")
    output.mkdir(parents=True, exist_ok=True)
    try:
        for name in SELECTED:
            copy_one(source / name, output / name)
        for directory in SELECTED_DIRS:
            for item in sorted((source / directory).glob("*")):
                if item.is_file():
                    copy_one(item, output / directory / item.name)
        copy_one(stage_receipt, output / "EXTERNAL_RUNTIME_STAGE_RECEIPT.json")

        _CASE_ROOT = output
        stub_source = json.loads((source / "acceptance_results.json").read_text())
        real_source = json.loads((source / "return_model_test_results.json").read_text())
        portable = {
            "schema": "m27.a04.portable-client-receipts/v2",
            "stub": {
                "counts": stub_source["counts"],
                "provider_kind": stub_source["provider_kind"],
                "native_q34": stub_source["native_q34"],
                "cases": relative_case_index(stub_source, "client_cases"),
            },
            "real_model": {
                "counts": real_source["counts"],
                "model": real_source["model"],
                "model_sha256": real_source["model_sha256"],
                "actual_model_inference": real_source["actual_model_inference"],
                "native_q34": real_source["native_q34"],
                "cases": relative_case_index(real_source, "return_model_cases"),
            },
            "secret_scan": "PASS_NO_REDACTION_REQUIRED",
            "absolute_receipt_pointers_replaced_by_relative_v2_pointers": True,
        }
        portable_path = output / "PORTABLE_CLIENT_RECEIPTS_V2.json"
        portable_path.write_text(
            json.dumps(portable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        source_files = {}
        for name in ("atlas.txt", "cedar.txt", "delta.txt", "manifest.json"):
            path = A04 / "data" / name
            source_files[f"wave_b01/components/a04/data/{name}"] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        files = {}
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "BUNDLE_MANIFEST.json":
                files[path.relative_to(output).as_posix()] = {
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
        manifest = {
            "schema": "m27.a04.safe-evidence-bundle/v2",
            "scope": "NONPROD_LOCAL_ONLY",
            "file_count": len(files),
            "files": files,
            "source_files": source_files,
            "secret_scan": "PASS_NO_REDACTION_REQUIRED",
            "contains_tokens_or_credentials": False,
            "contains_protected_gold": False,
            "production_authority": False,
            "native_q34": False,
        }
        manifest_path = output / "BUNDLE_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "status": "PASS",
            "bundle": str(output),
            "file_count": len(files),
            "manifest_sha256": sha256(manifest_path),
            "stub_cases": len(portable["stub"]["cases"]),
            "real_model_cases": len(portable["real_model"]["cases"]),
        }, sort_keys=True))
        return 0
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
