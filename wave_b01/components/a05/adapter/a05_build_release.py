"""A05 builds a new immutable, scoped Owner first-party retrieval release. Offline only."""
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
MG21 = WORK.parent.parent / "MG21_FIRST_PARTY_GROUNDED_NONPROD_20261014" / "corpus"
SOURCE = WORK / "source"
EXPECTED_MANIFEST_SHA = "7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3"
EXPECTED_Q34 = "89f1d7be1623cd6926a69e38871544eefe39e584"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def build():
    original = (MG21 / "corpus.json").read_bytes()
    if sha(original) != EXPECTED_MANIFEST_SHA:
        raise ValueError("UNSIGNED_OR_CHANGED_OWNER_CORPUS")
    corpus = json.loads(original)
    if not (corpus.get("owner_source_controller_confirmed") is True
            and corpus["subject_q34_head"] == EXPECTED_Q34
            and corpus["real_first_party_docs"] == 11
            and corpus["grounded_quote_count"] == 21
            and len(corpus["docs"]) == 11 and len(corpus["chunks"]) == 21
            and not corpus["original523_included"] and not corpus["blind200_included"]
            and not corpus["third_party_mixed_corpus_qualified"]
            and not corpus["production_qualified"]):
        raise ValueError("OUT_OF_RIGHTS_SCOPE")
    SOURCE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (SOURCE / "corpus.json").exists() and (SOURCE / "corpus.json").read_bytes() != original:
        raise ValueError("IMMUTABLE_MANIFEST_CONFLICT")
    (SOURCE / "corpus.json").write_bytes(original)
    docs = {}
    for doc in corpus["docs"]:
        filename = doc["filename"]
        if Path(filename).name != filename or not filename.endswith(".md"):
            raise ValueError("SOURCE_PATH_INVALID")
        raw = (MG21 / filename).read_bytes()
        if len(raw) != doc["bytes"] or sha(raw) != doc["sha256"]:
            raise ValueError("SOURCE_DOCUMENT_CHANGED")
        p = SOURCE / filename
        if p.exists() and p.read_bytes() != raw:
            raise ValueError("IMMUTABLE_DOCUMENT_CONFLICT")
        p.write_bytes(raw)
        docs[filename] = raw
    seen = set()
    for chunk in corpus["chunks"]:
        pid, name = chunk["passage_id"], chunk["source_filename"]
        if pid in seen or name not in docs:
            raise ValueError("SOURCE_SPAN_DUPLICATED_OR_MISSING")
        seen.add(pid)
        raw = docs[name]
        a, b = chunk["byte_start"], chunk["byte_end"]
        if not 0 <= a < b <= len(raw):
            raise ValueError("SPAN_OUT_OF_BOUNDS")
        piece = raw[a:b]
        if sha(piece) != chunk["quote_sha256"] or piece.decode("utf-8") != chunk["quote"]:
            raise ValueError("SPAN_BYTES_MISMATCH")
        if chunk["source_sha256"] != sha(raw):
            raise ValueError("SOURCE_PROVENANCE_MISMATCH")
    created = datetime.fromisoformat(corpus["created_utc"])
    expires = created + timedelta(days=90)
    release = {
        "schema": "m27.a05.owner_context_release.v1",
        "release_id": "a05context-" + EXPECTED_MANIFEST_SHA[:16],
        "source_manifest_sha256": EXPECTED_MANIFEST_SHA,
        "source_revision_q34": EXPECTED_Q34,
        "owner_first_party_only": True,
        "tenant_acl": {"owner-internal": ["internal"]},
        "rights": "OWNER_DECLARED_FIRST_PARTY_ARCHITECTURE_DOCS_ONLY",
        "docs": 11,
        "verified_spans": 21,
        "snapshot_at": created.isoformat(),
        "expires_at": expires.isoformat(),
        "semantic_method": "local_cooccurrence_distributional_rerank_not_neural_embeddings",
        "product_qdrant_ready": False,
        "official_app_ready": False,
        "source_release_ci_signed": False,
        "real_idp_authorized": False,
        "official_523_included": False,
        "independent_blind200_included": False,
        "production_qualified": False
    }
    release_path = SOURCE / "release.json"
    release_bytes = encoded(release)
    if release_path.exists() and release_path.read_bytes() != release_bytes:
        raise ValueError("IMMUTABLE_RELEASE_CONFLICT")
    release_path.write_bytes(release_bytes)
    revoke = SOURCE / "revocations.json"
    if not revoke.exists():
        revoke.write_bytes(encoded({"schema": "m27.a05.revocation_state.v1",
                                     "release_id": release["release_id"],
                                     "epoch": 1, "revoked_document_sha256": []}))
    return {"release_id": release["release_id"], "release_sha256": sha(release_bytes),
            "manifest_sha256": EXPECTED_MANIFEST_SHA, "docs": 11, "spans": 21,
            "source_path": str(SOURCE), "expires_at": expires.isoformat()}

if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
