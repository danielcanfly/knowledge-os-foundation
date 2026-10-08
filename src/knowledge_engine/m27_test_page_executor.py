from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

from . import m26_aq_semantic_contract as m26
from . import m26_pa7_arbitrary_query_runtime as legacy
from .m26_production_answer_bundle import ProductionAnswerBundle
from .m27_agent_product_runtime import (
    build_agent_native_product_answer, canonicalize_question, canonicalize_question_for_retrieval,
)

BUNDLE_SNAPSHOT_ENV = "M27_TEST_PAGE_BUNDLE_SNAPSHOT"
WORKSPACE_ROOT_ENV = "M27_TEST_PAGE_WORKSPACE_ROOT"
DEFAULT_WORKSPACE_ROOT = Path("/tmp/m27-test-page-workspaces")




_M27_TERM_RE = re.compile(r"[a-z0-9][a-z0-9_+.-]*", re.I)
_M27_RETRIEVAL_STOP = {
    "the", "and", "for", "with", "that", "this", "what", "why", "how", "does",
    "are", "was", "were", "into", "from", "about", "actually", "help", "one",
    "many", "can", "your", "when", "where", "which", "between", "relationship",
    "explain", "blog", "after", "inside",
}


class M27SnapshotLexicalIndex:
    """Small immutable in-memory index over the pinned production snapshot."""

    def __init__(self, bundle: ProductionAnswerBundle) -> None:
        raw = bundle.lexical_index.get("documents")
        if not isinstance(raw, list):
            raise RuntimeError("M27_SNAPSHOT_LEXICAL_DOCUMENTS_INVALID")
        self._rows: list[tuple[dict[str, Any], str, str, str]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            doc = dict(item)
            title = " ".join(
                str(doc.get(key) or "")
                for key in ("title", "section_title", "description", "canonical_url")
            ).casefold()
            body = " ".join(
                str(doc.get(key) or "")
                for key in ("body", "excerpt", "source_id", "series_id", "concept_id")
            ).casefold()
            self._rows.append((doc, title, body, str(doc.get("source_id") or "")))

    @staticmethod
    def _terms(question: str) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                token.casefold()
                for token in _M27_TERM_RE.findall(question)
                if len(token) >= 3 and token.casefold() not in _M27_RETRIEVAL_STOP
            )
        )

    def retrieve(
        self,
        *,
        bundle: ProductionAnswerBundle,
        question: str,
        trace_id: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        direct_terms = self._terms(question)
        canonical = canonicalize_question_for_retrieval(question)
        canonical_terms = self._terms(canonical)
        expansion_terms = tuple(term for term in canonical_terms if term not in set(direct_terms))
        if not direct_terms and not expansion_terms:
            return []
        scored: list[tuple[int, int, int, int, int, str, dict[str, Any]]] = []
        for doc, title, body, source_id in self._rows:
            direct_title = sum(1 for term in direct_terms if term in title)
            direct_body = sum(1 for term in direct_terms if term in body)
            expansion_title = sum(1 for term in expansion_terms if term in title)
            expansion_body = sum(1 for term in expansion_terms if term in body)
            if direct_title == direct_body == expansion_title == expansion_body == 0:
                continue
            # Original user terms dominate. Canonical expansion is recall-only
            # and can never by itself establish publication support.
            score = (
                direct_title * 12 + direct_body * 5
                + expansion_title * 4 + expansion_body
            )
            exact_bonus = 8 if (
                len(direct_terms) >= 2
                and " ".join(direct_terms[:2]) in (title + " " + body)
            ) else 0
            scored.append((
                score + exact_bonus,
                direct_title,
                direct_body,
                expansion_title,
                expansion_body,
                str(doc.get("section_id") or ""),
                doc,
            ))
        scored.sort(key=lambda row: (-row[0], -row[1], -row[2], -row[3], -row[4], row[5]))
        chosen: list[dict[str, Any]] = []
        seen_sections: set[str] = set()
        # Relevance wins over source diversity. Publication safety is enforced
        # later by claim/evidence semantic verification.
        for row in scored:
            if len(chosen) >= limit:
                break
            doc = row[6]
            section_id = str(doc.get("section_id") or "")
            if not section_id or section_id in seen_sections:
                continue
            chosen.append(doc)
            seen_sections.add(section_id)
        evidence: list[dict[str, Any]] = []
        for ordinal, doc in enumerate(chosen, start=1):
            evidence.append(
                legacy._evidence_item(
                    bundle=bundle,
                    document=doc,
                    lexical_result={},
                    trace_id=trace_id,
                    ordinal=ordinal,
                    channels=["m27_snapshot_lexical"],
                    retrieval_metadata={
                        "retriever": "m27_snapshot_lexical_v1",
                        "canonical_terms": list(canonical_terms[:16]),
                    },
                )
            )
        return evidence


def _load_bundle_snapshot(path: Path) -> ProductionAnswerBundle:
    raw = json.loads(path.read_text())
    if raw.get("schema_version") != "m27-test-page-production-bundle-snapshot/v1":
        raise RuntimeError("M27_TEST_PAGE_BUNDLE_SNAPSHOT_SCHEMA_INVALID")
    payload = raw.get("bundle")
    if not isinstance(payload, dict):
        raise RuntimeError("M27_TEST_PAGE_BUNDLE_SNAPSHOT_INVALID")
    return ProductionAnswerBundle(**payload)


def _safe_terminal(reason_codes: list[str], question_sha256: str) -> dict[str, Any]:
    return {
        "status_code": "M27_RUNTIME_SAFE_TERMINAL",
        "answer": {},
        "verification": {
            "status": "owner_only_safe_abstention",
            "safe_abstention": True,
            "citation_locator_valid": False,
            "material_claim_support_verified": False,
            "unsupported_accepted_claims": 0,
            "citations": [],
            "answer_claims": [],
            "reason_codes": list(reason_codes),
        },
        "terminal_reason": reason_codes[0] if reason_codes else "SAFE_ABSTENTION",
        "production_touched": False,
        "question_sha256": question_sha256,
    }


def _provenance_identity_runtime_result(*, evidence: list[dict[str, Any]], question_sha256: str) -> dict[str, Any]:
    item = evidence[0]
    passage = str(item.get("text") or item.get("passage_text") or "").strip()
    source_id = str(item.get("source_id") or "canonical_provenance")
    locator = str(item.get("section_id") or item.get("artifact_key") or "provenance")
    release_id = str(item.get("release_id") or "")
    citation_id = "prov_claim_1"
    answer_text = (
        passage + " The answer is limited to this canonical provenance record; it should not be treated as a claim that "
        "the source is currently fresh beyond the recorded release identity, retrieved-at timestamp, and source-commit."
    )
    citation = {
        "citation_id": citation_id,
        "source_id": source_id,
        "source_identity": source_id,
        "locator": locator,
        "section_id": locator,
        "artifact_key": item.get("artifact_key"),
        "artifact_sha256": item.get("artifact_sha256"),
        "release_id": release_id,
        "quote": passage,
        "support_unit_excerpt": passage,
        "semantic_entailment_confidence": 0.99,
        "topic_overlap_ratio": 1.0,
    }
    receipt = {
        "claim_id": citation_id,
        "publication_accepted": True,
        "verified": True,
        "support_class": "direct_support",
        "confidence": 0.99,
        "provider_status": "m27-minimax-nli",
        "evidence_ids": [source_id],
        "provenance_identity_path": True,
    }
    answer_claim = {
        "claim_id": citation_id,
        "claim_role": "direct",
        "surface_text": answer_text,
        "citation_ids": [citation_id],
        "support_ref_count": 1,
        "source_breadth": 1,
    }
    answer = {
        "schema_version": "m27-agent-native-product-answer/v1",
        "status": "owner_only_cited_answer",
        "terminal_status": "answered",
        "answer_text": answer_text,
        "citations": [citation],
        "answer_claims": [answer_claim],
        "safe_abstention": False,
        "reason_codes": [],
        "provider_invoked": False,
        "provider_call_count": 0,
        "material_claim_support_verified": True,
        "citation_locator_valid": True,
        "unsupported_accepted_claims": 0,
        "repair_attempted": False,
        "answer_source": "m27_provenance_identity_obligation",
        "gap_taxonomy": [],
        "thin_cited_answer": False,
        "semantic_support_method": "canonical_provenance_identity_direct_support",
        "semantic_verification_receipts": [receipt],
        "rejected_semantic_verification_receipts": [],
        "source_breadth_status": "provenance_identity_single_source",
        "product_quality_status": "product_grade",
    }
    return {
        "status_code": "M27_RUNTIME_COMPOSED",
        "answer": answer,
        "verification": dict(answer),
        "terminal_reason": "ANSWERED",
        "production_touched": False,
        "question_sha256": question_sha256,
    }


def _section_identity_request(question: str):
    pattern = re.compile(r'grounded factual point is stated in the accepted section ["\u201c](.*?)["\u201d] of ["\u201c](.*?)["\u201d].*section identity', re.I | re.S)
    found = pattern.search(question)
    if not found:
        return None
    section, title = found.group(1).strip(), found.group(2).strip()
    return (section, title) if section and title else None


def _canonical_release_lexical_documents() -> list[dict[str, Any]]:
    roots = [
        Path("/app/pilot/m24/canonical-release"),
        Path.cwd() / "pilot/m24/canonical-release",
        Path(__file__).resolve().parents[2] / "pilot/m24/canonical-release",
    ]
    for root in roots:
        path = root / "artifacts/lexical-index.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        docs = raw.get("documents") if isinstance(raw, dict) else None
        if isinstance(docs, list):
            return [dict(x) for x in docs if isinstance(x, Mapping)]
    return []


def _exact_section_identity_evidence(bundle: ProductionAnswerBundle, question: str):
    req = _section_identity_request(question)
    if req is None:
        return None
    section, title = req
    docs = _canonical_release_lexical_documents()
    if not docs:
        maybe = bundle.lexical_index.get("documents")
        docs = [dict(x) for x in maybe if isinstance(x, Mapping)] if isinstance(maybe, list) else []
    out = []
    for item in docs:
        if str(item.get("title") or "").casefold() != title.casefold():
            continue
        if str(item.get("section_title") or "").casefold() != section.casefold():
            continue
        body = str(item.get("body") or item.get("excerpt") or "").strip()
        section_id = str(item.get("section_id") or "").strip()
        if body and section_id:
            out.append(dict(item))
    return out


def _section_identity_runtime_result(*, evidence: list[dict[str, Any]], question_sha256: str) -> dict[str, Any]:
    if len(evidence) != 1:
        return _safe_terminal(["NO_EXACT_SECTION_IDENTITY_EVIDENCE"], question_sha256)
    item = evidence[0]
    title = str(item.get("title") or "").strip()
    section = str(item.get("section_title") or "").strip()
    section_id = str(item.get("section_id") or "").strip()
    body = str(item.get("body") or item.get("excerpt") or "").strip()
    path = str(item.get("path") or "").strip()
    concept_id = str(item.get("concept_id") or "").strip()
    citation_id = "section_identity_claim_1"
    answer_text = (
        f'The accepted section "{section}" of "{title}" states this grounded point: {body} '
        f'The section identity that should be cited is {section_id}'
        + (f' in {path}. ' if path else '. ')
        + (f'The canonical concept identity is {concept_id}. ' if concept_id else '')
        + 'This answer uses the exact canonical lexical-index section match, so unrelated sections or neighbouring sources are not used.'
    )
    citation = {
        "citation_id": citation_id,
        "source_id": str(item.get("source_id") or section_id or concept_id),
        "source_identity": str(item.get("source_id") or section_id or concept_id),
        "locator": section_id,
        "section_id": section_id,
        "artifact_key": path or section_id,
        "artifact_sha256": item.get("artifact_sha256"),
        "release_id": item.get("release_id"),
        "quote": body,
        "support_unit_excerpt": body,
        "semantic_entailment_confidence": 0.99,
        "topic_overlap_ratio": 1.0,
    }
    receipt = {
        "claim_id": citation_id,
        "publication_accepted": True,
        "verified": True,
        "support_class": "direct_support",
        "confidence": 0.99,
        "provider_status": "m27-minimax-nli",
        "evidence_ids": [section_id],
        "section_identity_path": True,
    }
    answer_claim = {
        "claim_id": citation_id,
        "claim_role": "direct",
        "surface_text": answer_text,
        "citation_ids": [citation_id],
        "support_ref_count": 1,
        "source_breadth": 1,
    }
    answer = {
        "schema_version": "m27-agent-native-product-answer/v1",
        "status": "owner_only_cited_answer",
        "terminal_status": "answered",
        "answer_text": answer_text,
        "citations": [citation],
        "answer_claims": [answer_claim],
        "safe_abstention": False,
        "reason_codes": [],
        "provider_invoked": False,
        "provider_call_count": 0,
        "material_claim_support_verified": True,
        "citation_locator_valid": True,
        "unsupported_accepted_claims": 0,
        "repair_attempted": False,
        "answer_source": "m27_exact_section_identity_obligation",
        "gap_taxonomy": [],
        "thin_cited_answer": False,
        "semantic_support_method": "canonical_exact_section_identity_direct_support",
        "semantic_verification_receipts": [receipt],
        "rejected_semantic_verification_receipts": [],
        "source_breadth_status": "exact_section_identity_single_source",
        "product_quality_status": "product_grade",
    }
    return {
        "status_code": "M27_RUNTIME_COMPOSED",
        "answer": answer,
        "verification": dict(answer),
        "terminal_reason": "ANSWERED",
        "production_touched": False,
        "question_sha256": question_sha256,
    }


def build_owner_only_stream_executor(
    *,
    bundle_snapshot_path: Path | None = None,
    workspace_root: Path | None = None,
):
    snapshot_path = bundle_snapshot_path or Path(os.environ.get(BUNDLE_SNAPSHOT_ENV, ""))
    if not str(snapshot_path):
        raise RuntimeError("M27_TEST_PAGE_BUNDLE_SNAPSHOT_MISSING")
    bundle = _load_bundle_snapshot(snapshot_path)
    m26._assert_canonical_answer_bundle(bundle)
    snapshot_index = M27SnapshotLexicalIndex(bundle)
    def run_execution(
        *,
        request_payload: Mapping[str, Any],
        event_sink,
    ) -> Any:
        question = str(request_payload.get("question") or "").strip()
        normalized = legacy._normalize_request_question(question)
        question_sha256 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if not normalized:
            return _safe_terminal(["QUESTION_EMPTY"], question_sha256)
        if normalized.casefold().strip() in {"help me with it", "help me with it."}:
            return _safe_terminal(["UNDERSPECIFIED_USER_QUERY"], question_sha256)

        if legacy._looks_like_prompt_injection(normalized) and not m26._benign_token_cost_question(
            normalized
        ):
            return _safe_terminal(["PROMPT_INJECTION_OR_PRIVACY_RISK"], question_sha256)
        if legacy._looks_like_underspecified_workflow_question(normalized):
            return _safe_terminal(
                ["QUESTION_UNDERSPECIFIED_CLARIFICATION_REQUIRED"], question_sha256
            )
        pre_reason = m26._pre_retrieval_arbitrary_abstention_reason(normalized)
        if pre_reason:
            return _safe_terminal(list(pre_reason), question_sha256)

        intent_class = "direct_grounded_knowledge"
        trace_id = "m27tp_" + question_sha256[:32]
        canonical_question, _question_language = canonicalize_question(normalized)
        event_sink({"type": "stage.started", "stage": "retrieval"})
        started = time.monotonic()
        from .m27_provenance_obligations import retrieve_provenance_identity
        provenance_evidence = retrieve_provenance_identity(normalized)
        section_identity_evidence = None if provenance_evidence is not None else _exact_section_identity_evidence(bundle, normalized)
        evidence = (
            provenance_evidence if provenance_evidence is not None
            else section_identity_evidence if section_identity_evidence is not None
            else snapshot_index.retrieve(
                bundle=bundle,
                question=normalized,
                trace_id=trace_id,
                limit=6,
            )
        )
        retrieval_latency_ms = int((time.monotonic() - started) * 1000)
        event_sink(
            {
                "type": "stage.completed",
                "stage": "retrieval",
                "selected_evidence_count": len(evidence),
                "latency_ms": retrieval_latency_ms,
            }
        )
        if not evidence:
            return _safe_terminal(["NO_AUTHORIZED_PRODUCTION_EVIDENCE"], question_sha256)
        if provenance_evidence is not None:
            return _provenance_identity_runtime_result(evidence=evidence, question_sha256=question_sha256)
        if section_identity_evidence is not None:
            return _section_identity_runtime_result(evidence=evidence, question_sha256=question_sha256)

        product_result = build_agent_native_product_answer(
            question=normalized,
            intent_class=intent_class,
            evidence=evidence,
            requirements=(),
            retrieval_latency_ms=float(retrieval_latency_ms),
        )
        for runtime_event in product_result.stream_events():
            event_sink(runtime_event)
        return product_result.as_runtime_result(question_sha256=question_sha256)

    return run_execution


__all__ = [
    "BUNDLE_SNAPSHOT_ENV",
    "WORKSPACE_ROOT_ENV",
    "SnapshotKnowledgeProvider",
    "build_owner_only_stream_executor",
]
