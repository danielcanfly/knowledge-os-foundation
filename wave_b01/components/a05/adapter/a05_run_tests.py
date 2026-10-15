"""A05 independent OS/loopback HTTP positive, negative, source tamper & revocation tests."""
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from a05_retrieval import ContextIndex, SourceError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EV = ROOT / "evidence"
SRC = ROOT / "source"
EV.mkdir(exist_ok=True)
(EV / "raw").mkdir(exist_ok=True)
cases = []
def sha(v): return hashlib.sha256(v).hexdigest()
def record(name, fn):
    now = time.monotonic()
    try:
        observation = fn()
        ok = bool(observation)
        detail = {"result": observation}
    except Exception as exc:
        ok = False
        detail = {"exception": repr(exc)}
    result = {"name": name, "pass": ok, "duration_ms": round((time.monotonic()-now)*1000,3), **detail}
    cases.append(result)
    with (EV / "raw" / "a05_cases.ndjson").open("a") as out:
        out.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    return ok

def refuse(code, fn, error=None):
    try:
        fn()
    except SourceError as e:
        return e.http_code == code and (error is None or e.code == error)
    return False

index = ContextIndex()
release = index.release
kwargs = {"tenant": "owner-internal", "roles": ["internal"],
          "release_id": release["release_id"],
          "source_revision": release["source_revision_q34"]}
query = "What is the purpose of M27 Context-Native Adaptive AI Runtime?"
def direct(q=query, **override):
    k = dict(kwargs, question=q)
    k.update(override)
    return index.search(**k)

def assert_citations(output):
    assert output["answer_generated"] is False
    for item in output["results"]:
        c = item["citation"]
        raw = (SRC / c["document"]).read_bytes()
        text = raw[c["byte_start"]:c["byte_end"]]
        assert sha(raw) == c["document_sha256"]
        assert sha(text) == c["excerpt_sha256"]
        assert text.decode() == item["excerpt"]
        assert c["release_id"] == release["release_id"]
    return True

record("RELEASE_EXACT_OWNER_SIGNED_SOURCE_11_DOCS_21_SPANS",
       lambda: len(index.docs) == 11 and len(index.sections) == 21 and index.verify_original_bytes() is None)
record("POSITIVE_SOURCE_BM25_PLUS_LOCAL_DISTRIBUTIONAL", lambda:
       bool(direct()["results"]) and direct()["retrieval"].startswith("BM25_plus") and assert_citations(direct()))
record("UNKNOWN_FAIL_CLOSED", lambda: direct("xyzqzw fizzwut unreal-unicorn-issue")["status"] == "abstained")
record("PARTIALLY_MATCHING_UNSUPPORTED_FACT_ABSTAINS", lambda:
       direct("What runtime setting is needed for a quantum cobalt turbocharger engine tomorrow?")["status"] == "abstained")
record("REAL_LOCAL_DISTRIBUTIONAL_RERANK_SCORE_NONZERO", lambda:
       any(r["score"] > r["lexical_score"] for r in direct("AI Agent Runtime")["results"]))
record("CROSS_TENANT_FORBIDDEN", lambda: refuse(403, lambda: direct(tenant="other-tenant")))
record("UNAUTHORIZED_PUBLIC_ROLE_FORBIDDEN", lambda: refuse(403, lambda: direct(roles=["public"])))
record("INVALID_RELEASE_REJECTED", lambda: refuse(409, lambda: direct(release_id="tampered-release")))
record("INVALID_REVISION_REJECTED", lambda: refuse(409, lambda: direct(source_revision="stale-revision")))
record("SOURCE_EXPIRED_REJECTED", lambda: refuse(412, lambda: direct(now=datetime.now(timezone.utc)+timedelta(days=200))))
record("SOURCE_PRE_SNAPSHOT_REJECTED", lambda: refuse(412, lambda: direct(now=datetime(2020,1,1,tzinfo=timezone.utc))))
record("INVALID_INPUT_REJECTED", lambda: refuse(400, lambda: direct(q="  ")))
record("OVERSIZED_LIMIT_REJECTED", lambda: refuse(400, lambda: direct(limit=200)))

# Test all source spans through the actual retrieval algorithm, not a static fixture assertion.
def all_spans_retrievable():
    found = []
    for item in index.sections:
        value = direct(item["quote"], limit=5)
        assert_citations(value)
        found.append({"passage_id": item["passage_id"],
                      "retrieved": item["passage_id"] in [s["passage_id"] for s in value["results"]],
                      "rank": next((j+1 for j,s in enumerate(value["results"]) if s["passage_id"]==item["passage_id"]), None)})
    (EV / "raw" / "a05_21_span_retrieval.json").write_text(json.dumps(found, indent=2)+"\n")
    return all(x["retrieved"] for x in found)
record("ALL_21_SIGNED_SOURCE_SPANS_QUERY_RETRIEVABLE", all_spans_retrievable)

d00 = SRC / "00_m27_architecture_overview.md"
rev = SRC / "revocations.json"
manifest = SRC / "corpus.json"
release_file = SRC / "release.json"

def mutate_then_restore(path, changed, test):
    old = path.read_bytes()
    try:
        path.write_bytes(changed)
        return test()
    finally:
        path.write_bytes(old)
record("MUTATED_SOURCE_BYTES_REFUSE_INSTEAD_OF_CITE",
       lambda: mutate_then_restore(d00, d00.read_bytes()+b"\nTAMPER",
         lambda: refuse(409, lambda: direct(), "source_integrity_failed")))
record("CORRUPT_ORIGINAL_CORPUS_MANIFEST_REFUSED",
       lambda: mutate_then_restore(manifest, manifest.read_bytes()+b" ",
         lambda: refuse(409, lambda: direct(), "release_changed")))
record("ALTERED_RELEASE_METADATA_REFUSED",
       lambda: mutate_then_restore(release_file, release_file.read_bytes()+b" ",
         lambda: refuse(409, lambda: direct(), "release_changed")))
record("MISSING_SOURCE_FILE_REFUSED",
       lambda: mutate_then_restore(d00, b"",
         lambda: refuse(409, lambda: direct(), "source_integrity_failed")))
record("INVALID_REVOCATION_STATE_FAIL_CLOSED",
       lambda: mutate_then_restore(rev, b"{invalid",
         lambda: refuse(409, lambda: direct(), "revocation_state_unavailable")))

def revocation_roundtrip():
    initial = json.loads(rev.read_bytes())
    revoked = index.docs["00_m27_architecture_overview.md"]["sha256"]
    changed = dict(initial, epoch=initial["epoch"]+1, revoked_document_sha256=[revoked])
    def check_revoked():
        res = direct()
        assert all(r["citation"]["document_sha256"] != revoked for r in res["results"])
        assert res["revocation_epoch"] == changed["epoch"]
        return True
    a = mutate_then_restore(rev, json.dumps(changed).encode(), check_revoked)
    restored = direct()
    return a and restored["revocation_epoch"] == initial["epoch"] and any(
           r["citation"]["document_sha256"] == revoked for r in restored["results"])
record("DOCUMENT_REVOCATION_AND_REENABLE_NO_CACHED_LEAK", revocation_roundtrip)

# A physically separate HTTP server and urllib client on a live OS TCP socket.
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
def http_call(path, body=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
http_payload = dict(kwargs, question=query, limit=5)
proc = subprocess.Popen([sys.executable, "-u", str(HERE / "a05_http_server.py"), str(port)],
                        cwd=str(HERE), stdout=(EV/"raw"/"a05_server.stdout.log").open("w"),
                        stderr=(EV/"raw"/"a05_server.stderr.log").open("w"))
try:
    ready = False
    for _ in range(40):
        if proc.poll() is not None:
            break
        try:
            status, payload = http_call("/v1/health")
            ready = status == 200 and payload.get("healthy") is True
            if ready: break
        except (OSError, ValueError): time.sleep(.1)
    record("REAL_OS_LOOPBACK_HTTP_STARTUP", lambda: ready and proc.poll() is None)
    if ready:
        def positive_http():
            status, result = http_call("/v1/query", http_payload)
            return status == 200 and result["status"] == "source_passages" and assert_citations(result)
        record("REAL_HTTP_SOURCE_BACKED_CITATION_POSITIVE", positive_http)
        record("REAL_HTTP_PUBLIC_DENIED", lambda:
               (lambda s,v: s == 403 and v["results"] == [])(*http_call("/v1/query", dict(http_payload,roles=["public"]))))
        record("REAL_HTTP_CROSS_TENANT_DENIED", lambda:
               (lambda s,v: s == 403 and v["results"] == [])(*http_call("/v1/query", dict(http_payload,tenant="other-tenant"))))
        record("REAL_HTTP_UNKNOWN_ABSTAINS", lambda:
               (lambda s,v: s == 200 and v["status"] == "abstained" and not v["results"])(
                   *http_call("/v1/query", dict(http_payload,question="zxqz totally unknown nonword"))))
        record("REAL_HTTP_REVOKE_ALL_SOURCES_FAIL_CLOSED", lambda:
               mutate_then_restore(rev,
                   json.dumps(dict(json.loads(rev.read_bytes()), epoch=9,
                     revoked_document_sha256=[d["sha256"] for d in index.docs.values()])).encode(),
                   lambda: (lambda s,v: s == 200 and v["status"] == "abstained" and not v["results"])(
                       *http_call("/v1/query", http_payload))))
        record("REAL_HTTP_STALE_REVISION_REJECTED", lambda:
               (lambda s,v: s == 409 and v["results"] == [])(
                   *http_call("/v1/query", dict(http_payload,source_revision="old"))))
        record("REAL_HTTP_SOURCE_TAMPER_REJECTED", lambda:
               mutate_then_restore(d00, d00.read_bytes()+b"\nTAMPER",
                   lambda: (lambda s,v: s == 409 and not v["results"])(
                       *http_call("/v1/query", http_payload))))
        record("REAL_HTTP_AUTH_IS_TEST_ONLY_NOT_IDP", lambda:
               http_call("/v1/health")[1]["real_idp"] is False)
finally:
    if proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill();proc.wait()
record("REAL_HTTP_SERVER_CLEAN_TERMINATION", lambda: proc.poll() is not None)
record("SOURCE_RESTORED_AFTER_DESTRUCTIVE_NEGATIVES", lambda: index.verify_original_bytes() is None)
summary = {"schema":"m27.a05.local_positive_negative_http_receipt.v1",
           "pass": sum(c["pass"] for c in cases), "total":len(cases),
           "fail":sum(not c["pass"] for c in cases),
           "all_pass":all(c["pass"] for c in cases),
           "source_docs":11,"source_spans":21,
           "release_id":release["release_id"],"release_sha256":index.release_sha,
           "source_manifest_sha256":sha(manifest.read_bytes()),
           "actual_os_http":ready,"native_i37_http_test":False,
           "real_qdrant":False,"real_idp":False,"official_evaluations":0,
           "case_details":cases}
(EV/"A05_LOCAL_HTTP_RESULTS.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str)+"\n")
print(json.dumps({"pass":summary["pass"],"total":summary["total"],
                 "all_pass":summary["all_pass"]},sort_keys=True))
sys.exit(0 if summary["all_pass"] else 2)
