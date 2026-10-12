import json

from fastapi.testclient import TestClient

from knowledge_engine.m27_isolated_http import create_app


def test_attestation_scoped_and_safe(monkeypatch):
    monkeypatch.setenv("M27_BUILD_SHA", "test-sha")
    def execute(**kwargs):
        return {"status_code": "M27_RUNTIME_SAFE_TERMINAL", "terminal_reason": "TEST_SAFE"}
    client = TestClient(create_app(stream_executor=execute))
    headers = {"x-m27-canary-route-id": "m27-owner-only-stage28", "x-m27-canary-mode": "owner_only"}
    r = client.post("/v1/answers/stream", json={"question": "Test"}, headers=headers)
    assert r.status_code == 200
    att = next(json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ") and "m27_canary_attested" in line)
    assert att["candidate_git_sha"] == "test-sha"
    assert att["credential_header_seen_by_candidate"] is False
    assert len(att["request_id"]) == 32
    normal = client.post("/v1/answers/stream", json={"question": "Test"})
    assert "m27_canary_attested" not in normal.text
    headers["x-m27-owner-canary-auth"] = "synthetic-only"
    injected = client.post("/v1/answers/stream", json={"question": "Test"}, headers=headers)
    att2 = next(json.loads(line[6:]) for line in injected.text.splitlines() if line.startswith("data: ") and "m27_canary_attested" in line)
    assert att2["credential_header_seen_by_candidate"] is True
    assert "synthetic-only" not in injected.text
