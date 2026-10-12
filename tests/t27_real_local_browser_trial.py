"""T27 nonproduction Chrome->FastAPI->M26 SSE trial on 127.0.0.1 only.

The answer body is explicitly injected fixture data, NOT a real approved Provider
or authoritative source. Output must never be submitted as a product grade.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "pilot/m27/t27-local-native-trial/client.js"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OWNER = "ab" * 32


def dto(*, safe: bool) -> dict:
    if safe:
        return {
            "status": "owner_only_safe_abstention", "safe_abstention": True,
            "answer_text": "", "citations": [], "answer_claims": [],
        }
    return {
        "status": "owner_only_cited_answer", "safe_abstention": False,
        "answer_text": "Synthetic local cited UTF-8 receipt. [fixture_1]",
        "answer_claims": [{
            "claim_id": "fixture_claim", "surface_text": "Synthetic local cited UTF-8 receipt.",
        }],
        "citations": [{
            "claim_id": "fixture_claim", "citation_id": "fixture_1",
            "source_identity": "LOCAL_FIXTURE_NOT_LICENSED", "locator_id": "fixture_locator",
        }],
        "integrity": {
            "unsupported_accepted_claims": 0,
            "material_claim_support_verified": True,
            "citation_locator_valid": True,
        },
    }


def serve(port: int) -> None:
    import uvicorn
    from fastapi.responses import HTMLResponse, Response

    from knowledge_engine import m26_ask_api

    # Create an isolated local test host from the original route, not a second
    # hand-written mock /api/m26/query/stream implementation.
    m26_ask_api._preload_query_runtime = lambda: None

    def fixture_query(**kwargs: object) -> dict:
        sink = kwargs.get("event_sink")
        if callable(sink):
            sink({"type": "stage.started", "stage": "retrieval"})
            time.sleep(0.03)
            sink({"type": "stage.completed", "stage": "retrieval",
                  "selected_evidence_count": 1, "latency_ms": 30})
        return dto(safe="safe abstention" in str(kwargs.get("request_payload", {})))

    m26_ask_api.run_owner_query_for_web = fixture_query
    actual_generator = m26_ask_api.verified_query_event_stream

    async def delayed_terminal(**kwargs: object):
        async for frame in actual_generator(**kwargs):
            if frame.startswith("event: final_answer_done"):
                # Fixture-only flush separation for independently observed
                # substantive-first SSE. Not a production latency result.
                await asyncio.sleep(0.08)
            yield frame

    m26_ask_api.verified_query_event_stream = delayed_terminal
    app = m26_ask_api.create_app(root=ROOT, require_remote_dense=False)
    local_token = os.environ["T27_LOCAL_TOKEN"]
    os.environ["M26_QUERY_BACKEND_TOKEN"] = local_token
    os.environ["KNOWLEDGE_ENGINE_OWNER_SUBJECT_HASH"] = OWNER
    os.environ.pop("M26_ALLOW_LOCAL_BACKEND_AUTH_BYPASS", None)

    @app.get("/t27/health")
    async def health() -> dict:
        return {"mode": "local_fixture", "external_authorized": False}

    @app.get("/t27/client.js")
    async def js() -> Response:
        return Response(CLIENT.read_bytes(), media_type="application/javascript")

    @app.get("/t27/run", response_class=HTMLResponse)
    async def run(mode: str = "cited") -> HTMLResponse:
        if mode not in ("cited", "unauthorized", "safe"):
            return HTMLResponse("Invalid local case", status_code=400)
        # Only disposable local test credentials are embedded in a loopback page.
        config = {
            "token": "" if mode == "unauthorized" else local_token,
            "owner": OWNER,
            "mode": mode,
        }
        body = (
            "<!doctype html><meta charset='UTF-8'><title>T27 Local Trial</title>"
            "<pre id='receipt'>pending</pre>"
            "<script>window.__T27_CONFIG__="
            + json.dumps(config, separators=(",", ":"))
            + ";</script><script src='/t27/client.js'></script>"
        )
        return HTMLResponse(body, headers={"Cache-Control": "no-store"})

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(evidence: Path) -> dict:
    import httpx
    from playwright.sync_api import sync_playwright

    evidence.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    port = local_port()
    output = evidence / "T27_LOCAL_HTTP_HOST.log"
    env = os.environ.copy()
    env["T27_LOCAL_TOKEN"] = token
    env["PYTHONPATH"] = str(ROOT / "src")
    start = time.monotonic()
    with output.open("wb") as log:
        host = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "serve",
             "--port", str(port)], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            with httpx.Client(timeout=1.0, trust_env=False) as client:
                for _ in range(120):
                    if host.poll() is not None:
                        raise RuntimeError("Local fixture host exited before readiness")
                    try:
                        if client.get(url + "/t27/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Local fixture host failed readiness")
                auth_negative = client.post(
                    url + "/api/m26/query/stream",
                    json={"question": "without local token"},
                    headers={"x-m26-owner-subject-hash": OWNER},
                )
            if auth_negative.status_code != 403:
                raise AssertionError("Original M26 route did not reject missing token")
            receipts = {}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=CHROME, headless=True,
                    args=["--no-first-run", "--no-default-browser-check"],
                )
                try:
                    for mode in ("unauthorized", "safe", "cited"):
                        context = browser.new_context()
                        page = context.new_page()
                        try:
                            response = page.goto(url + "/t27/run?mode=" + mode,
                                                 wait_until="domcontentloaded", timeout=20000)
                            if not response or page.locator("#receipt").count() != 1:
                                raise AssertionError(
                                    f"CHROME_LOCAL_PAGE_UNAVAILABLE mode={mode} "
                                    f"http_status={response.status if response else None} "
                                    f"title={page.title()[:80]}"
                                )
                            page.wait_for_function(
                                "() => !!document.querySelector('#receipt') && "
                                "document.querySelector('#receipt').dataset.done === 'yes'",
                                timeout=20000,
                            )
                            raw = page.locator("#receipt").inner_text()
                            receipts[mode] = json.loads(raw)
                        finally:
                            context.close()
                finally:
                    browser.close()
            if receipts["unauthorized"]["http_status"] != 403:
                raise AssertionError("Chrome missing-token negative not 403")
            if receipts["unauthorized"]["first_substantive_utf8_ms"] is not None:
                raise AssertionError("Denied browser received substantive text")
            if receipts["safe"]["outcome"] != "REJECTED":
                raise AssertionError("Abstention incorrectly classified")
            if receipts["safe"]["first_substantive_utf8_ms"] is not None:
                raise AssertionError("Safe abstention incorrectly counted as cited")
            cited = receipts["cited"]
            if (cited["http_status"] != 200 or cited["outcome"] != "COMPLETE"
                    or cited["first_substantive_utf8_ms"] is None
                    or not cited["cited_before_terminal"]
                    or not cited["first_substantive_sha256"]):
                raise AssertionError("Real Chrome client cited-first transport failure")
            return {
                "schema": "m27.w5.t27.local_browser_transport.v1",
                "passed": True, "fixture_only": True, "official": False,
                "authorized_external_nonprod": False,
                "real_provider_dispatches": 0, "official_case_count": 0,
                "host_process_pid": host.pid,
                "host_process_returncode_after_terminate": "pending",
                "real_chrome_browser": True,
                "route": "/api/m26/query/stream",
                "headless_chrome_binary_sha256": hashlib.sha256(
                    Path(CHROME).read_bytes()).hexdigest(),
                "client_js_sha256": hashlib.sha256(CLIENT.read_bytes()).hexdigest(),
                "duration_ms": (time.monotonic() - start) * 1000,
                "original_route_unauthorized_status": auth_negative.status_code,
                "cases": receipts,
            }
        finally:
            if host.poll() is None:
                host.terminate()
                try:
                    host.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    host.kill()
                    host.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["serve", "run"])
    parser.add_argument("--port", type=int)
    parser.add_argument("--evidence")
    args = parser.parse_args()
    if args.action == "serve":
        if not args.port or not os.environ.get("T27_LOCAL_TOKEN"):
            raise SystemExit("Local fixture controller input missing")
        serve(args.port)
    else:
        if not args.evidence:
            raise SystemExit("--evidence required")
        output = Path(args.evidence)
        result = run(output)
        target = output / "T27_CHROME_NATIVE_HTTP_RECEIPTS.json"
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        os.chmod(target, 0o600)
        print(json.dumps({
            "passed": result["passed"],
            "cases": {
                k: {
                    "http": v["http_status"],
                    "outcome": v["outcome"],
                    "cited_before_terminal": v["cited_before_terminal"],
                } for k, v in result["cases"].items()
            },
            "evidence": str(target),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
