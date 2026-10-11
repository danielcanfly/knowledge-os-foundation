"""Independent L21 staging denial matrix. No original P16/B13 blocked batch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_i15_native_local_client_integration_v1_experimental as i15
from knowledge_engine import m27_w5_l21_staging_combined_local_runtime_v1_experimental as l21
from knowledge_engine import m27_w5_p16_external_evidence_ingress_v1_experimental as p17

NS = "l21-fixture-tests"


def synthetic_positive() -> dict:
    """Deterministic unit receipt (not a substitute for child-process tests)."""
    s = i15.spec(0, NS)
    return {
        "fixture": True, "mode": "positive", "namespace": NS,
        "case_id": s["case_id"] + "-positive",
        "source_sha256": s["source_sha256"],
        "source_revision": s["source_revision"],
        "answer_sha256": s["answer_sha256"],
        "endpoint": "127.0.0.1:40000", "status": "COMPLETE",
        "client": {
            "client_pid": 1101, "status": "COMPLETE",
            "recv_calls": 42, "recv_bytes": 819,
            "request_ns": 100, "first_recv_ns": 105,
            "first_data_ns": 115, "terminal_ns": 142,
            "first_text_ms": 1.5, "terminal_ms": 2.8,
            "received_answer_sha256": s["source_sha256"],
            "answer_length": len(s["answer_bytes"]),
            "answer_events": 3, "progress_events": 1,
        },
        "server": {
            "server_pid": 1102, "enqueue_ns": [200],
            "flush_ns": [205], "terminal_ns": 225,
        },
        "diagnostics": {
            "client_exit": 0, "server_exit": 0,
            "process_limit": 4, "failure_stage": None,
            "cleanup": {
                "client": {"reaped": True}, "server": {"reaped": True},
            },
        },
    }


@pytest.mark.parametrize("field,value", [
    (("fixture",), False),
    (("fixture",), None),
    (("mode",), "server_500"),
    (("mode",), ""),
    (("namespace",), "foreign"),
    (("case_id",), "replayed"),
    (("case_id",), "i15-case-00-positive"),
    (("source_sha256",), "f" * 64),
    (("source_sha256",), None),
    (("source_revision",), "revoked-revision"),
    (("answer_sha256",), "0" * 64),
    (("status",), "FAILED"),
    (("endpoint",), "0.0.0.0:80"),
    (("endpoint",), "127.0.0.2:80"),
    (("client", "client_pid"), 1102),
    (("client", "client_pid"), 0),
    (("client", "client_pid"), "1101"),
    (("client", "status"), "ABSTAINED"),
    (("client", "recv_calls"), 0),
    (("client", "recv_calls"), True),
    (("client", "recv_bytes"), 0),
    (("client", "request_ns"), None),
    (("client", "first_recv_ns"), 90),
    (("client", "first_recv_ns"), None),
    (("client", "first_data_ns"), 100),
    (("client", "first_data_ns"), 142),
    (("client", "first_data_ns"), None),
    (("client", "terminal_ns"), None),
    (("client", "terminal_ns"), 115),
    (("client", "first_text_ms"), -1.0),
    (("client", "first_text_ms"), None),
    (("client", "first_text_ms"), 3.0),
    (("client", "terminal_ms"), -1.0),
    (("client", "terminal_ms"), None),
    (("client", "received_answer_sha256"), "a" * 64),
    (("client", "answer_length"), 0),
    (("client", "answer_length"), 10000),
    (("client", "answer_events"), 0),
    (("client", "progress_events"), 0),
    (("server", "server_pid"), 1101),
    (("server", "server_pid"), 0),
    (("server", "enqueue_ns"), []),
    (("server", "flush_ns"), []),
    (("server", "flush_ns"), [199]),
    (("server", "terminal_ns"), 201),
    (("diagnostics", "client_exit"), 1),
    (("diagnostics", "server_exit"), None),
    (("diagnostics", "process_limit"), 16),
    (("diagnostics", "failure_stage"), "boot"),
    (("diagnostics", "cleanup", "client", "reaped"), False),
    (("diagnostics", "cleanup", "server", "reaped"), False),
])
def test_51_distinct_mutated_local_evidence_cases_denied(field, value):
    record = synthetic_positive()
    current = record
    for key in field[:-1]:
        current = current[key]
    current[field[-1]] = value
    with pytest.raises(l21.LocalDenied):
        l21.validate_case(record, 0, "positive", NS)


def test_unit_valid_fixture_receipt_explicitly_synthetic():
    receipt = l21.validate_case(synthetic_positive(), 0, "positive", NS)
    assert receipt.outcome == "completed" and receipt.synthetic_only
    assert receipt.citation_id == i15.spec(0, NS)["citation_id"]
    assert receipt.source_sha256 == hashlib.sha256(
        i15.spec(0, NS)["answer_bytes"]
    ).hexdigest()


@pytest.mark.parametrize("namespace", [
    "", "x", "../unsafe", "spaces disallowed", "💥", "n" * 49,
    "a/b", "a\x00b", "a.b", " x",
])
def test_bad_namespaces_denied(namespace):
    with pytest.raises(l21.LocalDenied, match="NAMESPACE_INVALID"):
        l21.validate_case(synthetic_positive(), 0, "positive", namespace)


@pytest.mark.parametrize("index", [-1, 12, 100, True, "0", None])
def test_case_index_not_part_of_local_fixture_denied(index):
    with pytest.raises(l21.LocalDenied):
        l21.validate_case(synthetic_positive(), index, "positive", NS)


@pytest.mark.parametrize("plan", [
    [], [(0, "positive")] * 2, [(0, "forged")],
    [(12, "positive")], [(-1, "positive")],
    [(True, "positive")], [(0, "positive")] * 29,
])
def test_plan_invalid_never_starts_processes(tmp_path, plan):
    with pytest.raises(l21.LocalDenied):
        l21.execute_plan(tmp_path, NS, plan)


@pytest.mark.parametrize("field,value", [
    (("status",), "COMPLETE"),
    (("client", "status"), "COMPLETE"),
    (("client", "first_data_ns"), 999),
])
def test_synthetic_fault_cannot_be_marked_completed(field, value):
    receipt = synthetic_positive()
    receipt["mode"] = "progress_only"
    receipt["case_id"] = i15.spec(0, NS)["case_id"] + "-progress_only"
    receipt["status"] = "PROGRESS_ONLY_NOT_FIRST_TEXT"
    receipt["client"]["status"] = "PROGRESS_ONLY_NOT_FIRST_TEXT"
    receipt["client"]["first_data_ns"] = None
    current = receipt
    for key in field[:-1]:
        current = current[key]
    current[field[-1]] = value
    with pytest.raises(l21.LocalDenied):
        l21.validate_case(receipt, 0, "progress_only", NS)


def test_p17_real_local_denial_receipt_rehash_and_refuse_official(tmp_path):
    worktree = Path(__file__).resolve().parents[1]
    denial = l21.p17_denial_only(worktree, tmp_path / "scratch")
    receipt = tmp_path / "scratch/l21-denial-receipt/P16_REQUEST_RECEIPT.json"
    assert denial.exit_code == p17.EXIT_AUTHORITY_DENIED
    assert denial.decision == "DENIED"
    assert denial.validated
    assert denial.receipt_sha256 == hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert denial.actual_file_sha256 == denial.receipt_sha256
    assert not denial.may_execute_official_evaluation
    obj = json.loads(receipt.read_bytes())
    assert obj["classification"] == p17.CODE_ABSENT
    assert obj["verified_content_sha256"] == {}
    assert obj["denial_reasons"]


def test_p17_digest_bound_denial_tampering_is_rejected(tmp_path):
    worktree = Path(__file__).resolve().parents[1]
    denial = l21.p17_denial_only(worktree, tmp_path / "scratch")
    receipt = tmp_path / "scratch/l21-denial-receipt/P16_REQUEST_RECEIPT.json"
    raw = json.loads(receipt.read_bytes())
    raw["may_execute_official_evaluation"] = True
    receipt.write_text(json.dumps(raw))
    assert not p17.validate_denial_receipt(receipt, denial.receipt_sha256)
    assert not p17.validate_denial_receipt(
        receipt, hashlib.sha256(receipt.read_bytes()).hexdigest()
    )


def test_p17_denial_does_not_become_rights_admission_even_if_replayed(tmp_path):
    worktree = Path(__file__).resolve().parents[1]
    for index in range(2):
        denial = l21.p17_denial_only(worktree, tmp_path / f"scratch{index}")
        assert denial.decision == "DENIED"
        assert denial.original523 == p17.e15.REJECT_523
        assert denial.phase_b == p17.e15.REJECT_B


@pytest.mark.parametrize("scratch_variant", ["same_worktree", "ancestor", "relative", "file"])
def test_invalid_scratch_never_runs_server_or_external_evaluation(
    tmp_path, scratch_variant,
):
    worktree = Path(__file__).resolve().parents[1]
    scratch = {
        "same_worktree": worktree / "scratch",
        "ancestor": worktree.parent,
        "relative": Path("relative-dir"),
        "file": tmp_path / "not-a-folder",
    }[scratch_variant]
    if scratch_variant == "file":
        scratch.write_text("existing fixture")
    with pytest.raises(l21.LocalDenied):
        l21._scratch(worktree, scratch)


def test_real_28_outcomes_separate_child_processes_and_p17_denial(tmp_path):
    worktree = Path(__file__).resolve().parents[1]
    receipt = l21.run(worktree, tmp_path / "scratch", "l21-28-case")
    assert receipt["status"] == l21.STATUS
    assert receipt["completed"] == 12
    assert receipt["fault_denied"] == 16
    assert receipt["denominator"]["total"] == 28
    assert receipt["denominator"]["first_text_p95_ms"] is None
    assert receipt["may_execute_official_evaluation"] is False
    raw = Path(receipt["receipt_path"]).read_bytes()
    assert receipt["receipt_sha256"] == hashlib.sha256(raw).hexdigest()
    obj = json.loads(raw)
    assert obj["p17_denial"]["validated"] is True
    assert len(obj["outcomes"]["cases"]) == 28
    assert len({v["source_sha256"] for v in obj["outcomes"]["cases"]
                if v["outcome"] == "completed"}) == 12
    assert all(v["client_pid"] != v["server_pid"]
               for v in obj["outcomes"]["cases"])
    assert obj["release_authorized"] is False
    assert obj["outcomes"]["official_p95"] is None


def test_real_bounded_mixed_concurrency_faults_never_count_as_completion(tmp_path):
    worktree = Path(__file__).resolve().parents[1]
    plan = [
        (0, "positive"), (1, "positive"),
        (2, "wrong_tenant"), (3, "server_500"),
        (4, "positive"), (5, "progress_only"),
    ]
    results = l21.execute_plan(worktree, "l21-stress", plan)
    assert results["plan_total"] == 6
    assert results["completed"] == 3
    assert results["fault_denied"] == 3
    assert results["process_limit"] == 4
    assert results["official_p95"] is None
    assert all(v["synthetic_only"] for v in results["cases"])

def test_l22_isolated_synthetic_accept_window_is_bounded():
    assert i15.LOCAL_SERVER_ACCEPT_DEADLINE_SECONDS == 20.0
    assert l21.LOCAL_BOOT_DEADLINE_SECONDS == 24.0
    assert l21.LOCAL_CLIENT_DEADLINE_SECONDS == 24.0


def test_l22_actual_delayed_external_client_receives_cited_answer(monkeypatch):
    """5s late client must still receive a real 127.0.0.1 answer (old 4s failed)."""
    worktree = Path(__file__).resolve().parents[1]
    original_env = i15._child_env

    def delayed_fixture_env(path):
        env = original_env(path)
        env["M27_L22_SYNTHETIC_DELAY_CONNECT"] = "5"
        return env

    monkeypatch.setattr(i15, "_child_env", delayed_fixture_env)
    monkeypatch.setattr(i15, "BOOT_DEADLINE_SECONDS", 24.0)
    monkeypatch.setattr(i15, "CLIENT_DEADLINE_SECONDS", 24.0)
    monkeypatch.setattr(i15, "SERVER_EXIT_DEADLINE_SECONDS", 16.0)
    result = i15.run_case(worktree, 0, "positive", "l22-delayed")
    validated = l21.validate_case(result, 0, "positive", "l22-delayed")
    assert result["status"] == "COMPLETE"
    assert validated.outcome == "completed"
    assert result["client"]["recv_calls"] > 0
    assert result["client"]["first_data_ns"] < result["client"]["terminal_ns"]
    assert result["diagnostics"]["cleanup"]["server"]["reaped"]
    assert result["diagnostics"]["cleanup"]["client"]["reaped"]
