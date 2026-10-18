"""H02 isolated G01 raw-evidence checker. Offline provenance, NEVER Product output."""
import hashlib
import json
from pathlib import Path

H02 = "aa5fc61b296648c1117a37ea7561c4e2c8454f58"
G01 = "81eae18f819ab90850bce3b89a3ee9237be68a8d"
INDEX_SHA = "d7721c4126c6da1f57c04714e7ae64410764433fa09feb549e1188b41a0a5593"
PRE_SHA = "a5058f017d7427a68cfc87b971dd48a0fb3288ac5948ef68e8394cbd8bd638e8"
ABI = "m27.h02.native-a05-source-consumer/nonprod.v1"
OBLIGATIONS = {"execution_governance_verification", "planner_context_requirements"}

class Refused(ValueError):
    pass

def need(ok, why):
    if not ok:
        raise Refused(why)

def hash_bytes(x):
    return hashlib.sha256(x).hexdigest()

def fingerprint(p):
    data = Path(p).read_bytes()
    return {"bytes": len(data), "sha256": hash_bytes(data)}

def verify_index(index, evidence_root, source_root):
    need(index.get("head")==G01 and index.get("h02_readonly_head")==H02,
         "HEAD_PIN_MISMATCH")
    counts = []
    for key, root, expected in (("receipts", evidence_root, 21),
                                ("final_file_sha256", source_root, 8)):
        rows=index[key]
        need(len(rows)==expected and len({x["path"] for x in rows})==expected,
             "COUNT_OR_DUPLICATE")
        for x in rows:
            rel=Path(x["path"])
            need(not rel.is_absolute() and ".." not in rel.parts, "PATH_ESCAPES_SCOPE")
            path=(Path(root)/rel).resolve()
            need(path.is_relative_to(Path(root).resolve()),"PATH_ESCAPES_SCOPE")
            need(fingerprint(path)=={"bytes":x["bytes"],"sha256":x["sha256"]},
                 "ORIGINAL_SHA_OR_SIZE_MISMATCH:"+str(rel))
        counts.append(expected)
    return counts

def verify_task(pre, h02_root):
    need(pre["h02_read_only_head"]==H02 and pre["abi_reference"]==ABI,
         "TASK_ABI_MISMATCH")
    need(pre["provider"]=="MiniMax-M3" and
         "NOT_CLOUDFLARE_PRIMARY" in pre["provider_route"] and
         pre["max_provider_calls"]==1 and pre["max_tokens"]==320 and
         pre["no_product_authority"] and pre["no_cache"] and pre["no_actions"],
         "GATEWAY_OR_TASK_AUTHORITY_MISREPRESENTED")
    need(set(pre["obligations"])==OBLIGATIONS and
         set(pre["task_contract"]["definition_of_done"]["predicate_refs"])==OBLIGATIONS,
         "ANSWER_OBLIGATION_MISMATCH")
    t=pre["task_contract"]
    need(t["tenant_id"]=="owner-internal" and
         t["actor"]["principal_id"]=="internal" and
         t["authority"]["max_side_effect"]=="read" and
         t["budget"]["max_attempts"]==1 and
         not t["privacy"]["allow_memory_promotion"] and
         pre["source_rights"]=="owner-first-party-nonprod-only",
         "TASK_RIGHTS_NOT_ADMISSIBLE")
    bindings=pre["source_bindings"]
    need(len(bindings)==2 and len({x["source_sha256"] for x in bindings})==2,
         "TWO_DISTINCT_SOURCE_DOCS_REQUIRED")
    for x in bindings:
        need(x["source_id"].startswith("A05/") and
             x["source_id"].count("/")==1 and
             x["tenant"]=="owner-internal" and x["principal"]=="internal" and
             x["rights"]=="OWNER_NONPROD_READ_ONLY" and not x["revoked"],
             "SOURCE_RIGHTS_REJECTED")
        path=Path(h02_root)/"wave_b01/components/a05/source"/x["source_id"][4:]
        data=path.read_bytes()
        a,z=x["byte_span"]
        need(0<=a<z<=len(data) and hash_bytes(data)==x["source_sha256"] and
             hash_bytes(data[a:z])==x["excerpt_sha256"],"SOURCE_BYTES_UNBOUND")
    return True

def verify_wire(wire, client):
    rows=client["receipts"]
    need([x["event"] for x in rows]==
         ["request_started","answer_text","answer_text","terminal"],"CLIENT_ORDER")
    need([x["body"]["seq"] for x in rows]==[1,2,3,4] and
         len({x["body"]["request_id"] for x in rows})==1, "RUN_SEQUENCE")
    need(all(rows[i]["received_monotonic_ns"]<rows[i+1]["received_monotonic_ns"]
             for i in range(3)),"CLIENT_CLOCK_ORDER")
    need(rows[-1]["body"]["status"]=="answered" and
         rows[-1]["body"]["published_claims"]==2, "NONPROD_TERMINAL_MISSING")
    claims=rows[1:3]
    need(len({x["body"]["citation"]["source_sha256"] for x in claims})==2 and
         {x["body"]["obligation"] for x in claims}==OBLIGATIONS,
         "CLAIM_OBLIGATIONS_MISMATCH")
    for x in claims:
        d=x["body"]
        need(d["generated"] is True and d["verified"] is True and
             d["provider_stream_open_at_emit"] is True and
             d["text_sha256"]==hash_bytes(d["text"].encode()) and
             x["ack_status"]==200 and x["received_monotonic_ns"]<x["ack_monotonic_ns"]<
             rows[-1]["received_monotonic_ns"],"GENERATED_TEXT_OR_ACK_FAILURE")
    events=[e["event"] for e in wire]
    vm=[e["provider_event"] for e in wire if e["event"]=="vm_wire"]
    deltas=[e["text"] for e in vm if e.get("event")=="delta"]
    need(len(deltas)==4 and all(x["body"]["text"] in "".join(deltas) for x in claims),
         "RAW_GENERATION_NOT_PROVEN")
    need(sum(e.get("event")=="request_start" for e in vm)==1 and
         sum(e.get("event")=="model_identity" and e.get("model")=="MiniMax-M3" for e in vm)==1 and
         sum(e.get("event")=="provider_done" for e in vm)==1 and
         sum(e.get("event")=="stream_end" and e.get("provider_done") is True for e in vm)==1,
         "PROVIDER_LIFECYCLE_MISMATCH")
    need(events.count("verify")==2 and events.count("publish_answer_text")==2 and
         events.count("ack")==2 and events.count("final_source_reverify")==2 and
         events.count("publish_terminal")==1,"VERIFIER_PUBLISH_TERMINAL_COUNTS")
    for i,x in enumerate(claims):
        v=[j for j,e in enumerate(wire) if e["event"]=="verify"][i]
        p=[j for j,e in enumerate(wire) if e["event"]=="publish_answer_text"][i]
        a=[j for j,e in enumerate(wire) if e["event"]=="ack"][i]
        need(v<p<a<events.index("publish_terminal") and
             wire[v]["verdict"]["accepted"] is True and
             wire[v]["verdict"]["text_sha256"]==x["body"]["text_sha256"],
             "CLAIM_UNVERIFIED_BEFORE_PUBLISH")
    need(events.index("publish_terminal")>
         max(i for i,e in enumerate(wire) if e["event"]=="final_source_reverify"),
         "SOURCE_REVOKE_RECHECK_ORDER")
    return True

def verify_native_boundary(native, doc, f01):
    need(ABI in native and ABI in doc and
         'PROVIDER = "NOT_RUN"' in native and
         '"source_candidate_not_answer"' in native and
         '"model_generated": False' in native and
         "m27_g01_a05_live_qa" not in native and
         "publish_answer_text" not in native, "NATIVE_Q34_EQUIVALENT_UNSAFE")
    need(f01["case_count"]==17 and f01["provider_calls"]==0 and
         f01["classification"]=="NO_REMOTE_INFERENCE" and
         f01["receipt_status"]=="NOT_RUN" and
         f01["provider_raw_receipts"]==[], "F01_PROSPECTIVE_UNQUALIFIED")
    return True

def audit(g01_evidence, g01_source, h02_source, f01_evidence):
    evidence=Path(g01_evidence)
    idx=evidence/"G01_RAW_EVIDENCE_INDEX_V2.json"
    need(fingerprint(idx)["sha256"]==INDEX_SHA, "INDEX_HASH")
    a,b=verify_index(json.loads(idx.read_bytes()),evidence,g01_source)
    run=evidence/"G01_REAL_A05_ATTEMPT_01"
    precase=run/"G01_FROZEN_PRECASE.json"
    need(fingerprint(precase)["sha256"]==PRE_SHA,"PRECASE_HASH")
    verify_task(json.loads(precase.read_bytes()),h02_source)
    wire=[json.loads(x) for x in (run/"server_vm_wire.jsonl").read_text().splitlines() if x]
    client=json.loads((run/"independent_client_receipts.json").read_bytes())
    verify_wire(wire,client)
    native=(Path(h02_source)/"src/knowledge_engine/m27_h02_native_nonprod_consumer.py").read_text()
    doc=(Path(h02_source)/"docs/m27/h02_native_nonprod_consumer_abi.md").read_text()
    f01=json.loads((Path(f01_evidence)/"f01_17_raw_model_receipts_manifest.json").read_bytes())
    verify_native_boundary(native,doc,f01)
    return {"verdict":"SCOPED_EVIDENCE_ACCEPTED",
            "formal":"FORMAL_H02_PRODUCT_HOLD","g01_original_raw_sha_count":a,
            "g01_original_source_sha_count":b,
            "historical_real_minimax_requests":1,"provider_deltas":4,
            "verified_model_claims":2,"client_acks_before_nonprod_terminal":2,
            "f01_new_online":"0/17 NOT_RUN","native_abi":ABI,
            "h02_model_generation":False,"cloudflare_primary":"HOLD",
            "product_idp_and_semantic_issuer":"MISSING",
            "new_provider_calls":0,"actual_invoice":"NOT_OBSERVED"}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    for key in ("g01_evidence","g01_source","h02_source","f01_evidence"):
        p.add_argument("--"+key.replace("_","-"),required=True)
    args=p.parse_args()
    try:
        print(json.dumps(audit(**vars(args)),sort_keys=True,indent=2))
    except (Refused,FileNotFoundError,KeyError,ValueError,TypeError) as exc:
        print(json.dumps({"verdict":"FAIL_CLOSED","reason":str(exc)},sort_keys=True))
        raise SystemExit(2)
