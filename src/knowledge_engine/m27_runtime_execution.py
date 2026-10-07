from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .m26_aq_semantic_contract import synthesize_and_verify
from . import m26_aq_semantic_contract as canonical_m26
from . import m26_pa7_arbitrary_query_runtime as legacy_m26
from . import m26_pa7_semantic_closure_runtime as semantic_runtime
from .m26_context_compiler import compile_context_package
from .m26_retrieval_envelope import with_self_digest
from .m27_adaptive_compute import AdaptiveComputeBudget, AdaptiveComputeController
from .m27_context_orchestrator import M27RuntimeTask
from .m27_production_evidence_bridge import (
    ProductionEvidenceAuthority,
    ProductionEvidenceBridgeError,
    admit_production_evidence,
    citation_bindings_preserved,
    validate_production_authority,
)
from .m27_runtime_telemetry import (
    M27RoundTelemetry,
    M27RuntimeTelemetry,
    ProviderCallTelemetry,
    assert_privacy_safe_telemetry,
    elapsed_ms,
)
from .m27_tool_contracts import KnowledgeSearchInput
from .m27_tool_executor import ReadOnlyToolExecutor, ToolExecutionPolicy
from .m27_workspace_contracts import WorkspaceArtifactKind, WorkspaceId, WorkspaceScope
from .m27_workspace_store import WorkspaceStore


@dataclass(frozen=True, slots=True)
class M27ExecutableRequest:
    """Explicit isolated route with synthetic or pinned production-equivalent evidence."""

    question: str
    evidence_catalog: Mapping[str, Mapping[str, Any]]
    compiler_policy: Mapping[str, Any]
    semantic_provider: object
    production_evidence_authority: ProductionEvidenceAuthority | None = None
    requirements: Sequence[object] = ()
    intent_class: str = "direct_grounded_knowledge"
    endpoint_proof: Mapping[str, Any] | None = None


class ProviderQuotaExhausted(RuntimeError):
    pass


class ProviderQuota:
    """Enforce caller's provider allowance across M26 internal verification calls."""

    def __init__(self, provider: object, *, max_calls: int, deadline_at: float) -> None:
        self._provider = provider
        self.max_calls = max_calls
        self.deadline_at = deadline_at
        self.calls = 0
        self.telemetry: list[ProviderCallTelemetry] = []

    def call(self, payload: Mapping[str, Any], call_class: str) -> object:
        if self.calls >= self.max_calls or time.monotonic() >= self.deadline_at:
            raise ProviderQuotaExhausted("isolated M27 provider budget exhausted")
        self.calls += 1
        start_ns = time.perf_counter_ns()
        try:
            result = self._provider.call(payload, call_class)
        except Exception:
            self.telemetry.append(
                ProviderCallTelemetry(
                    call_index=self.calls,
                    call_class=call_class,
                    latency_ms=elapsed_ms(start_ns, time.perf_counter_ns()),
                    success=False,
                    reason_code="PROVIDER_EXCEPTION",
                )
            )
            raise
        self.telemetry.append(
            ProviderCallTelemetry(
                call_index=self.calls,
                call_class=call_class,
                latency_ms=elapsed_ms(start_ns, time.perf_counter_ns()),
                success=True,
                reason_code="PROVIDER_CALL_OK",
            )
        )
        return result


def _evidence_authority(request: M27ExecutableRequest) -> str:
    if request.production_evidence_authority is not None:
        return "production_equivalent"
    return "synthetic_only"


def _release_for_compiler(request: M27ExecutableRequest) -> Mapping[str, Any]:
    authority = request.production_evidence_authority
    if authority is not None:
        return {
            "schema_version": "knowledge-engine-m27-production-evidence-bridge/v1",
            "release_id": authority.release_id,
            "manifest_sha256": authority.manifest_sha256,
        }
    return {"release_id": "isolated-synthetic"}


def _verification_citations_are_selected(
    verification: Mapping[str, Any],
    selected: Sequence[Mapping[str, Any]],
) -> bool:
    selected_locators = {str(item.get("locator_id") or "") for item in selected}
    selected_evidence_ids = {str(item.get("evidence_id") or "") for item in selected}
    citations = verification.get("citations")
    if not isinstance(citations, Sequence) or isinstance(citations, (str, bytes)):
        return False
    for citation in citations:
        if not isinstance(citation, Mapping):
            return False
        locator_id = str(citation.get("locator_id") or "")
        evidence_id = str(citation.get("evidence_id") or "")
        if locator_id and locator_id not in selected_locators:
            return False
        if evidence_id and evidence_id not in selected_evidence_ids:
            return False
    return True


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
    release: Mapping[str, Any],
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
            "release": dict(release),
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


def _try_canonical_evidence_bound_fast_path(
    *,
    question: str,
    trace_id: str,
    intent_class: str,
    evidence: Sequence[Mapping[str, Any]],
    requirements: Sequence[object],
    endpoint_proof: Mapping[str, Any],
) -> dict[str, Any] | None:
    runtime_requirements = canonical_m26._runtime_semantic_requirements(requirements)
    candidates: list[Mapping[str, Any]] = []
    try:
        candidate = legacy_m26._deterministic_provider_candidate(question=question, intent_class=intent_class, evidence=evidence)
        if isinstance(candidate, Mapping): candidates.append(candidate)
    except Exception:
        pass
    try:
        recovery = canonical_m26._supported_semantic_recovery_candidate(question=question, intent_class=intent_class, evidence=evidence, requirements=runtime_requirements, endpoint_proof=endpoint_proof)
    except Exception:
        recovery = None
    if isinstance(recovery, Mapping): candidates.append(recovery)
    try:
        candidates.extend(canonical_m26._deterministic_facet_local_preflight_candidates(question=question, intent_class=intent_class, evidence=evidence, requirements=runtime_requirements))
    except Exception:
        pass
    seen: set[str] = set()
    for candidate in candidates:
        fp = canonical_m26.canonical_sha256(candidate)
        if fp in seen: continue
        seen.add(fp)
        try:
            verified = legacy_m26._verify_multi_evidence_provider_output(trace_id=trace_id, question=question, intent_class=intent_class, evidence=evidence, provider_text=json.dumps(semantic_runtime._verification_candidate(candidate), ensure_ascii=False, separators=(",", ":")))
            answer = legacy_m26._verified_multi_evidence_answer(intent_class=intent_class, verified=verified, evidence=evidence, calls=[], repair_attempted=False)
            canonical_m26._use_verified_natural_surface(answer, canonical_m26._public_candidate_surface(candidate, answer))
        except Exception:
            continue
        if answer.get("status") != "owner_only_cited_answer": continue
        answer_text = str(answer.get("answer_text", ""))
        if canonical_m26.evaluate_visible_semantics(answer_text, runtime_requirements, question): continue
        if canonical_m26._internal_reference_leaks(answer_text, question): continue
        if canonical_m26._question_answer_alignment_failures(question=question, answer_text=answer_text, evidence=evidence): continue
        source_ids = sorted({str(item.get("source_identity", "")) for item in answer.get("citations", []) if isinstance(item, Mapping) and str(item.get("source_identity", ""))})
        if canonical_m26._quality_surface_failures(question=question, answer_text=answer_text, source_identities=source_ids): continue
        failures, _ = canonical_m26._endpoint_aware_requirement_support_failures(runtime=canonical_m26._RUNTIME_FACADE, requirements=runtime_requirements, evidence=canonical_m26._candidate_evidence(candidate, evidence), endpoint_proof=endpoint_proof)
        if failures: continue
        answer["answer_source"] = "m27_canonical_evidence_bound_preflight"
        return dict(answer)
    return None



def _try_canonical_fast_provider_answer(
    *,
    question: str,
    trace_id: str,
    intent_class: str,
    evidence: Sequence[Mapping[str, Any]],
    provider: ProviderQuota,
) -> dict[str, Any] | None:
    payload = legacy_m26._fast_synthesis_payload(
        question=question, trace_id=trace_id, intent_class=intent_class, evidence=evidence
    )
    try:
        provider_result = provider.call(payload, legacy_m26.FAST_SYNTHESIS_CALL_CLASS)
        normalized = legacy_m26._normalize_fast_provider_result(provider_result)
    except Exception:
        return None
    if legacy_m26._fast_public_abstention_publication(normalized) is not None:
        return None
    publication = legacy_m26._validate_fast_provider_candidate(
        question=question, selected_evidence=evidence, provider_output=normalized
    )
    if publication is None:
        return None
    if canonical_m26._question_answer_alignment_failures(
        question=question, answer_text=str(publication.get("answer_text", "")), evidence=evidence
    ):
        return None
    if canonical_m26._fast_required_facet_citation_failures(
        question=question, intent_class=intent_class, evidence=evidence, publication=publication
    ):
        return None
    evidence_by_id = {str(item["evidence_id"]): item for item in evidence}
    citations: list[dict[str, Any]] = []
    support_refs = list(publication.get("support_refs", []))
    for index, citation_id in enumerate(publication.get("citation_ids", []), start=1):
        citation_id = str(citation_id)
        selected = evidence_by_id.get(citation_id)
        if selected is None:
            return None
        support_ref = support_refs[index - 1] if index - 1 < len(support_refs) else legacy_m26._deterministic_support_ref(selected)
        if support_ref is None:
            snippet = str(selected.get("passage_text", ""))[:240]
            support_ref = {
                "evidence_id": citation_id,
                "locator_id": str(selected["locator_id"]),
                "exact_quote": snippet,
                "exact_support_snippet": snippet,
                "exact_quote_sha256": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                "uncertainty": "low",
            }
        citations.append(legacy_m26._public_citation(
            selected, {"claim_id": "claim_1", "claim_role": "direct"}, support_ref, index
        ))
    answer_text = str(publication.get("answer_text", "")).strip()
    if not answer_text or not citations:
        return None
    return {
        "status": "owner_only_cited_answer",
        "terminal_status": "fast_answer_ready",
        "answer_text": answer_text,
        "citations": citations,
        "answer_claims": [{
            "claim_id": "claim_1", "claim_role": "direct", "surface_text": answer_text,
            "citation_ids": [item["citation_id"] for item in citations],
            "support_ref_count": len(citations),
        }],
        "safe_abstention": False, "reason_codes": [], "provider_invoked": True,
        "provider_call_count": 1, "material_claim_support_verified": True,
        "citation_locator_valid": True, "unsupported_accepted_claims": 0,
        "repair_attempted": False,
        "answer_source": "m27_canonical_fast_natural_cited_synthesis",
    }


def execute_isolated(
    *,
    request: M27ExecutableRequest,
    task: M27RuntimeTask,
    plan: object,
    budget_signal: Mapping[str, object],
    executor: ReadOnlyToolExecutor,
    store: WorkspaceStore,
    route: str = "UNAVAILABLE",
    compute_tier: str = "UNAVAILABLE",
    budget_class: str = "UNAVAILABLE",
    adaptive_budget: AdaptiveComputeBudget | None = None,
    adaptive_controller: AdaptiveComputeController | None = None,
) -> dict[str, object]:
    """Execute actual Stage5 gather, M26.3 compile and canonical M26 verification.

    No caller-supplied compiled/verification output enters this route.
    """
    execution_start_ns = time.perf_counter_ns()
    workspace_id = WorkspaceId.from_safe_token(scope=WorkspaceScope.TASK, task_token=task.task_id)
    store.create_workspace(workspace_id=workspace_id, scope=WorkspaceScope.TASK)
    rounds: list[dict[str, object]] = []
    telemetry_rounds: list[M27RoundTelemetry] = []
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
    adaptive_provider_cap = (
        adaptive_budget.max_provider_calls if adaptive_budget is not None else 4
    )
    provider = ProviderQuota(
        request.semantic_provider,
        max_calls=(
            min(attempts, adaptive_provider_cap)
            if type(attempts) is int and attempts > 0
            else 0
        ),
        deadline_at=time.monotonic()
        + (deadline_ms / 1000 if type(deadline_ms) is int and deadline_ms > 0 else 0),
    )
    capabilities = tuple(getattr(plan, "tool_capabilities", ()))
    effective_tool_cap = (
        adaptive_budget.max_tool_calls if adaptive_budget is not None else task.max_tool_calls
    )
    effective_round_cap = (
        adaptive_budget.max_continuation_rounds
        if adaptive_budget is not None
        else task.max_continuation_rounds
    )
    permitted = (
        bool(capabilities)
        and len(capabilities) <= effective_tool_cap
        and all(capability == "knowledge.search" for capability in capabilities)
    )
    production_authority = request.production_evidence_authority
    authority_rejection: str | None = None
    if production_authority is not None:
        try:
            validate_production_authority(production_authority)
        except ProductionEvidenceBridgeError as exc:
            authority_rejection = exc.reason_code
    # Fail closed when evidence authorities, budget or capability do not exist.
    if not allowed_budget:
        terminal_reason = "BUDGET_NOT_AUTHORITATIVE"
    elif authority_rejection is not None:
        terminal_reason = "PRODUCTION_EVIDENCE_AUTHORITY_REJECTED"
    elif not permitted:
        terminal_reason = "NO_AUTHORIZED_EVIDENCE_CAPABILITY"
    else:
        policy = ToolExecutionPolicy(
            authorized_capabilities=tuple(sorted(capabilities)),
            authorization_token=task.task_id,
        )
        for round_index in range(effective_round_cap + 1):
            if len(records) >= effective_tool_cap:
                terminal_reason = "TOOL_CALL_BUDGET_EXHAUSTED"
                break
            if provider.calls >= provider.max_calls or time.monotonic() >= provider.deadline_at:
                terminal_reason = "PROVIDER_OR_DEADLINE_EXHAUSTED"
                break
            round_start_ns = time.perf_counter_ns()
            provider_start_index = len(provider.telemetry)
            tool_start_ns = time.perf_counter_ns()
            retrieval = executor.execute(
                "knowledge.search",
                KnowledgeSearchInput(request_token=task.request_token),
                policy=policy,
                authorization_token=task.task_id,
            )
            tool_end_ns = time.perf_counter_ns()
            records.append(retrieval.record)
            previous_count = len(gathered)
            binding_start_ns = time.perf_counter_ns()
            bound = _bound_evidence(output=retrieval.output, catalog=request.evidence_catalog)
            if production_authority is not None:
                try:
                    bound = admit_production_evidence(
                        evidence=bound, authority=production_authority
                    )
                except ProductionEvidenceBridgeError as exc:
                    binding_end_ns = time.perf_counter_ns()
                    terminal_reason = "PRODUCTION_EVIDENCE_AUTHORITY_REJECTED"
                    verification = {
                        "status": "owner_only_safe_abstention",
                        "safe_abstention": True,
                        "citation_locator_valid": False,
                        "material_claim_support_verified": False,
                        "unsupported_accepted_claims": 0,
                        "citations": [],
                        "reason_codes": ("PRODUCTION_EVIDENCE_AUTHORITY_REJECTED", exc.reason_code),
                    }
                    round_end_ns = time.perf_counter_ns()
                    provider_round = tuple(provider.telemetry[provider_start_index:])
                    round_telemetry = M27RoundTelemetry(
                        round_index=round_index,
                        continuation_reason="INITIAL" if round_index == 0 else "VERIFIER_GAP",
                        route=route,
                        task_kind=task.kind.value,
                        compute_tier=compute_tier,
                        budget_class=budget_class,
                        stage_latency_ms={
                            "tool_ms": elapsed_ms(tool_start_ns, tool_end_ns),
                            "evidence_binding_ms": elapsed_ms(binding_start_ns, binding_end_ns),
                            "compiler_ms": 0.0,
                            "provider_ms": 0.0,
                            "verifier_ms": 0.0,
                            "round_total_ms": elapsed_ms(round_start_ns, round_end_ns),
                        },
                        tool_calls=("knowledge.search",),
                        retrieval_evidence_count=len(gathered),
                        evidence_delta=0,
                        compiler_status="authority_rejected",
                        provider_calls=provider_round,
                        verifier_status="owner_only_safe_abstention",
                        continuation_allowed=False,
                        continuation_decision="TERMINAL",
                        terminal_reason=terminal_reason,
                    )
                    telemetry_rounds.append(round_telemetry)
                    rounds.append(
                        {
                            "round_index": round_index,
                            "continuation_reason": "INITIAL"
                            if round_index == 0
                            else "VERIFIER_GAP",
                            "capabilities_invoked": ["knowledge.search"],
                            "evidence_count": len(gathered),
                            "evidence_delta": 0,
                            "compiler_status": "authority_rejected",
                            "verification_status": "owner_only_safe_abstention",
                            "budget_outcome": "TERMINAL",
                            "provider_calls": provider.calls,
                            "tool_calls": len(records),
                            "terminal_reason": terminal_reason,
                            "evidence_authority": "production_equivalent",
                            "compiler_authority": "m26_3_synthetic_selector_non_authoritative",
                        }
                    )
                    break
            for evidence in bound:
                gathered[str(evidence["evidence_id"])] = evidence
            binding_end_ns = time.perf_counter_ns()
            compiler_start_ns = time.perf_counter_ns()
            if production_authority is not None:
                compiled = {"status": "production_evidence_preserved", "safe_for_provider_mock": True}
                selected = tuple(dict(item) for item in gathered.values())
            else:
                compiled, selected = _compile_synthetic(
                    evidence=tuple(gathered.values()),
                    request_id=f"{task.task_id}:{round_index}",
                    policy=request.compiler_policy,
                    release=_release_for_compiler(request),
                )
            compiler_end_ns = time.perf_counter_ns()
            compiler_status = str(compiled.get("status", "unavailable"))
            if not selected:
                verifier_start_ns = time.perf_counter_ns()
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
                verifier_start_ns = time.perf_counter_ns()
                try:
                    endpoint_proof = dict(request.endpoint_proof or {"required": False, "matched": False})
                    fast_answer = _try_canonical_evidence_bound_fast_path(question=request.question, trace_id=f"{task.task_id}:r{round_index}", intent_class=request.intent_class, evidence=selected, requirements=requirements, endpoint_proof=endpoint_proof)
                    if fast_answer is not None:
                        answer = fast_answer
                    else:
                        fast_provider_answer = _try_canonical_fast_provider_answer(
                            question=request.question,
                            trace_id=f"{task.task_id}:r{round_index}",
                            intent_class=request.intent_class,
                            evidence=selected,
                            provider=provider,
                        )
                        if fast_provider_answer is not None:
                            answer = fast_provider_answer
                        else:
                            answer, _closure = synthesize_and_verify(
                                question=request.question,
                                trace_id=f"{task.task_id}:r{round_index}",
                                intent_class=request.intent_class,
                                evidence=selected,
                                provider_client=provider,
                                requirements=requirements,
                                endpoint_proof=endpoint_proof,
                            )
                    verification = dict(answer)
                    if (
                        production_authority is not None
                        and verification.get("status") == "owner_only_cited_answer"
                        and not citation_bindings_preserved(
                            citations=verification.get("citations"),
                            selected_evidence=selected,
                            authority=production_authority,
                        )
                    ):
                        answer = {}
                        verification = {
                            "status": "owner_only_safe_abstention",
                            "safe_abstention": True,
                            "citation_locator_valid": False,
                            "material_claim_support_verified": False,
                            "unsupported_accepted_claims": 0,
                            "citations": [],
                            "reason_codes": ("PRODUCTION_CITATION_BINDING_DRIFT",),
                        }
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
            verifier_end_ns = time.perf_counter_ns()
            status = str(verification.get("status", "unknown"))
            citations = verification.get("citations", [])
            verified = (
                status == "owner_only_cited_answer"
                and bool(verification.get("material_claim_support_verified"))
                and bool(verification.get("citation_locator_valid"))
                and verification.get("unsupported_accepted_claims") == 0
                and bool(citations)
                and bool(selected)
                and _verification_citations_are_selected(verification, selected)
            )
            budget_ok = (
                provider.calls < provider.max_calls
                and time.monotonic() < provider.deadline_at
                and len(records) < effective_tool_cap
            )
            has_gap = not verified
            if adaptive_budget is not None and adaptive_controller is not None:
                adaptive_continuation = adaptive_controller.decide_continuation(
                    budget=adaptive_budget,
                    telemetry={
                        "evidence_delta": len(gathered) - previous_count,
                        "round_total_ms": elapsed_ms(round_start_ns, time.perf_counter_ns()),
                    },
                    completed_rounds=round_index,
                    tool_calls=len(records),
                    provider_calls=provider.calls,
                    verified=verified,
                )
                can_continue = has_gap and budget_ok and adaptive_continuation.allowed
                adaptive_continuation_reason = adaptive_continuation.reason_code.value
            else:
                can_continue = has_gap and round_index < effective_round_cap and budget_ok
                adaptive_continuation_reason = "LEGACY_BOUNDED_CONTINUATION"
            terminal_reason = (
                "VERIFIED_CITED_ANSWER"
                if verified
                else "VERIFIER_GAP_CONTINUE"
                if can_continue
                else "VERIFIER_GAP_SAFE_TERMINAL"
            )
            round_end_ns = time.perf_counter_ns()
            provider_round = tuple(provider.telemetry[provider_start_index:])
            provider_ms = round(sum(item.latency_ms for item in provider_round), 3)
            verifier_total_ms = elapsed_ms(verifier_start_ns, verifier_end_ns)
            verifier_exclusive_ms = round(max(0.0, verifier_total_ms - provider_ms), 3)
            round_telemetry = M27RoundTelemetry(
                round_index=round_index,
                continuation_reason="INITIAL" if round_index == 0 else "VERIFIER_GAP",
                route=route,
                task_kind=task.kind.value,
                compute_tier=compute_tier,
                budget_class=budget_class,
                stage_latency_ms={
                    "tool_ms": elapsed_ms(tool_start_ns, tool_end_ns),
                    "evidence_binding_ms": elapsed_ms(binding_start_ns, binding_end_ns),
                    "compiler_ms": elapsed_ms(compiler_start_ns, compiler_end_ns),
                    "provider_ms": provider_ms,
                    "verifier_ms": verifier_exclusive_ms,
                    "round_total_ms": elapsed_ms(round_start_ns, round_end_ns),
                },
                tool_calls=("knowledge.search",),
                retrieval_evidence_count=len(gathered),
                evidence_delta=len(gathered) - previous_count,
                compiler_status=compiler_status,
                provider_calls=provider_round,
                verifier_status=status,
                continuation_allowed=can_continue,
                continuation_decision="CONTINUE" if can_continue else "TERMINAL",
                terminal_reason=terminal_reason,
            )
            telemetry_rounds.append(round_telemetry)
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
                    "adaptive_continuation_reason": adaptive_continuation_reason,
                    "evidence_authority": (
                        "production_equivalent"
                        if production_authority is not None
                        else "synthetic_only"
                    ),
                    "compiler_authority": (
                        "production_evidence_preserved_after_formal_authority_admission"
                        if production_authority is not None
                        else "m26_3_synthetic_only"
                    ),
                }
            )
            if not can_continue:
                break
    authority_label = _evidence_authority(request)
    verification = {
        **verification,
        "evidence_authority": authority_label,
        "production_evidence_authority": production_authority is not None,
    }
    telemetry = M27RuntimeTelemetry(
        request_id=task.request_token,
        task_id=task.task_id,
        route=route,
        task_kind=task.kind.value,
        compute_tier=compute_tier,
        budget_class=budget_class,
        rounds=tuple(telemetry_rounds),
        terminal_reason=terminal_reason,
        feature_flags={
            "M27_ENABLED": True,
            "ISOLATED_EXECUTABLE_RUNTIME": True,
            "PRODUCTION_EQUIVALENT_EVIDENCE": production_authority is not None,
        },
        reason_codes=tuple(str(code) for code in getattr(plan, "reason_codes", ()))
        + tuple(adaptive_budget.reason_codes if adaptive_budget is not None else ()),
        total_latency_ms=elapsed_ms(execution_start_ns, time.perf_counter_ns()),
    ).as_dict()
    assert_privacy_safe_telemetry(telemetry)
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
                "release_id": item.get("release_id", ""),
                "artifact_sha256": item.get("artifact_sha256", ""),
                "provenance_record_sha256": item.get("provenance_record_sha256", ""),
            }
            for item in gathered.values()
        ),
        "tool_records": tuple(records),
        "verification": verification,
        "answer": answer if terminal_reason == "VERIFIED_CITED_ANSWER" else {},
        "provider_calls": provider.calls,
        "terminal_reason": terminal_reason,
        "evidence_authority": authority_label,
        "production_touched": False,
        "telemetry": telemetry,
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
            "evidence_authority": authority_label,
            "telemetry_schema_version": telemetry["schema_version"],
        },
    )
    store.write_json_artifact(
        workspace_id=workspace_id,
        kind=WorkspaceArtifactKind.DIAGNOSTIC,
        relative_path="runtime/telemetry.json",
        payload=telemetry,
    )
    return result
