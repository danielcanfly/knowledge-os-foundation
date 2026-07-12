from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "knowledge_os_validate_relation_ontology",
    ROOT / "scripts" / "validate_relation_ontology.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _validate(value: dict) -> dict:
    return MODULE.validate_relation_ontology(
        value,
        _load("schemas/relation-ontology-v0.1.schema.json"),
    )


def test_normative_ontology_passes_deterministically() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    first = _validate(ontology)
    second = _validate(ontology)
    assert first == second
    assert first["relation_type_count"] == 20
    assert first["directed_type_count"] == 16
    assert first["symmetric_type_count"] == 4


def test_invalid_fixture_fails() -> None:
    with pytest.raises(MODULE.RelationOntologyError):
        _validate(_load("examples/relation-ontology.invalid.json"))


def test_unknown_schema_property_fails() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    ontology["relation_types"][0]["sigma_color"] = "#fff"
    with pytest.raises(MODULE.RelationOntologyError, match="schema violation"):
        _validate(ontology)


def test_duplicate_type_fails() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    ontology["relation_types"].append(copy.deepcopy(ontology["relation_types"][0]))
    with pytest.raises(MODULE.RelationOntologyError, match="duplicate relation type"):
        _validate(ontology)


def test_missing_inverse_fails() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    ontology["relation_types"] = [
        item for item in ontology["relation_types"] if item["type"] != "has_subtype"
    ]
    with pytest.raises(MODULE.RelationOntologyError, match="inverse is not declared"):
        _validate(ontology)


def test_non_reciprocal_inverse_fails() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    by_type = {item["type"]: item for item in ontology["relation_types"]}
    by_type["has_subtype"]["inverse"] = "part_of"
    with pytest.raises(MODULE.RelationOntologyError, match="not reciprocal"):
        _validate(ontology)


def test_symmetric_relation_must_be_self_inverse() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    by_type = {item["type"]: item for item in ontology["relation_types"]}
    by_type["contrasts_with"]["inverse"] = "complements"
    with pytest.raises(MODULE.RelationOntologyError, match="not reciprocal|self-inverse"):
        _validate(ontology)


def test_directed_and_symmetric_flags_are_exclusive() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    ontology["relation_types"][0]["symmetric"] = True
    with pytest.raises(MODULE.RelationOntologyError):
        _validate(ontology)


def test_fallback_is_fixed_and_generic() -> None:
    ontology = _load("examples/relation-ontology.valid.json")
    ontology["fallback_type"] = "uses"
    with pytest.raises(MODULE.RelationOntologyError):
        _validate(ontology)
