from __future__ import annotations

import inspect
from dataclasses import fields

import pytest

from knowledge_engine.m27_decision_trace import (
    BudgetClass,
    ComputeTier,
    ContextSource,
    DecisionReasonCode,
    DecisionRoute,
    DecisionTraceEvent,
    GuardObservation,
    GuardOutcome,
    SafeAbstentionOutcome,
    StatusClass,
    TraceGuard,
    emit_decision_trace_if_enabled,
    new_trace_id,
)
from knowledge_engine.m27_feature_flags import (
    M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED,
    M27FeatureFlags,
    load_m27_feature_flags,
)


def _event() -> DecisionTraceEvent:
    return DecisionTraceEvent(
        trace_id=new_trace_id(),
        route=DecisionRoute.SEMANTIC_CLOSURE,
        reason_code=DecisionReasonCode.CLAIM_SUPPORT_GAP,
        compute_tier=ComputeTier.LEGACY_M26,
        deadline_budget_class=BudgetClass.CONSTRAINED,
        provider_budget_class=BudgetClass.HEALTHY,
        provider_attempt_count=2,
        context_sources=(ContextSource.LEXICAL, ContextSource.DENSE),
        evidence_count=8,
        citation_count=3,
        status_class=StatusClass.CITED_ANSWER,
        safe_abstention_outcome=SafeAbstentionOutcome.DID_NOT_ABSTAIN,
        guard_outcomes=(
            GuardObservation(
                guard=TraceGuard.CITATION_BINDING,
                outcome=GuardOutcome.PASSED,
            ),
            GuardObservation(
                guard=TraceGuard.UNSUPPORTED_MATERIAL_CLAIM,
                outcome=GuardOutcome.PASSED,
            ),
        ),
    )


def test_feature_flag_defaults_false() -> None:
    assert M27FeatureFlags().context_runtime_shadow_trace_enabled is False
    assert (
        load_m27_feature_flags(
            environ={},
            isolated_runtime=True,
        ).context_runtime_shadow_trace_enabled
        is False
    )


def test_feature_flag_cannot_enable_outside_isolated_m27_runtime() -> None:
    flags = load_m27_feature_flags(
        environ={M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED: "true"},
        isolated_runtime=False,
    )
    directly_constructed = M27FeatureFlags(
        shadow_trace_requested=True,
        isolated_runtime=False,
    )

    assert flags.context_runtime_shadow_trace_enabled is False
    assert directly_constructed.context_runtime_shadow_trace_enabled is False


def test_feature_flag_enables_only_with_explicit_isolated_runtime_gate() -> None:
    flags = load_m27_feature_flags(
        environ={M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED: "true"},
        isolated_runtime=True,
    )

    assert flags.context_runtime_shadow_trace_enabled is True


def test_feature_flag_does_not_retain_raw_environment_value() -> None:
    secret_like_value = "secret-do-not-store"
    flags = load_m27_feature_flags(
        environ={M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED: secret_like_value},
        isolated_runtime=True,
    )

    assert flags.context_runtime_shadow_trace_enabled is False
    assert secret_like_value not in repr(flags)


def test_trace_schema_has_no_raw_or_sensitive_payload_fields() -> None:
    field_names = {field.name for field in fields(DecisionTraceEvent)}
    signature_names = set(inspect.signature(DecisionTraceEvent).parameters)
    forbidden = {
        "query",
        "raw_query",
        "answer",
        "raw_answer",
        "evidence_text",
        "full_evidence_text",
        "source_text",
        "full_source_text",
        "secret",
        "api_key",
        "token",
        "credential",
        "environment_value",
        "env_value",
        "private_payload",
        "payload",
        "metadata",
        "production_write_credential",
    }

    assert forbidden.isdisjoint(field_names)
    assert forbidden.isdisjoint(signature_names)


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "raw_query",
        "raw_answer",
        "full_evidence_text",
        "full_source_text",
        "secret",
        "api_key",
        "token",
        "credential",
        "env_value",
        "private_payload",
        "payload",
    ],
)
def test_trace_constructor_rejects_sensitive_payload_kwargs(forbidden_field: str) -> None:
    kwargs = {
        "trace_id": new_trace_id(),
        "route": DecisionRoute.SEMANTIC_CLOSURE,
        "reason_code": DecisionReasonCode.ROUTE_SELECTED,
        "compute_tier": ComputeTier.LEGACY_M26,
        "deadline_budget_class": BudgetClass.HEALTHY,
        "provider_budget_class": BudgetClass.HEALTHY,
        "provider_attempt_count": 1,
        "context_sources": (ContextSource.LEXICAL,),
        "evidence_count": 3,
        "citation_count": 2,
        "status_class": StatusClass.CITED_ANSWER,
        "safe_abstention_outcome": SafeAbstentionOutcome.DID_NOT_ABSTAIN,
        forbidden_field: "sensitive-value",
    }

    with pytest.raises(TypeError):
        DecisionTraceEvent(**kwargs)


def test_trace_id_rejects_free_form_or_raw_query_text() -> None:
    with pytest.raises(ValueError, match="canonical UUID"):
        DecisionTraceEvent(
            trace_id="What confidential customer question did I ask?",
            route=DecisionRoute.SEMANTIC_CLOSURE,
            reason_code=DecisionReasonCode.ROUTE_SELECTED,
            compute_tier=ComputeTier.LEGACY_M26,
            deadline_budget_class=BudgetClass.HEALTHY,
            provider_budget_class=BudgetClass.HEALTHY,
            provider_attempt_count=1,
            context_sources=(ContextSource.LEXICAL,),
            evidence_count=1,
            citation_count=1,
            status_class=StatusClass.CITED_ANSWER,
            safe_abstention_outcome=SafeAbstentionOutcome.DID_NOT_ABSTAIN,
        )


def test_enum_fields_reject_free_form_text() -> None:
    with pytest.raises(TypeError, match="DecisionReasonCode"):
        DecisionTraceEvent(
            trace_id=new_trace_id(),
            route=DecisionRoute.SEMANTIC_CLOSURE,
            reason_code="customer secret goes here",  # type: ignore[arg-type]
            compute_tier=ComputeTier.LEGACY_M26,
            deadline_budget_class=BudgetClass.HEALTHY,
            provider_budget_class=BudgetClass.HEALTHY,
            provider_attempt_count=1,
            context_sources=(ContextSource.LEXICAL,),
            evidence_count=1,
            citation_count=1,
            status_class=StatusClass.CITED_ANSWER,
            safe_abstention_outcome=SafeAbstentionOutcome.DID_NOT_ABSTAIN,
        )


def test_sanitized_enums_counts_ids_and_guard_outcomes_serialize() -> None:
    event = _event()

    payload = event.as_dict()

    assert payload == {
        "schema_version": "m27-sanitized-decision-trace/v1",
        "trace_id": event.trace_id,
        "route": "SEMANTIC_CLOSURE",
        "reason_code": "CLAIM_SUPPORT_GAP",
        "compute_tier": "LEGACY_M26",
        "deadline_budget_class": "CONSTRAINED",
        "provider_budget_class": "HEALTHY",
        "provider_attempt_count": 2,
        "provider_attempt_class": "MULTIPLE",
        "context_sources": ["LEXICAL", "DENSE"],
        "evidence_count": 8,
        "citation_count": 3,
        "status_class": "CITED_ANSWER",
        "safe_abstention_outcome": "DID_NOT_ABSTAIN",
        "guard_outcomes": [
            {"guard": "CITATION_BINDING", "outcome": "PASSED"},
            {"guard": "UNSUPPORTED_MATERIAL_CLAIM", "outcome": "PASSED"},
        ],
    }


def test_unavailable_provider_attempt_count_has_explicit_class() -> None:
    event = _event()
    unavailable = DecisionTraceEvent(
        trace_id=event.trace_id,
        route=event.route,
        reason_code=event.reason_code,
        compute_tier=ComputeTier.UNAVAILABLE_IN_STAGE1,
        deadline_budget_class=BudgetClass.UNAVAILABLE_IN_STAGE1,
        provider_budget_class=BudgetClass.UNAVAILABLE_IN_STAGE1,
        provider_attempt_count=None,
        context_sources=(ContextSource.UNAVAILABLE_IN_STAGE1,),
        evidence_count=0,
        citation_count=0,
        status_class=StatusClass.UNAVAILABLE_IN_STAGE1,
        safe_abstention_outcome=SafeAbstentionOutcome.UNAVAILABLE_IN_STAGE1,
    )

    assert unavailable.as_dict()["provider_attempt_class"] == "UNAVAILABLE_IN_STAGE1"


def test_trace_disabled_is_inert() -> None:
    emitted: list[DecisionTraceEvent] = []
    flags = M27FeatureFlags()

    result = emit_decision_trace_if_enabled(_event(), flags=flags, sink=emitted.append)

    assert result is False
    assert emitted == []


def test_trace_enabled_emits_only_the_sanitized_event() -> None:
    emitted: list[DecisionTraceEvent] = []
    flags = load_m27_feature_flags(
        environ={M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED: "true"},
        isolated_runtime=True,
    )
    event = _event()

    result = emit_decision_trace_if_enabled(event, flags=flags, sink=emitted.append)

    assert result is True
    assert emitted == [event]
    assert set(event.as_dict()) == {
        "schema_version",
        "trace_id",
        "route",
        "reason_code",
        "compute_tier",
        "deadline_budget_class",
        "provider_budget_class",
        "provider_attempt_count",
        "provider_attempt_class",
        "context_sources",
        "evidence_count",
        "citation_count",
        "status_class",
        "safe_abstention_outcome",
        "guard_outcomes",
    }
