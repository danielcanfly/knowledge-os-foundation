"""D09 synthetic metadata-only admission tests: never load sealed content."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from knowledge_engine.m27_w4_d09_corpus_admission_v1_experimental import (
    SCHEMA,
    STRATA,
    TrustedCustodyRegistry,
    audit_historical_rows,
    scan_manifest,
    sign_fixture,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
FUTURE = "2027-01-10T00:00:00Z"
PAST = "2026-01-10T00:00:00Z"
SIGN_KEY = b"synthetic-test-key-only-not-external-custody"


def _hash(i: int) -> str:
    return f"{i:064x}"


def fixture_manifest():
    sources = [
        {
            "record_id": f"src{i:03d}",
            "document_id": f"doc{i % 20:02d}",
            "family_id": f"family{i % 5}",
            "origin_id": f"origin{i % 5}",
            "revision": "rev01",
            "source_sha256": _hash(i + 1000),
            "span_index_sha256": _hash(i + 2000),
            "license_id": "licensed-eval",
            "acl_until": FUTURE,
            "retention_until": FUTURE,
            "consent_until": FUTURE,
            "published_at": PAST,
            "issued_at": PAST,
        }
        for i in range(100)
    ]
    strata = [
        key for key, number in STRATA.items() for _ in range(number)
    ]
    cases = []
    for i in range(200):
        parent = i - 140 if i >= 140 else None
        tags = []
        if parent is not None:
            tags.append("PARAPHRASE")
        if i < 40:
            tags.append("LONG_TAIL")
        if i < 30:
            tags.append("MATCHED_NEGATIVE")
        if i < 20:
            tags.extend(["SUPPORTED_POSITIVE", "PROVENANCE_POSITIVE"])
        if i < 12:
            tags.append("GRAPHOLOGY")
        if i < 15:
            tags.append("HISTORICAL_TOPIC")
        source_ids = [f"src{i % 100:03d}"]
        if strata[i] == "CROSS_DOCUMENT":
            source_ids.append(f"src{(i + 5) % 100:03d}")
        cases.append(
            {
                "case_id": f"case{i:03d}",
                "intent_id": f"intent{i if parent is None else parent:03d}",
                "dedup_digest": _hash(i + 3000),
                "source_ids": source_ids,
                "primary_stratum": strata[i],
                "tags": tags,
                "paraphrase_of": f"case{parent:03d}" if parent is not None else None,
                "previously_exposed": False,
            }
        )
    manifest = {
        "schema_version": SCHEMA,
        "manifest_id": "blind-holdout-metadata-01",
        "issued_at": "2026-10-10T01:00:00Z",
        "expires_at": FUTURE,
        "custodian_id": "custodian-external",
        "evaluator_id": "evaluator-external",
        "implementer_ids": ["implementer-01"],
        "reviewer_ids": ["reviewer-01", "reviewer-02"],
        "license_id": "licensed-eval",
        "license_scope": "EVALUATION_ONLY",
        "access_control": "EVALUATOR_ONLY",
        "retention_until": FUTURE,
        "consent_until": FUTURE,
        "sealed_dataset_id": "external-seal-v01",
        "sealed_dataset_sha256": _hash(9001),
        "sealed_storage_ref": "independent-escrow-alias-01",
        "candidate_commit": "a" * 40,
        "candidate_image_sha256": _hash(9002),
        "source_records": sources,
        "cases": cases,
        "access_ledger": [
            {"subject_id": "evaluator-external", "role": "evaluator",
             "granted": True, "accessed": False},
            {"subject_id": "implementer-01", "role": "implementer",
             "granted": False, "accessed": False},
        ],
        "approval_key_id": "external-key-01",
    }
    registry = TrustedCustodyRegistry(
        custodian_keys={
            ("custodian-external", "external-key-01"): SIGN_KEY
        },
        sealed_datasets={"external-seal-v01": _hash(9001)},
        sealed_storage_refs={
            "external-seal-v01": "independent-escrow-alias-01"
        },
        source_families={
            src["record_id"]: src["family_id"] for src in sources
        },
        source_documents={
            src["record_id"]: src["document_id"] for src in sources
        },
        source_origins={
            src["record_id"]: src["origin_id"] for src in sources
        },
        reviewed_cases={
            c["case_id"]: frozenset({"reviewer-01", "reviewer-02"})
            for c in cases
        },
        source_digests={
            src["record_id"]: src["source_sha256"] for src in sources
        },
        source_revisions={src["record_id"]: "rev01" for src in sources},
        reviewer_ids=frozenset({"reviewer-01", "reviewer-02"}),
        semantic_intents={
            c["case_id"]: c["intent_id"] for c in cases
        },
        forbidden_case_ids=frozenset({"old-dev-case"}),
        forbidden_intents=frozenset({"old-intent"}),
        forbidden_dedup_digests=frozenset({_hash(777777)}),
        approved_licenses=frozenset({"licensed-eval"}),
        independently_verified=True,  # TEST-ONLY, not real external verification
    )
    manifest["approval_signature"] = sign_fixture(manifest, SIGN_KEY)
    return manifest, registry


def _resign(m):
    m["approval_signature"] = sign_fixture(m, SIGN_KEY)


def test_synthetic_fixture_metadata_only_not_launch_authority():
    m, trusted = fixture_manifest()
    result = scan_manifest(m, trusted, now=NOW)
    assert result["verdict"] == "W4_D09_CORPUS_METADATA_ADMITTED"
    assert result["may_launch_test"] is False
    assert result["gates"]["legacy_523_product"]["status"] == "MISSING"
    assert result["gates"]["evaluation_launch"]["status"] == "NOT_VERIFIED"
    assert result["counts"]["independent_intents"] == 140
    assert result["counts"]["paraphrase_probes"] == 60


def test_actual_no_manifest_returns_not_admitted():
    result = scan_manifest(None, now=NOW)
    assert result["verdict"] == "W4_D09_CORPUS_NOT_ADMITTED"
    assert all(
        result["gates"][k]["status"] == "MISSING"
        for k in ("source_provenance", "sealed_custody", "case_population")
    )


def test_registry_absent_is_not_verified_not_admitted():
    m, _ = fixture_manifest()
    result = scan_manifest(m, now=NOW)
    assert result["verdict"] == "W4_D09_CORPUS_NOT_ADMITTED"
    assert result["gates"]["custodian"]["status"] == "NOT_VERIFIED"
    assert result["gates"]["source_provenance"]["status"] == "NOT_VERIFIED"


def test_registry_not_independently_verified_cannot_admit():
    m, registry = fixture_manifest()
    result = scan_manifest(
        m, replace(registry, independently_verified=False), now=NOW
    )
    assert result["verdict"] == "W4_D09_CORPUS_NOT_ADMITTED"


NEGATIVE_MUTATIONS = [
    "wrong_schema", "secret_answer_key", "secret_source_content",
    "missing_manifest_id", "future_issued", "expired_manifest",
    "missing_custodian", "custodian_is_evaluator", "bad_key_id",
    "forged_signature", "license_missing", "license_wrong_scope",
    "expired_retention", "expired_consent", "unauthorized_license",
    "sealed_id_missing", "sealed_digest_missing", "sealed_digest_forged",
    "sealed_storage_missing", "sealed_storage_forged", "case_review_not_verified",
    "registry_without_seal", "unapproved_source_sha",
    "unapproved_source_rev", "source_digest_invalid", "source_span_invalid",
    "source_acl_expired", "source_consent_expired", "source_retention_expired",
    "source_license_wrong", "duplicate_source_id", "missing_source",
    "few_source_records", "few_docs", "few_families", "fake_independent_family",
    "missing_access_ledger", "restrict_access", "implementer_access",
    "evaluator_not_granted", "evaluator_is_implementer",
    "reviewers_missing", "reviewer_is_implementer", "reviewer_unapproved",
    "cases_missing", "cases_short", "duplicate_case_id",
    "duplicate_exact_case", "case_id_historical",
    "intent_historical", "fingerprint_historical",
    "reused_development", "fake_semantic_intent", "missing_intent_attestation",
    "repeat_intent_without_paraphrase", "orphan_paraphrase",
    "bad_paraphrase_tag", "not_enough_intents", "missing_long_tail",
    "missing_negative_controls", "missing_supported_positives",
    "missing_provenance_positives", "too_many_graphology",
    "too_many_historical", "unknown_stratum", "insufficient_cross_doc",
    "source_unknown", "document_concentration", "family_concentration",
    "candidate_commit_missing", "candidate_image_missing",
    "case_contains_gold_answer", "case_contains_prompt",
    "case_field_not_approved", "access_record_with_secret",
]


@pytest.mark.parametrize("mutation", NEGATIVE_MUTATIONS)
def test_adversarial_fail_closed(mutation):
    m, registry = fixture_manifest()
    m = deepcopy(m)
    one = m["cases"][0]
    source = m["source_records"][0]
    if mutation == "wrong_schema":
        m["schema_version"] = "fake-v2"
    elif mutation == "secret_answer_key":
        m["answer_key"] = {"case000": "private-answer"}
    elif mutation == "secret_source_content":
        source["source_text"] = "forbidden-content"
    elif mutation == "missing_manifest_id":
        m.pop("manifest_id")
    elif mutation == "future_issued":
        m["issued_at"] = FUTURE
    elif mutation == "expired_manifest":
        m["expires_at"] = PAST
    elif mutation == "missing_custodian":
        m.pop("custodian_id")
    elif mutation == "custodian_is_evaluator":
        m["custodian_id"] = m["evaluator_id"]
    elif mutation == "bad_key_id":
        m["approval_key_id"] = "unknown-key"
    elif mutation == "forged_signature":
        m["approval_signature"] = "0" * 64
    elif mutation == "license_missing":
        m.pop("license_id")
    elif mutation == "license_wrong_scope":
        m["license_scope"] = "ANY_USE"
    elif mutation == "expired_retention":
        m["retention_until"] = PAST
    elif mutation == "expired_consent":
        m["consent_until"] = PAST
    elif mutation == "unauthorized_license":
        m["license_id"] = "other-license"
        for s in m["source_records"]:
            s["license_id"] = "other-license"
    elif mutation == "sealed_id_missing":
        m.pop("sealed_dataset_id")
    elif mutation == "sealed_digest_missing":
        m.pop("sealed_dataset_sha256")
    elif mutation == "sealed_digest_forged":
        m["sealed_dataset_sha256"] = _hash(1234)
    elif mutation == "sealed_storage_missing":
        m.pop("sealed_storage_ref")
    elif mutation == "sealed_storage_forged":
        m["sealed_storage_ref"] = "unknown-escrow-alias"
    elif mutation == "case_review_not_verified":
        registry = replace(registry, reviewed_cases={})
    elif mutation == "registry_without_seal":
        registry = replace(registry, sealed_datasets={})
    elif mutation == "unapproved_source_sha":
        source["source_sha256"] = _hash(8888)
    elif mutation == "unapproved_source_rev":
        source["revision"] = "rev99"
    elif mutation == "source_digest_invalid":
        source["source_sha256"] = "notsha"
    elif mutation == "source_span_invalid":
        source["span_index_sha256"] = "notsha"
    elif mutation == "source_acl_expired":
        source["acl_until"] = PAST
    elif mutation == "source_consent_expired":
        source["consent_until"] = PAST
    elif mutation == "source_retention_expired":
        source["retention_until"] = PAST
    elif mutation == "source_license_wrong":
        source["license_id"] = "license-elsewhere"
    elif mutation == "duplicate_source_id":
        m["source_records"][1]["record_id"] = source["record_id"]
    elif mutation == "missing_source":
        m.pop("source_records")
    elif mutation == "few_source_records":
        m["source_records"] = m["source_records"][:99]
    elif mutation == "few_docs":
        for s in m["source_records"]:
            s["document_id"] = f"doc{int(s['document_id'][3:]) % 19:02d}"
    elif mutation == "few_families":
        for s in m["source_records"]:
            s["family_id"] = "family0"
    elif mutation == "fake_independent_family":
        m["source_records"][1]["origin_id"] = "origin0"
        m["source_records"][1]["family_id"] = "family1"
    elif mutation == "missing_access_ledger":
        m["access_ledger"] = []
    elif mutation == "restrict_access":
        m["access_control"] = "DENIED"
    elif mutation == "implementer_access":
        m["access_ledger"][1]["accessed"] = True
    elif mutation == "evaluator_not_granted":
        m["access_ledger"][0]["granted"] = False
    elif mutation == "evaluator_is_implementer":
        m["implementer_ids"].append("evaluator-external")
    elif mutation == "reviewers_missing":
        m["reviewer_ids"] = ["reviewer-01"]
    elif mutation == "reviewer_is_implementer":
        m["reviewer_ids"][0] = "implementer-01"
    elif mutation == "reviewer_unapproved":
        m["reviewer_ids"][0] = "reviewer-03"
    elif mutation == "cases_missing":
        m.pop("cases")
    elif mutation == "cases_short":
        m["cases"].pop()
    elif mutation == "duplicate_case_id":
        m["cases"][1]["case_id"] = one["case_id"]
    elif mutation == "duplicate_exact_case":
        m["cases"][1]["dedup_digest"] = one["dedup_digest"]
    elif mutation == "case_id_historical":
        one["case_id"] = "old-dev-case"
    elif mutation == "intent_historical":
        one["intent_id"] = "old-intent"
    elif mutation == "fingerprint_historical":
        one["dedup_digest"] = _hash(777777)
    elif mutation == "reused_development":
        one["previously_exposed"] = True
    elif mutation == "fake_semantic_intent":
        one["intent_id"] = "invented-unreviewed"
    elif mutation == "missing_intent_attestation":
        changed = dict(registry.semantic_intents)
        changed.pop(one["case_id"])
        registry = replace(registry, semantic_intents=changed)
    elif mutation == "repeat_intent_without_paraphrase":
        m["cases"][1]["intent_id"] = one["intent_id"]
    elif mutation == "orphan_paraphrase":
        one["paraphrase_of"] = "case999"
    elif mutation == "bad_paraphrase_tag":
        m["cases"][140]["tags"].remove("PARAPHRASE")
    elif mutation == "not_enough_intents":
        for c in m["cases"][100:140]:
            c["intent_id"] = one["intent_id"]
    elif mutation == "missing_long_tail":
        for c in m["cases"]:
            c["tags"] = [t for t in c["tags"] if t != "LONG_TAIL"]
    elif mutation == "missing_negative_controls":
        for c in m["cases"]:
            c["tags"] = [t for t in c["tags"] if t != "MATCHED_NEGATIVE"]
    elif mutation == "missing_supported_positives":
        for c in m["cases"]:
            c["tags"] = [t for t in c["tags"] if t != "SUPPORTED_POSITIVE"]
    elif mutation == "missing_provenance_positives":
        for c in m["cases"]:
            c["tags"] = [t for t in c["tags"] if t != "PROVENANCE_POSITIVE"]
    elif mutation == "too_many_graphology":
        for c in m["cases"][:31]:
            if "GRAPHOLOGY" not in c["tags"]:
                c["tags"].append("GRAPHOLOGY")
    elif mutation == "too_many_historical":
        for c in m["cases"][:41]:
            if "HISTORICAL_TOPIC" not in c["tags"]:
                c["tags"].append("HISTORICAL_TOPIC")
    elif mutation == "unknown_stratum":
        one["primary_stratum"] = "UNKNOWN"
    elif mutation == "insufficient_cross_doc":
        next(
            c for c in m["cases"] if c["primary_stratum"] == "CROSS_DOCUMENT"
        )["source_ids"] = ["src000"]
    elif mutation == "source_unknown":
        one["source_ids"] = ["missing-source-id"]
    elif mutation == "document_concentration" or mutation == "family_concentration":
        for c in m["cases"]:
            c["source_ids"] = ["src000"]
    elif mutation == "candidate_commit_missing":
        m["candidate_commit"] = ""
    elif mutation == "candidate_image_missing":
        m["candidate_image_sha256"] = ""
    elif mutation == "case_contains_gold_answer":
        one["gold_answer"] = "secret"
    elif mutation == "case_contains_prompt":
        one["prompt"] = "hidden"
    elif mutation == "case_field_not_approved":
        one["label"] = "ANSWERABLE"
    elif mutation == "access_record_with_secret":
        m["access_ledger"][0]["token"] = "forbidden"
    else:
        raise AssertionError(mutation)
    if mutation != "forged_signature":
        _resign(m)
    result = scan_manifest(m, registry, now=NOW)
    assert result["verdict"] == "W4_D09_CORPUS_NOT_ADMITTED", mutation
    assert result["may_launch_test"] is False
    assert any(
        result["gates"][gate]["status"] != "ELIGIBLE"
        for gate in (
            "schema", "custodian", "rights", "sealed_custody",
            "source_provenance", "access_separation", "reviewers",
            "case_population", "intent_dedup", "source_diversity",
            "adversarial_coverage", "candidate_freeze",
        )
    ), mutation


def test_missing_all_does_not_throw_or_admit():
    result = scan_manifest({}, now=NOW)
    assert result["verdict"] == "W4_D09_CORPUS_NOT_ADMITTED"


def test_untrusted_non_mapping_does_not_admit():
    assert scan_manifest("malformed", now=NOW)["verdict"] == (
        "W4_D09_CORPUS_NOT_ADMITTED"
    )


def test_utc_required():
    with pytest.raises(ValueError, match="timezone"):
        scan_manifest(None, now=datetime(2026, 10, 10))


def test_signature_canonical_stable_order():
    m, _ = fixture_manifest()
    assert sign_fixture(dict(reversed(list(m.items()))), SIGN_KEY) == (
        m["approval_signature"]
    )


def test_historical_523_synthetic_replay_not_new_questions():
    rows = [
        {
            "question": f"Graphology fact {i % 9}",
            "execution_mode": "live_answer_stream",
            "expectation": "verified_cited_answer",
        }
        for i in range(237)
    ]
    rows += [
        {
            "question": f"Safe fact {i % 11}",
            "execution_mode": "live_answer_stream",
            "expectation": (
                "safe_abstention" if i < 52 else "rejected_before_provider"
            ),
        }
        for i in range(104)
    ]
    rows += [
        {
            "question": f"Safe fact {i % 11}",
            "execution_mode": "contract_replay",
            "expectation": (
                "budget_terminal" if i < 26 else (
                    "m26_invariant" if i < 52 else "governance_contract"
                )
            ),
        }
        for i in range(182)
    ]
    audit = audit_historical_rows(rows)
    assert audit["total_rows"] == 523
    assert audit["execution_mode"]["live_answer_stream"] == 341
    assert audit["execution_mode"]["contract_replay"] == 182
    assert audit["distinct_normalized_questions"] == 20
    assert audit["distinct_cited_answer_questions"] == 9
    assert not audit["semantic_intent_independence_verified"]


def test_historical_normalization_and_bad_mode():
    audit = audit_historical_rows([
        {"question": "Cafe\u0301  QUESTION", "execution_mode": "contract_replay",
         "expectation": "budget_terminal"},
        {"question": "CAFÉ question", "execution_mode": "live_answer_stream",
         "expectation": "verified_cited_answer"},
        {"question": "not-valid", "execution_mode": "bogus",
         "expectation": "verified_cited_answer"},
    ])
    assert audit["distinct_normalized_questions"] == 2
    assert audit["invalid_rows"] == 1


def test_actual_hidden_content_never_appears_in_result():
    m, trusted = fixture_manifest()
    m["answer_key"] = {"case000": "NEVER-PRINT-THIS-SECRET"}
    _resign(m)
    result = scan_manifest(m, trusted, now=NOW)
    assert "NEVER-PRINT-THIS-SECRET" not in str(result)
    assert result["gates"]["schema"]["status"] == "NOT_ELIGIBLE"


def test_frozen_gates_do_not_confuse_legacy_with_blind_population():
    m, trusted = fixture_manifest()
    r = scan_manifest(m, trusted, now=NOW)
    statuses = Counter(v["status"] for v in r["gates"].values())
    assert statuses["ELIGIBLE"] == 12
    assert statuses["MISSING"] == 1
    assert statuses["NOT_VERIFIED"] == 1
