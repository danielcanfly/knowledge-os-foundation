"""A05 source-backed hybrid retrieval adapter. No Provider, Qdrant or generated claims."""
from __future__ import annotations
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "source"
PIN = "7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3"
STOP = frozenset("the a an and or what is are of for to in on with from about how why that this does do it be can as by at into should its our under".split())
def sha(data): return hashlib.sha256(data).hexdigest()
def tokens(s):
    return [w for w in re.findall(r"[a-z][a-z0-9]{1,}", s.lower()) if w not in STOP]

class SourceError(Exception):
    def __init__(self, http_code, code):
        self.http_code, self.code = http_code, code
        super().__init__(code)

class ContextIndex:
    def __init__(self, root=SOURCE):
        self.root = Path(root)
        manifest = (self.root / "corpus.json").read_bytes()
        if sha(manifest) != PIN:
            raise SourceError(409, "manifest_integrity_failed")
        self.corpus = json.loads(manifest)
        self.release = json.loads((self.root / "release.json").read_bytes())
        if self.release["source_manifest_sha256"] != PIN or self.release["docs"] != 11 or self.release["verified_spans"] != 21:
            raise SourceError(409, "release_manifest_mismatch")
        self.release_bytes = (self.root / "release.json").read_bytes()
        self.release_sha = sha(self.release_bytes)
        self.docs = {d["filename"]: d for d in self.corpus["docs"]}
        self.sections = list(self.corpus["chunks"])
        if len({p["passage_id"] for p in self.sections}) != 21:
            raise SourceError(409, "invalid_section_identity")
        self.lex = [Counter(tokens(p["quote"])) for p in self.sections]
        self.lengths = [sum(v.values()) for v in self.lex]
        self.avglen = max(1.0, sum(self.lengths) / len(self.lex))
        self.df = Counter(w for v in self.lex for w in v)
        self.idf = {w: math.log(1 + (21 - f + .5) / (f + .5)) for w, f in self.df.items()}
        # True local term-document distributional context, NOT model embeddings or Qdrant.
        self.term_context = defaultdict(Counter)
        for row in self.lex:
            for w in row:
                for near, qty in row.items():
                    if near != w:
                        self.term_context[w][near] += min(row[w], qty)
        self.context_norms = {w: math.sqrt(sum(n*n for n in neighbors.values()))
                              for w, neighbors in self.term_context.items()}
        self.verify_original_bytes()

    def verify_original_bytes(self):
        for name, d in self.docs.items():
            p = self.root / name
            if not p.is_file() or p.is_symlink():
                raise SourceError(409, "source_missing_or_unsafe")
            raw = p.read_bytes()
            if len(raw) != d["bytes"] or sha(raw) != d["sha256"]:
                raise SourceError(409, "source_integrity_failed")
        for sec in self.sections:
            d = self.docs.get(sec["source_filename"])
            if d is None or sec["source_sha256"] != d["sha256"]:
                raise SourceError(409, "source_provenance_failed")
            raw = (self.root / d["filename"]).read_bytes()
            a, b = sec["byte_start"], sec["byte_end"]
            piece = raw[a:b]
            if not 0 <= a < b <= len(raw) or sha(piece) != sec["quote_sha256"] or piece.decode() != sec["quote"]:
                raise SourceError(409, "span_integrity_failed")
        if sha((self.root / "corpus.json").read_bytes()) != PIN or sha((self.root / "release.json").read_bytes()) != self.release_sha:
            raise SourceError(409, "release_changed")

    def _revoked(self):
        try:
            rec = json.loads((self.root / "revocations.json").read_bytes())
        except (OSError, ValueError):
            raise SourceError(409, "revocation_state_unavailable")
        if rec.get("schema") != "m27.a05.revocation_state.v1" or rec.get("release_id") != self.release["release_id"] or not isinstance(rec.get("epoch"), int) or rec["epoch"] < 1:
            raise SourceError(409, "revocation_state_invalid")
        revoked = rec.get("revoked_document_sha256")
        if not isinstance(revoked, list) or any(not isinstance(s, str) or len(s) != 64 for s in revoked):
            raise SourceError(409, "revocation_state_invalid")
        return set(revoked), rec["epoch"]

    def _similarity(self, first, second):
        a, b = self.term_context.get(first, {}), self.term_context.get(second, {})
        denom = self.context_norms.get(first, 0) * self.context_norms.get(second, 0)
        if not denom:
            return 0.0
        return sum(value * b.get(k, 0) for k, value in a.items()) / denom

    def search(self, *, question, tenant, roles, release_id, source_revision, limit=5, now=None):
        if not isinstance(tenant, str) or not isinstance(roles, list) or any(not isinstance(r, str) for r in roles):
            raise SourceError(403, "access_denied")
        allowed = self.release["tenant_acl"].get(tenant, [])
        if not allowed or "internal" not in roles or not set(roles).intersection(allowed):
            raise SourceError(403, "access_denied")
        if release_id != self.release["release_id"] or source_revision != self.release["source_revision_q34"]:
            raise SourceError(409, "release_or_revision_mismatch")
        if not isinstance(question, str) or len(question) > 2048 or not question.strip():
            raise SourceError(400, "invalid_question")
        if type(limit) is not int or not 1 <= limit <= 5:
            raise SourceError(400, "invalid_limit")
        self.verify_original_bytes()
        revoked, revocation_epoch = self._revoked()
        instant = now if now is not None else datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise SourceError(400, "invalid_time")
        if instant >= datetime.fromisoformat(self.release["expires_at"]):
            raise SourceError(412, "source_stale")
        if instant < datetime.fromisoformat(self.release["snapshot_at"]):
            raise SourceError(412, "source_future_dated")
        query_terms = set(tokens(question))
        known = query_terms.intersection(self.df)
        # Disallow a stray common source word from laundering an unsupported claim.
        if not known or (len(query_terms) >= 4 and len(known) / len(query_terms) < 0.5):
            return {"status": "abstained", "answer_generated": False,
                    "abstention_reason": "INSUFFICIENT_SOURCE_QUERY_SUPPORT",
                    "release_id": self.release["release_id"],
                    "retrieval": "BM25_plus_local_distributional_rerank_NOT_product_vector",
                    "revocation_epoch": revocation_epoch, "results": []}
        rows = []
        for i, section in enumerate(self.sections):
            if section["source_sha256"] in revoked:
                continue
            frequencies = self.lex[i]
            matched = known.intersection(frequencies)
            if not matched:
                continue
            bm25 = sum(self.idf[w] * (freq * 2.2) /
                        (freq + 1.2 * (.25 + .75 * self.lengths[i] / self.avglen))
                        for w in matched for freq in [frequencies[w]])
            semantic = sum(max((self._similarity(q, term) for term in frequencies
                                if q != term), default=0.0)
                           for q in known) / max(1, len(known))
            score = round(bm25 + .2 * min(semantic, 1.0), 8)
            rows.append((score, bm25, i))
        rows.sort(key=lambda x: (-x[0], self.sections[x[2]]["passage_id"]))
        # Strict evidence gate: zero known terms or no matching passage => abstain.
        result = []
        for score, lexical_score, i in rows[:limit]:
            s = self.sections[i]
            excerpt = (self.root / s["source_filename"]).read_bytes()[s["byte_start"]:s["byte_end"]].decode()
            citation = {"passage_id": s["passage_id"],
                        "document": s["source_filename"],
                        "source_uri": "urn:sha256:" + s["source_sha256"],
                        "document_sha256": s["source_sha256"],
                        "byte_start": s["byte_start"], "byte_end": s["byte_end"],
                        "excerpt_sha256": s["quote_sha256"],
                        "release_id": self.release["release_id"],
                        "source_revision": self.release["source_revision_q34"],
                        "revocation_epoch": revocation_epoch,
                        "snapshot_at": self.release["snapshot_at"],
                        "expires_at": self.release["expires_at"]}
            result.append({"passage_id": s["passage_id"], "excerpt": excerpt,
                           "score": score, "lexical_score": round(lexical_score, 8),
                           "citation": citation})
        return {"status": "source_passages" if result else "abstained",
                "answer_generated": False, "abstention_reason": None if result else "NO_SUPPORTED_SOURCE",
                "release_id": self.release["release_id"],
                "retrieval": "BM25_plus_local_distributional_rerank_NOT_product_vector",
                "revocation_epoch": revocation_epoch, "results": result}

if __name__ == "__main__":
    idx = ContextIndex()
    print(json.dumps({"loaded": True, "docs": len(idx.docs), "spans": len(idx.sections),
                      "terms": len(idx.df), "semantic": "local_cooccurrence_non_neural",
                      "product_qdrant_ready": False}))
