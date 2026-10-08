"""Read-only, release-bound provenance evidence for explicit identity questions."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def _release_root() -> Path:
    candidates = [
        ROOT / "pilot/m24/canonical-release",
        Path("/app/pilot/m24/canonical-release"),
        Path.cwd() / "pilot/m24/canonical-release",
    ]
    for candidate in candidates:
        if (candidate / "manifest.json").exists() and (candidate / "artifacts/provenance.json").exists():
            return candidate
    return candidates[0]

RELEASE_ROOT = _release_root()
IDENTITY = re.compile(r'accepted claim set for ["\u201c]([^"\u201d]+)["\u201d].*?source ["\u201c]([^"\u201d]+)["\u201d]', re.I)

def retrieve_provenance_identity(question: str):
    lowered = question.casefold()
    if not all(x in lowered for x in ("retrieved-at", "source-commit", "release")):
        return None
    found = IDENTITY.search(question)
    if not found:
        return None
    topic, source_id = found.groups()
    manifest_path = RELEASE_ROOT / "manifest.json"
    evidence_path = RELEASE_ROOT / "artifacts/provenance.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw = evidence_path.read_bytes()
        expected = [x["sha256"] for x in manifest["artifacts"] if x["kind"] == "provenance"]
        if len(expected) != 1 or hashlib.sha256(raw).hexdigest() != expected[0]:
            return []
        document = json.loads(raw)
        source_commit = manifest["source"]["commit_sha"]
        release_id = manifest["release_id"]
        source_repo = manifest["source"]["repository"]
    except (OSError, KeyError, ValueError, TypeError):
        return []
    slug = re.sub(r"[^a-z0-9]+", "-", topic.casefold()).strip("-")
    matches = [x for x in document["records"]
        if str(x.get("subject", {}).get("concept_id", "")).rsplit("/", 1)[-1] == slug
        and any(y.get("source_id") == source_id for y in x.get("sources", []))]
    if len(matches) != 1:
        return []
    record = matches[0]
    sources = [x for x in record["sources"] if x.get("source_id") == source_id]
    if len(sources) != 1 or not sources[0].get("retrieved_at"):
        return []
    source = sources[0]
    origin = source.get("origin_commit")
    origin_note = (f"The upstream origin commit recorded for this captured source is {origin}. "
                   if origin else "An upstream origin commit is not recorded for this source, and no such value should be inferred. ")
    passage = (
        f"For the accepted claim set about {topic}, the canonical provenance source identity is {source_id}. "
        f"The required retrieved-at timestamp is {source['retrieved_at']}. "
        f"The accepted source-commit for the historical release is {source_commit} in repository {source_repo}. "
        f"The accepted release identity is {release_id}. "
        f"The specific provenance record identity is {record.get('synthesis_id') or record.get('review_decision_id')}. "
        f"{origin_note}"
        "These identities describe the historical accepted release and its evidence capture, not a guarantee that the source "
        "is the latest available version today. All three required identity dimensions should be checked against a newer "
        "accepted release before treating this accepted claim set as currently fresh."
    )
    return [{
        "source_id": source_id, "concept_id": record["subject"]["concept_id"],
        "section_id": f"provenance/{slug}/{source_id}", "title": topic,
        "passage_text": passage, "text": passage,
        "artifact_key": f"releases/{release_id}/artifacts/provenance.json",
        "artifact_sha256": expected[0], "provenance_record_sha256": expected[0],
        "release_id": release_id,
        "passage_text_sha256": hashlib.sha256(passage.encode()).hexdigest()
    }]
