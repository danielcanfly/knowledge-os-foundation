"""Formal C1 M26-direct Workers AI SSE codec, gated by upstream signed grant.

A successful decoder result is NOT signer admission. Only the formal caller's
independently pinned Provider Controller can enable this specific wire ABI.
Returns clearly NORMALIZED C1 events, not forged original Cloudflare NDJSON;
raw upstream SSE SHA256 is separately included in audit callback metadata.
No own credentials or signature issuance. No fallback once stream begins.
"""
from __future__ import annotations
import hashlib
import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, HTTPSHandler, HTTPRedirectHandler, build_opener
from typing import Callable, Iterable, Iterator

ABI="m27.c1.provider-workers-ai-sse/v1"
MODEL="@cf/openai/gpt-oss-120b"
MAX_RAW_TOTAL=131072
MAX_EVENTS=128
MAX_EVENT_BYTES=32768
MAX_DELTA_CHARS=1024

class WireRejected(ValueError):pass

def require(ok:bool, why:str):
    if not ok:raise WireRejected(why)

def approved_direct_url(url:str)->bool:
    if not isinstance(url,str):return False
    parsed=urlsplit(url)
    return (parsed.scheme=="https" and
       parsed.hostname=="api.cloudflare.com" and
       parsed.port in (None,443) and
       parsed.username is None and parsed.password is None and
       not parsed.query and not parsed.fragment and
       re.fullmatch(r"/client/v4/accounts/[a-z0-9_-]{8,100}/ai/v1/chat/completions",
                    parsed.path,re.I) is not None)

def canonical(obj:dict)->bytes:
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode("utf-8")

def normalized(kind:str, text:str, model:str, request_id:str):
    event={"kind":kind,"text":text,"model":model,"request_id":request_id}
    return canonical(event),event

def decode_sse(lines:Iterable[bytes], *,
               model:str, request_id:str, audit:Callable[[dict],None]):
    """Strict Cloudflare-compatible OpenAI SSE parser without issuer powers.

    Vendor SSE events are never disguised as raw normalized NDJSON: upstream
    wire digest is preserved in a separate record and normalized bytes
    are only internal transport to already-gated GeneratedSession.
    """
    require(model==MODEL and 3<=len(request_id)<=180,
            "C1_SSE_APPROVED_MODEL_OR_TASK_MISSING")
    total=0;events=0;deltas=0
    attested=False;finished=False;done=False
    for raw in lines:
        require(type(raw) is bytes,"C1_SSE_UPSTREAM_RAW_NOT_BYTES")
        total+=len(raw)
        require(total<=MAX_RAW_TOTAL,"C1_SSE_UPSTREAM_TOTAL_BUDGET")
        if not raw.startswith(b"data:"):continue
        events+=1
        require(events<=MAX_EVENTS and len(raw)<=MAX_EVENT_BYTES,
                "C1_SSE_UPSTREAM_FRAME_BUDGET")
        data=raw[5:].strip()
        upstream_sha=hashlib.sha256(raw).hexdigest()
        if data==b"[DONE]":
            require(not done and finished and attested and deltas>0,
                    "C1_SSE_EARLY_OR_DUPLICATE_DONE")
            audit({"origin":"CLOUDFLARE_ORIGINAL_SSE_WIRE","sequence":events,
                   "upstream_raw_line_sha256":upstream_sha,
                   "upstream_raw_bytes":len(raw),
                   "meaning":"REAL_PROVIDER_DONE_FRAME"})
            done=True
            yield normalized("done","",model,request_id)
            break
        require(not finished and not done, "C1_SSE_FRAME_AFTER_FINISH")
        try: part=json.loads(data.decode("utf-8"))
        except (UnicodeError,ValueError) as ex:
            raise WireRejected("C1_SSE_INVALID_JSON") from ex
        require(type(part) is dict,"C1_SSE_NOT_AN_OBJECT")
        upstream_model=part.get("model")
        if upstream_model is not None:
            require(upstream_model in (MODEL,"gpt-oss-120b"),
                    "C1_SSE_PROVIDER_MODEL_MISMATCH")
            attested=True
        choices=part.get("choices")
        require(type(choices) is list and len(choices)==1 and
                type(choices[0]) is dict, "C1_SSE_CHOICES_INVALID")
        choice=choices[0]
        delta=choice.get("delta")
        require(type(delta) is dict,"C1_SSE_DELTA_NOT_OBJECT")
        content=delta.get("content","")
        if content is None:content=""
        require(type(content) is str,"C1_SSE_TEXT_INVALID")
        if content:
            require(attested and not finished and len(content)<=MAX_DELTA_CHARS,
                    "C1_SSE_TEXT_MODEL_UNATTESTED_OR_OVERSIZED")
            deltas+=1
            audit({"origin":"CLOUDFLARE_ORIGINAL_SSE_WIRE",
                   "sequence":events,
                   "upstream_raw_line_sha256":upstream_sha,
                   "upstream_raw_bytes":len(raw),
                   "normalized_delta_sha256":hashlib.sha256(content.encode()).hexdigest(),
                   "meaning":"LIVE_NEW_PROVIDER_DELTA"})
            yield normalized("delta",content,model,request_id)
        reason=choice.get("finish_reason")
        if reason is not None:
            require(reason=="stop" and not finished,
                    "C1_SSE_NONSTOP_OR_DUPLICATE_FINISH")
            finished=True
            audit({"origin":"CLOUDFLARE_ORIGINAL_SSE_WIRE",
                   "sequence":events,
                   "upstream_raw_line_sha256":upstream_sha,
                   "upstream_raw_bytes":len(raw),
                   "meaning":"REAL_PROVIDER_FINISH_STOP"})
    require(done and attested and finished and deltas>0,
            "C1_SSE_INCOMPLETE_OR_NO_TEXT")

class DirectWorkersAISSE:
    def __init__(self, *,url:str,model:str, token_path,
                 private_file:Callable, max_wall_seconds:int=30,
                 audit:Callable[[dict],None]|None=None):
        require(approved_direct_url(url),"C1_SSE_DIRECT_CLOUDFLARE_ROUTE_DENIED")
        require(model==MODEL,"C1_SSE_SIGNED_PROVIDER_MODEL_DENIED")
        self.url,self.model=url,model
        self.token_path=token_path
        self.private_file=private_file
        self.max_wall_seconds=max_wall_seconds
        self.audit=audit or (lambda record:None)

    def one_bounded_stream(self,*,prompt:str,task_sha:str,
                           request_id:str,max_tokens:int):
        require(isinstance(prompt,str) and len(prompt)<=1500 and
                isinstance(task_sha,str) and re.fullmatch(r"[0-9a-f]{64}",task_sha)
                and isinstance(request_id,str) and request_id
                and type(max_tokens) is int and 1<=max_tokens<=192,
                "C1_SSE_TASK_OR_TOKEN_BUDGET_INVALID")
        token=self.private_file(self.token_path,max_size=2048)
        require(b"\n" not in token and b"\r" not in token,
                "C1_SSE_CREDENTIAL_INVALID")
        body=canonical({"model":self.model,
          "messages":[
            {"role":"system","content":"Answer only the grounded task without unsupported claims."},
            {"role":"user","content":prompt}],
          "stream":True,"max_tokens":max_tokens,
          "temperature":0,"reasoning_effort":"low"})
        req=Request(self.url,data=body,method="POST",headers={
          "Authorization":"Bearer "+token.decode("ascii"),
          "Content-Type":"application/json",
          "Accept":"text/event-stream"})
        class NeverRedirect(HTTPRedirectHandler):
            def redirect_request(self,*a,**kw):
                raise WireRejected("C1_SSE_REDIRECT_DENIED")
        opener=build_opener(ProxyHandler({}),HTTPSHandler(),NeverRedirect())
        try:
            with opener.open(req,timeout=self.max_wall_seconds) as stream:
                require(stream.status==200 and
                        stream.headers.get("Content-Type","").lower().startswith("text/event-stream"),
                        "C1_SSE_HTTP_OR_CONTENT_TYPE_DENIED")
                yield from decode_sse(stream,model=self.model,request_id=request_id,
                                      audit=self.audit)
        finally:
            token=b""  # only local process has ever read token, no logs/argv
