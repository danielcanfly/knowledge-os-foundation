from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_tag_taxonomy", ROOT / "scripts" / "validate_tag_taxonomy.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validate(value: dict) -> dict:
    return MODULE.validate_tag_taxonomy(value, load("schemas/tag-taxonomy-v0.1.schema.json"))


def test_normative_taxonomy_is_deterministic() -> None:
    value = load("examples/tag-taxonomy.valid.json")
    assert validate(value) == validate(value)
    assert validate(value)["canonical_tag_count"] == 16


@pytest.mark.parametrize("field", ["sigma_color", "x", "y", "size"])
def test_renderer_fields_fail_closed(field: str) -> None:
    value = load("examples/tag-taxonomy.valid.json")
    value[field] = "forbidden"
    with pytest.raises(MODULE.TagTaxonomyError, match="schema violation"):
        validate(value)


def test_unknown_alias_target_fails() -> None:
    value = load("examples/tag-taxonomy.valid.json")
    value["tag_aliases"]["unknown"] = "not-canonical"
    with pytest.raises(MODULE.TagTaxonomyError, match="not canonical"):
        validate(value)


def test_alias_shadowing_fails() -> None:
    value = load("examples/tag-taxonomy.valid.json")
    value["tag_aliases"]["agents"] = "rag"
    value["tag_aliases"] = dict(sorted(value["tag_aliases"].items()))
    with pytest.raises(MODULE.TagTaxonomyError, match="shadows"):
        validate(value)


def test_duplicate_tag_across_dimensions_fails() -> None:
    value = load("examples/tag-taxonomy.valid.json")
    value["dimensions"]["concern"].append("agents")
    value["dimensions"]["concern"].sort()
    with pytest.raises(MODULE.TagTaxonomyError, match="multiple dimensions"):
        validate(value)


def test_unsorted_registry_fails() -> None:
    value = copy.deepcopy(load("examples/tag-taxonomy.valid.json"))
    value["dimensions"]["domain"] = list(reversed(value["dimensions"]["domain"]))
    with pytest.raises(MODULE.TagTaxonomyError, match="sorted"):
        validate(value)
