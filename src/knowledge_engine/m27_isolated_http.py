from __future__ import annotations

import os
import socket

from fastapi import FastAPI

from .m27_isolated_admission_harness import ADMISSION_HARNESS_SCHEMA_VERSION
from .m27_production_evidence_bridge import PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA
from .m27_runtime_execution import M27ExecutableRequest

APP_SCHEMA = "m27-production-equivalent-isolated-http/v1"
RUNTIME_IDENTITY = "m27-production-equivalent-runtime"
ENDPOINT_MODULE = "knowledge_engine.m27_isolated_http:app"

app = FastAPI(title="M27 Production-Equivalent Isolated Runtime", version="1.0.0")


def _identity() -> dict[str, object]:
    return {
        "schema_version": APP_SCHEMA,
        "ok": True,
        "runtime_identity": RUNTIME_IDENTITY,
        "endpoint_module": ENDPOINT_MODULE,
        "runtime_execution_type": M27ExecutableRequest.__name__,
        "production_evidence_authority_schema": PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA,
        "admission_harness_schema": ADMISSION_HARNESS_SCHEMA_VERSION,
        "build_sha": os.environ.get("M27_BUILD_SHA", ""),
        "image_digest": os.environ.get("M27_IMAGE_DIGEST", ""),
        "container_id": os.environ.get("M27_CONTAINER_ID", socket.gethostname()),
        "isolated_runtime": True,
        "production_equivalent": True,
        "production_touched": False,
        "smoke_questions_sent": 0,
        "provider_calls": 0,
    }


@app.get("/v1/health")
def health() -> dict[str, object]:
    return _identity()


@app.get("/v1/preflight")
def preflight() -> dict[str, object]:
    payload = _identity()
    payload.update(
        {
            "preflight_only": True,
            "answer_execution_authorized": False,
            "quota_active_requests": 0,
            "quota_provider_calls": 0,
        }
    )
    return payload
