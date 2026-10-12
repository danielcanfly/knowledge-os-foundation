"""I25 four-lane preintegration, intentionally SYNTHETIC and nonproduction.

Combines I23 external OS loopback receipts with C24 client-side SSE observation,
and P24/E24/B24 independent admission boundaries. No protected original tests,
real provider, unseen cases, credential or release authority are accessed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from knowledge_engine import m27_w5_b24_blind200_admission_v1_experimental as b24
from knowledge_engine import m27_w5_c24_client_observation_v1_experimental as c24
from knowledge_engine import m27_w5_e24_original523_evidence_scorer_v1_experimental as e24
from knowledge_engine import m27_w5_i23_n22_l22_combined_local_runtime_v1_experimental as i23
from knowledge_engine import m27_w5_p24_p16_b13_witness_gate_v1_experimental as p24

PASS = "I25_FOUR_LANE_NONPROD_STAGING_PASS"
FAIL = "I25_FOUR_LANE_NONPROD_STAGING_NOT_VERIFIED"
ORIGINS = {
    "p24": "e7dedb59bd36ea958842eecc1701c2cdc424dbec",
    "c24": "a066e8aee307fcfec076a5cdd25e1741a8150000",
    "e24": "55df1671aeba619204a606a099855ba313cb5831",
    "b24": "ae07ba08692335e07b25f8a4a8825c5416ab7690",
}
SUFFIXES = {
    "p24": "m27_w5_p24_p16_b13_witness_gate_v1",
    "c24": "m27_w5_c24_client_observation_v1",
    "e24": "m27_w5_e24_original523_evidence_scorer_v1",
    "b24": "m27_w5_b24_blind200_admission_v1",
}
PATHS = {
    "p24": ("src/knowledge_engine/m27_w5_p24_p16_b13_witness_gate_v1_experimental.py",
            "tests/test_m27_w5_p24_p16_b13_witness_gate_v1_experimental.py",
            "docs/m27/m27_w5_p24_p16_b13_witness_gate_v1.md"),
    "c24": ("src/knowledge_engine/m27_w5_c24_client_observation_v1_experimental.py",
            "tests/test_m27_w5_c24_client_observation_v1_experimental.py",
            "docs/m27/m27_w5_c24_client_observation_v1.md"),
    "e24": ("src/knowledge_engine/m27_w5_e24_original523_evidence_scorer_v1_experimental.py",
            "tests/test_m27_w5_e24_original523_evidence_scorer_v1_experimental.py",
            "docs/m27/m27_w5_e24_original523_evidence_scorer_v1.md"),
    "b24": ("src/knowledge_engine/m27_w5_b24_blind200_admission_v1_experimental.py",
            "tests/test_m27_w5_b24_blind200_admission_v1_experimental.py",
            "docs/m27/m27_w5_b24_blind200_admission_v1.md"),
}
GATES = {
    "P16_ORIGINAL_PASS": False, "B13_ORIGINAL_PASS": False,
    "M16_CANONICAL_ACCEPTED": False, "OFFICIAL_523_PASS": False,
    "PHASE_B200_OFFICIAL_PASS": False, "REAL_APP_CLIENT_P95_PASS": False,
    "W5_FULL_COMPLETE": False, "W6_AUTHORIZED": False,
    "REL01_CERTIFIED": False, "REL02_AUTHORIZED": False,
    "PRODUCTION_AUTHORIZED": False,
}


class IntegrationDenied(ValueError):
    """A specific unverified, nonproduction integration boundary."""


def need(ok: bool, why: str) -> None:
    if not ok:
        raise IntegrationDenied(why)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attest_four_origins(worktree: Path) -> dict[str, dict[str, str]]:
    """Verify physical bytes against ORIGINAL committed Git blobs; no source edits."""
    need(worktree.is_dir() and not worktree.is_symlink(), "WORKTREE_INVALID")
    pins: dict[str, dict[str, str]] = {}
    for lane, commit in ORIGINS.items():
        paths: dict[str, str] = {}
        for relative in PATHS[lane]:
            file = worktree / relative
            need(file.is_file() and not file.is_symlink(), "MISSING_OR_LINK:" + relative)
            raw = file.read_bytes()
            command = ["git", "-C", str(worktree), "show", commit + ":" + relative]
            result = subprocess.run(command, capture_output=True, timeout=15, check=False)
            need(result.returncode == 0, "ORIGIN_GIT_BLOB_MISSING:" + lane)
            need(result.stdout == raw, "ORIGIN_BYTES_DIFFER:" + lane)
            paths[relative] = digest(raw)
        pins[lane] = paths
    return pins


def authority_boundaries() -> dict[str, dict]:
    """Real module entrypoints, intentionally no fabricated signer/holdout grants."""
    witness = p24.verify_existing_witness(None, None)
    need(witness["decision"] == p24.STATUS_UNVERIFIED
         and witness["original_p16_pass"] is False
         and witness["original_b13_pass"] is False, "P24_UNSAFE_PROMOTION")
    phase = b24.admit({}, {}, pinned_root_sha256=None)
    need(phase["admission"] == b24.NOT_ADMITTED
         and phase["evaluation"] == b24.NOT_EXECUTED
         and phase["official_score"] is None, "B24_UNSAFE_PROMOTION")
    try:
        e24.trusted_roots({}, "0" * 64)
    except e24.Denied as exc:
        scorer = {"status": "OFFICIAL_523_NOT_RUN_EVALUATOR_RIGHTS_NOT_ESTABLISHED",
                  "reason": exc.reason}
    else:
        raise IntegrationDenied("E24_ACCEPTED_UNPINNED_REGISTRY")
    observation = c24.independent_custody({}, None, None, None)
    need(observation["status"] == c24.UNKNOWN, "C24_UNAUTHENTICATED_ACK")
    return {"p24": witness, "b24": phase, "e24": scorer,
            "c24": observation}


def c24_physical_client(worktree: Path, scratch: Path, *,
                        corrupt: str | None = None) -> dict:
    """Actual child-process TCP recv, real SSE fragment parsing, fixture source only."""
    need(corrupt in (None, "citation", "terminal", "progress_only"),
         "CORRUPTION_MODE_INVALID")
    need(scratch.is_dir() and not scratch.is_symlink(), "SCRATCH_INVALID")
    document = b"I25 permitted synthetic source evidence."
    answer = "Cited local synthetic text"
    encoded = answer.encode("utf-8")
    stamp = digest(document)
    runner = digest(b"I25 synthetic runner")
    image = digest(b"I25 synthetic candidate")
    case = c24.CasePlan("i25-local-01", "i25-request-01", "i25-nonce-01",
                        runner, image, True)
    src = c24.SourcePin("fixture-citation", "fixture-source", "rev-1",
                        stamp, document, authorized=True)
    citation = {
        "citation_id": src.citation_id, "source_id": src.source_id,
        "revision": src.revision, "source_sha256": src.source_sha256,
        "source_start": 0, "source_end": 3,
        "quote_sha256": digest(document[:3]),
        "answer_start": 0, "answer_end": len(encoded),
    }
    if corrupt == "citation":
        citation["quote_sha256"] = "0" * 64
    idents = {key: getattr(case, key) for key in c24.IDENTITY}
    events = [
        c24.make_test_frame("progress", {**idents, "phase": "preparing"}),
    ]
    if corrupt != "progress_only":
        events.append(c24.make_test_frame("answer", {
            **idents, "sequence": 0, "start": 0, "end": len(encoded),
            "text": answer, "sha256": digest(encoded), "citations": [citation],
        }))
        if corrupt != "terminal":
            events.append(c24.make_test_frame("terminal", {
                **idents, "status": "completed", "answer_bytes": len(encoded),
                "answer_sha256": digest(encoded),
            }))
    plan = scratch / "I25_C24_CLIENT_PLAN_PRIVATE.json"
    output = scratch / "I25_C24_CLIENT_RECEIPT_PRIVATE.json"
    metadata = {"plan": vars(case), "source": {
        "citation_id": src.citation_id, "source_id": src.source_id,
        "revision": src.revision, "source_sha256": src.source_sha256,
        "bytes_b64": base64.b64encode(document).decode(),
        "revoked": False, "authorized": True,
    }}
    plan.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    plan.chmod(0o600)
    server_errors: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(15)
        port = server.getsockname()[1]

        def serve() -> None:
            try:
                with server.accept()[0] as connection:
                    connection.settimeout(5)
                    request = connection.recv(4096)
                    if not request.startswith(b"GET /synthetic HTTP/1.1"):
                        server_errors.append("UNEXPECTED_HTTP_REQUEST")
                        return
                    connection.sendall(
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: text/event-stream; charset=utf-8\r\n\r\n"
                    )
                    for event in events:
                        time.sleep(.025)
                        try:
                            connection.sendall(event)
                        except (BrokenPipeError, ConnectionResetError):
                            if corrupt is None:
                                server_errors.append("EARLY_CLIENT_DISCONNECT")
                            break
            except OSError as exc:
                server_errors.append(type(exc).__name__)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        env = {**os.environ, "PYTHONPATH": str(worktree / "src")}
        cmd = [sys.executable, "-m",
               "knowledge_engine.m27_w5_c24_client_observation_v1_experimental",
               "--synthetic-loopback-port", str(port), "--plan-json", str(plan),
               "--output", str(output)]
        child = subprocess.run(cmd, cwd=worktree, env=env, capture_output=True,
                               timeout=20, check=False)
        thread.join(timeout=6)
    need(not thread.is_alive() and not server_errors, "C24_SOCKET_SERVER_FAULT")
    need(output.is_file(), "C24_CHILD_RECEIPT_MISSING")
    raw = output.read_bytes()
    receipt = json.loads(raw)
    expected_complete = corrupt is None
    need((child.returncode == 0) == expected_complete, "C24_CHILD_EXIT_CONTRACT")
    need((receipt.get("status") == "COMPLETE") == expected_complete,
         "C24_RECEIPT_STATUS_CONTRACT")
    need(receipt.get("synthetic") is True
         and receipt["custody"]["status"] == c24.UNKNOWN
         and receipt["official_qualified"] is False
         and receipt["w5_full_complete"] is False, "C24_FAKE_EXTERNAL_AUTHORITY")
    if expected_complete:
        need(receipt["answer_sha256"] == digest(encoded)
             and receipt["answer_bytes"] == len(encoded)
             and receipt["source_native_citations"][0]["quote_sha256"]
             == digest(document[:3])
             and receipt["first_substantive_text_ns"] < receipt["terminal_ns"]
             and receipt["recv_calls"] > 1 and receipt["client_pid"] != os.getpid(),
             "C24_NO_REAL_CITED_CLIENT_BYTES")
    return {"status": receipt["status"], "client_pid": receipt["client_pid"],
            "parent_pid": os.getpid(), "exit_code": child.returncode,
            "wire_sha256": receipt["wire_transcript_sha256"], "receipt_sha256": digest(raw),
            "recv_calls": receipt["recv_calls"],
            "first_text_ns": receipt["first_substantive_text_ns"],
            "terminal_ns": receipt["terminal_ns"],
            "official_qualified": False, "synthetic": True, "fault": corrupt,
            "stdout_sha256": digest(child.stdout), "stderr_sha256": digest(child.stderr)}


def run(worktree: Path, scratch: Path, namespace: str) -> dict:
    need(worktree.is_absolute() and scratch.is_absolute(), "PATHS_NOT_ABSOLUTE")
    need(not scratch.is_symlink() and not scratch.resolve().is_relative_to(worktree.resolve()),
         "SCRATCH_WITHIN_GIT_OR_SYMLINK")
    need(1 <= len(namespace) <= 20, "NAMESPACE_INVALID")
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    scratch.chmod(0o700)
    outcomes: dict[str, object] = {}
    problems: list[str] = []
    try:
        outcomes["source_origins"] = attest_four_origins(worktree)
        outcomes["i23_sources"] = i23.attest_sources(worktree)
        outcomes["external_gates"] = authority_boundaries()
        outcomes["c24_client"] = c24_physical_client(worktree, scratch)
    except (IntegrationDenied, c24.ObservationDenied, OSError, ValueError,
            KeyError, subprocess.TimeoutExpired) as exc:
        problems.append("PRE:" + type(exc).__name__ + ":" + str(exc)[:130])
    if not problems:
        try:
            actual = i23.run(worktree, scratch / "i23_physical",
                             namespace + "-i25")
            outcomes["i23"] = actual
            need(actual["status"] == i23.PASS, "I23_PHYSICAL_28_SIX_LATE_FAILED")
            raw = json.loads(Path(actual["receipt_path"]).read_bytes())
            need(raw.get("outcomes", {}).get("n22_audited", {}).get("completed") == 12
                 and raw["outcomes"]["n22_audited"]["expected_denied"] == 16
                 and raw["outcomes"]["l22_six"]["completed"] == 3
                 and raw["outcomes"]["l22_six"]["expected_denied"] == 3
                 and raw["outcomes"]["l22_delayed"]["delay_elapsed_ms"] >= 4500,
                 "I23_LOCAL_COHORT_COUNTS_INVALID")
        except (IntegrationDenied, i23.CombinedDenied, OSError, ValueError,
                KeyError, TypeError) as exc:
            problems.append("I23:" + type(exc).__name__ + ":" + str(exc)[:130])
    status = FAIL if problems else PASS
    result = {"version": "m27.w5.i25.four_lane_nonprod.v1", "status": status,
              "fixture_only": True, "verified_source_lanes": list(ORIGINS),
              "source_parent": "52c18e9979ec24dedaed35cae4ca8690d8dfddcd",
              "sources": ORIGINS, "outcomes": outcomes, "problems": problems,
              "gates": GATES, "real_app_client_p95_ms": None,
              "real_provider_calls": 0}
    data = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    path = scratch / "I25_FOUR_LANE_RECEIPT.json"
    path.write_bytes(data)
    path.chmod(0o600)
    return {"status": status, "receipt_path": str(path), "sha256": digest(data),
            "problems": problems, "gates": GATES}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="I25 local-only four-lane engineering")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--namespace", default="i25-four")
    a = parser.parse_args(argv)
    try:
        receipt = run(a.worktree, a.scratch, a.namespace)
    except (IntegrationDenied, OSError, ValueError, KeyError) as exc:
        receipt = {"status": FAIL, "reason": type(exc).__name__ + ":" + str(exc)[:140],
                   "gates": GATES}
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == PASS else 20


if __name__ == "__main__":
    raise SystemExit(main())
