from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .m26_aq_semantic_contract import synthesize_and_verify
from .m26_context_compiler import compile_context_package
from .m26_retrieval_envelope import with_self_digest
from .m27_context_orchestrator import M27RuntimeTask
from .m27_tool_contracts import KnowledgeSearchInput
from .m27_tool_executor import ReadOnlyToolExecutor, ToolExecutionPolicy
from .m27_workspace_contracts import WorkspaceArtifactKind, WorkspaceId, WorkspaceScope
from .m27_workspace_store import WorkspaceStore


@dataclass(frozen=True, slots=True)
class M27ExecutableRequest:
    """Explicit isolated synthetic-evidence route, never the production bundle."""

    question: str
    evidence_catalog: Mapping[str, Mapping[str, Any]]
    compiler_policy: Mapping[str, Any]
    semantic_provider: object
    requirements: Sequence[object] = ()
    intent_class: str = "direct_grounded_knowledge"


class ProviderQuotaExhausted(RuntimeError):
    pass


class ProviderQuota:
    """Enforce caller's provider allowance across M26 internal verification calls."""

    def __init__(self, provider: object, *, max_calls: int, deadline_at: float) -> None:
        self._provider = provider
        self.max_calls = max_calls
        self.deadline_at = deadline_at
        self.calls = 0

    def call(self, payload: Mapping[str, Any], call_class: str) -> object:
        if self.calls >= self.max_calls or time.monotonic() >= self.deadline_at:
            raise ProviderQuotaExhausted("isolated M27 provider budget exhausted")
        self.calls += 1
        return self._provider.call(payload, call_class)


def _bound_evidence(
    *,
    output: object,
    catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    evidence: list[dict[str, Any]] = []
    for item in getattr(output, "items", ()):
        source = catalog.get(item.knowledge_id)
        if source is None:
            continue
        if (
            not item.source_identity
            or not item.locator_id
            or source.get("source_identity") != item.source_identity
            or source.get("locator_id") != item.locator_id
        ):
            continue
        raw = source.get("passage_text")
        if not isinstance(raw, str) or not raw:
            continue
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != source.get("passage_text_sha256"):
            continue
        if not source.get("artifact_sha256") or not source.get("provenance_record_sha256"):
            continue
        evidence.append(dict(source))
    return tuple(evidence)


def _compile_synthetic(
    *,
    evidence: Sequence[Mapping[str, Any]],
    request_id: str,
    policy: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    # M26.3 is synthetic-only by contract. Never treat this as production context.
    unique: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(evidence, start=1):
        pid = str(item.get("evidence_id", ""))
        if not pid or pid in unique:
            continue
        content = str(item["passage_text"])
        unique[pid] = {
            "passage_id": pid,
            "rank": index,
            "text": content,
            "text_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "source_identity": item["source_identity"],
            "locator_id": item["locator_id"],
            "source_id": item.get("source_id", item["source_identity"]),
            "section_id": item.get("section_id", item["locator_id"]),
            "locator": {"locator_id": item["locator_id"]},
        }
    envelope = with_self_digest(
        {
            "schema_version": "knowledge-engine-m26-evidence-envelope/v1",
            "request_id": request_id,
            "sufficiency": "sufficient" if unique else "insufficient",
            "release": {"release_id": "isolated-synthetic"},
            "passages": list(unique.values()),
            "excluded_evidence": [],
        }
    )
    gap = with_self_digest(
        {
            "schema_version": "knowledge-engine-m26-retrieval-gap-report/v1",
            "first_divergent_stage": "none",
            "reason_codes": [],
            "safe_for_context_compiler": bool(unique),
        }
    )
    compiled = compile_context_package(envelope, gap, policy)
    manifest = compiled.get("context_manifest")
    if not isinstance(manifest, Mapping) or not compiled.get("safe_for_provider_mock"):
        return compiled, ()
    chosen = set(manifest.get("selected_passage_ids", ()))
    return compiled, tuple(dict(item) for item in evidence if item.get("evidence_id") in chosen)


def execute_isolated(
    *,
    request: M27ExecutableRequest,
    task: M27RuntimeTask,
    plan: object,
    budget_signal: Mapping[str, object],
    executor: ReadOnlyToolExecutor,
    store: WorkspaceStore,
) -> dict[str, object]:
    """Execute actual Stage5 gather, M26.3 compile and canonical M26 verification.

    No caller-supplied compiled/verification output enters this route.
    """
    workspace_id = WorkspaceId.from_safe_token(scope=WorkspaceScope.TASK, task_token=task.task_id)
    store.create_workspace(workspace_id=workspace_id, scope=WorkspaceScope.TASK)
    rounds: list[dict[str, object]] = []
    records: list[object] = []
    gathered: dict[str, dict[str, Any]] = {}
    answer: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    terminal_reason = "UNVERIFIED_SAFE_TERMINAL"
    deadline_ms = budget_signal.get("deadline_remaining_ms")
    minimum_ms = budget_signal.get("minimum_budget_ms")
    attempts = budget_signal.get("provider_attempts_remaining")
    allowed_budget = (
        type(deadline_ms) is int
        and type(minimum_ms) is int
        and type(attempts) is int
        and deadline_ms >= minimum_ms > 0
        and attempts > 0
        and budget_signal.get("affordable") is True
    )
    provider = ProviderQuota(
        request.semantic_provider,
        max_calls=attempts if type(attempts) is int and attempts > 0 else 0,
        deadline_at=time.monotonic()
        + (deadline_ms / 1000 if type(deadline_ms) is int and deadline_ms > 0 else 0),
    )
    capabilities = tuple(getattr(plan, "tool_capabilities", ()))
    permitted = (
        bool(capabilities)
        and len(capabilities) <= task.max_tool_calls
        and all(capability == "knowledge.search" for capability in capabilities)
    )
    # Fail closed when evidence authorities, budget or capability do not exist.
    if not allowed_budget:
        terminal_reason = "BUDGET_NOT_AUTHORITATIVE"
    elif not permitted:
        terminal_reason = "NO_AUTHORIZED_EVIDENCE_CAPABILITY"
    else:
        policy = ToolExecutionPolicy(
            authorized_capabilities=tuple(sorted(capabilities)),
            authorization_token=task.task_id,
        )
        for round_index in range(task.max_continuation_rounds + 1):
            if len(records) >= task.max_tool_calls:
                terminal_reason = "TOOL_CALL_BUDGET_EXHAUSTED"
                break
            if provider.calls >= provider.max_calls or time.monotonic() >= provider.deadline_at:
                terminal_reason = "PROVIDER_OR_DEADLINE_EXHAUSTED"
                break
            retrieval = executor.execute(
                "knowledge.search",
                KnowledgeSearchInput(request_token=task.request_token),
                policy=policy,
                authorization_token=task.task_id,
            )
            records.append(retrieval.record)
            previous_count = len(gathered)
            for evidence in _bound_evidence(
                output=retrieval.output, catalog=request.evidence_catalog
            ):
                gathered[str(evidence["evidence_id"])] = evidence
            compiled, selected = _compile_synthetic(
                evidence=tuple(gathered.values()),
                request_id=f"{task.task_id}:{round_index}",
                policy=request.compiler_policy,
            )
            compiler_status = str(compiled.get("status", "unavailable"))
            if not selected:
                verification = {
                    "status": "owner_only_safe_abstention",
                    "safe_abstention": True,
                    "citation_locator_valid": False,
                    "material_claim_support_verified": False,
                    "unsupported_accepted_claims": 0,
                    "citations": [],
                }
            else:
                from .m26_aq_semantic_contract import derive_semantic_requirements

                requirements = request.requirements or derive_semantic_requirements(
                    request.question, request.intent_class
                )
                try:
                    answer, _closure = synthesize_and_verify(
                        question=request.question,
                        trace_id=f"{task.task_id}:r{round_index}",
                        intent_class=request.intent_class,
                        evidence=selected,
                        provider_client=provider,
                        requirements=requirements,
                        endpoint_proof={"required": False, "matched": False},
                    )
                    verification = dict(answer)
                except ProviderQuotaExhausted:
                    answer = {}
                    verification = {
                        "status": "owner_only_safe_abstention",
                        "safe_abstention": True,
                        "citation_locator_valid": False,
                        "material_claim_support_verified": False,
                        "unsupported_accepted_claims": 0,
                        "citations": [],
                        "reason_codes": ("PROVIDER_BUDGET_EXHAUSTED",),
                    }
            status = str(verification.get("status", "unknown"))
            citations = verification.get("citations", [])
            verified = (
                status == "owner_only_cited_answer"
                and bool(verification.get("material_claim_support_verified"))
                and bool(verification.get("citation_locator_valid"))
                and verification.get("unsupported_accepted_claims") == 0
                and bool(citations)
                and bool(selected)
            )
            budget_ok = (
                provider.calls < provider.max_calls
                and time.monotonic() < provider.deadline_at
                and len(records) < task.max_tool_calls
            )
            has_gap = not verified
            can_continue = has_gap and round_index < task.max_continuation_rounds and budget_ok
            terminal_reason = (
                "VERIFIED_CITED_ANSWER"
                if verified
                else "VERIFIER_GAP_CONTINUE"
                if can_continue
                else "VERIFIER_GAP_SAFE_TERMINAL"
            )
            rounds.append(
                {
                    "round_index": round_index,
                    "continuation_reason": "INITIAL" if round_index == 0 else "VERIFIER_GAP",
                    "capabilities_invoked": ["knowledge.search"],
                    "evidence_count": len(gathered),
                    "evidence_delta": len(gathered) - previous_count,
                    "compiler_status": compiler_status,
                    "verification_status": status,
                    "budget_outcome": "CAN_CONTINUE" if can_continue else "TERMINAL",
                    "provider_calls": provider.calls,
                    "tool_calls": len(records),
                    "terminal_reason": terminal_reason,
                }
            )
            if not can_continue:
                break
    result = {
        "status_code": "M27_RUNTIME_COMPOSED"
        if terminal_reason == "VERIFIED_CITED_ANSWER"
        else "M27_RUNTIME_SAFE_TERMINAL",
        "workspace_id": workspace_id.value,
        "rounds": tuple(rounds),
        "evidence_identities": tuple(
            {
                "evidence_id": item["evidence_id"],
                "passage_id": item["evidence_id"],
                "source_identity": item["source_identity"],
                "locator_id": item["locator_id"],
                "evidence_type": item.get("evidence_type", "passage"),
            }
            for item in gathered.values()
        ),
        "tool_records": tuple(records),
        "verification": verification,
        "answer": answer if terminal_reason == "VERIFIED_CITED_ANSWER" else {},
        "provider_calls": provider.calls,
        "terminal_reason": terminal_reason,
        "production_touched": False,
    }
    store.write_json_artifact(
        workspace_id=workspace_id,
        kind=WorkspaceArtifactKind.DIAGNOSTIC,
        relative_path="runtime/execution_summary.json",
        payload={
            "status_code": result["status_code"],
            "rounds": rounds,
            "terminal_reason": terminal_reason,
            "tool_calls": len(records),
            "provider_calls": provider.calls,
            "production_touched": False,
        },
    )
    return result
