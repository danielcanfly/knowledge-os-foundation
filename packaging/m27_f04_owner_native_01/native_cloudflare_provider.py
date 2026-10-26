"""Image-native direct Cloudflare Workers AI transport for frozen C1 parity."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import socket
import stat
from urllib.error import HTTPError, URLError

import m27_c1_formal_workers_ai_sse as wire

MODEL = wire.MODEL
ROUTE = "M26_DIRECT_WORKERS_AI_OWNER_CANARY_NONPROD"


class Denied(ValueError):
    pass


def private_bytes(path: Path, *, max_size: int = 2048) -> bytes:
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or
                stat.S_IMODE(st.st_mode) != 0o600 or
                not 0 < st.st_size <= max_size):
            raise Denied("CLOUDFLARE_PRIVATE_FILE_OWNER_MODE")
        raw = os.read(fd, max_size + 1)
        if len(raw) != st.st_size:
            raise Denied("CLOUDFLARE_PRIVATE_FILE_READ_DRIFT")
        return raw
    finally:
        os.close(fd)


def account_id(path: Path) -> str:
    raw = private_bytes(path, max_size=128)
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise Denied("CLOUDFLARE_ACCOUNT_ID_INVALID") from exc
    if re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", value) is None:
        raise Denied("CLOUDFLARE_ACCOUNT_ID_INVALID")
    return value


def _http_category(error: HTTPError) -> str:
    status = error.code
    body = error.read(8192) if status in (400, 401, 403, 408, 429, 500, 502, 503, 504) else b""
    if status == 429 and b"3036" in body:
        return "CLOUDFLARE_DAILY_QUOTA_EXHAUSTED_3036"
    if status == 429 and b"3040" in body:
        return "CLOUDFLARE_TRANSIENT_CAPACITY_3040"
    if status == 403 and b"5035" in body:
        return "CLOUDFLARE_PAID_PLAN_ONLY_5035"
    if status in (401, 403, 404):
        return "CLOUDFLARE_AUTH_OR_CONFIG"
    if status == 429:
        return "CLOUDFLARE_RATE_LIMIT_OR_CAPACITY_429"
    return "CLOUDFLARE_HTTP_" + str(status)


def stream(*, account_file: Path, token_file: Path, prompt: str):
    """Yield frozen C1 provider events without exposing account/token bytes."""
    account = account_id(account_file)
    request_id = hashlib.sha256(("cloudflare-native:" + prompt).encode()).hexdigest()[:48]
    task_sha = hashlib.sha256(prompt.encode()).hexdigest()
    audits: list[dict] = []
    codec = wire.DirectWorkersAISSE(
        url=("https://api.cloudflare.com/client/v4/accounts/" + account +
             "/ai/v1/chat/completions"),
        model=MODEL,
        token_path=Path(token_file),
        private_file=private_bytes,
        max_wall_seconds=30,
        audit=audits.append,
    )
    yield {"event": "request_start", "model": MODEL, "route": ROUTE,
           "stream_requested": True, "max_tokens": 192,
           "in_container_https": True}
    identity = False
    deltas = 0
    done = False
    try:
        for _, event in codec.one_bounded_stream(
                prompt=prompt, task_sha=task_sha,
                request_id=request_id, max_tokens=192):
            if event["kind"] == "delta":
                if not identity:
                    yield {"event": "model_identity", "model": MODEL,
                           "model_match": True}
                    identity = True
                deltas += 1
                yield {"event": "delta", "text": event["text"],
                       "chunk_index": deltas}
            elif event["kind"] == "done":
                done = True
        yield {"event": "stream_diagnostic", "model_attested": identity,
               "done_frame": done, "finish_stop": done,
               "delta_count": deltas, "wire_audit_records": len(audits)}
        if done and identity and deltas:
            yield {"event": "provider_done"}
            yield {"event": "stream_end", "provider_done": True,
                   "delta_count": deltas}
        else:
            yield {"event": "error", "category": "CLOUDFLARE_INCOMPLETE_STREAM"}
    except HTTPError as exc:
        yield {"event": "response_headers", "status": exc.code}
        yield {"event": "error", "category": _http_category(exc)}
    except (URLError, socket.timeout, TimeoutError):
        yield {"event": "error",
               "category": "CLOUDFLARE_TIMEOUT_OR_NETWORK_TRANSIENT"}
    except wire.WireRejected as exc:
        category = ("CLOUDFLARE_TIMEOUT_OR_NETWORK_TRANSIENT"
                    if "DEADLINE" in str(exc)
                    else "CLOUDFLARE_STREAM_PROTOCOL_MISMATCH")
        yield {"event": "error", "category": category}

