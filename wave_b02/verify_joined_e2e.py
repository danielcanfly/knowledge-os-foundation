#!/usr/bin/env python3
"""Independent, offline verification of the B02 joined E2E evidence chain."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

from wave_b02.joined_core import A05_SOURCE, a06_projection, contract_hash


REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).resolve().parent / "joined_evidence_v2"
HISTORY = Path(__file__).resolve().parent / "joined_history"
EXPECTED = {
    "positive_crash_reconcile_rollback": "succeeded",
    "wrong_acl": "denied",
    "stale_source": "denied",
    "revoked_source": "denied",
    "source_byte_tamper": "denied",
    "citation_span_tamper": "denied",
    "unauthorized_action": "denied",
    "exhausted_budget": "denied",
    "missing_verified_text": "denied",
    "invalid_verified_text": "denied",
    "timeout": "timeout",
    "cancel": "cancelled",
    "unknown_unresolved": "held_unknown",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require(value: bool, code: str) -> None:
    if not value:
        raise AssertionError(code)


def terminal(receipt: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in receipt["events"] if row["event"] == "run.terminal"]
    require(len(rows) == 1, "TERMINAL_COUNT")
    return rows[0]


def verify_model(run_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    claim = next(row for row in receipt["events"] if row["event"] == "claim.verified")
    audit = load(EVIDENCE / "server_runs" / run_id / "MODEL_AUDIT.json")
    selected = next(row for row in audit["attempts"]
                    if row["attempt"] == audit["selected_attempt"])
    require(selected["actual_local_model"] is True, "MODEL_NOT_LOCAL")
    require(selected["external_provider_calls"] == 0, "EXTERNAL_PROVIDER_USED")
    require(selected["billable_provider_calls"] == 0, "BILLABLE_PROVIDER_USED")
    require(selected["output"] == claim["text"], "MODEL_TEXT_BYTES")
    require(selected["output_sha256"] == claim["text_sha256"], "MODEL_TEXT_DIGEST")
    require(selected["model_sha256"] ==
            "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
            "MODEL_PIN")
    return {"output_sha256": selected["output_sha256"],
            "duration_ms": selected["duration_ms"], "pid": selected["pid"]}


def verify_action(run_id: str, *, unknown: bool) -> dict[str, Any]:
    root = EVIDENCE / "server_runs" / run_id
    action = load(root / "A06_ACTION_RECEIPT.json")
    by_name = {row["name"]: row for row in action["receipts"]}
    require(by_name["crash_after_effect"]["exit_code"] == 73, "CRASH_EXIT")
    require(len({row["pid"] for row in action["receipts"]}) == len(action["receipts"]),
            "CHILD_PID_REUSE")
    db_path = root / "a06_action" / "journal.sqlite"
    with sqlite3.connect(db_path) as db:
        require(db.execute("pragma integrity_check").fetchone()[0] == "ok", "SQLITE_INTEGRITY")
        tables = [row[0] for row in db.execute(
            "select name from sqlite_master where type='table' order by name")]
    require(bool(tables), "SQLITE_EMPTY")
    if unknown:
        require(action["status"] == "UNKNOWN_EFFECT_RECONCILE_REQUIRED", "UNKNOWN_STATUS")
        require(action["physical_retry_count"] == 0, "UNKNOWN_RETRIED")
        require(by_name["resume_unknown_hold"]["exit_code"] in (1, 2), "UNKNOWN_RESUME")
        require(action["action_ledger"][1] == "UNKNOWN", "UNKNOWN_LEDGER")
    else:
        require(action["status"] == "RECONCILED_AND_ROLLED_BACK", "ACTION_STATUS")
        require(action["physical_attempts"] == 1, "ACTION_ATTEMPTS")
        require(action["a06_stage"] == "VERIFIED", "ACTION_STAGE")
        require(action["action_ledger"][1] == "ROLLED_BACK", "ROLLBACK_LEDGER")
        require(action["after_rollback"] == {"observation": "idle", "revision": 0},
                "ROLLBACK_STATE")
    return {"receipt_sha256": digest(root / "A06_ACTION_RECEIPT.json"),
            "sqlite_sha256": digest(db_path), "sqlite_tables": tables}


def current_inventory() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(EVIDENCE.rglob("*")):
        if path.is_file() and path.name != "JOINED_ARTIFACT_INVENTORY.json":
            rows.append({"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size,
                         "sha256": digest(path)})
    return rows


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    results = load(EVIDENCE / "JOINED_RESULTS.json")
    require(results["status"] == "PASS", "RESULT_STATUS")
    require(results["new_test_denominator"] == {
        "directly_affected_unit": 9, "joined_runs": 13, "total": 22,
        "passed": 22, "failed": 0}, "DENOMINATOR")
    require(results["old_127_rerun"] is False and results["old_127_preserved"] is True,
            "OLD_127_STATE")
    require(results["before"] == results["after"], "EXECUTION_MUTATED_TRACKED_STATE")
    require(results["before"]["tracked_clean"] is True, "EXECUTION_NOT_CLEAN")
    require(all(results[key] is False for key in (
        "formal_product_go", "c28_live_trial", "production_mutated", "q34_mutated",
        "sealed_evaluation_accessed", "deployment_attempted")), "FORMAL_GATE_OR_SCOPE")
    require(load(EVIDENCE / "SECRET_SCAN.json")["pass"] is True, "SECRET_SCAN")

    original_inventory = load(EVIDENCE / "JOINED_ARTIFACT_INVENTORY.json")
    original_rows = {row["path"]: row for row in original_inventory["artifacts"]}
    for rel, row in original_rows.items():
        path = REPO / rel
        require(path.is_file() and path.stat().st_size == row["bytes"] and
                digest(path) == row["sha256"], "ORIGINAL_INVENTORY:" + rel)

    corpus = load(A05_SOURCE / "corpus.json")
    require(len(corpus["docs"]) == 11 and len(corpus["chunks"]) == 21, "A05_COUNTS")
    require(digest(A05_SOURCE / "release.json") == results["a05"]["release_sha256"],
            "A05_RELEASE_SHA")
    require(digest(A05_SOURCE / "corpus.json") == results["a05"]["corpus_sha256"],
            "A05_CORPUS_SHA")

    case_checks = []
    model_checks = {}
    for name, expected in EXPECTED.items():
        contract = load(EVIDENCE / "contracts" / (name + ".json"))
        receipt_path = EVIDENCE / "client_cases" / (name + ".json")
        receipt = load(receipt_path)
        run_id = receipt["run_id"]
        require(contract["run_id"] == run_id, "CONTRACT_RUN_ID:" + name)
        require(all(row["run_id"] == run_id for row in receipt["events"]),
                "EVENT_RUN_ID:" + name)
        require(terminal(receipt)["status"] == expected, "TERMINAL:" + name)
        admitted = [row for row in receipt["events"] if row["event"] == "task.admitted"]
        if admitted:
            require(admitted[0]["contract_sha256"] == contract_hash(contract),
                    "CONTRACT_HASH:" + name)
            require(admitted[0]["a06_projection_sha256"] ==
                    contract_hash(a06_projection(contract)), "A06_PROJECTION_HASH:" + name)
        if name not in {"positive_crash_reconcile_rollback", "unknown_unresolved"}:
            require(not any(row["event"] == "claim.verified" for row in receipt["events"]),
                    "NEGATIVE_TEXT_PUBLISHED:" + name)
        case_checks.append({"name": name, "terminal": expected,
                            "receipt_sha256": digest(receipt_path)})

    positive_name = "positive_crash_reconcile_rollback"
    positive = load(EVIDENCE / "client_cases" / (positive_name + ".json"))
    order = [row["event"] for row in positive["events"]]
    require(order.index("claim.verified") < order.index("worker.finished") <
            order.index("run.terminal"), "EARLY_STREAM_ORDER")
    require({row["kind"]: row["status"] for row in positive["controls"]} ==
            {"forged_ack": 409, "valid_ack": 200, "replay_ack": 409}, "ACK_CONTROLS")
    claim = next(row for row in positive["events"] if row["event"] == "claim.verified")
    source = A05_SOURCE / claim["source_id"]
    raw = source.read_bytes()
    start, end = claim["span"]
    require(digest(source) == claim["source_sha256"], "SOURCE_SHA")
    require(hashlib.sha256(raw[start:end]).hexdigest() == claim["excerpt_sha256"],
            "SOURCE_SPAN_SHA")
    model_checks[positive_name] = verify_model(positive["run_id"], positive)
    positive_action = verify_action(positive["run_id"], unknown=False)

    unknown = load(EVIDENCE / "client_cases/unknown_unresolved.json")
    model_checks["unknown_unresolved"] = verify_model(unknown["run_id"], unknown)
    unknown_action = verify_action(unknown["run_id"], unknown=True)

    attempt1 = load(HISTORY / "attempt_001_cold_model_timeout/client_cases/positive_crash_reconcile_rollback.json")
    attempt2 = load(HISTORY / "attempt_002_verifier_rejection/client_cases/positive_crash_reconcile_rollback.json")
    attempt3 = load(HISTORY / "attempt_003_precommit_pass/JOINED_RESULTS.json")
    require(terminal(attempt1)["error_code"] == "JOINED_MODEL_TIMEOUT_OR_EMPTY",
            "HISTORY_TIMEOUT_LOST")
    require(terminal(attempt2)["error_code"] == "BOUNDED_SEMANTIC_UNSUPPORTED",
            "HISTORY_VERIFIER_FAIL_LOST")
    require(attempt3["status"] == "PASS", "HISTORY_PRECOMMIT_PASS_LOST")

    source_files = ["joined_core.py", "joined_server.py", "joined_client.py",
                    "a06_joined_child.py", "run_joined_e2e.py", "test_joined_e2e.py"]
    execution_head = results["before"]["head"]
    require(execution_head == subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
        "EXECUTION_HEAD_NOT_CURRENT")
    verification = {
        "schema": "m27.wave-b02.joined-independent-verification/v1",
        "status": "PASS", "execution_head": execution_head,
        "execution_tree": results["before"]["tree"],
        "source_sha256": {name: digest(Path(__file__).parent / name) for name in source_files},
        "case_checks": case_checks, "model_checks": model_checks,
        "positive_action": positive_action, "unknown_action": unknown_action,
        "a05_exact_source": {"document": claim["source_id"], "span": claim["span"],
                             "source_sha256": claim["source_sha256"],
                             "excerpt_sha256": claim["excerpt_sha256"],
                             "docs": 11, "spans": 21},
        "history_preserved": ["cold_model_timeout", "verifier_rejection", "precommit_pass"],
        "old_127_rerun": False, "external_provider_calls": 0,
        "formal_product_go": False, "c28_live_trial": False,
    }
    verify_path = EVIDENCE / "INDEPENDENT_VERIFY.json"
    write(verify_path, verification)
    rows = current_inventory()
    write(EVIDENCE / "JOINED_ARTIFACT_INVENTORY.json", {
        "schema": "m27.wave-b02.joined-artifact-inventory/v1",
        "artifact_count": len(rows), "artifacts": rows,
        "excluded_self": str((EVIDENCE / "JOINED_ARTIFACT_INVENTORY.json").relative_to(REPO)),
    })
    require(all((REPO / row["path"]).is_file() and
                digest(REPO / row["path"]) == row["sha256"] for row in rows),
            "FINAL_INVENTORY")
    print(json.dumps({"status": "PASS", "cases": len(case_checks),
                      "artifacts": len(rows), "execution_head": execution_head}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
