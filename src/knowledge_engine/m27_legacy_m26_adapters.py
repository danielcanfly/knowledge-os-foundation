from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .m27_context_runtime_contracts import (
    STAGE1_UNAVAILABLE,
    ComputeDecision,
    ContextCompileResult,
    ContextPlan,
    EvidencePlan,
    Stage1Unavailable,
    VerificationDecision,
)

_MISSING = object()


def _read_signal(signal: object, key: str) -> Any:
    if isinstance(signal, Mapping):
        return signal.get(key, _MISSING)
    return getattr(signal, key, _MISSING)


def _stage1_str(value: Any) -> str | Stage1Unavailable:
    if value is _MISSING or value is None:
        return STAGE1_UNAVAILABLE
    return str(value)


def _optional_stage1_str(value: Any) -> str | None | Stage1Unavailable:
    if value is _MISSING:
        return STAGE1_UNAVAILABLE
    if value is None:
        return None
    return str(value)


def _stage1_int(value: Any) -> int | Stage1Unavailable:
    if value is _MISSING or value is None or isinstance(value, bool):
        return STAGE1_UNAVAILABLE
    try:
        return int(value)
    except (TypeError, ValueError):
        return STAGE1_UNAVAILABLE


def _stage1_bool(value: Any) -> bool | Stage1Unavailable:
    if isinstance(value, bool):
        return value
    return STAGE1_UNAVAILABLE


def _reason_codes(value: Any) -> tuple[str, ...]:
    if value is _MISSING or value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _string_tuple(value: Any) -> tuple[str, ...] | Stage1Unavailable:
    if value is _MISSING or value is None:
        return STAGE1_UNAVAILABLE
    if isinstance(value, str) or not isinstance(value, Sequence):
        return STAGE1_UNAVAILABLE
    return tuple(str(item) for item in value)


class LegacyM26SemanticRoutingAdapter:
    """Pure adapter over an already-produced M26 SemanticRoutingDecision."""

    def normalize(self, routing_signal: object) -> ContextPlan:
        return ContextPlan(
            route=_stage1_str(_read_signal(routing_signal, "route")),
            reason=_stage1_str(_read_signal(routing_signal, "reason")),
            evidence_plan=EvidencePlan(),
        )


class LegacyM26DeadlineBudgetAdapter:
    """Expose existing M26 routing-budget fields without re-running routing."""

    def normalize(self, budget_signal: object) -> ComputeDecision:
        affordable = _read_signal(budget_signal, "affordable")
        if callable(affordable):
            affordable = _MISSING

        return ComputeDecision(
            route=_stage1_str(_read_signal(budget_signal, "route")),
            reason=_stage1_str(_read_signal(budget_signal, "reason")),
            deadline_remaining_ms=_stage1_int(
                _read_signal(budget_signal, "deadline_remaining_ms")
            ),
            minimum_budget_ms=_stage1_int(_read_signal(budget_signal, "minimum_budget_ms")),
            provider_attempts_remaining=_stage1_int(
                _read_signal(budget_signal, "provider_attempts_remaining")
            ),
            affordable=_stage1_bool(affordable),
        )


class LegacyM26ContextCompilerAdapter:
    """Normalize an existing m26_context_compiler package; never compile again."""

    def normalize(self, compiled_output: Mapping[str, object]) -> ContextCompileResult:
        manifest_value = compiled_output.get("context_manifest", _MISSING)
        manifest = manifest_value if isinstance(manifest_value, Mapping) else None
        budget_value = compiled_output.get("evidence_budget", _MISSING)
        budget = budget_value if isinstance(budget_value, Mapping) else None
        diagnostics_value = compiled_output.get("diagnostics", _MISSING)
        diagnostics = diagnostics_value if isinstance(diagnostics_value, Mapping) else None

        selected = (
            _string_tuple(manifest.get("selected_passage_ids", _MISSING))
            if manifest is not None
            else STAGE1_UNAVAILABLE
        )
        token_budget = (
            _stage1_int(manifest.get("token_budget", _MISSING))
            if manifest is not None
            else (
                _stage1_int(budget.get("token_budget", _MISSING))
                if budget is not None
                else STAGE1_UNAVAILABLE
            )
        )
        measured = (
            _stage1_int(manifest.get("measured_token_estimate", _MISSING))
            if manifest is not None
            else (
                _stage1_int(budget.get("measured_token_estimate", _MISSING))
                if budget is not None
                else STAGE1_UNAVAILABLE
            )
        )
        citations = compiled_output.get("citations", _MISSING)
        citation_count: int | Stage1Unavailable
        if isinstance(citations, Sequence) and not isinstance(citations, (str, bytes)):
            citation_count = len(citations)
        else:
            citation_count = STAGE1_UNAVAILABLE

        manifest_sha = compiled_output.get("context_manifest_sha256", _MISSING)
        budget_sha = compiled_output.get("evidence_budget_sha256", _MISSING)

        return ContextCompileResult(
            status=_stage1_str(compiled_output.get("status", _MISSING)),
            context_manifest_sha256=_optional_stage1_str(manifest_sha),
            evidence_budget_sha256=_optional_stage1_str(budget_sha),
            token_budget=token_budget,
            measured_token_estimate=measured,
            selected_passage_ids=selected,
            citation_count=citation_count,
            safe_for_provider=_stage1_bool(
                compiled_output.get("safe_for_provider_mock", _MISSING)
            ),
            prompt_injection_quarantined=(
                _stage1_bool(diagnostics.get("prompt_injection_quarantined", _MISSING))
                if diagnostics is not None
                else STAGE1_UNAVAILABLE
            ),
            reason_codes=(
                _reason_codes(diagnostics.get("reason_codes", _MISSING))
                if diagnostics is not None
                else ()
            ),
        )


class LegacyM26VerifierAdapter:
    """Normalize existing verifier/final-response fields without re-verifying."""

    def normalize(self, verification_output: Mapping[str, object]) -> VerificationDecision:
        citations = verification_output.get("citations", _MISSING)
        citation_count: int | Stage1Unavailable
        if isinstance(citations, Sequence) and not isinstance(citations, (str, bytes)):
            citation_count = len(citations)
        else:
            citation_count = STAGE1_UNAVAILABLE

        return VerificationDecision(
            status=_stage1_str(verification_output.get("status", _MISSING)),
            terminal_status=_stage1_str(
                verification_output.get("terminal_status", _MISSING)
            ),
            safe_abstention=_stage1_bool(
                verification_output.get("safe_abstention", _MISSING)
            ),
            reason_codes=_reason_codes(
                verification_output.get("reason_codes", _MISSING)
            ),
            provider_call_count=_stage1_int(
                verification_output.get("provider_call_count", _MISSING)
            ),
            material_claim_support_verified=_stage1_bool(
                verification_output.get("material_claim_support_verified", _MISSING)
            ),
            citation_locator_valid=_stage1_bool(
                verification_output.get("citation_locator_valid", _MISSING)
            ),
            unsupported_accepted_claims=_stage1_int(
                verification_output.get("unsupported_accepted_claims", _MISSING)
            ),
            repair_attempted=_stage1_bool(
                verification_output.get("repair_attempted", _MISSING)
            ),
            citation_count=citation_count,
            answer_source=_stage1_str(
                verification_output.get("answer_source", _MISSING)
            ),
        )
