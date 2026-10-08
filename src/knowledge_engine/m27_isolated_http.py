from __future__ import annotations

import os
import socket
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .m27_isolated_admission_harness import ADMISSION_HARNESS_SCHEMA_VERSION
from .m27_isolated_streaming import (
    M27_ISOLATED_STREAM_PATH,
    M27_ISOLATED_STREAM_SCHEMA,
    m27_isolated_event_stream,
    sse_frame,
)
from .m27_production_evidence_bridge import PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA
from .m27_runtime_execution import M27ExecutableRequest

APP_SCHEMA = "m27-production-equivalent-isolated-http/v1"
RUNTIME_IDENTITY = "m27-production-equivalent-runtime"
ENDPOINT_MODULE = "knowledge_engine.m27_isolated_http:app"


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
        "first_answer_stream_schema": M27_ISOLATED_STREAM_SCHEMA,
        "first_answer_stream_path": M27_ISOLATED_STREAM_PATH,
    }


def create_app(*, stream_executor=None) -> FastAPI:
    candidate = FastAPI(title="M27 Production-Equivalent Isolated Runtime", version="1.0.0")
    if stream_executor is not None:
        candidate.state.m27_stream_executor = stream_executor

    @candidate.get("/v1/health")
    def health() -> dict[str, object]:
        return _identity()

    @candidate.get("/v1/preflight")
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

    @candidate.post(M27_ISOLATED_STREAM_PATH)
    async def stream_answer(request: Request, payload: dict[str, object]) -> StreamingResponse:
        executor = getattr(request.app.state, "m27_stream_executor", None)
        if executor is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE",
                    "schema_version": M27_ISOLATED_STREAM_SCHEMA,
                    "production_touched": False,
                },
            )
        route_id = request.headers.get("x-m27-canary-route-id", "")
        canary_mode = request.headers.get("x-m27-canary-mode", "")
        is_canary = route_id == "m27-owner-only-stage28" and canary_mode == "owner_only"
        async def attested_stream():
            if is_canary:
                yield sse_frame("m27_canary_attested", {
                    "route_id": route_id,
                    "candidate_id": "m27-owner-canary-28",
                    "candidate_git_sha": os.environ.get("M27_BUILD_SHA", ""),
                    "canary_mode": canary_mode,
                    "request_id": uuid.uuid4().hex,
                    "credential_header_seen_by_candidate": "x-m27-owner-canary-auth" in request.headers,
                })
            async for chunk in m27_isolated_event_stream(
                request=request, request_payload=payload, run_execution=executor,
            ):
                yield chunk
        return StreamingResponse(attested_stream(), media_type="text/event-stream")

    return candidate


def create_test_page_app() -> FastAPI:
    from .m27_test_page_executor import build_owner_only_stream_executor

    return create_app(stream_executor=build_owner_only_stream_executor())


app = create_app()

__all__ = ["app", "create_app", "create_test_page_app"]
