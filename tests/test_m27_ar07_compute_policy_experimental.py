"""C07 offline mock-only AR07 policy adversaries; no provider, tooling or network."""

import pytest

from knowledge_engine.m27_ar07_compute_policy_experimental import (
    ComputeDecisionInput,
    MockAblationCase,
    PriceSnapshotFixture,
    ProviderCatalogFixture,
    StreamFrameFixture,
    mock_ablation,
    propose_compute,
)


def base(**changes):
    item = dict(
        tenant_id="tenant-fixture",
        task_id="task-fixture",
        run_id="run-fixture",
        task_version=1,
        lease_epoch=4,
        workload_kind="QA-I",
        phase="generation",
        now_ms=100,
        deadline_at_ms=14000,
        residency="TW",
        privacy_class="restricted",
        currency="MICROUSD",
        approved_providers=("provider-allowed",),
        source_revision="r1",
        authorized_revision="r1",
        source_grant_valid=True,
        source_expires_at_ms=20000,
        context_expires_at_ms=20000,
        budget_version=9,
        max_cost_microunits=100,
        spent_cost_microunits=0,
        reserved_cost_microunits=0,
        max_tokens=100,
        spent_tokens=0,
        reserved_tokens=0,
        max_wall_ms=12000,
        spent_wall_ms=0,
        reserved_wall_ms=0,
        max_tool_calls=0,
        spent_tool_calls=0,
        reserved_tool_calls=0,
        max_attempts=3,
        attempts_used=0,
        max_retries=1,
        retry_index=0,
        request_tokens=10,
        request_wall_ms=1000,
        request_tool_calls=0,
        qa_verification_reserve_ms=3000,
        retrieval_depth=0,
        max_retrieval_depth=1,
        reflection_steps=0,
        max_reflection_steps=1,
        agent_count=1,
        max_agent_count=2,
        failure_class=None,
        cancelled=False,
        unknown_effect=False,
        billing_uncertain=False,
        late_billing_overrun=False,
        actual_cost_microunits=None,
        expected_marginal_value=0,
        verified_stream_frame=None,
    )
    item.update(changes)
    return ComputeDecisionInput(**item)


def catalog(**changes):
    d = dict(
        route_id="r-approved",
        provider_id="provider-allowed",
        model_id="model-mock",
        model_version="v1",
        supported_workloads=("QA-I", "RES-L", "CODE-L"),
        residencies=("TW",),
        privacy_classes=("restricted",),
        available=True,
        observed_at_ms=90,
        expires_at_ms=3000,
        max_request_tokens=500,
        supports_verified_citations=True,
    )
    d.update(changes)
    return ProviderCatalogFixture(**d)


def price(**changes):
    d = dict(
        snapshot_id="price-fixture-1",
        provider_id="provider-allowed",
        model_id="model-mock",
        model_version="v1",
        currency="MICROUSD",
        cost_per_token_microunits=2,
        observed_at_ms=90,
        expires_at_ms=3000,
        trusted_fixture=True,
    )
    d.update(changes)
    return PriceSnapshotFixture(**d)


def decision(inp=None, providers=None, prices=None):
    return propose_compute(
        base() if inp is None else inp,
        (catalog(),) if providers is None else providers,
        (price(),) if prices is None else prices,
    )


def assert_deny(result, reason):
    assert result.status in {"DENY", "STOP", "PAUSE", "ABSTAIN"}
    assert reason in result.trace.reason_codes
    assert result.provider_call_authorized is False
    assert result.required_owner_action is None
    assert result.trace.no_external_effect is True


def test_positive_qa_requires_ar02_cas_and_never_authorizes_call():
    result = decision()
    assert result.status == "RESERVATION_REQUIRED"
    assert result.required_owner_action == "AR02_CAS_RESERVE"
    assert result.provider_call_authorized is False
    assert result.reservation_cost_microunits == 20
    assert result.reservation_tokens == 10
    assert result.trace.budget_version == 9
    assert result.trace.price_snapshot_id == "price-fixture-1"
    assert result.trace.model_version == "v1"
    assert result.trace.verified_first_answer_preterminal is False
    assert result.trace.actual_cost_status == "UNKNOWN"
    assert not result.trace.economically_certified


def test_b01_zero_cost_denied_even_huge_marginal_utility():
    assert_deny(
        decision(base(max_cost_microunits=0, expected_marginal_value=10**18)), "COST_CEILING"
    )


def test_b02_zero_token_and_cheap_provider_denied():
    assert_deny(decision(base(max_tokens=0)), "TOKEN_CEILING")


def test_b03_inclusive_ceiling_exact_and_one_over():
    assert decision(base(max_cost_microunits=20)).status == "RESERVATION_REQUIRED"
    assert_deny(decision(base(max_cost_microunits=19)), "COST_CEILING")
    assert_deny(
        decision(base(spent_cost_microunits=79, reserved_cost_microunits=2)), "COST_CEILING"
    )


def test_b04_two_concurrent_reservations_are_never_granted_by_planner():
    first = decision(base(max_cost_microunits=100, request_tokens=30))
    second = decision(base(max_cost_microunits=100, request_tokens=30))
    assert first.status == second.status == "RESERVATION_REQUIRED"
    assert first.trace.budget_version == second.trace.budget_version == 9
    assert not first.provider_call_authorized and not second.provider_call_authorized
    # Only the owning AR02 writer may settle first CAS and advance its version.
    assert_deny(
        decision(
            base(
                max_cost_microunits=100,
                request_tokens=30,
                reserved_cost_microunits=60,
                budget_version=10,
            )
        ),
        "COST_CEILING",
    )


def test_b05_retry_and_attempt_exhaustion():
    assert_deny(decision(base(attempts_used=3)), "ATTEMPTS_EXHAUSTED")
    assert_deny(
        decision(
            base(attempts_used=2, retry_index=2, failure_class="transient_provider_unavailable")
        ),
        "RETRY_EXHAUSTED",
    )
    assert (
        decision(
            base(attempts_used=1, retry_index=1, failure_class="timeout_before_dispatch")
        ).status
        == "RESERVATION_REQUIRED"
    )


def test_b06_untyped_or_non_retry_safe_timeouts_block():
    assert_deny(
        decision(base(attempts_used=1, retry_index=1, failure_class="invalid_response")),
        "RETRY_NOT_SAFE",
    )
    assert_deny(
        decision(base(attempts_used=1, retry_index=1, failure_class=None)), "RETRY_NOT_SAFE"
    )


def test_b07_possible_effect_timeout_requires_reconciliation():
    assert_deny(
        decision(base(failure_class="timeout_after_possible_dispatch", retry_index=1)),
        "UNKNOWN_EFFECT_RECONCILE",
    )
    assert_deny(decision(base(unknown_effect=True)), "UNKNOWN_EFFECT_RECONCILE")


def test_b08_late_billing_overrun_cannot_be_ignored_or_refunded():
    out = decision(base(late_billing_overrun=True, actual_cost_microunits=101))
    assert_deny(out, "LATE_BILLING_OVERRUN")
    assert out.trace.actual_cost_status == "OBSERVED_NOT_SETTLED"
    assert out.trace.actual_cost_microunits == 101


def test_b09_missing_invoice_is_unknown_not_zero():
    out = decision()
    assert out.trace.actual_cost_status == "UNKNOWN"
    assert out.trace.actual_cost_microunits is None
    assert_deny(decision(base(billing_uncertain=True)), "BILLING_UNCERTAIN")
    assert_deny(decision(base(actual_cost_microunits=-1)), "BILLING_UNCERTAIN")


def test_b10_price_stale_missing_untrusted_and_version_mismatch_denied():
    assert_deny(decision(prices=()), "NO_VALID_PRICE")
    assert_deny(decision(prices=(price(expires_at_ms=100),)), "NO_VALID_PRICE")
    assert_deny(decision(prices=(price(trusted_fixture=False),)), "NO_VALID_PRICE")
    assert_deny(decision(prices=(price(model_version="v2"),)), "NO_VALID_PRICE")
    assert_deny(decision(base(currency="INR")), "NO_VALID_PRICE")
    assert_deny(
        decision(base(expected_marginal_value=10**18), prices=(price(expires_at_ms=99),)),
        "NO_VALID_PRICE",
    )


def test_context_grant_revision_and_expiry_fail_closed():
    for changes in (
        {"source_grant_valid": False},
        {"source_revision": "r2"},
        {"source_expires_at_ms": 100},
        {"context_expires_at_ms": 100},
    ):
        assert_deny(decision(base(**changes)), "CONTEXT_STALE_OR_UNAUTHORIZED")


def test_tenant_residency_privacy_and_version_are_filters_first():
    assert_deny(decision(base(approved_providers=())), "NO_ELIGIBLE_ROUTE")
    assert_deny(decision(providers=(catalog(residencies=("US",)),)), "NO_ELIGIBLE_ROUTE")
    assert_deny(decision(providers=(catalog(privacy_classes=("public",)),)), "NO_ELIGIBLE_ROUTE")
    assert_deny(decision(providers=(catalog(model_version="other"),)), "NO_VALID_PRICE")
    assert_deny(decision(providers=(catalog(available=False),)), "NO_ELIGIBLE_ROUTE")
    assert_deny(decision(providers=(catalog(expires_at_ms=100),)), "NO_ELIGIBLE_ROUTE")


def test_fallback_cannot_cross_privacy_boundary_even_if_first_unavailable():
    bad = catalog(
        route_id="alternate", provider_id="unapproved", available=True, residencies=("US",)
    )
    out = decision(providers=(catalog(available=False), bad))
    assert_deny(out, "NO_ELIGIBLE_ROUTE")
    assert out.trace.rejected_routes


def test_qa_is_distinct_from_long_task_and_preserves_verifier_wall_reserve():
    assert_deny(decision(base(request_wall_ms=9001)), "QA_VERIFICATION_RESERVE")
    assert (
        decision(base(workload_kind="RES-L", request_wall_ms=9001)).status == "RESERVATION_REQUIRED"
    )
    assert_deny(decision(base(qa_verification_reserve_ms=0)), "QA_VERIFICATION_RESERVE")
    assert (
        decision(base(workload_kind="CODE-L", request_wall_ms=2000)).status
        == "RESERVATION_REQUIRED"
    )


def test_verified_first_answer_only_preterminal_with_pinned_citation():
    for frame in (
        StreamFrameFixture(True, True, False, True),
        StreamFrameFixture(True, True, True, False),
        StreamFrameFixture(False, True, True, True),
        StreamFrameFixture(True, False, True, True),
    ):
        assert not decision(
            base(verified_stream_frame=frame)
        ).trace.verified_first_answer_preterminal
    good = StreamFrameFixture(True, True, True, True)
    assert decision(base(verified_stream_frame=good)).trace.verified_first_answer_preterminal


def test_cancel_deadline_wall_and_tool_reservations():
    assert_deny(decision(base(cancelled=True)), "CANCELLED")
    assert_deny(decision(base(deadline_at_ms=100)), "DEADLINE_EXPIRED")
    assert_deny(decision(base(max_wall_ms=100)), "WALL_CEILING")
    assert_deny(decision(base(request_tool_calls=1)), "TOOL_CEILING")
    assert_deny(decision(base(request_tool_calls=1, max_tool_calls=1)), "AR04_PERMIT_REQUIRED")


def test_no_unbounded_reflection_retrieval_agents_or_fanout():
    assert_deny(decision(base(retrieval_depth=2)), "EXPANSION_CAP")
    assert_deny(decision(base(reflection_steps=2)), "EXPANSION_CAP")
    assert_deny(decision(base(agent_count=3)), "EXPANSION_CAP")
    assert (
        decision(
            base(workload_kind="RES-L", agent_count=2, request_tokens=10)
        ).reservation_cost_microunits
        == 40
    )
    assert_deny(decision(base(agent_count=2, max_cost_microunits=39)), "COST_CEILING")
    assert_deny(decision(base(agent_count=0)), "EXPANSION_CAP")


def test_budget_arithmetic_rejects_negative_malformed_and_unknown_workload():
    assert_deny(decision(base(spent_tokens=-1)), "INVALID_BUDGET")
    assert_deny(decision(base(reserved_cost_microunits=-1)), "INVALID_BUDGET")
    assert_deny(decision(base(request_tokens=0)), "INVALID_REQUEST")
    assert_deny(decision(base(workload_kind="invalid")), "UNKNOWN_WORKLOAD")
    assert_deny(decision(base(lease_epoch=-1)), "INVALID_IDENTITY")
    assert_deny(decision(base(max_attempts=0)), "ATTEMPTS_EXHAUSTED")


def test_actual_cost_is_observation_not_planner_authority():
    out = decision(base(actual_cost_microunits=23))
    assert out.status == "RESERVATION_REQUIRED"
    assert out.trace.actual_cost_status == "OBSERVED_NOT_SETTLED"
    assert out.trace.actual_cost_microunits == 23
    assert not out.trace.economically_certified


def test_redaction_no_prompt_secret_holdout_labels_in_trace():
    out = decision(base(task_id="task-fixture"))
    serialized = repr(out.trace).lower()
    for disallowed in ("password", "secret_key", "prompt_text", "holdout_label"):
        assert disallowed not in serialized


def test_synthetic_ablation_no_performance_claim_or_zero_denominator():
    cases = (
        MockAblationCase("S-QA-1", "QA-I", "simple", 10, 200, True),
        MockAblationCase("S-QA-1", "QA-I", "adaptive", 30, 300, True),
        MockAblationCase("S-QA-2", "QA-I", "simple", 10, 200, False),
        MockAblationCase("S-QA-2", "QA-I", "adaptive", 20, 400, False),
        MockAblationCase("S-RES-1", "RES-L", "simple", 40, 1200, False),
        MockAblationCase("S-RES-1", "RES-L", "adaptive", 50, 1100, False),
    )
    result = mock_ablation(cases)
    assert result["status"] == "SYNTHETIC_ONLY_NO_PERFORMANCE_CLAIM"
    assert result["QA-I"]["simple"]["accepted"] == 1
    assert result["QA-I"]["simple"]["total_cost"] == 20
    assert result["QA-I"]["adaptive"]["cost_per_accepted"] == 50
    assert result["RES-L"]["simple"]["cost_per_accepted"] is None
    assert result["RES-L"]["adaptive"]["cost_per_accepted"] is None
    assert result["QA-I"]["simple"]["count"] == 2
    assert result["QA-I"]["mock_pareto"] == "simple_dominates_fixture"
    assert result["RES-L"]["mock_pareto"] == "no_fixture_dominance"
    with pytest.raises(ValueError, match="paired"):
        mock_ablation((MockAblationCase("unpaired", "QA-I", "simple", 1, 1, True),))
    with pytest.raises(ValueError, match="Duplicate"):
        mock_ablation(
            (
                MockAblationCase("duplicate", "QA-I", "simple", 1, 1, True),
                MockAblationCase("duplicate", "QA-I", "simple", 1, 1, True),
            )
        )


@pytest.mark.parametrize(
    "malformed",
    [
        {"request_wall_ms": -1},
        {"max_cost_microunits": -1},
        {"max_tokens": -1},
        {"reserved_wall_ms": -1},
        {"max_tool_calls": -1},
        {"attempts_used": -1},
    ],
)
def test_negative_numbers_never_produce_reservation(malformed):
    assert_deny(decision(base(**malformed)), "INVALID_BUDGET")
