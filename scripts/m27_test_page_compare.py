from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SseEvent:
    event: str
    at_ms: float
    data: dict[str, Any]


def parse_sse_blocks(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data: dict[str, Any] = {}
        for raw_line in block.splitlines():
            line = raw_line.strip("\r")
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload = line.split(":", 1)[1].strip()
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = {"_unparsed": payload}
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = {"_value": parsed}
        if event_name:
            events.append({"event": event_name, "data": data})
    return events


def summarize_sse_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(events)
    event_names = [str(row.get("event", "")) for row in rows]
    first_material_index: int | None = None
    for index, row in enumerate(rows):
        event_name = str(row.get("event", ""))
        payload = row.get("data") if isinstance(row.get("data"), dict) else {}
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if (
            event_name in {"verified_claim_ready", "cited_segment_ready", "answer.completed"}
            or "answer_text" in serialized
            or "final_answer" in serialized
        ):
            first_material_index = index
            break
    final_event = event_names[-1] if event_names else None
    answer_completed = "answer.completed" in event_names
    safe_terminal = any(
        (row.get("data") or {}).get("status") in {"owner_only_safe_abstention", "safe_abstention"}
        for row in rows
        if isinstance(row.get("data"), dict)
    )
    return {
        "event_count": len(rows),
        "event_names": event_names,
        "final_event": final_event,
        "answer_completed": answer_completed,
        "safe_terminal_observed": safe_terminal,
        "first_material_event_index": first_material_index,
    }


def post_sse_probe(url: str, question: str, *, timeout_seconds: int = 95) -> dict[str, Any]:
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first_byte: float | None = None
    chunks: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = response.status
            content_type = response.headers.get("content-type", "")
            while True:
                line = response.readline()
                if not line:
                    break
                now = time.perf_counter()
                if first_byte is None and line.strip():
                    first_byte = now
                chunks.append(line.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "http_status": exc.code,
            "error_class": "HTTPError",
            "body_preview": body[:1000],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:  # pragma: no cover - operational guard
        return {
            "ok": False,
            "error_class": type(exc).__name__,
            "error": repr(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    text = "".join(chunks)
    events = parse_sse_blocks(text)
    return {
        "ok": True,
        "http_status": status,
        "content_type": content_type,
        "ttfb_ms": round(((first_byte or time.perf_counter()) - started) * 1000, 3),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "bytes": len(text.encode("utf-8")),
        "sse_summary": summarize_sse_events(events),
    }


def get_json(url: str, *, timeout_seconds: int = 5) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                parsed = {"_value": parsed}
            return {
                "ok": True,
                "http_status": response.status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "body": parsed,
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "http_status": exc.code,
            "error_class": "HTTPError",
            "body_preview": exc.read().decode("utf-8", errors="replace")[:1000],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:  # pragma: no cover - operational guard
        return {
            "ok": False,
            "error_class": type(exc).__name__,
            "error": repr(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner-only M27 vs M26 test-page-equivalent probe")
    parser.add_argument("--m26-health", default="http://127.0.0.1:8081/v1/health")
    parser.add_argument("--m26-answers", default="http://127.0.0.1:8081/v1/answers")
    parser.add_argument("--m27-health", default="http://127.0.0.1:18080/v1/health")
    parser.add_argument("--m27-stream", default="http://127.0.0.1:18080/v1/answers/stream")
    parser.add_argument("--question", default="What is safe?")
    parser.add_argument("--skip-answer-probes", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "schema_version": "m27-test-page-compare/v1",
        "scope": "owner_only_local_test_page_equivalent",
        "production_public_routing_mutated": False,
        "m26_health": get_json(args.m26_health),
        "m27_health": get_json(args.m27_health),
    }
    if not args.skip_answer_probes:
        result["m26_answer_probe"] = post_sse_probe(args.m26_answers, args.question)
        result["m27_stream_probe"] = post_sse_probe(args.m27_stream, args.question, timeout_seconds=10)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
