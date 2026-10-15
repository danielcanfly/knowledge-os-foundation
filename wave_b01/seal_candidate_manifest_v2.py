#!/usr/bin/env python3
"""Seal and verify the full-source B01 V2 machine handoff manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WAVE = ROOT / "wave_b01"
COMPONENTS = WAVE / "components"
OUTPUT = WAVE / "CANDIDATE_MANIFEST_V2.json"
LINKAGE = WAVE / "evidence" / "acceptance" / "RECEIPT_LOG_LINKAGE_V2.json"
BUNDLE = WAVE / "evidence" / "a04_repro_v2" / "BUNDLE_MANIFEST.json"

INPUTS = {
    "I37": {"head": "216f912994d20d134b1c8af50f7b2dd1a1c89a15",
             "tree": "f65a00d7b538e7acbc3404fa822f89631ddeed91", "mode": "BASE"},
    "A01": {"head": "0349a6b75c644139dff351fe627973c54a8f61c7",
             "tree": "62691766d560920965e9b595e7b20518d277886b", "mode": "CODE"},
    "A03": {"head": "216f912994d20d134b1c8af50f7b2dd1a1c89a15",
             "tree": "f65a00d7b538e7acbc3404fa822f89631ddeed91", "mode": "QA_SEAL_ONLY"},
    "A04": {"head": "964ee42d8d08915cfd51265cff7232837967a9bd",
             "tree": "16be439379c005a51aa6eaf71c95831e5de91d27", "mode": "COMPONENT"},
    "A05": {"head": "373720ebbbc427ed7cc47af2a1abe751d603ee85",
             "tree": "fb6a14737eec18750c53874c180015c8654fa1f1", "mode": "COMPONENT"},
    "A06": {"head": "f59ae5e36922e89a045fee0a930ba10d79f76c78",
             "tree": "96171eb880f75ee27c16996af61d73e08de4e457", "mode": "COMPONENT"},
    "A07": {"head": "411f0838e4328c0c2382d5c4f2ac6ca573cc829d",
             "tree": "f5d88c2d080a1e5f7b87bab51b7390e8433ddac0", "mode": "COMPONENT"},
    "A08": {"head": "e6927805b732b139d52eda09e7510ffa91a08be0",
             "tree": "1371c032b5e69ae3ff7cd23a9c57db454a045a78", "mode": "CODE"},
    "A09": {"head": "f68278b6d0b6406b5f8f0172799a06cb7a6dfa2a",
             "tree": "aa2bfd892117775fc48a5e046d669dff78e5616f", "mode": "CODE"},
    "A10": {"head": "4b3d4d79d6a8a9c0f7616f36a332fab29f922983",
             "tree": "e578134cdadffea13ea2a77b93b9ca1c5cefb55b", "mode": "PUBLIC_INTERFACE_ONLY"},
    "Q34_FROZEN": {"head": "89f1d7be1623cd6926a69e38871544eefe39e584",
                    "tree": "cde4d6ad61acef348350afcfe18f836d798a2091", "mode": "IMMUTABLE"},
}

DECLARED_REPAIRS = {
    "a04/README.md": "DOCUMENT_EXTERNAL_RUNTIME_REPLAY",
    "a04/local_model_provider.py": "REQUIRE_DIGEST_PINNED_EXTERNAL_RUNTIME",
    "a04/MODEL_RUNTIME_MANIFEST.json": "NEW_V2_REPRO_SUPPORT",
    "a04/licenses/QWEN2.5_APACHE-2.0.txt": "NEW_PINNED_PUBLIC_LICENSE",
    "a04/run_repro_v2.py": "NEW_CLEAN_CHECKOUT_RUNNER",
    "a04/stage_model_runtime.py": "NEW_OUTSIDE_GIT_STAGER",
    "a05/adapter/a05_run_tests.py": "CREATE_MISSING_EVIDENCE_RAW_DIRECTORY",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def tracked_source(root: Path) -> dict[str, str]:
    names = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"]
    ).decode().split("\0")
    return {name: sha256(root / name) for name in names if name}


def current_component_files() -> dict[str, Path]:
    result = {}
    for path in sorted(COMPONENTS.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(COMPONENTS)
        parts = relative.parts
        if "__pycache__" in parts or "model_runtime" in parts:
            continue
        if parts[0] in ("a04", "a05", "a06") and "evidence" in parts:
            continue
        if relative.as_posix() in ("a04/data/tokens.json", "a04/data/revocations.json"):
            continue
        result[relative.as_posix()] = path
    return result


def a05_expected(results: dict) -> dict[str, str]:
    expected = {}
    for name, record in results["code_sha256"].items():
        expected[f"a05/adapter/{name}"] = record["sha256"]
    for name, record in results["source_sha256"].items():
        expected[f"a05/{name}"] = record["sha256"]
    for name, record in results["native_release_artifact_sha256"].items():
        expected[f"a05/{name}"] = record["sha256"]
    return expected


def build(source_base: Path, a05_results_path: Path) -> dict:
    source_maps = {}
    for name in ("A04", "A06", "A07"):
        source = source_base / name
        if git(source, "rev-parse", "HEAD") != INPUTS[name]["head"]:
            raise ValueError(f"{name}_HEAD_MISMATCH")
        if git(source, "rev-parse", "HEAD^{tree}") != INPUTS[name]["tree"]:
            raise ValueError(f"{name}_TREE_MISMATCH")
        if git(source, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError(f"{name}_TRACKED_DIRTY")
        source_maps[name.lower()] = {
            f"{name.lower()}/{key}": value
            for key, value in tracked_source(source).items()
        }
    a05_results = json.loads(a05_results_path.read_text(encoding="utf-8"))
    if a05_results["git"]["a05_adapter"]["head"] != INPUTS["A05"]["head"]:
        raise ValueError("A05_HEAD_MISMATCH")
    if a05_results["git"]["a05_adapter"]["tree"] != INPUTS["A05"]["tree"]:
        raise ValueError("A05_TREE_MISMATCH")
    source_maps["a05"] = a05_expected(a05_results)

    current = current_component_files()
    files = {}
    missing = []
    for component, expected_map in source_maps.items():
        missing.extend(sorted(set(expected_map) - set(current)))
        for path, expected_sha in expected_map.items():
            if path not in current:
                continue
            actual = sha256(current[path])
            if actual == expected_sha:
                status = "MATCH_ACCEPTED_SOURCE"
            elif path in DECLARED_REPAIRS:
                status = "DECLARED_B01_REPAIR"
            else:
                raise ValueError(f"UNDECLARED_SOURCE_DRIFT:{path}")
            files[path] = {
                "sha256": actual,
                "accepted_source_sha256": expected_sha,
                "status": status,
                "change": DECLARED_REPAIRS.get(path),
            }
    if missing:
        raise ValueError(f"MISSING_ACCEPTED_FILES:{missing}")
    for path, actual_path in current.items():
        if path not in files:
            if path not in DECLARED_REPAIRS and path != "a05/INTEGRATION_CONTRACT_REQUEST.json":
                raise ValueError(f"UNDECLARED_IMPORTED_FILE:{path}")
            files[path] = {
                "sha256": sha256(actual_path),
                "accepted_source_sha256": None,
                "status": "DECLARED_B01_ADDITION",
                "change": DECLARED_REPAIRS.get(path, "MASTER_ACCEPTED_INTERFACE_COPY"),
            }

    read_only = {
        "A02_current_candidate_attestation": {
            "path": "wave_b01/evidence_inputs/a02_current_candidate_attestation.json",
            "sha256": sha256(WAVE / "evidence_inputs/a02_current_candidate_attestation.json"),
            "authority": "UNSIGNED_NONPROD_READ_ONLY",
        },
        "A10_public_contract": {
            "path": "wave_b01/interfaces/a10_public_contract.json",
            "sha256": sha256(WAVE / "interfaces/a10_public_contract.json"),
            "sealed_content": False,
        },
        "A10_scoped_completion": {
            "path": "wave_b01/evidence_inputs/a10_scoped_completion.json",
            "sha256": sha256(WAVE / "evidence_inputs/a10_scoped_completion.json"),
            "sealed_content": False,
        },
    }
    return {
        "schema": "m27.wave-b01.nonprod-candidate/v2",
        "abi": "m27.wave-b01.nonprod-integration/v1",
        "scope": "NONPROD_ONLY",
        "b01_v1_parent": {
            "head": "705a95ffa262bd58990c9bdd5bbce7b4ee9209c3",
            "tree": "3efa0e78c8ac407b2a20d5282b420ab04b96926f",
        },
        "accepted_inputs": INPUTS,
        "integration_commit_map": {
            "A01": "759e176215a661013fdd7737dc93cd00705aec0e",
            "A08": "07709f7f9753a6e0bee578f30324a42828dcbe62",
            "A09": "f502ca7bbfc6ffdc00aa3805d5d44267d5876108",
        },
        "imported_files": files,
        "imported_file_count": len(files),
        "declared_integration_changes": DECLARED_REPAIRS,
        "read_only_inputs": read_only,
        "evidence": {
            "receipt_log_linkage_v2": {
                "path": LINKAGE.relative_to(ROOT).as_posix(),
                "sha256": sha256(LINKAGE),
            },
            "a04_safe_bundle_v2": {
                "path": BUNDLE.relative_to(ROOT).as_posix(),
                "sha256": sha256(BUNDLE),
            },
        },
        "negative_authority_assertions": {
            "production_authority": False,
            "release_authority": False,
            "native_q34": False,
            "formal_x01_x09": "0/9_NOT_RUN",
            "official_original523": "0/523_NOT_RUN",
            "official_product_blind200": "0/200_NOT_RUN",
            "sealed_evaluation_access": False,
            "a02_external_signature": False,
            "a08_coding_source_refusal_preserved": True,
        },
    }


def verify(manifest: dict) -> None:
    if manifest["schema"] != "m27.wave-b01.nonprod-candidate/v2":
        raise ValueError("SCHEMA_MISMATCH")
    for name, identity in manifest["accepted_inputs"].items():
        if len(identity["head"]) != 40 or len(identity["tree"]) != 40:
            raise ValueError(f"NON_FULL_GIT_ID:{name}")
    current = current_component_files()
    recorded = manifest["imported_files"]
    if set(current) != set(recorded):
        raise ValueError("IMPORTED_FILE_SET_DRIFT")
    for path, file_path in current.items():
        if sha256(file_path) != recorded[path]["sha256"]:
            raise ValueError(f"IMPORTED_FILE_DIGEST_DRIFT:{path}")
    for item in manifest["read_only_inputs"].values():
        if sha256(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("READ_ONLY_INPUT_DRIFT")
    for item in manifest["evidence"].values():
        if sha256(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("EVIDENCE_MANIFEST_DRIFT")
    negative = manifest["negative_authority_assertions"]
    if any(negative[key] is not False for key in (
        "production_authority", "release_authority", "native_q34",
        "sealed_evaluation_access", "a02_external_signature",
    )):
        raise ValueError("AUTHORITY_ESCALATION")
    if negative["a08_coding_source_refusal_preserved"] is not True:
        raise ValueError("REFUSAL_NOT_PRESERVED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--source-base", type=Path)
    parser.add_argument("--a05-results", type=Path)
    args = parser.parse_args()
    if args.write == args.verify_only:
        parser.error("choose exactly one of --write or --verify-only")
    if args.write:
        if args.source_base is None or args.a05_results is None:
            parser.error("--write requires --source-base and --a05-results")
        value = build(args.source_base, args.a05_results)
        OUTPUT.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    verify(value)
    print(json.dumps({
        "status": "PASS",
        "manifest": str(OUTPUT),
        "manifest_sha256": sha256(OUTPUT),
        "imported_files": value["imported_file_count"],
        "full_git_identities": len(value["accepted_inputs"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
