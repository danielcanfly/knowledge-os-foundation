#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class RelationOntologyError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RelationOntologyError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RelationOntologyError(f"root must be an object: {path}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def validate_relation_ontology(
    ontology: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(ontology),
        key=lambda item: [str(part) for part in item.absolute_path],
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise RelationOntologyError(f"schema violation at {location}: {error.message}")

    records = ontology["relation_types"]
    by_type: dict[str, dict[str, Any]] = {}
    for record in records:
        relation_type = record["type"]
        if relation_type in by_type:
            raise RelationOntologyError(f"duplicate relation type: {relation_type}")
        by_type[relation_type] = record

    for relation_type, record in sorted(by_type.items()):
        directed = record["directed"]
        symmetric = record["symmetric"]
        if directed == symmetric:
            raise RelationOntologyError(
                f"{relation_type}: exactly one of directed or symmetric must be true"
            )
        inverse = record["inverse"]
        inverse_record = by_type.get(inverse)
        if inverse_record is None:
            raise RelationOntologyError(
                f"{relation_type}: inverse is not declared: {inverse}"
            )
        if inverse_record["inverse"] != relation_type:
            raise RelationOntologyError(
                f"{relation_type}: inverse pair is not reciprocal: {inverse}"
            )
        if symmetric:
            if inverse != relation_type:
                raise RelationOntologyError(
                    f"{relation_type}: symmetric relation must be self-inverse"
                )
            if inverse_record["directed"] or not inverse_record["symmetric"]:
                raise RelationOntologyError(
                    f"{relation_type}: symmetric inverse flags are inconsistent"
                )
        else:
            if inverse == relation_type:
                raise RelationOntologyError(
                    f"{relation_type}: directed relation cannot be self-inverse"
                )
            if not inverse_record["directed"] or inverse_record["symmetric"]:
                raise RelationOntologyError(
                    f"{relation_type}: directed inverse flags are inconsistent"
                )

    fallback = ontology.get("fallback_type")
    fallback_record = by_type.get(fallback)
    if fallback_record is None:
        raise RelationOntologyError("fallback type is not declared")
    if fallback_record["retrieval_semantics"] != ["generic"]:
        raise RelationOntologyError("fallback type must use only generic retrieval semantics")

    return {
        "schema_version": "knowledge-os-relation-ontology-validation/v1",
        "status": "passed",
        "ontology_id": ontology["ontology_id"],
        "ontology_version": ontology["version"],
        "relation_type_count": len(records),
        "directed_type_count": sum(1 for item in records if item["directed"]),
        "symmetric_type_count": sum(1 for item in records if item["symmetric"]),
        "ontology_sha256": hashlib.sha256(_canonical_bytes(ontology)).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--ontology",
        type=Path,
        default=root / "examples/relation-ontology.valid.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=root / "schemas/relation-ontology-v0.1.schema.json",
    )
    args = parser.parse_args()
    try:
        report = validate_relation_ontology(_load(args.ontology), _load(args.schema))
    except RelationOntologyError as exc:
        print(f"RELATION_ONTOLOGY_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print("RELATION_ONTOLOGY_VALIDATION_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
