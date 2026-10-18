"""H02-owned isolated A05 first-party source consumer.

SOURCE CANDIDATE ONLY. There is no model generation, Product answer route,
IdP, qualified independent semantic issuer, third-party rights or live Gateway.
This loopback nonprod app never changes Q34, native Product API, or cache.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time

if __package__:
    from . import m27_f03_source_rights_admission as f03
    from . import m27_g01_qa_outcome as g01
    from . import m27_task_contracts_v1 as tc
else:
    import m27_f03_source_rights_admission as f03
    import m27_g01_qa_outcome as g01
    import m27_task_contracts_v1 as tc

ABI = "m27.h02.native-a05-source-consumer/nonprod.v1"
PRODUCT = "PRODUCT_NOT_ADMITTED"
PROVIDER = "NOT_RUN"
CACHE = "OFF"
ROUTE = "/nonprod/h02-native/source-candidate"
ACK = "/nonprod/h02-native/ack"
CANCEL = "/nonprod/h02-native/cancel"
TERMINAL = "/nonprod/h02-native/terminal"
STATUS = "/nonprod/h02-native/status"
MAX_BODY = 3072
MAX_EXCERPT = 512


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Denied(ValueError):
    pass


def guard(condition: bool, code: str) -> None:
    if not condition:
        raise Denied(code)


def shape(permit: dict, names: set[str]) -> None:
    guard(type(permit) is dict and set(permit) == names, "UNEXPECTED_REQUEST_FIELDS")


def fail(code: str) -> dict:
    return {"status": code, "product_status": PRODUCT, "cache": CACHE,
            "provider": PROVIDER, "g03_action_allowed": False,
            "g05_invoice_verified": False, "actual_savings_verified": False,
            "fallback_allowed": False, "scope": ABI}


def local_task(question: str, principal: str) -> dict:
    """Existing TaskContract v1 validation, OS observation is not IdP auth."""
    task = g01.task_contract()
    task["task_id"] = "h02-a05-source-consumer"
    task["tenant_id"] = "owner-internal"
    task["actor"]["principal_id"] = principal
    task["actor"]["auth_context_ref"] = "OS-LOCAL-UNSIGNED-NOT-IDP"
    task["authority"]["policy_ref"] = "h02/a05/owner-local-read-only"
    task["authority"]["policy_version"] = f03.A05_SOURCE_PIN
    task["authority"]["allowed_capability_ids"] = ["source:read-only"]
    task["authority"]["max_side_effect"] = "read"
    task["goal"]["text"] = question
    task["constraints"] = ["Only exact, locally verified A05 source clauses",
                           "Never model-generated or Product answer",
                           "Require client ACK before terminal",
                           "No cache/action/finance/fallback"]
    task["context_scopes"] = [{"provider_kind": "workspace",
                              "scope_id": f03.A05_RELEASE_ID, "access": "read"}]
    task["output_specs"][0]["expected_uri_scope"] = "nonprod/h02/a05-only"
    task["output_specs"][0]["validator_refs"] = ["h02-independent-os-source-byte-verifier"]
    task["definition_of_done"]["predicate_refs"] = [
        "a05_source_sha", "local_rights_epoch", "two_exact_source_clauses",
        "independent_os_byte_verification", "two_preterminal_acks"]
    task["metadata"] = {"h02:a05_source_pin": f03.A05_SOURCE_PIN,
                        "h02:issuer_state": PRODUCT}
    return tc.task_contract(task)


class FsyncJournal:
    """Append-only events; restart will not publish or repeat any effect."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def record(self, event: dict) -> None:
        with self.lock:
            with self.path.open("ab") as fd:
                fd.write(json.dumps(event, sort_keys=True, ensure_ascii=True).encode() + b"\n")
                fd.flush()
                os.fsync(fd.fileno())

    def recover(self) -> str:
        if not self.path.exists():
            return "EMPTY"
        try:
            rows = [json.loads(x) for x in self.path.read_bytes().splitlines()]
            if not all(type(x) is dict and "event" in x for x in rows):
                return "INCOMPLETE_NO_REPLAY"
        except (ValueError, UnicodeError):
            return "INCOMPLETE_NO_REPLAY"
        if not rows:
            return "EMPTY"
        return "PREVIOUS_TERMINAL_NO_REPLAY" if rows[-1]["event"] == "terminal" else "INCOMPLETE_NO_REPLAY"


class Consumer:
    def __init__(self, *, repo: Path, fence: Path, journal: Path,
                 source_root: Path | None = None, isolated_test_copy: bool = False,
                 verifier: Path | None = None):
        self.repo = Path(repo).resolve(strict=True)
        self.reader = f03.A05OwnerCorpusAdmission(
            self.repo, fence=fence, source_root=source_root,
            isolated_test_copy=isolated_test_copy)
        self.verifier = Path(verifier) if verifier else (
            self.repo / "tools/m27_h02_native_source_verifier.py")
        self.journal = FsyncJournal(journal)
        self.recovery = self.journal.recover()
        self.principal = "os-uid:" + str(os.geteuid())
        self.entries: dict[str, dict] = {}
        self.lock = threading.RLock()

    def _source(self, question: str) -> dict:
        result = self.reader.source_retrieval(
            question, tenant="owner-internal", principal=self.principal,
            obligations=["PolicyEngine decides."], ttl_seconds=120)
        guard(result.get("decision") == "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",
              result.get("decision", "SOURCE_READ_DENIED"))
        guard(not result["product_admitted"] and not result["verified_final"]
              and not result["answer_cache_enabled"] and result["candidate_only"],
              "UNTRUSTED_PRODUCT_QUALIFICATION")
        return result

    def _verify(self, text: str, citation: dict) -> dict:
        request = {"source_root": str(self.reader.source_root),
                   "citation": citation, "text": text,
                   "manifest_sha256": f03.A05_SOURCE_PIN}
        proc = subprocess.run([sys.executable, str(self.verifier)],
                              input=json.dumps(request), text=True,
                              capture_output=True, timeout=12, check=False)
        guard(proc.returncode == 0, "INDEPENDENT_OS_VERIFIER_DENIED")
        try:
            result = json.loads(proc.stdout)
        except ValueError as exc:
            raise Denied("INVALID_VERIFIER_RESPONSE") from exc
        guard(result.get("verified") is True and result.get("signed_issuer") is False
              and result.get("excerpt_sha256") == citation["excerpt_sha256"],
              "INDEPENDENT_OS_VERIFIER_DENIED")
        return result

    def _current(self, entry: dict) -> None:
        again = self._source(entry["question"])
        guard(again["revocation_sha256"] == entry["rights_sha"] and
              again["rights_epoch"] == entry["epoch"] and
              again["release_sha256"] == entry["release_sha"] and
              again["sources"] == entry["citations"],
              "SOURCE_REVOKED_STALE_OR_CHANGED")

    def start(self, question: str, *, tenant: str = "owner-internal",
              principal: str | None = None, issuer: str | None = None) -> dict:
        with self.lock:
            guard(issuer is None, "UNKNOWN_ISSUER_PRODUCT_NOT_ADMITTED")
            guard(tenant == "owner-internal" and
                  (principal is None or principal == self.principal),
                  "TENANT_OR_PRINCIPAL_MISMATCH")
            guard(type(question) is str and question == "PolicyEngine",
                  "BOUNDED_QUERY_ONLY")
            task = local_task(question, self.principal)
            data = self._source(question)
            # New positive: two distinct exact source clauses, not generated claims.
            source = next((i for i, excerpt in enumerate(data["candidate_excerpts"])
                           if "Responsible for deterministic enforcement." in excerpt
                           and "PolicyEngine decides." in excerpt), None)
            guard(source is not None, "TWO_CLAUSE_SOURCE_NOT_AVAILABLE")
            cite = data["sources"][source]
            clauses = ("Responsible for deterministic enforcement.",
                       "PolicyEngine decides.")
            candidates = []
            for ordinal, clause in enumerate(clauses, 1):
                guard(len(clause) <= MAX_EXCERPT and clause in data["candidate_excerpts"][source],
                      "UNSUPPORTED_SOURCE_CLAUSE")
                proof = self._verify(clause, cite)
                candidates.append({"claim_id": "a05-clause-" + str(ordinal),
                                   "kind": "source_candidate_not_answer",
                                   "text": clause, "citation": cite,
                                   "text_sha256": digest(clause.encode()),
                                   "proof_sha256": digest(json.dumps(proof, sort_keys=True).encode()),
                                   "challenge": secrets.token_hex(24),
                                   "model_generated": False})
            sid = secrets.token_hex(24)
            entry = {"question": question, "task_sha": tc.sha256(task),
                     "citations": data["sources"], "epoch": data["rights_epoch"],
                     "rights_sha": data["revocation_sha256"],
                     "release_sha": data["release_sha256"],
                     "claims": candidates, "acked": set(), "state": "AWAITING_ACK"}
            self._current(entry)
            self.entries[sid] = entry
            self.journal.record({"event": "source_candidate_sent", "sid": sid,
                                 "source_manifest_sha256": f03.A05_SOURCE_PIN,
                                 "source_release": f03.A05_RELEASE_ID,
                                 "task_sha256": entry["task_sha"], "model_generated": False,
                                 "process_verified": True, "when_ns": time.monotonic_ns()})
            return {**fail("LOCAL_FIRSTPARTY_SOURCE_CANDIDATE"),
                    "session_id": sid, "task_sha256": entry["task_sha"],
                    "source_manifest_sha256": f03.A05_SOURCE_PIN,
                    "source_version": f03.A05_REVISION,
                    "source_release_id": f03.A05_RELEASE_ID,
                    "rights_epoch": entry["epoch"], "claims": candidates,
                    "complete_answer": False, "model_generated": False,
                    "independent_os_source_byte_verified": True,
                    "source_mode": data["nonprod_file_mode"]}

    def ack(self, sid: str, claim_id: str, challenge: str, text_sha256: str) -> dict:
        with self.lock:
            entry = self._entry(sid)
            guard(entry["state"] == "AWAITING_ACK", "ACK_AFTER_TERMINAL_OR_CANCEL")
            candidate = next((c for c in entry["claims"] if c["claim_id"] == claim_id), None)
            guard(candidate is not None and claim_id not in entry["acked"],
                  "WRONG_OR_DUPLICATE_CLAIM_ACK")
            guard(type(challenge) is str and type(text_sha256) is str
                  and secrets.compare_digest(challenge, candidate["challenge"])
                  and secrets.compare_digest(text_sha256, candidate["text_sha256"]),
                  "CLIENT_ACK_WRONG_NONCE_OR_DIGEST")
            self._current(entry)
            entry["acked"].add(claim_id)
            self.journal.record({"event": "client_ack", "sid": sid, "claim_id": claim_id,
                                 "when_ns": time.monotonic_ns()})
            return {**fail("LOCAL_CLIENT_ACK_RECEIVED"), "acked": len(entry["acked"])}

    def _entry(self, sid: str) -> dict:
        guard(type(sid) is str and sid in self.entries, "UNKNOWN_SESSION_NO_REPLAY")
        return self.entries[sid]

    def terminal(self, sid: str) -> dict:
        with self.lock:
            entry = self._entry(sid)
            guard(entry["state"] == "AWAITING_ACK", "DUPLICATE_TERMINAL")
            # Revocation is an independent denial even when ACKs are incomplete.
            self._current(entry)
            guard(len(entry["acked"]) == 2, "SECOND_CLAIM_OR_ACK_MISSING")
            entry["state"] = "TERMINATED"
            self.journal.record({"event": "terminal", "sid": sid,
                                 "status": "LOCAL_SOURCE_TWO_CLAUSES_ACKED_NOT_PRODUCT",
                                 "when_ns": time.monotonic_ns()})
            return {**fail("LOCAL_SOURCE_TWO_CLAUSES_ACKED_NOT_PRODUCT"),
                    "obligations_locally_fulfilled": True, "product_pass": False,
                    "model_generated_answer": False}

    def cancel(self, sid: str) -> dict:
        with self.lock:
            entry = self._entry(sid)
            guard(entry["state"] == "AWAITING_ACK", "CANCEL_AFTER_TERMINAL")
            entry["state"] = "CANCELLED"
            self.journal.record({"event": "terminal", "sid": sid,
                                 "status": "CANCELLED_NO_REPLAY",
                                 "when_ns": time.monotonic_ns()})
            return fail("CANCELLED_NO_REPLAY")


class Handler(BaseHTTPRequestHandler):
    """Loopback-only HTTP surface separate from native/Production routes."""
    consumer: Consumer

    def log_message(self, fmt, *args):
        return

    def reply(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == STATUS:
            return self.reply({**fail("LOOPBACK_NONPROD_SOURCE_ONLY"),
                               "recovery": self.consumer.recovery})
        return self.reply(fail("UNKNOWN_ENDPOINT"), 404)

    def do_POST(self):
        try:
            guard(self.path in (ROUTE, ACK, CANCEL, TERMINAL), "UNKNOWN_ENDPOINT")
            length = int(self.headers.get("Content-Length", "-1"))
            guard(0 < length <= MAX_BODY, "REQUEST_BODY_SIZE")
            data = json.loads(self.rfile.read(length))
            guard(type(data) is dict, "INVALID_JSON_OBJECT")
            if self.path == ROUTE:
                shape(data, {"question"})
                result = self.consumer.start(data["question"])
            elif self.path == ACK:
                shape(data, {"session_id", "claim_id", "challenge", "text_sha256"})
                result = self.consumer.ack(data["session_id"], data["claim_id"],
                                           data["challenge"], data["text_sha256"])
            elif self.path == CANCEL:
                shape(data, {"session_id"})
                result = self.consumer.cancel(data["session_id"])
            else:
                shape(data, {"session_id"})
                result = self.consumer.terminal(data["session_id"])
            self.reply(result)
        except (Denied, ValueError, TypeError, KeyError, OSError) as exc:
            self.reply(fail(str(exc) if isinstance(exc, Denied) else "INVALID_REQUEST"), 403)
        except Exception:
            self.reply(fail("UNEXPECTED_FAILURE_CLOSED"), 503)


def serve(*, repo: Path, fence: Path, journal: Path, port: int,
          source_root: Path | None = None, isolated_test_copy: bool = False,
          ready_file: Path | None = None):
    consumer = Consumer(repo=repo, fence=fence, journal=journal,
                        source_root=source_root, isolated_test_copy=isolated_test_copy)
    class AppHandler(Handler):
        pass
    AppHandler.consumer = consumer
    httpd = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    if ready_file is not None:
        ready_file.write_text(json.dumps({"port": httpd.server_port,
                                         "pid": os.getpid(), "status": PRODUCT}))
    try:
        httpd.serve_forever(poll_interval=0.1)
    finally:
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--fence", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file")
    parser.add_argument("--source-root")
    parser.add_argument("--isolated-test-copy", action="store_true")
    args = parser.parse_args()
    serve(repo=Path(args.repo), fence=Path(args.fence), journal=Path(args.journal),
          port=args.port, ready_file=Path(args.ready_file) if args.ready_file else None,
          source_root=Path(args.source_root) if args.source_root else None,
          isolated_test_copy=args.isolated_test_copy)


if __name__ == "__main__":
    main()
