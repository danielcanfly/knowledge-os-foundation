"""N31 HTTP gate and real I28→I02 fixture dispatch tests (not real IdP)."""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest

TOKEN = "local-n31-test-token-1234567890123456"


@pytest.fixture
def fixture_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("N31_LOCAL_ONLY", "1")
    monkeypatch.setenv("N31_ROOT", str(tmp_path))
    monkeypatch.setenv("N31_TEST_TOKEN", TOKEN)
    monkeypatch.setenv("N31_FIXTURE_PORT", "27840")
    monkeypatch.setenv("N31_FIXTURE_TOKEN", TOKEN)
    module = importlib.import_module("knowledge_engine.m27_n31_nonprod_app")
    return module.N31LocalApp(tmp_path, TOKEN, 27840, TOKEN)


def invoke(app, *, method="POST", path="/task", data=None, token=TOKEN,
           client="127.0.0.1", server="127.0.0.1", host="127.0.0.1:27839"):
    raw = json.dumps(data).encode() if data is not None else b""
    received = False
    frames = []

    async def receive():
        nonlocal received
        if received:
            raise RuntimeError("unexpected second read")
        received = True
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        frames.append(message)

    headers = [(b"host", host.encode())]
    if token is not None:
        headers.append((b"x-n31-local-token", token.encode()))
    scope = {
        "type": "http", "method": method, "path": path,
        "client": (client, 50000), "server": (server, 27839),
        "headers": headers,
    }
    asyncio.run(app(scope, receive, send))
    status = next(x["status"] for x in frames if x["type"] == "http.response.start")
    payload = b"".join(x.get("body", b"") for x in frames if x["type"] == "http.response.body")
    return status, payload.decode(), frames


def task(kind, run, **extra):
    return {
        "workload": kind, "run": run, "tenant": "tenantA",
        "actor": "principalA", "source_revision": "rev1", "lease_epoch": 1,
        **extra,
    }


def test_cited_native_qa_is_http_taskcontract(fixture_app):
    status, raw, frames = invoke(fixture_app, data=task("QA-I", "caseQa"))
    assert status == 200
    lines = [json.loads(x) for x in raw.splitlines()]
    assert lines[0]["event"] == "cited_text"
    assert lines[0]["citations"] == ["native:citation:A"]
    assert "Alpha" in lines[0]["text"]
    assert lines[-1]["event"] == "terminal"
    assert lines[-1]["first_text_preterminal"] is True
    assert lines[-1]["ar09"] == "ORACLE_UNAVAILABLE"
    assert lines[-1]["ar10"] == "DRAFT"
    assert lines[-1]["client_ack"] is False
    assert sum(x["type"] == "http.response.start" for x in frames) == 1
    assert any(x.get("more_body") is True for x in frames)


def test_research_has_readback_checkpoint_and_hash(fixture_app):
    status, raw, _ = invoke(fixture_app, data=task("RES-L", "caseResearch"))
    assert status == 200
    result = json.loads(raw)
    from hashlib import sha256
    from pathlib import Path
    data = Path(result["artifact_path"]).read_bytes()
    assert sha256(data).hexdigest() == result["artifact_sha256"]
    assert result["checkpoint_count"] == 2
    assert result["status"] == "RESEARCH_LOCAL_ARTIFACT_ONLY"


@pytest.mark.parametrize(("field", "invalid"), [
    ("tenant", "tenantB"), ("actor", "someoneElse"),
    ("source_revision", "rev2"), ("lease_epoch", 2),
    ("workload", "PROVIDER"), ("mode", "remote"),
])
def test_invalid_contract_denied_pre_admission(fixture_app, field, invalid):
    body = task("QA-I", "caseInvalid")
    body[field] = invalid
    status, _, _ = invoke(fixture_app, data=body)
    assert status == 403


def test_revoke_after_enqueue_cannot_publish(fixture_app):
    status, raw, frames = invoke(
        fixture_app, data=task("QA-I", "caseRevoked", revoke_after_enqueue=True),
    )
    assert status == 403
    assert "cited_text" not in raw
    assert len([x for x in frames if x["type"] == "http.response.body"]) == 1


def test_anonymous_and_nonloopback_denied(fixture_app):
    for kwargs in (
        {"token": None},
        {"client": "192.0.2.15"},
        {"server": "0.0.0.0"},
        {"host": "outside.example.invalid"},
    ):
        status, _, _ = invoke(fixture_app, data=task("QA-I", "denied"), **kwargs)
        assert status == 403


def test_health_never_healthy_with_synthetic_only(fixture_app):
    status, raw, _ = invoke(fixture_app, method="GET", path="/health", token=None)
    assert status == 503
    assert json.loads(raw)["status"] == "not_ready"
    assert json.loads(raw)["default_app_ready"] is False


def test_unknown_fields_and_unsafe_target_denied(fixture_app):
    body = {**task("ACT-LOCAL", "unsafe"), "target_url": "https://evil.invalid"}
    status, _, _ = invoke(fixture_app, data=body)
    assert status == 403


def test_feature_flag_required_even_with_local_token(fixture_app, tmp_path, monkeypatch):
    cls = type(fixture_app)
    monkeypatch.delenv("N31_LOCAL_ONLY")
    with pytest.raises(RuntimeError, match="N31_EXPLICIT_LOCAL_TEST_FLAGS_REQUIRED"):
        cls(tmp_path, TOKEN, 27840, TOKEN)
