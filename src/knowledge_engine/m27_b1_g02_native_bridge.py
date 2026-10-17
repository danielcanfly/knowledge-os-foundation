"""H02 G02 opt-in loopback Research admission bridge (nonprod, never product-registered).

TaskContract v1 is the exact native source validation. The only executable workload
is G02's real owner-document, zero-provider, read-only persisted research pipeline.
The independent source/journal verifier is executed in a separate interpreter.
No public identity, network gateway, semantic-provider or F35 authority is inferred.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from m27_task_contracts_v1 import outcome_receipt, sha256 as contract_sha, task_contract
from m27_b0_research_outcome import (
    ResearchDenied, execute, fsync_write, load_json, sha, canonical,
)

REQUEST_SCHEMA = "m27-h02-g02-first-party-nonprod/v1"
RUN_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$")
REQUEST_KEYS = {
    "schema", "request_id", "run_id", "task_id", "task_version",
    "tenant_id", "principal_id", "contract_sha256", "registry_sha256",
    "outcome_id",
}


class AdmissionDenied(ValueError):
    """Fail-closed scoped local Task and Outcome boundary."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise AdmissionDenied(reason)


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class ResearchBridge:
    def __init__(self, *, contract_path: Path, registry_path: Path,
                 db_path: Path, outcome_dir: Path, independent_checker: Path,
                 tenant_id: str, principal_id: str):
        self.contract_path = contract_path
        self.registry_path = registry_path
        self.db_path = db_path
        self.outcome_dir = outcome_dir
        self.independent_checker = independent_checker
        self.tenant_id = tenant_id
        self.principal_id = principal_id
        require(outcome_dir.is_dir() and not outcome_dir.is_symlink() and
                db_path.parent.is_dir() and not db_path.is_symlink(),
                "ISOLATED_NONPROD_STORAGE_REQUIRED")
        require(independent_checker.is_file() and not independent_checker.is_symlink(),
                "INDEPENDENT_VERIFIER_UNAVAILABLE")

    def input_contract(self) -> dict:
        contract = load_json(self.contract_path)
        task_contract(contract)  # actual immutable M27 ABI; validate on EVERY request
        require(contract["tenant_id"] == self.tenant_id and
                contract["actor"]["principal_id"] == self.principal_id,
                "SERVICE_ACTOR_SCOPE_MISMATCH")
        require(contract["workload_kind"] == "research" and
                contract["authority"]["max_side_effect"] == "read" and
                contract["authority"]["allowed_capability_ids"] ==
                ["local_owner_document_read"], "UNAUTHORIZED_RESEARCH_CAPABILITY")
        require(contract["definition_of_done"]["independent_verification_required"],
                "INDEPENDENT_VERIFICATION_REQUIRED")
        return contract

    def validate_request(self, request: object) -> dict:
        require(type(request) is dict and set(request) == REQUEST_KEYS,
                "REQUEST_ABI_INVALID")
        for key in ("request_id", "run_id"):
            require(type(request[key]) is str and RUN_ID.fullmatch(request[key]) is not None,
                    "UNSAFE_OR_MISSING_ID")
        require(request["schema"] == REQUEST_SCHEMA, "REQUEST_SCHEMA_UNSUPPORTED")
        require(request["tenant_id"] == self.tenant_id and
                request["principal_id"] == self.principal_id, "CLIENT_IDENTITY_MISMATCH")
        contract = self.input_contract()
        require(request["task_id"] == contract["task_id"] and
                type(request["task_version"]) is int and
                request["task_version"] == contract["task_version"] and
                request["contract_sha256"] == contract_sha(contract),
                "TASK_ABI_OR_CONTRACT_PIN_MISMATCH")
        registry = load_json(self.registry_path)
        require(request["registry_sha256"] == sha(canonical(registry)),
                "REGISTRY_PIN_MISMATCH")
        require(len(contract["output_specs"]) == 1 and
                request["outcome_id"] == contract["output_specs"][0]["outcome_id"],
                "OUTCOME_ABI_MISMATCH")
        return contract

    def bind_request(self, request: dict) -> None:
        """Bind run and request to immutable original bytes before starting G02."""
        digest = sha(canonical(request))
        with sqlite3.connect(str(self.db_path), timeout=8) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""CREATE TABLE IF NOT EXISTS h02_request_bindings(
                run_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                request_sha256 TEXT NOT NULL, tenant_id TEXT NOT NULL,
                principal_id TEXT NOT NULL, task_id TEXT NOT NULL)""")
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT request_id,request_sha256,tenant_id,principal_id,task_id "
                               "FROM h02_request_bindings WHERE run_id=? OR request_id=?",
                               (request["run_id"], request["request_id"])).fetchone()
            if prior:
                require(prior == (request["request_id"], digest, request["tenant_id"],
                                  request["principal_id"], request["task_id"]),
                        "REPLAY_OR_DUPLICATE_REQUEST_MISMATCH")
            else:
                db.execute("INSERT INTO h02_request_bindings VALUES (?,?,?,?,?,?)",
                           (request["run_id"], request["request_id"], digest,
                            request["tenant_id"], request["principal_id"],
                            request["task_id"]))
            db.commit()

    def check_independently(self, request: dict) -> dict:
        cmd = [sys.executable, str(self.independent_checker), "--db", str(self.db_path),
               "--contract", str(self.contract_path), "--sources", str(self.registry_path),
               "--out", str(self.outcome_dir), "--run-id", request["run_id"]]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
        require(done.returncode == 0, "INDEPENDENT_READBACK_REJECTED")
        try:
            evidence = json.loads(done.stdout)
        except ValueError as exc:
            raise AdmissionDenied("INDEPENDENT_READER_MALFORMED") from exc
        require(evidence.get("verdict") == "INDEPENDENT_LOCAL_RESEARCH_BYTES_AND_CITATIONS_PASS" and
                evidence.get("verified_live_citations") == 4 and
                evidence.get("tenant_id") == request["tenant_id"] and
                evidence.get("principal_id") == request["principal_id"] and
                evidence.get("run_id") == request["run_id"],
                "INDEPENDENT_EVIDENCE_MISMATCH")
        return evidence

    def dispatch(self, request: dict, *, pause_at: str = "") -> dict:
        contract = self.validate_request(request)
        self.bind_request(request)
        result = execute(self.db_path, self.contract_path, self.registry_path,
                         self.outcome_dir, request["run_id"], pause=pause_at)
        independent = self.check_independently(request)
        require(independent["markdown_sha256"] == result["markdown_sha256"] and
                independent["json_sha256"] == result["json_sha256"] and
                independent["journal_head_sha256"] == result["journal_head"] and
                result["events"] == 4, "PERSISTED_RESULT_DRIFT")
        receipt_file = self.outcome_dir / (request["run_id"] + ".h02-receipt.json")
        if receipt_file.exists():
            prior = load_json(receipt_file)
            require(prior["receipt"]["run_id"] == request["run_id"] and
                    prior["markdown_sha256"] == result["markdown_sha256"] and
                    prior["json_sha256"] == result["json_sha256"] and
                    prior["journal_head_sha256"] == result["journal_head"],
                    "RECEIPT_REPLAY_DRIFT")
            receipt = prior["receipt"]
        else:
            stamp = utc_stamp()
            receipt = {
                "schema_version": "1.0.0", "tenant_id": request["tenant_id"],
                "outcome_id": request["outcome_id"], "run_id": request["run_id"],
                "artifact_refs": ["local-nonprod:sha256:" + result["markdown_sha256"],
                                  "local-nonprod:sha256:" + result["json_sha256"]],
                "verification_result_ids": ["local-source-lines:4:" + result["journal_head"]],
                "fulfilled": True, "observed_at": stamp, "created_at": stamp,
                "supersedes_receipt_id": None,
            }
            outcome_receipt(receipt)
            fsync_write(receipt_file, canonical({
                "receipt": receipt, "markdown_sha256": result["markdown_sha256"],
                "json_sha256": result["json_sha256"],
                "journal_head_sha256": result["journal_head"]}) + b"\n")
        outcome_receipt(receipt)
        return {
            "scope": "NONPROD_OWNER_FIRST_PARTY_LOCAL_RESEARCH_ONLY",
            "request_id": request["request_id"], "run_id": request["run_id"],
            "task_id": contract["task_id"], "tenant_id": request["tenant_id"],
            "principal_id": request["principal_id"], "admission": "NATIVE_TASK_V1_ACCEPTED",
            "state": "DURABLE_SOURCE_BACKED_RESEARCH_READBACK_PASS",
            "markdown_sha256": result["markdown_sha256"],
            "json_sha256": result["json_sha256"],
            "journal_head_sha256": result["journal_head"],
            "citations": independent["verified_live_citations"],
            "receipt_sha256": sha(receipt_file.read_bytes()),
            "receipt_path": str(receipt_file),
            "markdown_path": result["markdown"], "json_path": result["json"],
            "formal_product_qualified": False,
        }


def serve(bridge: ResearchBridge, *, port: int, once: bool, pause_at: str) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/nonprod/h02/research":
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                require(0 < size <= 8192, "BODY_SIZE_DENIED")
                body = json.loads(self.rfile.read(size))
                response = bridge.dispatch(body, pause_at=pause_at)
                status = 200
            except (AdmissionDenied, ResearchDenied, ValueError, sqlite3.DatabaseError,
                    TimeoutError, subprocess.TimeoutExpired, OSError, KeyError) as exc:
                status = 403
                response = {"state": "SAFE_DENIAL", "reason": str(exc)[:180]}
            data = canonical(response)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            return  # neither payloads nor process secrets in logs

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"ready": True, "listen": "127.0.0.1",
                      "port": server.server_address[1], "scope": "nonprod-loopback"}),
          flush=True)
    try:
        server.handle_request() if once else server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    for flag in ("contract", "sources", "db", "out", "checker", "tenant", "principal"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--pause-at", choices=("", "AFTER_STEP_1", "AFTER_FINALIZATION"),
                        default="")
    args = parser.parse_args()
    bridge = ResearchBridge(contract_path=Path(args.contract),
                            registry_path=Path(args.sources), db_path=Path(args.db),
                            outcome_dir=Path(args.out), independent_checker=Path(args.checker),
                            tenant_id=args.tenant, principal_id=args.principal)
    serve(bridge, port=args.port, once=args.once, pause_at=args.pause_at)


if __name__ == "__main__":
    main()
