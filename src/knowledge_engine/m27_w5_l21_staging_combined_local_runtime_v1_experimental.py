"""L21 experimental *local fixture* runtime. Never an evidence/release authority.

Reuses I15's independent real localhost client/server processes and P17's
content-digested DENIAL receipt. Nothing here admits original523, Phase B,
provider traffic, external sources, canonical M16, or production.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15
from knowledge_engine import m27_w5_p16_external_evidence_ingress_v1_experimental as p17

VERSION = "W5L21ExploratoryCombinedLocalRuntimeV1"
STATUS = "L21_EXPLORATORY_LOCAL_ENGINEERING_COMPLETE_OR_PARTIAL"
DENIED = "L21_FAIL_CLOSED"
RESTRICTIONS = (
    "NOT_CANONICAL_M16_ACCEPTED",
    "NOT_ORIGINAL523_OFFICIAL_PASS",
    "NOT_AR09_PHASE_B_ADMISSION",
    "NOT_P16_EXTERNAL_RIGHTS_AUTHORITY",
    "NOT_B13_POSITIVE_ADMISSION",
    "NOT_PRODUCT_P95",
    "NOT_REAL_PROVIDER",
    "NOT_PRODUCTION_OR_RELEASE",
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOCAL_BOOT_DEADLINE_SECONDS = 24.0
LOCAL_CLIENT_DEADLINE_SECONDS = 24.0
LOCAL_SERVER_EXIT_DEADLINE_SECONDS = 16.0
_LOCAL_CASE_LOCK = threading.Lock()


class LocalDenied(ValueError):
    """Typed, non-sensitive fail-closed local staging rejection."""


def require(value: bool, code: str) -> None:
    if not value:
        raise LocalDenied(code)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class LocalReceipt:
    case_id: str
    mode: str
    outcome: str
    client_pid: int
    server_pid: int
    source_revision: str
    source_sha256: str
    citation_id: str
    answer_sha256: str
    first_text_ms: float | None
    terminal_ms: float | None
    answer_byte_count: int
    synthetic_only: bool = True


@dataclass(frozen=True)
class DenialReceipt:
    decision: str
    exit_code: int
    validated: bool
    receipt_sha256: str
    actual_file_sha256: str
    original523: str
    phase_b: str
    may_execute_official_evaluation: bool = False


def _ns(namespace: str) -> None:
    require(
        isinstance(namespace, str) and
        bool(re.fullmatch(r"[a-zA-Z0-9_-]{2,48}", namespace)),
        "NAMESPACE_INVALID",
    )


def _scratch(worktree: Path, scratch: Path) -> None:
    require(worktree.is_absolute() and worktree.is_dir() and
            (worktree / "src").is_dir() and not worktree.is_symlink(),
            "WORKTREE_UNSAFE")
    require(scratch.is_absolute() and not scratch.is_symlink() and
            not scratch.resolve().is_relative_to(worktree.resolve()) and
            not worktree.resolve().is_relative_to(scratch.resolve()),
            "SCRATCH_OUTSIDE_WORKTREE_REQUIRED")
    require(not (scratch.exists() and not scratch.is_dir()), "SCRATCH_NOT_DIRECTORY")


def _time(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value < 1e12


def validate_case(
    case: Mapping[str, Any], index: int, mode: str, namespace: str,
) -> LocalReceipt:
    """Check receipt fields against independently reconstructed local source bytes.

    Client timestamps are compared ONLY with timestamps from the same client,
    never with server/parent monotonic clocks in another process.
    """
    _ns(namespace)
    require(type(index) is int and 0 <= index < len(i15.PHRASES), "INDEX_INVALID")
    require(mode == "positive" or mode in i15.FAULT_MODES, "MODE_INVALID")
    require(isinstance(case, Mapping), "CASE_NOT_MAPPING")
    expected = i15.spec(index, namespace)
    require(case.get("fixture") is True, "FIXTURE_FLAG_ABSENT")
    require(case.get("mode") == mode and case.get("namespace") == namespace,
            "MODE_OR_NAMESPACE_MISMATCH")
    require(case.get("case_id") == expected["case_id"] + "-" + mode,
            "CASE_ID_MISMATCH")
    actual_source_sha = sha(expected["answer_bytes"])
    require(
        actual_source_sha == expected["source_sha256"] and
        case.get("source_sha256") == actual_source_sha and
        bool(SHA_PATTERN.fullmatch(actual_source_sha)),
        "SOURCE_BYTES_SHA_MISMATCH",
    )
    require(case.get("source_revision") == expected["source_revision"],
            "SOURCE_REVISION_MISMATCH")
    require(case.get("answer_sha256") == sha(expected["answer_bytes"]),
            "ANSWER_PIN_MISMATCH")
    client, server, diag = (case.get("client"), case.get("server"),
                            case.get("diagnostics"))
    require(all(isinstance(x, Mapping) for x in (client, server, diag)),
            "RECEIPT_STRUCTURE_INVALID")
    cp, sp = client.get("client_pid"), server.get("server_pid")
    require(type(cp) is int and cp > 0 and type(sp) is int and sp > 0 and cp != sp,
            "SEPARATE_CLIENT_SERVER_PID_REQUIRED")
    require(
        diag.get("client_exit") == 0 and diag.get("server_exit") == 0
        and diag.get("process_limit") == 4
        and diag.get("failure_stage") is None,
        "CHILD_PROCESS_EVIDENCE_INVALID",
    )
    cleanup = diag.get("cleanup")
    require(isinstance(cleanup, Mapping) and
            all(isinstance(cleanup.get(k), Mapping) and
                cleanup[k].get("reaped") is True for k in ("server", "client")),
            "CHILD_REAP_NOT_VERIFIED")
    require(type(client.get("recv_calls")) is int and client["recv_calls"] > 0
            and type(client.get("recv_bytes")) is int and client["recv_bytes"] > 0,
            "NO_ACTUAL_CLIENT_RECV")
    require(case.get("endpoint", "").startswith("127.0.0.1:"),
            "NON_LOOPBACK_ENDPOINT")
    require(client.get("request_ns") is not None and
            type(client["request_ns"]) is int and
            type(client.get("first_recv_ns")) is int and
            client["request_ns"] <= client["first_recv_ns"],
            "CLIENT_CLOCK_OR_RECEIVE_INVALID")
    if mode == "positive":
        require(case.get("status") == "COMPLETE" and
                client.get("status") == "COMPLETE", "POSITIVE_NOT_COMPLETE")
        require(client.get("received_answer_sha256") == actual_source_sha and
                client.get("answer_length") == len(expected["answer_bytes"]),
                "CLIENT_ANSWER_BYTES_MISMATCH")
        first, terminal = client.get("first_data_ns"), client.get("terminal_ns")
        require(type(first) is int and type(terminal) is int and
                client["first_recv_ns"] <= first < terminal,
                "FIRST_TEXT_NOT_BEFORE_TERMINAL")
        require(_time(client.get("first_text_ms")) and
                _time(client.get("terminal_ms")) and
                client["first_text_ms"] < client["terminal_ms"],
                "FIRST_TEXT_DURATION_INVALID")
        require(client.get("answer_events", 0) > 0 and
                client.get("progress_events", 0) > 0,
                "NO_SUBSTANTIVE_CITED_EVENT")
        enqueue, flush = server.get("enqueue_ns"), server.get("flush_ns")
        require(isinstance(enqueue, list) and isinstance(flush, list) and
                bool(enqueue) and bool(flush) and
                enqueue[0] <= flush[0] <= server.get("terminal_ns", -1),
                "SERVER_ENQUEUE_FLUSH_INVALID")
    else:
        require(case.get("status") != "COMPLETE" and
                client.get("status") != "COMPLETE",
                "FAULT_IMPROPERLY_ACCEPTED")
        if mode == "progress_only":
            require(client.get("first_data_ns") is None,
                    "PROGRESS_SPOOFED_AS_FIRST_TEXT")
    return LocalReceipt(
        case_id=expected["case_id"] + "-" + mode, mode=mode,
        outcome="completed" if mode == "positive" else "fault_denied",
        client_pid=cp, server_pid=sp,
        source_revision=expected["source_revision"],
        source_sha256=actual_source_sha, citation_id=expected["citation_id"],
        answer_sha256=sha(expected["answer_bytes"]),
        first_text_ms=client.get("first_text_ms") if mode == "positive" else None,
        terminal_ms=client.get("terminal_ms") if mode == "positive" else None,
        answer_byte_count=len(expected["answer_bytes"]) if mode == "positive" else 0,
    )


def plan28() -> tuple[tuple[int, str], ...]:
    return tuple(
        [(i, "positive") for i in range(12)] +
        [(i % 12, mode) for i, mode in enumerate(i15.FAULT_MODES)]
    )


def execute_plan(
    worktree: Path, namespace: str, plan: Sequence[tuple[int, str]],
    attempt_log: Path | None = None,
) -> dict[str, Any]:
    _ns(namespace)
    require(1 <= len(plan) <= 28, "PLAN_SIZE_INVALID")
    for index, mode in plan:
        require(type(index) is int and 0 <= index < 12, "PLAN_INDEX_INVALID")
        require(mode == "positive" or mode in i15.FAULT_MODES,
                "PLAN_MODE_INVALID")
    require(len({(index, mode) for index, mode in plan}) == len(plan),
            "REPEATED_CASE_ID")
    # Local-only bounded boot-time recovery for a busy development host.
    # Keep the I15 module's canonical constants restored after the run.
    with _LOCAL_CASE_LOCK, patch.multiple(
        i15,
        BOOT_DEADLINE_SECONDS=LOCAL_BOOT_DEADLINE_SECONDS,
        CLIENT_DEADLINE_SECONDS=LOCAL_CLIENT_DEADLINE_SECONDS,
        SERVER_EXIT_DEADLINE_SECONDS=LOCAL_SERVER_EXIT_DEADLINE_SECONDS,
    ), ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(i15.run_case, worktree, index, mode, namespace)
            for index, mode in plan
        ]
        raw_cases = [f.result() for f in futures]
    if attempt_log is not None:
        require(attempt_log.is_absolute() and not attempt_log.is_symlink(),
                "ATTEMPT_LOG_PATH_INVALID")
        sanitized = [{
            "index": index, "mode": mode,
            "case_id": case.get("case_id"), "status": case.get("status"),
            "client_status": case.get("client", {}).get("status"),
            "server_status": case.get("server", {}).get("status"),
            "client_exit": case.get("diagnostics", {}).get("client_exit"),
            "server_exit": case.get("diagnostics", {}).get("server_exit"),
            "failure_stage": case.get("diagnostics", {}).get("failure_stage"),
            "client_pid": case.get("client", {}).get("client_pid"),
            "server_pid": case.get("server", {}).get("server_pid"),
        } for case, (index, mode) in zip(raw_cases, plan, strict=True)]
        attempt_log.write_text(
            json.dumps({"classification": "UNVERIFIED_LOCAL_ATTEMPTS",
                        "cases": sanitized}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        attempt_log.chmod(0o600)
    receipts = []
    for case, (index, mode) in zip(raw_cases, plan, strict=True):
        try:
            receipts.append(validate_case(case, index, mode, namespace))
        except LocalDenied as exc:
            raise LocalDenied(
                f"CASE_{index}_{mode}_{exc}:"
                f"{case.get('status')}:"
                f"{case.get('diagnostics', {}).get('failure_stage')}"
            ) from exc
    count = sum(r.outcome == "completed" for r in receipts)
    faults = len(receipts) - count
    denominator = i15.denominator(raw_cases)
    counts_valid = (
        denominator["total"] == len(receipts) and
        denominator["completed"] == count and
        denominator["failure_or_abstention"] == faults
    )
    require(
        counts_valid and (faults == 0 or
                          denominator["first_text_p95_ms"] is None),
        "DENOMINATOR_FAILED_CLOSED",
    )
    return {
        "plan_total": len(receipts), "completed": count, "fault_denied": faults,
        "official_p95": None, "fixture": True,
        "process_limit": i15.PROCESS_CHILD_LIMIT,
        "denominator": denominator,
        "cases": [asdict(r) for r in receipts],
    }


def p17_denial_only(worktree: Path, scratch: Path) -> DenialReceipt:
    """P17 creates a real digest-bound *denial* receipt from missing rights.

    No trust registry is provisioned, no external artifact is ever inspected.
    """
    _scratch(worktree, scratch)
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch.chmod(0o700)
    ingress = scratch / "l21-synthetic-no-external-rights"
    ingress.mkdir(mode=0o700, exist_ok=True)
    ingress.chmod(0o700)
    manifest = {
        "schema": p17.SCHEMA,
        "subject": "l21-local-fixture", "run_id": "l21-fixture-run",
        "grant_id": "l21-no-external-grant", "host_id": "l21-local-host",
        "candidate_commit": "f" * 40,
        "candidate_image_sha256": "0" * 64,
        "artifacts": [],
    }
    manifest_path = ingress / "manifest.json"
    require(not manifest_path.is_symlink(), "MANIFEST_SYMLINK_DENIED")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    receipt_dir = scratch / "l21-denial-receipt"
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = p17.main([
            "inspect", "--ingress-root", str(ingress),
            "--manifest", "manifest.json", "--scratch", str(receipt_dir),
        ])
    try:
        envelope = json.loads(stdout.getvalue())
    except ValueError as exc:
        raise LocalDenied("P17_RESPONSE_NOT_JSON") from exc
    require(code == p17.EXIT_AUTHORITY_DENIED and
            envelope.get("decision") == p17.CLI_DENIED and
            envelope.get("original523") == p17.e15.REJECT_523 and
            envelope.get("ar09_phase_b") == p17.e15.REJECT_B and
            envelope.get("official_cited_gate_pass") is False and
            envelope.get("may_execute_official_evaluation") is False and
            envelope.get("transport_ok") is True and
            envelope.get("receipt_written") is True,
            "P17_DENIAL_CONTRACT_VIOLATION")
    receipt_file = receipt_dir / "P16_REQUEST_RECEIPT.json"
    declared_sha = envelope.get("receipt_sha256", "")
    require(type(declared_sha) is str and
            bool(SHA_PATTERN.fullmatch(declared_sha)) and
            envelope.get("receipt_path") == str(receipt_file) and
            not receipt_file.is_symlink() and
            p17.validate_denial_receipt(receipt_file, declared_sha),
            "P17_DENIAL_RECEIPT_DIGEST_OR_SHAPE_INVALID")
    actual = sha(receipt_file.read_bytes())
    require(actual == declared_sha, "P17_RECEIPT_REHASH_MISMATCH")
    return DenialReceipt(
        decision=p17.CLI_DENIED, exit_code=code, validated=True,
        receipt_sha256=declared_sha, actual_file_sha256=actual,
        original523=p17.e15.REJECT_523, phase_b=p17.e15.REJECT_B,
    )


def run(worktree: Path, scratch: Path, namespace: str) -> dict[str, Any]:
    _scratch(worktree, scratch)
    _ns(namespace)
    denial = p17_denial_only(worktree, scratch)
    outcomes = execute_plan(
        worktree, namespace, plan28(),
        attempt_log=scratch / "L21_UNVERIFIED_ATTEMPTS.json",
    )
    require(
        outcomes["plan_total"] == 28 and outcomes["completed"] == 12 and
        outcomes["fault_denied"] == 16 and
        outcomes["denominator"]["first_text_p95_ms"] is None,
        "28_CASE_EXPLORATION_INCOMPLETE",
    )
    report = {
        "version": VERSION, "status": STATUS, "staging_only": True,
        "worktree": str(worktree), "namespace": namespace,
        "p17_denial": asdict(denial), "outcomes": outcomes,
        "external_evidence_authorized": False,
        "may_execute_official_evaluation": False,
        "release_authorized": False, "restrictions": RESTRICTIONS,
    }
    raw = (json.dumps(report, ensure_ascii=False, indent=2,
                      sort_keys=True, allow_nan=False) + "\n").encode()
    output = scratch / "L21_EXPLORATORY_INTEGRATION_RECEIPT.json"
    output.write_bytes(raw)
    output.chmod(0o600)
    return {
        "status": STATUS, "receipt_path": str(output), "receipt_sha256": sha(raw),
        "completed": 12, "fault_denied": 16, "denominator": outcomes["denominator"],
        "p17_denial_sha256": denial.receipt_sha256,
        "may_execute_official_evaluation": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LOCAL synthetic fixture-only L21")
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--namespace", default="l21-local")
    args = parser.parse_args(argv)
    try:
        result = run(args.worktree, args.scratch, args.namespace)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (LocalDenied, i15.I15Denied, OSError, ValueError, TypeError) as exc:
        code = str(exc) if isinstance(exc, LocalDenied) else type(exc).__name__
        print(json.dumps({"status": DENIED, "reason": code,
                          "release_authorized": False,
                          "may_execute_official_evaluation": False}))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
