"""G01 current F02-envelope QA outcome consumer, first-party A05 NONPROD only.

This module consumes ONLY SYNTHETIC_FIXTURE events until independent F02 fresh
live receipts and a separately authorized H02 fan-in exist. It never invokes a
provider, authenticates external Product IdP, signs a semantic issuer, or uses
a cache. Exact source spans are read by accepted A05 F03 and OS-verifier.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import types
from urllib.parse import parse_qs, urlsplit

if not __package__ and "knowledge_engine" not in sys.modules:
    p = types.ModuleType("knowledge_engine")
    p.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules["knowledge_engine"] = p
from knowledge_engine import m27_h02_native_nonprod_consumer as h02
from knowledge_engine import m27_task_contracts_v1 as tc

ABI = "m27.nonprod.f02-g01.generated-stream/v1"
SCOPE = "G01_FIRST_PARTY_A05_NONPROD_FIXTURE_ONLY"
QUESTION = ("Which plane includes Verification, and who decides "
            "deterministic policy enforcement?")
OBLIGATIONS = (
    ("execution_governance_verification", "Execution Governance Verification",
     "Verification", "00_m27_architecture_overview.md"),
    ("policy_engine_enforcement", "PolicyEngine", "PolicyEngine decides.",
     "01_contracts.md"),
)
ACCEPTED_TEXT = (
    re.compile(r"^Verification (?:belongs to|is in) the Execution & Governance Plane\.$"),
    re.compile(r"^PolicyEngine decides deterministic enforcement\.$"),
)
EVENT_KINDS = frozenset({"provider_start", "provider_delta", "claim_proposed",
                         "provider_done", "provider_error"})
ROUTE = "/nonprod/g01-current/start"
EVENT = "/nonprod/g01-current/event"
NEXT = "/nonprod/g01-current/next"
ACK = "/nonprod/g01-current/ack"
TERMINAL = "/nonprod/g01-current/terminal"
CANCEL = "/nonprod/g01-current/cancel"
STATUS = "/nonprod/g01-current/status"
MAX_BODY = 4096


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(test, code):
    if not test:
        raise h02.Denied(code)


def result(status, **fields):
    return {"status": status, "abi": ABI, "scope": SCOPE, "cache": "OFF",
            "product_pass": False, "product_authenticated": False,
            "semantic_issuer_qualified": False, "fresh_generated_provenance": False,
            "model_origin_class": "SYNTHETIC_FIXTURE",
            "provider_called": False, **fields}


class Consumer:
    """Serial in-process event admission; restart always fences unfinished runs."""

    def __init__(self, *, repo: Path, fence: Path, journal: Path,
                 source_root: Path | None = None, isolated_test_copy: bool = False):
        self.repo = Path(repo).resolve(strict=True)
        self.fence = Path(fence)
        self.journal = h02.FsyncJournal(Path(journal))
        self.reader = h02.f03.A05OwnerCorpusAdmission(
            self.repo, fence=self.fence, source_root=source_root,
            isolated_test_copy=isolated_test_copy)
        self.verifier = h02.Consumer(repo=self.repo, fence=fence,
                                     journal=Path(journal).with_suffix(".verifier.jsonl"),
                                     source_root=source_root,
                                     isolated_test_copy=isolated_test_copy)
        self.principal = "os-uid:" + str(os.geteuid())
        self.lock = threading.RLock()
        self.sessions = {}
        self.recovery = self.journal.recover()
        # A restart is not an authorized replay of effects or ACKs.
        self.boot_has_history = self.recovery != "EMPTY"

    def _source(self):
        """Two *distinct*, real, owner-first-party A05 source document spans."""
        receipts = []
        for oid, question, obligation, filename in OBLIGATIONS:
            receipt = self.reader.source_retrieval(
                question, tenant="owner-internal", principal=self.principal,
                obligations=[obligation], ttl_seconds=120)
            check(receipt.get("decision") == "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE"
                  and receipt.get("candidate_only") is True
                  and receipt.get("product_admitted") is False
                  and receipt.get("answer_cache_enabled") is False,
                  "A05_SOURCE_RIGHTS_OR_RETRIEVAL_DENIED")
            pairs = zip(receipt["sources"], receipt["candidate_excerpts"])
            matching = next(((c, t) for c, t in pairs
                             if c["document"] == filename and obligation in t), None)
            check(matching is not None, "OBLIGATION_MISSING_REAL_A05_SPAN")
            cite, excerpt = matching
            proof = self.verifier._verify(obligation, cite)
            check(proof["verified"] is True and proof["signed_issuer"] is False,
                  "INDEPENDENT_OS_BYTE_VERIFICATION_DENIED")
            receipts.append({"obligation_id": oid, "citation": cite,
                             "excerpt_sha256": cite["excerpt_sha256"],
                             "document_sha256": cite["document_sha256"],
                             "release_sha256": receipt["release_sha256"],
                             "rights_sha256": receipt["revocation_sha256"],
                             "rights_epoch": receipt["rights_epoch"],
                             "source_manifest_sha256": receipt["source_manifest_sha256"],
                             "os_verifier_proof_sha256": sha(canonical(proof)),
                             "source_excerpt": excerpt})
        check(receipts[0]["document_sha256"] != receipts[1]["document_sha256"] and
              receipts[0]["excerpt_sha256"] != receipts[1]["excerpt_sha256"],
              "TWO_INDEPENDENT_MATERIAL_SOURCES_REQUIRED")
        check(receipts[0]["rights_sha256"] == receipts[1]["rights_sha256"]
              and receipts[0]["rights_epoch"] == receipts[1]["rights_epoch"]
              and receipts[0]["release_sha256"] == receipts[1]["release_sha256"],
              "SOURCE_RIGHTS_INCONSISTENT")
        return receipts

    def _current(self, e):
        try:
            check(time.monotonic_ns() < e["deadline_ns"], "RUN_DEADLINE_EXPIRED")
            actual = self._source()
            for initial, now in zip(e["proofs"], actual):
                check(initial == now, "SOURCE_OR_RIGHTS_CHANGED_DURING_RUN")
        except h02.Denied:
            # An observed expiry, source drift or revocation is sticky. Restoring
            # an old OS-local epoch MUST NOT revive this run or its pending ACKs.
            if e["state"] == "ACTIVE":
                self._abort(e, "SOURCE_RIGHTS_OR_DEADLINE_BROKEN_NO_RESTORE")
            raise

    def start(self, body):
        with self.lock:
            check(not self.boot_has_history, "RESTART_OR_REPLAY_FENCED")
            check(type(body) is dict and set(body) ==
                  {"task_id", "request_id", "question", "tenant", "principal",
                   "cache_mode", "deadline_seconds"}, "BAD_REQUEST_CONTRACT")
            check(body["question"] == QUESTION and
                  type(body["task_id"]) is str and 3 <= len(body["task_id"]) <= 96 and
                  type(body["request_id"]) is str and 3 <= len(body["request_id"]) <= 96,
                  "UNADMITTED_QA_TASK")
            check(body["tenant"] == "owner-internal" and
                  body["principal"] == self.principal, "TENANT_PRINCIPAL_DENIED")
            check(body["cache_mode"] == "OFF" and
                  type(body["deadline_seconds"]) is int and
                  1 <= body["deadline_seconds"] <= 300,
                  "CACHE_OR_DEADLINE_DENIED")
            check(not self.sessions, "SINGLE_TASK_NO_REPLAY")
            proofs = self._source()
            task = h02.local_task(QUESTION, self.principal)
            task["task_id"] = body["task_id"]
            task["constraints"] = [
                "A05 first-party read-only source rights, OS-local scope only",
                "Proposed model claims are synthetic local fixtures until F02 live admission",
                "Two verified material spans, client ACK and final source recheck",
                "No Product authentication, independent semantic issuer, provider or cache"]
            task["definition_of_done"]["predicate_refs"] = [
                "source_2_distinct_spans", "verified_claims", "two_http_acks",
                "provider_done", "final_source_recheck", "nonprod_answer_text"]
            task = tc.task_contract(task)
            start_ns = time.monotonic_ns()
            sid = secrets.token_hex(24)
            source = proofs[0]
            pins = {
                "task_id": body["task_id"], "request_id": body["request_id"],
                "question_sha256": sha(QUESTION.encode()),
                "task_contract_sha256": tc.sha256(task),
                "tenant": body["tenant"], "principal": body["principal"],
                "source_release_sha256": source["release_sha256"],
                "source_manifest_sha256": source["source_manifest_sha256"],
                "source_rights_epoch": source["rights_epoch"],
                "source_acl_sha256": sha(canonical({"tenant": body["tenant"],
                                                   "principal": body["principal"],
                                                   "role": "internal", "not_idp": True})),
                "answer_obligation_ids": [x[0] for x in OBLIGATIONS],
                "cache_mode": "OFF", "model_route_policy_version": "NO_ROUTE_LOCAL_FIXTURE",
                "max_tokens": 0, "deadline": start_ns + body["deadline_seconds"] * 10**9,
            }
            self.sessions[sid] = {
                "pins": pins, "proofs": proofs, "deadline_ns": pins["deadline"],
                "seq": 0, "monotonic_ns": 0, "seen": set(), "deltas": "",
                "claims": {}, "acked": set(), "provider_start": False,
                "provider_done": False, "state": "ACTIVE", "start_ns": start_ns}
            self.journal.record({"event": "task_frozen", "session_id": sid,
                                 "pins_sha256": sha(canonical(pins)),
                                 "source_sha256": [x["document_sha256"] for x in proofs],
                                 "origin": "SYNTHETIC_FIXTURE"})
            return result("TASK_FROZEN_SOURCE_VERIFIED", session_id=sid,
                          pins=pins, citations={p["obligation_id"]: p["citation"]
                                                 for p in proofs},
                          source_byte_verified=True, actual_client_ack=False)

    def _entry(self, sid):
        check(type(sid) is str and sid in self.sessions, "UNKNOWN_SESSION_NO_REPLAY")
        return self.sessions[sid]

    def _abort(self, e, status):
        e["state"] = "ABSTAINED"
        self.journal.record({"event": "safe_abstention", "reason": status,
                             "origin": "SYNTHETIC_FIXTURE"})
        return result("SAFE_ABSTENTION", reason=status, complete_answer=False)

    def event(self, sid, event):
        with self.lock:
            e = self._entry(sid)
            check(e["state"] == "ACTIVE", "AFTER_TERMINAL_CANCEL_OR_ERROR")
            self._current(e)
            required = {"event_id", "task_id", "request_id", "seq", "monotonic_ns",
                        "event_kind", "raw_event_sha256", "model_origin_class", "data"}
            check(type(event) is dict and set(event) == required, "BAD_EVENT_SHAPE")
            check(event["task_id"] == e["pins"]["task_id"]
                  and event["request_id"] == e["pins"]["request_id"]
                  and event["model_origin_class"] == "SYNTHETIC_FIXTURE",
                  "PROVENANCE_NOT_ADMITTED")
            check(type(event["event_id"]) is str and len(event["event_id"]) >= 3
                  and event["event_id"] not in e["seen"], "REPLAYED_EVENT_ID")
            check(type(event["seq"]) is int and event["seq"] == e["seq"] + 1
                  and type(event["monotonic_ns"]) is int
                  and event["monotonic_ns"] > e["monotonic_ns"],
                  "EVENT_ORDER_OR_CLOCK_DENIED")
            check(event["event_kind"] in EVENT_KINDS and
                  type(event["data"]) is dict and
                  event["raw_event_sha256"] == sha(canonical(event["data"])),
                  "EVENT_INTEGRITY_OR_KIND_DENIED")
            kind, data = event["event_kind"], event["data"]
            if kind == "provider_start":
                check(not e["provider_start"] and e["seq"] == 0 and
                      data == {"provider": "SYNTHETIC_FIXTURE"},
                      "PROVIDER_START_ORDER")
                e["provider_start"] = True
            else:
                check(e["provider_start"] and not e["provider_done"],
                      "PROVIDER_LIFECYCLE_ORDER")
                if kind == "provider_delta":
                    check(set(data) == {"text"} and type(data["text"]) is str and
                          0 < len(data["text"]) <= 1024 and
                          len(e["deltas"]) + len(data["text"]) <= 2048,
                          "EMPTY_OR_OVERSIZED_DELTA")
                    e["deltas"] += data["text"]
                elif kind == "claim_proposed":
                    check(set(data) == {"obligation_id", "text", "citation"},
                          "CLAIM_SHAPE_DENIED")
                    oid, claim = data["obligation_id"], data["text"]
                    ids = e["pins"]["answer_obligation_ids"]
                    check(oid in ids and oid not in e["claims"] and
                          len(e["claims"]) == ids.index(oid), "OBLIGATION_ORDER_OR_DUPLICATE")
                    check(type(claim) is str and 20 <= len(claim) <= 250
                          and claim in e["deltas"] and
                          not re.search(r"(?<!\w)\d+(?!\w)|\b(no|not|never|without|cannot|doesn't)\b",
                                        claim, re.I), "UNSUPPORTED_NUMERIC_NEGATION_OR_DELTA")
                    idx = ids.index(oid)
                    check(ACCEPTED_TEXT[idx].fullmatch(claim) is not None,
                          "UNSUPPORTED_CLAIM_SEMANTICS")
                    expected = e["proofs"][idx]
                    check(data["citation"] == expected["citation"],
                          "FORGED_CITATION")
                    # Verify actual bytes/citation in a *separate* OS process.
                    phrase = OBLIGATIONS[idx][2]
                    self.verifier._verify(phrase, expected["citation"])
                    self._current(e)
                    nonce = secrets.token_hex(24)
                    e["claims"][oid] = {"claim_id": oid, "answer_text": claim,
                                        "text_sha256": sha(claim.encode()),
                                        "challenge": nonce, "citation": expected["citation"],
                                        "seq": event["seq"], "kind": "answer_text",
                                        "origin": "SYNTHETIC_FIXTURE",
                                        "verified_source": True}
                    self.journal.record({"event": "claim_verified", "id": oid,
                                         "sha256": sha(claim.encode()),
                                         "source_document_sha256": expected["document_sha256"]})
                elif kind == "provider_done":
                    check(data == {"done": True} and len(e["claims"]) == 2,
                          "PROVIDER_DONE_OR_TWO_CLAIMS_MISSING")
                    e["provider_done"] = True
                else:
                    check(set(data) == {"code"} and type(data["code"]) is str,
                          "UNTRUSTED_PROVIDER_ERROR")
                    return self._abort(e, "PROVIDER_ERROR_UNKNOWN")
            e["seq"] = event["seq"]
            e["monotonic_ns"] = event["monotonic_ns"]
            e["seen"].add(event["event_id"])
            self.journal.record({"event": kind, "seq": e["seq"],
                                 "event_id": event["event_id"],
                                 "origin": "SYNTHETIC_FIXTURE"})
            return result("EVENT_ACCEPTED", seq=e["seq"],
                          verified_claim_count=len(e["claims"]))

    def next_text(self, sid):
        with self.lock:
            e = self._entry(sid)
            check(e["state"] == "ACTIVE", "SESSION_NOT_ACTIVE")
            self._current(e)
            for oid in e["pins"]["answer_obligation_ids"]:
                if oid in e["claims"] and oid not in e["acked"]:
                    return result("VERIFIED_ANSWER_TEXT_READY", **e["claims"][oid])
            return result("NO_VERIFIED_TEXT", complete_answer=False)

    def ack(self, sid, claim_id, challenge, text_sha256, ack_sha256):
        with self.lock:
            e = self._entry(sid)
            check(e["state"] == "ACTIVE", "ACK_AFTER_END")
            self._current(e)
            check(claim_id in e["claims"] and claim_id not in e["acked"] and
                  e["pins"]["answer_obligation_ids"][len(e["acked"])] == claim_id,
                  "ACK_WRONG_CLAIM_OR_ORDER")
            claim = e["claims"][claim_id]
            check(type(challenge) is str and type(text_sha256) is str
                  and type(ack_sha256) is str and
                  hmac.compare_digest(challenge, claim["challenge"]) and
                  hmac.compare_digest(text_sha256, claim["text_sha256"]) and
                  hmac.compare_digest(ack_sha256, sha((
                      e["pins"]["request_id"] + "|" + claim_id + "|" + challenge
                      + "|" + text_sha256).encode())),
                  "FORGED_CLIENT_ACK")
            e["acked"].add(claim_id)
            self.journal.record({"event": "client_ack", "claim_id": claim_id,
                                 "claim_sha256": text_sha256,
                                 "when_ns": time.monotonic_ns()})
            return result("CLIENT_ACK_ACCEPTED", acked=len(e["acked"]),
                          actual_client_ack=True)

    def terminal(self, sid):
        with self.lock:
            e = self._entry(sid)
            check(e["state"] == "ACTIVE", "DUPLICATE_TERMINAL_OR_CANCEL")
            self._current(e)
            check(e["provider_done"], "MISSING_PROVIDER_DONE")
            check(len(e["claims"]) == 2 and len(e["acked"]) == 2,
                  "MISSING_SECOND_MATERIAL_ACK")
            answer = " ".join(e["claims"][oid]["answer_text"]
                              for oid in e["pins"]["answer_obligation_ids"])
            self.journal.record({"event": "final_source_recheck", "source_sha256":
                                 [p["document_sha256"] for p in self._source()]})
            e["state"] = "TERMINATED"
            self.journal.record({"event": "terminal", "status": "LOCAL_FIXTURE_ANSWERED",
                                 "when_ns": time.monotonic_ns()})
            return result("LOCAL_FIXTURE_ANSWERED", answer=answer,
                          actual_client_ack=True, complete_answer=True,
                          source_byte_verified=True,
                          actual_complete_answer_ms=round(
                              (time.monotonic_ns() - e["start_ns"]) / 1e6, 3))

    def cancel(self, sid):
        with self.lock:
            e = self._entry(sid)
            check(e["state"] == "ACTIVE", "CANCEL_AFTER_END")
            e["state"] = "CANCELLED"
            self.journal.record({"event": "cancelled", "session_id": sid})
            return result("CANCELLED_SAFE_TERMINAL", complete_answer=False)


class Handler(BaseHTTPRequestHandler):
    consumer: Consumer
    transport_token: str

    def log_message(self, *args):
        pass

    def reply(self, obj, code=200):
        raw = canonical(obj)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return (self.client_address[0] == "127.0.0.1" and
                self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}" and
                hmac.compare_digest(self.headers.get("X-G01-Local-Capability", ""),
                                    self.transport_token))

    def do_GET(self):
        if not self.authorized():
            return self.reply(result("OS_LOCAL_TRANSPORT_DENIED"), 403)
        url = urlsplit(self.path)
        try:
            if url.path == STATUS:
                return self.reply(result("LOCAL_NONPROD_FIXTURE_ONLY",
                                         server_pid=os.getpid(),
                                         recovery=self.consumer.recovery))
            check(url.path == NEXT, "UNKNOWN_ROUTE")
            params = parse_qs(url.query)
            check(set(params) == {"session_id"} and len(params["session_id"]) == 1,
                  "INVALID_QUERY")
            self.reply(self.consumer.next_text(params["session_id"][0]))
        except h02.Denied as exc:
            self.reply(result(str(exc)), 403)
        except Exception:
            self.reply(result("UNEXPECTED_FAILURE_CLOSED"), 503)

    def do_POST(self):
        if not self.authorized():
            return self.reply(result("OS_LOCAL_TRANSPORT_DENIED"), 403)
        if self.headers.get("Content-Type", "").lower() != "application/json":
            return self.reply(result("JSON_REQUIRED"), 415)
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
            return self.reply(result("BODY_LIMIT_DENIED"), 413)
        try:
            body = json.loads(self.rfile.read(int(length)))
            check(type(body) is dict, "REQUEST_OBJECT_REQUIRED")
            if self.path == ROUTE:
                out = self.consumer.start(body)
            elif self.path == EVENT:
                check(set(body) == {"session_id", "event"}, "BAD_EVENT_REQUEST")
                out = self.consumer.event(body["session_id"], body["event"])
            elif self.path == ACK:
                check(set(body) == {"session_id", "claim_id", "challenge",
                                    "text_sha256", "ack_sha256"}, "BAD_ACK_REQUEST")
                out = self.consumer.ack(body["session_id"], body["claim_id"],
                                        body["challenge"], body["text_sha256"],
                                        body["ack_sha256"])
            elif self.path == TERMINAL:
                check(set(body) == {"session_id"}, "BAD_TERMINAL_REQUEST")
                out = self.consumer.terminal(body["session_id"])
            elif self.path == CANCEL:
                check(set(body) == {"session_id"}, "BAD_CANCEL_REQUEST")
                out = self.consumer.cancel(body["session_id"])
            else:
                raise h02.Denied("UNKNOWN_ROUTE")
            self.reply(out)
        except h02.Denied as exc:
            self.reply(result(str(exc)), 403)
        except (ValueError, TypeError, KeyError):
            self.reply(result("INVALID_REQUEST"), 400)
        except Exception:
            self.reply(result("UNEXPECTED_FAILURE_CLOSED"), 503)


def serve(*, repo: Path, fence: Path, journal: Path, ready_file: Path,
          source_root: Path | None = None, isolated_test_copy: bool = False):
    c = Consumer(repo=repo, fence=fence, journal=journal, source_root=source_root,
                 isolated_test_copy=isolated_test_copy)
    class App(Handler):
        pass
    App.consumer = c
    App.transport_token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), App)
    check(ready_file.parent.is_dir() and not ready_file.exists(),
          "PRIVATE_READY_PATH_REQUIRED")
    fd = os.open(ready_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        payload = canonical({"server_pid": os.getpid(), "port": server.server_port,
                             "transport_token": App.transport_token,
                             "abi": ABI, "origin": "SYNTHETIC_FIXTURE"})
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--fence", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--ready-file", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--isolated-test-copy", action="store_true")
    args = parser.parse_args()
    serve(repo=Path(args.repo), fence=Path(args.fence), journal=Path(args.journal),
          ready_file=Path(args.ready_file),
          source_root=Path(args.source_root) if args.source_root else None,
          isolated_test_copy=args.isolated_test_copy)


if __name__ == "__main__":
    main()
