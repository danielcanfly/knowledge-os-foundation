from __future__ import annotations

import base64
import copy
import hashlib
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine.m27_b03_r01_admission_gate import (
    AdmissionEvidence,
    evaluate_f35_rel01,
)
from knowledge_engine.m27_b03_r01_execution_recovery import (
    EXPLICIT_REFUSAL_TEXT,
    ExecutionObservation,
    ExecutionOutcome,
    classify_execution_outcome,
)
from knowledge_engine.m27_b03_r01_public_receipt import (
    SCHEMA,
    AuthorizedIssuer,
    ReceiptRejected,
    canonical_json,
    verify_public_acceptance_receipt,
)

B03_COMMIT = "f4de69b2ffa30e112ac72aa772602440d64561ef"
B03_TREE = "c87e84eaaf973241c82104fc81d79325851cd226"
NOW_MS = 1_797_000_000_000
CLAIMS = {
    "artifact_files": 11,
    "changed_files": 25,
    "focused_passed": 43,
    "focused_total": 43,
    "regression_passed": 238,
    "regression_total": 238,
}


def _envelope() -> tuple[dict, AuthorizedIssuer, Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    issuer = AuthorizedIssuer(
        issuer_id="fixture-independent-master",
        role="INDEPENDENT_MASTER_EVIDENCE_WITNESS",
        public_key_b64=base64.b64encode(public_raw).decode("ascii"),
        authorization_receipt_sha256=hashlib.sha256(b"fixture-authorization").hexdigest(),
        authorization_status="DONE_WITH_RECEIPT",
        candidate_commit=B03_COMMIT,
        valid_from_ms=NOW_MS - 10_000,
        valid_until_ms=NOW_MS + 10_000,
    )
    payload = {
        "schema": SCHEMA,
        "receipt_id": "fixture-receipt-001",
        "issuer_id": issuer.issuer_id,
        "subject": "B03_MASTER_PHYSICAL_EVIDENCE",
        "candidate_commit": B03_COMMIT,
        "candidate_tree": B03_TREE,
        "observed_at_ms": NOW_MS - 100,
        "command_id": "fixture-command-001",
        "pid": 4242,
        "pid_command_id": "fixture-command-001",
        "claims": dict(CLAIMS),
        "artifact_digests": {"runtime": hashlib.sha256(b"fixture-runtime").hexdigest()},
        "physical_bytes_observed": True,
        "custody_independent": True,
        "production_touched": False,
    }
    signature = private_key.sign(canonical_json(payload))
    envelope = {
        "payload": payload,
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "algorithm": "Ed25519",
    }
    return envelope, issuer, private_key


def _verify(
    envelope: dict,
    issuer: AuthorizedIssuer | None,
    consumed_receipt_ids: frozenset[str] = frozenset(),
) -> dict:
    return verify_public_acceptance_receipt(
        envelope,
        issuer=issuer,
        expected_candidate=B03_COMMIT,
        expected_tree=B03_TREE,
        expected_claims=CLAIMS,
        now_ms=NOW_MS,
        maximum_age_ms=1_000,
        consumed_receipt_ids=consumed_receipt_ids,
    )


def _resign(envelope: dict, key: Ed25519PrivateKey) -> None:
    envelope["signature_b64"] = base64.b64encode(
        key.sign(canonical_json(envelope["payload"]))
    ).decode("ascii")


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        (ExecutionObservation(12, True, False, None), ExecutionOutcome.LIVE_PID_POLL),
        (ExecutionObservation(12, False, True, None), ExecutionOutcome.TIMEOUT_WITHOUT_REFUSAL),
        (ExecutionObservation(12, True, True, None), ExecutionOutcome.TIMEOUT_WITHOUT_REFUSAL),
        (ExecutionObservation(12, False, False, 1), ExecutionOutcome.ORDINARY_TECHNICAL_ERROR),
        (
            ExecutionObservation(12, False, False, None, authorization_granted=False),
            ExecutionOutcome.AUTHORIZATION_PENDING,
        ),
        (
            ExecutionObservation(None, False, False, None, stderr=EXPLICIT_REFUSAL_TEXT.encode()),
            ExecutionOutcome.EXPLICIT_PLATFORM_REFUSAL,
        ),
        (ExecutionObservation(None, False, False, None), ExecutionOutcome.UNKNOWN_UNCLASSIFIED),
    ],
)
def test_execution_outcomes_are_mutually_exclusive(observation, expected) -> None:
    assert classify_execution_outcome(observation) is expected


def test_public_receipt_accepts_authorized_ed25519_fixture() -> None:
    envelope, issuer, _ = _envelope()
    assert _verify(envelope, issuer)["accepted"] is True


def test_public_receipt_rejects_tamper() -> None:
    envelope, issuer, _ = _envelope()
    envelope["payload"]["physical_bytes_observed"] = False
    with pytest.raises(ReceiptRejected):
        _verify(envelope, issuer)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("count", "COUNT_MISMATCH"),
        ("missing", "PAYLOAD_SCHEMA"),
        ("forged_issuer", "FORGED_ISSUER"),
        ("wrong_candidate", "WRONG_CANDIDATE"),
        ("wrong_tree", "INCONSISTENT_TREE"),
        ("pid_command", "PID_COMMAND_MISMATCH"),
        ("stale", "STALE_TIMESTAMP"),
    ],
)
def test_public_receipt_negative_matrix(mutation: str, code: str) -> None:
    envelope, issuer, key = _envelope()
    payload = envelope["payload"]
    if mutation == "count":
        payload["claims"]["focused_passed"] = 42
    elif mutation == "missing":
        payload.pop("artifact_digests")
    elif mutation == "forged_issuer":
        payload["issuer_id"] = "forged"
    elif mutation == "wrong_candidate":
        payload["candidate_commit"] = "0" * 40
    elif mutation == "wrong_tree":
        payload["candidate_tree"] = "0" * 40
    elif mutation == "pid_command":
        payload["pid_command_id"] = "other-command"
    elif mutation == "stale":
        payload["observed_at_ms"] = NOW_MS - 1_001
    _resign(envelope, key)
    with pytest.raises(ReceiptRejected) as error:
        _verify(envelope, issuer)
    assert error.value.code == code


def test_public_receipt_rejects_forged_signature() -> None:
    envelope, issuer, _ = _envelope()
    other_key = Ed25519PrivateKey.generate()
    _resign(envelope, other_key)
    with pytest.raises(ReceiptRejected) as error:
        _verify(envelope, issuer)
    assert error.value.code == "SIGNATURE_INVALID"


@pytest.mark.parametrize(
    ("issuer_change", "code"),
    [
        ({"revoked": True}, "ISSUER_REVOKED"),
        ({"valid_until_ms": NOW_MS - 1}, "ISSUER_EXPIRED_OR_NOT_YET_VALID"),
        ({"authorization_status": "PENDING"}, "ISSUER_AUTHORIZATION_MISSING"),
    ],
)
def test_public_receipt_rejects_invalid_issuer(issuer_change: dict, code: str) -> None:
    envelope, issuer, _ = _envelope()
    issuer = replace(issuer, **issuer_change)
    with pytest.raises(ReceiptRejected) as error:
        _verify(envelope, issuer)
    assert error.value.code == code


def _admission() -> AdmissionEvidence:
    return AdmissionEvidence(
        expected_denominator=523,
        observed_denominator=523,
        passed_count=523,
        safe_terminal_expected=100,
        safe_terminal_correct=100,
        candidate_commit=B03_COMMIT,
        expected_candidate_commit=B03_COMMIT,
        source_tree=B03_TREE,
        expected_source_tree=B03_TREE,
        clock_monotonic=True,
        latency_p95_ms=900.0,
        latency_limit_ms=1_000.0,
        idp_receipt_valid=True,
        signer_receipt_valid=True,
        source_fresh=True,
        issuer_authorized=True,
        custody_independent=True,
        release_authorized=True,
    )


def test_admission_fixture_passes_but_never_sets_product_go() -> None:
    result = evaluate_f35_rel01(_admission())
    assert result["passed"] is True
    assert result["formal_product_go"] is False
    assert result["rel02_status"] == "NO_GO"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"observed_denominator": 522}, "FIXED_DENOMINATOR_MISMATCH"),
        ({"passed_count": 522}, "FULL_DENOMINATOR_NOT_PASSED"),
        ({"safe_terminal_correct": 99}, "FALSE_SAFE_OR_UNSAFE_TERMINAL"),
        ({"candidate_commit": "0" * 40}, "CANDIDATE_COMMIT_MISMATCH"),
        ({"clock_monotonic": False}, "CLOCK_NOT_MONOTONIC"),
        ({"latency_p95_ms": 1_001.0}, "LATENCY_OUTLIER"),
        ({"idp_receipt_valid": False}, "IDP_RECEIPT_ABSENT_OR_INVALID"),
        ({"signer_receipt_valid": False}, "SIGNER_RECEIPT_ABSENT_OR_INVALID"),
        ({"source_fresh": False}, "STALE_SOURCE"),
        ({"issuer_authorized": False}, "WRONG_OR_UNAUTHORIZED_ISSUER"),
        ({"custody_independent": False}, "CUSTODY_NOT_INDEPENDENT"),
        ({"release_authorized": False}, "REL01_AUTHORIZATION_ABSENT"),
        ({"production_touched": True}, "PRODUCTION_TOUCH_FORBIDDEN"),
    ],
)
def test_admission_negative_matrix(change: dict, reason: str) -> None:
    result = evaluate_f35_rel01(replace(_admission(), **change))
    assert result["passed"] is False
    assert result["formal_product_go"] is False
    assert reason in result["reason_codes"]


def test_same_uid_hmac_cannot_be_presented_as_independent_receipt() -> None:
    envelope, issuer, _ = _envelope()
    envelope["algorithm"] = "HMAC-SHA256"
    with pytest.raises(ReceiptRejected) as error:
        _verify(envelope, issuer)
    assert error.value.code == "UNSUPPORTED_OR_SELF_SIGNATURE"


def test_copy_is_not_new_independent_evidence() -> None:
    envelope, issuer, _ = _envelope()
    copied = copy.deepcopy(envelope)
    assert copied == envelope
    first = _verify(envelope, issuer)
    with pytest.raises(ReceiptRejected) as error:
        _verify(copied, issuer, frozenset({first["receipt_id"]}))
    assert error.value.code == "REPLAYED_OR_COPIED_RECEIPT"
