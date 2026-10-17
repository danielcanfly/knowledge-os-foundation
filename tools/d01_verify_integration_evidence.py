#!/usr/bin/env python3
"""Independently verify the sealed D01 Nonprod integration artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "d01"


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def junit(relative: str) -> tuple[int, int, int, int]:
    suites = list(ET.parse(ROOT / relative).getroot().iter("testsuite"))
    return tuple(
        sum(int(s.attrib.get(key, "0")) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    )


def main() -> int:
    checks = 0
    inventory = load("D01_SOURCE_AND_EVIDENCE_SHA256.json")
    require(inventory["entry_count"] == len(inventory["entries"]), "inventory count")
    for entry in inventory["entries"]:
        path = ROOT / entry["path"]
        require(path.is_file(), f"missing:{entry['path']}")
        require(path.stat().st_size == entry["bytes"], f"bytes:{entry['path']}")
        require(sha(path) == entry["sha256"], f"sha:{entry['path']}")
        checks += 3

    for receipt_path in sorted((EVIDENCE / "raw").glob("*.receipt.json")):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") != "m27.c02.command-receipt/v1":
            require(receipt.get("retained") is True, f"failed attempt retained:{receipt_path.name}")
            checks += 1
            continue
        stem = receipt_path.name.removesuffix(".receipt.json")
        for stream in ("stdout", "stderr"):
            path = receipt_path.with_name(f"{stem}.{stream}.log")
            require(path.stat().st_size == receipt[f"{stream}_bytes"], f"receipt bytes:{stem}")
            require(sha(path) == receipt[f"{stream}_sha256"], f"receipt sha:{stem}")
            checks += 2

    provenance = load("D01_MERGE_PROVENANCE.json")
    for item in provenance["imported"]:
        raw = (ROOT / item["path"]).read_bytes()
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        require(blob == item["git_blob_sha1"], f"git blob:{item['path']}")
        require(item["changed_after_selective_import"] is False, f"source changed:{item['path']}")
        checks += 2
    require(provenance["c02_default_registration"] is False, "C02 default registration")
    require(
        "m27_d01_nonprod_integration"
        not in (ROOT / "src/knowledge_engine/__init__.py").read_text(),
        "D01 default import",
    )
    checks += 2

    require(junit("evidence/d01/original_53/c01_original_51.junit.xml") == (51, 46, 0, 0), "C01 51")
    require(junit("evidence/d01/original_53/c02_original_2.junit.xml") == (2, 2, 0, 0), "C02 2")
    checks += 2
    abi = load("D01_ABI_COMPATIBILITY_RESULTS.json")
    require(abi["original_53"]["passed"] == 5, "original pass count")
    require(abi["original_53"]["failed"] == 48, "original red count")
    require(abi["full_8990_reproduction"] == "NOT_RERUN_NOT_CLAIMED", "8990 overclaim")
    for suite in abi["suites"].values():
        require(suite["failed"] == 0 and suite["exit_code"] == 0, f"suite:{suite['name']}")
        checks += 1
    checks += 3

    joined = load("evidence/d01/joined/D01_JOINED_REAL_MODEL_E2E.json")
    require(joined["fixed_denominator"] == 2, "joined denominator")
    require(joined["actual_local_model_generations"] == 2, "joined generation")
    require(joined["fixture_transport_deliveries"] == 1, "fixture delivery")
    require(joined["forged_ack_denials"] == 1, "forged ACK")
    require(joined["official_client_publications"] == 0, "official publication")
    require(joined["provider_qualification_proven"] is False, "provider qualification")
    for case in joined["cases"]:
        outcome = case["outcome"]
        require(
            case["model_exit_code"] == 0 and not case["model_timed_out"], f"model:{case['case_id']}"
        )
        require(
            set(outcome["stage_timings"])
            == {"source_retrieval", "generator", "verifier", "client"},
            f"timings:{case['case_id']}",
        )
        require(outcome["official_client_publication"] is False, f"publication:{case['case_id']}")
        checks += 3
    checks += 6

    authority = load("D01_INTEGRATION_AUTHORITY_LEDGER.json")
    admission = load("D01_INTEGRATION_ADMISSION_DECISION.json")
    require(
        authority["semantic_provider"]["issuer_independent_qualification"] == "NOT_PROVEN", "issuer"
    )
    require(authority["owner_adr"]["formally_accepted"] == 0, "ADR")
    require(authority["custodian"]["accepted_receipts"] == 0, "custodian")
    require(authority["independent_b03_r01_witness"] == "ABSENT_NOT_READ", "B03/R01")
    for key in (
        "C02_SEMANTIC_ADMISSION",
        "NATIVE_COMPOSER_ADMISSION",
        "FORMAL_PRODUCT_GO",
        "C28",
        "F35",
        "REL01",
    ):
        require(admission[key] is False, f"gate:{key}")
        checks += 1
    require(admission["PRODUCTION"] == "NO_GO", "Production")
    require(admission["d01_authorized_engineering"] == "PASS", "D01 engineering")
    checks += 6

    source = (ROOT / "src/knowledge_engine/m27_d01_nonprod_integration.py").read_text()
    require("and policy.real_client_authority_proven" in source, "real Client authority gate")
    require("and policy.product_release_authority_proven" in source, "Product authority gate")
    require(re.search(r'\n\s+"NO_GO",\n', source) is not None, "Production hard stop")
    checks += 3
    print(
        json.dumps(
            {"checks": checks, "inventory_entries": inventory["entry_count"], "status": "PASS"},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
