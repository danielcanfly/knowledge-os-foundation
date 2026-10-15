"""Fail-closed authority inventory and release decisions for Wave B02.

This module recognizes only immutable local evidence.  It never converts local
Nonprod authorization into an external issuer, Product release, or C28 launch
grant.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from wave_b02 import ABI


REPO = Path(__file__).resolve().parents[1]
MASTER_ROOT = REPO.parents[2]
REPORTS = MASTER_ROOT / "02_REPORTS" / "PARALLEL_VNEXT_20261014"
DISPATCH = MASTER_ROOT / "01_DISPATCH" / "PARALLEL_VNEXT_20261014"
B01_HEAD = "f47400fea3858260c9c34691af99b592f2f5c89b"
B01_TREE = "006d55fb59d58d701f68047afe45953e6676bde4"

VALID_STATUSES = {
    "AUTHORIZED_WITH_RECEIPT",
    "NOT_PROVEN",
    "EXPLICITLY_REFUSED",
    "OUT_OF_SCOPE",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proof(path: Path, *, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "immutable_identity": True,
    }


def build_authority_ledger(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    accepted = REPORTS / "MASTER_B01_FINAL_SCOPED_ACCEPTANCE_20261015.md"
    accepted_json = REPORTS / "MASTER_B01_FINAL_SCOPED_ACCEPTANCE_20261015.json"
    dispatch = DISPATCH / "B02_MASTER_DISPATCH_AUTHORITY_PREFLIGHT_20261016.md"
    common = DISPATCH / "00_SHARED_EXECUTION_AND_100_PERCENT_RULES.md"
    accepted_proof = proof(accepted, kind="MASTER_ACCEPTANCE")
    dispatch_proof = proof(dispatch, kind="OWNER_DISPATCH")

    def row(status: str, scope: str, evidence: Iterable[dict[str, Any]] = (),
            reason: str | None = None) -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError("INVALID_AUTHORITY_STATUS")
        return {
            "status": status,
            "scope": scope,
            "evidence": list(evidence),
            "reason": reason,
            "checked_at": now.isoformat(),
        }

    entries = {
        "b01_accepted_source": row(
            "AUTHORIZED_WITH_RECEIPT", "B01_NONPROD_EXACT_HEAD_TREE",
            [accepted_proof, proof(accepted_json, kind="MACHINE_ACCEPTANCE")]),
        "b02_local_engineering": row(
            "AUTHORIZED_WITH_RECEIPT", "LOCAL_NONPROD_S1_S4",
            [dispatch_proof, proof(common, kind="COMMON_RULES")]),
        "local_open_model": row(
            "AUTHORIZED_WITH_RECEIPT", "LOCAL_NONPROD_QWEN_ONLY",
            [accepted_proof], "Model/runtime/license digests are pinned by accepted B01."),
        "local_disposable_rollback": row(
            "AUTHORIZED_WITH_RECEIPT", "B02_OWNED_LOCAL_SANDBOX_ONLY",
            [dispatch_proof]),
        "formal_external_issuer": row(
            "NOT_PROVEN", "PRODUCT_SIGNING", reason="No genuine external issuer receipt."),
        "trusted_idp": row(
            "NOT_PROVEN", "EXTERNAL_IDP", reason="No genuine IdP grant or attestation."),
        "external_provider": row(
            "NOT_PROVEN", "BILLABLE_OR_REMOTE_PROVIDER", reason="No provider authorization/invoice."),
        "signed_artifact_coverage": row(
            "NOT_PROVEN", "SIGNED_RUNNABLE_PRODUCT", reason="Candidate is deliberately unsigned content-only."),
        "ci_signing_staging": row(
            "EXPLICITLY_REFUSED", "PRIVATE_CI_SIGNING_OR_STAGING",
            reason="MG23 equivalent operation was explicitly refused; no retry."),
        "production": row(
            "OUT_OF_SCOPE", "PRODUCTION", reason="Owner dispatch forbids Production mutation."),
        "c28_launch": row(
            "NOT_PROVEN", "C28_LIVE_TRIAL", reason="Separate launch authorization absent."),
        "remote_kill_switch": row(
            "NOT_PROVEN", "REMOTE_ROLLBACK_OR_KILL_SWITCH", reason="Only local disposable rollback is authorized."),
        "q34_native_streaming": row(
            "EXPLICITLY_REFUSED", "FROZEN_Q34_NATIVE_STREAMING",
            reason="Prior refusal preserved; Q34 remains frozen."),
        "product_qdrant": row(
            "EXPLICITLY_REFUSED", "ACTUAL_PRODUCT_QDRANT",
            reason="MG25 equivalent operation was explicitly refused; no retry."),
        "a08_coding_source_edit": row(
            "EXPLICITLY_REFUSED", "PERSISTED_CODING_SOURCE_PATCH",
            reason="Prior same-scope refusal preserved; no relay or rephrase."),
        "sealed_evaluation": row(
            "OUT_OF_SCOPE", "PROTECTED_OR_SEALED_EVALUATION",
            reason="No read, run, or mutation authorization."),
    }
    return {
        "schema": "m27.wave-b02.authority-ledger/v1",
        "abi": ABI,
        "generated_at": now.isoformat(),
        "sole_source": {"head": B01_HEAD, "tree": B01_TREE},
        "entries": entries,
        "secrets_inspected": False,
        "external_operations_attempted": False,
    }


def receipt_is_valid(row: Mapping[str, Any]) -> bool:
    if row.get("status") != "AUTHORIZED_WITH_RECEIPT":
        return False
    evidence = row.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        try:
            path = Path(item["path"])
            expected = item["sha256"]
        except (KeyError, TypeError):
            return False
        if not path.is_file() or len(str(expected)) != 64:
            return False
        if sha256_file(path) != expected:
            return False
    expires = row.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
                return False
        except (TypeError, ValueError):
            return False
    return True


LOCAL_REQUIRED = (
    "b01_accepted_source",
    "b02_local_engineering",
    "local_open_model",
    "local_disposable_rollback",
)
FORMAL_REQUIRED = (
    "formal_external_issuer",
    "trusted_idp",
    "external_provider",
    "signed_artifact_coverage",
    "ci_signing_staging",
    "remote_kill_switch",
)


def evaluate_release_gates(ledger: Mapping[str, Any]) -> dict[str, Any]:
    entries = ledger["entries"]
    local = {name: receipt_is_valid(entries[name]) for name in LOCAL_REQUIRED}
    formal = {name: receipt_is_valid(entries[name]) for name in FORMAL_REQUIRED}
    return {
        "schema": "m27.wave-b02.release-gates/v1",
        "abi": ABI,
        "nonprod_preflight_engineering_pass": all(local.values()),
        "formal_product_go": all(formal.values()),
        "c28_live_trial": receipt_is_valid(entries["c28_launch"]),
        "deployment_permitted": False,
        "local_gate_checks": local,
        "formal_gate_checks": formal,
        "external_gate_truth": {
            "formal_x01_x09": "0/9_NOT_RUN",
            "official_original523": "0/523_NOT_RUN",
            "official_product_blind200": "0/200_NOT_RUN",
            "q34_native_streaming": "NOT_QUALIFIED",
            "m26_regression": "857_PASS_6_HISTORICAL_FAIL",
            "a02_signature": "UNSIGNED_NONPROD_READ_ONLY",
        },
        "preserved_refusals": [
            name for name, row in entries.items()
            if row["status"] == "EXPLICITLY_REFUSED"
        ],
    }


@dataclass
class ReplayGuard:
    """Local deterministic replay guard; it is not a remote IdP."""

    accepted_issuer: str = "b02-local-witness"

    def __post_init__(self) -> None:
        self._seen: set[str] = set()

    def admit(self, envelope: Mapping[str, Any]) -> None:
        if envelope.get("issuer") != self.accepted_issuer:
            raise PermissionError("WRONG_ISSUER")
        if envelope.get("certificate_sha256") != "b" * 64:
            raise PermissionError("CERTIFICATE_MISMATCH")
        nonce = envelope.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise PermissionError("NONCE_REQUIRED")
        if nonce in self._seen:
            raise PermissionError("MALICIOUS_REPLAY")
        self._seen.add(nonce)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_local_model_runtime(runtime: Path, manifest_path: Path) -> dict[str, Any]:
    """Validate a staged B01 runtime without reading credentials or networking."""
    if not runtime.is_dir() or not (runtime / "STAGE_RECEIPT.json").is_file():
        raise RuntimeError("MODEL_NOT_LOADED")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = {}
    for name, spec in (
        ("model", manifest["model"]),
        ("cli", {"filename": manifest["llama_cpp"]["cli"],
                 "sha256": manifest["llama_cpp"]["cli_sha256"],
                 "bytes": manifest["llama_cpp"]["cli_bytes"]}),
    ):
        path = runtime / spec["filename"]
        checks[name] = (path.is_file() and path.stat().st_size == spec["bytes"]
                        and sha256_file(path) == spec["sha256"])
    if not all(checks.values()):
        raise RuntimeError("MODEL_RUNTIME_DIGEST_MISMATCH")
    return {"validated": True, "checks": checks,
            "stage_receipt_sha256": sha256_file(runtime / "STAGE_RECEIPT.json")}


def enforce_provider_budget(records: Iterable[Mapping[str, Any]], *,
                            max_attempts: int, max_total_ms: float) -> dict[str, Any]:
    rows = list(records)
    total_ms = sum(float(row.get("duration_ms", 0)) for row in rows)
    if len(rows) > max_attempts or total_ms > max_total_ms:
        raise RuntimeError("PROVIDER_RUNAWAY_DENIED")
    if any(int(row.get("billable_provider_calls", 0)) != 0 for row in rows):
        raise RuntimeError("EXTERNAL_PROVIDER_CALL_DENIED")
    return {"attempts": len(rows), "total_ms": round(total_ms, 3)}
