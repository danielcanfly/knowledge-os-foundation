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
        evidence = (provenance_evidence if provenance_evidence is not None else snapshot_index.retrieve(
            bundle=bundle,
            question=normalized,
            trace_id=trace_id,
            limit=6,
        ))
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
