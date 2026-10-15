"""Derive A05 I37-native test-only release from already verified MG27 release bytes.
No Qdrant deployment, no change to original MG27 or I37 source.
"""
import hashlib
import json
from pathlib import Path
from a05_retrieval import ContextIndex

HERE = Path(__file__).resolve().parent
W = HERE.parent
MG27 = W.parent.parent / "MG27_FIRSTPARTY_NATIVE_LEXICAL_20261014" / "private_store"
OLD = "mg27ownerlex-7835ec95cee63972"
CHANNEL = "a05-owner-context-nonprod-only"
NEW = "a05native-" + "7835ec95cee63972"
STORE = W / "native_private_store"

def sha(x): return hashlib.sha256(x).hexdigest()
def enc(x): return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def build():
    idx = ContextIndex()
    upstream = MG27/"releases"/OLD
    original_manifest = json.loads((upstream/"manifest.json").read_bytes())
    if original_manifest["release_id"] != OLD or len(original_manifest["artifacts"]) != 7:
        raise ValueError("NATIVE_UPSTREAM_INVALID")
    dest = STORE/"releases"/NEW
    dest.mkdir(parents=True, exist_ok=True)
    collected = {}
    for art in original_manifest["artifacts"]:
        kind = art["kind"]
        raw = (upstream/(kind+".json")).read_bytes()
        if len(raw)!=art["bytes"] or sha(raw)!=art["sha256"]:
            raise ValueError("NATIVE_UPSTREAM_ARTIFACT_CHANGED")
        obj=json.loads(raw)
        if kind=="graph":
            obj["release_id"]=NEW
        if kind=="graph_v2":
            obj["release"]["release_id"]=NEW
        if kind=="source_documents":
            for record in obj["documents"]:
                original=idx.docs[record["filename"]]
                if record["sha256"]!=original["sha256"] or sha(record["body"].encode())!=original["sha256"]:
                    raise ValueError("A05_SOURCE_LINEAGE_BROKEN")
        if kind=="semantic_inputs":
            if obj.get("embeddings_ready") is not False or len(obj["documents"])!=21:
                raise ValueError("FAKE_SEMANTIC_EMBEDDINGS")
            for section in obj["documents"]:
                match=next(x for x in idx.sections if x["passage_id"]==section["section_id"])
                if section["quote_sha256"]!=match["quote_sha256"] or section["content"]!=match["quote"]:
                    raise ValueError("INVALID_NATIVE_SOURCE_SPAN")
        data=enc(obj)
        filename=dest/(kind+".json")
        if filename.exists() and filename.read_bytes()!=data:
            raise ValueError("NATIVE_IMMUTABILITY_CONFLICT")
        filename.write_bytes(data)
        collected[kind]={"kind":kind,"key":f"releases/{NEW}/{kind}.json",
                         "bytes":len(data),"sha256":sha(data)}
    manifest = dict(original_manifest)
    manifest.update({"release_id":NEW,
                     "a05_context_release_id":idx.release["release_id"],
                     "a05_context_release_sha256":idx.release_sha,
                     "a05_context_acl_required":True,
                     "a05_context_revocation_requires_adapter":True,
                     "owner_source_manifest_sha256":idx.release["source_manifest_sha256"],
                     "official_default_app_ready":False, "real_qdrant_collection_ready":False,
                     "qualified_source_backed_generation":False,
                     "nonprod_firstparty_adapter_only":True,
                     "production_qualified":False})
    manifest["artifacts"]=[collected[a["kind"]] for a in original_manifest["artifacts"]]
    data=enc(manifest)
    target=dest/"manifest.json"
    if target.exists() and target.read_bytes()!=data:
        raise ValueError("NATIVE_MANIFEST_IMMUTABILITY_CONFLICT")
    target.write_bytes(data)
    pointer={"release_id":NEW,"manifest_key":f"releases/{NEW}/manifest.json",
             "manifest_sha256":sha(data),"scope":"A05_NONPROD_NATIVE_NOT_PRODUCTION"}
    ch=STORE/"channels"/(CHANNEL+".json")
    ch.parent.mkdir(exist_ok=True)
    if ch.exists() and ch.read_bytes()!=enc(pointer):
        raise ValueError("NATIVE_CHANNEL_CHANGED")
    ch.write_bytes(enc(pointer))
    if (STORE/"channels/production.json").exists():
        raise ValueError("FORBIDDEN_PRODUCTION_POINTER")
    receipt={"schema":"m27.a05.i37_native_owner_source_release.v1",
             "release_id":NEW,"manifest_sha256":sha(data),"channel":CHANNEL,
             "context_release_id":idx.release["release_id"],
             "original_mg27_release":OLD,"artifacts":collected,
             "docs":11,"spans":21,"qdrant_deployed":False,
             "native_citation_governance_caveat":"use A05 adapter for revocation and expiry enforcement",
             "production_ready":False}
    p=W/"evidence"/"A05_NATIVE_SOURCE_BUILD.json"
    p.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in receipt.items() if k!="artifacts"},sort_keys=True))
    return receipt
if __name__=="__main__":
    build()
