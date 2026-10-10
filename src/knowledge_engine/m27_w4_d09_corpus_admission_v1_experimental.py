"""Metadata-only, fail-closed AR09 Phase B corpus admission (experimental).

No protected text, hidden cases, answer keys, network access, dataset reads, or test
execution. Only separately supplied metadata and independently provisioned custody
verification may establish eligibility. Local fixtures are NOT external authority.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SCHEMA = "m27-w4-d09-corpus-admission-v1"
STATUS = frozenset(
    {"ELIGIBLE", "NOT_ELIGIBLE", "MISSING", "ACCESS_RESTRICTED", "NOT_VERIFIED"}
)
CORPUS_GATES = (
    "schema", "custodian", "rights", "source_provenance", "sealed_custody",
    "access_separation", "reviewers", "case_population", "intent_dedup",
    "source_diversity", "adversarial_coverage", "candidate_freeze",
)
ALL_GATES = CORPUS_GATES + ("legacy_523_product", "evaluation_launch")
STRATA = {
    "GROUNDED": 32, "PROVENANCE": 26, "CROSS_DOCUMENT": 28,
    "GRAPH": 18, "FRESHNESS": 20, "CONFLICT": 18,
    "INJECTION": 16, "PRIVACY": 14, "ABSTENTION": 28,
}
TOP_KEYS = frozenset({
    "schema_version", "manifest_id", "issued_at", "expires_at", "custodian_id",
    "evaluator_id", "implementer_ids", "reviewer_ids", "license_id",
    "license_scope", "access_control", "retention_until", "consent_until",
    "sealed_dataset_id", "sealed_dataset_sha256", "sealed_storage_ref",
    "candidate_commit",
    "candidate_image_sha256", "source_records", "cases", "access_ledger",
    "approval_key_id", "approval_signature",
})
SOURCE_KEYS = frozenset({
    "record_id", "document_id", "family_id", "origin_id", "revision",
    "source_sha256", "span_index_sha256", "license_id", "acl_until",
    "retention_until", "consent_until", "published_at", "issued_at",
})
CASE_KEYS = frozenset({
    "case_id", "intent_id", "source_ids", "primary_stratum", "tags",
    "dedup_digest", "paraphrase_of", "previously_exposed",
})
ACCESS_KEYS = frozenset({"subject_id", "role", "granted", "accessed"})
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class TrustedCustodyRegistry:
    """Out-of-manifest custody input, provisioned by an independent authority.

    This object does not attest its own authenticity. Integrators must validate the
    provenance/issuer of this registry out of band. Never ship test HMAC keys as
    real custodian credentials.
    """
    custodian_keys: Mapping[tuple[str, str], bytes] = field(default_factory=dict)
    sealed_datasets: Mapping[str, str] = field(default_factory=dict)
    sealed_storage_refs: Mapping[str, str] = field(default_factory=dict)
    source_digests: Mapping[str, str] = field(default_factory=dict)
    source_families: Mapping[str, str] = field(default_factory=dict)
    source_documents: Mapping[str, str] = field(default_factory=dict)
    source_origins: Mapping[str, str] = field(default_factory=dict)
    reviewed_cases: Mapping[str, frozenset[str]] = field(default_factory=dict)
    source_revisions: Mapping[str, str] = field(default_factory=dict)
    reviewer_ids: frozenset[str] = frozenset()
    semantic_intents: Mapping[str, str] = field(default_factory=dict)
    forbidden_case_ids: frozenset[str] = frozenset()
    forbidden_intents: frozenset[str] = frozenset()
    forbidden_dedup_digests: frozenset[str] = frozenset()
    approved_licenses: frozenset[str] = frozenset()
    independently_verified: bool = False


def _canonical(obj: Mapping[str, Any]) -> bytes:
    data = {k: v for k, v in obj.items() if k != "approval_signature"}
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sign_fixture(manifest: Mapping[str, Any], key: bytes) -> str:
    """ONLY a deterministic test aid, not an externally trusted signature."""
    return hmac.new(key, _canonical(manifest), hashlib.sha256).hexdigest()


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else None
    except ValueError:
        return None


def _id(value: object) -> bool:
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _islist(value: object) -> bool:
    return isinstance(value, list)


def _keys_exact(item: object, allowed: frozenset[str]) -> bool:
    return isinstance(item, dict) and not (item.keys() - allowed)


def _status(gates: dict[str, dict[str, Any]], gate: str, code: str,
            reason: str) -> None:
    priority = {
        "ELIGIBLE": 0, "NOT_VERIFIED": 1, "MISSING": 2,
        "ACCESS_RESTRICTED": 3, "NOT_ELIGIBLE": 4,
    }
    previous = gates[gate]["status"]
    if priority[code] >= priority[previous]:
        gates[gate]["status"] = code
    if reason not in gates[gate]["reasons"]:
        gates[gate]["reasons"].append(reason)


def _needed(gates: dict[str, dict[str, Any]], gate: str,
            obj: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = obj.get(key)
        if value is None or value == "" or value == []:
            _status(gates, gate, "MISSING", "missing_" + key)


def _active(gates: dict[str, dict[str, Any]], gate: str,
            record: Mapping[str, Any], key: str, now: datetime) -> None:
    raw = record.get(key)
    if raw is None or raw == "":
        _status(gates, gate, "MISSING", "missing_" + key)
    else:
        parsed = _date(raw)
        if parsed is None or parsed <= now:
            _status(gates, gate, "NOT_ELIGIBLE", "expired_or_invalid_" + key)


def scan_manifest(manifest: Mapping[str, Any] | None,
                  registry: TrustedCustodyRegistry | None = None,
                  *, now: datetime | None = None) -> dict[str, Any]:
    """Return bounded aggregate status only; never echo case/source identifiers.

    No test is launched or raw corpus bytes loaded. The sealed dataset must stay
    outside the shared repo. The independent evaluator alone owns registry keys.
    """
    gates = {name: {"status": "ELIGIBLE", "reasons": []} for name in ALL_GATES}
    _status(gates, "legacy_523_product", "MISSING",
            "real_candidate_523_denominator_and_scoring_not_supplied")
    _status(gates, "evaluation_launch", "NOT_VERIFIED",
            "E09B_separate_authorization_and_actual_run_required")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now_must_be_timezone_aware")
    current = current.astimezone(UTC)

    def finish(counts: dict[str, int] | None = None) -> dict[str, Any]:
        admitted = all(gates[n]["status"] == "ELIGIBLE" for n in CORPUS_GATES)
        return {
            "schema_version": SCHEMA,
            "verdict": (
                "W4_D09_CORPUS_METADATA_ADMITTED" if admitted
                else "W4_D09_CORPUS_NOT_ADMITTED"
            ),
            "may_launch_test": False,
            "gates": gates,
            "counts": counts or {},
        }

    if manifest is None:
        for name in CORPUS_GATES:
            _status(gates, name, "MISSING", "no_independent_corpus_manifest")
        return finish()
    if not isinstance(manifest, Mapping):
        _status(gates, "schema", "NOT_ELIGIBLE", "manifest_not_mapping")
        for name in CORPUS_GATES[1:]:
            _status(gates, name, "NOT_VERIFIED", "invalid_manifest")
        return finish()
    m = dict(manifest)
    if set(m) - TOP_KEYS or m.get("schema_version") != SCHEMA:
        _status(gates, "schema", "NOT_ELIGIBLE",
                "unknown_fields_or_wrong_schema_version")
    _needed(gates, "schema", m, ("manifest_id", "issued_at", "expires_at"))
    if not _id(m.get("manifest_id")):
        _status(gates, "schema", "NOT_ELIGIBLE", "invalid_manifest_identifier")
    if _date(m.get("issued_at")) is None or (
        _date(m.get("issued_at")) is not None
        and _date(m["issued_at"]) > current
    ):
        _status(gates, "schema", "NOT_ELIGIBLE", "invalid_or_future_issue_date")
    _active(gates, "schema", m, "expires_at", current)

    _needed(gates, "custodian", m, (
        "custodian_id", "evaluator_id", "approval_signature", "approval_key_id",
    ))
    if m.get("custodian_id") == m.get("evaluator_id"):
        _status(gates, "custodian", "NOT_ELIGIBLE",
                "independent_custodian_required")
    for name in ("custodian_id", "evaluator_id", "approval_key_id"):
        if not _id(m.get(name)):
            _status(gates, "custodian", "NOT_ELIGIBLE", "invalid_" + name)
    if registry is None or not registry.independently_verified:
        _status(gates, "custodian", "NOT_VERIFIED",
                "independently_provisioned_registry_not_verified")
    else:
        key = registry.custodian_keys.get(
            (m.get("custodian_id"), m.get("approval_key_id"))
        )
        if not isinstance(key, bytes) or len(key) < 16:
            _status(gates, "custodian", "NOT_VERIFIED",
                    "trusted_issuer_key_unavailable")
        else:
            try:
                expected = sign_fixture(m, key)
                valid = _digest(m.get("approval_signature")) and hmac.compare_digest(
                    expected, m["approval_signature"]
                )
            except (TypeError, ValueError):
                valid = False
            if not valid:
                _status(gates, "custodian", "NOT_ELIGIBLE",
                        "custodian_signature_mismatch")
    _needed(gates, "rights", m, ("license_id", "license_scope",
                                 "retention_until", "consent_until"))
    if m.get("license_scope") != "EVALUATION_ONLY":
        _status(gates, "rights", "NOT_ELIGIBLE", "unapproved_license_scope")
    for key in ("retention_until", "consent_until"):
        _active(gates, "rights", m, key, current)
    if registry is None or not registry.independently_verified:
        _status(gates, "rights", "NOT_VERIFIED", "license_authority_unverified")
    elif m.get("license_id") not in registry.approved_licenses:
        _status(gates, "rights", "NOT_ELIGIBLE", "license_not_approved")

    _needed(gates, "sealed_custody", m,
            ("sealed_dataset_id", "sealed_dataset_sha256",
             "sealed_storage_ref"))
    if not _id(m.get("sealed_dataset_id")) or not _digest(
        m.get("sealed_dataset_sha256")
    ):
        _status(gates, "sealed_custody", "NOT_ELIGIBLE",
                "invalid_seal_identifier_or_digest")
    if not _id(m.get("sealed_storage_ref")):
        _status(gates, "sealed_custody", "MISSING",
                "secure_external_storage_reference_missing")
    if registry is None or not registry.independently_verified:
        _status(gates, "sealed_custody", "NOT_VERIFIED",
                "external_sealed_dataset_not_verified")
    elif registry.sealed_datasets.get(m.get("sealed_dataset_id")) is None:
        _status(gates, "sealed_custody", "NOT_VERIFIED",
                "externally_sealed_dataset_not_registered")
    elif registry.sealed_datasets[m["sealed_dataset_id"]] != m.get(
        "sealed_dataset_sha256"
    ):
        _status(gates, "sealed_custody", "NOT_ELIGIBLE",
                "sealed_dataset_checksum_mismatch")
    if registry is not None and registry.independently_verified and (
        registry.sealed_storage_refs.get(m.get("sealed_dataset_id"))
        != m.get("sealed_storage_ref")
    ):
        _status(gates, "sealed_custody", "NOT_VERIFIED",
                "independent_secure_storage_reference_not_verified")

    if m.get("access_control") != "EVALUATOR_ONLY":
        _status(gates, "access_separation", "ACCESS_RESTRICTED",
                "no_authorized_evaluator_only_metadata_acl")
    implementers = m.get("implementer_ids")
    if not _islist(implementers) or any(not _id(x) for x in implementers):
        _status(gates, "access_separation", "MISSING",
                "missing_or_invalid_implementer_roster")
        implementers = []
    if m.get("evaluator_id") in implementers or m.get("custodian_id") in implementers:
        _status(gates, "access_separation", "NOT_ELIGIBLE",
                "custodian_or_evaluator_is_implementer")
    access = m.get("access_ledger")
    if not _islist(access) or not access:
        _status(gates, "access_separation", "ACCESS_RESTRICTED",
                "independent_access_audit_missing")
        access = []
    evaluator_grant = False
    for entry in access:
        if not _keys_exact(entry, ACCESS_KEYS):
            _status(gates, "access_separation", "NOT_ELIGIBLE",
                    "access_ledger_contains_unapproved_fields")
            continue
        actor = entry.get("subject_id")
        if not _id(actor) or not isinstance(entry.get("granted"), bool) or not isinstance(
            entry.get("accessed"), bool
        ):
            _status(gates, "access_separation", "NOT_ELIGIBLE",
                    "invalid_access_ledger_record")
        if actor in implementers and (entry.get("granted") or entry.get("accessed")):
            _status(gates, "access_separation", "NOT_ELIGIBLE",
                    "evaluator_to_implementer_exposure")
        if actor == m.get("evaluator_id") and entry.get("granted"):
            evaluator_grant = True
    if not evaluator_grant:
        _status(gates, "access_separation", "ACCESS_RESTRICTED",
                "evaluator_access_not_approved")

    reviewers = m.get("reviewer_ids")
    if not _islist(reviewers) or len(set(map(str, reviewers))) < 2:
        _status(gates, "reviewers", "MISSING",
                "two_independent_reviewers_required")
        reviewers = []
    for reviewer in reviewers:
        if not _id(reviewer) or reviewer in implementers or reviewer in (
            m.get("custodian_id"), m.get("evaluator_id"),
        ):
            _status(gates, "reviewers", "NOT_ELIGIBLE",
                    "reviewer_independence_invalid")
        if registry is None or not registry.independently_verified:
            _status(gates, "reviewers", "NOT_VERIFIED",
                    "reviewer_authority_unverified")
        elif reviewer not in registry.reviewer_ids:
            _status(gates, "reviewers", "NOT_ELIGIBLE",
                    "reviewer_not_independently_authorized")

    frozen_commit, image_digest = m.get("candidate_commit"), m.get(
        "candidate_image_sha256"
    )
    if not isinstance(frozen_commit, str) or HEX40.fullmatch(frozen_commit) is None:
        _status(gates, "candidate_freeze", "MISSING",
                "immutable_full_candidate_commit_unverified")
    if not _digest(image_digest):
        _status(gates, "candidate_freeze", "MISSING",
                "immutable_candidate_image_digest_unverified")

    sources = m.get("source_records")
    cases = m.get("cases")
    if not _islist(sources) or not sources:
        _status(gates, "source_provenance", "MISSING", "no_source_metadata")
        sources = []
    if not _islist(cases) or not cases:
        _status(gates, "case_population", "MISSING", "no_case_metadata")
        cases = []
    source_map: dict[str, Mapping[str, Any]] = {}
    families: set[str] = set()
    docs: set[str] = set()
    origin_family: dict[str, str] = {}
    for src in sources:
        if not _keys_exact(src, SOURCE_KEYS):
            _status(gates, "source_provenance", "NOT_ELIGIBLE",
                    "unapproved_source_metadata_fields")
            continue
        req = ("record_id", "document_id", "family_id", "origin_id", "revision",
               "source_sha256", "span_index_sha256", "license_id", "published_at",
               "issued_at")
        _needed(gates, "source_provenance", src, req)
        for key in ("record_id", "document_id", "family_id", "origin_id", "revision"):
            if not _id(src.get(key)):
                _status(gates, "source_provenance", "NOT_ELIGIBLE",
                        "invalid_source_opaque_identifier")
        for key in ("source_sha256", "span_index_sha256"):
            if not _digest(src.get(key)):
                _status(gates, "source_provenance", "NOT_ELIGIBLE",
                        "invalid_source_checksum")
        if _date(src.get("issued_at")) is None or _date(
            src.get("published_at")
        ) is None:
            _status(gates, "source_provenance", "NOT_ELIGIBLE",
                    "undated_source_revision")
        for key in ("acl_until", "retention_until", "consent_until"):
            _active(gates, "rights", src, key, current)
        if src.get("license_id") != m.get("license_id"):
            _status(gates, "rights", "NOT_ELIGIBLE",
                    "source_license_outside_manifest_scope")
        rid = src.get("record_id")
        if rid in source_map:
            _status(gates, "source_provenance", "NOT_ELIGIBLE",
                    "duplicate_source_record_id")
        elif _id(rid):
            source_map[rid] = src
        fam, origin = src.get("family_id"), src.get("origin_id")
        if _id(fam):
            families.add(fam)
        if _id(src.get("document_id")):
            docs.add(src["document_id"])
        if _id(origin):
            if origin in origin_family and origin_family[origin] != fam:
                _status(gates, "source_diversity", "NOT_ELIGIBLE",
                        "same_origin_claims_independent_families")
            origin_family[origin] = fam
        if registry is None or not registry.independently_verified:
            _status(gates, "source_provenance", "NOT_VERIFIED",
                    "independent_source_revision_unverified")
        elif (registry.source_digests.get(rid) != src.get("source_sha256")
              or registry.source_revisions.get(rid) != src.get("revision")
              or registry.source_families.get(rid) != src.get("family_id")
              or registry.source_origins.get(rid) != src.get("origin_id")
              or registry.source_documents.get(rid) != src.get("document_id")):
            _status(gates, "source_provenance", "NOT_ELIGIBLE",
                    "independent_source_digest_revision_or_origin_mismatch")
    if len(source_map) < 100 or len(docs) < 20 or len(families) < 5 or (
        len(origin_family) < 5
    ):
        _status(gates, "source_diversity", "NOT_ELIGIBLE",
                "below_100_sources_20_docs_5_independent_families")

    if len(cases) != 200:
        _status(gates, "case_population", "NOT_ELIGIBLE",
                "not_exactly_200_distinct_unseen_cases")
    seen_ids: set[str] = set()
    seen_dedup: set[str] = set()
    intent_first: dict[str, str] = {}
    family_cases: Counter[str] = Counter()
    doc_cases: Counter[str] = Counter()
    used_sources: set[str] = set()
    stratum_cases: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    for case in cases:
        if not _keys_exact(case, CASE_KEYS):
            _status(gates, "schema", "NOT_ELIGIBLE",
                    "unapproved_case_field_or_hidden_label")
            continue
        cid, intent, dedup = (case.get("case_id"), case.get("intent_id"),
                               case.get("dedup_digest"))
        if not _id(cid) or not _id(intent) or not _digest(dedup):
            _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                    "invalid_case_intent_or_keyed_dedup")
            continue
        if cid in seen_ids or dedup in seen_dedup:
            _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                    "duplicate_case_or_exact_normalized_question")
        if _id(cid):
            seen_ids.add(cid)
        if _digest(dedup):
            seen_dedup.add(dedup)
        if case.get("previously_exposed") is not False:
            _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                    "previously_exposed_or_unverified_reuse")
        if registry is None or not registry.independently_verified:
            _status(gates, "intent_dedup", "NOT_VERIFIED",
                    "independent_semantic_dedup_unverified")
        else:
            if (cid in registry.forbidden_case_ids
                or intent in registry.forbidden_intents
                or dedup in registry.forbidden_dedup_digests):
                _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                        "historical_or_development_contamination")
            if cid not in registry.semantic_intents:
                _status(gates, "intent_dedup", "NOT_VERIFIED",
                        "no_independent_semantic_intent_attestation")
            elif registry.semantic_intents[cid] != intent:
                _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                        "forged_or_misclustered_semantic_intent")
            if cid not in registry.reviewed_cases:
                _status(gates, "reviewers", "NOT_VERIFIED",
                        "case_level_dual_review_attestation_missing")
            elif len(registry.reviewed_cases[cid] & set(reviewers)) < 2:
                _status(gates, "reviewers", "NOT_ELIGIBLE",
                        "case_lacks_two_independent_reviews")
        parent = case.get("paraphrase_of")
        if intent in intent_first:
            if parent != intent_first[intent]:
                _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                        "repeated_semantic_intent_without_valid_paraphrase")
        elif parent is not None:
            _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                    "orphan_or_forward_paraphrase")
        else:
            intent_first[intent] = cid
        case_tags = case.get("tags")
        if not _islist(case_tags) or any(t not in (
            "LONG_TAIL", "PARAPHRASE", "MATCHED_NEGATIVE",
            "SUPPORTED_POSITIVE", "PROVENANCE_POSITIVE", "GRAPHOLOGY",
            "HISTORICAL_TOPIC",
        ) for t in case_tags):
            _status(gates, "adversarial_coverage", "NOT_ELIGIBLE",
                    "unknown_or_missing_coverage_tags")
            case_tags = []
        if bool(parent) != ("PARAPHRASE" in case_tags):
            _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                    "paraphrase_tag_and_parent_inconsistent")
        tags.update(set(case_tags))
        primary = case.get("primary_stratum")
        if primary not in STRATA:
            _status(gates, "case_population", "NOT_ELIGIBLE",
                    "unknown_primary_stratum")
        else:
            stratum_cases[primary] += 1
        ids = case.get("source_ids")
        if not _islist(ids) or not ids or len(ids) != len(set(map(str, ids))):
            _status(gates, "source_diversity", "NOT_ELIGIBLE",
                    "invalid_case_source_references")
            ids = []
        used = [source_map[s] for s in ids if isinstance(s, str) and s in source_map]
        used_sources.update(s["record_id"] for s in used)
        if len(used) != len(ids):
            _status(gates, "source_diversity", "NOT_ELIGIBLE",
                    "source_reference_not_in_verified_manifest")
        used_docs = {src["document_id"] for src in used}
        if primary == "CROSS_DOCUMENT" and len(used_docs) < 2:
            _status(gates, "source_diversity", "NOT_ELIGIBLE",
                    "cross_document_case_lacks_two_distinct_docs")
        for doc in used_docs:
            doc_cases[doc] += 1
        for family in {src["family_id"] for src in used}:
            family_cases[family] += 1
    if len(used_sources) < 100:
        _status(gates, "source_diversity", "NOT_ELIGIBLE",
                "fewer_than_100_sources_actually_used_by_cases")
    if len(intent_first) < 140:
        _status(gates, "intent_dedup", "NOT_ELIGIBLE",
                "below_140_independent_semantic_intents")
    if len(seen_ids) != len(cases):
        _status(gates, "case_population", "NOT_ELIGIBLE",
                "non_unique_opaque_case_ids")
    if any(n > 20 for n in doc_cases.values()) or any(
        n > 40 for n in family_cases.values()
    ):
        _status(gates, "source_diversity", "NOT_ELIGIBLE",
                "source_document_or_family_concentration_exceeded")
    if stratum_cases != STRATA:
        _status(gates, "case_population", "NOT_ELIGIBLE",
                "primary_strata_do_not_match_preregistered_200")
    minimum = {
        "LONG_TAIL": 40, "PARAPHRASE": 60,
        "MATCHED_NEGATIVE": 30, "SUPPORTED_POSITIVE": 20,
        "PROVENANCE_POSITIVE": 20,
    }
    if any(tags[tag] < count for tag, count in minimum.items()):
        _status(gates, "adversarial_coverage", "NOT_ELIGIBLE",
                "required_longtail_paraphrase_positive_negative_coverage_missing")
    if tags["GRAPHOLOGY"] > 30 or tags["HISTORICAL_TOPIC"] > 40:
        _status(gates, "adversarial_coverage", "NOT_ELIGIBLE",
                "topic_concentration_exceeded")
    counts = {
        "total_cases": len(cases), "distinct_case_ids": len(seen_ids),
        "independent_intents": len(intent_first),
        "source_records": len(source_map), "documents": len(docs),
        "independent_families": len(origin_family),
        "paraphrase_probes": tags["PARAPHRASE"],
        "long_tail_cases": tags["LONG_TAIL"],
    }
    return finish(counts)


def audit_historical_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Recompute approved historical row metadata without emitting questions.

    Normalized strings only yield aggregate unique counts; semantic diversity
    cannot be proven from a lexical dedup. Not a product-quality claim.
    """
    mode = Counter()
    expectations = Counter()
    seen: set[str] = set()
    cited: set[str] = set()
    invalid = 0
    live_expectations = {
        "verified_cited_answer", "safe_abstention", "rejected_before_provider"
    }
    for item in rows:
        if not isinstance(item, Mapping):
            invalid += 1
            continue
        value = item.get("question")
        if not isinstance(value, str) or not value.strip():
            invalid += 1
            continue
        normalized = unicodedata.normalize("NFKC", value)
        normalized = " ".join(normalized.casefold().split())
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).digest()
        seen.add(fingerprint.hex())
        if item.get("expectation") == "verified_cited_answer":
            cited.add(fingerprint.hex())
        m, e = item.get("execution_mode"), item.get("expectation")
        if m not in ("live_answer_stream", "contract_replay"):
            invalid += 1
        if (m == "live_answer_stream" and e not in live_expectations
            or m == "contract_replay" and e in live_expectations):
            invalid += 1
        mode[str(m)] += 1
        expectations[str(e)] += 1
    return {
        "total_rows": len(rows), "execution_mode": dict(sorted(mode.items())),
        "expectations": dict(sorted(expectations.items())),
        "distinct_normalized_questions": len(seen),
        "distinct_cited_answer_questions": len(cited),
        "invalid_rows": invalid,
        "row_count_is_unseen_question_count": False,
        "semantic_intent_independence_verified": False,
    }
