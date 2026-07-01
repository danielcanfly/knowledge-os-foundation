from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "knowledge_os_validate_contracts", ROOT / "scripts" / "validate_contracts.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_validator_cli_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_contracts.py"), "--root", str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "CONTRACT_VALIDATION_PASSED" in result.stdout


def test_acl_downgrade_is_rejected() -> None:
    validator = MODULE.load_schema(ROOT / "schemas" / "provenance.schema.json")
    record = MODULE.load_json(ROOT / "examples" / "provenance.valid.json")
    record["sources"][0]["audience"] = "restricted"
    record["access"]["source_audiences"] = ["restricted"]
    record["access"]["effective_audience"] = "public"
    record["integrity"]["record_sha256"] = MODULE.sha256_bytes(
        MODULE.canonical_provenance_payload(record)
    )
    with pytest.raises(MODULE.ContractError, match="ACL downgrade"):
        MODULE.validate_provenance(record, validator, label="mutated-provenance")


def test_missing_evidence_source_is_rejected() -> None:
    validator = MODULE.load_schema(ROOT / "schemas" / "provenance.schema.json")
    record = MODULE.load_json(ROOT / "examples" / "provenance.valid.json")
    record["claims"][0]["evidence"][0]["source_ref"] = "src_does_not_exist"
    record["integrity"]["record_sha256"] = MODULE.sha256_bytes(
        MODULE.canonical_provenance_payload(record)
    )
    with pytest.raises(MODULE.ContractError, match="references missing source"):
        MODULE.validate_provenance(record, validator, label="mutated-provenance")


def test_broken_internal_link_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    shutil.copytree(ROOT / "examples" / "okf-bundle", bundle)
    concept = bundle / "concepts" / "knowledge-compiler.md"
    concept.write_text(
        concept.read_text(encoding="utf-8")
        + "\nSee [missing concept](/concepts/does-not-exist.md).\n",
        encoding="utf-8",
    )
    validator = MODULE.load_schema(ROOT / "schemas" / "provenance.schema.json")
    with pytest.raises(MODULE.ContractError, match="broken internal link"):
        MODULE.validate_okf_bundle(bundle, validator)


def test_dirty_release_manifest_is_rejected() -> None:
    validator = MODULE.load_schema(ROOT / "schemas" / "release-manifest.schema.json")
    manifest = MODULE.load_json(ROOT / "examples" / "release-manifest.valid.json")
    manifest["source"]["dirty"] = True
    with pytest.raises(MODULE.ContractError, match="source.dirty"):
        MODULE.validate_json_schema(validator, manifest, "dirty-manifest")
