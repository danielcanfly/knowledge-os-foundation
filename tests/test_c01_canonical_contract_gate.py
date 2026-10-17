from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from knowledge_engine.c01_canonical_contract_gate import (
    BASE_COMMIT,
    BASE_TREE,
    ContractGateError,
    approval_denials,
    case_bucket,
    self_digest,
    validate_case_receipts,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(source: Path) -> dict:
    return {
        "node_id": "tests/test_contract.py::test_contract",
        "original_test": {"sha256": "a" * 64},
        "canonical_candidate": {
            "historic_version": "legacy/v1",
            "version": "canonical/v2",
        },
        "publication_capable": True,
        "source": source,
    }


def _approval(source: Path) -> dict:
    now = datetime.now(UTC)
    return {
        "schema_version": "m27-c01-owner-contract-adr/v1",
        "node_id": "tests/test_contract.py::test_contract",
        "original_test_sha256": "a" * 64,
        "source": {"commit": BASE_COMMIT, "tree": BASE_TREE},
        "issuer": {"id": "owner-1", "role": "owner"},
        "signature_receipt": {
            "verified": True,
            "verifier_id": "verifier-1",
            "signature_sha256": "b" * 64,
        },
        "target_scope": "current_contract_only",
        "historic_outcome_preserved": True,
        "canonical_contract_version": "canonical/v2",
        "supersedes_contract_version": "legacy/v1",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "semantic_proof": {"status": "verified"},
        "source_bindings": [{"path": source.name, "sha256": _sha(source)}],
    }


def _denials(tmp_path: Path, mutate) -> list[str]:
    source = tmp_path / "source.txt"
    source.write_text("canonical source\n", encoding="utf-8")
    approval = _approval(source)
    mutate(approval, source)
    return approval_denials(
        approval,
        _case(source),
        repo_root=tmp_path,
        trusted_issuers=["owner-1"],
        trusted_verifiers=["verifier-1"],
        now=datetime.now(UTC),
    )


def test_complete_external_approval_contract_is_admissible(tmp_path):
    assert _denials(tmp_path, lambda _approval, _source: None) == []


@pytest.mark.parametrize(
    ("case", "accepted", "expected"),
    [
        (
            {
                "owner": "C01",
                "adjudication": "ACTUAL_ENGINEERING_DEFECT_FIXED",
                "current_measurement": {"outcome": "PASS"},
            },
            False,
            "CURRENT_CANONICAL_ACTUALLY_PASSED",
        ),
        (
            {
                "owner": "C01",
                "adjudication": "REAL_GATE_STILL_RED",
                "current_measurement": {"outcome": "FAIL"},
            },
            False,
            "LEGACY_UNMODIFIED_STILL_FAILING",
        ),
        (
            {
                "owner": "C01",
                "adjudication": "CONTRACT_OBSOLETE_PENDING_OWNER_ADR",
                "current_measurement": {"outcome": "FAIL"},
            },
            False,
            "SUPERSEDED_PROPOSED_NOT_APPROVED",
        ),
        (
            {
                "owner": "C01",
                "adjudication": "CONTRACT_OBSOLETE_PENDING_OWNER_ADR",
                "current_measurement": {"outcome": "FAIL"},
            },
            True,
            "OWNER_ADR_FORMALLY_ACCEPTED",
        ),
        (
            {
                "owner": "C02",
                "adjudication": "NEEDS_C02_INTERFACE",
                "current_measurement": {"outcome": "NOT_RUN_C02_OWNED"},
            },
            False,
            "C02_EXTERNAL_CAPABILITY_HOLD",
        ),
    ],
)
def test_version_aware_buckets_keep_historic_and_current_outcomes_separate(
    case, accepted, expected
):
    assert case_bucket(case, formally_accepted=accepted) == expected


def test_case_receipt_tamper_fails_closed(tmp_path):
    case = {"case_id": "C01-001", "evidence_receipt": "case.json"}
    ledger = {"cases": [case], "self_sha256": "a" * 64}
    receipt = {
        "ledger_self_sha256": ledger["self_sha256"],
        "case": case,
    }
    receipt["self_sha256"] = self_digest(receipt)
    receipt_path = tmp_path / "case.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert validate_case_receipts(ledger, repo_root=tmp_path) == 1

    receipt["case"] = {**case, "case_id": "tampered"}
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ContractGateError, match="SELF_SHA256_MISMATCH"):
        validate_case_receipts(ledger, repo_root=tmp_path)


@pytest.mark.parametrize(
    ("expected", "mutate"),
    [
        ("WRONG_SOURCE_LINEAGE", lambda a, _s: a["source"].update(commit="0" * 40)),
        ("WRONG_SOURCE_TREE", lambda a, _s: a["source"].update(tree="0" * 40)),
        ("UNTRUSTED_ISSUER", lambda a, _s: a["issuer"].update(id="forged")),
        ("FORGED_OR_UNVERIFIED_ADR", lambda a, _s: a["signature_receipt"].update(verified=False)),
        ("MISSING_ORIGINAL_TEST_SHA256", lambda a, _s: a.pop("original_test_sha256")),
        (
            "STALE_OR_ROLLBACK_CONTRACT_VERSION",
            lambda a, _s: a.update(canonical_contract_version="legacy/v1"),
        ),
        ("LEGACY_FRESH_SCOPE_AMBIGUOUS", lambda a, _s: a.update(target_scope="all_versions")),
        ("SOURCE_TAMPER", lambda _a, s: s.write_text("tampered\n", encoding="utf-8")),
        ("ADR_EXPIRED", lambda a, _s: a.update(expires_at="2000-01-01T00:00:00+00:00")),
        ("SEMANTIC_PROOF_DENIED", lambda a, _s: a["semantic_proof"].update(status="denied")),
    ],
)
def test_owner_adr_fail_closed_negatives(tmp_path, expected, mutate):
    assert expected in _denials(tmp_path, mutate)
