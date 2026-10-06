from __future__ import annotations

import pytest

from knowledge_engine.m27_isolated_admission_harness import (
    ADMISSION_HARNESS_SCHEMA_VERSION,
    HostResourceSnapshot,
    IsolatedAdmissionHarness,
    IsolatedAdmissionHarnessConfig,
    IsolatedBuildIdentity,
    ProductionHealthSnapshot,
    QuotaLifecycleSnapshot,
    require_authorized_preflight,
    summarize_receipts,
)

EXPECTED_SHA = "abc123def456"


def _harness() -> IsolatedAdmissionHarness:
    return IsolatedAdmissionHarness(
        IsolatedAdmissionHarnessConfig(
            expected_build_sha=EXPECTED_SHA,
            isolated_endpoint="http://127.0.0.1:8080",
            minimum_available_memory_mb=2048,
            maximum_swap_used_mb=512,
            maximum_load_1m=8.0,
        )
    )


def _build(endpoint: str = "http://127.0.0.1:8080", sha: str = EXPECTED_SHA):
    return IsolatedBuildIdentity(
        commit_sha=sha,
        image_digest="sha256:" + "f" * 64,
        container_id="m27-smoke-eval-001",
        endpoint=endpoint,
    )


def _prod(identity: str = "prod-release:stable", status_code: int = 200):
    return ProductionHealthSnapshot(status_code=status_code, identity=identity)


def _host(
    *,
    memory: int = 4096,
    swap: int = 0,
    load: float = 1.0,
    containers: int = 1,
    workloads: int = 0,
):
    return HostResourceSnapshot(
        available_memory_mb=memory,
        swap_used_mb=swap,
        load_1m=load,
        active_eval_containers=containers,
        active_build_or_test_workloads=workloads,
    )


def _quota(active: int = 0, calls: int = 0):
    return QuotaLifecycleSnapshot(active_requests=active, provider_calls=calls)


def test_preflight_authorizes_only_verified_loopback_isolated_runtime():
    receipt = _harness().preflight(
        requested_endpoint="http://127.0.0.1:8080",
        build_identity=_build(),
        production_health=_prod(),
        host_resources=_host(),
        quota_state=_quota(),
    )

    assert receipt.status == "AUTHORIZED"
    assert receipt.schema_version == ADMISSION_HARNESS_SCHEMA_VERSION
    assert receipt.reason_codes == ()
    assert receipt.production_touched is False
    assert receipt.request_sent is False
    assert receipt.production_identity_before == "prod-release:stable"
    require_authorized_preflight(receipt)


def test_preflight_refuses_production_target_before_first_request():
    receipt = _harness().preflight(
        requested_endpoint="https://danielcanfly.com",
        build_identity=_build(endpoint="https://danielcanfly.com"),
        production_health=_prod(),
        host_resources=_host(),
        quota_state=_quota(),
    )

    assert receipt.status == "BLOCKED"
    assert "PRODUCTION_TARGET_DENIED" in receipt.reason_codes
    assert "ISOLATED_ENDPOINT_MISMATCH" in receipt.reason_codes
    assert receipt.request_sent is False
    with pytest.raises(RuntimeError, match="preflight blocked"):
        require_authorized_preflight(receipt)


def test_preflight_rejects_build_drift_and_unhealthy_production_read():
    receipt = _harness().preflight(
        requested_endpoint="http://127.0.0.1:8080",
        build_identity=_build(sha="wrong-sha"),
        production_health=_prod(status_code=503),
        host_resources=_host(),
        quota_state=_quota(),
    )

    assert receipt.status == "BLOCKED"
    assert "ISOLATED_BUILD_IDENTITY_MISMATCH" in receipt.reason_codes
    assert "PRODUCTION_HEALTH_READONLY_FAILED" in receipt.reason_codes
    assert receipt.production_touched is False


def test_preflight_rejects_resource_exclusivity_and_quota_poison():
    receipt = _harness().preflight(
        requested_endpoint="http://127.0.0.1:8080",
        build_identity=_build(),
        production_health=_prod(),
        host_resources=_host(memory=1024, swap=1024, load=99.0, containers=2, workloads=1),
        quota_state=_quota(active=1),
    )

    assert receipt.status == "BLOCKED"
    assert set(receipt.reason_codes) >= {
        "HOST_MEMORY_GUARD_TRIPPED",
        "HOST_SWAP_GUARD_TRIPPED",
        "HOST_LOAD_GUARD_TRIPPED",
        "EVAL_CONTAINER_EXCLUSIVITY_VIOLATION",
        "BUILD_OR_TEST_WORKLOAD_EXCLUSIVITY_VIOLATION",
        "QUOTA_ACTIVE_STATE_NOT_CLEAN",
    }


def test_transport_classifier_hard_stops_429_without_provider_calls_and_bad_sse():
    receipt = _harness().classify_case_transport(
        http_status=429,
        provider_calls=0,
        terminal_event={"type": "progress"},
        citation_count=None,
        latency_ms=None,
        ttft_ms=-1,
    )

    assert receipt.status == "HARD_STOP"
    assert set(receipt.reason_codes) >= {
        "HTTP_429_ZERO_PROVIDER_CALLS",
        "MALFORMED_OR_MISSING_TERMINAL_SSE",
        "CITATION_STATUS_UNKNOWN",
        "LATENCY_STATUS_UNKNOWN",
        "TTFT_STATUS_UNKNOWN",
    }
    assert receipt.request_sent is True
    assert receipt.production_touched is False


def test_transport_classifier_accepts_measured_terminal_event():
    receipt = _harness().classify_case_transport(
        http_status=200,
        provider_calls=2,
        terminal_event={"type": "terminal"},
        citation_count=3,
        latency_ms=991.5,
        ttft_ms=120.0,
    )

    assert receipt.status == "OBSERVED"
    assert receipt.reason_codes == ()


def test_postflight_requires_stable_production_identity_clean_quota_and_cleanup():
    harness = _harness()
    pre = harness.preflight(
        requested_endpoint="http://127.0.0.1:8080",
        build_identity=_build(),
        production_health=_prod(identity="prod-A"),
        host_resources=_host(),
        quota_state=_quota(),
    )

    receipt = harness.postflight(
        preflight_receipt=pre,
        production_health_after=_prod(identity="prod-B"),
        host_resources_after=_host(containers=0),
        quota_state_after=_quota(active=2),
        cleanup_confirmed=False,
    )

    assert receipt.status == "HARD_STOP"
    assert set(receipt.reason_codes) >= {
        "PRODUCTION_IDENTITY_CHANGED",
        "EVAL_CONTAINER_EXCLUSIVITY_VIOLATION",
        "QUOTA_ACTIVE_STATE_NOT_CLEAN",
        "ISOLATED_CLEANUP_NOT_CONFIRMED",
    }
    assert receipt.production_identity_before == "prod-A"
    assert receipt.production_identity_after == "prod-B"
    assert receipt.production_touched is False


def test_summarize_receipts_preserves_hard_stop_reasons_without_quality_claims():
    harness = _harness()
    receipts = (
        harness.classify_case_transport(
            http_status=200,
            provider_calls=2,
            terminal_event={"type": "terminal"},
            citation_count=1,
            latency_ms=100.0,
            ttft_ms=10.0,
        ),
        harness.classify_case_transport(
            http_status=429,
            provider_calls=0,
            terminal_event=None,
            citation_count=None,
            latency_ms=None,
            ttft_ms=None,
        ),
    )

    summary = summarize_receipts(receipts)

    assert summary["schema_version"] == ADMISSION_HARNESS_SCHEMA_VERSION
    assert summary["request_sent_count"] == 2
    assert summary["production_touched"] is False
    assert "HTTP_429_ZERO_PROVIDER_CALLS" in summary["reason_codes"]
