from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from knowledge_engine.m27_isolated_http import create_app
from knowledge_engine.m27_isolated_streaming import M27_ISOLATED_STREAM_PATH


def _verified_result() -> dict[str, Any]:
    citation = {
        "claim_id": "claim-1",
        "evidence_id": "ev-1",
        "locator_id": "loc-1",
        "source_identity": "source-1",
    }
    return {
        "status_code": "M27_RUNTIME_COMPOSED",
        "answer": {
            "answer_text": "Verified integration text.",
            "citations": [citation],
            "answer_claims": [
                {"claim_id": "claim-1", "surface_text": "Verified integration text."}
            ],
            "material_claim_support_verified": True,
            "citation_locator_valid": True,
            "unsupported_accepted_claims": 0,
        },
        "verification": {
            "citations": [citation],
            "material_claim_support_verified": True,
            "citation_locator_valid": True,
            "unsupported_accepted_claims": 0,
        },
        "terminal_reason": "VERIFIED_CITED_ANSWER",
        "production_touched": False,
    }


def test_factory_remains_fail_closed_without_executor() -> None:
    response = TestClient(create_app()).post(
        M27_ISOLATED_STREAM_PATH, json={"question": "test"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE"


def test_factory_injects_executor_without_changing_stream_contract() -> None:
    def executor(**kwargs: Any) -> dict[str, Any]:
        kwargs["event_sink"]({"type": "stage.started", "stage": "retrieval"})
        return _verified_result()

    response = TestClient(create_app(stream_executor=executor)).post(
        M27_ISOLATED_STREAM_PATH,
        json={"question": "test", "question_sha256": "ab" * 32},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: verified_claim_ready" in response.text
    assert "event: cited_segment_ready" in response.text
    assert response.text.index("event: cited_segment_ready") < response.text.index(
        "event: final_answer_done"
    )
    assert '"production_touched":false' in response.text
