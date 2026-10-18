"""Separate OS source byte/citation check for H02 Nonprod. Not a semantic issuer."""
import hashlib
import json
from pathlib import Path
import sys

PIN = "7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def verify(payload):
    if not isinstance(payload, dict) or set(payload) != {
        "source_root", "citation", "text", "manifest_sha256"
    }:
        raise ValueError("REQUEST_SHAPE")
    if payload["manifest_sha256"] != PIN:
        raise ValueError("MANIFEST_MISMATCH")
    base = Path(payload["source_root"]).resolve(strict=True)
    manifest = base / "corpus.json"
    if manifest.is_symlink() or sha(manifest.read_bytes()) != PIN:
        raise ValueError("CORPUS_DRIFT")
    citation = payload["citation"]
    if not isinstance(citation, dict):
        raise ValueError("CITATION_SHAPE")
    name = citation.get("document")
    if not isinstance(name, str) or name != Path(name).name or not name.endswith(".md"):
        raise ValueError("DOCUMENT_PATH")
    path = base / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base):
        raise ValueError("DOCUMENT_PATH")
    raw = path.read_bytes()
    if sha(raw) != citation.get("document_sha256"):
        raise ValueError("DOCUMENT_SHA")
    begin, end = citation.get("byte_start"), citation.get("byte_end")
    if not isinstance(begin, int) or not isinstance(end, int) or not 0 <= begin < end <= len(raw):
        raise ValueError("SPAN_BOUNDS")
    span = raw[begin:end]
    if sha(span) != citation.get("excerpt_sha256"):
        raise ValueError("EXCERPT_SHA")
    text = payload["text"]
    if not isinstance(text, str) or len(text) > 512 or text not in span.decode("utf-8"):
        raise ValueError("NOT_EXACT_SOURCE_CLAUSE")
    if citation.get("source_uri") != "urn:sha256:" + sha(raw):
        raise ValueError("SOURCE_URI")
    if citation.get("release_id") != "a05context-7835ec95cee63972":
        raise ValueError("RELEASE_ID")
    return {"verified": True, "independent_os_process": True,
            "excerpt_sha256": sha(span), "document_sha256": sha(raw),
            "signed_issuer": False, "semantic_entailment_qualified": False}


def main():
    try:
        raw = sys.stdin.read(16384)
        if len(raw) >= 16384:
            raise ValueError("REQUEST_TOO_LARGE")
        result = verify(json.loads(raw))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"verified": False, "code": str(exc) if isinstance(exc, ValueError)
                          else "INDEPENDENT_READ_FAILURE", "signed_issuer": False}))
        return 3


if __name__ == "__main__":
    sys.exit(main())
