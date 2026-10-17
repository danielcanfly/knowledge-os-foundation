#!/usr/bin/env python3
"""Build D01 ledgers from sealed local receipts without promoting admission."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "d01"
BASELINE_HEAD = "f857622be0e07a3979e65275a4b4c402c5ec7e8b"
BASELINE_TREE = "962cbc34a2a0bfe0e921912312b9e9a1713a202b"
C01_HEAD = "b3724656bb6f3e237ca5d755ce9ecc1c5768c0af"
C01_TREE = "264c2acf68af44a37b74339f9f97720c07cb9dc3"
C02_HEAD = "ad16177209ffb9e573235b398e4ce3838ed8a421"
C02_TREE = "a2c97f017309d7b7778e9c689087ee601c8f4ec7"

C01_BLOBS = {
    "scripts/c01_run_residual_cases.py": "1571df50e69749d6e275dd92be4190723cec5dc0",
    "src/knowledge_engine/c01_canonical_contract_gate.py": (
        "e3776895e55559d263fbcd9aa9bb3f2a9ad2b2fe"
    ),
    "src/knowledge_engine/m26_aq_semantic_contract.py": "158b1b9c3ba11f43c400ca83c99b2bf12957a9fa",
    "src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py": (
        "ce59e05a6e2869f3fc296135e943c8351a3fd1aa"
    ),
    "tests/test_c01_canonical_contract_gate.py": "b1a5c2a549f69565de01bcbf687e696104cf2393",
    "tests/test_c01_legacy_canonical_bundle_bridge.py": "553bb5ae79d0aa82d865bb4009c603ca30397f5d",
}
C02_BLOBS = {
    "src/knowledge_engine/m27_c02_native_composer.py": "377cf1cc383e8f24c14325f07c80e66d034c1ecd",
    "src/knowledge_engine/m27_c02_semantic_provider.py": "a2ff4f62b1f9f71cdfaeec5720e83e46c0f46e52",
    "tests/test_m27_c02_semantic_provider_native_composer.py": (
        "828f1f39b3d9e578ee3fc88890336bb0987cb69b"
    ),
    "tools/c02_capture_command.py": "210d4f3da21cbf6c6f7ce64de9922ef3029363d2",
    "tools/c02_fixture_client.py": "8a3ac030eedddcd97572f38f31e3b1f9c66af7c1",
    "tools/c02_run_fixture_client_receipts.py": "7379aad53cd93006d28942066f104157142f703b",
    "tools/c02_run_real_model_candidates.py": "00e5cab9bfb0d4a0983c5ca1180a8865393ba0a9",
}
D01_FILES = (
    "src/knowledge_engine/m27_d01_nonprod_integration.py",
    "tests/test_m27_d01_nonprod_integration.py",
    "tools/d01_run_joined_e2e.py",
    "tools/d01_build_artifacts.py",
    "tools/d01_verify_integration_evidence.py",
)
LEDGER_FILES = (
    "D01_INTEGRATION_AUTHORITY_LEDGER.json",
    "D01_MERGE_PROVENANCE.json",
    "D01_ABI_COMPATIBILITY_RESULTS.json",
    "D01_JOINED_POSITIVE_NEGATIVE_RESULTS.json",
    "D01_INTEGRATION_ADMISSION_DECISION.json",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def pytest_summary(name: str, expected: tuple[int, int]) -> dict[str, int | str]:
    text = (EVIDENCE / "raw" / f"{name}.stdout.log").read_text(encoding="utf-8")
    passed = int((re.findall(r"(\d+) passed", text) or ["0"])[-1])
    failed = int((re.findall(r"(\d+) failed", text) or ["0"])[-1])
    if (passed, failed) != expected:
        raise SystemExit(f"D01_COUNT_MISMATCH:{name}:{passed}:{failed}")
    receipt = read_json(EVIDENCE / "raw" / f"{name}.receipt.json")
    return {
        "name": name,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "exit_code": receipt["exit_code"],
        "receipt": f"evidence/d01/raw/{name}.receipt.json",
    }


def junit_counts(relative: str) -> dict[str, int]:
    root = ET.parse(ROOT / relative).getroot()
    suites = list(root.iter("testsuite"))
    return {
        key: sum(int(s.attrib.get(key, "0")) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def main() -> int:
    joined = read_json(EVIDENCE / "joined" / "D01_JOINED_REAL_MODEL_E2E.json")
    original_c01 = junit_counts("evidence/d01/original_53/c01_original_51.junit.xml")
    original_c02 = junit_counts("evidence/d01/original_53/c02_original_2.junit.xml")
    if original_c01 != {"tests": 51, "failures": 46, "errors": 0, "skipped": 0}:
        raise SystemExit("D01_C01_ORIGINAL_DENOMINATOR_MISMATCH")
    if original_c02 != {"tests": 2, "failures": 2, "errors": 0, "skipped": 0}:
        raise SystemExit("D01_C02_ORIGINAL_DENOMINATOR_MISMATCH")

    authority = {
        "schema": "m27.d01.integration-authority-ledger/v1",
        "scope": "D01_NONPROD_ENGINEERING_ONLY",
        "issuer": {"authority": "Owner D01 dispatch", "engineering_scope_authorized": True},
        "semantic_provider": {
            "issuer_independent_qualification": "NOT_PROVEN",
            "provider_grant": "ABSENT",
            "candidate_fixture_used_for_transport_only": True,
            "admission": False,
        },
        "idp": {"formal_identity_proof": "NOT_PROVEN", "admission": False},
        "custodian": {
            "required_receipts": 12,
            "accepted_receipts": 0,
            "state": "PENDING_REISSUANCE",
        },
        "owner_adr": {"required": 33, "formally_accepted": 0, "state": "PROPOSED_NOT_APPROVED"},
        "git": {
            "baseline_head": BASELINE_HEAD,
            "baseline_tree": BASELINE_TREE,
            "c01_accepted_head": C01_HEAD,
            "c01_accepted_tree": C01_TREE,
            "c02_engineering_head": C02_HEAD,
            "c02_engineering_tree": C02_TREE,
        },
        "gguf": {
            "actual_local_generation": True,
            "model_sha256": joined["model_sha256"],
            "semantic_qualification": False,
        },
        "oci": {"current_product_signed_image": "NOT_PROVEN", "admission": False},
        "ci": {"current_product_signer_receipt": "NOT_PROVEN", "admission": False},
        "c28": False,
        "streaming": {"ephemeral_fixture_transport": True, "official_client_publication": False},
        "rights": {
            "d01_local_test_sources": "OWNER_DISPATCHED_NONPROD_FIXTURE",
            "complete_product_source_rights": "NOT_PROVEN",
            "unsafe_unsupported_skill_claim_red": 1,
        },
        "independent_b03_r01_witness": "ABSENT_NOT_READ",
        "external_gates": {
            "x01_x09": "0/9",
            "e27_original523": "0/523",
            "blind200": "0/200",
        },
    }
    write_json(ROOT / LEDGER_FILES[0], authority)

    imported = []
    for source, commit, tree, mapping in (
        ("C01", C01_HEAD, C01_TREE, C01_BLOBS),
        ("C02", C02_HEAD, C02_TREE, C02_BLOBS),
    ):
        for relative, expected_blob in mapping.items():
            actual_blob = git_blob(ROOT / relative)
            if actual_blob != expected_blob:
                raise SystemExit(f"D01_IMPORTED_BLOB_MISMATCH:{relative}")
            imported.append(
                {
                    "source": source,
                    "source_commit": commit,
                    "source_tree": tree,
                    "path": relative,
                    "git_blob_sha1": actual_blob,
                    "changed_after_selective_import": False,
                }
            )
    provenance = {
        "schema": "m27.d01.merge-provenance/v1",
        "method": "SELECTIVE_PATH_IMPORT_NOT_WHOLE_EVIDENCE_COMMIT",
        "baseline": {"head": BASELINE_HEAD, "tree": BASELINE_TREE},
        "branch": "codex/d01-exclusive-nonprod-integration-20261017",
        "imported": imported,
        "d01_authored": [
            {
                "path": relative,
                "sha256": sha256(ROOT / relative),
                "bytes": (ROOT / relative).stat().st_size,
            }
            for relative in D01_FILES
        ],
        "excluded": [
            "C01 Worker raw history and sealed evidence",
            "C02 Worker raw history and sealed evidence",
            "all default Product registration and release pointers",
        ],
        "baseline_files_changed": sorted(
            relative for relative in C01_BLOBS if relative.startswith("src/knowledge_engine/m26_")
        ),
        "baseline_change_reason": "accepted C01 loader-injection compatibility repair only",
        "c02_default_registration": False,
    }
    write_json(ROOT / LEDGER_FILES[1], provenance)

    suites = {
        "d01_integration": pytest_summary("d01_integration_31", (31, 0)),
        "c01_contract": pytest_summary("c01_contract_23", (23, 0)),
        "c01_related": pytest_summary("c01_related_34", (34, 0)),
        "c02_contract": pytest_summary("c02_contract_46", (46, 0)),
        "impacted_m27": pytest_summary("impacted_m27_54", (54, 0)),
        "m26_mature": pytest_summary("m26_mature_154", (154, 0)),
        "targeted_api_translation_legacy_tenant_citation": pytest_summary(
            "targeted_api_translation_legacy_tenant_citation_34", (34, 0)
        ),
    }
    abi = {
        "schema": "m27.d01.abi-compatibility-results/v1",
        "status": "PASS_AUTHORIZED_NONPROD_INTEGRATION",
        "original_53": {
            "denominator": 53,
            "passed": 5,
            "failed": 48,
            "c01": {"passed": 5, "failed": 46, **original_c01},
            "c02": {"passed": 0, "failed": 2, **original_c02},
            "targeted_remaining": 48,
        },
        "recovered_original_five": pytest_summary("c01_recovered_5", (5, 0)),
        "suites": suites,
        "joined_e2e": {
            "fixed_denominator": joined["fixed_denominator"],
            "actual_local_model_generations": joined["actual_local_model_generations"],
            "fixture_transport_deliveries": joined["fixture_transport_deliveries"],
            "forged_ack_denials": joined["forged_ack_denials"],
            "official_client_publications": joined["official_client_publications"],
            "receipt": "evidence/d01/joined/D01_JOINED_REAL_MODEL_E2E.json",
        },
        "full_8990_reproduction": "NOT_RERUN_NOT_CLAIMED",
        "historical_8990_breakdown_not_current_score": "8935/53/0/2",
    }
    write_json(ROOT / LEDGER_FILES[2], abi)

    joined_result = {
        "schema": "m27.d01.joined-positive-negative-results/v1",
        "status": joined["status"],
        "fixed_denominator": joined["fixed_denominator"],
        "source_generator_verifier_client_timings_present": all(
            set(case["outcome"]["stage_timings"])
            == {"source_retrieval", "generator", "verifier", "client"}
            for case in joined["cases"]
        ),
        "cases": [
            {
                "case_id": case["case_id"],
                "model_pid": case["model_pid"],
                "client_pid": case["client_processes"][0]["pid"],
                "model_exit_code": case["model_exit_code"],
                "generated_text_sha256": case["generated_text_sha256"],
                "source_sha256": case["outcome"]["source_receipt"]["sources"][0]["source_sha256"],
                "status": case["outcome"]["status"],
                "terminal_reason": case["outcome"]["terminal_reason"],
                "fixture_transport_delivery": case["outcome"]["fixture_transport_delivery"],
                "official_client_publication": case["outcome"]["official_client_publication"],
            }
            for case in joined["cases"]
        ],
        "model_sha256": joined["model_sha256"],
        "llama_cli_sha256": joined["llama_cli_sha256"],
        "generation_latency_ms": {
            "denominator": joined["generation_latency_denominator"],
            "mean": joined["generation_latency_mean_ms"],
            "p95": joined["generation_latency_p95_ms"],
        },
        "external_provider_calls": joined["external_provider_calls"],
        "billable_provider_calls": joined["billable_provider_calls"],
        "local_compute_cost_claimed_zero": joined["local_compute_cost_claimed_zero"],
    }
    write_json(ROOT / LEDGER_FILES[3], joined_result)

    admission = {
        "schema": "m27.d01.integration-admission-decision/v1",
        "d01_authorized_engineering": "PASS",
        "semantic_provider_issuer_independent_qualification": "NOT_PROVEN",
        "C02_SEMANTIC_ADMISSION": False,
        "NATIVE_COMPOSER_ADMISSION": False,
        "FORMAL_PRODUCT_GO": False,
        "C28": False,
        "F35": False,
        "REL01": False,
        "PRODUCTION": "NO_GO",
        "official_client_publications": 0,
        "owner_adrs_self_approved": 0,
        "custodian_receipts_self_approved": 0,
        "external_gate_disposition": "RETAINED_SEPARATELY_NOT_D01_ENGINEERING_FAILURE",
    }
    write_json(ROOT / LEDGER_FILES[4], admission)

    inventory_paths = set(C01_BLOBS) | set(C02_BLOBS) | set(D01_FILES) | set(LEDGER_FILES)
    inventory_paths.update(
        str(path.relative_to(ROOT)) for path in EVIDENCE.rglob("*") if path.is_file()
    )
    inventory_paths.discard("D01_SOURCE_AND_EVIDENCE_SHA256.json")
    entries = []
    for relative in sorted(inventory_paths):
        path = ROOT / relative
        entries.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(
        ROOT / "D01_SOURCE_AND_EVIDENCE_SHA256.json",
        {
            "schema": "m27.d01.source-and-evidence-sha256/v1",
            "self_excluded_to_avoid_recursive_digest": True,
            "entry_count": len(entries),
            "entries": entries,
        },
    )
    print(json.dumps({"status": "PASS", "inventory_entries": len(entries)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
