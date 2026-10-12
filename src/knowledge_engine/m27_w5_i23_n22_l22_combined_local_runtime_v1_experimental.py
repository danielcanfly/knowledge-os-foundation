"""I23 independently audited N22 external TCP + L22 bounded local-process fixture.

Only isolated synthetic 127.0.0.1. No external source rights or product SLO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15
from knowledge_engine import m27_w5_l21_staging_combined_local_runtime_v1_experimental as l22
from knowledge_engine import m27_w5_n21_independent_local_client_v1_experimental as n22

PASS = "I23_COMBINED_NONPROD_LOCAL_ENGINEERING_PASS"
FAIL = "I23_COMBINED_NONPROD_LOCAL_NOT_VERIFIED"
EXPECTED_PYTHON = "/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python"
# Independently recorded physical SHA256 of Q22 committed source, tests, docs.
_PINNED_FILES = (
    "src/knowledge_engine/m27_w5_n21_independent_local_client_v1_experimental.py",
    "tests/test_m27_w5_n21_independent_local_client_v1_experimental.py",
    "docs/m27/m27_w5_n21_independent_local_client_v1_receipts.md",
    "src/knowledge_engine/m27_w5_i15_native_local_client_integration_v1_experimental.py",
    "src/knowledge_engine/m27_w5_l21_staging_combined_local_runtime_v1_experimental.py",
    "tests/test_m27_w5_l21_staging_combined_local_runtime_v1_experimental.py",
    "docs/W5_L21_EXPLORATORY_COMBINED_RUNTIME_V1_EXPERIMENTAL.md",
)
_PINNED_DIGESTS = (
    "bdec2047321de97f1e75b4683e46214fe464e2d6d16dfa9c0afc2ad580a0a717",
    "b5df142f73c40df021f9f1ea55327441bf4688bfd59645357ca6f4056ac5f3ad",
    "f657345b42ee21a62de25fc97062359e5117053228b27cd7ce51469782aaefa7",
    "f96ba03a57a21f7a0b76dafdcb7c44ff89dbab6e32e016dad9466964560d5b40",
    "25d44943c956b89ca45018e756b80d7fd2e6453c5e85cf28aa79eaf74e9b14d4",
    "5fd65e7b16d2bad6ad4046e4731057f5dfbab6aa81f17e09a9ee3b24ebee016b",
    "8294267cce13d5a51954da397a6eadb88cd0e3eeb0363bb1230d32397566ffca",
)
PINNED = dict(zip(_PINNED_FILES, _PINNED_DIGESTS, strict=True))
MIXED = [(0, "positive"), (1, "positive"), (2, "wrong_tenant"),
         (3, "server_500"), (4, "positive"), (5, "progress_only")]


class CombinedDenied(ValueError):
    """Fail-closed combined fixture contract."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise CombinedDenied(reason)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def attest_sources(worktree: Path) -> dict[str, str]:
    require(worktree.is_absolute() and worktree.is_dir(), "WORKTREE_INVALID")
    require(i15.PYTHON == EXPECTED_PYTHON, "PYTHON_NOT_PINNED")
    require(n22.CLIENT_PREWARM_DEADLINE_SECONDS == 24.0
            and n22.SERVER_BOOT_DEADLINE_SECONDS == 24.0,
            "N22_24S_READINESS_NOT_BOUNDED")
    require(i15.LOCAL_SERVER_ACCEPT_DEADLINE_SECONDS == 20.0
            and l22.LOCAL_BOOT_DEADLINE_SECONDS == 24.0
            and l22.LOCAL_CLIENT_DEADLINE_SECONDS == 24.0
            and l22.LOCAL_SERVER_EXIT_DEADLINE_SECONDS == 16.0,
            "L22_20S_FIXTURE_ACCEPT_NOT_BOUNDED")
    found = {}
    for rel, expected in PINNED.items():
        path = worktree / rel
        require(path.is_file() and not path.is_symlink(), "SOURCE_MISSING_OR_LINK:" + rel)
        found[rel] = sha(path.read_bytes())
        require(found[rel] == expected, "SOURCE_SHA_MISMATCH:" + rel)
    return found


def audit_n22(receipt: dict, namespace: str) -> dict:
    require(type(receipt) is dict, "N22_RECEIPT_NOT_OBJECT")
    cases = receipt.get("cases")
    require(type(cases) is list and len(cases) == 28, "N22_MISSING_CASES")
    require(receipt.get("status") == n22.PASS and receipt.get("fixture") is True,
            "N22_NOT_VERIFIED")
    require(receipt.get("attempted") == 28 and receipt.get("completed") == 12
            and receipt.get("rejected_or_failed") == 16
            and receipt.get("expected_positive") == 12
            and receipt.get("expected_negative") == 16
            and receipt.get("positive_valid") is True
            and receipt.get("negative_valid") is True, "N22_COUNT_OR_VALIDITY")
    require(receipt.get("first_text_p95_ms") is None
            and receipt.get("full_answer_p95_ms") is None
            and receipt.get("terminal_p95_ms") is None
            and receipt.get("denominator_status") == "UNKNOWN_HAS_FAILURES",
            "N22_INVALID_FULL_DENOMINATOR")
    plan = [(i, "positive") for i in range(12)]
    plan += [(i % 12, mode) for i, mode in enumerate(i15.FAULT_MODES)]
    require(len(plan) == 28 and len({c["case_id"] for c in cases}) == 28,
            "N22_CASE_DUPLICATE")
    positive = 0
    denied = 0
    for (index, mode), item in zip(plan, cases, strict=True):
        spec = i15.spec(index, namespace)
        require(item.get("mode") == mode
                and item.get("case_id") == spec["case_id"] + "-" + mode
                and item.get("source_sha256") == spec["source_sha256"]
                and item.get("source_revision") == spec["source_revision"]
                and item.get("expected_answer_sha256") == spec["answer_sha256"],
                "N22_CASE_SOURCE_OR_ORDER_INVALID")
        client = item.get("client", {})
        server = item.get("server", {})
        cleanup = item.get("cleanup", {})
        require(type(item.get("server_pid")) is int
                and type(item.get("client_pid")) is int
                and item["server_pid"] != item["client_pid"]
                and item["server_pid"] > 0 and item["client_pid"] > 0,
                "N22_INDEPENDENT_PID_INVALID")
        require(client.get("client_pid") == item["client_pid"]
                and server.get("server_pid") == item["server_pid"],
                "N22_PID_RECEIPT_INVALID")
        require(isinstance(item.get("endpoint"), str)
                and item["endpoint"].startswith("127.0.0.1:"),
                "N22_NOT_LOOPBACK")
        require(cleanup.get("client", {}).get("reaped") is True
                and cleanup.get("server", {}).get("reaped") is True,
                "N22_CHILD_NOT_REAPED")
        require(item.get("client_prewarm_deadline_s") == 24.0
                and item.get("server_boot_deadline_s") == 24.0,
                "N22_DEADLINE_INVALID")
        if mode == "positive":
            require(item.get("status") == "COMPLETE"
                    and client.get("status") == "COMPLETE"
                    and client.get("received_digest") == spec["answer_sha256"]
                    and client.get("received_bytes") == len(spec["answer_bytes"])
                    and type(client.get("recv_calls")) is int
                    and client["recv_calls"] > 0
                    and client.get("answer_events", 0) > 0
                    and client.get("progress_events", 0) > 0
                    and all(type(client.get(k)) is int for k in (
                        "request_sent_ns", "first_recv_ns", "first_answer_ns",
                        "full_answer_ns", "terminal_ns"
                    ))
                    and client["request_sent_ns"] <= client["first_recv_ns"]
                    <= client["first_answer_ns"]
                    <= client["full_answer_ns"] < client["terminal_ns"],
                    "N22_POSITIVE_NO_CITED_PRETERMINAL_BYTES")
            positive += 1
        else:
            require(item.get("status") != "COMPLETE"
                    and client.get("status") != "COMPLETE",
                    "N22_EXPECTED_FAULT_BECAME_COMPLETED")
            if mode == "progress_only":
                require(client.get("first_answer_ns") is None,
                        "N22_PROGRESS_ONLY_SPOOF")
            denied += 1
    require(positive == 12 and denied == 16, "N22_12_16_INVALID")
    return {"attempted": 28, "completed": positive, "expected_denied": denied,
            "independent_os_pids": True, "source_pinned": True,
            "preterminal_cited_utf8_received": True, "all_outcome_p95": None}


def audit_l22_six(result: dict) -> dict:
    require(result.get("plan_total") == 6 and result.get("completed") == 3
            and result.get("fault_denied") == 3 and result.get("fixture") is True
            and result.get("official_p95") is None
            and result.get("denominator", {}).get("first_text_p95_ms") is None,
            "L22_SIX_OUTCOME_COUNTS")
    cases = result.get("cases", [])
    require(len(cases) == 6 and
            all(c.get("synthetic_only") is True for c in cases),
            "L22_SIX_NOT_SYNTHETIC")
    require(all(c.get("client_pid") != c.get("server_pid") for c in cases),
            "L22_SIX_NOT_SEPARATE_PROCESSES")
    return {"attempted": 6, "completed": 3, "expected_denied": 3,
            "all_outcome_p95": None}


def actual_delayed_client(worktree: Path, namespace: str) -> dict:
    original_env = i15._child_env

    def delayed_env(path: Path) -> dict:
        env = original_env(path)
        env["M27_L22_SYNTHETIC_DELAY_CONNECT"] = "5"
        return env

    with l22._LOCAL_CASE_LOCK, patch.object(i15, "_child_env", delayed_env), patch.multiple(
        i15, BOOT_DEADLINE_SECONDS=24.0, CLIENT_DEADLINE_SECONDS=24.0,
        SERVER_EXIT_DEADLINE_SECONDS=16.0,
    ):
        raw = i15.run_case(worktree, 0, "positive", namespace)
    validated = l22.validate_case(raw, 0, "positive", namespace)
    client = raw["client"]
    require(raw["status"] == "COMPLETE" and validated.outcome == "completed"
            and client["recv_calls"] > 0
            and client["connect_start_ns"] - client["client_spawn_ns"] >= 4_500_000_000
            and client["first_data_ns"] < client["terminal_ns"]
            and raw["diagnostics"]["cleanup"]["client"]["reaped"]
            and raw["diagnostics"]["cleanup"]["server"]["reaped"],
            "L22_DELAYED_REAL_CLIENT_INVALID")
    return {"status": "PASS", "delay_seconds_requested": 5,
            "client_pid": client["client_pid"],
            "server_pid": raw["server"]["server_pid"],
            "delay_elapsed_ms": round(
                (client["connect_start_ns"] - client["client_spawn_ns"]) / 1e6, 3),
            "receive_calls": client["recv_calls"],
            "preterminal_utf8_sha256": client["received_answer_sha256"],
            "source_sha256": i15.spec(0, namespace)["source_sha256"],
            "reaped_both": True}


def run(worktree: Path, scratch: Path, namespace: str) -> dict:
    require(scratch.is_absolute() and not scratch.is_symlink()
            and not scratch.resolve().is_relative_to(worktree.resolve()),
            "SCRATCH_UNSAFE")
    i15.spec(0, namespace)
    require(len(namespace) <= 28, "NAMESPACE_TOO_LONG")
    pins = attest_sources(worktree)
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    scratch.chmod(0o700)
    outcomes: dict = {}
    errors: list[str] = []
    started = time.monotonic()
    # Execute every N22 case even if expected denial or startup failure occurs.
    try:
        n22_summary = n22.suite(worktree, scratch / "n22", namespace)
        n22_path = Path(n22_summary["path"])
        n22_bytes = n22_path.read_bytes()
        require(sha(n22_bytes) == n22_summary["sha256"], "N22_RECEIPT_DIGEST")
        n22_receipt = json.loads(n22_bytes)
        outcomes["n22_raw"] = n22_summary
        outcomes["n22_audited"] = audit_n22(n22_receipt, namespace)
    except (CombinedDenied, n22.Denied, i15.I15Denied, OSError,
            ValueError, KeyError, TypeError) as exc:
        errors.append("N22:" + type(exc).__name__ + ":" + str(exc)[:160])
    # Separate 2-worker overlap and three bounded fault injections.
    try:
        six = l22.execute_plan(
            worktree, namespace + "-mix", MIXED,
            attempt_log=scratch / "L22_SIX_RAW_ATTEMPTS.json",
        )
        outcomes["l22_six"] = audit_l22_six(six)
    except (CombinedDenied, l22.LocalDenied, i15.I15Denied, OSError,
            ValueError, KeyError, TypeError) as exc:
        errors.append("L22_MIX:" + type(exc).__name__ + ":" + str(exc)[:160])
    # Distinct physical 5-second late OS client; not a mocked socket/clock.
    try:
        outcomes["l22_delayed"] = actual_delayed_client(worktree, namespace + "-late")
    except (CombinedDenied, l22.LocalDenied, i15.I15Denied, OSError,
            ValueError, KeyError, TypeError) as exc:
        errors.append("L22_DELAY:" + type(exc).__name__ + ":" + str(exc)[:160])
    require(set(outcomes).issuperset({"n22_raw"}) or bool(errors),
            "NO_REAL_OUTCOME")
    status = PASS if not errors and len(outcomes) == 4 else FAIL
    result = {
        "version": "W5I23CombinedLocalRuntimeV1",
        "status": status, "fixture_only": True,
        "namespace": namespace, "worktree": str(worktree),
        "source_sha256": pins, "outcomes": outcomes, "errors": errors,
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "official_product_p95": None, "all_outcome_p95": None,
        "original523_admitted": False, "phase_b_admitted": False,
        "external_source_rights": False, "authenticated_app_ack": False,
        "canonical_m16_accepted": False, "w5_full_complete": False,
        "w6_release_production_authorized": False,
    }
    blob = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    path = scratch / "I23_COMBINED_RECEIPT.json"
    path.write_bytes(blob)
    path.chmod(0o600)
    return {"status": status, "receipt_path": str(path), "sha256": sha(blob),
            "n22": outcomes.get("n22_raw"), "l22_six": outcomes.get("l22_six"),
            "l22_delayed": outcomes.get("l22_delayed"), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="I23 local nonproduction integration")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--namespace", default="i23-local")
    args = parser.parse_args()
    try:
        result = run(args.worktree, args.scratch, args.namespace)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if result["status"] == PASS else 20
    except (CombinedDenied, n22.Denied, l22.LocalDenied,
            i15.I15Denied, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": FAIL,
                          "reason": type(exc).__name__ + ":" + str(exc)[:160],
                          "w5_full_complete": False}, sort_keys=True))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
