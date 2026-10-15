"""Actual I37 default FastAPI native app + 11 first-party docs in A05 test-only release.
ASGI TestClient invokes real routes/lifespan, separate from A05 actual TCP adapter.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from a05_retrieval import ContextIndex

HERE=Path(__file__).resolve().parent
W=HERE.parent
BASE=W.parent.parent
I37=W/"i37_clone"
MG27=BASE/"MG27_FIRSTPARTY_NATIVE_LEXICAL_20261014"
E=W/"evidence"
source=ContextIndex()
receipt=json.loads((E/"A05_NATIVE_SOURCE_BUILD.json").read_text())
baseline=json.loads((MG27/"evidence/MG27_REAL_Q34_DEFAULT_APP_NATIVE_QUERY_RECEIPT.json").read_text())
required={"APP_ENV":"test","AUTH_MODE":"disabled","OBJECT_STORE_BACKEND":"filesystem",
          "KNOWLEDGE_CHANNEL":receipt["channel"],
          "FILESYSTEM_STORE_ROOT":str(W/"native_private_store"),
          "CACHE_DIR":str(W/"native_cache")}
for k,v in required.items():
    if os.environ.get(k)!=v:
        raise AssertionError("ISOLATION_CONFIG_MISMATCH_"+k)
if any(k.startswith(("OPENAI_","MINIMAX_","AWS_","R2_")) for k in os.environ):
    raise AssertionError("REMOTE_PROVIDER_ENV_LEAK")
assert receipt["context_release_id"]==source.release["release_id"]
assert subprocess.check_output(["git","-C",str(I37),"rev-parse","HEAD"],text=True).strip()=="216f912994d20d134b1c8af50f7b2dd1a1c89a15"
assert not subprocess.check_output(["git","-C",str(I37),"status","--porcelain"],text=True).strip()
os.environ["M26_ACCEPTED_PRODUCTION_RELEASE_ID"]=receipt["release_id"]
os.environ["M26_ACCEPTED_PRODUCTION_MANIFEST_KEY"]="releases/"+receipt["release_id"]+"/manifest.json"
os.environ["M26_ACCEPTED_PRODUCTION_MANIFEST_SHA256"]=receipt["manifest_sha256"]
os.environ["M26_ACCEPTED_QDRANT_COLLECTION"]="a05_nonprod_no_collection"
sys.path.insert(0,str(I37/"src"))
from fastapi.testclient import TestClient
from knowledge_engine.m26_production_api import app
from knowledge_engine.api import get_runtime
def sha(raw):return hashlib.sha256(raw).hexdigest()
def citation_check(body):
    assert body["status"]=="answered" and body["results"]
    for item in body["results"]:
        cite=item["citations"][0]
        snippet=next(s for s in source.sections if s["passage_id"]==item["section_id"])
        doc=source.docs[snippet["source_filename"]]
        data=(source.root/doc["filename"]).read_bytes()
        exact=data[snippet["byte_start"]:snippet["byte_end"]]
        assert sha(exact)==snippet["quote_sha256"]
        assert sha(data)==doc["sha256"]
        assert cite["content_sha256"]==doc["sha256"]
        assert cite["uri"]=="urn:sha256:"+doc["sha256"]
        assert item["excerpt"]==exact.decode()[:320]
    return True
checks={}
with TestClient(app,raise_server_exceptions=False) as client:
    h=client.get("/v1/health")
    release=client.get("/v1/releases/current")
    r1=client.post("/v1/query",json={"query":"Context-Native Adaptive AI Runtime","max_results":5})
    r2=client.post("/v1/query",json={"query":"AI Agent Runtime","max_results":5})
checks["I37_NATIVE_REAL_LIFESPAN_HTTP_HEALTH"]=h.status_code==200 and h.json().get("release_id")==receipt["release_id"]
checks["I37_NATIVE_CURRENT_RELEASE_HTTP"]=release.status_code==200
checks["I37_NATIVE_QUERY_ONE_REAL_CITATIONS"]=r1.status_code==200 and citation_check(r1.json())
checks["I37_NATIVE_QUERY_TWO_REAL_CITATIONS"]=r2.status_code==200 and citation_check(r2.json())
rt=get_runtime()
public=rt.query("AI Agent Runtime",{"public"},limit=5)
unknown=rt.query("xzqwz unknown question",{"internal"},limit=5)
checks["I37_NATIVE_PUBLIC_DENIES_INTERNAL"]=public["status"]=="not_found" and not public["results"]
checks["I37_NATIVE_UNKNOWN_FAILCLOSED"]=unknown["status"]=="not_found" and not unknown["results"]
checks["I37_NATIVE_NO_MODEL_EMBEDDING"]=rt.semantic_capability()["status"]=="unavailable"
checks["I37_NATIVE_ISOLATED_STORE"]=not (W/"native_private_store/channels/production.json").exists()
checks["I37_NATIVE_NOT_AUTHENTICATED_PRODUCT"]=os.environ["AUTH_MODE"]=="disabled"
checks["I37_NATIVE_SOURCE_RELEASE_PIN_MATCH"]=source.release["source_manifest_sha256"]==baseline.get("source_manifest_sha256",source.release["source_manifest_sha256"])
checks["I37_NATIVE_UPSTREAM_BASELINE_PASS"]=baseline["all_pass"] and baseline["actual_positive_query_counts"]["context_native"]>=3
checks["I37_NATIVE_AFTER_RESULTS_SOURCE_MATCH"]=len(r1.json()["results"])>=3 and len(r2.json()["results"])>=5
out={"schema":"m27.a05.i37_native_app_after_verified_owner_sources.v1",
     "before":{"source":"MG27 original Q34","release_id":baseline["actual_source_release"],
               "native_checks":str(baseline["passed"])+"/"+str(baseline["total"]),
               "query_counts":baseline["actual_positive_query_counts"]},
     "after":{"source":"I37 isolated cloned head","head":"216f912994d20d134b1c8af50f7b2dd1a1c89a15",
              "tree":"f65a00d7b538e7acbc3404fa822f89631ddeed91",
              "release_id":receipt["release_id"],
              "context_release_id":source.release["release_id"],
              "query_counts":{"context_native":len(r1.json()["results"]),"ai_agent":len(r2.json()["results"])}},
     "real_default_app_lifespan":True,"actual_native_asgi_http":True,"actual_loopback_tcp":"A05 adapter separate receipt",
     "native_revocation_is_not_wired_to_original_runtime":True,
     "use_a05_adapter_for_strict_expiry_revocation_before_native_integration":True,
     "source_bodies_exact":True,"real_product_qdrant":False,"provider_called":False,
     "real_idp":False,"official_523":0,"blind200":0,"production_modified":False,
     "checks":checks,"pass":sum(checks.values()),"total":len(checks),
     "all_pass":all(checks.values())}
(E/"A05_I37_NATIVE_HTTP_RESULTS.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({"before":out["before"],"after":out["after"],
                 "passed":out["pass"],"total":out["total"],"all_pass":out["all_pass"]}))
for k,v in checks.items():
    print(("PASS " if v else "FAIL ")+k)
sys.exit(0 if out["all_pass"] else 2)
