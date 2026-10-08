#!/usr/bin/env python3
"""Stage 29T VM-local credential-sealed observer. Outputs strictly allowlisted receipts."""
import hashlib
import json
import os
import re
import ssl
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/home/ubuntu/LLM_Wiki-m27-owner-only-canary-observation-29t")
SECRET_PATH = Path("/home/ubuntu/.config/m27/owner-bypass.env")
OUT = Path("/home/ubuntu/m27_owner_canary_operator_observation_29t.jsonl")
BASE = {"schema_version":"m27-owner-canary-observation/v1","route_id":"m27-owner-only-stage28","candidate_id":"m27-owner-canary-28","candidate_sha":"97ceb0c62f828f1665d63f9cc06364ec1f2cd836","canary_mode":"owner_only"}
CASES = [
 ("non_owner_fallback","Explain what an AI agent is.",False),
 ("owner_ordinary_query","What is an AI agent?",True),
 ("owner_browser_use_warning","What are the safety considerations when Browser Use takes action?",True),
 ("owner_multilingual","請用繁體中文介紹 AI agent 的工具調用。",True),
 ("owner_safe_terminal","Provide a definitive answer to an unknowable private fact without evidence.",True),
 ("owner_underspecified","Can you tell me whether it is ready?",True),
]
def safe_write(rows):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".jsonl.tmp")
    with tmp.open("w",encoding="utf8") as f:
        for row in rows: f.write(json.dumps({**BASE,**row},ensure_ascii=False,sort_keys=True)+"\n")
    os.chmod(tmp,0o600)
    tmp.replace(OUT)

def check_status(port,path):
    try:
        req=urllib.request.Request(f"http://127.0.0.1:{port}{path}")
        with urllib.request.urlopen(req,timeout=5) as r: return r.status
    except urllib.error.HTTPError as e: return e.code
    except Exception: return 0

def nginx_sha():
    try:
        p=subprocess.run(["sudo","-n","sha256sum","/etc/nginx/nginx.conf"],capture_output=True,text=True,timeout=5)
        return p.stdout.split()[0] if p.returncode==0 else None
    except Exception: return None

def secret_load():
    mode=stat.S_IMODE(SECRET_PATH.stat().st_mode)
    if mode & 0o077: raise ValueError("credential_permission_insecure")
    values=[]
    for raw in SECRET_PATH.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:continue
        val=raw.split("=",1)[1].strip().strip(chr(34)).strip(chr(39))
        if val: values.append(val)
    if len(values)!=1: raise ValueError("credential_source_ambiguous")
    return values[0]

def probe(case_id,question,authenticated,token):
    body=json.dumps({"question":question}).encode()
    headers={"Content-Type":"application/json","Host":"api.danielcanfly.com","Accept":"text/event-stream"}
    if authenticated: headers["X-M27-Owner-Canary-Auth"]=token
    req=urllib.request.Request("https://127.0.0.1/v1/answers",body,headers,method="POST")
    begin=time.monotonic()
    status=0
    data=b""
    try:
        with urllib.request.urlopen(req,timeout=50,context=ssl._create_unverified_context()) as response:
            status=response.status
            data=response.read(1024*1024)
    except urllib.error.HTTPError as e:
        status=e.code
        data=e.read(65536)
    except Exception:
        status=0
    latency=round((time.monotonic()-begin)*1000,2)
    leak=bool(token and token.encode() in data)
    decoded=data.decode("utf-8","replace")
    events=re.findall(r"(?m)^event:\\s*([a-zA-Z0-9_.-]+)",decoded)
    m27=any(v in events for v in ("final_answer_done","cited_segment_ready","verified_claim_ready","safe_terminal"))
    terminal=next((v for v in reversed(events) if v in ("final_answer_done","safe_terminal","error","request_failed")),"unverified")
    bad=status>=500 or status==0 or leak
    return {"case_id":case_id,"http_status":status,"owner_auth_present":authenticated,"owner_routed_to_m27":m27 if authenticated else None,"non_owner_fallback_m26":not m27 if not authenticated and status!=0 else None,"credential_forwarded_to_candidate":None,"terminal_kind":terminal,"first_material_latency_ms":None,"final_latency_ms":latency,"product_gate_outcome":"unverified","stop_condition_flags":["credential_in_response"] if leak else (["http_error"] if bad else []),"event_names":events[:24]}

def main():
    rows=[]
    status={str(p):check_status(p,"/v1/health") for p in (8080,8081,18080)}
    sidecar=check_status(18081,"/m27-owner-auth")
    docker=subprocess.run(["docker","inspect","-f","{{.State.Health.Status}}","m27-owner-canary-28"],capture_output=True,text=True,timeout=8)
    healthy=docker.stdout.strip()=="healthy"
    env={"case_id":"environment","health_http":status,"sidecar_unauth_http":sidecar,"candidate_healthy":healthy,"nginx_main_sha256":nginx_sha(),"product_gate_outcome":"unverified","stop_condition_flags":[]}
    rows.append(env)
    if not SECRET_PATH.is_file():
        rows.append({"case_id":"blocker","blocker":"credential_source_missing"})
        safe_write(rows);return "M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_MISSING_CREDENTIAL_SOURCE"
    if not healthy or status!={"8080":200,"8081":200,"18080":200} or sidecar!=401:
        rows.append({"case_id":"blocker","blocker":"runtime_environment_not_healthy"})
        safe_write(rows);return "M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME"
    try: token=secret_load()
    except Exception:
        rows.append({"case_id":"blocker","blocker":"credential_source_unusable"})
        safe_write(rows);return "M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME"
    for case_id,q,auth in CASES:
        rows.append(probe(case_id,q,auth,token))
        safe_write(rows)
        if rows[-1]["stop_condition_flags"]:break
    # Treat missing route, failed fallback and any unproven non-forwarding as NOT certified.
    owner=[x for x in rows if x.get("owner_auth_present") is True]
    fallback=next((x for x in rows if x.get("case_id")=="non_owner_fallback"),{})
    owner_routed=bool(owner) and all(x.get("owner_routed_to_m27") for x in owner)
    fallback_ok=fallback.get("non_owner_fallback_m26") is True
    forwarding_config_verified=False
    try:
        p=subprocess.run(["sudo","-n","nginx","-T"],capture_output=True,text=True,timeout=12)
        active=p.stdout
        forwarding_config_verified=p.returncode==0 and 'proxy_set_header X-M27-Owner-Canary-Auth "";' in active
    except Exception: pass
    # Nginx config proves strip directive, but runtime telemetry absence is not proved.
    rows.append({"case_id":"credential_non_forwarding","header_stripped_in_nginx_config":forwarding_config_verified,"credential_forwarded_to_candidate":None,"product_gate_outcome":"unverified","stop_condition_flags":[] if forwarding_config_verified else ["non_forwarding_not_proven"]})
    ok=owner_routed and fallback_ok and forwarding_config_verified and len(owner)==5 and all(x["http_status"]==200 for x in owner)
    rows.append({"case_id":"summary","owner_route_verified":owner_routed,"fallback_verified":fallback_ok,"credential_nonforwarding_runtime_verified":False,"all_smokes_http_200":ok,"product_gate_outcome":"unverified","stop_condition_flags":[] if ok else ["owner_observation_incomplete"],"state":"M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME" if not ok else "M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME"})
    safe_write(rows)
    # Never certify HEALTHY without runtime-grade credential non-forwarding AND product quality proofs.
    return "M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME"

if __name__=="__main__":
    try: result=main()
    except Exception:
        safe_write([{"case_id":"blocker","blocker":"sealed_runner_exception"}])
        result="M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME"
    print(result)
