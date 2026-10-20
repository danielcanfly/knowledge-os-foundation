"""C1 owner-firstparty NONPROD cloud-first streaming adapter (separate from Q34 Gateway).

Cloudflare endpoint/model follow deployed M26 *direct Workers AI*, not the
previously refused custom Gateway/Q34 probe. No secrets leave owner-canary.
This is an isolated Dev Provider trace and does NOT certify the separate
formally signed C1 Product Provider/Issuer/IdP gates.
"""
from __future__ import annotations
import json,os,subprocess,time
from pathlib import Path
from typing import Iterator
from m27_c1_dev_minimax_a05_e2e import MODEL as MINIMAX, vendor_generator

MODEL = "@cf/openai/gpt-oss-120b"
ROUTE = "M26_DIRECT_WORKERS_AI_OWNER_CANARY_NONPROD"
MINIMAX_ROUTE = "VM_OWNER_CANARY_NONPROD"
MAX_PROVIDER_EVENTS=256
MAX_SSE_BYTES=32768
# Source deployed M26 only eligible infrastructure/availability classes.
# Never fallback after malformed provider events, identity/semantic/ACL
# denials, unsupported provider protocol or a partial visible answer.
FALLBACK_ELIGIBLE=frozenset({
 "CLOUDFLARE_DAILY_QUOTA_EXHAUSTED_3036",
 "CLOUDFLARE_TRANSIENT_CAPACITY_3040",
 "CLOUDFLARE_RATE_LIMIT_OR_CAPACITY_429",
 "CLOUDFLARE_TIMEOUT_OR_NETWORK_TRANSIENT",
 "CLOUDFLARE_HTTP_408",
 "CLOUDFLARE_HTTP_500",
 "CLOUDFLARE_HTTP_502",
 "CLOUDFLARE_HTTP_503",
 "CLOUDFLARE_HTTP_504",
})
VM="oracle-vm"
CONTAINER="m27-owner-canary-28"

# Executed only inside already-running Owner Canary. Reads env in process
# and emits original non-secret generated deltas + bounded model metadata.
# Calls exact current M26 direct /ai/v1/chat/completions, NOT AI Gateway.
# No Authorization header/credentials/account id printed.
VM_STREAM_SCRIPT=r"""
import hashlib,json,os,sys,time
import httpx
def emit(event,**kw):
    print(json.dumps(dict(event=event,**kw),ensure_ascii=True,separators=(',',':')),flush=True)
model='@cf/openai/gpt-oss-120b'
account=os.getenv('CLOUDFLARE_ACCOUNT_ID','')
key=(os.getenv('CLOUDFLARE_WORKER_AI_RESTFUL_API_KEY') or
     os.getenv('CLOUDFLARE_AI_TOKEN') or os.getenv('CLOUDFLARE_API_TOKEN') or '')
if not account or not key:
    emit('error',category='CLOUDFLARE_AUTH_OR_CONFIG');sys.exit(0)
url='https://api.cloudflare.com/client/v4/accounts/'+account+'/ai/v1/chat/completions'
prompt=json.loads(sys.stdin.readline())
if not isinstance(prompt,str) or not (50<=len(prompt)<=1400):
    emit('error',category='C1_PROMPT_BAD_SCOPE');sys.exit(0)
payload={'model':model,'messages':[
    {'role':'system','content':'Only two exact source-grounded short factual English sentences, each a new line. No unsupported claims or rationale.'},
    {'role':'user','content':prompt}],
    'stream':True,'max_tokens':192,'temperature':0,
    'reasoning_effort':'low'}
emit('request_start',model=model,route='M26_DIRECT_WORKERS_AI_OWNER_CANARY_NONPROD',
     stream_requested=True,max_tokens=192)
try:
    with httpx.stream('POST',url,headers={
       'Authorization':'Bearer '+key,'Content-Type':'application/json'},
       json=payload,timeout=httpx.Timeout(25,connect=6)) as response:
        status=response.status_code
        emit('response_headers',status=status,
             content_type=response.headers.get('content-type','').split(';')[0])
        if status!=200:
            # M26 error body may contain Cloudflare 3036/5035; never expose it.
            bounded=response.read()[:8192] if status in (400,401,403,408,429,500,502,503,504) else b''
            category=('CLOUDFLARE_DAILY_QUOTA_EXHAUSTED_3036' if status==429 and b'3036' in bounded
                      else 'CLOUDFLARE_TRANSIENT_CAPACITY_3040' if status==429 and b'3040' in bounded
                      else 'CLOUDFLARE_PAID_PLAN_ONLY_5035' if status==403 and b'5035' in bounded
                      else 'CLOUDFLARE_AUTH_OR_CONFIG' if status in (401,403,404)
                      else 'CLOUDFLARE_RATE_LIMIT_OR_CAPACITY_429' if status==429
                      else 'CLOUDFLARE_HTTP_'+str(status))
            emit('error',category=category)
            sys.exit(0)
        if not response.headers.get('content-type','').lower().startswith('text/event-stream'):
            emit('error',category='CLOUDFLARE_STREAM_PROTOCOL_MISMATCH')
            sys.exit(0)
        got_model=False;done=False;deltas=0;finish=False;usage_seen=False;empty_tail_seen=False;native_tail_seen=False;heartbeat_seen=False
        total_deadline=time.monotonic()+30
        for i,line in enumerate(response.iter_lines()):
            if time.monotonic()>=total_deadline:
                done=False
                emit('error',category='CLOUDFLARE_STREAM_TOTAL_DEADLINE')
                break
            if i>256:
                done=False
                emit('error',category='CLOUDFLARE_EVENT_BUDGET')
                break
            if done:
                if line.strip() and not line.lstrip().startswith(':'):
                    done=False
                    emit('error',category='CLOUDFLARE_FRAME_AFTER_DONE_DENIED')
                    break
                continue
            if not line.startswith('data:'):
                if line.strip() and not line.lstrip().startswith(':'):
                    emit('error',category='CLOUDFLARE_UNKNOWN_SSE_METADATA')
                    break
                continue
            raw=line[5:].strip()
            if raw=='[DONE]':
                if not finish or not got_model or deltas==0:
                    emit('error',category='CLOUDFLARE_PREMATURE_DONE_DENIED')
                    break
                done=True
                continue
            if len(raw)>32768:
                emit('error',category='CLOUDFLARE_WIRE_TOO_LONG')
                break
            try:
                part=json.loads(raw)
                if not isinstance(part,dict):raise ValueError()
                reported=part.get('model')
                if reported:
                    # Model identification must be pinned, never a different
                    # vendor/model across fallback or reasoning metadata.
                    if reported not in ('@cf/openai/gpt-oss-120b','gpt-oss-120b'):
                        emit('error',category='CLOUDFLARE_MODEL_MISMATCH')
                        break
                    if not got_model:
                        emit('model_identity',model=model,model_match=True)
                        got_model=True
                choices=part.get('choices')
                if finish:
                    # Some genuine Cloudflare Workers AI streams end in a
                    # native (non-OpenAI) empty response + cumulative usage
                    # frame, after stop and before [DONE]. This is metadata,
                    # NOT a second answer or accepted model text.
                    if 'response' in part:
                        if (native_tail_seen or usage_seen or empty_tail_seen or
                            'choices' in part or
                            not set(part).issubset({'response','usage',
                              'model','id','object','created','system_fingerprint'})
                            or part.get('response')!='' or
                            not isinstance(part.get('usage'),dict)):
                            emit('error',category='CLOUDFLARE_POSTFINISH_DATA_DENIED')
                            break
                        native_tail_seen=True
                        continue
                    # OpenAI-compatible providers may also emit bounded
                    # nonanswer control frames, never any late material text.
                    safe_fields={'id','object','created','model','choices',
                                 'usage','system_fingerprint'}
                    if not set(part).issubset(safe_fields):
                        emit('error',category='CLOUDFLARE_POSTFINISH_DATA_DENIED')
                        break
                    usage=part.get('usage')
                    if choices==[]:
                        # Cloudflare may emit ONE empty heartbeat without
                        # usage. It is not an answer or a terminal grant.
                        if usage is None:
                            if heartbeat_seen:
                                emit('error',category='CLOUDFLARE_POSTFINISH_DATA_DENIED')
                                break
                            heartbeat_seen=True
                            continue
                        if (usage_seen or not isinstance(usage,dict) or
                            not all(type(usage.get(k)) is int and usage[k]>=0
                              for k in ('prompt_tokens','completion_tokens',
                                        'total_tokens')) or
                            usage['total_tokens'] < max(usage['prompt_tokens'],
                                                         usage['completion_tokens'])):
                            emit('error',category='CLOUDFLARE_POSTFINISH_DATA_DENIED')
                            break
                        usage_seen=True
                        continue
                    if (empty_tail_seen or not isinstance(choices,list) or
                        len(choices)!=1 or not isinstance(choices[0],dict) or
                        usage not in (None,{}) or
                        not set(choices[0]).issubset(
                            {'index','delta','finish_reason','logprobs'})):
                        emit('error',category='CLOUDFLARE_POSTFINISH_DATA_DENIED')
                        break
                    tail=choices[0]
                    chunk=tail.get('delta')
                    if (not isinstance(chunk,dict) or
                        not set(chunk).issubset({'content','role'}) or
                        chunk.get('content') not in (None,'') or
                        chunk.get('role','assistant')!='assistant' or
                        tail.get('finish_reason') not in (None,'stop') or
                        tail.get('index',0)!=0 or
                        tail.get('logprobs') not in (None,{})):
                        emit('error',category='CLOUDFLARE_POSTFINISH_DATA_DENIED')
                        break
                    empty_tail_seen=True
                    continue
                if not isinstance(choices,list) or len(choices)!=1:
                    emit('error',category='CLOUDFLARE_CHOICES_INVALID')
                    break
                choice=choices[0]
                content=choice.get('delta',{}).get('content','')
                if content is None:content=''
                if not isinstance(content,str):
                    emit('error',category='CLOUDFLARE_DELTA_INVALID')
                    break
                if content:
                    if not got_model:
                        emit('error',category='CLOUDFLARE_MODEL_NOT_ATTESTED')
                        break
                    deltas+=1;emit('delta',text=content,chunk_index=deltas)
                reason=choice.get('finish_reason')
                if reason is not None:
                    if reason!='stop':
                        emit('error',category='CLOUDFLARE_NONSTOP_FINISH_DENIED')
                        break
                    finish=True
            except (TypeError,ValueError,KeyError):
                emit('error',category='CLOUDFLARE_INVALID_SSE_JSON')
                break
        else:
            if not done:
                emit('error',category='CLOUDFLARE_NO_DONE_FRAME')
        emit('stream_diagnostic',model_attested=got_model,done_frame=done,
             finish_stop=finish,delta_count=deltas)
        if time.monotonic()>=total_deadline:
            done=False
            emit('error',category='CLOUDFLARE_STREAM_TOTAL_DEADLINE')
        if done and got_model and finish and deltas:
            emit('provider_done')
            emit('stream_end',provider_done=True,delta_count=deltas)
        else:
            emit('error',category='CLOUDFLARE_INCOMPLETE_STREAM')
except (httpx.TimeoutException,httpx.NetworkError) as exc:
    emit('error',category='CLOUDFLARE_TIMEOUT_OR_NETWORK_TRANSIENT')
except Exception as exc:
    emit('error',category='CLOUDFLARE_LOCAL_WIRE_ERROR_'+type(exc).__name__)
"""

def only_safe_event(item):
    if not isinstance(item,dict) or not isinstance(item.get("event"),str):
        raise ValueError("C1_PROVIDER_EVENT_MALFORMED")
    if item["event"] not in (
        "request_start","response_headers","model_identity","delta",
        "provider_done","stream_end","stream_diagnostic","error"):
        raise ValueError("C1_PROVIDER_EVENT_NOT_IN_WIRE_CONTRACT")
    if item["event"]=="delta" and (not isinstance(item.get("text"),str)
       or len(item["text"])>4096):
        raise ValueError("C1_PROVIDER_DELTA_BOUND")
    return item

def invoke_direct_cloudflare(prompt: str) -> Iterator[dict]:
    if not (isinstance(prompt,str) and 50<=len(prompt)<=1400):
        raise ValueError("C1_PROVIDER_PROMPT_SCOPE")
    # Production endpoint is contacted INSIDE existing disposable Nonprod
    # canary only. Source code/prompt sent, no bearer/secret over local stdout.
    args=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=7",
          VM,"docker","exec","-i",CONTAINER,"python3","-u","-"]
    # VM script and literal prompt are supplied on STDIN; no credential args.
    script=VM_STREAM_SCRIPT.replace("prompt=json.loads(sys.stdin.readline())",
      "prompt="+repr(prompt))
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        proc.stdin.write(script)
        proc.stdin.close()
        for n,line in enumerate(proc.stdout,1):
            if n>MAX_PROVIDER_EVENTS:raise ValueError("CF_EVENT_BUDGET")
            try: item=json.loads(line)
            except ValueError:raise ValueError("CF_EVENT_JSON_INVALID")
            yield only_safe_event(item)
        proc.wait(timeout=32)
        if proc.returncode:
            yield {"event":"error","category":"CF_VM_EXIT_"+str(proc.returncode)}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if proc.stderr:proc.stderr.close()

def cloudflare_first_with_minimax_backup(*,prompt, vendor,
                                        primary_fn=None, fallback_fn=None):
    """One cloud request; only a real eligible infrastructure failure may retry.

    There is NO fallback if any authenticated real Cloudflare delta is emitted.
    A developer must not force a MiniMax success by hiding bad primary text.
    """
    primary=primary_fn if primary_fn is not None else invoke_direct_cloudflare
    fallback=fallback_fn if fallback_fn is not None else vendor_generator(Path(vendor))
    emitted_cloud_text=False
    failed_reason=None
    for item in primary(prompt):
        item=only_safe_event(item)
        if item["event"]=="delta":emitted_cloud_text=True
        if item["event"]=="error":
            failed_reason=item.get("category")
            if failed_reason in FALLBACK_ELIGIBLE and not emitted_cloud_text:
                break
            yield item
            return
        yield item
    if failed_reason is None:return
    yield {"event":"failover","reason":failed_reason,"provider":"MiniMax-M3",
           "source":"ACTUAL_CLOUDFLARE_INFRASTRUCTURE_ERROR"}
    for item in fallback():
        yield only_safe_event(item)
