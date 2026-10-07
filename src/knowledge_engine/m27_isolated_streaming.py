from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

M27_ISOLATED_STREAM_SCHEMA = "m27-isolated-first-answer-stream/v1"
M27_ISOLATED_STREAM_PATH = "/v1/answers/stream"
M27_STREAM_QUEUE_MAX = 128


def sse_frame(event_type: str, payload: Mapping[str, Any]) -> str:
    body = {
        "schema_version": M27_ISOLATED_STREAM_SCHEMA,
        "event": event_type,
        **dict(payload),
    }
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(body, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def runtime_progress_event(
    event: Mapping[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    event_type = str(event.get("type", ""))
    stage = str(event.get("stage", ""))
    live_material_events = {
        "evidence_ready",
        "answer_plan_ready",
        "claim_graph_ready",
        "claim_verification_started",
        "verified_claim_ready",
        "citation_bound",
        "cited_segment_ready",
        "stream_publishable",
        "final_answer_done",
        "verifier_gap_detected",
        "verifier_gap_repair_started",
        "verifier_gap_repair_done",
    }
    if event_type in live_material_events:
        payload = {
            str(key): value
            for key, value in dict(event).items()
            if key not in {"type", "raw_provider_key", "owner_bypass", "secret"}
        }
        return event_type, payload
    if event_type == "safe_terminal_done":
        payload = {
            str(key): value
            for key, value in dict(event).items()
            if key not in {"type", "raw_provider_key", "owner_bypass", "secret"}
        }
        payload.setdefault("status", "owner_only_safe_abstention")
        return "safe_abstention_done", payload
    if event_type == "product.event":
        product_event = str(event.get("event", "")).strip()
        if product_event:
            return product_event, {
                key: value for key, value in event.items()
                if key not in {"type", "event", "raw_provider_key", "owner_bypass", "secret"}
            }
    if event_type == "stage.started" and stage:
        return f"{stage}_started", {"stage": stage}
    if event_type == "stage.completed" and stage:
        payload: dict[str, Any] = {"stage": stage}
        if "selected_evidence_count" in event:
            payload["selected_evidence_count"] = int(
                event.get("selected_evidence_count", 0) or 0
            )
        if "latency_ms" in event:
            payload["latency_ms"] = int(event.get("latency_ms", 0) or 0)
        return f"{stage}_ready", payload
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def m27_stream_response_from_result(result: Any) -> dict[str, Any]:
    """Normalize an isolated M27 runtime result into a streamable final DTO.

    This is intentionally a publication adapter only. It does not execute or
    alter the authoritative runtime; it exposes verified material already present
    in the result and fails safe when the result is terminal-safe.
    """

    if hasattr(result, "status_code"):
        status_code = str(result.status_code)
        answer = _mapping(getattr(result, "answer", None))
        verification = _mapping(getattr(result, "verification", None))
        terminal_reason = str(getattr(result, "terminal_reason", ""))
        production_touched = bool(getattr(result, "production_touched", False))
    elif isinstance(result, Mapping):
        if result.get("schema_version") == M27_ISOLATED_STREAM_SCHEMA:
            return dict(result)
        status_code = str(result.get("status_code", result.get("status", "")))
        answer = _mapping(result.get("answer", result))
        verification = _mapping(result.get("verification", result))
        terminal_reason = str(result.get("terminal_reason", ""))
        production_touched = bool(result.get("production_touched", False))
    else:
        status_code = "M27_RUNTIME_SAFE_TERMINAL"
        answer = {}
        verification = {}
        terminal_reason = "INVALID_RUNTIME_RESULT"
        production_touched = False

    safe_abstention = status_code != "M27_RUNTIME_COMPOSED"
    citations = _mapping_list(answer.get("citations")) or _mapping_list(
        verification.get("citations")
    )
    claims = _mapping_list(answer.get("answer_claims")) or _mapping_list(
        verification.get("answer_claims")
    )
    answer_text = str(answer.get("answer_text", "") or "")
    material_support = bool(
        answer.get(
            "material_claim_support_verified",
            verification.get("material_claim_support_verified", False),
        )
    )
    locator_valid = bool(
        answer.get("citation_locator_valid", verification.get("citation_locator_valid", False))
    )
    unsupported = int(
        answer.get(
            "unsupported_accepted_claims",
            verification.get("unsupported_accepted_claims", 1),
        )
        or 0
    )
    micro_timeline = _mapping(answer.get("micro_timeline")) or _mapping(verification.get("micro_timeline"))
    answer_plan = _mapping(answer.get("answer_plan")) or _mapping(verification.get("answer_plan"))
    claim_graph = _mapping_list(answer.get("claim_graph")) or _mapping_list(verification.get("claim_graph"))
    gap_taxonomy = list(answer.get("gap_taxonomy", verification.get("gap_taxonomy", [])) or [])
    return {
        "schema_version": M27_ISOLATED_STREAM_SCHEMA,
        "status": (
            "owner_only_cited_answer"
            if not safe_abstention
            else "owner_only_safe_abstention"
        ),
        "status_code": status_code,
        "terminal_status": "answered" if not safe_abstention else "safe_abstention",
        "terminal_reason": terminal_reason,
        "answer_text": answer_text if not safe_abstention else "",
        "safe_abstention": safe_abstention,
        "citations": citations if not safe_abstention else [],
        "answer_claims": claims if not safe_abstention else [],
        "integrity": {
            "unsupported_accepted_claims": unsupported,
            "material_claim_support_verified": material_support,
            "citation_locator_valid": locator_valid,
        },
        "production_touched": production_touched,
        "answer_plan": answer_plan,
        "claim_graph": claim_graph,
        "gap_taxonomy": gap_taxonomy,
        "micro_timeline": micro_timeline,
        "response": dict(answer) if answer else {},
    }


def m27_verified_material_events(
    dto: Mapping[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    if bool(dto.get("safe_abstention", True)) or dto.get("status") != "owner_only_cited_answer":
        return [("safe_abstention_done", {"response": dict(dto)})]

    integrity = _mapping(dto.get("integrity"))
    citation_rows = _mapping_list(dto.get("citations"))
    answer_text = str(dto.get("answer_text", "")).strip()
    if (
        int(integrity.get("unsupported_accepted_claims", 1) or 0) != 0
        or integrity.get("material_claim_support_verified") is not True
        or integrity.get("citation_locator_valid") is not True
        or not citation_rows
        or not answer_text
        or dto.get("production_touched") is True
    ):
        return [
            (
                "error",
                {
                    "code": "M27_ISOLATED_STREAM_FINAL_NOT_STREAMABLE",
                    "message": (
                        "authoritative final state did not satisfy "
                        "verified streaming invariants"
                    ),
                },
            )
        ]

    citations_by_claim: dict[str, list[dict[str, Any]]] = {}
    for citation in citation_rows:
        claim_id = str(citation.get("claim_id", "")).strip()
        if claim_id:
            citations_by_claim.setdefault(claim_id, []).append(citation)

    events: list[tuple[str, dict[str, Any]]] = []
    for claim in _mapping_list(dto.get("answer_claims")):
        claim_id = str(claim.get("claim_id", "")).strip()
        surface_text = str(claim.get("surface_text", "")).strip()
        claim_citations = citations_by_claim.get(claim_id, [])
        if claim_id and surface_text and claim_citations:
            events.append(
                (
                    "verified_claim_ready",
                    {
                        "claim_id": claim_id,
                        "text": surface_text,
                        "citations": claim_citations,
                    },
                )
            )

    events.append(
        (
            "cited_segment_ready",
            {"text": answer_text, "citations": citation_rows},
        )
    )
    events.append(("final_answer_done", {"response": dict(dto)}))
    return events


async def m27_isolated_event_stream(
    *,
    request: Any,
    request_payload: Mapping[str, Any],
    run_execution: Callable[..., Any],
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue(maxsize=M27_STREAM_QUEUE_MAX)
    disconnected = threading.Event()
    live_material_seen = False
    question_sha256 = str(request_payload.get("question_sha256", ""))

    def enqueue_runtime_event(event: Mapping[str, Any]) -> None:
        if disconnected.is_set():
            return

        def enqueue() -> None:
            if disconnected.is_set():
                return
            try:
                event_queue.put_nowait(dict(event))
            except asyncio.QueueFull:
                return

        loop.call_soon_threadsafe(enqueue)

    yield sse_frame(
        "request_started",
        {
            "question_sha256": question_sha256,
            "authoritative_runtime": "m27-isolated-runtime",
            "isolated_runtime": True,
            "production_touched": False,
        },
    )

    worker = asyncio.create_task(
        asyncio.to_thread(
            run_execution,
            request_payload=dict(request_payload),
            event_sink=enqueue_runtime_event,
        )
    )

    try:
        while True:
            if await request.is_disconnected():
                disconnected.set()
                worker.cancel()
                return
            while True:
                try:
                    runtime_event = event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                mapped = runtime_progress_event(runtime_event)
                if mapped is not None:
                    if mapped[0] in {"verified_claim_ready", "cited_segment_ready"}:
                        live_material_seen = True
                    yield sse_frame(mapped[0], mapped[1])
            if worker.done():
                break
            await asyncio.sleep(0.01)

        dto = m27_stream_response_from_result(await worker)
        while True:
            try:
                runtime_event = event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            mapped = runtime_progress_event(runtime_event)
            if mapped is not None:
                if mapped[0] in {"verified_claim_ready", "cited_segment_ready"}:
                    live_material_seen = True
                if mapped[0] != "final_answer_done":
                    yield sse_frame(mapped[0], mapped[1])

        for event_type, payload in m27_verified_material_events(dto):
            if live_material_seen and event_type in {"verified_claim_ready", "cited_segment_ready"}:
                continue
            if event_type == "final_answer_done" and "response" in payload:
                response = _mapping(payload.get("response"))
                if response.get("answer_text") and "answer" not in payload:
                    payload = {**payload, "answer": response.get("answer_text"), "text": response.get("answer_text")}
            yield sse_frame(event_type, payload)
    except asyncio.CancelledError:
        disconnected.set()
        worker.cancel()
        raise
    except Exception as exc:
        code = str(getattr(exc, "reason_code", "") or "M27_ISOLATED_STREAM_RUNTIME_FAILED")
        yield sse_frame("error", {"code": code})
    finally:
        disconnected.set()


__all__ = [
    "M27_ISOLATED_STREAM_PATH",
    "M27_ISOLATED_STREAM_SCHEMA",
    "M27_STREAM_QUEUE_MAX",
    "m27_isolated_event_stream",
    "m27_stream_response_from_result",
    "m27_verified_material_events",
    "runtime_progress_event",
    "sse_frame",
]
