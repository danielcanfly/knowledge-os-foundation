"""N31 opted-in loopback ASGI fixture. Not an authenticated or default M26 App."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import queue
import re
import threading
from dataclasses import replace
from pathlib import Path

from knowledge_engine.m27_i28_local_fixture_inputs import (
    KEY,
    Transport,
    make,
    qa_bundle,
    research_bundle,
)
from knowledge_engine.m27_m28_local_rights_memory_fence import LocalRightsMemoryFence
from knowledge_engine.m27_r29_local_action_v1_experimental import (
    R29Action,
    R29LocalActionVerifier,
    R29LocalFixtureAdapter,
)
from knowledge_engine.m27_w4_i02_local_runtime_v1_experimental import I02Denied

_ALLOWED = {"QA-I", "RES-L", "ACT-LOCAL"}
_RUN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{0,35}\Z")
_MAX_BODY = 4096


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


class _NativeTransport(Transport):
    """Acknowledge each actual ASGI send before permitting I02 to proceed."""

    def __init__(self, stream: queue.Queue):
        super().__init__()
        self.stream = stream
        self.pending = {}

    def enqueue(self, frame):
        super().enqueue(frame)
        self.pending[frame.sequence] = frame

    def flush(self, sequence):
        super().flush(sequence)
        frame = self.pending[sequence]
        ack = threading.Event()
        self.stream.put(("frame", {
            "event": "cited_text",
            "sequence": sequence,
            "text": frame.data.decode("utf-8"),
            "citations": list(frame.citation_ids),
            "source_sha256": frame.data_sha256,
            "local_fixture_only": True,
        }, ack))
        if not ack.wait(5):
            raise I02Denied("N31_ASGI_SEND_TIMEOUT")


class N31LocalApp:
    def __init__(self, root: Path, token: str, fixture_port: int,
                 fixture_token: str):
        if os.environ.get("APP_ENV") != "test" or os.environ.get("N31_LOCAL_ONLY") != "1":
            raise RuntimeError("N31_EXPLICIT_LOCAL_TEST_FLAGS_REQUIRED")
        if not root.is_absolute() or root.is_symlink() or not root.exists():
            raise RuntimeError("N31_PRIVATE_ROOT_REQUIRED")
        if not token or len(token) < 24:
            raise RuntimeError("N31_LOCAL_TEST_TOKEN_REQUIRED")
        self.root = root.resolve()
        self.token = token
        self.fixture_port = fixture_port
        self.fixture_token = fixture_token

    async def _send(self, send, status: int, result: dict):
        raw = _json_bytes(result)
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(raw)).encode()),
            (b"cache-control", b"no-store"),
        ]})
        await send({"type": "http.response.body", "body": raw})

    def _fixture(self, workload: str, run: str):
        directory = self.root / "journals"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime, contract = make(directory, kind=workload, run=run)
        rights = LocalRightsMemoryFence(
            self.root / "rights" / (run + ".sqlite"),
            self.root / "blobs" / run,
            fixture_only=True,
        )
        lease = rights.grant(
            tenant="tenantA", run=run, principal="principalA", purpose="research",
            revision="rev1", lease_id="lease_" + run,
        )
        runtime.lifecycle = rights
        return runtime, replace(contract, lifecycle_lease=lease), rights, lease

    @staticmethod
    def _check_body(body: dict):
        allowed = {
            "workload", "run", "tenant", "actor", "source_revision", "lease_epoch",
            "mode", "revoke_after_enqueue",
        }
        if not isinstance(body, dict) or not set(body) <= allowed:
            raise I02Denied("UNKNOWN_REQUEST_FIELDS")
        if (body.get("workload") not in _ALLOWED
                or not isinstance(body.get("run"), str)
                or _RUN.fullmatch(body["run"]) is None
                or body.get("tenant") != "tenantA"
                or body.get("actor") != "principalA"
                or body.get("source_revision") != "rev1"
                or body.get("lease_epoch") != 1
                or type(body.get("revoke_after_enqueue", False)) is not bool
                or body.get("mode", "normal") not in {"normal", "lost_ack", "observer_unknown"}):
            raise I02Denied("N31_IDENTITY_REVISION_LEASE_OR_UNSAFE_INTENT")
        if body["workload"] != "ACT-LOCAL" and body.get("mode", "normal") != "normal":
            raise I02Denied("INVALID_NONACTION_MODE")

    def _execute(self, body: dict, stream: queue.Queue):
        run, kind = body["run"], body["workload"]
        runtime, contract, rights, lease = self._fixture(kind, run)
        runtime.admit(contract)
        if kind == "QA-I":
            args = qa_bundle(runtime, contract)
            transport = _NativeTransport(stream)
            args["transport"] = transport
            if body.get("revoke_after_enqueue"):
                transport.on_enqueue = lambda _frame: rights.revoke(lease)
            outcome, state, budget = runtime.qa(contract, **args)
            return {
                "workload": kind, "run": run, "status": outcome.status,
                "citations_sha256": outcome.original_citation_sha256,
                "first_text_preterminal": outcome.first_text_flushed_preterminal,
                "transport_status": state.status,
                "local_budget_state": (
                    str(budget.status) if hasattr(budget, "status") else "fixture"
                ),
            }
        if kind == "RES-L":
            if body.get("revoke_after_enqueue"):
                raise I02Denied("REVOCATION_HOOK_QA_ONLY")
            outcome, payload, resume = runtime.research_workflow(
                contract, **research_bundle(contract),
            )
            artifact = self.root / "artifacts"
            artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = artifact / (run + ".md")
            with path.open("xb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != outcome.artifact_sha256:
                raise I02Denied("RESEARCH_PHYSICAL_READBACK_MISMATCH")
            return {
                "workload": kind, "run": run, "status": outcome.status,
                "artifact_sha256": digest, "artifact_path": str(path),
                "checkpoint_count": resume["checkpoint_count"],
            }
        action = R29Action(
            idempotency_key="idem_" + run, effect_id="effect_" + run,
            tenant_id="tenantA", run_id=run, actor_id="principalA",
            source_revision="rev1", mode=body.get("mode", "normal"),
        )
        adapter = R29LocalFixtureAdapter(
            port=self.fixture_port, token=self.fixture_token, enabled=True,
        )
        verifier = R29LocalActionVerifier("verifier_x", KEY)
        outcome, receipt = runtime.action_local(
            contract, action, adapter=adapter, verifier=verifier,
            after_enqueue=(lambda: rights.revoke(lease))
            if body.get("revoke_after_enqueue") else None,
        )
        return {
            "workload": kind, "run": run, "status": outcome.status,
            "effect": receipt.get("effect", "UNKNOWN"),
            "sent_attempted": receipt.get("sent_attempted", False),
            "artifact_sha256": outcome.artifact_sha256,
        }

    async def _run(self, body: dict, send):
        stream: queue.Queue = queue.Queue()

        def worker():
            try:
                stream.put(("done", self._execute(body, stream), None))
            except Exception as exc:
                # No stack trace/source content or provider secrets exposed to HTTP.
                category = "DENIED" if isinstance(exc, (I02Denied, ValueError)) else "FAILED"
                stream.put(("error", {"error": category,
                                     "type": type(exc).__name__}, None))

        thread = threading.Thread(target=worker, daemon=True, name="n31-task-" + body["run"])
        thread.start()
        started = False
        while True:
            event, obj, ack = await asyncio.to_thread(stream.get)
            if event == "frame":
                if not started:
                    await send({"type": "http.response.start", "status": 200, "headers": [
                        (b"content-type", b"application/x-ndjson; charset=utf-8"),
                        (b"cache-control", b"no-store"),
                        (b"x-n31-fixture-only", b"true"),
                    ]})
                    started = True
                await send({"type": "http.response.body",
                            "body": _json_bytes(obj) + b"\n", "more_body": True})
                ack.set()
                continue
            if not started:
                await self._send(send, 200 if event == "done" else 403, {
                    **obj, "local_fixture_only": True, "ar09": "ORACLE_UNAVAILABLE",
                    "ar10": "DRAFT", "external_auth": False, "client_ack": False,
                    "ar09_evaluator_executed": False,
                    "ar10_registration_executed": False,
                })
            else:
                await send({"type": "http.response.body", "body": _json_bytes({
                    "event": "terminal" if event == "done" else "denied",
                    **obj, "ar09": "ORACLE_UNAVAILABLE", "ar10": "DRAFT",
                    "client_ack": False,
                    "ar09_evaluator_executed": False,
                    "ar10_registration_executed": False,
                }) + b"\n", "more_body": False})
            return

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return
        host_headers = [
            value.decode("ascii", "ignore").lower() for name, value
            in scope.get("headers", []) if name.lower() == b"host"
        ]
        client = scope.get("client") or ("", 0)
        server = scope.get("server") or ("", 0)
        if (client[0] != "127.0.0.1" or server[0] != "127.0.0.1"
                or len(host_headers) != 1
                or host_headers[0].split(":")[0] != "127.0.0.1"):
            await self._send(send, 403, {"error": "NON_LOOPBACK_DENIED"})
            return
        if scope.get("path") == "/health" and scope.get("method") == "GET":
            await self._send(send, 503, {
                "status": "not_ready", "scope": "local_fixture_only",
                "external_auth": False, "approved_bundle": False,
                "exact_source_signed_image": False, "default_app_ready": False,
            })
            return
        headers = {
            name.lower(): value for name, value in scope.get("headers", [])
        }
        auth = headers.get(b"x-n31-local-token", b"")
        if not hmac.compare_digest(auth, self.token.encode()):
            await self._send(send, 403, {"error": "LOCAL_FIXTURE_TOKEN_DENIED"})
            return
        if scope.get("path") != "/task" or scope.get("method") != "POST":
            await self._send(send, 404, {"error": "NOT_FOUND"})
            return
        raw = bytearray()
        while True:
            event = await receive()
            if event["type"] != "http.request":
                return
            raw.extend(event.get("body", b""))
            if len(raw) > _MAX_BODY:
                await self._send(send, 413, {"error": "BODY_TOO_LARGE"})
                return
            if not event.get("more_body", False):
                break
        try:
            body = json.loads(raw)
            self._check_body(body)
        except (ValueError, UnicodeError, TypeError):
            await self._send(send, 403, {"error": "BAD_OR_UNAUTHORIZED_TASK"})
            return
        await self._run(body, send)


def build_app():
    root = os.environ.get("N31_ROOT", "")
    return N31LocalApp(
        Path(root), os.environ.get("N31_TEST_TOKEN", ""),
        int(os.environ.get("N31_FIXTURE_PORT", "0")),
        os.environ.get("N31_FIXTURE_TOKEN", ""),
    )


app = build_app()
