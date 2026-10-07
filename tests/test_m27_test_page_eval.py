from __future__ import annotations

from scripts.m27_test_page_compare import parse_sse_blocks, summarize_sse_events


def test_parse_sse_blocks_extracts_event_and_data() -> None:
    text = (
        'event: request_started\n'
        'data: {"ok":true}\n\n'
        'event: cited_segment_ready\n'
        'data: {"text":"answer"}\n\n'
    )
    events = parse_sse_blocks(text)
    assert events == [
        {"event": "request_started", "data": {"ok": True}},
        {"event": "cited_segment_ready", "data": {"text": "answer"}},
    ]


def test_summarize_sse_events_detects_material_and_final() -> None:
    events = parse_sse_blocks(
        'event: request_started\n'
        'data: {}\n\n'
        'event: cited_segment_ready\n'
        'data: {"answer_text":"grounded"}\n\n'
        'event: final_answer_done\n'
        'data: {"status":"owner_only_cited_answer"}\n\n'
    )
    summary = summarize_sse_events(events)
    assert summary["event_count"] == 3
    assert summary["first_material_event_index"] == 1
    assert summary["final_event"] == "final_answer_done"


def test_summarize_sse_events_detects_safe_terminal_status() -> None:
    events = parse_sse_blocks(
        'event: safe_abstention_done\n'
        'data: {"status":"owner_only_safe_abstention"}\n\n'
    )
    summary = summarize_sse_events(events)
    assert summary["safe_terminal_observed"] is True
    assert summary["answer_completed"] is False
