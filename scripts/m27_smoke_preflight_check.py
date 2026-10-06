
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from knowledge_engine.m27_isolated_admission_harness import (
    HostResourceSnapshot,
    IsolatedAdmissionHarness,
    IsolatedAdmissionHarnessConfig,
    IsolatedBuildIdentity,
    ProductionHealthSnapshot,
    QuotaLifecycleSnapshot,
)
from knowledge_engine.m27_smoke_preflight import (
    EVAL_LABEL_KEY,
    EVAL_LABEL_VALUE,
    LOW_MEMORY_MAX_SWAP_USED_MB,
    LOW_MEMORY_MIN_AVAILABLE_MB,
)

EXPECTED_ENDPOINT = "http://127.0.0.1:18080"
PRODUCTION_HEALTH_URL = "http://127.0.0.1:8080/v1/health"
EXPECTED_MODULE = "knowledge_engine.m27_isolated_http:app"
EXPECTED_RUNTIME = "m27-production-equivalent-runtime"


def _http_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=5) as response:  # nosec: loopback only
        return json.loads(response.read().decode("utf-8"))


def _run(args: list[str]) -> str:
    return subprocess.check_output(args, text=True).strip()


def _meminfo() -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) // 1024
    return values.get("MemAvailable", 0), values.get("SwapTotal", 0) - values.get("SwapFree", 0)


def _load_1m() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def _eval_containers() -> list[dict[str, str]]:
    raw = _run(
        [
            "docker",
            "ps",
            "--filter",
            f"label={EVAL_LABEL_KEY}={EVAL_LABEL_VALUE}",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Image}}",
        ]
    )
    rows: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        cid, name, image = line.split("\t", 2)
        rows.append({"id": cid, "name": name, "image": image})
    return rows


def main() -> int:
    expected_sha = _run(["git", "rev-parse", "HEAD"])
    production_before = _http_json(PRODUCTION_HEALTH_URL)
    endpoint_health = _http_json(EXPECTED_ENDPOINT + "/v1/health")
    endpoint_preflight = _http_json(EXPECTED_ENDPOINT + "/v1/preflight")
    containers = _eval_containers()
    available_mb, swap_used_mb = _meminfo()
    host = HostResourceSnapshot(
        available_memory_mb=available_mb,
        swap_used_mb=swap_used_mb,
        load_1m=_load_1m(),
        active_eval_containers=len(containers),
        active_build_or_test_workloads=0,
    )
    container = (
        containers[0]
        if len(containers) == 1
        else {"id": "", "name": "", "image": ""}
    )
    build = IsolatedBuildIdentity(
        commit_sha=str(endpoint_health.get("build_sha") or ""),
        image_digest=str(endpoint_health.get("image_digest") or ""),
        container_id=str(endpoint_health.get("container_id") or ""),
        endpoint=EXPECTED_ENDPOINT,
    )
    prod_before_snapshot = ProductionHealthSnapshot(
        status_code=200 if production_before.get("ok") is True else 503,
        identity=json.dumps(production_before.get("backend", {}), sort_keys=True),
    )
    harness = IsolatedAdmissionHarness(
        IsolatedAdmissionHarnessConfig(
            expected_build_sha=expected_sha,
            isolated_endpoint=EXPECTED_ENDPOINT,
            minimum_available_memory_mb=LOW_MEMORY_MIN_AVAILABLE_MB,
            maximum_swap_used_mb=LOW_MEMORY_MAX_SWAP_USED_MB,
            maximum_load_1m=16.0,
        )
    )
    preflight = harness.preflight(
        requested_endpoint=EXPECTED_ENDPOINT,
        build_identity=build,
        production_health=prod_before_snapshot,
        host_resources=host,
        quota_state=QuotaLifecycleSnapshot(
            active_requests=int(endpoint_preflight.get("quota_active_requests", -1)),
            provider_calls=int(endpoint_preflight.get("quota_provider_calls", -1)),
        ),
    )
    semantic_reasons: list[str] = []
    if endpoint_health.get("runtime_identity") != EXPECTED_RUNTIME:
        semantic_reasons.append("ENDPOINT_RUNTIME_IDENTITY_MISMATCH")
    if endpoint_health.get("endpoint_module") != EXPECTED_MODULE:
        semantic_reasons.append("ENDPOINT_MODULE_MISMATCH")
    if "m26_console_api" in str(endpoint_health.get("endpoint_module")):
        semantic_reasons.append("M26_CONSOLE_ENDPOINT_REJECTED")
    if endpoint_preflight.get("answer_execution_authorized") is not False:
        semantic_reasons.append("PREFLIGHT_AUTHORIZES_ANSWER_EXECUTION")
    if int(endpoint_preflight.get("smoke_questions_sent", -1)) != 0:
        semantic_reasons.append("SMOKE_QUESTIONS_SENT")
    if int(endpoint_preflight.get("provider_calls", -1)) != 0:
        semantic_reasons.append("PROVIDER_CALLS_OCCURRED")
    production_after = _http_json(PRODUCTION_HEALTH_URL)
    postflight = harness.postflight(
        preflight_receipt=preflight,
        production_health_after=ProductionHealthSnapshot(
            status_code=200 if production_after.get("ok") is True else 503,
            identity=json.dumps(production_after.get("backend", {}), sort_keys=True),
        ),
        host_resources_after=host,
        quota_state_after=QuotaLifecycleSnapshot(
            active_requests=int(endpoint_preflight.get("quota_active_requests", -1)),
            provider_calls=int(endpoint_preflight.get("quota_provider_calls", -1)),
        ),
        cleanup_confirmed=True,
    )
    status = (
        "READY"
        if preflight.status == "AUTHORIZED"
        and postflight.status == "CLEAN"
        and not semantic_reasons
        else "BLOCKED"
    )
    result = {
        "schema_version": "m27-smoke-preflight-check/v1",
        "status": status,
        "endpoint": EXPECTED_ENDPOINT,
        "endpoint_module": endpoint_health.get("endpoint_module"),
        "runtime_identity": endpoint_health.get("runtime_identity"),
        "build_sha": endpoint_health.get("build_sha"),
        "image_digest": endpoint_health.get("image_digest"),
        "container": container,
        "eval_container_count": len(containers),
        "host": {
            "available_memory_mb": available_mb,
            "swap_used_mb": swap_used_mb,
            "low_memory_min_available_mb": LOW_MEMORY_MIN_AVAILABLE_MB,
            "low_memory_max_swap_used_mb": LOW_MEMORY_MAX_SWAP_USED_MB,
            "load_1m": host.load_1m,
        },
        "preflight_status": preflight.status,
        "preflight_reasons": list(preflight.reason_codes),
        "postflight_status": postflight.status,
        "postflight_reasons": list(postflight.reason_codes),
        "semantic_reasons": semantic_reasons,
        "quota_active_requests": endpoint_preflight.get("quota_active_requests"),
        "quota_provider_calls": endpoint_preflight.get("quota_provider_calls"),
        "smoke_questions_sent": endpoint_preflight.get("smoke_questions_sent"),
        "provider_calls": endpoint_preflight.get("provider_calls"),
        "production_identity_stable": (
            production_before.get("backend") == production_after.get("backend")
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
