"""B13R independent metadata-evidence seam. Never runs refused B13 positive operations.

A plausible self-issued receipt, synthetically witnessed SHA, or green pytest
cannot create independent source, executable, signer, provider or release proof.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA = "m27.w5.b13r.independent.evidence.proposal/v1"
RECEIPT_SCHEMA = "m27.w5.b13r.independent.evidence.debt/v1"
MANIFEST_SHA = "0781bb17f1dd405e5140accc1071d019742643902849bb75cd512af9be2f0cde"
B13_COMMIT = "c8bcc4f7f2fe124556f9f60768b8ea1cd248000c"
PROFILE = "CORE_OFFLINE_FEATURE_OFF"
SOURCE_MODULES = (
    "m27_ar02_durable_writer_v1_experimental",
    "m27_ar03_context_broker_experimental",
    "m27_ar03_verified_rights_v1_experimental",
    "m27_ar04_permit_sandbox_v1_experimental",
    "m27_ar05_independent_verifier_v1_experimental",
    "m27_ar06_governed_memory_experimental",
    "m27_ar07_compute_policy_experimental",
    "m27_i01_core_local_vertical_v1_experimental",
    "m27_w3_ar06_durable_governance_v1_experimental",
    "m27_w3_ar07_compute_budget_v1_experimental",
    "m27_w3_ar08_coding_action_v1_experimental",
    "m27_w3_ar08_qa_stream_v1_experimental",
    "m27_w3_ar08_research_recovery_v1_experimental",
    "m27_w4_ar09_independent_harness_v1_experimental",
    "m27_w4_d09_corpus_admission_v1_experimental",
    "m27_w4_e09b_blind_gate_v1_experimental",
    "m27_w4_i02_local_runtime_v1_experimental",
    "m27_w4_p09_external_evidence_v1_experimental",
    "m27_w4_t09_transport_evidence_v1_experimental",
    "m27_w5_l10_ar10_candidate_governance_v1_experimental",
)
I02 = "m27_w4_i02_local_runtime_v1_experimental"
MODULE_IMPORT_ORDER = (I02, *(n for n in SOURCE_MODULES if n != I02))
SAFE_NEXT_STEPS = (
    "INTERFACE_CONTRACT_READ_ONLY_REVIEW",
    "SYNTHETIC_NEGATIVE_ONLY_TESTS",
    "EVIDENCE_RECEIPT_SCHEMA_VALIDATION",
    "INDEPENDENT_UNRELATED_SCOPED_BUG_FIX",
)
DENIED_OPERATIONS = (
    "B13_OFFLINE_CORE_DEPENDENCY_CLOSURE_POSITIVE_RUN",
    "MASTER_F13_20_SOURCE_GIT_BLOB_BATCH_READBACK",
)
DENIED_STATUS = "DENIED_NO_EQUIVALENT_RETRY"

# The distinction between an obligation's need and what can be trusted is
# intentional. There is no attestation trust root in this offline component.
@dataclass(frozen=True)
class Obligation:
    id: str
    requires: tuple[str, ...]
    required_domain: str
    status: str
    original_operation: str | None = None


OBLIGATIONS = (
    Obligation("F13_ORIGINAL_20_BLOBS", ("20 originals", "Git blob equality",
                                       "20 SHA256 on-disk comparisons"),
               "independent_original_blob_observer",
               "F13_SHA_BLOB_COMPARISON_NOT_VERIFIED",
               DENIED_OPERATIONS[1]),
    Obligation("F13_TWO_CANONICAL_ZIPS", ("2 independently rooted builds",
                                          "21 canonical ZIP entries",
                                          "equal full bytes", "20 source SHA bindings"),
               "independent_byte_level_archive_observer",
               "B13_20_FILE_ZIP_NOT_VERIFIED",
               DENIED_OPERATIONS[0]),
    Obligation("B13_ISOLATED_20_IMPORTS", ("pinned Python 3.11.15 -I -S -B",
                                            "I02 first", "20 origin+spec SHA checks",
                                            "no host/site shadow"),
               "independent_fresh_process_observer",
               "B13_I02_20_MODULE_IMPORT_NOT_VERIFIED",
               DENIED_OPERATIONS[0]),
    Obligation("AR06_TO_AR03_LAZY", ("real AR06 function-local call",
                                     "original AR03 broker select",
                                     "deny-first tenant/purpose/revocation"),
               "independent_function_execution_observer",
               "B13_AR03_LAZY_FUNCTION_NOT_VERIFIED",
               DENIED_OPERATIONS[0]),
    Obligation("P09_OPTIONAL_ED25519", ("actual no-cryptography interpreter",
                                        "real P09 rejection, no VERIFIED/ADMITTED",
                                        "real independent root requirement"),
               "independent_cryptography_failure_observer",
               "B13_P09_ABSENT_CRYPTO_NOT_VERIFIED",
               DENIED_OPERATIONS[0]),
    Obligation("SOURCE_PACKAGE_BINDING", ("archive bytes / manifest / source commit",
                                           "independent archive readback"),
               "independent_package_provenance_observer",
               "B13_SOURCE_PACKAGE_BINDING_NOT_VERIFIED"),
    Obligation("TEST_COMMIT_PROVENANCE", ("exact B13 commit / tests / Ruff",
                                         "independent Master replay"),
               "independent_local_master",
               "B13_TEST_COMMIT_PROVENANCE_HISTORICALLY_ACCEPTED_ONLY"),
    Obligation("REAL_EXECUTED_OCI_IMAGE", ("actual immutable OCI digest",
                                           "independent build and execution attestation"),
               "external_ci_oci_signer",
               "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"),
    Obligation("REAL_EXTERNAL_SIGNER", ("cryptographic Ed25519 authority",
                                         "trust root and custody proof"),
               "independent_external_rights_authority",
               "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"),
    Obligation("CLIENT_ACK_PROVIDER_COST", ("actual first answer client ACK",
                                             "real pricing and p95",
                                             "original eligible 523"),
               "independent_client_and_billing_auditor",
               "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"),
    Obligation("AR09_PHASE_B", ("qualified independent unseen holdout",
                                  "lawful rights and original outcomes"),
               "independent_unseen_evaluator",
               "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"),
    Obligation("REL01_RELEASE", ("all release hard gates", "independent authorization"),
               "release_authority", "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"),
    Obligation("REL02_PRODUCTION", ("production change authorization",
                                    "signed rollout and rollback"),
               "production_release_authority",
               "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"),
)
BY_OBLIGATION = {o.id: o for o in OBLIGATIONS}
LOCAL_OBLIGATIONS = frozenset(o.id for o in OBLIGATIONS[:7])
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


class EvidenceRejected(ValueError):
    """Typed, fail-closed evidence rejection (never an attestation success)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def check(ok: bool, code: str) -> None:
    if not ok:
        raise EvidenceRejected(code)


def exact(obj: Any, keys: set[str], error: str) -> None:
    check(type(obj) is dict and set(obj) == keys, error)


def valid_sha(value: object) -> bool:
    return type(value) is str and SHA.fullmatch(value) is not None and value != "0" * 64


def valid_id(value: object) -> bool:
    return type(value) is str and IDENTIFIER.fullmatch(value) is not None


def canonical(document: object) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def empty_proposal() -> dict[str, Any]:
    """Honest no-evidence starting point, never a manufactured positive proof."""
    return {
        "schema": SCHEMA,
        "candidate_commit": B13_COMMIT,
        "f13_manifest_sha256": MANIFEST_SHA,
        "trust_profile": PROFILE,
        "production_authorized": False,
        "owner_grant": False,
        "release_certified": False,
        "real_phase_b_admitted": False,
        "claimed_status": "B13_POSITIVE_RUN_NOT_VERIFIED",
        "artifacts": [],
        "witnesses": [],
        "denials": [
            {"operation_id": op, "disposition": DENIED_STATUS}
            for op in DENIED_OPERATIONS
        ],
    }


_ARTIFACT_KEYS = {
    "id", "obligation", "digest", "byte_count", "locator",
    "candidate_commit", "f13_manifest_sha256", "source_count",
    "zip_entry_count", "module_ids", "python_flags", "producer_domain",
    "feature_profile", "algorithm", "local_claim", "run_id",
}
_WITNESS_KEYS = {
    "id", "artifact_id", "obligation", "observed_digest", "witness_digest",
    "observer_domain", "observer_id", "observed_at_ms", "produced_at_ms",
    "independent_bytes_readback",
}


def validate_artifact(a: object) -> None:
    exact(a, _ARTIFACT_KEYS, "ARTIFACT_SCHEMA_FORGED")
    check(valid_id(a["id"]) and valid_id(a["run_id"]), "ARTIFACT_ID_INVALID")
    check(type(a["obligation"]) is str and a["obligation"] in BY_OBLIGATION,
          "ARTIFACT_OBLIGATION_UNKNOWN")
    check(valid_sha(a["digest"]), "ARTIFACT_DIGEST_INVALID")
    check(type(a["byte_count"]) is int and a["byte_count"] > 0,
          "ARTIFACT_SIZE_INVALID")
    locator = a["locator"]
    check(type(locator) is str and locator == "artifact://untrusted/" + a["id"],
          "ARTIFACT_PATH_PROVENANCE_SPOOF")
    check(a["candidate_commit"] == B13_COMMIT and
          a["f13_manifest_sha256"] == MANIFEST_SHA,
          "ARTIFACT_FROZEN_BINDING_MISMATCH")
    check(type(a["source_count"]) is int and a["source_count"] == 20,
          "ARTIFACT_SOURCE_CARDINALITY")
    check(type(a["zip_entry_count"]) is int and a["zip_entry_count"] == 21,
          "ARTIFACT_ZIP_CARDINALITY")
    mods = a["module_ids"]
    check(type(mods) is list and len(mods) == 20 and
          all(type(m) is str for m in mods) and
          mods == list(MODULE_IMPORT_ORDER), "ARTIFACT_MODULE_IDENTITY_OR_ORDER")
    check(a["python_flags"] == ["-I", "-S", "-B"],
          "ARTIFACT_ISOLATION_UNVERIFIED")
    check(a["producer_domain"] == "UNTRUSTED_LOCAL_PROPOSAL",
          "ARTIFACT_PRODUCER_AUTHORITY_FORGED")
    check(a["feature_profile"] == PROFILE, "ARTIFACT_OPTIONAL_POLICY_FORGED")
    check(a["algorithm"] == "NONE_UNVERIFIED", "ARTIFACT_SIGNATURE_SELF_ATTESTED")
    check(a["local_claim"] in ("UNKNOWN", "CLAIMED_PASS", "DENIED"),
          "ARTIFACT_CLAIM_INVALID")
    check(a["obligation"] in LOCAL_OBLIGATIONS or a["local_claim"] != "CLAIMED_PASS",
          "ARTIFACT_RELEASE_PROMOTION_FORBIDDEN")


def validate_witness(w: object, artifacts: Mapping[str, dict]) -> None:
    exact(w, _WITNESS_KEYS, "WITNESS_SCHEMA_FORGED")
    check(valid_id(w["id"]) and valid_id(w["observer_id"]),
          "WITNESS_ID_INVALID")
    check(type(w["artifact_id"]) is str and w["artifact_id"] in artifacts,
          "WITNESS_UNKNOWN_ARTIFACT")
    a = artifacts[w["artifact_id"]]
    check(w["obligation"] == a["obligation"], "WITNESS_OBLIGATION_MISMATCH")
    check(valid_sha(w["observed_digest"]) and
          valid_sha(w["witness_digest"]), "WITNESS_DIGEST_INVALID")
    check(w["observed_digest"] == a["digest"], "WITNESS_SOURCE_HASH_MISMATCH")
    check(w["observer_domain"] == "UNTRUSTED_SYNTHETIC_PROPOSAL",
          "WITNESS_INDEPENDENT_DOMAIN_UNPROVEN")
    check(type(w["observed_at_ms"]) is int and
          type(w["produced_at_ms"]) is int and
          0 < w["produced_at_ms"] <= w["observed_at_ms"],
          "WITNESS_TIME_ORDER_INVALID")
    # A proposal cannot self-assert byte readback: that needs independently
    # authenticated evidence inaccessible to this negative-only gate.
    check(w["independent_bytes_readback"] is False,
          "WITNESS_BYTE_PROOF_SELF_ASSERTED")


def validate_proposal(data: object) -> dict[str, Any]:
    """Validate typed metadata, never promote it to source/runtime proof."""
    proposal_keys = set(empty_proposal())
    exact(data, proposal_keys, "PROPOSAL_SCHEMA_FORGED")
    check(data["schema"] == SCHEMA, "PROPOSAL_VERSION_MISMATCH")
    check(data["candidate_commit"] == B13_COMMIT, "PROPOSAL_COMMIT_FORGED")
    check(data["f13_manifest_sha256"] == MANIFEST_SHA,
          "PROPOSAL_F13_MANIFEST_FORGED")
    check(data["trust_profile"] == PROFILE, "PROPOSAL_PROFILE_FORGED")
    for field in ("production_authorized", "owner_grant",
                  "release_certified", "real_phase_b_admitted"):
        check(data[field] is False, "PROPOSAL_UNAUTHORIZED_PROMOTION: " + field)
    check(data["claimed_status"] == "B13_POSITIVE_RUN_NOT_VERIFIED",
          "PROPOSAL_FALSE_POSITIVE_STATUS")
    check(type(data["denials"]) is list and
          data["denials"] == empty_proposal()["denials"],
          "PROPOSAL_DENIAL_HISTORY_ERASED")
    check(type(data["artifacts"]) is list and type(data["witnesses"]) is list,
          "PROPOSAL_RECEIPT_COLLECTION_INVALID")
    check(len(data["artifacts"]) <= len(OBLIGATIONS) * 4 and
          len(data["witnesses"]) <= len(OBLIGATIONS) * 8,
          "PROPOSAL_RECEIPT_LIMIT_EXCEEDED")
    artifacts: dict[str, dict] = {}
    run_ids: set[str] = set()
    digests: set[str] = set()
    for a in data["artifacts"]:
        validate_artifact(a)
        check(a["id"] not in artifacts, "ARTIFACT_DUPLICATE_ID")
        check(a["run_id"] not in run_ids, "ARTIFACT_REPLAY_RUN_ID")
        check(a["digest"] not in digests, "ARTIFACT_REUSED_DIGEST")
        artifacts[a["id"]] = a
        run_ids.add(a["run_id"])
        digests.add(a["digest"])
    witnesses: set[str] = set()
    witness_artifacts: set[str] = set()
    for w in data["witnesses"]:
        validate_witness(w, artifacts)
        check(w["id"] not in witnesses, "WITNESS_DUPLICATE_ID")
        check(w["artifact_id"] not in witness_artifacts, "WITNESS_REPLAY")
        witnesses.add(w["id"])
        witness_artifacts.add(w["artifact_id"])
    check(witness_artifacts == set(artifacts),
          "ARTIFACT_INDEPENDENT_WITNESS_MISSING")
    return {
        "proposal_valid": True,
        "artifact_metadata_records": len(artifacts),
        "witness_metadata_records": len(witnesses),
        "metadata_status": "STRUCTURALLY_VALID_NOT_INDEPENDENTLY_ATTESTED",
        "independent_original_bytes_observed": False,
        "independent_signer_authenticated": False,
    }


def review_history(worker_report: str, master_review: str) -> dict[str, str]:
    """Historical text is read-only, untrusted, and unable to grant a PASS."""
    check(type(worker_report) is str and type(master_review) is str,
          "HISTORY_INVALID_TYPE")
    check(len(worker_report) <= 1_000_000 and len(master_review) <= 1_000_000,
          "HISTORY_UNBOUNDED")
    # Absence of a known veto is never evidence of its clearance.
    marker = "B13_BLOCKED" in worker_report and (
        "PLATFORM SAFETY REFUSAL" in worker_report.upper()
        or "PLATFORM SAFETY" in worker_report.upper()
    )
    independently = "BLOCKED" in master_review.upper() and (
        "PLATFORM SAFETY" in master_review.upper()
    )
    check(marker and independently, "HISTORY_REFUSAL_NOT_CONFIRMED")
    return {
        "worker_document_sha256": hashlib.sha256(worker_report.encode()).hexdigest(),
        "master_document_sha256": hashlib.sha256(master_review.encode()).hexdigest(),
        "interpretation": "HISTORICAL_REFUSALS_PRESERVED_NO_POSITIVE_PROOF",
    }


def admission(proposal: object, *,
              worker_report: str | None = None,
              master_review: str | None = None) -> dict[str, Any]:
    """Admit only a local *gap analysis*, never B13 runtime or release proof."""
    metadata = validate_proposal(proposal)
    history: dict[str, str] | None = None
    if worker_report is not None or master_review is not None:
        check(worker_report is not None and master_review is not None,
              "HISTORY_PAIR_INCOMPLETE")
        history = review_history(worker_report, master_review)
    matrix = [asdict(o) for o in OBLIGATIONS]
    statuses = {
        "validator": "EVIDENCE_GAP_VALIDATOR_LOCAL_PASS",
        "positive": "B13_POSITIVE_RUN_NOT_VERIFIED",
        "zip": "B13_20_FILE_ZIP_NOT_VERIFIED",
        "imports": "B13_I02_20_MODULE_IMPORT_NOT_VERIFIED",
        "lazy": "B13_AR03_LAZY_FUNCTION_NOT_VERIFIED",
        "crypto": "B13_P09_ABSENT_CRYPTO_NOT_VERIFIED",
        "ed25519_denial": "OPTIONAL_ED25519_DENIAL_UNVERIFIED",
        "release": "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED",
        "all_features_closed": False,
        "production_authorized": False,
        "REL01": "NOT_CERTIFIED",
        "REL02": "NOT_AUTHORIZED",
    }
    result = {
        "schema": RECEIPT_SCHEMA,
        "f13_manifest_sha256": MANIFEST_SHA,
        "candidate_commit": B13_COMMIT,
        "profile": PROFILE,
        "statuses": statuses,
        "proof_obligations": matrix,
        "evidence_debt": [o.id for o in OBLIGATIONS if
                          o.id != "TEST_COMMIT_PROVENANCE"],
        "metadata": metadata,
        "historical_review": history,
        "denied_operations": [{"operation_id": op, "status": DENIED_STATUS}
                              for op in DENIED_OPERATIONS],
        "safe_non_equivalent_next_steps": list(SAFE_NEXT_STEPS),
        "evidence_admitted_to_core": False,
        "signed_authority_admitted": False,
        "release_permitted": False,
    }
    result["receipt_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


class B13IndependentEvidenceAdmissionV1:
    """Pure, offline, independently versioned evidence-debt validator."""

    @staticmethod
    def assess(proposal: object, *,
               worker_report: str | None = None,
               master_review: str | None = None) -> dict[str, Any]:
        return admission(proposal, worker_report=worker_report,
                         master_review=master_review)
