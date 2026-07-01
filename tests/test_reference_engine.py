from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "knowledge_engine_reference", ROOT / "reference" / "knowledge_engine.py"
)
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)


def build(tmp_path: Path) -> Path:
    output = tmp_path / "store"
    ENGINE.build_release(
        ROOT / "examples" / "okf-bundle",
        output,
        ENGINE.parse_utc("2026-07-02T12:00:00Z"),
        "staging",
        "danielcanfly/knowledge-source",
        "a" * 40,
        "d" * 40,
    )
    return output


def test_reference_build_matches_contract(tmp_path: Path) -> None:
    store = build(tmp_path)
    pointer = json.loads((store / "channels" / "staging.json").read_text(encoding="utf-8"))
    manifest_path = store / pointer["manifest_key"]
    validator_spec = importlib.util.spec_from_file_location(
        "knowledge_os_contract_validator", ROOT / "scripts" / "validate_contracts.py"
    )
    assert validator_spec and validator_spec.loader
    validator_module = importlib.util.module_from_spec(validator_spec)
    sys.modules[validator_spec.name] = validator_module
    validator_spec.loader.exec_module(validator_module)
    validator = validator_module.load_schema(ROOT / "schemas" / "release-manifest.schema.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validator_module.validate_release_manifest(manifest, validator, store)


def test_authorized_query_returns_concept(tmp_path: Path) -> None:
    store = build(tmp_path)
    result = ENGINE.query_release(store, "staging", "knowledge compiler", "internal")
    assert result["results"][0]["concept_id"] == "concepts/knowledge-compiler"
    assert result["results"][0]["citations"]


def test_acl_filter_returns_structured_non_answer(tmp_path: Path) -> None:
    store = build(tmp_path)
    result = ENGINE.query_release(store, "staging", "knowledge compiler", "public")
    assert result["results"] == []
    assert result["non_answer_reason"] == "no_authorized_match"


def test_tampered_artifact_is_rejected(tmp_path: Path) -> None:
    store = build(tmp_path)
    pointer = json.loads((store / "channels" / "staging.json").read_text(encoding="utf-8"))
    graph = store / "releases" / pointer["release_id"] / "artifacts" / "graph.json"
    graph.write_text(graph.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ENGINE.EngineError, match="artifact integrity failure"):
        ENGINE.query_release(store, "staging", "knowledge compiler", "internal")
