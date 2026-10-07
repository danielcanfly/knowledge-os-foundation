from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from . import m26_aq_semantic_contract as m26
from . import m26_pa7_arbitrary_query_runtime as legacy
from . import m26_pa7_semantic_closure_runtime as runtime
from .m26_production_answer_bundle import ProductionAnswerBundle
from .m27_context_orchestrator import M27RuntimeTask, RuntimeTaskKind
from .m27_production_evidence_bridge import (
    ProductionEvidenceAuthority,
    production_evidence_binding_sha256,
)
from .m27_runtime_execution import M27ExecutableRequest
from .m27_runtime_harness import M27RuntimeHarness, M27RuntimeHarnessInput
from .m27_tool_contracts import KnowledgeItemRef, KnowledgeSearchOutput
from .m27_tool_executor import ReadOnlyToolExecutor
from .m27_workspace_store import WorkspaceStore

BUNDLE_SNAPSHOT_ENV = "M27_TEST_PAGE_BUNDLE_SNAPSHOT"
WORKSPACE_ROOT_ENV = "M27_TEST_PAGE_WORKSPACE_ROOT"
DEFAULT_WORKSPACE_ROOT = Path("/tmp/m27-test-page-workspaces")


class SnapshotKnowledgeProvider:
    def __init__(self, rows: Mapping[str, Mapping[str, Any]]) -> None:
        self._rows = dict(rows)
        self.searches = 0

    def search(self, request: object) -> KnowledgeSearchOutput:
        self.searches += 1
        limit = int(getattr(request, "max_results", 8) or 8)
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
    root = Path(__file__).resolve().parents[2]
    compiler_policy = json.loads((root / "pilot/m26/m26-3-context-policy.json").read_text())
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

        intent_class = m26._canonical_intent_class(normalized, legacy._intent_class(normalized))
        trace_id = "m27tp_" + question_sha256[:32]
        retrieval_question = legacy._fast_retrieval_query(normalized)
        event_sink({"type": "stage.started", "stage": "retrieval"})
        started = time.monotonic()
        lexical, dense = legacy._run_lexical_primary_retrieval(
            question=retrieval_question,
            bundle=bundle,
            dense_channel=None,
            dense_fallback_channel=None,
            require_remote_dense=False,
            top_k=8,
            event_sink=None,
        )
        evidence = legacy._select_evidence(
            bundle=bundle,
            lexical_result=lexical,
            dense_result=dense,
            trace_id=trace_id,
            question=retrieval_question,
            intent_class=intent_class,
        )
        requirements = m26.derive_semantic_requirements(normalized, intent_class)
        evidence, _endpoint_proof = runtime._strengthen_evidence(
            bundle=bundle,
            evidence=evidence,
            lexical_result=lexical,
            trace_id=trace_id,
            question=normalized,
            intent_class=intent_class,
            requirements=requirements,
        )
        event_sink(
            {
                "type": "stage.completed",
                "stage": "retrieval",
                "selected_evidence_count": len(evidence),
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )
        if not evidence:
            return _safe_terminal(["NO_AUTHORIZED_PRODUCTION_EVIDENCE"], question_sha256)

        rows: dict[str, dict[str, Any]] = {
            f"ev-{idx:02d}": dict(item) for idx, item in enumerate(evidence[:8], start=1)
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
        provider = m26.MiniMaxClient(
            os.environ.get("MINIMAX_API_KEY", ""),
            max_calls=4,
            max_cost=Decimal("0.10"),
        )
        executable_request = M27ExecutableRequest(
            question=normalized,
            evidence_catalog=rows,
            compiler_policy=compiler_policy,
            semantic_provider=provider,
            production_evidence_authority=authority,
            requirements=tuple(requirements),
            intent_class=intent_class,
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
                    "deadline_remaining_ms": 60000,
                    "minimum_budget_ms": 500,
                    "provider_attempts_remaining": 4,
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
