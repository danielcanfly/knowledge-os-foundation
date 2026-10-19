"""C1 isolated bootable Native candidate adapter. NEVER a signed Product or live LLM.

Adds OS-loopback client capability, exact Git/source version admission and
TaskContract/source-rights verified H02 execution. Generated model route denies
until a genuinely independent Provider/IdP/semantic qualification exists.
Does not modify Q34/D01, shared API, legacy source or prior F02/G01 adapters.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import subprocess

import m27_h02_native_nonprod_consumer as h02
import m27_f02_current_native_model_events as f02
import m27_g01_current_native_consumer as g01
import m27_task_contracts_v1 as contract

ABI = "m27.c1.native-app-source-client-candidate/v1"
STATUS_PATH = "/nonprod/c1/status"
SOURCE_PATH = "/nonprod/c1/task"
ACK_PATH = "/nonprod/c1/ack"
TERMINAL_PATH = "/nonprod/c1/terminal"
MODEL_PATH = "/nonprod/c1/model-generation"
CACHE = "OFF"
MAX_BODY = 2048


class AdmissionDenied(ValueError):
    pass


def check(ok: bool, code: str) -> None:
    if not ok:
        raise AdmissionDenied(code)


def git_field(repo: Path, key: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", key],
                            capture_output=True, text=True, check=True, timeout=5)
    return result.stdout.strip()


def source_vector(repo: Path, *, expected_head: str, expected_tree: str) -> dict:
    """Exact commit and tree; dirty tracked/untracked source is NOT boot-eligible."""
    repo = Path(repo).resolve(strict=True)
    check(len(expected_head) == 40 and len(expected_tree) == 40,
          "UNPINNED_SOURCE_VECTOR")
    head, tree = git_field(repo, "HEAD"), git_field(repo, "HEAD^{tree}")
    check(head == expected_head and tree == expected_tree, "SOURCE_VERSION_MISMATCH")
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                             "--untracked-files=all"],
                            capture_output=True, text=True, check=True, timeout=15)
    # Runtime may only run from a clean exact checkout; journal must be OUTSIDE it.
    check(not status.stdout.strip(), "DIRTY_CURRENT_SOURCE_NOT_FROZEN")
    task = h02.local_task("PolicyEngine", "os-uid:" + str(os.geteuid()))
    return {
        "abi": ABI, "head": head, "tree": tree,
        "parent": git_field(repo, "HEAD^"),
        "task_contract_sha256": contract.sha256(task),
        "task_contract_schema": task.get("schema_version", "task-contract-v1"),
        "h02_abi": h02.ABI, "f02_abi": f02.ABI, "g01_abi": g01.ABI,
        "source_manifest_sha256": h02.f03.A05_SOURCE_PIN,
        "source_release_id": h02.f03.A05_RELEASE_ID,
        "source_revision": h02.f03.A05_REVISION,
        "source_rights": "OS_LOCAL_FIRSTPARTY_CANDIDATE_ONLY",
        "client_identity": "OS_LOOPBACK_CAPABILITY_NOT_REMOTE_IDP",
        "semantic_verification": "INDEPENDENT_ISSUER_NOT_QUALIFIED",
        "generation": "NOT_RUN", "model_route": "UNQUALIFIED_NO_CALL",
        "provider_primary": "CLOUDFLARE_CUSTOM_WORKER_REFUSED_PROBE_NOT_RETRIED",
        "provider_fallback": "MINIMAX_DIAGNOSTIC_NOT_RUN",
        "cache": CACHE, "current_signed_image": None, "product_pass": False,
    }


def read_client_capability(path: Path) -> bytes:
    """Local application bearer file only, not cryptographic Product IdP."""
    path = Path(path)
    info = path.lstat()
    check(stat.S_ISREG(info.st_mode) and not path.is_symlink()
          and stat.S_IMODE(info.st_mode) == 0o600
          and info.st_uid == os.geteuid(), "CLIENT_TOKEN_FILE_AUTHORITY_DENIED")
    raw = path.read_bytes()
    check(32 <= len(raw) <= 256 and b"\n" not in raw
          and raw.strip() == raw, "CLIENT_TOKEN_INVALID")
    return raw


class Candidate:
    def __init__(self, *, repo: Path, fence: Path, journal: Path,
                 token_file: Path, expected_head: str, expected_tree: str):
        self.version = source_vector(repo, expected_head=expected_head,
                                     expected_tree=expected_tree)
        self.token = read_client_capability(token_file)
        self.reader = h02.Consumer(repo=repo, fence=fence, journal=journal)
        check(self.reader.recovery in ("EMPTY", "PREVIOUS_TERMINAL_NO_REPLAY"),
              "INCOMPLETE_PREVIOUS_TASK_NO_REPLAY")

    def begin(self, data: dict) -> dict:
        check(type(data) is dict and set(data) == {"question", "tenant"},
              "TASK_CONTRACT_FIELDS_DENIED")
        check(data["question"] == "PolicyEngine"
              and data["tenant"] == "owner-internal", "TASK_TENANT_OR_SCOPE_DENIED")
        receipt = self.reader.start(data["question"], tenant=data["tenant"])
        check(receipt["task_sha256"] == self.version["task_contract_sha256"],
              "TASKCONTRACT_VERSION_DRIFT")
        check(receipt["source_manifest_sha256"] ==
              self.version["source_manifest_sha256"], "SOURCE_MANIFEST_DRIFT")
        return {**receipt, "candidate_abi": ABI,
                "client_authentication": "LOCAL_CAPABILITY_NOT_IDP",
                "generated_answer": False, "product_pass": False}

    def ack(self, data: dict) -> dict:
        check(type(data) is dict and set(data) ==
              {"session_id", "claim_id", "challenge", "text_sha256"},
              "ACK_CONTRACT_FIELDS_DENIED")
        return self.reader.ack(**{
            "sid": data["session_id"], "claim_id": data["claim_id"],
            "challenge": data["challenge"], "text_sha256": data["text_sha256"]})

    def terminal(self, data: dict) -> dict:
        check(type(data) is dict and set(data) == {"session_id"},
              "TERMINAL_CONTRACT_FIELDS_DENIED")
        return self.reader.terminal(data["session_id"])


class Handler(BaseHTTPRequestHandler):
    candidate: Candidate

    def log_message(self, *_):
        pass

    def reply(self, obj: dict, status: int = 200):
        raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self) -> bool:
        host = self.headers.get("Host", "")
        return (self.client_address[0] == "127.0.0.1"
                and host in ("127.0.0.1", "127.0.0.1:" + str(self.server.server_port))
                and hmac.compare_digest(
                    self.headers.get("X-C1-Local-Capability", "").encode(),
                    self.candidate.token))

    def do_GET(self):
        if not self.authorized():
            return self.reply({"status": "CLIENT_AUTH_DENIED"}, 403)
        if self.path == STATUS_PATH:
            return self.reply({"status": "BOOTED_SOURCE_CLIENT_CANDIDATE_NOT_PRODUCT",
                               "version": self.candidate.version,
                               "cache": CACHE, "provider_called": False})
        self.reply({"status": "UNKNOWN_ROUTE"}, 404)

    def do_POST(self):
        if not self.authorized():
            return self.reply({"status": "CLIENT_AUTH_DENIED"}, 403)
        if self.path == MODEL_PATH:
            return self.reply({"status": "LIVE_NATIVE_PROVIDER_AND_ISSUER_NOT_QUALIFIED",
                               "provider_called": False, "fallback_called": False,
                               "product_pass": False}, 403)
        if self.path not in (SOURCE_PATH, ACK_PATH, TERMINAL_PATH):
            return self.reply({"status": "UNKNOWN_ROUTE"}, 404)
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            check(0 < size <= MAX_BODY, "REQUEST_BODY_TOO_LARGE")
            data = json.loads(self.rfile.read(size))
            if self.path == SOURCE_PATH:
                response = self.candidate.begin(data)
            elif self.path == ACK_PATH:
                response = self.candidate.ack(data)
            else:
                response = self.candidate.terminal(data)
            self.reply(response)
        except (AdmissionDenied, h02.Denied, ValueError, TypeError, KeyError) as exc:
            self.reply({"status": str(exc) if isinstance(exc, AdmissionDenied)
                        else "INVALID_OR_UNQUALIFIED_REQUEST",
                        "product_pass": False}, 403)
        except Exception:
            self.reply({"status": "INTERNAL_FAIL_CLOSED", "product_pass": False}, 503)


def serve(*, repo: Path, fence: Path, journal: Path, token_file: Path,
          expected_head: str, expected_tree: str, port: int, ready_file: Path):
    candidate = Candidate(repo=repo, fence=fence, journal=journal,
                          token_file=token_file, expected_head=expected_head,
                          expected_tree=expected_tree)
    class NativeHandler(Handler):
        pass
    NativeHandler.candidate = candidate
    server = ThreadingHTTPServer(("127.0.0.1", port), NativeHandler)
    try:
        ready_file.write_text(json.dumps({"port": server.server_port,
            "pid": os.getpid(), "source_head": expected_head,
            "abi": ABI, "product_admitted": False}))
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    for arg in ("repo", "fence", "journal", "token-file", "expected-head",
                "expected-tree", "ready-file"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    serve(repo=Path(args.repo), fence=Path(args.fence), journal=Path(args.journal),
          token_file=Path(args.token_file), expected_head=args.expected_head,
          expected_tree=args.expected_tree, port=args.port,
          ready_file=Path(args.ready_file))


if __name__ == "__main__":
    main()
