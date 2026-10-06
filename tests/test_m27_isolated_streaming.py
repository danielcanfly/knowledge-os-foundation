from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi.testclient import TestClient

from knowledge_engine.m27_isolated_http import app
from knowledge_engine.m27_isolated_streaming import (
    M27_ISOLATED_STREAM_PATH,
    M27_STREAM_QUEUE_MAX,
    m27_isolated_event_stream,
    m27_verified_material_events,
)


class _NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectAfterFirstPoll:
    def __init__(self) -> None:
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls >= 2


def _dto(*, safe: bool = False, verified: bool = True) -> dict[str, Any]:
    if safe:
        return {
            "schema_version": "m27-isolated-first-answer-stream/v1",
            "status": "owner_only_safe_abstention",
            "status_code": "M27_RUNTIME_SAFE_TERMINAL",
            "terminal_status": "safe_abstention",
            "terminal_reason": "VERIFIER_GAP_SAFE_TERMINAL",
            "answer_text": "",
            "safe_abstention": True,
            "citations": [],
            "answer_claims": [],
            "integrity": {
                "unsupported_accepted_claims": 0,
                "material_claim_support_verified": False,
                "citation_locator_valid": False,
            },
            "production_touched": False,
        }
    return {
        "schema_version": "m27-isolated-first-answer-stream/v1",
        "status": "owner_only_cited_answer",
        "status_code": "M27_RUNTIME_COMPOSED",
        "terminal_status": "answered",
        "terminal_reason": "VERIFIED_CITED_ANSWER",
        "answer_text": "Graphology keeps and analyzes graph data.",
        "safe_abstention": False,
        "citations": [
            {
                "citation_id": "c1",
                "claim_id": "claim_1",
                "locator_id": "loc_1",
                "source_identity": "source_1",
            }
        ],
        "answer_claims": [
            {
                "claim_id": "claim_1",
                "surface_text": "Graphology keeps and analyzes graph data.",
                "citation_ids": ["c1"],
            }
        ],
        "integrity": {
            "unsupported_accepted_claims": 0 if verified else 1,
            "material_claim_support_verified": verified,
            "citation_locator_valid": verified,
        },
        "production_touched": False,
    }


def _parse_frame(frame: str) -> tuple[str, dict[str, Any]]:
    lines = [line for line in frame.splitlines() if line]
    event = lines[0].split(": ", 1)[1]
    payload = json.loads(lines[1].split(": ", 1)[1])
    return event, payload


def _parse_text(text: str) -> list[tuple[str, dict[str, Any]]]:
    return [_parse_frame(frame) for frame in text.strip().split("\n\n") if frame.strip()]


def test_isolated_stream_preserves_final_parity_and_orders_material_before_final() -> None:
    async def scenario() -> None:
        calls = 0

        def run_execution(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            sink = kwargs["event_sink"]
            sink({"type": "stage.started", "stage": "retrieval"})
            sink(
                {
                    "type": "stage.completed",
                    "stage": "retrieval",
                    "selected_evidence_count": 1,
                    "latency_ms": 2,
                }
            )
            return _dto()

        frames = [
            frame
            async for frame in m27_isolated_event_stream(
                request=_NeverDisconnected(),
                request_payload={"question_sha256": "aa" * 32},
                run_execution=run_execution,
            )
        ]
        events = [_parse_frame(frame) for frame in frames]
        names = [name for name, _ in events]

        assert calls == 1
        assert names[0] == "request_started"
        assert "retrieval_started" in names
        assert "retrieval_ready" in names
        assert names[-3:] == [
            "verified_claim_ready",
            "cited_segment_ready",
            "final_answer_done",
        ]
        assert names.index("cited_segment_ready") < names.index("final_answer_done")
        assert events[-2][1]["text"] == events[-1][1]["response"]["answer_text"]
        assert events[-1][1]["response"]["production_touched"] is False

    asyncio.run(scenario())


def test_safe_terminal_emits_no_material_text() -> None:
    events = m27_verified_material_events(_dto(safe=True))
    assert [name for name, _ in events] == ["safe_abstention_done"]
    assert "Graphology" not in json.dumps(events)


def test_unverified_answer_is_never_material_streamed() -> None:
    events = m27_verified_material_events(_dto(verified=False))
    assert [name for name, _ in events] == ["error"]
    assert "Graphology keeps" not in json.dumps(events)


def test_disconnect_stops_before_material_and_final() -> None:
    async def scenario() -> None:
        def run_execution(**kwargs: Any) -> dict[str, Any]:
            kwargs["event_sink"]({"type": "stage.started", "stage": "retrieval"})
            time.sleep(0.05)
            return _dto()

        frames = [
            frame
            async for frame in m27_isolated_event_stream(
                request=_DisconnectAfterFirstPoll(),
                request_payload={"question_sha256": "bb" * 32},
                run_execution=run_execution,
            )
        ]
        names = [_parse_frame(frame)[0] for frame in frames]
        assert names == ["request_started"]
        assert "cited_segment_ready" not in names
        assert "final_answer_done" not in names

    asyncio.run(scenario())


def test_stream_queue_is_bounded() -> None:
    assert M27_STREAM_QUEUE_MAX == 128


def test_stream_endpoint_fails_closed_without_executor() -> None:
    if hasattr(app.state, "m27_stream_executor"):
        delattr(app.state, "m27_stream_executor")
    denied = TestClient(app).post(M27_ISOLATED_STREAM_PATH, json={"question": "test"})
    assert denied.status_code == 503
    assert denied.json()["detail"]["code"] == "M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE"


def test_stream_endpoint_returns_sse_with_injected_isolated_executor() -> None:
    def run_execution(**kwargs: Any) -> dict[str, Any]:
        kwargs["event_sink"]({"type": "stage.started", "stage": "retrieval"})
        return _dto()

    app.state.m27_stream_executor = run_execution
    try:
        response = TestClient(app).post(
            M27_ISOLATED_STREAM_PATH,
            json={"question": "test", "question_sha256": "cc" * 32},
        )
    finally:
        delattr(app.state, "m27_stream_executor")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_text(response.text)
    names = [name for name, _ in events]
    assert names[0] == "request_started"
    assert "verified_claim_ready" in names
    assert "cited_segment_ready" in names
    assert names.index("cited_segment_ready") < names.index("final_answer_done")
