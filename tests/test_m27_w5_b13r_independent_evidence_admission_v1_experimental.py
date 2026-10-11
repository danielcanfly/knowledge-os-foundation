"""B13R >=45 distinct negative receipts; no B13 original positive run executed."""
from __future__ import annotations

import copy
import json

import pytest

from knowledge_engine.m27_w5_b13r_independent_evidence_admission_v1_experimental import (
    B13_COMMIT,
    DENIED_OPERATIONS,
    DENIED_STATUS,
    MANIFEST_SHA,
    MODULE_IMPORT_ORDER,
    OBLIGATIONS,
    PROFILE,
    RECEIPT_SCHEMA,
    SAFE_NEXT_STEPS,
    SCHEMA,
    B13IndependentEvidenceAdmissionV1,
    EvidenceRejected,
    admission,
    canonical,
    empty_proposal,
    review_history,
    validate_proposal,
)


def candidate(obligation="F13_TWO_CANONICAL_ZIPS"):
    doc = empty_proposal()
    artifact = {
        "id": "untrusted-synthetic-a1",
        "obligation": obligation,
        "digest": "1" * 64,
        "byte_count": 500,
        "locator": "artifact://untrusted/untrusted-synthetic-a1",
        "candidate_commit": B13_COMMIT,
        "f13_manifest_sha256": MANIFEST_SHA,
        "source_count": 20,
        "zip_entry_count": 21,
        "module_ids": list(MODULE_IMPORT_ORDER),
        "python_flags": ["-I", "-S", "-B"],
        "producer_domain": "UNTRUSTED_LOCAL_PROPOSAL",
        "feature_profile": PROFILE,
        "algorithm": "NONE_UNVERIFIED",
        "local_claim": "CLAIMED_PASS",
        "run_id": "synthetic-run-a1",
    }
    witness = {
        "id": "synthetic-witness-1",
        "artifact_id": artifact["id"],
        "obligation": obligation,
        "observed_digest": artifact["digest"],
        "witness_digest": "2" * 64,
        "observer_domain": "UNTRUSTED_SYNTHETIC_PROPOSAL",
        "observer_id": "not-independent",
        "observed_at_ms": 2000,
        "produced_at_ms": 1000,
        "independent_bytes_readback": False,
    }
    doc["artifacts"] = [artifact]
    doc["witnesses"] = [witness]
    return doc


def fail(reason, proposal):
    with pytest.raises(EvidenceRejected) as exc:
        validate_proposal(proposal)
    assert exc.value.code == reason


TOP = [
    ("missing_schema", "PROPOSAL_SCHEMA_FORGED"),
    ("extra_gate", "PROPOSAL_SCHEMA_FORGED"),
    ("wrong_schema", "PROPOSAL_VERSION_MISMATCH"),
    ("stale_commit", "PROPOSAL_COMMIT_FORGED"),
    ("replayed_f12_manifest", "PROPOSAL_F13_MANIFEST_FORGED"),
    ("f13_sha_valid_looking_fake", "PROPOSAL_F13_MANIFEST_FORGED"),
    ("wrong_profile", "PROPOSAL_PROFILE_FORGED"),
    ("fake_prod", "PROPOSAL_UNAUTHORIZED_PROMOTION: production_authorized"),
    ("fake_owner_grant", "PROPOSAL_UNAUTHORIZED_PROMOTION: owner_grant"),
    ("fake_release", "PROPOSAL_UNAUTHORIZED_PROMOTION: release_certified"),
    ("fake_phase_b", "PROPOSAL_UNAUTHORIZED_PROMOTION: real_phase_b_admitted"),
    ("self_claim_pass", "PROPOSAL_FALSE_POSITIVE_STATUS"),
    ("false_green_zip", "PROPOSAL_FALSE_POSITIVE_STATUS"),
    ("safety_denial_deleted", "PROPOSAL_DENIAL_HISTORY_ERASED"),
    ("safety_denial_as_timeout", "PROPOSAL_DENIAL_HISTORY_ERASED"),
    ("denied_action_complete", "PROPOSAL_DENIAL_HISTORY_ERASED"),
    ("wrong_denial_order", "PROPOSAL_DENIAL_HISTORY_ERASED"),
    ("denial_rerouted_rdc", "PROPOSAL_DENIAL_HISTORY_ERASED"),
    ("artifacts_invalid_type", "PROPOSAL_RECEIPT_COLLECTION_INVALID"),
    ("witnesses_invalid_type", "PROPOSAL_RECEIPT_COLLECTION_INVALID"),
    ("artifact_list_huge", "PROPOSAL_RECEIPT_LIMIT_EXCEEDED"),
    ("witness_list_huge", "PROPOSAL_RECEIPT_LIMIT_EXCEEDED"),
]


@pytest.mark.parametrize(("kind", "reason"), TOP, ids=[t[0] for t in TOP])
def test_top_level_forgery_cases(kind, reason):
    p = empty_proposal()
    if kind == "missing_schema":
        p.pop("schema")
    elif kind == "extra_gate":
        p["signed_release"] = True
    elif kind == "wrong_schema":
        p["schema"] = "m27.w5.b13r/v0"
    elif kind == "stale_commit":
        p["candidate_commit"] = "a" * 40
    elif kind == "replayed_f12_manifest":
        p["f13_manifest_sha256"] = (
            "051dafba045515350d0908886fcc9d46da30262df5839cb383c685574a47f751"
        )
    elif kind == "f13_sha_valid_looking_fake":
        p["f13_manifest_sha256"] = "f" * 64
    elif kind == "wrong_profile":
        p["trust_profile"] = "ALL_FEATURES_VERIFIED"
    elif kind in ("fake_prod", "fake_owner_grant", "fake_release", "fake_phase_b"):
        field = {"fake_prod": "production_authorized", "fake_owner_grant": "owner_grant",
                 "fake_release": "release_certified",
                 "fake_phase_b": "real_phase_b_admitted"}[kind]
        p[field] = True
    elif kind in ("self_claim_pass", "false_green_zip"):
        p["claimed_status"] = ("B13_CORE_COMPLETE_PASS" if kind == "self_claim_pass"
                               else "B13_LOCAL_20_SOURCE_BYTES_REPRODUCIBLE_PASS")
    elif kind == "safety_denial_deleted":
        p["denials"] = []
    elif kind == "safety_denial_as_timeout":
        p["denials"][0]["disposition"] = "TECHNICAL_TIMEOUT"
    elif kind == "denied_action_complete":
        p["denials"][0]["disposition"] = "COMPLETED"
    elif kind == "wrong_denial_order":
        p["denials"].reverse()
    elif kind == "denial_rerouted_rdc":
        p["denials"][0]["disposition"] = "RDC_SUCCESS"
    elif kind == "artifacts_invalid_type":
        p["artifacts"] = {}
    elif kind == "witnesses_invalid_type":
        p["witnesses"] = None
    elif kind == "artifact_list_huge":
        p["artifacts"] = [None] * (len(OBLIGATIONS) * 4 + 1)
    elif kind == "witness_list_huge":
        p["witnesses"] = [None] * (len(OBLIGATIONS) * 8 + 1)
    fail(reason, p)


ARTIFACT = [
    ("extra_signer_field", "ARTIFACT_SCHEMA_FORGED"),
    ("missing_sha", "ARTIFACT_SCHEMA_FORGED"),
    ("bad_id", "ARTIFACT_ID_INVALID"),
    ("replay_id_untyped", "ARTIFACT_ID_INVALID"),
    ("bad_run_id", "ARTIFACT_ID_INVALID"),
    ("unknown_obligation", "ARTIFACT_OBLIGATION_UNKNOWN"),
    ("invalid_digest", "ARTIFACT_DIGEST_INVALID"),
    ("zero_digest", "ARTIFACT_DIGEST_INVALID"),
    ("negative_size", "ARTIFACT_SIZE_INVALID"),
    ("bool_size", "ARTIFACT_SIZE_INVALID"),
    ("host_source_path", "ARTIFACT_PATH_PROVENANCE_SPOOF"),
    ("mutable_tag", "ARTIFACT_PATH_PROVENANCE_SPOOF"),
    ("cross_domain_locator", "ARTIFACT_PATH_PROVENANCE_SPOOF"),
    ("wrong_source_commit", "ARTIFACT_FROZEN_BINDING_MISMATCH"),
    ("wrong_source_sha", "ARTIFACT_FROZEN_BINDING_MISMATCH"),
    ("nineteen_source", "ARTIFACT_SOURCE_CARDINALITY"),
    ("bool_source_count", "ARTIFACT_SOURCE_CARDINALITY"),
    ("nineteen_zip_entries", "ARTIFACT_ZIP_CARDINALITY"),
    ("truncated_zip_entries", "ARTIFACT_ZIP_CARDINALITY"),
    ("nineteen_imports", "ARTIFACT_MODULE_IDENTITY_OR_ORDER"),
    ("duplicate_module_replaces_broker", "ARTIFACT_MODULE_IDENTITY_OR_ORDER"),
    ("wrong_i02_order", "ARTIFACT_MODULE_IDENTITY_OR_ORDER"),
    ("injected_module", "ARTIFACT_MODULE_IDENTITY_OR_ORDER"),
    ("missing_isolation", "ARTIFACT_ISOLATION_UNVERIFIED"),
    ("site_enabled", "ARTIFACT_ISOLATION_UNVERIFIED"),
    ("fake_owner_producer", "ARTIFACT_PRODUCER_AUTHORITY_FORGED"),
    ("fake_external_producer", "ARTIFACT_PRODUCER_AUTHORITY_FORGED"),
    ("all_features_mode", "ARTIFACT_OPTIONAL_POLICY_FORGED"),
    ("fixture_hmac_as_ed25519", "ARTIFACT_SIGNATURE_SELF_ATTESTED"),
    ("fake_ed25519_pass", "ARTIFACT_SIGNATURE_SELF_ATTESTED"),
    ("unknown_local_claim", "ARTIFACT_CLAIM_INVALID"),
    ("fake_external_oci_pass", "ARTIFACT_RELEASE_PROMOTION_FORBIDDEN"),
    ("fake_client_p95_pass", "ARTIFACT_RELEASE_PROMOTION_FORBIDDEN"),
    ("fake_phaseb_labels_pass", "ARTIFACT_RELEASE_PROMOTION_FORBIDDEN"),
    ("fake_first_text_client_ack", "ARTIFACT_RELEASE_PROMOTION_FORBIDDEN"),
]


@pytest.mark.parametrize(("kind", "reason"), ARTIFACT, ids=[x[0] for x in ARTIFACT])
def test_artifact_metadata_adversaries(kind, reason):
    obligation = {
        "fake_external_oci_pass": "REAL_EXECUTED_OCI_IMAGE",
        "fake_client_p95_pass": "CLIENT_ACK_PROVIDER_COST",
        "fake_phaseb_labels_pass": "AR09_PHASE_B",
        "fake_first_text_client_ack": "CLIENT_ACK_PROVIDER_COST",
    }.get(kind, "F13_TWO_CANONICAL_ZIPS")
    p = candidate(obligation)
    a = p["artifacts"][0]
    if kind == "extra_signer_field":
        a["real_signed_oci"] = True
    elif kind == "missing_sha":
        a.pop("digest")
    elif kind == "bad_id":
        a["id"] = "../traversal"
    elif kind == "replay_id_untyped":
        a["id"] = 1
    elif kind == "bad_run_id":
        a["run_id"] = ""
    elif kind == "unknown_obligation":
        a["obligation"] = "FAKE_SOURCE_RIGHTS"
    elif kind == "invalid_digest":
        a["digest"] = "q" * 64
    elif kind == "zero_digest":
        a["digest"] = "0" * 64
    elif kind == "negative_size":
        a["byte_count"] = -1
    elif kind == "bool_size":
        a["byte_count"] = True
    elif kind == "host_source_path":
        a["locator"] = "/Users/huaihsuanhuang/Desktop/Chatgpt/src/secret.py"
    elif kind == "mutable_tag":
        a["locator"] = "docker://latest"
    elif kind == "cross_domain_locator":
        a["locator"] = "https://fake.test/attestation"
    elif kind == "wrong_source_commit":
        a["candidate_commit"] = "f" * 40
    elif kind == "wrong_source_sha":
        a["f13_manifest_sha256"] = "f" * 64
    elif kind == "nineteen_source":
        a["source_count"] = 19
    elif kind == "bool_source_count":
        a["source_count"] = True
    elif kind == "nineteen_zip_entries":
        a["zip_entry_count"] = 20
    elif kind == "truncated_zip_entries":
        a["zip_entry_count"] = 1
    elif kind == "nineteen_imports":
        a["module_ids"].pop()
    elif kind == "duplicate_module_replaces_broker":
        a["module_ids"][1] = a["module_ids"][2]
    elif kind == "wrong_i02_order":
        a["module_ids"].reverse()
    elif kind == "injected_module":
        a["module_ids"][4] = "knowledge_engine.malicious"
    elif kind == "missing_isolation":
        a["python_flags"] = ["-I", "-S"]
    elif kind == "site_enabled":
        a["python_flags"] = ["-I", "-B", "-s"]
    elif kind == "fake_owner_producer":
        a["producer_domain"] = "OWNER_SIGNED"
    elif kind == "fake_external_producer":
        a["producer_domain"] = "INDEPENDENT_AUDITOR_SIGNED"
    elif kind == "all_features_mode":
        a["feature_profile"] = "ED25519_FULL_VERIFIED"
    elif kind == "fixture_hmac_as_ed25519":
        a["algorithm"] = "HMAC_SHA256_FAKE_AUTHORITY"
    elif kind == "fake_ed25519_pass":
        a["algorithm"] = "ED25519_VERIFIED"
    elif kind == "unknown_local_claim":
        a["local_claim"] = "PASS_REAL_IMAGE"
    fail(reason, p)


WITNESS = [
    ("extra_root", "WITNESS_SCHEMA_FORGED"),
    ("missing_observer_id", "WITNESS_SCHEMA_FORGED"),
    ("bad_witness_id", "WITNESS_ID_INVALID"),
    ("fake_observer_id", "WITNESS_ID_INVALID"),
    ("unknown_artifact", "WITNESS_UNKNOWN_ARTIFACT"),
    ("obligation_drift", "WITNESS_OBLIGATION_MISMATCH"),
    ("bad_observed_sha", "WITNESS_DIGEST_INVALID"),
    ("bad_witness_sha", "WITNESS_DIGEST_INVALID"),
    ("hash_mismatch", "WITNESS_SOURCE_HASH_MISMATCH"),
    ("pretend_external_authority", "WITNESS_INDEPENDENT_DOMAIN_UNPROVEN"),
    ("pretend_master_signature", "WITNESS_INDEPENDENT_DOMAIN_UNPROVEN"),
    ("timestamp_reverse", "WITNESS_TIME_ORDER_INVALID"),
    ("timestamp_zero", "WITNESS_TIME_ORDER_INVALID"),
    ("timestamp_string", "WITNESS_TIME_ORDER_INVALID"),
    ("self_assert_actual_bytes", "WITNESS_BYTE_PROOF_SELF_ASSERTED"),
]


@pytest.mark.parametrize(("kind", "reason"), WITNESS, ids=[x[0] for x in WITNESS])
def test_witness_forgery_and_negative_provenance(kind, reason):
    p = candidate()
    r = p["witnesses"][0]
    if kind == "extra_root":
        r["external_root"] = "owner"
    elif kind == "missing_observer_id":
        r.pop("observer_id")
    elif kind == "bad_witness_id":
        r["id"] = "../owner"
    elif kind == "fake_observer_id":
        r["observer_id"] = True
    elif kind == "unknown_artifact":
        r["artifact_id"] = "ghost"
    elif kind == "obligation_drift":
        r["obligation"] = "P09_OPTIONAL_ED25519"
    elif kind == "bad_observed_sha":
        r["observed_digest"] = "g" * 64
    elif kind == "bad_witness_sha":
        r["witness_digest"] = "0" * 64
    elif kind == "hash_mismatch":
        r["observed_digest"] = "a" * 64
    elif kind == "pretend_external_authority":
        r["observer_domain"] = "REAL_EXTERNAL_SIGNED_AUTHORITY"
    elif kind == "pretend_master_signature":
        r["observer_domain"] = "MASTER_INDEPENDENT_VERIFIER"
    elif kind == "timestamp_reverse":
        r["observed_at_ms"] = 900
    elif kind == "timestamp_zero":
        r["produced_at_ms"] = 0
    elif kind == "timestamp_string":
        r["observed_at_ms"] = "2000"
    elif kind == "self_assert_actual_bytes":
        r["independent_bytes_readback"] = True
    fail(reason, p)


COLLECTION = [
    ("no_witness", "ARTIFACT_INDEPENDENT_WITNESS_MISSING"),
    ("duplicate_artifact_id", "ARTIFACT_DUPLICATE_ID"),
    ("duplicate_run_id", "ARTIFACT_REPLAY_RUN_ID"),
    ("replayed_archive_digest", "ARTIFACT_REUSED_DIGEST"),
    ("duplicate_witness_id", "WITNESS_DUPLICATE_ID"),
    ("duplicate_witness_for_archive", "WITNESS_REPLAY"),
]


@pytest.mark.parametrize(("kind", "reason"), COLLECTION, ids=[x[0] for x in COLLECTION])
def test_duplicate_replay_and_torn_receipt_negative(kind, reason):
    p = candidate()
    if kind == "no_witness":
        p["witnesses"] = []
    elif kind.startswith("duplicate_artifact") or kind == "duplicate_run_id" or (
        kind == "replayed_archive_digest"
    ):
        clone = copy.deepcopy(p["artifacts"][0])
        clone["id"] = "untrusted-synthetic-a2"
        clone["locator"] = "artifact://untrusted/untrusted-synthetic-a2"
        clone["run_id"] = "synthetic-run-a2"
        clone["digest"] = "3" * 64
        if kind == "duplicate_artifact_id":
            clone["id"] = p["artifacts"][0]["id"]
            clone["locator"] = p["artifacts"][0]["locator"]
        elif kind == "duplicate_run_id":
            clone["run_id"] = p["artifacts"][0]["run_id"]
        elif kind == "replayed_archive_digest":
            clone["digest"] = p["artifacts"][0]["digest"]
        p["artifacts"].append(clone)
    else:
        clone = copy.deepcopy(p["witnesses"][0])
        clone["id"] = "synthetic-witness-2"
        if kind == "duplicate_witness_id":
            clone["id"] = p["witnesses"][0]["id"]
        p["witnesses"].append(clone)
    fail(reason, p)


@pytest.mark.parametrize(("worker", "master", "reason"), [
    ("fake green", "blocked due to safety", "HISTORY_REFUSAL_NOT_CONFIRMED"),
    ("B13_BLOCKED", "blocked due to safety", "HISTORY_REFUSAL_NOT_CONFIRMED"),
    ("B13_BLOCKED platform safety refusal", "master green", "HISTORY_REFUSAL_NOT_CONFIRMED"),
    (None, "master safety", "HISTORY_INVALID_TYPE"),
    ("worker", None, "HISTORY_INVALID_TYPE"),
])
def test_untrusted_history_fails_closed(worker, master, reason):
    with pytest.raises(EvidenceRejected) as ex:
        review_history(worker, master)
    assert ex.value.code == reason


def test_empty_proposal_is_a_safe_local_validator_not_package_pass():
    proposal = empty_proposal()
    result = B13IndependentEvidenceAdmissionV1.assess(proposal)
    assert result["schema"] == RECEIPT_SCHEMA
    assert result["statuses"]["validator"] == "EVIDENCE_GAP_VALIDATOR_LOCAL_PASS"
    assert result["statuses"]["positive"] == "B13_POSITIVE_RUN_NOT_VERIFIED"
    assert result["statuses"]["zip"] == "B13_20_FILE_ZIP_NOT_VERIFIED"
    assert result["statuses"]["imports"] == "B13_I02_20_MODULE_IMPORT_NOT_VERIFIED"
    assert result["statuses"]["lazy"] == "B13_AR03_LAZY_FUNCTION_NOT_VERIFIED"
    assert result["statuses"]["crypto"] == "B13_P09_ABSENT_CRYPTO_NOT_VERIFIED"
    assert result["statuses"]["ed25519_denial"] == "OPTIONAL_ED25519_DENIAL_UNVERIFIED"
    assert result["statuses"]["release"] == "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"
    assert result["statuses"]["all_features_closed"] is False
    assert result["statuses"]["production_authorized"] is False
    assert result["metadata"]["artifact_metadata_records"] == 0
    assert result["denied_operations"] == [
        {"operation_id": op, "status": DENIED_STATUS} for op in DENIED_OPERATIONS
    ]
    assert tuple(result["safe_non_equivalent_next_steps"]) == SAFE_NEXT_STEPS
    assert len(result["proof_obligations"]) == 13
    assert result["receipt_sha256"] and len(result["receipt_sha256"]) == 64
    assert result["evidence_admitted_to_core"] is False
    assert result["signed_authority_admitted"] is False
    assert result["release_permitted"] is False


def test_credible_looking_synthetic_bytes_and_witness_still_no_positive():
    p = candidate()
    m = validate_proposal(p)
    assert m["metadata_status"] == "STRUCTURALLY_VALID_NOT_INDEPENDENTLY_ATTESTED"
    assert m["independent_original_bytes_observed"] is False
    a = admission(p)
    assert a["statuses"]["positive"] == "B13_POSITIVE_RUN_NOT_VERIFIED"
    assert a["statuses"]["zip"] == "B13_20_FILE_ZIP_NOT_VERIFIED"
    assert a["statuses"]["release"] == "REAL_CI_OCI_AND_REL01_REL02_UNAUTHORIZED"
    assert a["evidence_admitted_to_core"] is False
    assert len(canonical(a)) and canonical(json.loads(canonical(a))) == canonical(a)


def test_release_claim_unknown_denied_and_other_external_gates():
    for obligation in ("REAL_EXECUTED_OCI_IMAGE", "REAL_EXTERNAL_SIGNER",
                       "CLIENT_ACK_PROVIDER_COST", "AR09_PHASE_B",
                       "REL01_RELEASE", "REL02_PRODUCTION"):
        p = candidate(obligation)
        p["artifacts"][0]["local_claim"] = "UNKNOWN"
        assert admission(p)["release_permitted"] is False


def test_history_blocker_in_a_realistic_document_pair():
    p = empty_proposal()
    result = admission(p, worker_report="B13_BLOCKED: platform safety refusal",
                       master_review="BLOCKED due to platform safety refusal")
    assert result["historical_review"]["interpretation"] == (
        "HISTORICAL_REFUSALS_PRESERVED_NO_POSITIVE_PROOF"
    )
    assert result["statuses"]["positive"] == "B13_POSITIVE_RUN_NOT_VERIFIED"


@pytest.mark.parametrize(("worker", "master"), [
    (None, "BLOCKED"),
    ("B13_BLOCKED", None),
])
def test_history_partial_pair_never_authorizes(worker, master):
    with pytest.raises(EvidenceRejected) as e:
        admission(empty_proposal(), worker_report=worker, master_review=master)
    assert e.value.code == "HISTORY_PAIR_INCOMPLETE"


def test_denied_history_operations_are_exact_and_not_transport_failures():
    doc = empty_proposal()
    assert doc["schema"] == SCHEMA
    assert len(doc["denials"]) == len(DENIED_OPERATIONS) == 2
    assert all(r["disposition"] == "DENIED_NO_EQUIVALENT_RETRY"
               for r in doc["denials"])
    assert "B13_POSITIVE_RUN_NOT_VERIFIED" in canonical(admission(doc)).decode()
