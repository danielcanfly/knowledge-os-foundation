from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

ADMISSION_HARNESS_SCHEMA_VERSION = "m27-isolated-admission-harness/v1"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


@dataclass(frozen=True, slots=True)
class ProductionHealthSnapshot:
    status_code: int
    identity: str
    endpoint: str = "production:/v1/health"

    @property
    def healthy(self) -> bool:
        return self.status_code == 200 and bool(self.identity)


@dataclass(frozen=True, slots=True)
class HostResourceSnapshot:
    available_memory_mb: int
    swap_used_mb: int
    load_1m: float
    active_eval_containers: int
    active_build_or_test_workloads: int = 0


@dataclass(frozen=True, slots=True)
class QuotaLifecycleSnapshot:
    active_requests: int
    provider_calls: int = 0


@dataclass(frozen=True, slots=True)
class IsolatedBuildIdentity:
    commit_sha: str
    image_digest: str
    container_id: str
    endpoint: str


@dataclass(frozen=True, slots=True)
class IsolatedAdmissionHarnessConfig:
    expected_build_sha: str
    isolated_endpoint: str = "http://127.0.0.1:8080"
    expected_quota_active_requests: int = 0
    minimum_available_memory_mb: int = 1024
    maximum_swap_used_mb: int = 256
    maximum_load_1m: float = 16.0


@dataclass(frozen=True, slots=True)
class IsolatedAdmissionReceipt:
    schema_version: str
    status: str
    reason_codes: tuple[str, ...]
    target_endpoint: str
    expected_build_sha: str
    observed_build_sha: str | None = None
    production_identity_before: str | None = None
    production_identity_after: str | None = None
    production_touched: bool = False
    request_sent: bool = False
    cleanup_confirmed: bool | None = None
    measured: Mapping[str, object] = field(default_factory=dict)

    @property
    def authorized(self) -> bool:
        return self.status == "AUTHORIZED"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "target_endpoint": self.target_endpoint,
            "expected_build_sha": self.expected_build_sha,
            "observed_build_sha": self.observed_build_sha,
            "production_identity_before": self.production_identity_before,
            "production_identity_after": self.production_identity_after,
            "production_touched": self.production_touched,
            "request_sent": self.request_sent,
            "cleanup_confirmed": self.cleanup_confirmed,
            "measured": dict(self.measured),
        }


def _is_loopback_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http":
        return False
    return (parsed.hostname or "") in _LOOPBACK_HOSTS


def _same_endpoint(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _resource_reason_codes(
    snapshot: HostResourceSnapshot, config: IsolatedAdmissionHarnessConfig
) -> list[str]:
    reasons: list[str] = []
    if snapshot.available_memory_mb < config.minimum_available_memory_mb:
        reasons.append("HOST_MEMORY_GUARD_TRIPPED")
    if snapshot.swap_used_mb > config.maximum_swap_used_mb:
        reasons.append("HOST_SWAP_GUARD_TRIPPED")
    if snapshot.load_1m > config.maximum_load_1m:
        reasons.append("HOST_LOAD_GUARD_TRIPPED")
    if snapshot.active_eval_containers != 1:
        reasons.append("EVAL_CONTAINER_EXCLUSIVITY_VIOLATION")
    if snapshot.active_build_or_test_workloads != 0:
        reasons.append("BUILD_OR_TEST_WORKLOAD_EXCLUSIVITY_VIOLATION")
    return reasons


class IsolatedAdmissionHarness:
    """Fail-closed guard rail for future Session 05 small-smoke admission."""

    def __init__(self, config: IsolatedAdmissionHarnessConfig) -> None:
        self._config = config

    @property
    def config(self) -> IsolatedAdmissionHarnessConfig:
        return self._config

    def preflight(
        self,
        *,
        requested_endpoint: str,
        build_identity: IsolatedBuildIdentity,
        production_health: ProductionHealthSnapshot,
        host_resources: HostResourceSnapshot,
        quota_state: QuotaLifecycleSnapshot,
    ) -> IsolatedAdmissionReceipt:
        reasons: list[str] = []
        if not _is_loopback_endpoint(requested_endpoint):
            reasons.append("PRODUCTION_TARGET_DENIED")
        if not _same_endpoint(requested_endpoint, self._config.isolated_endpoint):
            reasons.append("ISOLATED_ENDPOINT_MISMATCH")
        if not _same_endpoint(build_identity.endpoint, self._config.isolated_endpoint):
            reasons.append("BUILD_ENDPOINT_MISMATCH")
        if build_identity.commit_sha != self._config.expected_build_sha:
            reasons.append("ISOLATED_BUILD_IDENTITY_MISMATCH")
        if not build_identity.image_digest or not build_identity.container_id:
            reasons.append("ISOLATED_BUILD_IDENTITY_INCOMPLETE")
        if not production_health.healthy:
            reasons.append("PRODUCTION_HEALTH_READONLY_FAILED")
        reasons.extend(_resource_reason_codes(host_resources, self._config))
        if quota_state.active_requests != self._config.expected_quota_active_requests:
            reasons.append("QUOTA_ACTIVE_STATE_NOT_CLEAN")
        return IsolatedAdmissionReceipt(
            schema_version=ADMISSION_HARNESS_SCHEMA_VERSION,
            status="AUTHORIZED" if not reasons else "BLOCKED",
            reason_codes=tuple(reasons),
            target_endpoint=requested_endpoint,
            expected_build_sha=self._config.expected_build_sha,
            observed_build_sha=build_identity.commit_sha,
            production_identity_before=production_health.identity,
            production_touched=False,
            request_sent=False,
            measured={
                "production_health_status_code": production_health.status_code,
                "available_memory_mb": host_resources.available_memory_mb,
                "swap_used_mb": host_resources.swap_used_mb,
                "load_1m": host_resources.load_1m,
                "active_eval_containers": host_resources.active_eval_containers,
                "active_build_or_test_workloads": host_resources.active_build_or_test_workloads,
                "quota_active_requests": quota_state.active_requests,
                "provider_calls": quota_state.provider_calls,
            },
        )

    def classify_case_transport(
        self,
        *,
        http_status: int,
        provider_calls: int,
        terminal_event: Mapping[str, object] | None,
        citation_count: int | None,
        latency_ms: float | None,
        ttft_ms: float | None,
    ) -> IsolatedAdmissionReceipt:
        reasons: list[str] = []
        if http_status == 429 and provider_calls == 0:
            reasons.append("HTTP_429_ZERO_PROVIDER_CALLS")
        if terminal_event is None or terminal_event.get("type") != "terminal":
            reasons.append("MALFORMED_OR_MISSING_TERMINAL_SSE")
        if citation_count is None:
            reasons.append("CITATION_STATUS_UNKNOWN")
        if latency_ms is None or latency_ms < 0:
            reasons.append("LATENCY_STATUS_UNKNOWN")
        if ttft_ms is None or ttft_ms < 0:
            reasons.append("TTFT_STATUS_UNKNOWN")
        return IsolatedAdmissionReceipt(
            schema_version=ADMISSION_HARNESS_SCHEMA_VERSION,
            status="OBSERVED" if not reasons else "HARD_STOP",
            reason_codes=tuple(reasons),
            target_endpoint=self._config.isolated_endpoint,
            expected_build_sha=self._config.expected_build_sha,
            production_touched=False,
            request_sent=True,
            measured={
                "http_status": http_status,
                "provider_calls": provider_calls,
                "citation_count": citation_count,
                "latency_ms": latency_ms,
                "ttft_ms": ttft_ms,
            },
        )

    def postflight(
        self,
        *,
        preflight_receipt: IsolatedAdmissionReceipt,
        production_health_after: ProductionHealthSnapshot,
        host_resources_after: HostResourceSnapshot,
        quota_state_after: QuotaLifecycleSnapshot,
        cleanup_confirmed: bool,
    ) -> IsolatedAdmissionReceipt:
        reasons: list[str] = []
        if not production_health_after.healthy:
            reasons.append("PRODUCTION_HEALTH_READONLY_FAILED")
        if (
            preflight_receipt.production_identity_before
            and production_health_after.identity != preflight_receipt.production_identity_before
        ):
            reasons.append("PRODUCTION_IDENTITY_CHANGED")
        reasons.extend(_resource_reason_codes(host_resources_after, self._config))
        if quota_state_after.active_requests != self._config.expected_quota_active_requests:
            reasons.append("QUOTA_ACTIVE_STATE_NOT_CLEAN")
        if not cleanup_confirmed:
            reasons.append("ISOLATED_CLEANUP_NOT_CONFIRMED")
        return IsolatedAdmissionReceipt(
            schema_version=ADMISSION_HARNESS_SCHEMA_VERSION,
            status="CLEAN" if not reasons else "HARD_STOP",
            reason_codes=tuple(reasons),
            target_endpoint=preflight_receipt.target_endpoint,
            expected_build_sha=self._config.expected_build_sha,
            observed_build_sha=preflight_receipt.observed_build_sha,
            production_identity_before=preflight_receipt.production_identity_before,
            production_identity_after=production_health_after.identity,
            production_touched=False,
            request_sent=False,
            cleanup_confirmed=cleanup_confirmed,
            measured={
                "production_health_status_code": production_health_after.status_code,
                "available_memory_mb": host_resources_after.available_memory_mb,
                "swap_used_mb": host_resources_after.swap_used_mb,
                "load_1m": host_resources_after.load_1m,
                "active_eval_containers": host_resources_after.active_eval_containers,
                "active_build_or_test_workloads": (
                    host_resources_after.active_build_or_test_workloads
                ),
                "quota_active_requests": quota_state_after.active_requests,
                "provider_calls": quota_state_after.provider_calls,
            },
        )


def require_authorized_preflight(receipt: IsolatedAdmissionReceipt) -> None:
    if not receipt.authorized:
        raise RuntimeError(
            "isolated admission preflight blocked: " + ",".join(receipt.reason_codes)
        )


def summarize_receipts(receipts: Sequence[IsolatedAdmissionReceipt]) -> dict[str, object]:
    return {
        "schema_version": ADMISSION_HARNESS_SCHEMA_VERSION,
        "receipt_count": len(receipts),
        "statuses": [receipt.status for receipt in receipts],
        "reason_codes": sorted({code for receipt in receipts for code in receipt.reason_codes}),
        "production_touched": any(receipt.production_touched for receipt in receipts),
        "request_sent_count": sum(1 for receipt in receipts if receipt.request_sent),
    }
