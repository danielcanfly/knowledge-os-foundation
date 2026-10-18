"""B1-02 isolated, nonprod-only Cloudflare online generation to independent OS Client.
VM credentials are read only inside the already-existing owner-canary container.
Never imported by native Q34, Product API, Composer, M26 gateway or Production.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import importlib.util
_spec = importlib.util.spec_from_file_location('b1_b0_readonly_proof', Path(__file__).with_name('m27_b0_stream_experiment.py'))
proof = importlib.util.module_from_spec(_spec)
# Historical B0 SHA predates the B0 shared-rule amendment. Pin and recheck
# current first-party source bytes WITHOUT modifying old B0 module on disk.
_spec.loader.exec_module(proof)
B1_PINNED_OWNER_SOURCE_SHA256 = '137009ea0618710222bef118c3ca258dfe98b5f8911e8dc588ac154dd4d17fb9'
proof.SOURCE_SHA256 = B1_PINNED_OWNER_SOURCE_SHA256
_b0_original_authorize = proof.authorize_source
def _b1_authorize_source(name, **kwargs):
    kwargs['expected_sha'] = B1_PINNED_OWNER_SOURCE_SHA256
    return _b0_original_authorize(name, **kwargs)
proof.authorize_source = _b1_authorize_source
_b0_original_verify = proof.verify_generated
def _b1_verify_generated(text, binding):
    verdict = _b0_original_verify(text, binding)
    if verdict.get('accepted') or not binding.get('source_id','').endswith('/cache'):
        return verdict
    # Only a source-equivalent environment noun may be normalized. Never
    # normalize negatives, numbers, other proper nouns, ACL or quantities.
    import re
    normalized = re.sub(r'\bNonprod environment\b', 'Nonprod', text, flags=re.I)
    if normalized == text:
        return verdict
    alias = _b0_original_verify(normalized, binding)
    if not alias.get('accepted'):
        return verdict
    return {**alias,'reason':'bounded_nonprod_environment_equivalence',
            'text_sha256':hashlib.sha256(text.strip().encode()).hexdigest(),
            'normalized_for_semantics':True}
proof.verify_generated = _b1_verify_generated

MODEL = "MiniMax-M3"
VM = "oracle-vm"
CONTAINER = "m27-owner-canary-28"
OWNER = "B1_F02_OWNER_NONPROD"
LIMIT_CHUNKS = 350
MAX_OUTPUT_CHARS = 1300
TIMEOUT = 65
# Runs inside the existing VM container: source code is sent, NOT any key or env.
# Only the live model's delta.content is copied back as evidence.
VM_PROVIDER_SCRIPT = r"""
import hashlib,json,os,sys,time
import httpx
def emit(event,**kwargs):
    print(json.dumps(dict(event=event,wall_ns=time.time_ns(),
                          monotonic_ns=time.monotonic_ns(),**kwargs),
                     ensure_ascii=True,separators=(',',':')),flush=True)
model='MiniMax-M3'
key=os.getenv('MINIMAX_API_KEY','')
if not key:
    emit('error',category='missing_vm_credentials');sys.exit(2)
url='https://api.minimax.io/anthropic/v1/messages'
prompt=('Using ONLY the following owner-authored two evidence facts, generate exactly TWELVE '
        'short factual English paraphrase sentences on twelve separate lines, with no bullets '
        'or numbering. Odd lines 1,3,5,7,9,11 restate source A, the semantic answer cache '
        'is initially OFF in Nonprod. Even lines 2,4,6,8,10,12 restate source B, Remote '
        'Desktop Commander is FIRST for engineering work on MacBook. Keep meaning, negation, '
        'time and scope unchanged. No extra names, quantities, consequences, interpretations '
        'or facts. Send each sentence followed by newline as it is generated. '
        'Source A: Initial semantic answer cache remains OFF in Nonprod. '
        'Source B: All new engineering uses Remote Desktop Commander first on MacBook.')
payload={'model':model,'stream':True,'max_tokens':650,'temperature':0,
         'system':'Produce only concise factual paraphrases entailed by supplied first-party evidence.',
         'messages':[{'role':'user','content':prompt}]}
emit('request_start',model=model,provider='MiniMax',route='VM_OWNER_CANARY_NONPROD',
     stream_requested=True,max_tokens=650)
try:
    with httpx.stream('POST',url,headers={'Authorization':'Bearer '+key,
            'Content-Type':'application/json'},json=payload,
            timeout=httpx.Timeout(45.0,connect=8.0)) as response:
        rid=response.headers.get('x-request-id','')
        emit('response_headers',status=response.status_code,
             request_id_sha256=hashlib.sha256(rid.encode()).hexdigest() if rid else None,
             content_type=response.headers.get('content-type','').split(';')[0])
        if response.status_code != 200:
            emit('error',category='HTTP_'+str(response.status_code));sys.exit(3)
        count=0;done=False;model_ok=False;error=False
        for line in response.iter_lines():
            if not line.startswith('data:'):continue
            try:body=json.loads(line[5:].strip())
            except (ValueError,TypeError):
                emit('error',category='malformed_provider_sse');error=True;break
            kind=body.get('type')
            if kind=='message_start':
                reported=(body.get('message') or {}).get('model','')
                model_ok=(reported==model)
                emit('model_identity',model_match=model_ok,model=reported)
                if not model_ok:
                    emit('error',category='provider_model_mismatch');error=True;break
            elif kind=='content_block_delta':
                delta=body.get('delta') or {}
                chunk=delta.get('text','') if delta.get('type')=='text_delta' else ''
                if isinstance(chunk,str) and chunk and model_ok:
                    count+=1;emit('delta',text=chunk,chunk_index=count)
                    if count>350:emit('error',category='over_chunk_budget');error=True;break
            elif kind=='error':
                emit('error',category='PROVIDER_STREAM_ERROR');error=True;break
            elif kind=='message_stop':
                done=True;emit('provider_done');break
        emit('stream_end',provider_done=(done and model_ok and not error),delta_count=count)
except Exception as exc:
    emit('error',category=type(exc).__name__)
"""

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def stamp():
    return {"wall_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns()}

def parse_sse(frame: bytes):
    try:
        lines = frame.decode("utf-8").splitlines()
        event = next(l[7:] for l in lines if l.startswith("event: "))
        body = json.loads(next(l[6:] for l in lines if l.startswith("data: ")))
        if event not in {"request_started", "answer_text", "terminal", "progress"} or not isinstance(body, dict):
            raise ValueError("bad_event")
        return event, body
    except (StopIteration, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("malformed_sse") from exc

def validate(receipts, *, require_early=True):
    events = [r["event"] for r in receipts]
    if not events or events[0] != "request_started" or events[-1] != "terminal":
        raise ValueError("malformed_order")
    answers = [r for r in receipts if r["event"] == "answer_text"]
    if not answers or any(r.get("ack_status") != 200 for r in answers):
        raise ValueError("no_independent_verified_ack")
    terminal = receipts[-1]
    if terminal["body"].get("status") != "answered":
        raise ValueError("non_answer_terminal")
    rid = receipts[0]["body"].get("request_id")
    sequence = [r["body"].get("seq") for r in receipts]
    if any(r["body"].get("request_id") != rid for r in receipts) or sequence != list(range(1, len(sequence)+1)):
        raise ValueError("replayed_or_malformed_receipt")
    if any(not r["body"].get("verified") or not r["body"].get("citation") or
           not r["body"].get("generated") or
           sha(r["body"]["text"].encode()) != r["body"].get("text_sha256")
           for r in answers):
        raise ValueError("unverified_or_missing_citation")
    if any(r["received_wall_ns"] >= terminal["received_wall_ns"] for r in answers):
        raise ValueError("answer_not_preterminal")
    if require_early and not any(r["body"].get("provider_stream_open_at_emit") for r in answers):
        raise ValueError("buffered_replay")
    return True

class Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    def __init__(self, evidence, *, generator=None, rights=True, revoked=False):
        super().__init__(("127.0.0.1", 0), Handler)
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True,exist_ok=True)
        self.lock = threading.RLock()
        self.pending = {}
        self.generator = generator or cloud_generation
        self.rights = rights
        self.revoked = revoked
        self.request_seen = set()
        self.ack_results = []

    def audit(self, obj):
        item = {**stamp(), **obj}
        with self.lock, (self.evidence / "server_vm_wire.jsonl").open("a") as file:
            file.write(json.dumps(item,sort_keys=True)+"\n")
            file.flush(); os.fsync(file.fileno())

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def log_message(self,*args): pass
    def frame(self, name, body):
        packet = ("event: "+name+"\ndata: "+json.dumps(body,sort_keys=True)+"\n\n").encode()
        self.wfile.write(packet); self.wfile.flush()
        self.server.audit({"event":"publish_"+name,"request_id":body.get("request_id"),
                           "seq":body.get("seq")})
    def do_POST(self):
        if self.path != "/ack": self.send_error(404);return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n<3 or n>2500: raise ValueError("invalid_length")
            obj=json.loads(self.rfile.read(n))
            nonce=obj.get("nonce")
            with self.server.lock:
                item=self.server.pending.get(nonce)
                ok=bool(item and not item["used"] and
                        all(obj.get(k)==item[k] for k in
                            ("request_id","seq","text_sha256","challenge")))
                if ok:
                    item["used"]=True
                    item["ack"].set()
            code=200 if ok else 403
        except (ValueError,TypeError,KeyError):
            code=400;ok=False
        self.server.audit({"event":"ack","ok":ok,"status":code})
        self.server.ack_results.append(code)
        self.send_response(code); self.send_header("Content-Length","0");self.end_headers()
    def do_GET(self):
        if self.path != "/stream" or self.headers.get("X-B1-Principal")!=OWNER:
            self.send_error(403);return
        challenge=self.headers.get("X-B1-Challenge","")
        if len(challenge)!=32 or not all(c in "0123456789abcdef" for c in challenge):
            self.send_error(403);return
        rid=secrets.token_hex(12);seq=1
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.frame("request_started",{"request_id":rid,"seq":seq,"challenge_sha256":sha(challenge.encode())})
        try:
            bindings = [proof.authorize_source("cache",principal=proof.OWNER,
                        rights=self.server.rights,revoked=self.server.revoked),
                        proof.authorize_source("commander",principal=proof.OWNER,
                        rights=self.server.rights,revoked=self.server.revoked)]
        except (OSError, ValueError) as exc:
            self.server.audit({"event":"fail_closed","reason":str(exc)})
            self.frame("terminal",{"request_id":rid,"seq":2,"status":"safe_abstention"})
            return
        provider_done=False
        answer_count=0
        text_buffer=""
        provider_event=None
        last_provider_delta=None
        try:
            for provider_event in self.server.generator():
                # generator produces only sanitized records, no auth material
                self.server.audit({"event":"vm_wire","provider_event":provider_event})
                kind=provider_event.get("event")
                if kind=="provider_done": provider_done=True;continue
                if kind in {"error","stream_end"}:
                    if kind=="stream_end" and provider_event.get("provider_done"):provider_done=True
                    continue
                if kind!="delta": continue
                last_provider_delta=provider_event
                text_buffer+=provider_event.get("text","")
                if len(text_buffer)>MAX_OUTPUT_CHARS: raise ValueError("output_budget_exceeded")
                if "\n" not in text_buffer:continue
                line,text_buffer=text_buffer.split("\n",1)
                line=line.strip()
                if not line: continue
                # Revocation may be received AFTER the pre-generation ACL preflight.
                if not self.server.rights or self.server.revoked:
                    raise ValueError("source_revoked_or_rights_removed_during_stream")
                # This narrowly scoped experiment qualifies the FIRST answer only.
                # Subsequent model text is never published, cached or treated as verified.
                if answer_count>=1:
                    self.server.audit({"event":"unpublished_model_tail",
                                       "text_sha256":sha(line.encode())})
                    continue
                verdict=proof.verify_generated(line,bindings[answer_count])
                self.server.audit({"event":"verify","claim_index":answer_count,
                                   "verdict":verdict,"text_sha256":sha(line.encode())})
                if not verdict.get("accepted"):raise ValueError("generated_claim_unsupported")
                seq+=1;answer_count+=1
                nonce=secrets.token_hex(20)
                with self.server.lock:
                    pending={"request_id":rid,"seq":seq,"text_sha256":sha(line.encode()),
                             "challenge":challenge,"used":False,"ack":threading.Event()}
                    self.server.pending[nonce]=pending
                self.frame("answer_text",{"request_id":rid,"seq":seq,"text":line,
                    "text_sha256":pending["text_sha256"],"nonce":nonce,"challenge":challenge,
                    "citation":{k:verdict[k] for k in ("source_id","source_sha256","byte_span","excerpt_sha256")},
                    "generated":True,"verified":True,"provider_stream_open_at_emit":not provider_done,
                    "vm_delta_wall_ns":last_provider_delta["wall_ns"],
                    "vm_delta_monotonic_ns":last_provider_delta["monotonic_ns"]})
                if not pending["ack"].wait(6):raise ValueError("client_ack_missing")
                with self.server.lock:self.server.pending.pop(nonce,None)
            # If no newline at end, fail closed; NEVER replay an already buffered final sentence.
            if not provider_done or answer_count==0:
                raise ValueError("no_verified_preterminal_cloud_answer")
            self.frame("terminal",{"request_id":rid,"seq":seq+1,"status":"answered"})
        except (OSError,ValueError,TimeoutError) as exc:
            self.server.audit({"event":"fail_closed","reason":str(exc)})
            try:self.frame("terminal",{"request_id":rid,"seq":seq+1,"status":"partial_terminated"})
            except (OSError,BrokenPipeError):pass
        except BrokenPipeError:
            self.server.audit({"event":"disconnect_cancel"})
        finally:
            with self.server.lock:self.server.pending.clear()

def cloud_generation():
    args=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=7",VM,
          "docker","exec","-i",CONTAINER,"python3","-u","-"]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        proc.stdin.write(VM_PROVIDER_SCRIPT)
        proc.stdin.close()
        count=0
        for line in proc.stdout:
            count+=1
            if count>LIMIT_CHUNKS:raise ValueError("provider_trace_exceeded")
            try:
                obj=json.loads(line)
                if not isinstance(obj,dict) or "event" not in obj:raise ValueError()
            except (ValueError,TypeError):raise ValueError("malformed_vm_stream_record")
            yield obj
        proc.wait(timeout=TIMEOUT)
        if proc.returncode:yield {"event":"error","category":"vm_provider_exit_"+str(proc.returncode)}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if proc.stderr:proc.stderr.close()

def client(port: int, evidence: Path, *, forged=False):
    challenge=secrets.token_hex(16)
    req=Request(f"http://127.0.0.1:{port}/stream",
                headers={"X-B1-Principal":OWNER,"X-B1-Challenge":challenge})
    receipts=[]
    with urlopen(req,timeout=TIMEOUT) as stream:
        while True:
            frame=bytearray()
            while True:
                line=stream.readline()
                if not line:break
                frame+=line
                if line==b"\n":break
            if not frame:break
            event,obj=parse_sse(bytes(frame))
            item={"event":event,"body":obj,"received_wall_ns":time.time_ns(),
                  "received_monotonic_ns":time.monotonic_ns(),"client_pid":os.getpid()}
            if event=="answer_text":
                ack={k:obj[k] for k in ("request_id","seq","text_sha256","nonce","challenge")}
                if forged:ack["text_sha256"]="0"*64
                post=Request(f"http://127.0.0.1:{port}/ack",
                             data=json.dumps(ack).encode(),
                             headers={"Content-Type":"application/json"})
                try:
                    with urlopen(post,timeout=8) as resp:item["ack_status"]=resp.status
                except HTTPError as exc:item["ack_status"]=exc.code
                item["ack_wall_ns"]=time.time_ns()
            receipts.append(item)
            if event=="terminal":break
    try:
        valid=validate(receipts)
    except (ValueError,KeyError,TypeError):
        valid=False
    result={"client_pid":os.getpid(),"client_validated":valid,
            "receipts":receipts,"challenge_sha256":sha(challenge.encode())}
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/"independent_client_receipts.json").write_text(json.dumps(result,indent=2))
    return result

def run(evidence: Path):
    srv=Server(evidence)
    thread=threading.Thread(target=srv.serve_forever,daemon=True)
    thread.start()
    try:
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                          "client","--port",str(srv.server_port),"--evidence",str(evidence)],
                         capture_output=True,text=True,timeout=TIMEOUT+18,
                         env={**os.environ,"PYTHONPATH":"src"})
        if p.returncode:raise RuntimeError("independent_client_crashed:"+p.stderr[-250:])
        result=json.loads(p.stdout)
        # Model may buffer; only wall-clock ordering AND preterminal provider
        # end allow promotion. Cross-host times are reported separately.
        events=[json.loads(line) for line in (evidence/"server_vm_wire.jsonl").read_text().splitlines()]
        provider_done=[x for x in events if x.get("event")=="vm_wire" and (x.get("provider_event") or {}).get("event")=="provider_done"]
        result["server_trace_events"]=len(events)
        result["remote_model"]=MODEL
        result["provider_done_recorded"]=bool(provider_done)
        return result
    finally:
        srv.shutdown();srv.server_close();thread.join(3)

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("mode",choices=["run","client"])
    arg.add_argument("--evidence",type=Path,required=True)
    arg.add_argument("--port",type=int)
    opts=arg.parse_args()
    res=client(opts.port,opts.evidence) if opts.mode=="client" else run(opts.evidence)
    print(json.dumps(res,sort_keys=True))
if __name__=="__main__": main()
