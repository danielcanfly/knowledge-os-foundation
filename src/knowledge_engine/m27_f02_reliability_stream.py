"""F02 Stage: isolated, cloud-only, two-obligation verified first-text stream.
Reuses the legitimate B1 VM-side MiniMax adapter without accessing its credentials.
Not an authenticated Product, third-party semantic certification, or Q34 modification.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

B1_FILE = Path(__file__).with_name("m27_b1_online_stream_client.py")
_spec = importlib.util.spec_from_file_location("b2_pinned_b1", B1_FILE)
b1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b1)
PROOF = b1.proof
OWNER = "B2_F02_NONPROD_OWNER"
QUESTION = "What is the initial Nonprod semantic answer cache mode, and which tool is first for MacBook engineering?"
OBLIGATIONS = ("cache_initial_mode", "macbook_first_tool")
MAX_LINES = 4
MAX_CHARS = 1800
MAX_DELTAS = 350

def sha(data):
    return hashlib.sha256(data).hexdigest()

def clock():
    return dict(wall_ns=time.time_ns(), monotonic_ns=time.monotonic_ns())

def source_bindings(*, principal=PROOF.OWNER, rights=True, revoked=False):
    return [
        PROOF.authorize_source("cache", principal=principal, rights=rights, revoked=revoked),
        PROOF.authorize_source("commander", principal=principal, rights=rights, revoked=revoked),
    ]

def verify_claim(text, binding, *, rights=True, revoked=False):
    """Source-byte recheck plus deliberately bounded two-fact language, not open entailment."""
    if not rights or revoked:
        return {"accepted":False,"reason":"source_rights_revoked"}
    try:
        fresh = PROOF.authorize_source(binding["source_id"].split("/")[-1],
                                      principal=binding["principal"],
                                      rights=(binding["rights"]=="owner-first-party-nonprod"),
                                      revoked=binding["revoked"])
    except (OSError, KeyError, ValueError) as exc:
        return {"accepted":False,"reason":"source_binding_authorization_failed:"+type(exc).__name__}
    for key in ("source_sha256","source_id","byte_span","excerpt_sha256","quote"):
        if binding.get(key)!=fresh[key]:
            return {"accepted":False,"reason":"source_binding_changed_"+key}
    value=text.strip()
    low=value.lower()
    words=re.findall(r"[a-z]+",low)
    if not value or len(value)>240 or len(words)>36 or re.search(r"[\d\r\n<>]",value):
        return {"accepted":False,"reason":"invalid_shape_or_number"}
    if re.search(r"[^A-Za-z ,.'-]",value) or low.count(".")>1:
        return {"accepted":False,"reason":"invalid_punctuation"}
    # Block changes to negation, scope, modality and extra unrelated assertions.
    forbidden = set("never sometimes may might could probably production tenant tenants unrestricted guaranteed permanently only except without before after instead disabled enabled paid free tomorrow yesterday".split())
    if any(w in forbidden for w in words if w not in ("disabled",)):
        return {"accepted":False,"reason":"unsupported_scope_or_negation"}
    cache = binding["source_id"].endswith("/cache")
    if cache:
        allowed=set("the a semantic answer cache is remains stays initially initial starts off in nonprod environment mode state default turned set to configured as its disabled currently by at first begins within".split())
        supported=("semantic" in words and "cache" in words and "nonprod" in words and
                   ("off" in words or "disabled" in words) and
                   "on" not in words and "enabled" not in words)
        if "disabled" in words and any(w in words for w in ("not","isn't")):
            supported=False
    else:
        allowed=set("all new engineering work tasks activities on a the macbook with remote desktop commander is used uses first starting starts begin begins initiated using tool for as primary initial process by should must relies rely required choice default to use".split())
        supported=(all(w in words for w in ("remote","desktop","commander","macbook")) and
                   any(w in words for w in ("engineering","work","tasks")) and
                   ("first" in words or
                    (any(w in words for w in ("starts","starting","begins","begin","initiated")) and "with" in words)))
    if not supported or any(w not in allowed for w in words):
        return {"accepted":False,"reason":"bounded_entailment_not_established"}
    return {"accepted":True,"reason":"bounded_two_fact_owner_verification",
            **{k:fresh[k] for k in ("source_id","source_sha256","byte_span","excerpt_sha256")},
            "text_sha256":sha(value.encode())}

def validate(receipts, *, require_live=True):
    if len(receipts)!=4 or [r["event"] for r in receipts]!=["request_started","answer_text","answer_text","terminal"]:
        raise ValueError("incomplete_or_replayed_event_sequence")
    rid=receipts[0]["body"].get("request_id")
    for i,r in enumerate(receipts,1):
        if r["body"].get("request_id")!=rid or r["body"].get("seq")!=i:
            raise ValueError("invalid_request_or_sequence")
        if i>1 and r["received_monotonic_ns"]<receipts[i-2]["received_monotonic_ns"]:
            raise ValueError("client_clock_regression")
    answers=receipts[1:3]; terminal=receipts[-1]
    if terminal["body"].get("status")!="answered" or terminal["body"].get("obligations")!=list(OBLIGATIONS):
        raise ValueError("full_answer_obligation_incomplete")
    if [x["body"].get("obligation") for x in answers]!=list(OBLIGATIONS):
        raise ValueError("wrong_claim_identity_or_order")
    if len(set(x["body"].get("text_sha256") for x in answers))!=2:
        raise ValueError("not_distinct_claims")
    for r in answers:
        b=r["body"]
        if (not b.get("generated") or not b.get("verified") or
            r.get("ack_status")!=200 or sha(b.get("text","").encode())!=b.get("text_sha256") or
            b.get("citation",{}).get("source_sha256")!=b1.B1_PINNED_OWNER_SOURCE_SHA256 or
            not b.get("provider_stream_open_at_emit") or
            r["received_monotonic_ns"]>=terminal["received_monotonic_ns"] or
            r.get("ack_monotonic_ns",0)>=terminal["received_monotonic_ns"]):
            raise ValueError("unverified_unacked_buffered_or_late_claim")
    if require_live and not terminal["body"].get("genuine_provider_done"):
        raise ValueError("no_genuine_model_terminal")
    expected=sha("\n".join(r["body"]["text"] for r in answers).encode())
    if terminal["body"].get("answer_sha256")!=expected:
        raise ValueError("final_answer_content_mismatch")
    return True

# Prompt constraints are semantic labels, not pre-written returned answers. All answer
# bytes still MUST originate in genuine VM-side MiniMax streamed deltas.
VM_PROMPT = (
    "Answer the following TWO questions with exactly TWO brief complete English sentences, "
    "one per line, without labels, bullets, commentary, examples or a third sentence. "
    "Question A: What is the initial semantic answer cache mode in Nonprod? "
    "Sentence 1 must describe the semantic answer cache initially being OFF in Nonprod. "
    "Question B: Which tool is FIRST for engineering on MacBook? "
    "Sentence 2 must explain that Remote Desktop Commander is FIRST for engineering on MacBook. "
    "Finish each sentence with a period, then a newline. No speculative qualifiers, "
    "extra facts, changed negation, additional restrictions, or platform statements. "
    "First-party source A: Initial semantic answer cache remains OFF in Nonprod. "
    "First-party source B: All new engineering uses Remote Desktop Commander first on MacBook."
)

VM_PROMPT_B = (
    "Return one concise answer to two separate questions. Output two simple sentences "
    "on separate lines, each ending in a period, with no numbering, bullets or preface. "
    "First describe the INITIAL semantic answer cache mode specifically in Nonprod: OFF. "
    "Second identify the FIRST tool used for engineering work on MacBook: "
    "Remote Desktop Commander. Retain exact meaning without extrapolating, adding dates, "
    "platforms, permission rules or speculative words. "
    "Evidence A: Initial semantic answer cache remains OFF in Nonprod. "
    "Evidence B: All new engineering uses Remote Desktop Commander first on MacBook."
)

def cloud_generation():
    # Narrowly replace the prompt in the already tested VM-side native MiniMax adapter.
    base=b1.VM_PROVIDER_SCRIPT
    start=base.index("prompt=(")
    end=base.index("\npayload=",start)
    variant=os.getenv("F02_CASE_VARIANT","A")
    if variant not in ("A","B"):raise ValueError("unauthorized_prompt_variant")
    prompt=VM_PROMPT if variant=="A" else VM_PROMPT_B
    script=(base[:start]+"prompt="+repr(prompt)+base[end:]).replace(
        "'max_tokens':650","'max_tokens':320").replace("max_tokens=650","max_tokens=320")
    args=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=7",b1.VM,
          "docker","exec","-i",b1.CONTAINER,"python3","-u","-"]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        proc.stdin.write(script)
        proc.stdin.close()
        for n,line in enumerate(proc.stdout,1):
            if n>b1.LIMIT_CHUNKS:raise ValueError("vm_trace_budget_exceeded")
            try:
                event=json.loads(line)
                if not isinstance(event,dict) or "event" not in event:raise ValueError()
            except (ValueError,TypeError):raise ValueError("malformed_vm_provider_event")
            yield event
        proc.wait(timeout=b1.TIMEOUT)
        if proc.returncode:
            yield {"event":"error","category":"vm_nonzero_"+str(proc.returncode)}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if proc.stderr:proc.stderr.close()

class Server(b1.Server):
    def __init__(self, evidence, *, generator=None, rights=True, revoked=False):
        super().__init__(evidence,generator=generator or cloud_generation,rights=rights,revoked=revoked)
        self.RequestHandlerClass=Handler
        self.tenant=OWNER
        self.cancelled=threading.Event()
        self.active_request=None

class Handler(b1.Handler):
    def do_POST(self):
        if self.path!="/cancel":
            return super().do_POST()
        length=int(self.headers.get("Content-Length","0"))
        if not (0<length<=400) or self.headers.get("X-B2-Principal")!=OWNER:
            self.send_error(403);return
        try:
            body=json.loads(self.rfile.read(length))
            ok=bool(self.server.active_request and
                    body.get("request_id")==self.server.active_request[0] and
                    body.get("challenge")==self.server.active_request[1])
        except (ValueError,TypeError):
            ok=False
        if ok:self.server.cancelled.set()
        self.server.audit({"event":"cancel_request","accepted":ok})
        self.send_response(200 if ok else 403)
        self.send_header("Content-Length","0")
        self.end_headers()

    def do_GET(self):
        if self.path!="/stream" or self.headers.get("X-B2-Principal")!=OWNER:
            self.send_error(403);return
        challenge=self.headers.get("X-B2-Challenge","")
        if len(challenge)!=32 or any(c not in "0123456789abcdef" for c in challenge):
            self.send_error(403);return
        rid=secrets.token_hex(12);seq=1
        self.server.cancelled.clear()
        self.server.active_request=(rid,challenge)
        try:
            bindings=source_bindings(rights=self.server.rights,revoked=self.server.revoked)
        except (OSError,ValueError) as exc:
            bindings=[]
            self.server.audit({"event":"source_preflight_rejected","category":type(exc).__name__})
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.frame("request_started",{"request_id":rid,"seq":seq,"challenge_sha256":sha(challenge.encode()),
                                      "question":QUESTION,"obligations":list(OBLIGATIONS)})
        completed=[];buffer="";provider_done=False;delta_count=0;line_count=0
        provider_starts=0;model_confirmed=False
        try:
            if not bindings: raise ValueError("source_not_authorized")
            for event in self.server.generator():
                if self.server.cancelled.is_set():raise ValueError("client_cancelled")
                self.server.audit({"event":"vm_wire","provider_event":event,"request_id":rid})
                kind=event.get("event")
                if kind=="request_start":
                    provider_starts+=1
                    if provider_starts!=1:raise ValueError("second_provider_start_disallowed")
                    continue
                if kind=="model_identity":
                    if not event.get("model_match") or event.get("model")!=b1.MODEL:
                        raise ValueError("model_identity_mismatch")
                    model_confirmed=True
                    continue
                if kind=="error": raise ValueError("provider_error:"+str(event.get("category")))
                if kind=="provider_done":provider_done=True;continue
                if kind=="stream_end":
                    if event.get("provider_done"):provider_done=True
                    else: raise ValueError("provider_stream_incomplete")
                    continue
                if kind!="delta":continue
                if provider_starts!=1 or not model_confirmed:
                    raise ValueError("unauthenticated_provider_delta")
                delta_count+=1
                if delta_count>MAX_DELTAS:raise ValueError("too_many_provider_deltas")
                chunk=event.get("text")
                if not isinstance(chunk,str) or not chunk:raise ValueError("malformed_delta")
                buffer+=chunk
                if len(buffer)>MAX_CHARS: raise ValueError("provider_text_budget")
                while "\n" in buffer or "." in buffer:
                    candidates=[(buffer.index(d),d) for d in ("\n",".") if d in buffer]
                    pos,delimiter=min(candidates)
                    line=buffer[:pos+(delimiter==".")]
                    buffer=buffer[pos+1:]
                    line=line.strip()
                    if not line:continue
                    line_count+=1
                    if line_count>MAX_LINES:raise ValueError("too_many_model_lines")
                    index=(line_count-1)%2
                    verdict=verify_claim(line,bindings[index],
                                         rights=self.server.rights,revoked=self.server.revoked)
                    self.server.audit({"event":"verify","claim_index":index,"model_line":line_count,
                                       "verdict":verdict,"text_sha256":sha(line.encode()),"request_id":rid})
                    if len(completed)>=2:
                        # Model may continue generating. These bytes are OUTSIDE the
                        # fully verified two-obligation answer and never published.
                        if not verdict["accepted"]:
                            raise ValueError("unsupported_post_answer_tail")
                        self.server.audit({"event":"excluded_unpublished_tail","line":line_count,
                                           "tail_verifier_accepted":bool(verdict["accepted"]),
                                           "text_sha256":sha(line.encode()),"request_id":rid})
                        continue
                    if not verdict["accepted"]:
                        raise ValueError("unsupported_generated_line_"+str(line_count)+":"+verdict["reason"])
                    if index!=len(completed):raise ValueError("incorrect_claim_order")
                    seq+=1
                    nonce=secrets.token_hex(20)
                    pending={"request_id":rid,"seq":seq,"text_sha256":sha(line.encode()),
                             "challenge":challenge,"used":False,"ack":threading.Event()}
                    with self.server.lock:self.server.pending[nonce]=pending
                    self.frame("answer_text",{"request_id":rid,"seq":seq,"text":line,"nonce":nonce,
                          "challenge":challenge,"text_sha256":pending["text_sha256"],
                          "obligation":OBLIGATIONS[index],"citation":{k:verdict[k] for k in
                              ("source_id","source_sha256","byte_span","excerpt_sha256")},
                          "verified":True,"generated":True,"provider_stream_open_at_emit":not provider_done,
                          "vm_delta_wall_ns":event.get("wall_ns"),
                          "vm_delta_monotonic_ns":event.get("monotonic_ns")})
                    self.server.audit({"event":"claim_verified_and_sent","claim_index":index,
                                       "seq":seq,"request_id":rid})
                    if not pending["ack"].wait(6):raise ValueError("client_ack_missing")
                    with self.server.lock:self.server.pending.pop(nonce,None)
                    completed.append(line)
            # A trailing incomplete line may be valid only after genuine provider stop.
            if buffer.strip():
                line=buffer.strip();index=line_count%2
                verdict=verify_claim(line,bindings[index],rights=self.server.rights,
                                     revoked=self.server.revoked)
                self.server.audit({"event":"verify_final_fragment","verdict":verdict,
                                   "text_sha256":sha(line.encode()),"request_id":rid})
                if len(completed)<2 or not verdict["accepted"]:
                    raise ValueError("incomplete_or_unsupported_final_fragment")
                self.server.audit({"event":"excluded_unpublished_final_fragment",
                                   "text_sha256":sha(line.encode()),"request_id":rid})
            if not provider_done or len(completed)!=2 or delta_count<1 or provider_starts!=1 or not model_confirmed:
                raise ValueError("full_verified_cloud_answer_missing")
            for i, published in enumerate(completed):
                final_check=verify_claim(published,bindings[i],rights=self.server.rights,
                                         revoked=self.server.revoked)
                self.server.audit({"event":"final_source_reverify","claim_index":i,
                                   "verdict":final_check,"request_id":rid})
                if not final_check["accepted"]:
                    raise ValueError("claim_revoked_or_stale_before_terminal")
            if self.server.cancelled.is_set():raise ValueError("client_cancelled_before_terminal")
            seq+=1
            self.frame("terminal",{"request_id":rid,"seq":seq,"status":"answered",
                      "obligations":list(OBLIGATIONS),"answer_sha256":sha("\n".join(completed).encode()),
                      "genuine_provider_done":True,"published_claims":2})
        except (ValueError,KeyError,TypeError,OSError,TimeoutError) as exc:
            self.server.audit({"event":"fail_closed","reason":str(exc),"request_id":rid,
                               "published_claims":len(completed)})
            try:
                self.frame("terminal",{"request_id":rid,"seq":seq+1,
                          "status":"partial_terminated" if completed else "safe_abstention",
                          "obligations_met":len(completed),"genuine_provider_done":provider_done})
            except (BrokenPipeError,ConnectionResetError,OSError):pass
        finally:
            with self.server.lock:
                self.server.pending.clear()
                self.server.active_request=None

def client(port,evidence,*,forged=False,drop_after_first=False,cancel_after_first=False):
    challenge=secrets.token_hex(16)
    req=Request(f"http://127.0.0.1:{port}/stream",
                headers={"X-B2-Principal":OWNER,"X-B2-Challenge":challenge})
    receipts=[]
    try:
        with urlopen(req,timeout=b1.TIMEOUT) as stream:
            while True:
                packet=bytearray()
                while True:
                    line=stream.readline()
                    if not line:break
                    packet+=line
                    if line==b"\n":break
                if not packet:break
                event,body=b1.parse_sse(bytes(packet))
                item={"event":event,"body":body,**{"received_"+k:v for k,v in clock().items()},
                      "client_pid":os.getpid()}
                if event=="answer_text":
                    ack={k:body[k] for k in ("request_id","seq","text_sha256","nonce","challenge")}
                    if forged:ack["text_sha256"]="0"*64
                    post=Request(f"http://127.0.0.1:{port}/ack",data=json.dumps(ack).encode(),
                                 headers={"Content-Type":"application/json"})
                    try:
                        with urlopen(post,timeout=8) as resp:item["ack_status"]=resp.status
                    except HTTPError as exc:item["ack_status"]=exc.code
                    item["ack_wall_ns"]=time.time_ns()
                    item["ack_monotonic_ns"]=time.monotonic_ns()
                    if cancel_after_first and not any(x["event"]=="answer_text" for x in receipts):
                        cancel=Request(f"http://127.0.0.1:{port}/cancel",
                           data=json.dumps({"request_id":body["request_id"],
                                            "challenge":challenge}).encode(),
                           headers={"Content-Type":"application/json","X-B2-Principal":OWNER})
                        with urlopen(cancel,timeout=8) as resp:
                            item["cancel_status"]=resp.status
                receipts.append(item)
                if drop_after_first and event=="answer_text":break
                if event=="terminal":break
    except (OSError,ValueError) as exc:
        failure=type(exc).__name__
    else:failure=None
    try:validated=validate(receipts)
    except (ValueError,KeyError,TypeError) as exc:validated=False;failure=str(exc)
    evidence=Path(evidence);evidence.mkdir(parents=True,exist_ok=True)
    result={"client_pid":os.getpid(),"client_validated":validated,
            "validation_failure":failure,"receipts":receipts,
            "challenge_sha256":sha(challenge.encode())}
    (evidence/"independent_client_receipts.json").write_text(json.dumps(result,indent=2))
    return result

def run(evidence):
    srv=Server(evidence)
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    try:
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),"client",
                          "--port",str(srv.server_port),"--evidence",str(evidence)],
                         capture_output=True,text=True,timeout=b1.TIMEOUT+20)
        if p.returncode:raise RuntimeError("client_process_failed:"+p.stderr[-300:])
        result=json.loads(p.stdout)
        log=Path(evidence)/"server_vm_wire.jsonl"
        events=[json.loads(line) for line in log.read_text().splitlines()]
        result["server_trace_events"]=len(events)
        result["provider"]=b1.MODEL
        result["provider_done_observed"]=any(e.get("event")=="vm_wire" and
             (e.get("provider_event") or {}).get("event")=="provider_done" for e in events)
        result["provider_delta_count"]=sum(e.get("event")=="vm_wire" and
            (e.get("provider_event") or {}).get("event")=="delta" for e in events)
        (Path(evidence)/"run_summary.json").write_text(json.dumps(result,indent=2))
        return result
    finally:
        srv.shutdown();srv.server_close();thread.join(3)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=("run","client"))
    ap.add_argument("--evidence",required=True,type=Path)
    ap.add_argument("--port",type=int)
    args=ap.parse_args()
    result=run(args.evidence) if args.mode=="run" else client(args.port,args.evidence)
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
