"""C1 isolated bootable Native candidate adapter. NEVER a signed Product or live LLM.

Adds OS-loopback client capability, exact Git/source version admission and
TaskContract/source-rights verified H02 execution. Generated model route denies
until a genuinely independent Provider/IdP/semantic qualification exists.
Does not modify Q34/D01, shared API, legacy source or prior F02/G01 adapters.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import subprocess
import time
import socket
import socketserver
from contextlib import contextmanager
import m27_c1_gitless_source_proof as gitless

import m27_h02_native_nonprod_consumer as h02
import m27_f02_current_native_model_events as f02
import m27_g01_current_native_consumer as g01
import m27_task_contracts_v1 as contract
import m27_c1_genuine_native_generation_seam as native_live

ABI = "m27.c1.native-app-source-client-candidate/v1"
STATUS_PATH = "/nonprod/c1/status"
SOURCE_PATH = "/nonprod/c1/task"
ACK_PATH = "/nonprod/c1/ack"
TERMINAL_PATH = "/nonprod/c1/terminal"
MODEL_PATH = "/nonprod/c1/model-generation"
LIVE_PREPARE = MODEL_PATH + "/prepare"
LIVE_VERIFY = MODEL_PATH + "/verified-claim"
LIVE_ACK = MODEL_PATH + "/ack"
LIVE_TERMINAL = MODEL_PATH + "/terminal"
LIVE_CANCEL = MODEL_PATH + "/cancel"
LIVE_ROUTES = (LIVE_PREPARE, MODEL_PATH, LIVE_VERIFY, LIVE_ACK,
               LIVE_TERMINAL, LIVE_CANCEL)
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


def source_vector(repo: Path, *, expected_head: str, expected_tree: str,
                  signed_gitless_manifest: Path | None = None,
                  gitless_public_root: Path | None = None) -> dict:
    """Exact commit and tree; dirty tracked/untracked source is NOT boot-eligible."""
    repo = Path(repo).resolve(strict=True)
    check(len(expected_head) == 40 and len(expected_tree) == 40,
          "UNPINNED_SOURCE_VECTOR")
    if not (repo / ".git").exists():
        check(signed_gitless_manifest is not None
              and gitless_public_root is not None,
              "GITLESS_SIGNED_SOURCE_MANIFEST_REQUIRED")
        check(gitless.is_hex(gitless.C1_GITLESS_TRUST_ROOT_SHA256,64),
              "GITLESS_EXTERNAL_SOURCE_SIGNER_NOT_ADMITTED")
        # Reject before ANY manifest file read without a true external root.
        raw = Path(signed_gitless_manifest).read_bytes()
        check(len(raw) <= 250000, "GITLESS_MANIFEST_OVERSIZED")
        attestation = gitless.verify_signed_gitless_bundle(
            repo, json.loads(raw), expected_head=expected_head,
            expected_tree=expected_tree, public_key_path=gitless_public_root)
        check(attestation["signed_source_admitted"] is True,
              "GITLESS_SOURCE_NOT_INDEPENDENTLY_ATTESTED")
        head, tree = expected_head, expected_tree
        parent = None  # Future signed manifest must bind a parent if required.
    else:
        head, tree = git_field(repo, "HEAD"), git_field(repo, "HEAD^{tree}")
        check(head == expected_head and tree == expected_tree,
              "SOURCE_VERSION_MISMATCH")
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                                 "--untracked-files=all"],
                                capture_output=True, text=True, check=True, timeout=15)
        check(not status.stdout.strip(), "DIRTY_CURRENT_SOURCE_NOT_FROZEN")
        parent = git_field(repo, "HEAD^")
    task = h02.local_task("PolicyEngine", "os-uid:" + str(os.geteuid()))
    return {
        "abi": ABI, "head": head, "tree": tree,
        "parent": parent,
        # Actual instance SHA exists only when H02 admits that particular task.
        # Pre-boot timestamp snapshot was NOT an ABI freeze and caused 403s.
        "task_contract_sha256": None,
        "task_contract_sha256_kind": "PER_ADMITTED_SESSION_ONLY",
        "task_contract_template_sha256": contract_template_sha256(task),
        "task_contract_schema": task.get("schema_version", "task-contract-v1"),
        "h02_abi": h02.ABI, "f02_abi": f02.ABI, "g01_abi": g01.ABI,
        "source_manifest_sha256": h02.f03.A05_SOURCE_PIN,
        "source_release_id": h02.f03.A05_RELEASE_ID,
        "source_revision": h02.f03.A05_REVISION,
        "source_rights": "OS_LOCAL_FIRSTPARTY_CANDIDATE_ONLY",
        "gitless_proof_abi": gitless.ABI,
        "gitless_source_signer": (
            "NOT_ADMITTED" if gitless.C1_GITLESS_TRUST_ROOT_SHA256 is None
            else "EXTERNALLY_PINNED_CHECK_SEPARATE_SIGNER_RECEIPT"),
        "gitless_f03_blob_reader": "READONLY_AUTHORIZED_GIT_OBJECT_MOUNT_NOT_QUALIFIED",
        "native_same_namespace_ingress": "UNIX_KERNEL_PEER_UID_PLUS_LOCAL_0600_BEARER",
        "client_identity": "OS_UNIX_OR_LOOPBACK_CAPABILITY_NOT_REMOTE_IDP",
        "independent_product_client_idp": "NOT_QUALIFIED",
        "semantic_verification": "INDEPENDENT_ISSUER_NOT_QUALIFIED",
        "generation": "NOT_RUN", "model_route": "UNQUALIFIED_NO_CALL",
        "provider_primary": "CLOUDFLARE_CUSTOM_WORKER_REFUSED_PROBE_NOT_RETRIED",
        "provider_fallback": "MINIMAX_DIAGNOSTIC_NOT_RUN",
        "cache": CACHE, "current_signed_image": None, "product_pass": False,
    }


def contract_template_sha256(task: dict) -> str:
    """Time-independent, exact contract policy profile, never a run's Task SHA.

    The three removed UTC fields remain mandatory and independently validated
    by the original H02/TaskContract admission on EACH new task. No auth TTL is
    enlarged or skipped by this cross-request pin.
    """
    normalized = copy.deepcopy(task)
    normalized.pop("created_at")
    normalized.pop("deadline_at")
    normalized["actor"].pop("auth_expires_at")
    return hashlib.sha256(contract.canonical({
        "schema": "m27.c1.task-template/v1",
        "contract_without_per_run_utc_timestamps": normalized,
    })).hexdigest()


def current_task_template(principal: str) -> str:
    live = h02.local_task("PolicyEngine", principal)
    return contract_template_sha256(live)


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
                 token_file: Path, expected_head: str, expected_tree: str,
                 signed_gitless_manifest: Path | None = None,
                 gitless_public_root: Path | None = None):
        self.version = source_vector(
            repo, expected_head=expected_head, expected_tree=expected_tree,
            signed_gitless_manifest=signed_gitless_manifest,
            gitless_public_root=gitless_public_root)
        self.token = read_client_capability(token_file)
        self.reader = h02.Consumer(repo=repo, fence=fence, journal=journal)
        self.native_live = native_live.NativeLiveProduct(
            repo=repo, fence=fence, journal=Path(str(journal) + ".native-live.jsonl"))
        self.contract_instances: dict[str, dict] = {}
        check(self.reader.recovery in ("EMPTY", "PREVIOUS_TERMINAL_NO_REPLAY"),
              "INCOMPLETE_PREVIOUS_TASK_NO_REPLAY")

    def begin(self, data: dict) -> dict:
        check(type(data) is dict and set(data) == {"question", "tenant"},
              "TASK_CONTRACT_FIELDS_DENIED")
        check(data["question"] == "PolicyEngine"
              and data["tenant"] == "owner-internal", "TASK_TENANT_OR_SCOPE_DENIED")
        # The upstream H02 contract has created_at/deadline_at/auth_expires_at
        # created per task with second-resolution UTC; comparing its SHA with a
        # boot-time instance nondeterministically denied valid clients.
        check(current_task_template(self.reader.principal) ==
              self.version["task_contract_template_sha256"],
              "TASK_TEMPLATE_POLICY_DRIFT")
        receipt = self.reader.start(data["question"], tenant=data["tenant"])
        sid = receipt["session_id"]
        admitted = self.reader.entries.get(sid)
        check(type(admitted) is dict and
              type(receipt["task_sha256"]) is str and
              re.fullmatch("[0-9a-f]{64}", receipt["task_sha256"]) is not None and
              admitted["task_sha"] == receipt["task_sha256"],
              "ACTUAL_TASKCONTRACT_NOT_JOURNALED")
        check(receipt["source_manifest_sha256"] ==
              self.version["source_manifest_sha256"] and
              receipt["source_release_id"] == self.version["source_release_id"] and
              receipt["source_version"] == self.version["source_revision"] and
              admitted["epoch"] == receipt["rights_epoch"],
              "SOURCE_MANIFEST_OR_RIGHTS_DRIFT")
        self.contract_instances[sid] = {
            "task_sha256": receipt["task_sha256"],
            "source_manifest_sha256": receipt["source_manifest_sha256"],
            "rights_epoch": receipt["rights_epoch"],
        }
        return {**receipt, "candidate_abi": ABI,
                "task_contract_template_sha256":
                    self.version["task_contract_template_sha256"],
                "pinned_task_contract_sha256": receipt["task_sha256"],
                "client_authentication": "LOCAL_CAPABILITY_NOT_IDP",
                "generated_answer": False, "product_pass": False}

    def _require_pinned_task(self, sid: str) -> None:
        pin = self.contract_instances.get(sid)
        entry = self.reader.entries.get(sid)
        check(type(pin) is dict and type(entry) is dict and
              pin["task_sha256"] == entry["task_sha"] and
              pin["rights_epoch"] == entry["epoch"] and
              pin["source_manifest_sha256"] ==
              self.version["source_manifest_sha256"],
              "ADMITTED_TASK_OR_RIGHTS_PIN_INVALID")

    def ack(self, data: dict) -> dict:
        check(type(data) is dict and set(data) ==
              {"session_id", "claim_id", "challenge", "text_sha256"},
              "ACK_CONTRACT_FIELDS_DENIED")
        self._require_pinned_task(data["session_id"])
        return self.reader.ack(**{
            "sid": data["session_id"], "claim_id": data["claim_id"],
            "challenge": data["challenge"], "text_sha256": data["text_sha256"]})

    def terminal(self, data: dict) -> dict:
        check(type(data) is dict and set(data) == {"session_id"},
              "TERMINAL_CONTRACT_FIELDS_DENIED")
        self._require_pinned_task(data["session_id"])
        result = self.reader.terminal(data["session_id"])
        self.contract_instances.pop(data["session_id"], None)
        return result


class ThreadedC1UnixHTTPServer(socketserver.ThreadingMixIn,
                               socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False


def native_unix_peer_uid(connection) -> int | None:
    """Kernel peer identity, never a caller-provided header."""
    try:
        if hasattr(connection, "getpeereid"):
            return connection.getpeereid()[0]
        if hasattr(socket, "SO_PEERCRED"):
            raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                        struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", raw)
            return uid
        if hasattr(socket, "LOCAL_PEERCRED") and os.uname().sysname == "Darwin":
            # Darwin kernel XUCRED: version=u32(0), cr_uid=u32 at offset 4.
            # SOL_LOCAL is 0 on Darwin and is absent from some Python builds.
            raw = connection.getsockopt(getattr(socket, "SOL_LOCAL", 0),
                                        socket.LOCAL_PEERCRED, 128)
            if len(raw) >= 12 and struct.unpack_from("=I", raw, 0)[0] == 0:
                return struct.unpack_from("=I", raw, 4)[0]
    except (OSError, AttributeError, struct.error):
        return None
    return None


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
        if isinstance(self.server, ThreadedC1UnixHTTPServer):
            # Same native OS namespace, kernel-enforced UID plus 0600 bearer.
            # This is strictly LOCAL identity, NOT an independent Product IdP.
            net_ok = (host == "c1-unix.local" and
                      native_unix_peer_uid(self.connection) == os.geteuid())
        else:
            net_ok = (self.client_address[0] == "127.0.0.1" and
                      host in ("127.0.0.1",
                               "127.0.0.1:" + str(self.server.server_port)))
        return (net_ok and hmac.compare_digest(
            self.headers.get("X-C1-Local-Capability", "").encode(),
            self.candidate.token))

    def do_GET(self):
        if not self.authorized():
            return self.reply({"status": "CLIENT_AUTH_DENIED"}, 403)
        if self.path == STATUS_PATH:
            return self.reply({"status": "BOOTED_SOURCE_CLIENT_CANDIDATE_NOT_PRODUCT",
                               "version": self.candidate.version,
                               "cache": CACHE, "provider_called": False,
                               "native_live": self.candidate.native_live.admission_status()})
        self.reply({"status": "UNKNOWN_ROUTE"}, 404)

    def do_POST(self):
        if not self.authorized():
            return self.reply({"status": "CLIENT_AUTH_DENIED"}, 403)
        if self.path in LIVE_ROUTES:
            try:
                size = int(self.headers.get("Content-Length", "-1"))
                check(0 < size <= MAX_BODY, "REQUEST_BODY_TOO_LARGE")
                data = json.loads(self.rfile.read(size))
                live = self.candidate.native_live
                if self.path == LIVE_PREPARE:
                    result = live.prepare(data)
                elif self.path == MODEL_PATH:
                    result = live.start(data)
                elif self.path == LIVE_VERIFY:
                    result = live.verify_claim(data)
                elif self.path == LIVE_ACK:
                    result = live.ack(data)
                elif self.path == LIVE_TERMINAL:
                    result = live.terminal(data)
                else:
                    result = live.cancel(data)
                return self.reply(result, 200)
            except (native_live.NotQualified, AdmissionDenied) as exc:
                reason = str(exc)
                safe_code = (len(reason) <= 120 and
                             re.fullmatch(r"[A-Z0-9_]+", reason) is not None)
                return self.reply({
                    "status": reason if safe_code else "LIVE_AUTHORITY_NOT_QUALIFIED",
                    "provider_called": False, "fallback_called": False,
                    "product_pass": False, "cache": "OFF"}, 403)
            except (ValueError, TypeError, KeyError, UnicodeError):
                return self.reply({"status": "BAD_NATIVE_REQUEST",
                                   "provider_called": False,
                                   "product_pass": False}, 403)
            except Exception:
                return self.reply({"status": "NATIVE_UNKNOWN_FAIL_CLOSED",
                                   "product_pass": False}, 503)
        if self.path not in (SOURCE_PATH, ACK_PATH, TERMINAL_PATH):
            return self.reply({"status": "UNKNOWN_ROUTE"}, 404)
        started_ns = time.monotonic_ns()
        local_request_id = secrets.token_hex(8)
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
            self.reply({**response, "local_request_id": local_request_id,
                        "listener_pid": os.getpid(),
                        "duration_ms": (time.monotonic_ns() - started_ns) // 1000000})
        except (AdmissionDenied, h02.Denied, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, AdmissionDenied):
                reason = str(exc)
            elif isinstance(exc, h02.Denied):
                # Only a bounded code-like token; never raw source text, headers,
                # rights artifacts, transport exception or bearer capability.
                word = str(exc)
                reason = (word if len(word) <= 110 and
                          re.fullmatch(r"[A-Z0-9_]{3,110}", word)
                          else "UPSTREAM_SOURCE_RIGHTS_DENIED")
            else:
                reason = "INVALID_REQUEST_SHAPE"
            self.reply({"status": (str(exc) if isinstance(exc, AdmissionDenied)
                                   else "INVALID_OR_UNQUALIFIED_REQUEST"),
                        "nonsecret_denial_code": reason,
                        "local_request_id": local_request_id,
                        "listener_pid": os.getpid(),
                        "duration_ms": (time.monotonic_ns() - started_ns) // 1000000,
                        "product_pass": False}, 403)
        except Exception:
            self.reply({"status": "INTERNAL_FAIL_CLOSED",
                        "nonsecret_denial_code": "UNEXPECTED_RUNTIME_FAILURE",
                        "local_request_id": local_request_id,
                        "listener_pid": os.getpid(),
                        "duration_ms": (time.monotonic_ns() - started_ns) // 1000000,
                        "product_pass": False}, 503)


def serve(*, repo: Path, fence: Path, journal: Path, token_file: Path,
          expected_head: str, expected_tree: str, port: int, ready_file: Path,
          unix_socket: Path | None = None,
          signed_gitless_manifest: Path | None = None,
          gitless_public_root: Path | None = None):
    candidate = Candidate(
        repo=repo, fence=fence, journal=journal,
        token_file=token_file, expected_head=expected_head,
        expected_tree=expected_tree,
        signed_gitless_manifest=signed_gitless_manifest,
        gitless_public_root=gitless_public_root)
    class NativeHandler(Handler):
        pass
    NativeHandler.candidate = candidate
    if unix_socket is not None:
        unix_socket = Path(unix_socket)
        parent = unix_socket.parent
        pstat = parent.lstat()
        check(stat.S_ISDIR(pstat.st_mode) and not parent.is_symlink()
              and stat.S_IMODE(pstat.st_mode) == 0o700
              and pstat.st_uid == os.geteuid()
              and not unix_socket.exists() and not unix_socket.is_symlink(),
              "UNIX_SOCKET_PARENT_OR_PREEXISTING_PATH_DENIED")
        previous_umask = os.umask(0o177)
        try:
            server = ThreadedC1UnixHTTPServer(str(unix_socket), NativeHandler)
        finally:
            os.umask(previous_umask)
        check(stat.S_IMODE(unix_socket.lstat().st_mode) == 0o600,
              "UNIX_SOCKET_FILE_PERMISSIONS_DENIED")
        endpoint = {"unix_socket": str(unix_socket),
                    "peer_identity": "KERNEL_SAME_UID_LOCAL_ONLY_NOT_IDP"}
    else:
        server = ThreadingHTTPServer(("127.0.0.1", port), NativeHandler)
        endpoint = {"port": server.server_port,
                    "peer_identity": "OS_LOOPBACK_CAPABILITY_NOT_IDP"}
    try:
        ready_file.write_text(json.dumps({
            **endpoint, "pid": os.getpid(), "source_head": expected_head,
            "abi": ABI, "product_admitted": False, "cache": "OFF"}))
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        if unix_socket is not None and unix_socket.is_socket():
            unix_socket.unlink()


def main():
    parser = argparse.ArgumentParser()
    for arg in ("repo", "fence", "journal", "token-file", "expected-head",
                "expected-tree", "ready-file"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--unix-socket")
    parser.add_argument("--signed-gitless-manifest")
    parser.add_argument("--gitless-public-root")
    args = parser.parse_args()
    serve(repo=Path(args.repo), fence=Path(args.fence), journal=Path(args.journal),
          token_file=Path(args.token_file), expected_head=args.expected_head,
          expected_tree=args.expected_tree, port=args.port,
          ready_file=Path(args.ready_file),
          unix_socket=Path(args.unix_socket) if args.unix_socket else None,
          signed_gitless_manifest=Path(args.signed_gitless_manifest)
              if args.signed_gitless_manifest else None,
          gitless_public_root=Path(args.gitless_public_root)
              if args.gitless_public_root else None)


if __name__ == "__main__":
    main()
