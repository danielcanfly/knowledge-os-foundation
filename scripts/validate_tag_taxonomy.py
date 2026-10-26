#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class TagTaxonomyError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TagTaxonomyError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TagTaxonomyError(f"root must be an object: {path}")
    return value


def validate_tag_taxonomy(taxonomy: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(taxonomy), key=lambda e: list(e.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise TagTaxonomyError(f"schema violation at {location}: {error.message}")
    canonical: dict[str, str] = {}
    for dimension, tags in taxonomy["dimensions"].items():
        if tags != sorted(tags):
            raise TagTaxonomyError(f"{dimension}: canonical tags must be sorted")
        for tag in tags:
            if tag in canonical:
                raise TagTaxonomyError(f"canonical tag belongs to multiple dimensions: {tag}")
            canonical[tag] = dimension
    aliases = taxonomy["tag_aliases"]
    if list(aliases) != sorted(aliases):
        raise TagTaxonomyError("tag aliases must be sorted")
    for alias, target in aliases.items():
        if alias in canonical:
            raise TagTaxonomyError(f"alias shadows canonical tag: {alias}")
        if target not in canonical:
            raise TagTaxonomyError(f"alias target is not canonical: {target}")
        if target in aliases:
            raise TagTaxonomyError(f"alias chain is forbidden: {alias}")
    canonical_bytes = (json.dumps(taxonomy, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return {
        "schema_version": "knowledge-os-tag-taxonomy-validation/v1",
        "status": "passed",
        "canonical_tag_count": len(canonical),
        "tag_alias_count": len(aliases),
        "taxonomy_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, default=root / "examples/tag-taxonomy.valid.json")
    parser.add_argument("--schema", type=Path, default=root / "schemas/tag-taxonomy-v0.1.schema.json")
    args = parser.parse_args()
    try:
        report = validate_tag_taxonomy(_load(args.taxonomy), _load(args.schema))
    except TagTaxonomyError as exc:
        print(f"TAG_TAXONOMY_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print("TAG_TAXONOMY_VALIDATION_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
