#!/usr/bin/env python3
"""Real C1 formal admission checker v2: no hardcoded issuer count or wire failure.

Verifies previously accepted real Cloudflare SSE custody separately from the
formal, current-source externally signed authority package. It can report
CRYPTO_ADMISSION_PASS only after four distinct principals' REAL valid Ed25519
receipts AND three reviewed release-root pins AND a current formal run; this
program never signs or mints identities. Independent auditor still signs off.
"""
from __future__ import annotations
import argparse,ast,base64,hashlib,json,os,re,subprocess,sys,tempfile,time
from pathlib import Path

ROLES=("provider_controller","source_controller","semantic_issuer","client_idp")
PINS={
 "m27_c1_genuine_native_generation_seam.py":"TRUST_ROOT_MANIFEST_SHA256",
 "m27_f03_source_rights_admission.py":"F03_EXTERNAL_SOURCE_ROOT_SHA256",
 "m27_c1_gitless_source_proof.py":"C1_GITLESS_TRUST_ROOT_SHA256"}
CLOUDFLARE="@cf/openai/gpt-oss-120b"
SSE_ABI="m27.c1.provider-workers-ai-sse/v1"
NDJSON_ABI="m27.c1.provider-new-delta/v1"
OLD="cb997d9282886a540779b8f9751e07c3590b2797"
OLD_TREE="b1ed8e983df338d86a798fb31dcdfaa10f0ddfdc"

class Denied(ValueError):pass
def demand(ok,reason):
    if not ok:raise Denied(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canon(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,
           separators=(",",":"),allow_nan=False).encode()
def git(repo,*args):
    return subprocess.run(["git","-C",str(repo),*args],
        capture_output=True,text=True,check=True,timeout=10).stdout.strip()
def static(path,name):
    tree=ast.parse(path.read_bytes(),filename=str(path))
    values=[]
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(
            isinstance(x,ast.Name) and x.id==name for x in node.targets):
            values.append(ast.literal_eval(node.value))
    demand(len(values)==1,"TRUST_PIN_AMBIGUOUS_"+name)
    return values[0]
def root_pins(repo):
    results={}
    for file,name in PINS.items():
        val=static(repo/"src/knowledge_engine"/file,name)
        results[name]={"admitted":type(val) is str and
           re.fullmatch(r"[0-9a-f]{64}",val) is not None,
           "sha256":val if type(val) is str else None}
    return results
def legacy_dev_custody(repo,evidence):
    ledger=evidence/"CURRENT_C1_CLOUDFLARE_EVIDENCE_SHA256_INDEX.json"
    data=json.loads(ledger.read_bytes())
    demand((data["current_git_head"],data["current_git_tree"])==(OLD,OLD_TREE),
           "ORIGINAL_DEVELOPMENT_EVIDENCE_SUBJECT_CHANGED")
    current=git(repo,"rev-parse","HEAD")
    demand(git(repo,"merge-base",OLD,current)==OLD,
           "CURRENT_C1_IS_NOT_DESCENDANT_OF_VERIFIED_E2E_SOURCE")
    for name,detail in data["evidence_file_sha256_index"].items():
        p=(evidence/name).resolve()
        demand(p.is_relative_to(evidence.resolve()) and p.is_file()
               and p.stat().st_size==detail["bytes"] and
               sha(p.read_bytes())==detail["sha256"],
               "SOURCE_PROVIDER_CLIENT_RAW_EVIDENCE_CHANGED_"+name)
    for name,detail in data["new_changed_source_files"].items():
        raw=subprocess.run(["git","-C",str(repo),"show",OLD+":"+name],
             capture_output=True,check=True,timeout=10).stdout
        demand(sha(raw)==detail["sha256"] and len(raw)==detail["bytes"],
               "ACCEPTED_E2E_GIT_BLOB_CHANGED_"+name)
    d=data["live_provider_firstparty_current_positive"]
    demand(d["real_model"]==CLOUDFLARE and
           d["actual_raw_delta_events"]==16 and
           d["actual_local_native_client_http_200_acks"]==2 and
           d["first_client_ack_before_actual_provider_done_observed"] is True and
           d["formal_C1_product_qualified"] is False,
           "HISTORIC_POSITIVE_UNSUPPORTED")
    return {"status":"ACCEPTED_HISTORIC_FIRSTPARTY_NONPROD_E2E",
      "current_source_is_descendant":True,
      "original_head":OLD,"original_tree":OLD_TREE,
      "raw_file_count":len(data["evidence_file_sha256_index"]),
      "old_evidence_index_sha256":sha(ledger.read_bytes()),
      "historical_evidence_is_not_formal_current_signed_receipts":True}

def verify_ed25519(pem:str, payload:dict, signature_b64:str):
    demand(isinstance(pem,str) and pem.startswith("-----BEGIN PUBLIC KEY-----") and
           len(pem)<4096 and type(payload) is dict and
           isinstance(signature_b64,str),
           "EXTERNAL_SIGNED_RECEIPT_TYPE")
    try:sig=base64.b64decode(signature_b64,validate=True)
    except (ValueError,TypeError) as ex:
        raise Denied("EXTERNAL_SIGNATURE_NOT_BASE64") from ex
    demand(len(sig)==64,"EXTERNAL_ED25519_SIGNATURE_LENGTH")
    with tempfile.TemporaryDirectory(prefix="c1-readonly-ed25519-") as d:
        p=Path(d);(p/"pub.pem").write_text(pem)
        (p/"payload").write_bytes(canon(payload))
        (p/"sig").write_bytes(sig)
        cp=subprocess.run(["openssl","pkeyutl","-verify","-pubin",
            "-inkey",str(p/"pub.pem"),"-rawin","-in",str(p/"payload"),
            "-sigfile",str(p/"sig")],
            capture_output=True,check=False,timeout=7)
    demand(cp.returncode==0,"EXTERNAL_REAL_SIGNATURE_INVALID")

def validate_package(*,repo, path, pins, current_head,current_tree):
    pkg=json.loads(path.read_bytes())
    required={"version","subject_head","subject_tree","task_sha256",
      "request_id","nonce","source_proof_sha256","source_manifest_sha256",
      "provider_url","provider_model","wire_protocol","trust_root_path",
      "source_controller_public_root_path","gitless_public_root_path",
      "signed_receipts","actual_formal_run"}
    demand(type(pkg) is dict and set(pkg)==required and
           pkg["version"]=="m27.c1.formal-admission-evidence/v2",
           "FORMAL_PACKAGE_UNKNOWN_OR_INCOMPLETE")
    demand((pkg["subject_head"],pkg["subject_tree"])==(current_head,current_tree),
           "NEW_SIGNED_RECEIPTS_NOT_BOUND_TO_CURRENT_C1_SOURCE")
    for key in ("task_sha256","source_proof_sha256","source_manifest_sha256"):
        demand(type(pkg[key]) is str and
               re.fullmatch("[0-9a-f]{64}",pkg[key]),
               "FORMAL_DIGEST_NOT_64_HEX_"+key)
    manifest=Path(pkg["trust_root_path"]).resolve(strict=True)
    root_pins_expected=pins["TRUST_ROOT_MANIFEST_SHA256"]["sha256"]
    demand(root_pins_expected is not None and
           sha(manifest.read_bytes())==root_pins_expected,
           "FORMAL_ROOT_NOT_INDEPENDENTLY_ADMITTED_IN_RELEASE")
    root=json.loads(manifest.read_bytes())
    demand(type(root) is dict and set(root)=={"version","roles"} and
           root["version"]=="m27.external-independent-trust/v1" and
           type(root["roles"]) is dict and set(root["roles"])==set(ROLES),
           "FORMAL_ROOT_FOUR_ROLES_NOT_ADMITTED")
    subjects=[root["roles"][r]["principal"] for r in ROLES]
    demand(len(set(subjects))==4 and
           all(type(n) is str and len(n)>=3 for n in subjects),
           "FORMAL_ROLE_PRINCIPALS_NOT_DISTINCT")
    sourcepub=Path(pkg["source_controller_public_root_path"]).resolve(strict=True)
    gitlesspub=Path(pkg["gitless_public_root_path"]).resolve(strict=True)
    demand(sha(sourcepub.read_bytes())==
           pins["F03_EXTERNAL_SOURCE_ROOT_SHA256"]["sha256"] and
           sha(gitlesspub.read_bytes())==
           pins["C1_GITLESS_TRUST_ROOT_SHA256"]["sha256"],
           "FORMAL_SOURCE_OR_GITLESS_PUBLIC_ROOT_NOT_PINNED")
    # Independent public Source roots may be delegated to separate keys.
    # Their hashes must be release-pinned AND their delegation must be signed
    # in the Source Controller role receipt checked below.
    formal_text=(repo/"src/knowledge_engine"/
                 "m27_c1_genuine_native_generation_seam.py").read_text()
    is_supported=(
      pkg["wire_protocol"]==NDJSON_ABI and
      "application/x-ndjson" in formal_text and
      pkg["provider_model"]!=""
      or
      pkg["wire_protocol"]==SSE_ABI and
      'PROVIDER_SSE_ABI = cf_sse.ABI' in formal_text and
      pkg["provider_model"]==CLOUDFLARE and
      pkg["provider_url"].startswith("https://api.cloudflare.com/client/v4/accounts/") and
      pkg["provider_url"].endswith("/ai/v1/chat/completions"))
    demand(is_supported, "SIGNED_PROVIDER_WIRE_NOT_CURRENT_RELEASE_CONTRACT")
    receipt_list=pkg["signed_receipts"]
    demand(type(receipt_list) is list and len(receipt_list)==7,
           "FORMAL_INDEPENDENT_ROLE_RECEIPTS_NOT_PRESENT")
    counts={r:0 for r in ROLES}
    seen=set();now=int(time.time())
    for receipt in receipt_list:
        demand(type(receipt) is dict and set(receipt)=={"payload","signature_b64"},
               "FORMAL_RECEIPT_ENVELOPE")
        body=receipt["payload"]
        demand(type(body) is dict,"FORMAL_RECEIPT_PAYLOAD")
        role=body.get("role")
        demand(role in ROLES and
               body.get("issuer")==root["roles"][role]["principal"] and
               body.get("nonce")==pkg["nonce"] and
               body.get("task_sha256")==pkg["task_sha256"] and
               body.get("request_id")==pkg["request_id"] and
               body.get("source_proof_sha256")==pkg["source_proof_sha256"],
               "FORMAL_SIGNED_ROLE_TASK_OR_SOURCE_MISMATCH")
        issued,expires=body.get("issued_at"),body.get("expires_at")
        demand(type(issued) is int and type(expires) is int and
               0<=now-issued<=300 and issued<expires<=issued+300 and now<expires,
               "FORMAL_RECEIPT_TTL_REVOKED_OR_EXPIRED")
        if role=="source_controller":
            demand(body.get("source_manifest_sha256")==pkg["source_manifest_sha256"] and
                   type(body.get("rights_epoch")) is int and
                   body.get("tenant")=="owner-internal",
                   "FORMAL_SOURCE_CONTROLLER_TASK_OR_RIGHTS_NOT_SIGNED")
            # Release-pinned root files are independently reviewed separately
            # from this task grant. The exact C1 protocol does not allow ad-hoc
            # extra fields in the task's source-controller signature.
        if role=="provider_controller":
            demand(body.get("url")==pkg["provider_url"] and
                   body.get("model")==pkg["provider_model"] and
                   body.get("wire_protocol")==pkg["wire_protocol"],
                   "FORMAL_PROVIDER_SIGNED_ROUTE_ABI_MISMATCH")
        if role=="semantic_issuer":
            demand(body.get("obligation") in ("execution_governance_verification",
                    "policy_engine_enforcement") and
                   type(body.get("text_sha256")) is str and
                   body.get("provider_model")==pkg["provider_model"],
                   "FORMAL_SEMANTIC_CLAIM_NOT_BOUND")
        if role=="client_idp":
            claim=body.get("claim_id")
            if claim is None:
                demand(type(body.get("client_principal")) is str and
                       body.get("client_abi")=="m27.c1.native-verified-text-ack/v1",
                       "FORMAL_CLIENT_INITIATION_NOT_SIGNED")
            else:
                demand(claim in ("execution_governance_verification",
                    "policy_engine_enforcement") and
                    type(body.get("challenge")) is str and
                    type(body.get("text_sha256")) is str,
                    "FORMAL_CLIENT_ACK_NOT_SIGNED")
        stamp=(role,body.get("obligation",body.get("claim_id","initial_grant")))
        demand(stamp not in seen,"FORMAL_RECEIPT_REPLAY")
        seen.add(stamp)
        verify_ed25519(root["roles"][role]["public_key_pem"],
                       body,receipt["signature_b64"])
        counts[role]+=1
    demand(counts=={"provider_controller":1,"source_controller":1,
                    "semantic_issuer":2,"client_idp":3},
           "FORMAL_REQUIRED_DISTINCT_SIGNED_RECEIPTS_INCOMPLETE")
    run=pkg["actual_formal_run"]
    demand(type(run) is dict and
           run.get("formal_run_under_signed_c1_runtime") is True and
           run.get("request_id")==pkg["request_id"] and
           run.get("task_sha256")==pkg["task_sha256"] and
           run.get("client_ack_count")==2 and
           run.get("verified_final_citation_count")==2 and
           run.get("first_verified_client_ack_preterminal") is True and
           run.get("provider_done") is True,
           "FORMAL_REAL_NATIVE_RUNTIME_E2E_NOT_PROVEN")
    # A self-declared JSON boolean is not proof of real current-source Product
    # execution. A reviewer must inspect the original native journal and
    # upstream wire, not infer an independent PASS from this candidate alone.
    return {"status":"CRYPTO_SIGNED_ADMISSION_CANDIDATE_PASS_PENDING_INDEPENDENT_AUDIT",
       "verified_signed_receipt_count":len(receipt_list),
       "verified_role_counts":counts,"distinct_role_principals":4,
       "provider_wire":pkg["wire_protocol"],
       "actual_formal_run_self_report_not_independent":True}

def preflight(repo,ev,package=None):
    h,t=git(repo,"rev-parse","HEAD"),git(repo,"rev-parse","HEAD^{tree}")
    demand(not git(repo,"status","--porcelain"),
           "CURRENT_C1_WORKTREE_NOT_CLEAN")
    historic=legacy_dev_custody(repo,ev)
    pins=root_pins(repo)
    formal=(repo/"src/knowledge_engine"/
            "m27_c1_genuine_native_generation_seam.py").read_text()
    provider_abi=static(repo/"src/knowledge_engine"/
                        "m27_c1_genuine_native_generation_seam.py","PROVIDER_ABI")
    sse_supported=('PROVIDER_SSE_ABI = cf_sse.ABI' in formal and
        (repo/"src/knowledge_engine"/"m27_c1_formal_workers_ai_sse.py").is_file())
    accepted={"m27.c1.provider-new-delta/v1":provider_abi=="m27.c1.provider-new-delta/v1",
              SSE_ABI:sse_supported}
    signed={}
    if package is None:
        signed={"status":"NO_CURRENT_FORMAL_SIGNED_PACKAGE_PROVIDED",
                "verified_signed_receipt_count":0,
                "verified_role_counts":{r:0 for r in ROLES},
                "reason":"NO_AUTHENTIC_CURRENT_PRODUCT_ISSUER_EVIDENCE"}
    elif not all(x["admitted"] for x in pins.values()):
        signed={"status":"TRUST_ROOTS_NOT_PINNED_NO_SIGNED_PACKAGE_ACCEPTED",
                "verified_signed_receipt_count":0,
                "verified_role_counts":{r:0 for r in ROLES},
                "reason":"FORMAL_ROOTS_HAVE_NO_INDEPENDENT_RELEASE_AUTHORITY"}
    else:
        signed=validate_package(repo=repo,path=Path(package).resolve(strict=True),
              pins=pins,current_head=h,current_tree=t)
    return {
      "current_subject":{"head":h,"tree":t,"clean":True},
      "prior_real_provider_qa":historic,
      "supported_formal_wire_abis":accepted,
      "actual_static_release_trust_pins":pins,
      "signed_product_receipts":signed,
      "formal_independent_product_signoff":
          "PENDING_DIFFERENT_PRINCIPAL_AUDITOR"
          if signed["status"]=="CRYPTO_SIGNED_ADMISSION_CANDIDATE_PASS_PENDING_INDEPENDENT_AUDIT"
          else "HOLD_NO_VALID_CURRENT_EXTERNAL_SIGNED_ADMISSION",
      "formal_pass":False,  # Auditor, not code preflight, is final signer.
      "external_actions":0,"self_signers_created":0}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    p.add_argument("--evidence",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--formal-package")
    a=p.parse_args()
    output=Path(a.out)
    result=preflight(Path(a.repo).resolve(strict=True),
            Path(a.evidence).resolve(strict=True),a.formal_package)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    output.chmod(0o600)
    print(json.dumps({"subject":result["current_subject"],
       "provider_sse_formal_abi_supported":result["supported_formal_wire_abis"][SSE_ABI],
       "admitted_roots":sum(v["admitted"] for v in
            result["actual_static_release_trust_pins"].values()),
       "actually_verified_issuer_count":sum(1 for v in
            result["signed_product_receipts"]["verified_role_counts"].values() if v>0),
       "receipt_count":result["signed_product_receipts"]["verified_signed_receipt_count"],
       "formal_signoff_status":result["formal_independent_product_signoff"],
       "output":str(output)}))
if __name__=="__main__":main()
