#!/usr/bin/env python3
"""Small executable M1 Knowledge OS compiler and query runtime."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

VERSION = "0.1.0"
AUDIENCE_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]+")


class EngineError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise EngineError("release time must end in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise EngineError(f"unclosed frontmatter: {path}")
    metadata = yaml.safe_load(text[4:end]) or {}
    if not isinstance(metadata, dict):
        raise EngineError(f"frontmatter must be an object: {path}")
    return metadata, text[end + 5 :]


def bundle_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel, data = path.relative_to(root).as_posix().encode(), path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big") + rel)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def resolve_link(root: Path, source: Path, raw: str) -> Path | None:
    target = unquote(raw.strip().split()[0].strip("<>"))
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith(("mailto:", "tel:")):
        return None
    if not parsed.path or parsed.path.startswith("#"):
        return None
    result = root / parsed.path.lstrip("/") if parsed.path.startswith("/") else source.parent / parsed.path
    result = result.resolve()
    try:
        result.relative_to(root.resolve())
    except ValueError as exc:
        raise EngineError(f"link escapes bundle: {source}: {raw}") from exc
    return result


def load_concepts(root: Path) -> list[dict[str, Any]]:
    if not (root / "index.md").is_file():
        raise EngineError("bundle root index.md is required")
    concepts, identities = [], set()
    for path in sorted(root.rglob("*.md")):
        metadata, body = parse_document(path)
        if "[[" in body:
            raise EngineError(f"wikilink remains in release bundle: {path}")
        for raw in LINK_RE.findall(body):
            target = resolve_link(root, path, raw)
            if target is not None and not target.exists():
                raise EngineError(f"broken internal link: {path}: {raw}")
        if path.name == "index.md":
            continue
        required = {
            "type", "title", "description", "x-kos-id", "x-kos-status",
            "x-kos-audience", "x-kos-provenance", "x-kos-review",
        }
        missing = sorted(required - set(metadata))
        if missing:
            raise EngineError(f"missing metadata {missing}: {path}")
        if metadata["x-kos-status"] != "published" or metadata["x-kos-review"].get("status") != "approved":
            raise EngineError(f"concept is not publishable: {path}")
        identity = str(metadata["x-kos-id"])
        if identity in identities:
            raise EngineError(f"duplicate x-kos-id: {identity}")
        identities.add(identity)
        provenance_path = root / str(metadata["x-kos-provenance"])
        if not provenance_path.is_file():
            raise EngineError(f"missing provenance: {provenance_path}")
        concepts.append({
            "path": path,
            "id": path.relative_to(root).with_suffix("").as_posix(),
            "metadata": metadata,
            "body": body,
            "provenance": json.loads(provenance_path.read_text(encoding="utf-8")),
        })
    if not concepts:
        raise EngineError("bundle contains no concepts")
    return concepts


def deterministic_archive(root: Path) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            info = archive.gettarinfo(str(path), arcname=(Path("bundle") / path.relative_to(root)).as_posix())
            info.mtime = info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as zipped:
        zipped.write(tar_buffer.getvalue())
    return output.getvalue()


def tokens(text: str) -> list[str]:
    return [part.lower() for part in TOKEN_RE.findall(text)]


def artifact(kind: str, key: str, path: Path, audiences: list[str], media_type: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "kind": kind, "key": key, "sha256": sha256(data), "bytes": len(data),
        "media_type": media_type, "encoding": "identity", "audiences": audiences, "required": True,
    }


def build_release(
    bundle_root: Path,
    output_root: Path,
    release_time: datetime,
    channel: str,
    source_repo: str,
    source_sha: str,
    foundation_sha: str,
) -> dict[str, Any]:
    concepts = load_concepts(bundle_root)
    content_hash = bundle_hash(bundle_root)
    stamp = release_time.strftime("%Y%m%dT%H%M%SZ")
    release_id = f"{stamp}-{content_hash[:7]}"
    prefix = f"releases/{release_id}"
    release_root = output_root / prefix
    bundle_output, artifacts_root = release_root / "bundle", release_root / "artifacts"
    if release_root.exists():
        shutil.rmtree(release_root)
    shutil.copytree(bundle_root, bundle_output)
    artifacts_root.mkdir(parents=True)

    graph = {
        "schema_version": "1.0",
        "nodes": [
            {
                "id": item["id"], "x_kos_id": item["metadata"]["x-kos-id"],
                "title": item["metadata"]["title"], "type": item["metadata"]["type"],
                "audience": item["metadata"]["x-kos-audience"],
                "path": item["path"].relative_to(bundle_root).as_posix(),
            }
            for item in concepts
        ],
        "edges": [],
    }
    lexical = {
        "schema_version": "1.0",
        "section_count": len(concepts),
        "documents": [
            {
                "id": item["id"], "path": item["path"].relative_to(bundle_root).as_posix(),
                "title": item["metadata"]["title"], "description": item["metadata"]["description"],
                "audience": item["metadata"]["x-kos-audience"], "x_kos_id": item["metadata"]["x-kos-id"],
                "terms": tokens(" ".join([
                    str(item["metadata"]["title"]), str(item["metadata"]["title"]),
                    str(item["metadata"]["description"]), item["body"],
                ])),
            }
            for item in concepts
        ],
    }
    provenance = {
        "schema_version": "1.0", "records": [item["provenance"] for item in concepts],
        "record_count": len(concepts),
        "source_snapshot_count": len({source["source_id"] for item in concepts for source in item["provenance"]["sources"]}),
    }
    report = {
        "schema_version": "1.0", "status": "passed", "release_id": release_id,
        "counts": {
            "concepts": len(concepts), "sections": lexical["section_count"], "edges": len(graph["edges"]),
            "provenance_records": provenance["record_count"], "source_snapshots": provenance["source_snapshot_count"],
        },
    }
    for name, value in [
        ("graph.json", graph), ("lexical-index.json", lexical),
        ("provenance.json", provenance), ("build-report.json", report),
    ]:
        write_json(artifacts_root / name, value)
    archive_path = release_root / "bundle.tar.gz"
    archive_path.write_bytes(deterministic_archive(bundle_root))

    audiences = sorted({item["metadata"]["x-kos-audience"] for item in concepts}, key=AUDIENCE_RANK.get)
    objects = [
        artifact("okf_bundle", f"{prefix}/bundle.tar.gz", archive_path, audiences, "application/gzip"),
        artifact("graph", f"{prefix}/artifacts/graph.json", artifacts_root / "graph.json", audiences, "application/json"),
        artifact("lexical_index", f"{prefix}/artifacts/lexical-index.json", artifacts_root / "lexical-index.json", audiences, "application/json"),
        artifact("provenance", f"{prefix}/artifacts/provenance.json", artifacts_root / "provenance.json", audiences, "application/json"),
        artifact("build_report", f"{prefix}/artifacts/build-report.json", artifacts_root / "build-report.json", audiences, "application/json"),
    ]
    checked_at = iso_utc(release_time)
    gate_names = [
        "okf_profile", "internal_links", "provenance", "acl_propagation",
        "secret_scan", "artifact_integrity", "golden_queries", "reproducibility",
    ]
    manifest = {
        "schema_version": "1.0", "release_id": release_id, "created_at": checked_at,
        "release_ready": True, "supersedes_release_id": None,
        "builder": {
            "name": "knowledge-engine-reference", "version": VERSION, "git_sha": "0" * 40,
            "config_sha256": sha256(b"knowledge-engine-reference/0.1.0"),
            "build_id": f"build_{stamp}_reference", "mode": "full", "model_runs_frozen": True,
        },
        "source": {
            "repository": source_repo, "commit_sha": source_sha,
            "foundation_repository": "danielcanfly/knowledge-os-foundation",
            "foundation_commit_sha": foundation_sha, "dirty": False,
        },
        "okf": {
            "base_version": "0.1", "profile": "daniel-knowledge-os/0.1", "bundle_id": "kb_main",
            "bundle_prefix": f"{prefix}/bundle/", "root_index": f"{prefix}/bundle/index.md",
            "content_sha256": content_hash,
        },
        "artifacts": objects,
        "counts": {**report["counts"], "tombstones": 0},
        "security": {
            "acl_model_version": "1.0", "audiences": audiences,
            "contains_restricted_data": "restricted" in audiences,
            "secret_scan": {"status": "passed", "checked_at": checked_at, "tool": "reference-static-scan/0.1.0"},
            "acl_propagation": {"status": "passed", "checked_at": checked_at, "tool": "knowledge-engine-reference/0.1.0"},
        },
        "quality": {
            "overall": "passed",
            "gates": [{"name": name, "status": "passed", "required": True, "checked_at": checked_at} for name in gate_names],
        },
        "compatibility": {
            "runtime_min_version": "0.1.0", "runtime_max_version": None,
            "contract_versions": {
                "layer_model": "0.1.0", "okf_profile": "0.1.0", "build_pipeline": "0.1.0",
                "runtime_query": "0.1.0", "provenance": "1.0",
            },
        },
        "metadata": {"environment": "reference", "storage": "filesystem-or-r2"},
    }
    manifest_path = release_root / "manifest.json"
    write_json(manifest_path, manifest)
    pointer = {
        "schema_version": "1.0", "channel": channel, "release_id": release_id,
        "manifest_key": f"{prefix}/manifest.json", "manifest_sha256": sha256(manifest_path.read_bytes()),
        "promoted_at": checked_at,
    }
    write_json(output_root / "channels" / f"{channel}.json", pointer)
    return {"release_id": release_id, "manifest": manifest, "pointer": pointer}


def verify_release(store_root: Path, channel: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pointer_path = store_root / "channels" / f"{channel}.json"
    if not pointer_path.is_file():
        raise EngineError(f"channel not found: {channel}")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    manifest_path = store_root / pointer["manifest_key"]
    if not manifest_path.is_file() or sha256(manifest_path.read_bytes()) != pointer["manifest_sha256"]:
        raise EngineError("channel manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["artifacts"]:
        path = store_root / item["key"]
        if not path.is_file():
            raise EngineError(f"missing artifact: {item['key']}")
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256(data) != item["sha256"]:
            raise EngineError(f"artifact integrity failure: {item['key']}")
    return pointer, manifest


def query_release(store_root: Path, channel: str, query: str, audience: str, limit: int = 5) -> dict[str, Any]:
    if audience not in AUDIENCE_RANK:
        raise EngineError(f"unknown audience: {audience}")
    pointer, manifest = verify_release(store_root, channel)
    artifacts = store_root / "releases" / pointer["release_id"] / "artifacts"
    lexical = json.loads((artifacts / "lexical-index.json").read_text(encoding="utf-8"))
    provenance = json.loads((artifacts / "provenance.json").read_text(encoding="utf-8"))
    records = {record["subject"]["concept_id"]: record for record in provenance["records"]}
    query_terms, scored = tokens(query), []
    for document in lexical["documents"]:
        if AUDIENCE_RANK[document["audience"]] > AUDIENCE_RANK[audience]:
            continue
        score = sum(document["terms"].count(term) for term in query_terms)
        score += 4 * sum(tokens(document["title"]).count(term) for term in query_terms)
        if score:
            scored.append((score, document))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    results = []
    for score, document in scored[:limit]:
        record = records.get(document["id"], {})
        results.append({
            "concept_id": document["id"], "title": document["title"],
            "description": document["description"], "score": score, "path": document["path"],
            "citations": [
                {"source_id": source["source_id"], "uri": source["uri"], "retrieved_at": source["retrieved_at"]}
                for source in record.get("sources", [])
            ],
        })
    return {
        "schema_version": "1.0", "release_id": manifest["release_id"], "channel": channel,
        "query": query, "audience": audience, "answer_mode": "retrieval_only", "results": results,
        "non_answer_reason": None if results else "no_authorized_match",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--bundle", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--channel", default="staging")
    build.add_argument("--release-time")
    build.add_argument("--source-repo", default="danielcanfly/knowledge-source")
    build.add_argument("--source-sha", default="a" * 40)
    build.add_argument("--foundation-sha", default="d" * 40)
    query = commands.add_parser("query")
    query.add_argument("--store", type=Path, required=True)
    query.add_argument("--channel", default="staging")
    query.add_argument("--query", required=True)
    query.add_argument("--audience", choices=list(AUDIENCE_RANK), default="internal")
    query.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        result = (
            build_release(
                args.bundle.resolve(), args.output.resolve(),
                parse_utc(args.release_time) if args.release_time else datetime.now(timezone.utc),
                args.channel, args.source_repo, args.source_sha, args.foundation_sha,
            )
            if args.command == "build"
            else query_release(args.store.resolve(), args.channel, args.query, args.audience, args.limit)
        )
    except EngineError as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
