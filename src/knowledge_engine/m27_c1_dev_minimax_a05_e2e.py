"""M27 C1 bounded first-party Nonprod LIVE MiniMax-to-Unix-Client diagnostic.

This is NOT formal Product provider/origin, independently signed Semantic
Issuer, external Product Client IdP or C1 Product E2E PASS.  It never touches
the fail-closed native /model-generation route or its external root None.
The provider's real MiniMax-M3 stream is reused from independently accepted
G01/F02 source with exact pinned Git SHA and module SHA.  VM credentials
remain in the previously permitted owner-only Nonprod container.
"""
from __future__ import annotations
import argparse,hashlib,http.client,importlib.util,json,os,re,secrets,socket,socketserver
import stat,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

if not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
import m27_c1_current_native_product_nonprod as c1
import m27_c1_genuine_native_generation_seam as c1live
import m27_g01_current_native_consumer as g01
import m27_f03_source_rights_admission as f03

ABI="m27.c1.firstparty-dev-minimax-M3-live-a05-osclient/v1"
MODEL="MiniMax-M3"
PROVIDER_DEV_SCOPE="EXISTING_OWNER_CANARY_NONPROD_DIAGNOSTIC_NOT_CLOUDFLARE_PRIMARY"
VENDOR_GIT="81eae18f819ab90850bce3b89a3ee9237be68a8d"
PINNED={
 "m27_f02_reliability_stream.py":"f6b31b29f5e745ffd7c3610323d42f6a8ccb1cdc011e23b995df676a78de7102",
 "m27_b1_online_stream_client.py":"b662cb505d1c7dbd347436408329f918c1be9af170edd91e7ce6522ec1527391",
 "m27_b0_stream_experiment.py":"c12d7ecc81197e6c3f7fcb12b970d9a6c98924263e9ae25210f1948758af7e15"}
MAX_EVENTS=350
PROMPT=(
 "Answer this exact two-part question using only the two authentic M27 A05 "
 "source excerpts. Produce EXACTLY two short complete factual English sentences "
 "on two separate lines, ending each with a period and newline. No labels, "
 "bullets, headings, examples, opinions or additional sentences. "
 "Question: Which plane includes Verification, and who decides deterministic "
 "policy enforcement? Sentence one must say Verification is in the Execution "
 "& Governance Plane. Sentence two must say PolicyEngine decides deterministic "
 "enforcement. Evidence A from A05 00_m27_architecture_overview.md: "
 "'3. Execution & Governance Plane; Harness; Policy; ACL; Verification'. "
 "Evidence B from A05 01_contracts.md: "
 "'Responsible for selecting compute budget per request. "
 "PolicyEngine Responsible for deterministic enforcement. "
 "Agent may request. PolicyEngine decides.' "
 "Only produce content entailed by these two sources."
)
SEMANTIC=(
 re.compile(r"(?:Verification (?:belongs to|is in|is part of|is included in|is located in) (?:the )?Execution (?:&|and) Governance Plane|(?:The )?Execution (?:&|and) Governance Plane (?:includes|contains) Verification)\.",re.I),
 re.compile(r"(?:(?:The )?PolicyEngine (?:decides|determines|is responsible for) deterministic (?:policy )?enforcement|Deterministic (?:policy )?enforcement is (?:decided|determined) by (?:the )?PolicyEngine)\.",re.I))
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def must(ok,reason):
    if not ok:raise ValueError(reason)
def vendor_generator(vendor:Path):
    vendor=Path(vendor).resolve(strict=True)
    must(vendor.is_dir() and vendor.name=="g01_vendor","NOT_APPROVED_G01_PROVIDER_VENDOR")
    for name,expected in PINNED.items():
        must(digest((vendor/name).read_bytes())==expected,
             "PINNED_G01_VENDOR_BYTES_DRIFT_"+name)
    p=vendor.parent.parent
    proc=subprocess.run(["git","-C",str(p),"rev-parse","HEAD"],capture_output=True,text=True,check=True)
    must(proc.stdout.strip()==VENDOR_GIT,"G01_VENDOR_SOURCE_VERSION_MISMATCH")
    must(not subprocess.run(["git","-C",str(p),"status","--porcelain"],capture_output=True,text=True,check=True).stdout.strip(),
         "G01_VENDOR_WORKTREE_DIRTY")
    spec=importlib.util.spec_from_file_location("c1_readonly_accepted_f02",vendor/"m27_f02_reliability_stream.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.VM_PROMPT=PROMPT
    mod.VM_PROMPT_B=PROMPT
    # The original F02 adapter has a 320-token Nonprod cap. This C1 task
    # tightens the exact raw VM-side request to its OWN TaskContract 128 cap,
    # without weakening inherited F02/G01 source bytes or modifying them.
    exact=mod.b1.VM_PROVIDER_SCRIPT
    must(exact.count("'max_tokens':650")==1 and
         exact.count("max_tokens=650")>=1,
         "INCOMPATIBLE_AUTHENTIC_MINIMAX_VM_WIRE")
    mod.b1.VM_PROVIDER_SCRIPT=(exact.replace(
         "'max_tokens':650","'max_tokens':128").replace(
         "max_tokens=650","max_tokens=128"))
    return mod.cloud_generation

def real_os_semantic_verify(repo:Path,fence:Path,claim_id:str,text:str,actual_sha:str):
    """Separate real OS verifier; no local fake semantic-issuer signature."""
    program=Path(__file__).resolve()
    request={"repo":str(repo),"fence":str(fence),"claim_id":claim_id,
             "text":text,"source_proof_sha256":actual_sha}
    p=subprocess.run([sys.executable,str(program),"verify"],
      input=json.dumps(request),capture_output=True,text=True,timeout=16,check=False)
    must(p.returncode==0,"SEPARATE_OS_SEMANTIC_SOURCE_VERIFIER_DENIED")
    v=json.loads(p.stdout)
    must(v.get("accepted") is True and v.get("signed_semantic_issuer") is False
         and v.get("claim_id")==claim_id and
         v.get("source_proof_sha256")==actual_sha,
         "LOCAL_F03_VERIFIER_SOURCE_BINDING_DENIED")
    return v

def verify_child():
    req=json.loads(sys.stdin.read(16384))
    repo,fence=Path(req["repo"]),Path(req["fence"])
    claim_id,text=req["claim_id"],req["text"]
    must(claim_id in c1live.OBLIGATIONS and 16<=len(text)<=350 and
         not any(c in text for c in ("\n","\r","\0")),
         "UNSAFE_SOURCE_CLAIM")
    order=c1live.OBLIGATIONS.index(claim_id)
    must(SEMANTIC[order].fullmatch(text) is not None,
         "A05_SEMANTIC_ENTAILMENT_NOT_SUPPORTED")
    with tempfile.TemporaryDirectory(prefix="c1-real-os-source-verifier-") as td:
        verifier=g01.Consumer(repo=repo,fence=fence,journal=Path(td)/"source.jsonl")
        proofs=verifier._source()
        must(digest(canon(proofs))==req["source_proof_sha256"],
             "A05_RIGHTS_OR_SOURCE_REVOKED")
        p=proofs[order]
        assert p["obligation_id"]==claim_id
        print(json.dumps({
           "accepted":True,"claim_id":claim_id,
           "model_text_sha256":digest(text.encode()),
           "source_proof_sha256":req["source_proof_sha256"],
           "source_excerpt_sha256":p["excerpt_sha256"],
           "citation":p["citation"],"pid":os.getpid(),
           "signed_semantic_issuer":False,"scope":"OWNER_NONPROD_OS_VERIFIER_ONLY"}))

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def __init__(self, path, *, repo, fence, token_file, evidence, vendor):
        self.repo=repo;self.fence=fence;self.evidence=evidence
        self.capability=c1.read_client_capability(token_file)
        self.generator=vendor_generator(vendor)
        self.live=c1live.NativeLiveProduct(repo=repo,fence=fence,
               journal=evidence/"C1_REAL_TASK_JOURNAL.jsonl")
        self.prepared=self.live.prepare({
            "question":g01.QUESTION,"tenant":"owner-internal",
            "cache_mode":"OFF","max_tokens":128,"deadline_seconds":30,
            "fallback_consent":False})
        self.once=False;self.done=False;self.provider_calls=0
        self.deadline_ns=None
        self.ack_cond=threading.Condition();self.pending={};self.acked=[]
        self.journal=evidence/"C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl"
        self.log_lock=threading.Lock()
        os.umask(0o077)
        super().__init__(str(path),Handler)
        os.chmod(path,0o600)
    def audit(self,v):
        with self.log_lock,self.journal.open("a") as f:
            f.write(json.dumps({"at_ns":time.monotonic_ns(),**v},sort_keys=True)+"\n")
            f.flush();os.fsync(f.fileno())
    def current(self):
        current=self.live._source()
        must(digest(canon(current))==self.live.pending["source_proofs_sha256"],
             "F03_A05_RIGHTS_REVOKED_DURING_LIVE_MODEL")
        return current

class Handler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.0"
    def log_message(self,*args):pass
    def authorized(self):
        server=self.server
        return (self.headers.get("Host")=="c1-dev-unix.local" and
          c1.native_unix_peer_uid(self.connection)==os.geteuid() and
          self.headers.get("X-C1-Local-Capability","").encode()==server.capability)
    def reply(self,v,status=200):
        body=json.dumps(v,sort_keys=True).encode()
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.end_headers()
        self.wfile.write(body);self.wfile.flush()
    def frame(self,name,body):
        data=("event: "+name+"\ndata: "+json.dumps(body,sort_keys=True)+"\n\n").encode()
        self.wfile.write(data);self.wfile.flush()
        self.server.audit({"event":"native_delivery_"+name,
                           "request_id":body.get("request_id"),
                           "text_sha256":body.get("text_sha256"),
                           "source_cited":bool(body.get("citation")),
                           "provider_done_observed":self.server.done})
    def do_POST(self):
        if not self.authorized():return self.reply({"status":"CLIENT_AUTH_DENIED"},403)
        if self.path!="/ack":return self.reply({"status":"UNKNOWN_ROUTE"},404)
        try:
            n=int(self.headers.get("Content-Length","0"))
            must(0<n<=2048,"ACK_BODY_BUDGET")
            data=json.loads(self.rfile.read(n))
            must(type(data) is dict and
              set(data)=={"request_id","claim_id","challenge","text_sha256"},
              "ACK_SHAPE")
            s=self.server
            with s.ack_cond:
                pending=s.pending.get(data["claim_id"])
                must(pending is not None and pending["request_id"]==data["request_id"]
                     and pending["challenge"]==data["challenge"]
                     and pending["text_sha256"]==data["text_sha256"]
                     and data["claim_id"] not in s.acked,
                     "ACK_CHALLENGE_OR_REPLAY_DENIED")
                must(not s.done,"ACK_AFTER_PROVIDER_DONE_DENIED")
                s.current()
                s.acked.append(data["claim_id"])
                s.audit({"event":"native_client_local_ack",
                  "claim_id":data["claim_id"],"request_id":data["request_id"],
                  "text_sha256":data["text_sha256"],
                  "scope":"OS_LOCAL_BEARER_NOT_INDEPENDENT_IDP"})
                s.ack_cond.notify_all()
            self.reply({"status":"SOURCE_VERIFIED_DEV_NATIVE_ACK","product_pass":False})
        except (ValueError,KeyError,TypeError):
            self.reply({"status":"DEV_ACK_DENIED","product_pass":False},403)
    def do_GET(self):
        if not self.authorized():return self.reply({"status":"CLIENT_AUTH_DENIED"},403)
        s=self.server
        if self.path=="/status":
            return self.reply({"abi":ABI,"request_id":s.prepared["request_id"],
              "task_sha256":s.prepared["task_contract_sha256"],
              "source_proof_sha256":s.prepared["source_proof_sha256"],
              "source_release_sha256":f03.A05_SOURCE_PIN,
              "source_count":s.prepared["prepared_source_count"],
              "provider_calls":s.provider_calls,
              "product_pass":False,"formal_model_stream_admitted":False,
              "development_only":True})
        if self.path!="/stream" or s.once:
            return self.reply({"status":"NO_REPLAY_OR_UNKNOWN"},403)
        s.once=True
        s.deadline_ns=time.monotonic_ns()+30*10**9
        self.send_response(200);self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-store");self.end_headers()
        rid=s.prepared["request_id"];claims=[]
        task=s.prepared["task_contract_sha256"]
        model_verified=False;provider_done=False;stream_end=False
        count=0;buf=""
        try:
            s.current()
            self.frame("request_start",{"request_id":rid,"task_sha256":task,
                "model":MODEL,"abi":ABI,"source_proof_sha256":s.prepared["source_proof_sha256"]})
            s.provider_calls+=1
            for event in s.generator():
                must(time.monotonic_ns()<s.deadline_ns,
                     "C1_ONE_TASK_30_SECOND_DEADLINE")
                kind=event.get("event")
                if kind=="request_start":
                    must(event.get("model")==MODEL and
                         event.get("route")=="VM_OWNER_CANARY_NONPROD",
                         "PROVIDER_ROUTE_MISMATCH")
                    s.audit({"event":"actual_provider_started","provider":MODEL,
                             "request_id":rid})
                elif kind=="response_headers":
                    must(event.get("status")==200,"PROVIDER_HTTP_NOT_200")
                    s.audit({"event":"provider_response_headers",
                             "status":event["status"]})
                elif kind=="model_identity":
                    model_verified=event.get("model")==MODEL and event.get("model_match") is True
                    must(model_verified,"PROVIDER_REAL_MODEL_IDENTITY_DENIED")
                    s.audit({"event":"real_provider_identity","model":MODEL})
                elif kind=="delta":
                    must(model_verified and not provider_done and count<MAX_EVENTS,
                         "UNQUALIFIED_MODEL_STREAM_OR_BUDGET")
                    chunk=event.get("text")
                    must(type(chunk) is str and chunk and len(chunk)<=4096,
                         "INVALID_NEW_REAL_PROVIDER_DELTA")
                    count+=1;buf+=chunk
                    s.audit({"event":"actual_provider_raw_delta","sha256":digest(chunk.encode()),
                             "sequence":count})
                    while "\n" in buf and len(claims)<2:
                        line,buf=buf.split("\n",1)
                        line=line.strip()
                        if not line:continue
                        claim_id=c1live.OBLIGATIONS[len(claims)]
                        try:
                            v=real_os_semantic_verify(s.repo,s.fence,claim_id,line,
                                    s.prepared["source_proof_sha256"])
                        except Exception as exc:
                            # Actual rejected NEW provider text retained privately
                            # for bounded semantic repair. It is NOT a published
                            # verified answer, provider receipt, or billable claim.
                            failed=s.evidence/"REJECTED_REAL_MODEL_TEXT_DIAGNOSTIC.json"
                            failed.write_text(json.dumps({
                                "rejected_claim_text":line,
                                "text_sha256":digest(line.encode()),
                                "obligation_id":claim_id,
                                "error_type":type(exc).__name__,
                                "error_code":str(exc)[:110],
                                "product_pass":False},indent=2))
                            os.chmod(failed,0o600)
                            raise
                        must(v["accepted"] and not v["signed_semantic_issuer"],
                             "OWNER_OS_SEMANTIC_VERIFICATION_DENIED")
                        s.current()
                        nonce=secrets.token_hex(20);textsha=digest(line.encode())
                        s.pending[claim_id]={"request_id":rid,
                              "challenge":nonce,"text_sha256":textsha}
                        response={"request_id":rid,"task_sha256":task,"seq":len(claims)+1,
                            "claim_id":claim_id,"text":line,"text_sha256":textsha,
                            "challenge":nonce,"citation":v["citation"],
                            "real_model_generated":True,
                            "verified_by_separate_os_pid":v["pid"],
                            "verified_owner_source_not_independent_issuer":True,
                            "provider_done_observed":False,"product_pass":False}
                        self.frame("answer_text",response)
                        with s.ack_cond:
                            deadline=min(time.monotonic()+8,
                                         s.deadline_ns/1e9)
                            while claim_id not in s.acked:
                                remaining=deadline-time.monotonic()
                                must(remaining>0,"ACTUAL_CLIENT_ACK_TIMEOUT")
                                s.ack_cond.wait(timeout=remaining)
                        claims.append(response)
                elif kind=="provider_done":
                    must(model_verified and len(claims)==2 and len(s.acked)==2,
                         "PROVIDER_DONE_BEFORE_NATIVE_CLIENT_VERIFIED_ACKS")
                    provider_done=True;s.done=True
                    s.audit({"event":"actual_provider_done","delta_count":count})
                elif kind=="stream_end":
                    must(provider_done and event.get("provider_done") is True,
                         "REAL_PROVIDER_STREAM_END_DENIED")
                    stream_end=True
                elif kind=="error":
                    raise ValueError("REAL_PROVIDER_ERROR_"+str(event.get("category","UNKNOWN"))[:64])
            must(stream_end and provider_done and len(claims)==2 and not buf.strip() and
                 s.acked==list(c1live.OBLIGATIONS),
                 "REAL_PROVIDER_TERMINAL_OR_CLIENT_ACK_INCOMPLETE")
            s.current()
            answer=" ".join(x["text"] for x in claims)
            self.frame("terminal",{"request_id":rid,"status":"SCOPED_NONPROD_REAL_MINIMAX_A05_ACK",
              "real_model_calls":s.provider_calls,
              "provider_model":MODEL,"real_delta_count":count,
              "task_sha256":task,
              "answer_sha256":digest(answer.encode()),"answer_text":answer,
              "citations":{x["claim_id"]:x["citation"] for x in claims},
              "two_real_client_acks":True,"client_preterminal_observed":True,
              "formal_product_pass":False,"cost":"UNKNOWN","usage":"NOT_OBSERVED",
              "cache":"OFF"})
        except Exception as ex:
            s.audit({"event":"live_dev_fail_closed","reason":type(ex).__name__,
                     "reason_code":str(ex)[:110]})
            try:self.frame("terminal",{"request_id":rid,"status":"DEV_SAFE_ABSTENTION",
                 "real_model_calls":s.provider_calls,"answer_text":None,
                 "product_pass":False})
            except (OSError,BrokenPipeError):pass

class UnixClient(http.client.HTTPConnection):
    def __init__(self,path):super().__init__("c1-dev-unix.local",timeout=70);self.path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.connect(str(self.path))

def client_mode(path:Path,token:Path,evidence:Path):
    cap=c1.read_client_capability(token).decode()
    headers={"Host":"c1-dev-unix.local","X-C1-Local-Capability":cap}
    conn=UnixClient(path);receipts=[]
    try:
        conn.request("GET","/stream",headers=headers)
        r=conn.getresponse();must(r.status==200,"NATIVE_UNIX_CLIENT_STREAM_HTTP_NOT_200")
        name=None;body=None
        while True:
            line=r.readline()
            if not line:break
            line=line.decode().strip()
            if line.startswith("event: "):name=line[7:]
            elif line.startswith("data: "):body=json.loads(line[6:])
            elif line=="" and name and body:
                entry={"event":name,"at_ns":time.monotonic_ns(),
                       "request_id":body.get("request_id"),
                       "model_text_sha256":body.get("text_sha256"),
                       "citation_count":len(body.get("citations",{})) if name=="terminal" else int(bool(body.get("citation")))}
                if name=="answer_text":
                    assert body["provider_done_observed"] is False
                    must(body["text_sha256"]==digest(body["text"].encode()),
                         "VERIFIED_MODEL_TEXT_SHA_MISMATCH")
                    ack={x:body[x] for x in ("request_id","claim_id","challenge","text_sha256")}
                    request=UnixClient(path)
                    try:
                        request.request("POST","/ack",headers={**headers,"Content-Type":"application/json"},
                                        body=json.dumps(ack).encode())
                        a=request.getresponse()
                        entry["ack_http_status"]=a.status
                        entry["ack_receipt"]=json.loads(a.read()).get("status")
                    finally:request.close()
                    must(entry["ack_http_status"]==200,"OS_CLIENT_ACK_NOT_ADMITTED")
                if name=="terminal":
                    entry["status"]=body.get("status")
                    entry["real_model_calls"]=body.get("real_model_calls")
                    entry["answer_sha256"]=body.get("answer_sha256")
                    entry["scope_product_pass"]=body.get("formal_product_pass")
                    entry["full_cited_final"]=bool(body.get("answer_text") and
                                                    len(body.get("citations",{}))==2)
                receipts.append(entry)
                name=body=None
                if entry["event"]=="terminal":break
    finally:conn.close()
    evidence.mkdir(parents=True,exist_ok=True)
    output=evidence/"C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json"
    output.write_text(json.dumps({"client_pid":os.getpid(),"receipts":receipts,
      "genuine_model_generation_only_if_provider_evidence_admitted":True,
      "scope":"OWNER_NONPROD_DEV_NOT_EXTERNAL_SIGNER"},indent=2,sort_keys=True))
    os.chmod(output,0o600)
    return receipts

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=["run","client","verify"])
    ap.add_argument("--repo")
    ap.add_argument("--fence")
    ap.add_argument("--evidence")
    ap.add_argument("--vendor")
    ap.add_argument("--token")
    ap.add_argument("--socket")
    args=ap.parse_args()
    if args.mode=="verify":verify_child();return
    if args.mode=="client":
        receipts=client_mode(Path(args.socket),Path(args.token),Path(args.evidence))
        print(json.dumps({"event_sequence":[x["event"] for x in receipts],
         "client_acks":sum(x.get("ack_http_status")==200 for x in receipts),
         "terminal_status":receipts[-1].get("status") if receipts else "NO_TERMINAL",
         "first_generated_text_ms":None,
         "formal_product_pass":False},sort_keys=True))
        return
    repo=Path(args.repo).resolve();fence=Path(args.fence)
    evidence=Path(args.evidence).resolve();evidence.mkdir(parents=True,exist_ok=True)
    os.chmod(evidence,0o700)
    apath=Path(args.token)
    # Darwin AF_UNIX address has a short native path limit. Isolate ephemeral
    # owner-only socket next to 0600 local capability, never beneath the long
    # evidence tree. The endpoint never survives the one bounded run.
    socketpath=apath.parent/"c1.sock"
    must(stat.S_IMODE(apath.parent.stat().st_mode)==0o700 and
         apath.parent.stat().st_uid==os.geteuid() and
         not socketpath.exists(),"UNIX_SOCKET_OWNER_OR_REPLAY_DENIED")
    server=Server(socketpath,repo=repo,fence=fence,token_file=apath,
                  evidence=evidence,vendor=Path(args.vendor))
    runner=threading.Thread(target=server.serve_forever,daemon=True)
    runner.start()
    try:
        command=[sys.executable,str(Path(__file__).resolve()),"client",
          "--socket",str(socketpath),"--token",str(apath),
          "--evidence",str(evidence)]
        p=subprocess.run(command,capture_output=True,text=True,timeout=80,check=False)
        outcome={"parent_native_server_pid":os.getpid(),
          "client_process_exit":p.returncode,
          "client_stdout_safe":p.stdout[:900],
          "source_prepared":server.prepared,
          "actual_real_provider_call_count":server.provider_calls,
          "real_provider_done_observed":server.done,
          "local_native_ack_count":len(server.acked),
          "formal_product_pass":False,
          "provider":MODEL,"scope":"OWNER_FIRSTPARTY_DEV_DIAGNOSTIC",
          "billing_cost":"UNKNOWN"}
        record=evidence/"C1_REAL_MINIMAX_DEV_RUN_RESULT.json"
        record.write_text(json.dumps(outcome,indent=2,sort_keys=True))
        os.chmod(record,0o600)
        print(json.dumps({"native_server_pid":os.getpid(),"client_exit":p.returncode,
          "real_provider_calls":server.provider_calls,"provider_done":server.done,
          "native_acks":len(server.acked),"product_pass":False,
          "evidence_file":str(record)}))
    finally:
        server.shutdown();server.server_close()
        if socketpath.exists():socketpath.unlink()

if __name__=="__main__":main()
