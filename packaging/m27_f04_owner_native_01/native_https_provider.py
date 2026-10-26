"""Actual in-process HTTPS MiniMax SSE for one Owner Nonprod native image.

Distinct from frozen C1's legacy SSH/canary transport. No fixture, replay,
cross-container provider adapter, test signature, or external authority.
"""
from __future__ import annotations
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import time

MODEL="MiniMax-M3"
HOST="api.minimax.io"
PATH="/anthropic/v1/messages"
MAX_TOKENS=128
MAX_DELTAS=350
MAX_BYTES=180_000

class Denied(ValueError): pass
def require(ok,reason):
    if not ok:raise Denied(reason)

def secret(path:Path)->bytes:
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        st=os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid()
                and (st.st_mode & 0o077)==0 and 20<=st.st_size<=512,
                "PROVIDER_SECRET_OWNER_MODE_OR_LENGTH_DENIED")
        key=os.read(fd,513).strip()
        require(20<=len(key)<=512 and re.fullmatch(rb"[A-Za-z0-9_+./=-]+",key) is not None,
                "PROVIDER_SECRET_BYTES_INVALID")
        return key
    finally:os.close(fd)

def stream(*,provider_secret:Path,prompt:str):
    require(type(prompt) is str and 200<=len(prompt)<=3500,
            "PROMPT_NOT_AUTHORIZED")
    key=secret(provider_secret)
    payload={"model":MODEL,"stream":True,"max_tokens":MAX_TOKENS,
             "temperature":0,
             "system":"Produce only short factual claims entailed by two approved first-party A05 excerpts.",
             "messages":[{"role":"user","content":prompt}]}
    connection=http.client.HTTPSConnection(HOST,timeout=26)
    start=time.monotonic()
    count=0;received=0;verified=False;done=False;errored=False
    try:
        # Real HTTPS request executes from this app's own Linux container.
        # Secret is request auth only; never logged or returned as evidence.
        connection.request("POST",PATH,body=json.dumps(payload).encode(),
                           headers={"Authorization":"Bearer "+key.decode("ascii"),
                           "Content-Type":"application/json","Accept":"text/event-stream"})
        yield {"event":"request_start","model":MODEL,
               "route":"VM_OWNER_CANARY_NONPROD","in_container_https":True,
               "max_tokens":MAX_TOKENS}
        response=connection.getresponse()
        yield {"event":"response_headers","status":response.status}
        if response.status!=200:
            yield {"event":"error","category":"HTTP_"+str(response.status)}
            return
        for raw in response:
            if time.monotonic()-start>29:
                raise Denied("ONE_TASK_PROVIDER_TIME_BUDGET")
            received+=len(raw)
            if received>MAX_BYTES:raise Denied("PROVIDER_SSE_BYTE_BUDGET")
            if not raw.startswith(b"data:"):continue
            try:packet=json.loads(raw[5:].strip())
            except (ValueError,UnicodeError):
                raise Denied("INVALID_PROVIDER_SSE_JSON")
            require(type(packet) is dict,"INVALID_PROVIDER_SSE_TYPE")
            kind=packet.get("type")
            if kind=="message_start":
                actual=(packet.get("message") or {}).get("model")
                verified=(actual==MODEL)
                yield {"event":"model_identity","model":actual,"model_match":verified}
                require(verified,"MODEL_ORIGIN_NOT_ATTESTED")
            elif kind=="content_block_delta":
                delta=packet.get("delta") or {}
                txt=delta.get("text","") if delta.get("type")=="text_delta" else ""
                if txt:
                    require(verified and type(txt) is str and len(txt)<=4096,
                            "DELTA_WITHOUT_MODEL_IDENTITY")
                    count+=1
                    require(count<=MAX_DELTAS,"DELTA_BUDGET")
                    yield {"event":"delta","text":txt,"chunk_index":count}
            elif kind=="error":
                errored=True
                yield {"event":"error","category":"PROVIDER_SSE_ERROR"}
                return
            elif kind=="message_stop":
                require(verified,"DONE_WITHOUT_MODEL_PROOF")
                done=True
                yield {"event":"provider_done"}
                break
        yield {"event":"stream_end","provider_done":bool(done and verified and not errored),"delta_count":count}
    except (OSError,TimeoutError,Denied,http.client.HTTPException) as exc:
        # No unknown-effect retry, no arbitrary exception text.
        kind=exc.args[0] if isinstance(exc,Denied) else type(exc).__name__
        yield {"event":"error","category":str(kind)[:55]}
    finally:
        connection.close()
