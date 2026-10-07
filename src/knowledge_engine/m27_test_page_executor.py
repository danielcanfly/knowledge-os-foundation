from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from . import m26_aq_semantic_contract as m26
from . import m26_pa7_arbitrary_query_runtime as legacy
from .m26_production_answer_bundle import ProductionAnswerBundle
from .m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from .m27_agent_product_runtime import build_agent_native_product_answer, canonicalize_question
from .m27_production_evidence_bridge import (
    ProductionEvidenceAuthority,
    production_evidence_binding_sha256,
)
from .m27_runtime_execution import M27ExecutableRequest, SemanticProviderUnavailable
from .m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from .m27_tool_contracts import KnowledgeItemRef, KnowledgeSearchOutput
from .m27_tool_executor import ReadOnlyToolExecutor
from .m27_workspace_store import WorkspaceStore

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
        terms = self._terms(question)
        if not terms:
            return []
        scored: list[tuple[int, int, int, str, dict[str, Any]]] = []
        for doc, title, body, source_id in self._rows:
            title_hits = sum(1 for term in terms if term in title)
            body_hits = sum(1 for term in terms if term in body)
            if title_hits == 0 and body_hits == 0:
                continue
            score = title_hits * 9 + body_hits * 3
            exact_bonus = 6 if len(terms) >= 2 and " ".join(terms[:2]) in (title + " " + body) else 0
            scored.append(
                (
                    score + exact_bonus,
                    title_hits,
                    body_hits,
                    str(doc.get("section_id") or ""),
                    doc,
                )
            )
        scored.sort(key=lambda row: (-row[0], -row[1], -row[2], row[3]))
        chosen: list[dict[str, Any]] = []
        seen_sections: set[str] = set()
        seen_sources: set[str] = set()
        # First pass deliberately promotes source breadth. This is generic and
        # independent of case IDs or expected answers.
        for row in scored:
            doc = row[4]
            section_id = str(doc.get("section_id") or "")
            source_id = str(doc.get("source_id") or "")
            if not section_id or section_id in seen_sections or source_id in seen_sources:
                continue
            chosen.append(doc)
            seen_sections.add(section_id)
            seen_sources.add(source_id)
            if len(chosen) >= min(4, limit):
                break
        for row in scored:
            if len(chosen) >= limit:
                break
            doc = row[4]
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
                        "canonical_terms": list(terms[:16]),
                    },
                )
            )
        return evidence


class _UnavailableSemanticProvider:
    def call(self, payload: Mapping[str, Any], call_class: str) -> object:
        raise SemanticProviderUnavailable("semantic provider unavailable for isolated candidate")


class SnapshotKnowledgeProvider:
    def __init__(self, rows: Mapping[str, Mapping[str, Any]]) -> None:
        self._rows = dict(rows)
        self.searches = 0

    def search(self, request: object) -> KnowledgeSearchOutput:
        self.searches += 1
        # These rows are already the bounded canonical M26 selected/strengthened
        # evidence set. Do not silently truncate that authoritative set again.
        requested_limit = getattr(request, "max_results", None)
        limit = min(len(self._rows), int(requested_limit)) if isinstance(requested_limit, int) and requested_limit > 0 else len(self._rows)
        items = []
        for knowledge_id, row in list(self._rows.items())[:limit]:
            items.append(
                KnowledgeItemRef(
                    knowledge_id=knowledge_id,
                    source_identity=str(row.get("source_identity") or "") or None,
                    locator_id=str(row.get("locator_id") or "") or None,
                    evidence_type=str(row.get("evidence_type") or "passage"),
                )
            )
        return KnowledgeSearchOutput(
            items=tuple(items),
            total_count=len(self._rows),
            truncated=len(self._rows) > limit,
        )


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
    root = Path(os.environ.get("KNOWLEDGE_ENGINE_ROOT", "/app"))
    policy_path = root / "pilot/m26/m26-3-context-policy.json"
    if not policy_path.is_file():
        policy_path = Path.cwd() / "pilot/m26/m26-3-context-policy.json"
    if not policy_path.is_file():
        raise RuntimeError("M27_TEST_PAGE_COMPILER_POLICY_UNAVAILABLE")
    compiler_policy = json.loads(policy_path.read_text())
    workspace_base = workspace_root or Path(
        os.environ.get(WORKSPACE_ROOT_ENV, str(DEFAULT_WORKSPACE_ROOT))
    )
    workspace_base.mkdir(parents=True, exist_ok=True)

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
        evidence = snapshot_index.retrieve(
            bundle=bundle,
            question=canonical_question,
            trace_id=trace_id,
            limit=6,
        )
        requirements: tuple[object, ...] = ()
        _endpoint_proof = {
            "retriever": "m27_snapshot_lexical_v1",
            "canonicalization": "m27_multilingual_concept_expansion",
            "production_snapshot_read_only": True,
            "selected_evidence_count": len(evidence),
        }
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

        rows: dict[str, dict[str, Any]] = {
            f"ev-{idx:02d}": dict(item) for idx, item in enumerate(evidence, start=1)
        }
        bindings = {
            str(item["evidence_id"]): production_evidence_binding_sha256(item)
            for item in rows.values()
        }
        audiences = frozenset(
            str(item.get("audience") or "internal") for item in rows.values()
        )
        authority = ProductionEvidenceAuthority(
            bundle=bundle,
            release_id=bundle.release_id,
            manifest_sha256=bundle.manifest_sha256,
            allowed_audiences=audiences,
            evidence_binding_sha256_by_id=bindings,
        )
        try:
            provider = m26.MiniMaxClient(
                os.environ.get("MINIMAX_API_KEY", ""),
                max_calls=1,
                max_cost=Decimal("0.10"),
            )
        except Exception:
            provider = _UnavailableSemanticProvider()
        executable_request = M27ExecutableRequest(
            question=normalized,
            evidence_catalog=rows,
            compiler_policy=compiler_policy,
            semantic_provider=provider,
            production_evidence_authority=authority,
            requirements=requirements,
            intent_class=intent_class,
            endpoint_proof=dict(_endpoint_proof),
            event_sink=event_sink,
        )
        token = question_sha256[:24]
        task = M27RuntimeTask(
            task_id=f"task:test-page:{token}",
            kind=RuntimeTaskKind.KNOWLEDGE,
            request_token=f"request:test-page:{token}",
            max_continuation_rounds=1,
            max_tool_calls=3,
        )
        case_workspace = workspace_base / token
        if case_workspace.exists():
            shutil.rmtree(case_workspace)
        harness = M27RuntimeHarness(
            workspace_store=WorkspaceStore(root=case_workspace),
            tool_executor=ReadOnlyToolExecutor(
                knowledge_provider=SnapshotKnowledgeProvider(rows)
            ),
        )
        result = harness.run(
            M27RuntimeHarnessInput(
                task=task,
                routing_signal={"route": "SEMANTIC_CLOSURE", "reason": "owner_only_test_page"},
                budget_signal={
                    "route": "SEMANTIC_CLOSURE",
                    "reason": "bounded_semantic_recovery",
                    "deadline_remaining_ms": 14500,
                    "minimum_budget_ms": 500,
                    "provider_attempts_remaining": 1,
                    "affordable": True,
                },
                executable_request=executable_request,
                m27_enabled=True,
            )
        )
        return result

    return run_execution


__all__ = [
    "BUNDLE_SNAPSHOT_ENV",
    "WORKSPACE_ROOT_ENV",
    "SnapshotKnowledgeProvider",
    "build_owner_only_stream_executor",
]
