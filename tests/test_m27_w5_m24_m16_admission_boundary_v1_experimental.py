"""M24-only negative/fault/permission matrix, no original refused test reruns."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from knowledge_engine import m27_w5_m24_m16_admission_boundary_v1_experimental as m

ROOT = Path(__file__).resolve().parents[1]


def candidate(**changes):
    original = m.CandidateIdentity(
        head=m.BASE_COMMIT, baseline_commit=m.BASE_COMMIT, baseline_tree=m.BASE_TREE,
        candidate_tree=m.BASE_TREE, file_sha256=m.FILE_PINS.copy(),
        source_origins=m.ORIGINS, clean_or_owned_only=True, local_wire_imported=True,
    )
    return dataclasses.replace(original, **changes)


def evidence(gate, **changes):
    original = m.AuthorityEvidence(
        gate=gate, status="APPROVED", issuer="external:authority",
        witness_id="witness-01", nonce="nonce-01",
        candidate_commit=m.BASE_COMMIT, source_sha256="1" * 64,
        signed_claim="not-a-real-cryptographic-signature",
        original_count=523, live_count=341, replay_count=182,
        phase_b_count=200, p95_ms=14999,
    )
    return dataclasses.replace(original, **changes)


def decision(identity=None, claims=(), wire=None, cli=None):
    return m.assess(
        candidate() if identity is None else identity,
        evidence=claims,
        cli=cli,
        local_wire={"status": "COMPLETE"} if wire is None else wire,
    )


def reason(d, text):
    assert d.decision == "NOT_ADMITTED"
    assert text in d.reasons


@pytest.mark.parametrize("gate", m.GATES, ids=lambda g: "missing-" + g)
def test_missing_external_authority_is_denied(gate):
    d = decision()
    reason(d, "AUTHORITY_MISSING:" + gate)
    assert d.gate_states[gate] == "MISSING_UNVERIFIED"


@pytest.mark.parametrize("gate", m.GATES, ids=lambda g: "unsigned-" + g)
def test_unsigned_claim_is_rejected(gate):
    d = decision(claims=(evidence(gate, signed_claim=""),))
    reason(d, "AUTHORITY_UNTRUSTED_OR_MISBOUND:" + gate)


@pytest.mark.parametrize("fault,mutation,expected", [
    ("missing_identity", "ABSENT", "CANDIDATE_IDENTITY_NOT_VERIFIED"),
    ("bad_base", {"baseline_commit": "2" * 40}, "WRONG_I23_TREE_OR_HEAD"),
    ("bad_tree", {"baseline_tree": "3" * 40}, "WRONG_I23_TREE_OR_HEAD"),
    ("wrong_origin", {"source_origins": ()}, "SOURCE_ORIGIN_CHAIN_MISMATCH"),
    ("missing_pin", {"file_sha256": {}}, "SOURCE_SHA_PIN_MISMATCH"),
    ("bad_sha", {"file_sha256": {**m.FILE_PINS, next(iter(m.FILE_PINS)): "a" * 64}},
     "SOURCE_SHA_PIN_MISMATCH"),
    ("extra_pin", {"file_sha256": {**m.FILE_PINS, "hidden/secret.txt": "4" * 64}},
     "SOURCE_SHA_PIN_MISMATCH"),
    ("not_owned", {"clean_or_owned_only": False}, "CANDIDATE_IDENTITY_NOT_VERIFIED"),
    ("import_failed", {"local_wire_imported": False}, "I23_PROTOCOL_IMPORT_UNVERIFIED"),
    ("wrong_head", {"head": "not-a-commit"}, "WRONG_I23_TREE_OR_HEAD"),
], ids=lambda entry: entry if isinstance(entry, str) else None)
def test_identity_tamper(fault, mutation, expected):
    target = None if mutation == "ABSENT" else candidate(**mutation)
    if mutation == "ABSENT":
        d = m.assess(None, local_wire={"status": "COMPLETE"})
    else:
        d = decision(identity=target)
    reason(d, expected)


@pytest.mark.parametrize("change", [
    {"status": "DENIED"},
    {"status": "UNKNOWN"},
    {"issuer": ""},
    {"issuer": "../invalid"},
    {"witness_id": ""},
    {"witness_id": "with spaces"},
    {"nonce": ""},
    {"nonce": "../../bad"},
    {"candidate_commit": "0" * 40},
    {"source_sha256": ""},
    {"source_sha256": "z" * 64},
    {"signed_claim": ""},
], ids=[
    "denied_status", "unknown_status", "empty_issuer", "path_issuer",
    "no_witness", "bad_witness", "no_nonce", "bad_nonce",
    "wrong_commit", "absent_source_sha", "invalid_sha", "unsigned",
])
def test_untrusted_authority_claims(change):
    d = decision(claims=(evidence("source_rights", **change),))
    reason(d, "AUTHORITY_UNTRUSTED_OR_MISBOUND:source_rights")


@pytest.mark.parametrize("change", [
    {"original_count": 522},
    {"original_count": 524},
    {"original_count": True},
    {"live_count": 340},
    {"live_count": 523},
    {"replay_count": 181},
    {"replay_count": 341},
    {"replay_count": None},
], ids=[
    "522", "524", "bool-case", "340-live", "523-live",
    "181-replay", "341-replay", "missing-replay",
])
def test_wrong_original523_denominator(change):
    d = decision(claims=(evidence("original523_independent_grader", **change),))
    reason(d, "AUTHORITY_UNTRUSTED_OR_MISBOUND:original523_independent_grader")


@pytest.mark.parametrize("count", [0, 182, 199, 201, 523, None, -1])
def test_bad_blind_phase_b_denominator(count):
    d = decision(claims=(evidence("phase_b200_independent_custodian",
                                  phase_b_count=count),))
    reason(d, "AUTHORITY_UNTRUSTED_OR_MISBOUND:phase_b200_independent_custodian")


@pytest.mark.parametrize("value", [None, -1, 15001, 19000, "100", True, float("inf"), float("nan")],
                         ids=["none", "negative", "too_slow", "fake_p95", "string",
                              "bool", "inf", "nan"])
def test_fake_real_p95(value):
    d = decision(claims=(evidence("real_all_outcome_p95", p95_ms=value),))
    reason(d, "AUTHORITY_UNTRUSTED_OR_MISBOUND:real_all_outcome_p95")


@pytest.mark.parametrize("exit_code,payload,expected", [
    (0, {"status": "DENIED"}, "CLI_EXIT_ZERO_WITH_JSON_DENIAL"),
    (0, {"status": "NOT_ADMITTED"}, "CLI_EXIT_ZERO_WITH_JSON_DENIAL"),
    (0, {"status": "PASS", "evidence": {"decision": "DENIED"}}, "CLI_EXIT_ZERO_WITH_JSON_DENIAL"),
    (0, {"status": "PASS", "reasons": ["AUTHORITY_DENIED"]}, "CLI_EXIT_ZERO_WITH_JSON_DENIAL"),
    (0, {"status": "NOT_VERIFIED"}, "CLI_EXIT_ZERO_WITH_JSON_DENIAL"),
    (20, {"status": "DENIED"}, "CLI_NONZERO_NOT_POSITIVE"),
    (21, {"status": "DENIED"}, "CLI_NONZERO_NOT_POSITIVE"),
    (22, {"status": "DENIED"}, "CLI_NONZERO_NOT_POSITIVE"),
    (0, {"status": "PASS"}, "CLI_STATUS_NOT_LOCAL_PASS"),
    (0, {"message": "success"}, "CLI_STATUS_NOT_LOCAL_PASS"),
], ids=[
    "forged-exit0", "fake-admission", "nested-denial", "list-denial",
    "not-verified", "exit20", "exit21", "exit22", "unknown-pass", "missing-status",
])
def test_cli_denial_matrix(exit_code, payload, expected):
    d = decision(cli=m.CLIObservation(exit_code, json.dumps(payload)))
    reason(d, expected)


@pytest.mark.parametrize("stdout,expected", [
    ("not-json", "CLI_JSON_INVALID"),
    ("[]", "CLI_JSON_NOT_OBJECT"),
    ("null", "CLI_JSON_NOT_OBJECT"),
    ("", "CLI_JSON_INVALID"),
    ('{"status":', "CLI_JSON_INVALID"),
    ("0" * 65537, "CLI_OUTPUT_TOO_LARGE"),
], ids=["invalid", "array", "null", "empty", "partial", "over-limit"])
def test_cli_invalid_payload(stdout, expected):
    d = decision(cli=m.CLIObservation(0, stdout))
    reason(d, expected)


@pytest.mark.parametrize("gate", ["wrong_gate", "../rights", "", "SOURCE_RIGHTS"])
def test_unknown_authority_cannot_grant(gate):
    reason(decision(claims=(evidence(gate),)), "UNKNOWN_AUTHORITY_GATE")


def test_duplicate_same_gate_rejected():
    claims = (evidence("source_rights"), evidence("source_rights", nonce="nonce-02"))
    reason(decision(claims=claims), "DUPLICATE_AUTHORITY_GATE:source_rights")


def test_replayed_nonce_across_two_gates_rejected():
    claims = (evidence("source_rights"), evidence("native_client_external_ack"))
    reason(decision(claims=claims), "AUTHORITY_UNTRUSTED_OR_MISBOUND:native_client_external_ack")


def test_replayed_witness_across_two_gates_rejected():
    claims = (evidence("source_rights"), evidence("native_client_external_ack", nonce="nonce-02"))
    reason(decision(claims=claims), "AUTHORITY_UNTRUSTED_OR_MISBOUND:native_client_external_ack")


def test_synthetic_valid_looking_signature_still_not_approved():
    d = decision(claims=(evidence("source_rights"),))
    reason(d, "INDEPENDENT_WITNESS_NOT_AUTHENTICATED:source_rights")
    assert d.gate_states["source_rights"] == "UNVERIFIED_EXTERNAL_WITNESS"


def test_staging_local_pass_always_not_admitted():
    d = decision()
    assert d.local_state == m.LOCAL_STATUS
    reason(d, "M24_RELEASE_ADMISSION_DISABLED")


def test_denied_local_protocol_is_not_positive():
    reason(decision(wire={"status": "DENIED"}), "LOCAL_PROTOCOL_NOT_COMPLETE")


def test_missing_local_protocol_is_not_positive():
    d = m.assess(candidate(), local_wire={})
    reason(d, "LOCAL_PROTOCOL_NOT_EXECUTED")


def test_decision_is_idempotent_for_same_trusted_inputs():
    assert decision() == decision()


def test_decision_contains_no_claim_payload_or_secret_bytes():
    secret = "PRIVATE-API-KEY-DO-NOT-EXPORT"
    d = decision(claims=(evidence("source_rights", signed_claim=secret),))
    assert secret not in json.dumps(dataclasses.asdict(d))


def test_clean_i23_head_and_pins_on_real_worktree():
    identity = m.inspect_candidate(ROOT)
    assert identity.baseline_commit == m.BASE_COMMIT
    assert identity.baseline_tree == m.BASE_TREE
    assert set(identity.file_sha256) == set(m.FILE_PINS)
    assert identity.local_wire_imported


def test_hash_reader_exact_sha(tmp_path):
    f = tmp_path / "source.py"
    f.write_bytes(b"alpha")
    assert m._file_sha(tmp_path, "source.py") == m.hashlib.sha256(b"alpha").hexdigest()


def test_hash_reader_rejects_symlink(tmp_path):
    (tmp_path / "real").write_text("safe")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(OSError):
        m._file_sha(tmp_path, "link")


def test_hash_reader_rejects_non_regular(tmp_path):
    (tmp_path / "dir").mkdir()
    with pytest.raises(ValueError, match="SOURCE_NOT_REGULAR"):
        m._file_sha(tmp_path, "dir")


def test_hash_reader_rejects_oversized(tmp_path):
    (tmp_path / "big").write_bytes(b"X" * 2_000_001)
    with pytest.raises(ValueError, match="TOO_LARGE"):
        m._file_sha(tmp_path, "big")


def test_hash_reader_rejects_concurrent_mutation(tmp_path):
    file = tmp_path / "source"
    file.write_bytes(b"alpha")
    original_read = os.read
    once = False

    def modified_read(fd, n):
        nonlocal once
        data = original_read(fd, n)
        if not once:
            file.write_bytes(b"beta-longer")
            once = True
        return data

    with (patch.object(m.os, "read", side_effect=modified_read),
          pytest.raises(ValueError, match="SOURCE_CONCURRENT_MUTATION")):
        m._file_sha(tmp_path, "source")


def test_receipt_permissions_no_overwrite(tmp_path):
    output = m.write_receipt(tmp_path / "receipts", decision())
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(output.read_text())["decision"] == "NOT_ADMITTED"
    with pytest.raises(FileExistsError):
        m.write_receipt(output.parent, decision())


@pytest.mark.parametrize("namespace", ["", "UPPER", "../bad", "x", "bad space", "1invalid"])
def test_invalid_namespace_never_launches_client(namespace):
    with pytest.raises(ValueError, match="INVALID_LOCAL_NAMESPACE"):
        m.local_protocol_preflight(ROOT, namespace)


def test_safe_import_proof_and_original_components():
    assert len(m.ORIGINS) == 9
    assert [name for name, _, _ in m.ORIGINS] == [
        "I15", "C16", "E15", "P16", "P17", "L21", "L22", "N22", "I23"
    ]
    assert not m.RELEASE_ADMISSION_ENABLED
    assert m.CANONICAL_M16 not in (m.BASE_COMMIT,)


def test_scoped_client_wire_stub_never_auto_admits():
    from knowledge_engine import m27_w5_n21_independent_local_client_v1_experimental as n22
    fake = {
        "status": "COMPLETE",
        "client": {"status": "COMPLETE", "recv_calls": 1, "answer_events": 1,
                   "first_answer_ns": 10, "full_answer_ns": 20, "terminal_ns": 30},
        "endpoint": "127.0.0.1:4312", "server_pid": 100, "client_pid": 101,
        "source_sha256": n22.fixture_spec(0, "m24-test-01")["source_sha256"],
        "cleanup": {"client": {"reaped": True}, "server": {"reaped": True}},
    }
    with patch.object(n22, "run_case", return_value=fake):
        preflight = m.local_protocol_preflight(ROOT, "m24-test-01")
    assert preflight["status"] == "COMPLETE"
    reason(decision(wire=preflight), "M24_RELEASE_ADMISSION_DISABLED")
