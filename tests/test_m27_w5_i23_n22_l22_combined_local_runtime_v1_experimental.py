"""I23 fresh fault injection and combined nonproduction source contract."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15
from knowledge_engine import m27_w5_i23_n22_l22_combined_local_runtime_v1_experimental as i23
from knowledge_engine import m27_w5_n21_independent_local_client_v1_experimental as n22

NS = "i23-audit-unit"


def synthetic_receipt() -> dict:
    """Pure unit fixture only. Real client/server coverage executes separately."""
    cases = []
    plan = [(i, "positive") for i in range(12)] + [
        (i % 12, mode) for i, mode in enumerate(i15.FAULT_MODES)
    ]
    for idx, (index, mode) in enumerate(plan):
        s = i15.spec(index, NS)
        positive = mode == "positive"
        sp, cp = 21000 + idx * 2, 21001 + idx * 2
        client = {
            "client_pid": cp, "status": "COMPLETE" if positive else "DENIED",
            "received_digest": s["answer_sha256"] if positive else "0" * 64,
            "received_bytes": len(s["answer_bytes"]) if positive else 0,
            "recv_calls": 100, "answer_events": 2 if positive else 0,
            "progress_events": 1, "request_sent_ns": 10,
            "first_recv_ns": 20, "first_answer_ns": 30 if positive else None,
            "full_answer_ns": 40 if positive else None,
            "terminal_ns": 50 if positive else None,
        }
        cases.append({
            "case_id": s["case_id"] + "-" + mode, "mode": mode,
            "source_sha256": s["source_sha256"],
            "source_revision": s["source_revision"],
            "expected_answer_sha256": s["answer_sha256"],
            "server_pid": sp, "client_pid": cp,
            "endpoint": "127.0.0.1:40001",
            "client": client, "server": {"server_pid": sp},
            "status": "COMPLETE" if positive else "DENIED",
            "client_prewarm_deadline_s": 24.0,
            "server_boot_deadline_s": 24.0,
            "cleanup": {
                "client": {"reaped": True},
                "server": {"reaped": True},
            },
        })
    return {
        "status": n22.PASS, "fixture": True, "cases": cases,
        "attempted": 28, "completed": 12, "rejected_or_failed": 16,
        "expected_positive": 12, "expected_negative": 16,
        "positive_valid": True, "negative_valid": True,
        "first_text_p95_ms": None, "full_answer_p95_ms": None,
        "terminal_p95_ms": None,
        "denominator_status": "UNKNOWN_HAS_FAILURES",
    }


# Fifty-six independent artificial corruptions of an otherwise valid complete
# denominator. These are freshly executed tests, never previous-worker counts.
FAULTS = [
    (("status",), "NOT_VERIFIED"),
    (("fixture",), False),
    (("attempted",), 27),
    (("completed",), 11),
    (("rejected_or_failed",), 17),
    (("expected_positive",), 11),
    (("expected_negative",), 15),
    (("positive_valid",), False),
    (("negative_valid",), False),
    (("first_text_p95_ms",), 12.5),
    (("full_answer_p95_ms",), 12.5),
    (("terminal_p95_ms",), 12.5),
    (("denominator_status",), "PRODUCT_PASS"),
    (("cases", 0, "mode"), "wrong_tenant"),
    (("cases", 0, "case_id"), "replayed"),
    (("cases", 0, "source_sha256"), "f" * 64),
    (("cases", 0, "source_revision"), "revoked"),
    (("cases", 0, "expected_answer_sha256"), "f" * 64),
    (("cases", 0, "server_pid"), 21001),
    (("cases", 0, "client_pid"), 0),
    (("cases", 0, "endpoint"), "8.8.8.8:443"),
    (("cases", 0, "endpoint"), "127.0.0.2:80"),
    (("cases", 0, "client", "client_pid"), 0),
    (("cases", 0, "server", "server_pid"), 0),
    (("cases", 0, "cleanup", "client", "reaped"), False),
    (("cases", 0, "cleanup", "server", "reaped"), False),
    (("cases", 0, "client_prewarm_deadline_s"), 999.0),
    (("cases", 0, "server_boot_deadline_s"), 6.0),
    (("cases", 0, "status"), "DENIED"),
    (("cases", 0, "client", "status"), "DENIED"),
    (("cases", 0, "client", "received_digest"), "0" * 64),
    (("cases", 0, "client", "received_bytes"), 0),
    (("cases", 0, "client", "recv_calls"), 0),
    (("cases", 0, "client", "recv_calls"), True),
    (("cases", 0, "client", "answer_events"), 0),
    (("cases", 0, "client", "progress_events"), 0),
    (("cases", 0, "client", "request_sent_ns"), 25),
    (("cases", 0, "client", "first_recv_ns"), 35),
    (("cases", 0, "client", "first_answer_ns"), 45),
    (("cases", 0, "client", "full_answer_ns"), 51),
    (("cases", 0, "client", "terminal_ns"), None),
    (("cases", 0, "client", "terminal_ns"), 40),
    (("cases", 12, "mode"), "positive"),
    (("cases", 12, "case_id"), "spoof"),
    (("cases", 12, "source_sha256"), "f" * 64),
    (("cases", 12, "source_revision"), "stale"),
    (("cases", 12, "client_pid"), 21024),
    (("cases", 12, "client", "status"), "COMPLETE"),
    (("cases", 12, "status"), "COMPLETE"),
    (("cases", 12, "client", "first_answer_ns"), 100),
    (("cases", 12, "cleanup", "client", "reaped"), False),
    (("cases", 13, "cleanup", "server", "reaped"), False),
    (("cases", 14, "server_pid"), 0),
    (("cases", 16, "endpoint"), "example.com:80"),
    (("cases", 22, "client_prewarm_deadline_s"), 100.0),
    (("cases", 27, "server_boot_deadline_s"), 99.0),
]


def test_clean_synthetic_contract_is_only_a_unit_control():
    result = i23.audit_n22(synthetic_receipt(), NS)
    assert result["attempted"] == 28
    assert result["completed"] == 12
    assert result["expected_denied"] == 16
    assert result["all_outcome_p95"] is None


@pytest.mark.parametrize("path,replacement", FAULTS, ids=range(len(FAULTS)))
def test_i23_distinct_denominator_source_pid_and_fault_mutations_fail_closed(
    path, replacement,
):
    obj = copy.deepcopy(synthetic_receipt())
    current = obj
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement
    with pytest.raises(i23.CombinedDenied):
        i23.audit_n22(obj, NS)


@pytest.mark.parametrize("mutation", [
    {"plan_total": 5}, {"completed": 2}, {"fault_denied": 4},
    {"fixture": False}, {"official_p95": 12.0},
    {"denominator": {"first_text_p95_ms": 2.3}},
    {"cases": []},
])
def test_six_case_concurrent_failure_denominator_never_silently_reduced(mutation):
    valid = {
        "plan_total": 6, "completed": 3, "fault_denied": 3,
        "fixture": True, "official_p95": None,
        "denominator": {"first_text_p95_ms": None},
        "cases": [{"synthetic_only": True, "client_pid": i + 1,
                   "server_pid": 100 + i} for i in range(6)],
    }
    valid.update(mutation)
    with pytest.raises(i23.CombinedDenied):
        i23.audit_l22_six(valid)


def test_pinned_modules_and_bounded_l22_n22_deadlines():
    tree = Path(__file__).resolve().parents[1]
    pins = i23.attest_sources(tree)
    assert len(pins) == 7
    assert pins == i23.PINNED
    assert i15.LOCAL_SERVER_ACCEPT_DEADLINE_SECONDS == 20.0
    assert n22.SERVER_BOOT_DEADLINE_SECONDS == 24.0


@pytest.mark.parametrize("namespace", ["../bad", "invalid space", "🔔", "x" * 60])
def test_bad_namespace_rejected_before_socket_or_process(tmp_path, namespace):
    tree = Path(__file__).resolve().parents[1]
    with pytest.raises((i15.I15Denied, i23.CombinedDenied)):
        i23.run(tree, tmp_path / "scratch", namespace)


def test_i23_cli_returns_nonzero_for_not_verified(monkeypatch, capsys):
    monkeypatch.setattr(i23, "run", lambda *args: {"status": i23.FAIL})
    monkeypatch.setattr(sys, "argv", ["i23", "--worktree", "/tmp/a",
                                      "--scratch", "/tmp/b"])
    assert i23.main() == 20
    assert json.loads(capsys.readouterr().out)["status"] == i23.FAIL


def test_i23_cli_returns_nonzero_for_bad_28_case_count(monkeypatch, capsys):
    def invalid(*args):
        raise i23.CombinedDenied("N22_COUNT_OR_VALIDITY")
    monkeypatch.setattr(i23, "run", invalid)
    monkeypatch.setattr(sys, "argv", ["i23", "--worktree", "/tmp/a",
                                      "--scratch", "/tmp/b"])
    assert i23.main() == 20
    assert json.loads(capsys.readouterr().out)["status"] == i23.FAIL


def test_scratch_inside_source_tree_is_rejected_without_case_execution():
    tree = Path(__file__).resolve().parents[1]
    with pytest.raises(i23.CombinedDenied, match="SCRATCH_UNSAFE"):
        i23.run(tree, tree / "scratch", "i23-rejected")
