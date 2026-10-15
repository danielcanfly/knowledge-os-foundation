#!/usr/bin/env python3
"""Create exact first-party corpus and ephemeral independent test auth.
Never rewrite pinned sources or manifest if they already exist.
"""
import hashlib
import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
defs = {
    "atlas-A": ("tenant-alpha", "atlas.txt",
                "Atlas nonproduction trial uses exactly two review stages: intake and verification.\n",
                "atlas_stages",
                r"The Atlas trial (?:has|uses) two (?:distinct )?review stages\."),
    "delta-B": ("tenant-alpha", "delta.txt",
                "Delta notebook executes every four hours during the local validation exercise.\n",
                "delta_cadence",
                r"The Delta notebook (?:runs|executes) (?:once )?every four hours\."),
    "cedar-C": ("tenant-beta", "cedar.txt",
                "Cedar sandbox retains five audit records during the tenant-isolated exercise.\n",
                "cedar_audit",
                r"The Cedar sandbox (?:keeps|stores) five audit records\."),
}
manifest = {}
for source_id, (tenant, name, statement, fact_key, pattern) in defs.items():
    p = DATA / name
    if not p.exists():
        p.write_bytes(statement.encode())
    blob = p.read_bytes()
    fact_bytes = statement.strip().encode()
    if fact_bytes not in blob:
        raise SystemExit("source mismatch; refusing manifest rebuild")
    start = blob.index(fact_bytes)
    manifest[source_id] = {
        "tenant": tenant, "file": name, "sha256": hashlib.sha256(blob).hexdigest(),
        "fact": {
            "key": fact_key, "start": start, "end": start + len(fact_bytes),
            "quote": statement.strip(), "paraphrase_regex": pattern,
        },
    }
mf = DATA / "manifest.json"
if mf.exists():
    if json.loads(mf.read_text()) != manifest:
        raise SystemExit("manifest mismatch; not updating provenance")
else:
    mf.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
tokens = DATA / "tokens.json"
if not tokens.exists():
    tokens.write_text(json.dumps({"tenant-alpha": secrets.token_urlsafe(32),
                                  "tenant-beta": secrets.token_urlsafe(32)}))
rev = DATA / "revocations.json"
if not rev.exists():
    rev.write_text('{"revoked":[]}\n')
print("Pinned A04 first-party nonprod fixture corpus:", len(manifest), "documents", "ephemeral ACL tokens created")
