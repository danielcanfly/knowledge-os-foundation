from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge_engine.m27_isolated_http import APP_SCHEMA, RUNTIME_IDENTITY, app
from knowledge_engine.m27_smoke_preflight import (
    ContainerRecord,
    cleanup_allowed,
    exactly_one_eval_container,
    low_memory_guard_passes,
)


def test_endpoint_identity_is_m27_production_equivalent_not_m26_console(monkeypatch):
    monkeypatch.setenv("M27_BUILD_SHA", "abc123")
    monkeypatch.setenv("M27_IMAGE_DIGEST", "sha256:image")
    payload = TestClient(app).get("/v1/health").json()
    assert payload["schema_version"] == APP_SCHEMA
    assert payload["runtime_identity"] == RUNTIME_IDENTITY
    assert payload["endpoint_module"] == "knowledge_engine.m27_isolated_http:app"
    assert payload["runtime_execution_type"] == "M27ExecutableRequest"
    assert payload["production_equivalent"] is True
    assert "m26_console_api" not in payload["endpoint_module"]


def test_preflight_surface_has_zero_questions_and_provider_calls():
    payload = TestClient(app).get("/v1/preflight").json()
    assert payload["preflight_only"] is True
    assert payload["answer_execution_authorized"] is False
    assert payload["smoke_questions_sent"] == 0
    assert payload["provider_calls"] == 0
    assert payload["quota_active_requests"] == 0


def test_exactly_one_eval_container_detection():
    rows = [ContainerRecord("m27-isolated-eval-05r", {"com.daniel.m27.eval": "true"})]
    assert exactly_one_eval_container(rows)


def test_zero_eval_containers_fail_closed():
    assert not exactly_one_eval_container([])


def test_multi_eval_containers_fail_closed():
    rows = [
        ContainerRecord("m27-isolated-eval-a", {"com.daniel.m27.eval": "true"}),
        ContainerRecord("m27-isolated-eval-b", {"com.daniel.m27.eval": "true"}),
    ]
    assert not exactly_one_eval_container(rows)


def test_production_and_test_page_excluded_from_eval_count():
    rows = [
        ContainerRecord("llm_wiki-knowledge-engine-1", {}),
        ContainerRecord("knowledge-engine-test-answers", {}),
        ContainerRecord("m27-isolated-eval-05r", {"com.daniel.m27.eval": "true"}),
    ]
    assert exactly_one_eval_container(rows)


def test_cleanup_refuses_production_and_test_page():
    assert not cleanup_allowed(ContainerRecord("llm_wiki-knowledge-engine-1", {}))
    assert not cleanup_allowed(ContainerRecord("knowledge-engine-test-answers", {}))


def test_cleanup_allows_only_owned_eval_container():
    assert cleanup_allowed(
        ContainerRecord("m27-isolated-eval-05r", {"com.daniel.m27.eval": "true"})
    )
    assert not cleanup_allowed(ContainerRecord("m27-isolated-eval-05r", {}))


def test_low_memory_guard_is_explicit_and_deterministic():
    assert low_memory_guard_passes(available_memory_mb=192, swap_used_mb=768)
    assert not low_memory_guard_passes(available_memory_mb=191, swap_used_mb=768)
    assert not low_memory_guard_passes(available_memory_mb=192, swap_used_mb=769)


def test_build_image_container_identity_fields_are_exposed(monkeypatch):
    monkeypatch.setenv("M27_BUILD_SHA", "cbc3")
    monkeypatch.setenv("M27_IMAGE_DIGEST", "sha256:deadbeef")
    monkeypatch.setenv("M27_CONTAINER_ID", "container-1")
    payload = TestClient(app).get("/v1/health").json()
    assert payload["build_sha"] == "cbc3"
    assert payload["image_digest"] == "sha256:deadbeef"
    assert payload["container_id"] == "container-1"
