from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = "m27-c01-residual-case-ledger/v1"
DETERMINATION_SCHEMA = "m27-c01-acceptance-determination/v1"
APPROVAL_SCHEMA = "m27-c01-owner-contract-adr/v1"

BASE_COMMIT = "f857622be0e07a3979e65275a4b4c402c5ec7e8b"
BASE_TREE = "962cbc34a2a0bfe0e921912312b9e9a1713a202b"

ADJUDICATIONS = {
    "ACTUAL_ENGINEERING_DEFECT_FIXED",
    "CONTRACT_OBSOLETE_PENDING_OWNER_ADR",
    "LEGACY_ACCEPTANCE_REQUIRES_NEW_CUSTODIAN",
    "REAL_GATE_STILL_RED",
    "NEEDS_C02_INTERFACE",
}

BUCKETS = {
    "CURRENT_CANONICAL_ACTUALLY_PASSED",
    "LEGACY_UNMODIFIED_STILL_FAILING",
    "SUPERSEDED_PROPOSED_NOT_APPROVED",
    "OWNER_ADR_FORMALLY_ACCEPTED",
    "C02_EXTERNAL_CAPABILITY_HOLD",
    "ORIGINAL_M26_SIX_PRESERVED",
}


class ContractGateError(ValueError):
    pass


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    payload = {key: item for key, item in value.items() if key != "self_sha256"}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def self_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_self_digest(value: Mapping[str, Any], label: str) -> None:
    actual = value.get("self_sha256")
    if not isinstance(actual, str) or len(actual) != 64:
        raise ContractGateError(f"{label}: MISSING_SELF_SHA256")
    if actual != self_digest(value):
        raise ContractGateError(f"{label}: SELF_SHA256_MISMATCH")


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ContractGateError(f"{label}: INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractGateError(f"{label}: INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ContractGateError(f"{label}: TIMESTAMP_MUST_HAVE_TIMEZONE")
    return parsed.astimezone(UTC)


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ContractGateError(f"{label}: INVALID_SHA256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ContractGateError(f"{label}: INVALID_SHA256") from exc
    return value


def _resolve(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractGateError(f"{label}: MISSING_PATH")
    path = Path(value)
    return path if path.is_absolute() else root / path


def validate_case_ledger(
    ledger: Mapping[str, Any],
    *,
    repo_root: Path,
    verify_files: bool = True,
) -> dict[str, int]:
    verify_self_digest(ledger, "ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        raise ContractGateError("ledger: WRONG_SCHEMA")
    source = ledger.get("source")
    if not isinstance(source, Mapping):
        raise ContractGateError("ledger: MISSING_SOURCE")
    if source.get("commit") != BASE_COMMIT or source.get("tree") != BASE_TREE:
        raise ContractGateError("ledger: WRONG_BASELINE_LINEAGE")

    cases = ledger.get("cases")
    if not isinstance(cases, list) or len(cases) != 53:
        raise ContractGateError("ledger: EXACT_53_CASES_REQUIRED")
    node_ids = [case.get("node_id") for case in cases if isinstance(case, Mapping)]
    if len(node_ids) != 53 or len(set(node_ids)) != 53:
        raise ContractGateError("ledger: NODE_IDS_MUST_BE_53_UNIQUE")

    owners = Counter()
    adjudications = Counter()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping):
            raise ContractGateError(f"case {index}: NOT_AN_OBJECT")
        owner = case.get("owner")
        if owner not in {"C01", "C02"}:
            raise ContractGateError(f"case {index}: INVALID_OWNER")
        owners[str(owner)] += 1
        adjudication = case.get("adjudication")
        if adjudication not in ADJUDICATIONS:
            raise ContractGateError(f"case {index}: INVALID_ADJUDICATION")
        adjudications[str(adjudication)] += 1
        if owner == "C02" and adjudication != "NEEDS_C02_INTERFACE":
            raise ContractGateError(f"case {index}: C02_OWNERSHIP_RECLASSIFIED")
        if owner == "C01" and adjudication == "NEEDS_C02_INTERFACE":
            raise ContractGateError(f"case {index}: C01_WRONGLY_ASSIGNED_TO_C02")
        if case.get("source") != {"commit": BASE_COMMIT, "tree": BASE_TREE}:
            raise ContractGateError(f"case {index}: WRONG_CASE_SOURCE_LINEAGE")

        test = case.get("original_test")
        raw = case.get("original_failure")
        if not isinstance(test, Mapping) or not isinstance(raw, Mapping):
            raise ContractGateError(f"case {index}: MISSING_CUSTODY")
        _require_sha(test.get("sha256"), f"case {index} test")
        _require_sha(raw.get("raw_log_sha256"), f"case {index} raw log")
        if not raw.get("failed_assertion") or not raw.get("expected_behavior"):
            raise ContractGateError(f"case {index}: MISSING_EXPECTED_ACTUAL")
        if not raw.get("actual_behavior"):
            raise ContractGateError(f"case {index}: MISSING_ACTUAL_BEHAVIOR")
        invariants = case.get("invariants")
        if not isinstance(invariants, list) or not invariants:
            raise ContractGateError(f"case {index}: MISSING_INVARIANTS")
        if not case.get("risk"):
            raise ContractGateError(f"case {index}: MISSING_RISK")
        measurement = case.get("current_measurement")
        if not isinstance(measurement, Mapping):
            raise ContractGateError(f"case {index}: MISSING_CURRENT_MEASUREMENT")
        outcome = measurement.get("outcome")
        if adjudication == "ACTUAL_ENGINEERING_DEFECT_FIXED" and outcome != "PASS":
            raise ContractGateError(f"case {index}: FIXED_CASE_NOT_MEASURED_PASS")
        if owner == "C02" and outcome != "NOT_RUN_C02_OWNED":
            raise ContractGateError(f"case {index}: C02_CASE_WAS_RECLASSIFIED")
        if (
            owner == "C01"
            and adjudication != "ACTUAL_ENGINEERING_DEFECT_FIXED"
            and outcome != "FAIL"
        ):
            raise ContractGateError(f"case {index}: HISTORIC_RED_WAS_RELABELED")

        if verify_files:
            test_path = _resolve(repo_root, test.get("path"), f"case {index} test")
            if not test_path.is_file() or file_sha256(test_path) != test.get("sha256"):
                raise ContractGateError(f"case {index}: ORIGINAL_TEST_TAMPER")
            raw_path = _resolve(repo_root, raw.get("raw_log_path"), f"case {index} raw log")
            if not raw_path.is_file() or file_sha256(raw_path) != raw.get("raw_log_sha256"):
                raise ContractGateError(f"case {index}: RAW_LOG_TAMPER")
            candidate = case.get("canonical_candidate")
            if not isinstance(candidate, Mapping):
                raise ContractGateError(f"case {index}: MISSING_CANONICAL_CANDIDATE")
            for prefix in ("implementation", "public_acceptance"):
                candidate_path = _resolve(
                    repo_root, candidate.get(f"{prefix}_path"), f"case {index} {prefix}"
                )
                candidate_sha = _require_sha(
                    candidate.get(f"{prefix}_sha256"), f"case {index} {prefix}"
                )
                if not candidate_path.is_file() or file_sha256(candidate_path) != candidate_sha:
                    raise ContractGateError(f"case {index}: {prefix.upper()}_TAMPER")

    if owners != Counter({"C01": 51, "C02": 2}):
        raise ContractGateError("ledger: OWNERSHIP_MUST_BE_C01_51_C02_2")
    declared = ledger.get("counts")
    measured = {
        "total": 53,
        "c01_owned": 51,
        "c02_owned": 2,
        **{key: adjudications.get(key, 0) for key in sorted(ADJUDICATIONS)},
    }
    if declared != measured:
        raise ContractGateError("ledger: DECLARED_COUNTS_MISMATCH")
    return measured


def validate_case_receipts(ledger: Mapping[str, Any], *, repo_root: Path) -> int:
    cases = ledger.get("cases")
    if not isinstance(cases, list):
        raise ContractGateError("receipts: LEDGER_CASES_MISSING")
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping):
            raise ContractGateError(f"receipt {index}: INVALID_CASE")
        path = _resolve(repo_root, case.get("evidence_receipt"), f"receipt {index}")
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractGateError(f"receipt {index}: MISSING_OR_INVALID") from exc
        if not isinstance(receipt, Mapping):
            raise ContractGateError(f"receipt {index}: NOT_AN_OBJECT")
        verify_self_digest(receipt, f"receipt {index}")
        if receipt.get("ledger_self_sha256") != ledger.get("self_sha256"):
            raise ContractGateError(f"receipt {index}: WRONG_LEDGER_BINDING")
        if receipt.get("case") != case:
            raise ContractGateError(f"receipt {index}: CASE_BINDING_MISMATCH")
    return len(cases)


def approval_denials(
    approval: Mapping[str, Any],
    case: Mapping[str, Any],
    *,
    repo_root: Path,
    trusted_issuers: Sequence[str],
    trusted_verifiers: Sequence[str],
    now: datetime,
) -> list[str]:
    denials: list[str] = []
    if approval.get("schema_version") != APPROVAL_SCHEMA:
        denials.append("WRONG_ADR_SCHEMA")
    if approval.get("node_id") != case.get("node_id"):
        denials.append("LEGACY_FRESH_SCOPE_AMBIGUOUS")
    original = case.get("original_test", {})
    if not approval.get("original_test_sha256"):
        denials.append("MISSING_ORIGINAL_TEST_SHA256")
    elif approval.get("original_test_sha256") != original.get("sha256"):
        denials.append("ORIGINAL_TEST_SHA256_MISMATCH")
    source = approval.get("source", {})
    if not isinstance(source, Mapping):
        denials.append("MISSING_SOURCE_LINEAGE")
    else:
        if source.get("commit") != BASE_COMMIT:
            denials.append("WRONG_SOURCE_LINEAGE")
        if source.get("tree") != BASE_TREE:
            denials.append("WRONG_SOURCE_TREE")
    issuer = approval.get("issuer", {})
    if not isinstance(issuer, Mapping) or issuer.get("id") not in trusted_issuers:
        denials.append("UNTRUSTED_ISSUER")
    elif issuer.get("role") not in {"owner", "contract_issuer"}:
        denials.append("ISSUER_ROLE_NOT_AUTHORIZED")
    signature = approval.get("signature_receipt", {})
    if not isinstance(signature, Mapping) or signature.get("verified") is not True:
        denials.append("FORGED_OR_UNVERIFIED_ADR")
    else:
        if signature.get("verifier_id") not in trusted_verifiers:
            denials.append("UNTRUSTED_SIGNATURE_VERIFIER")
        try:
            _require_sha(signature.get("signature_sha256"), "signature")
        except ContractGateError:
            denials.append("INVALID_SIGNATURE_RECEIPT")
    if approval.get("target_scope") != "current_contract_only":
        denials.append("LEGACY_FRESH_SCOPE_AMBIGUOUS")
    if approval.get("historic_outcome_preserved") is not True:
        denials.append("HISTORIC_OUTCOME_NOT_PRESERVED")
    candidate = case.get("canonical_candidate", {})
    if approval.get("canonical_contract_version") != candidate.get("version"):
        denials.append("STALE_OR_ROLLBACK_CONTRACT_VERSION")
    if approval.get("supersedes_contract_version") != candidate.get("historic_version"):
        denials.append("STALE_OR_ROLLBACK_SUPERSESSION")
    try:
        issued = _timestamp(approval.get("issued_at"), "approval issued_at")
        expires = _timestamp(approval.get("expires_at"), "approval expires_at")
        if expires <= issued or now.astimezone(UTC) >= expires:
            denials.append("ADR_EXPIRED")
    except ContractGateError:
        denials.append("INVALID_ADR_TIME_WINDOW")
    semantic = approval.get("semantic_proof", {})
    if case.get("publication_capable") is True and (
        not isinstance(semantic, Mapping) or semantic.get("status") != "verified"
    ):
        denials.append("SEMANTIC_PROOF_DENIED")
    bindings = approval.get("source_bindings")
    if not isinstance(bindings, list) or not bindings:
        denials.append("MISSING_SOURCE_BINDINGS")
    else:
        for binding in bindings:
            if not isinstance(binding, Mapping):
                denials.append("INVALID_SOURCE_BINDING")
                continue
            try:
                path = _resolve(repo_root, binding.get("path"), "approval source")
                expected = _require_sha(binding.get("sha256"), "approval source")
                if not path.is_file() or file_sha256(path) != expected:
                    denials.append("SOURCE_TAMPER")
            except ContractGateError:
                denials.append("INVALID_SOURCE_BINDING")
    return sorted(set(denials))


def case_bucket(case: Mapping[str, Any], *, formally_accepted: bool = False) -> str:
    if case.get("owner") == "C02":
        return "C02_EXTERNAL_CAPABILITY_HOLD"
    if formally_accepted:
        return "OWNER_ADR_FORMALLY_ACCEPTED"
    if (
        case.get("adjudication") == "ACTUAL_ENGINEERING_DEFECT_FIXED"
        and case.get("current_measurement", {}).get("outcome") == "PASS"
    ):
        return "CURRENT_CANONICAL_ACTUALLY_PASSED"
    if case.get("adjudication") == "CONTRACT_OBSOLETE_PENDING_OWNER_ADR":
        return "SUPERSEDED_PROPOSED_NOT_APPROVED"
    return "LEGACY_UNMODIFIED_STILL_FAILING"


def build_determination(ledger: Mapping[str, Any]) -> dict[str, Any]:
    cases = ledger["cases"]
    decisions = [
        {
            "case_id": case["case_id"],
            "node_id": case["node_id"],
            "bucket": case_bucket(case),
            "owner": case["owner"],
            "approval_reference": None,
        }
        for case in cases
    ]
    counts = Counter(item["bucket"] for item in decisions)
    denominators = {key: counts.get(key, 0) for key in sorted(BUCKETS)}
    denominators["ORIGINAL_M26_SIX_PRESERVED"] = 6
    result: dict[str, Any] = {
        "schema_version": DETERMINATION_SCHEMA,
        "ledger_self_sha256": ledger["self_sha256"],
        "source": {"commit": BASE_COMMIT, "tree": BASE_TREE},
        "current_all_green": False,
        "formal_owner_adrs_accepted": 0,
        "decisions": decisions,
        "denominators": denominators,
        "release_effect": "NONE_NONPROD_ONLY",
    }
    result["self_sha256"] = self_digest(result)
    return result


def validate_determination(
    determination: Mapping[str, Any], ledger: Mapping[str, Any]
) -> dict[str, int]:
    verify_self_digest(determination, "determination")
    if determination.get("schema_version") != DETERMINATION_SCHEMA:
        raise ContractGateError("determination: WRONG_SCHEMA")
    if determination.get("ledger_self_sha256") != ledger.get("self_sha256"):
        raise ContractGateError("determination: WRONG_LEDGER_BINDING")
    if determination.get("current_all_green") is not False:
        raise ContractGateError("determination: UNMEASURED_ALL_GREEN_CLAIM")
    expected = build_determination(ledger)
    if determination.get("decisions") != expected["decisions"]:
        raise ContractGateError("determination: DECISION_MISMATCH")
    if determination.get("denominators") != expected["denominators"]:
        raise ContractGateError("determination: DENOMINATOR_MISMATCH")
    return dict(determination["denominators"])
