"""C24 independent client-side SSE observation. Never a self-issued product certificate.

SDK operates on bytes ACTUALLY received by a client; no server-progress timestamp
counts as substantive first text. CLI and calibration fixtures are synthetic only.
External grants, independent ACK signatures and custody require trusted roots.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "m27.w5.c24.client_observation.v1"
UNKNOWN = "UNKNOWN"
MAX_WIRE = 4 * 1024 * 1024
MAX_FRAME = 128 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = ("case_id", "request_id", "nonce", "runner_sha256", "candidate_sha256")


class ObservationDenied(ValueError):
    """Stable fail-closed error code, without source/body disclosures."""


def need(value: bool, code: str) -> None:
    if not value:
        raise ObservationDenied(code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest_valid(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


@dataclass(frozen=True)
class SourcePin:
    citation_id: str
    source_id: str
    revision: str
    source_sha256: str
    original_bytes: bytes
    revoked: bool = False
    authorized: bool = False

    def check(self) -> None:
        need(bool(self.citation_id and self.source_id and self.revision),
             "SOURCE_ID_MISSING")
        need(digest_valid(self.source_sha256)
             and sha(self.original_bytes) == self.source_sha256,
             "SOURCE_DIGEST_OR_CONTENT_MISMATCH")
        need(not self.revoked and self.authorized, "SOURCE_RIGHTS_UNVERIFIED_OR_REVOKED")


@dataclass(frozen=True)
class CasePlan:
    case_id: str
    request_id: str
    nonce: str
    runner_sha256: str
    candidate_sha256: str
    expected_citation: bool
    synthetic: bool = True
    client_role: str = "synthetic_fixture"
    cohort: str = "calibration"

    def validate(self) -> None:
        for name in ("case_id", "request_id", "nonce", "client_role", "cohort"):
            value = getattr(self, name)
            need(isinstance(value, str) and 1 <= len(value) <= 128
                 and all(c.isascii() and (c.isalnum() or c in "-_.") for c in value),
                 "CASE_FIELD_INVALID:" + name)
        need(digest_valid(self.runner_sha256)
             and digest_valid(self.candidate_sha256), "CANDIDATE_RUNNER_UNPINNED")
        need(type(self.expected_citation) is bool and type(self.synthetic) is bool,
             "CASE_FLAGS_INVALID")


def verify_ed25519(payload: dict, signature_b64: str, public_b64: str) -> bool:
    """Cryptographic check only, NOT a legal grant or approved trust root."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        signature = base64.b64decode(signature_b64, validate=True)
        key = base64.b64decode(public_b64, validate=True)
        need(len(signature) == 64 and len(key) == 32, "SIGNATURE_LENGTH_INVALID")
        Ed25519PublicKey.from_public_bytes(key).verify(signature, canonical(payload))
        return True
    except ImportError:
        return False
    except (ValueError, TypeError, KeyError, ObservationDenied):
        return False
    except Exception as exc:
        # InvalidSignature and backend verification errors both fail closed.
        if type(exc).__name__ in ("InvalidSignature", "UnsupportedAlgorithm"):
            return False
        raise


def independent_custody(
    capture: dict, grant: dict | None, ack: dict | None,
    trust_roots: dict[str, str] | None,
) -> dict:
    """Only pre-approved distinct signer roots qualify; no self-signed authority."""
    unverified = {"status": UNKNOWN, "reason": "REAL_APP_INDEPENDENT_AUTHORITY_MISSING"}
    if not isinstance(grant, dict) or not isinstance(ack, dict) or not trust_roots:
        return unverified
    try:
        need(grant.get("role") == "external_controller"
             and ack.get("role") == "independent_client",
             "SIGNER_ROLES_INVALID")
        gid, aid = grant.get("issuer"), ack.get("issuer")
        need(isinstance(gid, str) and isinstance(aid, str) and gid != aid,
             "SIGNERS_NOT_INDEPENDENT")
        need(gid in trust_roots and aid in trust_roots, "TRUST_ROOT_NOT_APPROVED")
        gp, ap = grant.get("payload"), ack.get("payload")
        need(isinstance(gp, dict) and isinstance(ap, dict), "SIGNED_PAYLOAD_ABSENT")
        need(gp.get("role", "controller") == "controller",
             "CONTROLLER_GRANT_ROLE_INVALID")
        need(verify_ed25519(gp, grant.get("signature", ""), trust_roots[gid]),
             "GRANT_SIGNATURE_INVALID")
        need(verify_ed25519(ap, ack.get("signature", ""), trust_roots[aid]),
             "ACK_SIGNATURE_INVALID")
        for key in ("case_id", "request_id", "nonce", "runner_sha256",
                    "candidate_sha256"):
            need(gp.get(key) == capture.get(key) and ap.get(key) == capture.get(key),
                 "SIGNED_IDENTITY_MISMATCH")
        need(gp.get("scope") == "native_client_evaluation"
             and gp.get("allow") is True
             and gp.get("source_rights_verified") is True
             and ap.get("client_observed") is True
             and ap.get("observation_sha256") == sha(canonical(
                 {k: v for k, v in capture.items() if k != "custody"}
             )), "SIGNED_SCOPE_OR_ACK_MISMATCH")
        need(not capture.get("synthetic") and capture.get("status") == "COMPLETE",
             "SYNTHETIC_OR_FAILED_CANNOT_CERTIFY")
        need(ap.get("client_pid") == capture.get("client_pid")
             and ap.get("client_process_nonce") == capture.get("client_process_nonce"),
             "ACK_PROCESS_NOT_BOUND")
        return {"status": "SIGNATURE_VERIFIED_EXTERNAL_REVIEW_REQUIRED",
                "reason": "EXTERNAL_LEGAL_AND_RUBRIC_ADMISSION_NOT_AUTOMATIC",
                "controller_issuer": gid, "client_issuer": aid}
    except (ObservationDenied, TypeError, ValueError):
        return {"status": UNKNOWN, "reason": "SIGNATURE_OR_CUSTODY_INVALID"}


class ClientCapture:
    """Called *inside* a genuine client recv loop, with the client's own clock.

    Caller must invoke admit before sending the request, then feed each recv
    chunk, then close even on timeout/disconnect. Do not feed server logs.
    """

    def __init__(
        self, plan: CasePlan, sources: Iterable[SourcePin],
        clock_ns: Callable[[], int] = time.monotonic_ns,
        client_pid: int | None = None, client_process_nonce: str | None = None,
        source_current: Callable[[SourcePin], bool] | None = None,
    ) -> None:
        plan.validate()
        self.plan = plan
        provided = tuple(sources)
        self.sources = {s.citation_id: s for s in provided}
        need(len(self.sources) > 0, "SOURCES_NOT_PROVISIONED")
        need(len(self.sources) == len(provided), "DUPLICATE_SOURCE_PIN")
        need(plan.synthetic or source_current is not None,
             "REAL_SOURCE_AUTHORITY_CALLBACK_MISSING")
        self.source_current = source_current
        for source in self.sources.values():
            source.check()
            if source_current is not None:
                need(source_current(source), "SOURCE_AUTHORITY_NOT_CURRENT")
        self.clock = clock_ns
        self.client_pid = client_pid if client_pid is not None else os.getpid()
        need(type(self.client_pid) is int and self.client_pid > 0, "CLIENT_PID_INVALID")
        self.client_process_nonce = client_process_nonce or os.urandom(16).hex()
        need(isinstance(self.client_process_nonce, str)
             and len(self.client_process_nonce) >= 16, "PROCESS_NONCE_INVALID")
        self.admitted_ns: int | None = None
        self.first_recv_ns: int | None = None
        self.first_text_ns: int | None = None
        self.full_answer_ns: int | None = None
        self.terminal_ns: int | None = None
        self.prev_clock_ns: int | None = None
        self.status = "NEW"
        self.pending = bytearray()
        self.http_header = False
        self.raw_received = 0
        self.recv_calls = 0
        self.progress_events = 0
        self.answer_events = 0
        self.next_seq = 0
        self.answer = bytearray()
        self.citations: list[dict] = []
        self.transcript = hashlib.sha256()
        self.errors: list[str] = []

    def tick(self) -> int:
        stamp = self.clock()
        need(type(stamp) is int and stamp >= 0, "CLOCK_INVALID")
        need(self.prev_clock_ns is None or stamp >= self.prev_clock_ns,
             "CLOCK_REGRESSION")
        self.prev_clock_ns = stamp
        return stamp

    def admit(self) -> None:
        need(self.status == "NEW", "DUPLICATE_ADMISSION")
        self.admitted_ns = self.tick()
        self.status = "OPEN"

    def feed(self, chunk: bytes) -> None:
        need(self.status == "OPEN", "BYTES_AFTER_TERMINAL_OR_CLOSE")
        need(type(chunk) is bytes, "WIRE_MUST_BE_BYTES")
        stamp = self.tick()
        if not chunk:
            return
        if self.first_recv_ns is None:
            self.first_recv_ns = stamp
        self.raw_received += len(chunk)
        self.recv_calls += 1
        need(self.raw_received <= MAX_WIRE, "WIRE_TOO_LARGE")
        self.pending.extend(chunk)
        self.transcript.update(chunk)
        if not self.http_header:
            marker = self.pending.find(b"\r\n\r\n")
            need(marker <= 8192 and (marker >= 0 or len(self.pending) <= 8192),
                 "HTTP_HEADER_TOO_LARGE")
            if marker < 0:
                return
            lines = bytes(self.pending[:marker]).split(b"\r\n")
            need(lines[0] == b"HTTP/1.1 200 OK", "HTTP_RESPONSE_NOT_200")
            need(b"content-type: text/event-stream; charset=utf-8" in
                 [line.lower() for line in lines[1:]], "NOT_UTF8_SSE")
            del self.pending[:marker + 4]
            self.http_header = True
        while b"\n\n" in self.pending:
            need(self.status == "OPEN", "EVENT_AFTER_TERMINAL")
            cut = self.pending.index(b"\n\n")
            need(0 < cut <= MAX_FRAME, "EVENT_SIZE_INVALID")
            event = bytes(self.pending[:cut])
            del self.pending[:cut + 2]
            lines = event.split(b"\n")
            need(len(lines) == 2 and lines[0].startswith(b"event: ")
                 and lines[1].startswith(b"data: ") and b"\r" not in event,
                 "EVENT_ENVELOPE_INVALID")
            try:
                kind = lines[0][7:].decode("ascii", "strict")
                payload = json.loads(lines[1][6:].decode("utf-8", "strict"))
            except (UnicodeError, ValueError) as exc:
                raise ObservationDenied("INVALID_EVENT_ENCODING") from exc
            self.event(kind, payload, stamp)
        need(len(self.pending) <= MAX_FRAME, "PARTIAL_EVENT_OVER_LIMIT")

    def event(self, kind: str, p: dict, stamp: int) -> None:
        need(type(p) is dict, "EVENT_BODY_INVALID")
        for key in IDENTITY:
            need(p.get(key) == getattr(self.plan, key), "EVENT_IDENTITY_" + key)
        need("authenticated_ack" not in p and "signature" not in p
             and "production_authorized" not in p, "SELF_ASSERTED_AUTHORITY")
        if kind == "progress":
            need(not self.answer_events and self.status == "OPEN"
                 and p.get("phase") == "preparing", "PROGRESS_INVALID")
            self.progress_events += 1
            return
        if kind == "error":
            need(self.status == "OPEN" and isinstance(p.get("code"), str),
                 "ERROR_EVENT_INVALID")
            self.errors.append(p["code"][:100])
            self.status = "ERROR"
            self.terminal_ns = stamp
            return
        if kind == "answer":
            need(self.status == "OPEN", "ANSWER_AFTER_TERMINAL")
            seq, start, end, raw_text = (
                p.get("sequence"), p.get("start"), p.get("end"), p.get("text")
            )
            need(type(seq) is int and seq == self.next_seq, "FRAME_REPLAY_OR_GAP")
            need(type(raw_text) is str and bool(raw_text.strip()),
                 "NO_SUBSTANTIVE_TEXT")
            data = raw_text.encode("utf-8")
            need(type(start) is int and start == len(self.answer)
                 and type(end) is int and end == start + len(data),
                 "FRAME_OFFSET_INVALID")
            need(p.get("sha256") == sha(data), "FRAME_DIGEST_INVALID")
            links = p.get("citations")
            need(isinstance(links, list) and len(links) > 0, "CITATION_LINK_MISSING")
            for link in links:
                need(isinstance(link, dict), "CITATION_SHAPE_INVALID")
                citation = self.sources.get(link.get("citation_id"))
                need(citation is not None, "SOURCE_NATIVE_CITATION_UNKNOWN")
                citation.check()
                if self.source_current is not None:
                    need(self.source_current(citation),
                         "SOURCE_REVOKED_AFTER_ADMISSION")
                for field, expected in (
                    ("source_id", citation.source_id),
                    ("revision", citation.revision),
                    ("source_sha256", citation.source_sha256),
                ):
                    need(link.get(field) == expected, "CITATION_" + field.upper())
                low, high = link.get("source_start"), link.get("source_end")
                need(type(low) is int and type(high) is int
                     and 0 <= low < high <= len(citation.original_bytes),
                     "SOURCE_BYTE_SPAN_INVALID")
                need(link.get("quote_sha256")
                     == sha(citation.original_bytes[low:high]),
                     "SOURCE_QUOTE_DIGEST_INVALID")
                a, b = link.get("answer_start"), link.get("answer_end")
                need(type(a) is int and type(b) is int
                     and start <= a < b <= end, "ANSWER_CITATION_SPAN_INVALID")
                self.citations.append({k: link[k] for k in (
                    "citation_id", "source_id", "revision", "source_sha256",
                    "source_start", "source_end", "quote_sha256",
                    "answer_start", "answer_end"
                )})
            self.answer.extend(data)
            self.next_seq += 1
            self.answer_events += 1
            if self.first_text_ns is None:
                self.first_text_ns = stamp
            return
        if kind == "terminal":
            for citation in self.sources.values():
                citation.check()
                if self.source_current is not None:
                    need(self.source_current(citation),
                         "SOURCE_REVOKED_BEFORE_TERMINAL")
            need(self.status == "OPEN" and self.answer_events > 0,
                 "TERMINAL_BEFORE_SUBSTANTIVE_TEXT")
            need(p.get("status") == "completed", "TERMINAL_NOT_COMPLETE")
            need(type(p.get("answer_bytes")) is int
                 and p["answer_bytes"] == len(self.answer)
                 and p.get("answer_sha256") == sha(self.answer),
                 "FINAL_INCOMPLETE_OR_DIGEST_INVALID")
            need(self.first_text_ns is not None and self.first_text_ns < stamp,
                 "FIRST_TEXT_NOT_BEFORE_TERMINAL")
            self.full_answer_ns = stamp
            self.terminal_ns = stamp
            self.status = "COMPLETE"
            return
        raise ObservationDenied("EVENT_TYPE_INVALID")

    def close(self, reason: str = "disconnect") -> dict:
        need(self.status != "NEW" and self.status != "CLOSED",
             "NEVER_ADMITTED_OR_DOUBLE_CLOSE")
        stamp = self.tick()
        if self.status == "OPEN":
            need(reason in ("disconnect", "timeout", "cancelled", "rejected"),
                 "CLOSE_REASON_INVALID")
            self.status = reason.upper()
            self.errors.append("MISSING_TERMINAL:" + reason)
        need(self.admitted_ns is not None and stamp >= self.admitted_ns,
             "ADMISSION_CLOCK_INVALID")
        terminal = self.terminal_ns
        complete = self.status == "COMPLETE"
        receipt = {
            "schema": SCHEMA, **{key: getattr(self.plan, key) for key in IDENTITY},
            "cohort": self.plan.cohort, "synthetic": self.plan.synthetic,
            "client_role": self.plan.client_role, "client_pid": self.client_pid,
            "client_process_nonce": self.client_process_nonce,
            "status": self.status, "request_admitted_ns": self.admitted_ns,
            "first_recv_ns": self.first_recv_ns,
            "first_substantive_text_ns": self.first_text_ns,
            "full_answer_ns": self.full_answer_ns, "terminal_ns": terminal,
            "client_closed_ns": stamp, "answer_sha256": sha(self.answer) if complete else None,
            "answer_bytes": len(self.answer) if complete else None,
            "source_native_citations": self.citations if complete else [],
            "progress_events": self.progress_events, "answer_events": self.answer_events,
            "recv_calls": self.recv_calls, "received_wire_bytes": self.raw_received,
            "wire_transcript_sha256": self.transcript.hexdigest(),
            "errors": list(self.errors),
            "full_response_latency_ms": (
                (terminal - self.admitted_ns) / 1e6 if complete and terminal else None
            ),
            "first_text_latency_ms": (
                (self.first_text_ns - self.admitted_ns) / 1e6
                if complete and self.first_text_ns is not None else None
            ),
            "custody": {"status": UNKNOWN, "reason": "EXTERNAL_ACK_NOT_PROVISIONED"},
            "official_qualified": False, "w5_full_complete": False,
        }
        self.status = "CLOSED"
        return receipt


def nearest_rank(values: list[float], percentile: float = .95) -> tuple[int, float]:
    need(bool(values) and 0 < percentile <= 1
         and all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                 for v in values), "PERCENTILE_INPUT_INVALID")
    rank = math.ceil(len(values) * percentile)
    return rank, sorted(values)[rank - 1]


def evaluate_cohort(
    plan: list[CasePlan], receipts: list[dict], *, synthetic_calibration: bool = False
) -> dict:
    """No missing outcome, timeout or denied case can be excluded from the p95."""
    target = len(plan)
    expected_rank = {341: 324, 237: 226}.get(target)
    need(expected_rank is not None, "UNSUPPORTED_OFFICIAL_DENOMINATOR")
    result: dict = {
        "cohort_size": target, "rank": expected_rank,
        "all_outcome_p95_ms": None, "decision": UNKNOWN,
        "synthetic_calibration_p95_ms": None, "w5_full_complete": False,
    }
    try:
        need(len({x.case_id for x in plan}) == target
             and len({x.nonce for x in plan}) == target, "PLAN_DUPLICATE")
        need(len(receipts) == target, "OUTCOME_MISSING_OR_DUPLICATE")
        mapping = {r["case_id"]: r for r in receipts}
        need(len(mapping) == target and set(mapping) == {x.case_id for x in plan},
             "UNPLANNED_OR_DUPLICATE_OUTCOME")
        need(len({(r["client_pid"], r["client_process_nonce"], r["nonce"])
                  for r in receipts}) == target, "PROCESS_NONCE_REPLAY")
        timings = []
        for case in plan:
            case.validate()
            r = mapping[case.case_id]
            for key in IDENTITY:
                need(r.get(key) == getattr(case, key), "OUTCOME_IDENTITY_MISMATCH")
            need(r.get("schema") == SCHEMA and r.get("synthetic") == case.synthetic,
                 "OUTCOME_SCHEMA_OR_MODE")
            need(r.get("status") == "COMPLETE", "OUTCOME_NOT_COMPLETE")
            start, first, end = (r.get("request_admitted_ns"),
                                 r.get("first_substantive_text_ns"),
                                 r.get("terminal_ns"))
            need(all(type(t) is int for t in (start, first, end))
                 and start <= first < end, "CLIENT_TIMING_NOT_AUTHENTICATED")
            latency = r.get("full_response_latency_ms")
            need(type(latency) in (int, float) and math.isfinite(latency)
                 and latency >= 0 and abs(latency - (end - start) / 1e6) < 1e-6,
                 "CLIENT_LATENCY_NOT_SAME_CLOCK")
            need(type(r.get("answer_bytes")) is int and r["answer_bytes"] > 0
                 and digest_valid(r.get("answer_sha256"))
                 and r.get("answer_events", 0) > 0, "ANSWER_MISSING")
            if case.expected_citation:
                need(bool(r.get("source_native_citations")),
                     "CITED_EXPECTED_WITHOUT_CITATION")
            timings.append(float(latency))
        rank, score = nearest_rank(timings)
        need(rank == expected_rank, "RANK_NOT_NEAREST")
        if synthetic_calibration and all(x.synthetic for x in plan):
            result["synthetic_calibration_p95_ms"] = score
            result["decision"] = "SYNTHETIC_CALIBRATION_ONLY"
        else:
            # A self-supplied dictionary with official_qualified=True is not
            # an independent certified cohort. Only a separately controlled,
            # signed evaluation can promote an actual full-outcome p95.
            result["decision"] = UNKNOWN
            result["reason"] = "INDEPENDENT_EVALUATION_AUTHORITY_NOT_ADMITTED"
    except (ObservationDenied, KeyError, TypeError, ValueError) as exc:
        result["reason"] = str(exc)[:100]
    return result


def make_test_frame(kind: str, payload: dict) -> bytes:
    """Synthetic calibration helper only; never evidence of real app traffic."""
    return (b"event: " + kind.encode("ascii") + b"\ndata: "
            + canonical(payload) + b"\n\n")


def synthetic_demo(port: int, plan_path: Path, output_path: Path) -> int:
    """OS client connects to 127.0.0.1 only. Output always SYNTHETIC."""
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    need(raw.get("plan", {}).get("synthetic") is True, "DEMO_MUST_BE_SYNTHETIC")
    case = CasePlan(**raw["plan"])
    source_info = {k: v for k, v in raw["source"].items() if k != "bytes_b64"}
    source = SourcePin(**{
        **source_info,
        "original_bytes": base64.b64decode(raw["source"]["bytes_b64"], validate=True),
    })
    # No arbitrary endpoint or authenticated real-app mode in demo CLI.
    capture = ClientCapture(case, [source])
    capture.admit()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=4) as conn:
            conn.sendall(b"GET /synthetic HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            conn.settimeout(4)
            while True:
                part = conn.recv(11)
                if not part:
                    break
                capture.feed(part)
                if capture.status in ("COMPLETE", "ERROR"):
                    break
        receipt = capture.close()
    except (OSError, ObservationDenied) as exc:
        if capture.status == "NEW":
            raise
        receipt = capture.close("disconnect") if capture.status != "CLOSED" else {}
        receipt["client_error"] = type(exc).__name__
    output_path.write_text(json.dumps(receipt, sort_keys=True, ensure_ascii=False))
    return 0 if receipt.get("status") == "COMPLETE" else 20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C24 synthetic-only OS client probe")
    parser.add_argument("--synthetic-loopback-port", type=int, required=True)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    need(0 < args.synthetic_loopback_port <= 65535, "PORT_INVALID")
    return synthetic_demo(args.synthetic_loopback_port, args.plan_json, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
