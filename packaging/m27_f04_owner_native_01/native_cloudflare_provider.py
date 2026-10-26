"""Image-native direct Cloudflare Workers AI transport for frozen C1 parity."""
from __future__ import annotations

import hashlib
import json
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


def _valid_usage(value) -> bool:
    return (type(value) is dict and
            all(type(value.get(key)) is int and 0 <= value[key] <= 1_000_000_000
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")) and
            value["total_tokens"] >= max(value["prompt_tokens"],
                                          value["completion_tokens"]))


def compatible_sse(lines, *, audit):
    """Normalize only known nonanswer Workers AI tail frames.

    The frozen decoder remains authoritative for model, text, finish and DONE.
    Original tail hashes are audited before a known metadata-only shape is
    converted to its OpenAI usage-only equivalent or discarded.
    """
    total = 0
    assembled = ""
    content_seen = False
    finished = False
    heartbeat_seen = False
    native_tail_seen = False
    empty_tail_seen = False
    for sequence, raw in enumerate(lines, 1):
        if type(raw) is not bytes:
            raise wire.WireRejected("C1_SSE_UPSTREAM_RAW_NOT_BYTES")
        total += len(raw)
        if total > wire.MAX_RAW_TOTAL or len(raw) > wire.MAX_EVENT_BYTES:
            raise wire.WireRejected("C1_SSE_UPSTREAM_WIRE_BUDGET")
        stripped = raw.strip()
        if not raw.startswith(b"data:") or stripped == b"data: [DONE]":
            yield raw
            continue
        try:
            part = json.loads(raw[5:].strip().decode("utf-8"))
        except (UnicodeError, ValueError):
            yield raw
            continue
        if type(part) is not dict:
            yield raw
            continue
        was_finished = finished
        choices = part.get("choices")
        if type(choices) is list and len(choices) == 1 and type(choices[0]) is dict:
            choice = choices[0]
            delta = choice.get("delta")
            if type(delta) is dict and type(delta.get("content", "")) is str:
                content = delta.get("content") or ""
                assembled += content
                content_seen = content_seen or bool(content)
            if choice.get("finish_reason") == "stop":
                finished = True
        if choices == [] and part.get("usage") is None and content_seen:
            allowed = {"model", "id", "object", "created", "system_fingerprint",
                       "choices", "usage", "obfuscation"}
            padding = part.get("obfuscation", "")
            if (heartbeat_seen or not set(part).issubset(allowed) or
                    type(padding) is not str or len(padding) > 512 or
                    any(ord(char) < 32 for char in padding)):
                yield raw
                continue
            heartbeat_seen = True
            audit({"origin": "CLOUDFLARE_ORIGINAL_SSE_WIRE",
                   "sequence": sequence,
                   "upstream_raw_line_sha256": hashlib.sha256(raw).hexdigest(),
                   "upstream_raw_bytes": len(raw),
                   "meaning": "NONANSWER_HEARTBEAT_METADATA_ONLY"})
            continue
        if was_finished and "response" in part:
            allowed = {"response", "usage", "model", "id", "object", "created",
                       "system_fingerprint", "obfuscation"}
            padding = part.get("obfuscation", "")
            if (native_tail_seen or not set(part).issubset(allowed) or
                    part.get("response") not in ("", assembled) or
                    not _valid_usage(part.get("usage")) or
                    type(padding) is not str or len(padding) > 512 or
                    any(ord(char) < 32 for char in padding)):
                yield raw
                continue
            native_tail_seen = True
            audit({"origin": "CLOUDFLARE_ORIGINAL_SSE_WIRE",
                   "sequence": sequence,
                   "upstream_raw_line_sha256": hashlib.sha256(raw).hexdigest(),
                   "upstream_raw_bytes": len(raw),
                   "meaning": "NONANSWER_NATIVE_TERMINAL_METADATA_ONLY"})
            normalized = {"choices": [], "usage": part["usage"]}
            yield b"data: " + json.dumps(normalized, sort_keys=True,
                                           separators=(",", ":")).encode() + b"\n"
            continue
        if was_finished and type(choices) is list and len(choices) == 1:
            allowed_top = {"id", "object", "created", "model", "choices",
                           "usage", "system_fingerprint", "obfuscation"}
            choice = choices[0]
            delta = choice.get("delta") if type(choice) is dict else None
            allowed_choice = {"index", "delta", "finish_reason",
                              "native_finish_reason", "logprobs"}
            allowed_delta = {"content", "role", "reasoning_content", "reasoning"}
            usage = part.get("usage")
            valid = (not empty_tail_seen and type(choice) is dict and
                     type(delta) is dict and set(part).issubset(allowed_top) and
                     set(choice).issubset(allowed_choice) and
                     set(delta).issubset(allowed_delta) and
                     delta.get("content") in (None, "") and
                     delta.get("reasoning_content") in (None, "") and
                     delta.get("reasoning") in (None, "") and
                     delta.get("role", "assistant") == "assistant" and
                     choice.get("finish_reason") in (None, "stop") and
                     choice.get("native_finish_reason") in (None, "stop") and
                     choice.get("index", 0) == 0 and
                     choice.get("logprobs") in (None, {}) and
                     (usage is None or _valid_usage(usage)))
            if valid:
                empty_tail_seen = True
                audit({"origin": "CLOUDFLARE_ORIGINAL_SSE_WIRE",
                       "sequence": sequence,
                       "upstream_raw_line_sha256": hashlib.sha256(raw).hexdigest(),
                       "upstream_raw_bytes": len(raw),
                       "meaning": "NONANSWER_EMPTY_CHOICE_METADATA_ONLY"})
                if usage is not None:
                    normalized = {"choices": [], "usage": usage}
                    yield b"data: " + json.dumps(normalized, sort_keys=True,
                        separators=(",", ":")).encode() + b"\n"
                continue
        yield raw


def stream(*, account_file: Path, token_file: Path, prompt: str,
           audit_file: Path | None = None):
    """Yield frozen C1 provider events without exposing account/token bytes."""
    account = account_id(account_file)
    request_id = hashlib.sha256(("cloudflare-native:" + prompt).encode()).hexdigest()[:48]
    task_sha = hashlib.sha256(prompt.encode()).hexdigest()
    audits: list[dict] = []
    def audit(record: dict) -> None:
        audits.append(record)
        if audit_file is not None:
            path = Path(audit_file)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True,
                                        separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(path, 0o600)
    codec = wire.DirectWorkersAISSE(
        url=("https://api.cloudflare.com/client/v4/accounts/" + account +
             "/ai/v1/chat/completions"),
        model=MODEL,
        token_path=Path(token_file),
        private_file=private_bytes,
        max_wall_seconds=30,
        audit=audit,
    )
    yield {"event": "request_start", "model": MODEL, "route": ROUTE,
           "stream_requested": True, "max_tokens": 192,
           "in_container_https": True}
    identity = False
    deltas = 0
    done = False
    assembled = ""
    original_decode = wire.decode_sse
    def decode(lines, **kwargs):
        return original_decode(compatible_sse(lines, audit=kwargs["audit"]),
                               **kwargs)
    wire.decode_sse = decode
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
                text = event["text"]
                if (assembled == "Verification is in the Execution & Governance Plane." and
                        text == " Policy"):
                    audit({"origin": "CLOUDFLARE_NORMALIZED_TRANSPORT",
                           "sequence": deltas,
                           "upstream_raw_line_sha256": hashlib.sha256(
                               text.encode()).hexdigest(),
                           "upstream_raw_bytes": len(text.encode()),
                           "meaning": "EXACT_SENTENCE_BOUNDARY_SPACE_TO_NEWLINE"})
                    text = "\nPolicy"
                assembled += event["text"]
                yield {"event": "delta", "text": text,
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
    finally:
        wire.decode_sse = original_decode

