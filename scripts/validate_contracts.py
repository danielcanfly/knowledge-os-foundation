#!/usr/bin/env python3
"""Validate the Knowledge OS executable contract fixtures.

The validator intentionally checks more than JSON Schema:
- release artifact hashes and byte counts
- required quality gates and artifact kinds
- OKF Profile frontmatter, links, identity and provenance paths
- provenance source references, record hash and ACL propagation
- negative fixtures must fail
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker

AUDIENCE_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
KOS_ID_RE = re.compile(r"^ko_[0-9A-HJKMNP-TV-Z]{26}$")
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
REQUIRED_RELEASE_KINDS = {"okf_bundle", "graph", "provenance", "build_report"}
REQUIRED_QUALITY_GATES = {
    "okf_profile", "internal_links", "provenance", "acl_propagation",
    "secret_scan", "artifact_integrity", "golden_queries", "reproducibility",
}


class ContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrontmatterDocument:
    metadata: dict[str, Any]
    body: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContractError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def load_schema(path: Path) -> Draft202012Validator:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_json_schema(validator: Draft202012Validator, instance: Any, label: str) -> None:
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        details = []
        for error in errors[:20]:
            where = ".".join(str(x) for x in error.absolute_path) or "<root>"
            details.append(f"{where}: {error.message}")
        raise ContractError(f"{label} failed JSON Schema:\n  " + "\n  ".join(details))


def parse_frontmatter(path: Path, allow_missing: bool = False) -> FrontmatterDocument:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        if allow_missing:
            return FrontmatterDocument({}, text)
        raise ContractError(f"OKFP-001 missing frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ContractError(f"OKFP-001 unclosed frontmatter: {path}")
    try:
        metadata = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ContractError(f"OKFP-001 invalid YAML: {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ContractError(f"OKFP-001 frontmatter must be an object: {path}")
    return FrontmatterDocument(metadata, text[end + 5 :])


def resolve_internal_link(bundle_root: Path, source_path: Path, raw_target: str) -> Path | None:
    target = unquote(raw_target.strip().split()[0].strip("<>"))
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith(("mailto:", "tel:")):
        return None
    path_part = parsed.path
    if not path_part or path_part.startswith("#"):
        return None
    resolved = bundle_root / path_part.lstrip("/") if path_part.startswith("/") else source_path.parent / path_part
    if path_part.endswith("/"):
        resolved = resolved / "index.md"
    try:
        resolved = resolved.resolve()
        resolved.relative_to(bundle_root.resolve())
    except (ValueError, OSError) as exc:
        raise ContractError(f"OKFP-005 link escapes bundle: {source_path}: {raw_target}") from exc
    return resolved


def validate_okf_bundle(bundle_root: Path, provenance_validator: Draft202012Validator) -> None:
    if not bundle_root.is_dir():
        raise ContractError(f"Bundle directory not found: {bundle_root}")
    root_index = bundle_root / "index.md"
    if not root_index.is_file():
        raise ContractError("OKFP-001 root index.md is required by this package")
    root_doc = parse_frontmatter(root_index, allow_missing=True)
    if root_doc.metadata:
        if root_doc.metadata.get("okf_version") != "0.1":
            raise ContractError("Root index okf_version must be 0.1")
        if root_doc.metadata.get("x-kos-profile") != "daniel-knowledge-os/0.1":
            raise ContractError("Root index x-kos-profile mismatch")

    seen_ids: dict[str, Path] = {}
    concept_count = 0
    for path in sorted(bundle_root.rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            doc = parse_frontmatter(path, allow_missing=True)
            body = doc.body
        else:
            concept_count += 1
            doc = parse_frontmatter(path)
            meta = doc.metadata
            body = doc.body
            required = [
                "type", "title", "description", "timestamp", "x-kos-id",
                "x-kos-status", "x-kos-audience", "x-kos-confidence", "x-kos-review",
            ]
            missing = [key for key in required if key not in meta]
            if missing:
                raise ContractError(f"OKFP-002 missing {missing}: {path}")
            for key in ("type", "title", "description"):
                if not isinstance(meta[key], str) or not meta[key].strip():
                    raise ContractError(f"OKFP-002 empty {key}: {path}")
            if not 20 <= len(meta["description"]) <= 300:
                raise ContractError(f"OKFP-002 description length out of range: {path}")
            timestamp = meta["timestamp"]
            timestamp_ok = False
            if isinstance(timestamp, str):
                timestamp_ok = bool(UTC_RE.match(timestamp))
            elif isinstance(timestamp, datetime):
                timestamp_ok = timestamp.tzinfo is not None and timestamp.utcoffset() == timezone.utc.utcoffset(timestamp)
            if not timestamp_ok:
                raise ContractError(f"OKFP-004 timestamp must be UTC ISO 8601: {path}")
            kos_id = meta["x-kos-id"]
            if not isinstance(kos_id, str) or not KOS_ID_RE.match(kos_id):
                raise ContractError(f"OKFP-003 malformed x-kos-id: {path}")
            if kos_id in seen_ids:
                raise ContractError(f"OKFP-003 duplicate x-kos-id: {path} and {seen_ids[kos_id]}")
            seen_ids[kos_id] = path
            if meta["x-kos-status"] not in {"published", "deprecated"}:
                raise ContractError(f"OKFP-008 non-publishable status: {path}")
            if meta["x-kos-audience"] not in AUDIENCE_RANK:
                raise ContractError(f"OKFP-009 invalid audience: {path}")
            confidence = meta["x-kos-confidence"]
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                raise ContractError(f"OKFP-002 invalid confidence: {path}")
            review = meta["x-kos-review"]
            if not isinstance(review, dict) or review.get("status") != "approved":
                raise ContractError(f"OKFP-008 published concept is not approved: {path}")
            provenance_rel = meta.get("x-kos-provenance")
            if not provenance_rel:
                raise ContractError(f"OKFP-007 missing provenance: {path}")
            provenance_path = (bundle_root / provenance_rel).resolve()
            try:
                provenance_path.relative_to(bundle_root.resolve())
            except ValueError as exc:
                raise ContractError(f"OKFP-007 provenance escapes bundle: {path}") from exc
            if not provenance_path.is_file():
                raise ContractError(f"OKFP-007 provenance file not found: {path}: {provenance_rel}")
            validate_provenance(load_json(provenance_path), provenance_validator, label=str(provenance_path))

        if WIKILINK_RE.search(body):
            raise ContractError(f"OKFP-006 wikilink remains in release bundle: {path}")
        for target in MD_LINK_RE.findall(body):
            resolved = resolve_internal_link(bundle_root, path, target)
            if resolved is not None and not resolved.exists():
                raise ContractError(f"OKFP-005 broken internal link: {path}: {target}")

    if concept_count < 1:
        raise ContractError("Release bundle must contain at least one concept")


def canonical_provenance_payload(record: dict[str, Any]) -> bytes:
    clone = json.loads(json.dumps(record))
    clone["integrity"]["record_sha256"] = ""
    return json.dumps(clone, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def validate_provenance(record: dict[str, Any], validator: Draft202012Validator, *, label: str = "provenance") -> None:
    validate_json_schema(validator, record, label)
    sources = record["sources"]
    source_ids = [source["source_id"] for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ContractError(f"{label}: duplicate source_id")
    claim_ids = [claim["claim_id"] for claim in record["claims"]]
    if len(claim_ids) != len(set(claim_ids)):
        raise ContractError(f"{label}: duplicate claim_id")
    source_id_set = set(source_ids)
    for claim in record["claims"]:
        for evidence in claim["evidence"]:
            if evidence["source_ref"] not in source_id_set:
                raise ContractError(f"{label}: claim {claim['claim_id']} references missing source {evidence['source_ref']}")
    declared = set(record["access"]["source_audiences"])
    actual = {source["audience"] for source in sources}
    if declared != actual:
        raise ContractError(f"{label}: source_audiences {declared} do not match actual {actual}")
    maximum = max(actual, key=lambda audience: AUDIENCE_RANK[audience])
    effective = record["access"]["effective_audience"]
    declassified = record["access"]["declassified"]
    if not declassified and AUDIENCE_RANK[effective] < AUDIENCE_RANK[maximum]:
        raise ContractError(f"{label}: ACL downgrade {maximum} -> {effective} without declassification")
    if declassified:
        decision = record["access"]["declassification"]
        if decision["from"] != maximum or decision["to"] != effective:
            raise ContractError(f"{label}: declassification endpoints do not match ACL calculation")
        if AUDIENCE_RANK[effective] >= AUDIENCE_RANK[maximum]:
            raise ContractError(f"{label}: declassification must lower restriction")
    expected_hash = sha256_bytes(canonical_provenance_payload(record))
    actual_hash = record["integrity"]["record_sha256"]
    if expected_hash != actual_hash:
        raise ContractError(f"{label}: provenance record_sha256 mismatch")


def canonical_bundle_hash(bundle_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in bundle_root.rglob("*") if p.is_file()):
        rel = path.relative_to(bundle_root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big")); digest.update(rel)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


def validate_release_manifest(manifest: dict[str, Any], validator: Draft202012Validator, object_root: Path) -> None:
    validate_json_schema(validator, manifest, "release-manifest.valid.json")
    release_id = manifest["release_id"]
    kinds = [artifact["kind"] for artifact in manifest["artifacts"]]
    missing_kinds = REQUIRED_RELEASE_KINDS - set(kinds)
    if missing_kinds:
        raise ContractError(f"Release missing required artifact kinds: {sorted(missing_kinds)}")
    keys = [artifact["key"] for artifact in manifest["artifacts"]]
    if len(keys) != len(set(keys)):
        raise ContractError("Release contains duplicate artifact keys")
    manifest_audiences = set(manifest["security"]["audiences"])
    for artifact in manifest["artifacts"]:
        if f"releases/{release_id}/" not in artifact["key"]:
            raise ContractError(f"Artifact key belongs to another release: {artifact['key']}")
        path = object_root / artifact["key"]
        if not path.is_file():
            raise ContractError(f"Artifact object missing: {path}")
        data = path.read_bytes()
        if sha256_bytes(data) != artifact["sha256"]:
            raise ContractError(f"Artifact SHA-256 mismatch: {artifact['key']}")
        if len(data) != artifact["bytes"]:
            raise ContractError(f"Artifact byte count mismatch: {artifact['key']}")
        if not set(artifact["audiences"]).issubset(manifest_audiences):
            raise ContractError(f"Artifact audience not declared by release: {artifact['key']}")
    gate_names = [gate["name"] for gate in manifest["quality"]["gates"]]
    if len(gate_names) != len(set(gate_names)):
        raise ContractError("Duplicate quality gate names")
    missing_gates = REQUIRED_QUALITY_GATES - set(gate_names)
    if missing_gates:
        raise ContractError(f"Missing quality gates: {sorted(missing_gates)}")
    root_index = object_root / manifest["okf"]["root_index"]
    if not root_index.is_file():
        raise ContractError(f"Manifest root_index does not exist: {root_index}")
    bundle_prefix = object_root / manifest["okf"]["bundle_prefix"]
    if canonical_bundle_hash(bundle_prefix) != manifest["okf"]["content_sha256"]:
        raise ContractError("OKF bundle content_sha256 mismatch")


def expect_failure(fn, label: str) -> None:
    try:
        fn()
    except (ContractError, Exception) as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        return
    raise ContractError(f"Negative fixture unexpectedly passed: {label}")


def validate_all(root: Path) -> None:
    release_validator = load_schema(root / "schemas/release-manifest.schema.json")
    provenance_validator = load_schema(root / "schemas/provenance.schema.json")
    valid_provenance = load_json(root / "examples/provenance.valid.json")
    validate_provenance(valid_provenance, provenance_validator, label="provenance.valid.json")
    valid_manifest = load_json(root / "examples/release-manifest.valid.json")
    validate_json_schema(release_validator, valid_manifest, "release-manifest.valid.json")
    validate_okf_bundle(root / "examples/okf-bundle", provenance_validator)
    invalid_manifest = load_json(root / "examples/release-manifest.invalid.json")
    expect_failure(lambda: validate_json_schema(release_validator, invalid_manifest, "release-manifest.invalid.json"), "release-manifest.invalid.json")
    invalid_provenance = load_json(root / "examples/provenance.invalid.json")
    expect_failure(lambda: validate_provenance(invalid_provenance, provenance_validator, label="provenance.invalid.json"), "provenance.invalid.json")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Contract package root")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        validate_all(args.root.resolve())
    except ContractError as exc:
        print(f"CONTRACT_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print("CONTRACT_VALIDATION_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
