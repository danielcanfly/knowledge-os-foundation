from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import m26_pa7_arbitrary_query_runtime as legacy
from .errors import IntegrityError
from .m26_production_answer_bundle import ProductionAnswerBundle
from .m26_real_corpus_binding import canonical_sha256

PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA = "m27-production-evidence-authority/v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_BINDING_FIELDS = (
    "evidence_id",
    "evidence_type",
    "locator_id",
    "release_id",
    "artifact_key",
    "artifact_sha256",
    "concept_id",
    "section_id",
    "source_id",
    "source_identity",
    "passage_text_sha256",
    "provenance_record_sha256",
)


class ProductionEvidenceBridgeError(IntegrityError):
    """Fail-closed production-equivalent evidence authority error."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ProductionEvidenceAuthority:
    """Pinned read-only authority for a formal M26 production-equivalent bundle."""

    bundle: ProductionAnswerBundle
    release_id: str
    manifest_sha256: str
    allowed_audiences: frozenset[str]
    evidence_binding_sha256_by_id: Mapping[str, str]
    schema_version: str = PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA
    read_only: bool = True


def production_evidence_binding_sha256(item: Mapping[str, Any]) -> str:
    """Digest the immutable M26 identity fields, including its runtime locator."""

    binding = {field: str(item.get(field, "")) for field in _BINDING_FIELDS}
    return canonical_sha256(binding)


def validate_production_authority(authority: ProductionEvidenceAuthority) -> None:
    if authority.schema_version != PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA:
        raise ProductionEvidenceBridgeError(
            "AUTHORITY_SCHEMA_MISMATCH",
            "unsupported authority schema",
        )
    if authority.read_only is not True:
        raise ProductionEvidenceBridgeError(
            "AUTHORITY_NOT_READ_ONLY",
            "production evidence authority must be read-only",
        )
    if not authority.allowed_audiences:
        raise ProductionEvidenceBridgeError(
            "ACL_AUTHORITY_MISSING",
            "allowed audiences are not pinned",
        )
    if not authority.allowed_audiences <= frozenset({"public", "internal"}):
        raise ProductionEvidenceBridgeError(
            "ACL_AUTHORITY_INVALID",
            "unknown audience in authority",
        )
    if not authority.evidence_binding_sha256_by_id:
        raise ProductionEvidenceBridgeError(
            "EVIDENCE_BINDINGS_MISSING",
            "formal M26 evidence bindings are not pinned",
        )
    for evidence_id, digest in authority.evidence_binding_sha256_by_id.items():
        if not str(evidence_id).startswith("m26pa7ev_"):
            raise ProductionEvidenceBridgeError(
                "EVIDENCE_BINDING_ID_INVALID",
                "formal evidence binding is not an M26 PA7 identity",
            )
        _require_hex64(str(digest), "EVIDENCE_BINDING_DIGEST_INVALID")

    bundle = authority.bundle
    if authority.release_id != bundle.release_id:
        raise ProductionEvidenceBridgeError(
            "RELEASE_ID_MISMATCH",
            "pinned release does not match bundle",
        )
    if authority.manifest_sha256 != bundle.manifest_sha256:
        raise ProductionEvidenceBridgeError(
            "MANIFEST_DIGEST_MISMATCH",
            "pinned manifest digest does not match bundle",
        )
    _require_hex64(authority.manifest_sha256, "MANIFEST_DIGEST_INVALID")

    accepted_release_id = bundle.accepted_release_id
    if accepted_release_id is not None and accepted_release_id != authority.release_id:
        raise ProductionEvidenceBridgeError(
            "ACCEPTED_RELEASE_MISMATCH",
            "bundle accepted release does not match pinned release",
        )

    status = str(bundle.manifest.get("status", "")).strip()
    if status and status != "production":
        raise ProductionEvidenceBridgeError(
            "RELEASE_NOT_PRODUCTION",
            "bundle manifest is not production status",
        )

    for kind in ("lexical_index", "provenance", "graph_v2"):
        key = str(bundle.artifact_keys.get(kind, ""))
        digest = str(bundle.artifact_sha256.get(kind, ""))
        if not key or not digest:
            raise ProductionEvidenceBridgeError(
                "RELEASE_ARTIFACT_MISSING",
                f"required production-equivalent artifact missing: {kind}",
            )
        _require_hex64(digest, "RELEASE_ARTIFACT_DIGEST_INVALID")
        if not key.startswith(f"releases/{authority.release_id}/"):
            raise ProductionEvidenceBridgeError(
                "RELEASE_ARTIFACT_KEY_MISMATCH",
                f"artifact key is not release-bound: {kind}",
            )

    pointer = bundle.production_pointer
    if pointer is not None:
        if str(pointer.get("release_id", "")) != authority.release_id:
            raise ProductionEvidenceBridgeError(
                "POINTER_RELEASE_MISMATCH",
                "production pointer release does not match pinned release",
            )
        pointer_manifest = str(pointer.get("manifest_sha256", ""))
        if pointer_manifest and pointer_manifest != authority.manifest_sha256:
            raise ProductionEvidenceBridgeError(
                "POINTER_MANIFEST_MISMATCH",
                "production pointer manifest digest does not match pinned manifest",
            )
    if bundle.production_pointer_sha256:
        _require_hex64(bundle.production_pointer_sha256, "POINTER_DIGEST_INVALID")


def admit_production_evidence(
    *,
    evidence: Sequence[Mapping[str, Any]],
    authority: ProductionEvidenceAuthority,
) -> tuple[dict[str, Any], ...]:
    """Admit only evidence that is pinned to the formal M26 bundle and release."""

    validate_production_authority(authority)
    admitted: list[dict[str, Any]] = []
    seen_evidence_ids: set[str] = set()
    seen_locators: set[str] = set()
    for raw in evidence:
        item = dict(raw)
        evidence_id = _required_string(item, "evidence_id")
        locator_id = _required_string(item, "locator_id")
        if evidence_id in seen_evidence_ids:
            raise ProductionEvidenceBridgeError(
                "DUPLICATE_EVIDENCE_ID",
                "duplicate evidence identity",
            )
        if locator_id in seen_locators:
            raise ProductionEvidenceBridgeError(
                "DUPLICATE_LOCATOR_ID",
                "duplicate locator identity",
            )
        seen_evidence_ids.add(evidence_id)
        seen_locators.add(locator_id)
        if not evidence_id.startswith("m26pa7ev_") or not _HEX32.fullmatch(
            evidence_id[len("m26pa7ev_") :]
        ):
            raise ProductionEvidenceBridgeError(
                "EVIDENCE_ID_NOT_M26_RUNTIME_OWNED",
                "production evidence id is not an M26 PA7 runtime-owned identity",
            )

        expected_binding = authority.evidence_binding_sha256_by_id.get(evidence_id)
        if expected_binding is None:
            raise ProductionEvidenceBridgeError(
                "EVIDENCE_BINDING_NOT_PINNED",
                "evidence identity is not present in the formal M26 bundle",
            )
        if production_evidence_binding_sha256(item) != expected_binding:
            raise ProductionEvidenceBridgeError(
                "EVIDENCE_BINDING_DRIFT",
                "source/locator/release/digest binding drifted",
            )

        evidence_type = str(item.get("evidence_type", "passage"))
        _validate_common(item, authority)
        if evidence_type == "passage":
            _validate_passage(item, authority)
        elif evidence_type == "graph_edge":
            _validate_graph_edge(item, authority)
        elif evidence_type == "provenance":
            _validate_provenance(item, authority)
        else:
            raise ProductionEvidenceBridgeError(
                "EVIDENCE_TYPE_NOT_ADMITTED",
                f"unsupported production evidence type: {evidence_type}",
            )
        admitted.append(item)
    return tuple(admitted)


def citation_bindings_preserved(
    *,
    citations: object,
    selected_evidence: Sequence[Mapping[str, Any]],
    authority: ProductionEvidenceAuthority,
) -> bool:
    """Require every published citation to preserve the exact admitted M26 binding."""

    if not isinstance(citations, list) or not citations:
        return False
    by_id = {str(item.get("evidence_id", "")): item for item in selected_evidence}
    for raw in citations:
        if not isinstance(raw, Mapping):
            return False
        evidence_id = str(raw.get("evidence_id", ""))
        evidence = by_id.get(evidence_id)
        if evidence is None:
            return False
        if authority.evidence_binding_sha256_by_id.get(
            evidence_id
        ) != production_evidence_binding_sha256(evidence):
            return False
        expected_equal = {
            "locator_id": evidence.get("locator_id"),
            "source_id": evidence.get("source_id"),
            "section_id": evidence.get("section_id"),
            "concept_id": evidence.get("concept_id"),
            "release_id": authority.release_id,
            "source_identity": evidence.get("source_identity"),
            "provenance_record_sha256": evidence.get("provenance_record_sha256"),
        }
        for field, expected in expected_equal.items():
            if str(raw.get(field, "")) != str(expected or ""):
                return False
        if str(raw.get("source_artifact_sha256", "")) != str(evidence.get("artifact_sha256", "")):
            return False
        if str(raw.get("support_text_sha256", "")) != str(evidence.get("passage_text_sha256", "")):
            return False
        if str(raw.get("source_locator", "")) != (
            f"{evidence.get('artifact_key', '')}#{evidence.get('section_id', '')}"
        ):
            return False
        if raw.get("runtime_owned_locator") is not True:
            return False
    return True


def _validate_common(
    item: Mapping[str, Any],
    authority: ProductionEvidenceAuthority,
) -> None:
    if _required_string(item, "release_id") != authority.release_id:
        raise ProductionEvidenceBridgeError(
            "EVIDENCE_RELEASE_MISMATCH",
            "evidence release drifted",
        )
    passage_text = _required_string(item, "passage_text")
    passage_digest = _required_string(item, "passage_text_sha256")
    _require_hex64(passage_digest, "PASSAGE_DIGEST_INVALID")
    if hashlib.sha256(passage_text.encode("utf-8")).hexdigest() != passage_digest:
        raise ProductionEvidenceBridgeError(
            "PASSAGE_DIGEST_MISMATCH",
            "passage text digest drifted",
        )
    provenance_digest = _required_string(item, "provenance_record_sha256")
    _require_hex64(provenance_digest, "PROVENANCE_DIGEST_INVALID")
    _required_string(item, "source_id")
    _required_string(item, "source_identity")
    _required_string(item, "section_id")
    locator_id = _required_string(item, "locator_id")
    allowed_prefixes = ("m26pa7loc_", "m26pa7edge_", "m26pa7prov_")
    suffix = locator_id.rsplit("_", 1)[-1]
    if not locator_id.startswith(allowed_prefixes) or not _HEX32.fullmatch(suffix):
        raise ProductionEvidenceBridgeError(
            "LOCATOR_NOT_M26_RUNTIME_OWNED",
            "locator is not an M26 PA7 runtime-owned identity",
        )


def _validate_passage(
    item: Mapping[str, Any],
    authority: ProductionEvidenceAuthority,
) -> None:
    bundle = authority.bundle
    _require_artifact_binding(item, bundle, "lexical_index")
    section_id = str(item["section_id"])
    matches = [
        doc
        for doc in bundle.lexical_index.get("documents", [])
        if isinstance(doc, Mapping) and str(doc.get("section_id", "")) == section_id
    ]
    if len(matches) != 1:
        raise ProductionEvidenceBridgeError(
            "SECTION_IDENTITY_MISMATCH",
            "passage section is not uniquely present in release lexical artifact",
        )
    document = matches[0]
    audience = str(document.get("audience", "public"))
    if audience not in authority.allowed_audiences:
        raise ProductionEvidenceBridgeError(
            "ACL_REJECTED",
            "passage audience is not authorized",
        )

    source_id = str(document.get("source_id") or document.get("concept_id", ""))
    if (
        str(item.get("source_id", "")) != source_id
        or str(item.get("source_identity", "")) != source_id
    ):
        raise ProductionEvidenceBridgeError(
            "SOURCE_IDENTITY_MISMATCH",
            "passage source identity drifted",
        )
    if str(item.get("concept_id", "")) != str(document.get("concept_id", "")):
        raise ProductionEvidenceBridgeError(
            "CONCEPT_IDENTITY_MISMATCH",
            "passage concept identity drifted",
        )

    expected_text = legacy._bounded_text(str(document.get("body") or document.get("excerpt") or ""))
    if str(item.get("passage_text", "")) != expected_text:
        raise ProductionEvidenceBridgeError(
            "PASSAGE_RELEASE_CONTENT_MISMATCH",
            "passage content does not match the release document",
        )
    record = legacy._provenance_record_for_document(bundle, document)
    if not record:
        raise ProductionEvidenceBridgeError(
            "PROVENANCE_RECORD_MISSING",
            "release document has no provenance record",
        )
    if str(item.get("provenance_record_sha256", "")) != canonical_sha256(record):
        raise ProductionEvidenceBridgeError(
            "PROVENANCE_RECORD_MISMATCH",
            "passage provenance digest does not match release provenance",
        )


def _validate_graph_edge(
    item: Mapping[str, Any],
    authority: ProductionEvidenceAuthority,
) -> None:
    bundle = authority.bundle
    _require_artifact_binding(item, bundle, "graph_v2")
    edge_id = str(item.get("edge_id") or item.get("section_id") or "")
    matches = [
        edge
        for edge in bundle.graph_v2.get("edges", [])
        if isinstance(edge, Mapping) and str(edge.get("edge_id", "")) == edge_id
    ]
    if len(matches) != 1:
        raise ProductionEvidenceBridgeError(
            "GRAPH_EDGE_IDENTITY_MISMATCH",
            "graph edge is not uniquely present in release graph",
        )
    prototype = legacy._graph_edge_evidence_item(
        bundle=bundle,
        edge=matches[0],
        trace_id="m27-bridge-validation",
        ordinal=1,
    )
    for field in (
        "source_id",
        "source_identity",
        "concept_id",
        "section_id",
        "passage_text",
        "passage_text_sha256",
        "provenance_record_sha256",
    ):
        if str(item.get(field, "")) != str(prototype.get(field, "")):
            raise ProductionEvidenceBridgeError(
                "GRAPH_EDGE_BINDING_MISMATCH",
                f"graph edge field drifted: {field}",
            )
    _require_graph_endpoint_acl(
        bundle,
        matches[0],
        authority.allowed_audiences,
    )


def _validate_provenance(
    item: Mapping[str, Any],
    authority: ProductionEvidenceAuthority,
) -> None:
    bundle = authority.bundle
    _require_artifact_binding(item, bundle, "provenance")
    wanted_digest = str(item.get("provenance_record_sha256", ""))
    records = [
        record
        for record in bundle.provenance.get("records", [])
        if isinstance(record, Mapping) and canonical_sha256(record) == wanted_digest
    ]
    if len(records) != 1:
        raise ProductionEvidenceBridgeError(
            "PROVENANCE_RECORD_MISMATCH",
            "provenance evidence does not bind one release record",
        )
    record = records[0]
    subject = record.get("subject") if isinstance(record.get("subject"), Mapping) else {}
    origin = record.get("origin") if isinstance(record.get("origin"), Mapping) else {}
    claims = record.get("claims") if isinstance(record.get("claims"), list) else []
    first_claim = claims[0] if claims and isinstance(claims[0], Mapping) else {}
    source_id = str(record.get("source_id") or "")
    claim_id = str(first_claim.get("claim_id") or source_id or "provenance_claim")
    expected_source = f"provenance:{claim_id}"
    if (
        str(item.get("source_id", "")) != expected_source
        or str(item.get("source_identity", "")) != expected_source
    ):
        raise ProductionEvidenceBridgeError(
            "SOURCE_IDENTITY_MISMATCH",
            "provenance source identity drifted",
        )
    if str(item.get("section_id", "")) != f"provenance#{claim_id}":
        raise ProductionEvidenceBridgeError(
            "PROVENANCE_LOCATOR_MISMATCH",
            "provenance section identity drifted",
        )
    concept_id = str(subject.get("concept_id") or item.get("concept_id") or "")
    claim_text = str(
        first_claim.get("text")
        or record.get("canonical_url")
        or origin.get("path")
        or "Provenance record is present for this production source."
    )
    statement = f"Provenance record for {concept_id} contains {claim_id}: {claim_text}"
    if str(item.get("passage_text", "")) != statement:
        raise ProductionEvidenceBridgeError(
            "PROVENANCE_TEXT_MISMATCH",
            "provenance evidence text drifted from release record",
        )
    if not _record_has_allowed_document(
        bundle,
        record,
        authority.allowed_audiences,
    ):
        raise ProductionEvidenceBridgeError(
            "ACL_REJECTED",
            "provenance record is not ACL-authorized",
        )


def _require_artifact_binding(
    item: Mapping[str, Any],
    bundle: ProductionAnswerBundle,
    kind: str,
) -> None:
    if str(item.get("artifact_key", "")) != str(bundle.artifact_keys.get(kind, "")):
        raise ProductionEvidenceBridgeError(
            "ARTIFACT_KEY_MISMATCH",
            f"evidence artifact key drifted for {kind}",
        )
    if str(item.get("artifact_sha256", "")) != str(bundle.artifact_sha256.get(kind, "")):
        raise ProductionEvidenceBridgeError(
            "ARTIFACT_DIGEST_MISMATCH",
            f"evidence artifact digest drifted for {kind}",
        )


def _require_graph_endpoint_acl(
    bundle: ProductionAnswerBundle,
    edge: Mapping[str, Any],
    allowed_audiences: frozenset[str],
) -> None:
    concepts = {str(edge.get("source", "")), str(edge.get("target", ""))}
    documents = [
        doc
        for doc in bundle.lexical_index.get("documents", [])
        if isinstance(doc, Mapping) and str(doc.get("concept_id", "")) in concepts
    ]
    present = {str(doc.get("concept_id", "")) for doc in documents}
    if concepts - present:
        raise ProductionEvidenceBridgeError(
            "GRAPH_ENDPOINT_SOURCE_MISSING",
            "graph endpoint has no release document for ACL validation",
        )
    if any(str(doc.get("audience", "public")) not in allowed_audiences for doc in documents):
        raise ProductionEvidenceBridgeError(
            "ACL_REJECTED",
            "graph endpoint is not ACL-authorized",
        )


def _record_has_allowed_document(
    bundle: ProductionAnswerBundle,
    record: Mapping[str, Any],
    allowed_audiences: frozenset[str],
) -> bool:
    subject = record.get("subject") if isinstance(record.get("subject"), Mapping) else {}
    concept_id = str(subject.get("concept_id", ""))
    source_id = str(record.get("source_id", ""))
    for doc in bundle.lexical_index.get("documents", []):
        if not isinstance(doc, Mapping):
            continue
        if concept_id and str(doc.get("concept_id", "")) == concept_id:
            return str(doc.get("audience", "public")) in allowed_audiences
        if source_id and str(doc.get("source_id", "")) == source_id:
            return str(doc.get("audience", "public")) in allowed_audiences
    return False


def _required_string(item: Mapping[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ProductionEvidenceBridgeError(
            "EVIDENCE_FIELD_MISSING",
            f"required evidence field missing: {field}",
        )
    return value


def _require_hex64(value: str, reason_code: str) -> None:
    if not _HEX64.fullmatch(value):
        raise ProductionEvidenceBridgeError(
            reason_code,
            "expected a lowercase SHA-256 digest",
        )


__all__ = [
    "PRODUCTION_EVIDENCE_AUTHORITY_SCHEMA",
    "ProductionEvidenceAuthority",
    "ProductionEvidenceBridgeError",
    "admit_production_evidence",
    "citation_bindings_preserved",
    "production_evidence_binding_sha256",
    "validate_production_authority",
]
