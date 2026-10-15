"""Versioned Wave B01 integration boundary for Master-accepted Nonprod inputs.

This module is intentionally a consumer-side adapter.  It does not write Q34,
Production, sealed evaluation assets, or release pointers.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from a08_nonprod.experiment import CANDIDATE
from knowledge_engine.m27_a09_abi_conformance import x09_evidence
from wave_b01.components.a05.adapter.a05_retrieval import ContextIndex
from wave_b01.components.a06.runner import contract_valid


ABI = "m27.wave-b01.nonprod-integration/v1"
ROOT = Path(__file__).resolve().parent
A05_SOURCE = ROOT / "components" / "a05" / "source"
A02_ATTESTATION = ROOT / "evidence_inputs" / "a02_current_candidate_attestation.json"
A10_RECEIPT = ROOT / "evidence_inputs" / "a10_scoped_completion.json"
A10_CONTRACT = ROOT / "interfaces" / "a10_public_contract.json"
A04_CONTRACT = ROOT / "components" / "a04" / "INTEGRATION_CONTRACT_REQUEST.json"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("OBJECT_REQUIRED")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def admit_task_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Admit the A06 task lane while keeping A08's provider lane isolated.

    A06 has three authorized local source reads and one reversible local action.
    A08 is provider-only simulation with zero tool grants.  Their budgets are
    therefore recorded as separate lanes rather than silently broadening either.
    """
    candidate = dict(contract)
    contract_valid(candidate)
    if CANDIDATE.max_provider_calls > 3 or CANDIDATE.max_tool_calls != 0:
        raise ValueError("A08_POLICY_SCOPE_WIDENED")
    return {
        "abi": ABI,
        "task_lane": {
            "version": candidate["version"],
            "run_id": candidate["run_id"],
            "tenant": candidate["tenant"],
            "rights": list(candidate["rights"]),
            "budget": dict(candidate["budget"]),
        },
        "provider_lane": {
            "policy": CANDIDATE.policy_id,
            "revision": CANDIDATE.revision,
            "review_only": True,
            "max_provider_calls": CANDIDATE.max_provider_calls,
            "max_tool_calls": CANDIDATE.max_tool_calls,
            "economics": "SIMULATED_NOT_INVOICE",
        },
        "production_authority": False,
    }


def retrieve_context(question: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Retrieve only A05 source-backed passages; memory is never mixed in."""
    index = ContextIndex(A05_SOURCE)
    result = index.search(
        question=question,
        tenant="owner-internal",
        roles=["internal"],
        release_id=index.release["release_id"],
        source_revision=index.release["source_revision_q34"],
        now=now,
    )
    result["memory_candidates_included"] = 0
    result["citation_authority"] = "A05_PINNED_FIRSTPARTY_SOURCE_ONLY"
    return result


def validate_a04_stream(events: Sequence[Mapping[str, Any]]) -> None:
    """Translate A04 claim/terminal events into A09 X09 evidence events."""
    normalized: list[dict[str, Any]] = []
    source_manifest: dict[str, str] = {}
    for event in events:
        kind = event.get("event")
        if kind == "claim.verified":
            source_id = event.get("source_id")
            source_sha256 = event.get("source_sha256")
            if isinstance(source_id, str) and isinstance(source_sha256, str):
                source_manifest[source_id] = source_sha256
            normalized.append({
                "type": "generated",
                "text": event.get("text"),
                "source_id": source_id,
                "source_sha256": source_sha256,
                "span": event.get("span"),
            })
        elif kind == "run.terminal":
            normalized.append({
                "type": "terminal",
                "text": "",
                "source_id": "",
                "source_sha256": "",
                "span": [],
            })
    x09_evidence(normalized, source_manifest=source_manifest)


def attestations_and_eval_gates() -> dict[str, Any]:
    """Admit only public/read-only A02 and A10 evidence without upgrading it."""
    a02 = _json(A02_ATTESTATION)
    a10 = _json(A10_RECEIPT)
    a10_contract = _json(A10_CONTRACT)
    if a02.get("signature") != {
        "formal_release_authority": False,
        "issuer": None,
        "mode": "UNSIGNED_NONPROD",
    }:
        raise ValueError("A02_AUTHORITY_ESCALATION")
    conflicts = a02.get("historical_conflicts", {})
    if not all(item.get("difference_preserved") is True or item.get("mismatch_preserved") is True
               for item in conflicts.values()):
        raise ValueError("A02_HISTORY_NOT_PRESERVED")
    if (a10.get("protected_existing_sealed200", {}).get("read") is not False
            or a10.get("official_original523", {}).get("run") is not False
            or a10.get("official_blind200_product", {}).get("run") is not False
            or a10_contract.get("release_authority") is not False
            or a10_contract.get("production_authority") is not False):
        raise ValueError("A10_EXTERNAL_GATE_ESCALATION")
    return {
        "abi": ABI,
        "a02": "UNSIGNED_NONPROD_READ_ONLY",
        "a02_formal_release_authority": False,
        "a10_public_only": True,
        "official_original523": "NOT_RUN_0_OF_523",
        "official_product_blind200": "NOT_RUN_0_OF_200",
        "sealed_content_read": False,
    }


def candidate_manifest() -> dict[str, Any]:
    a04 = _json(A04_CONTRACT)
    if a04.get("native_q34_integrated") is not False:
        raise ValueError("A04_NATIVE_Q34_SCOPE_WIDENED")
    return {
        "abi": ABI,
        "scope": "NONPROD_ONLY",
        "inputs": {
            "a02_attestation_sha256": sha256_file(A02_ATTESTATION),
            "a04_contract_sha256": sha256_file(A04_CONTRACT),
            "a05_release_sha256": sha256_file(A05_SOURCE / "release.json"),
            "a10_public_contract_sha256": sha256_file(A10_CONTRACT),
            "a10_public_receipt_sha256": sha256_file(A10_RECEIPT),
        },
        "boundaries": {
            "q34_unchanged": True,
            "production_unchanged": True,
            "sealed_evaluation_not_read": True,
            "historical_failures_preserved": True,
            "release_authority": False,
        },
    }
