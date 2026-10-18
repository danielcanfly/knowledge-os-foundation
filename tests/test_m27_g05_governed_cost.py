"""Scoped G05 tests: deterministic safety mechanics, NOT real billing or issuer."""

from dataclasses import replace

import pytest

from knowledge_engine.m27_b3_provider_router import FALLBACK, PRIMARY, Failure
from knowledge_engine.m27_g05_governed_cost import (
    ABI,
    BudgetScope,
    CostGovernor,
    GovernedLearning,
    MeterObservation,
    Tariff,
    cost_ablation,
)


def scope(**kw):
    return replace(
        BudgetScope(
            "task-v1",
            "tenant-1",
            "principal-1",
            "sha-source",
            "epoch-1",
            600,
            3,
            10000,
            "0.01",
            True,
        ),
        **kw,
    )


def tariff(**kw):
    return replace(
        Tariff(
            PRIMARY, "fixture-upstream", "v1", "2026-10-17T00:00Z", "0.2", "0.5", True, "a" * 64
        ),
        **kw,
    )


def reserve(g, key="a", **kw):
    data = dict(
        key=key,
        provider=PRIMARY,
        model_id="fixture-upstream",
        tariff=tariff(),
        input_tokens=50,
        output_tokens=20,
        task_sha256="task-v1",
        tenant="tenant-1",
        principal="principal-1",
        source_sha256="sha-source",
        acl_epoch="epoch-1",
        elapsed_ms=200,
    )
    data.update(kw)
    return g.reserve(**data)


def meter(**kw):
    data = dict(
        request_id="r1",
        task_sha256="task-v1",
        tenant="tenant-1",
        principal="principal-1",
        provider=PRIMARY,
        model_id="fixture-upstream",
        attempt=1,
        timestamp="2026-10-17T00:00Z",
        source_revision="sha-source",
        origin="PROVIDER_RESPONSE",
        input_tokens=50,
        output_tokens=20,
        billed_usd=None,
        invoice_verified=False,
        receipt_sha256="b" * 64,
        first_text_ns=1000000000,
        terminal_ns=1150000000,
    )
    data.update(kw)
    return MeterObservation(**data)


def learning():
    engine = GovernedLearning()
    c = engine.draft(
        tenant="tenant-1",
        principal="principal-1",
        source_revision="src-v1",
        evidence_sha256="e" * 64,
        hypothesis_sha256="a" * 64,
        author="author",
    )
    return engine, c


def test_abi_constant():
    assert ABI.startswith("m27.g05")


def test_cost_quote_exact_decimal():
    assert tariff().quote(1000, 1000) == tariff().quote(1000, 1000)
    assert str(tariff().quote(1000, 1000)) == "0.0007"


def test_reserve_snapshot_real_billing_unknown_not_zero():
    g = CostGovernor(scope())
    assert reserve(g).quoted_usd > 0
    g.record("a", meter())
    s = g.snapshot()
    assert s["tokens_reserved"] == 70
    assert s["attempts_reserved"] == 1
    assert s["actual_bill_usd"] is None
    assert s["unknown_bill_count"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"tenant": "tenant-B"},
        {"principal": "other"},
        {"task_sha256": "other"},
        {"source_sha256": "revoked"},
        {"acl_epoch": "old"},
    ],
)
def test_identity_acl_source_fence(change):
    with pytest.raises(PermissionError, match="SCOPE"):
        reserve(CostGovernor(scope()), **change)


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({"tariff": None}, "TARIFF"),
        ({"tariff": tariff(independently_verified=False)}, "UNVERIFIED"),
        ({"model_id": "wrong"}, "TARIFF"),
        ({"elapsed_ms": 10000}, "QUOTA"),
        ({"input_tokens": -1}, "INVALID"),
        ({"output_tokens": 0}, "INVALID"),
    ],
)
def test_reservation_fences(kw, expected):
    with pytest.raises((ValueError, PermissionError), match=expected):
        reserve(CostGovernor(scope()), **kw)


def test_total_token_budget_and_quota():
    g = CostGovernor(scope(max_total_tokens=100, max_attempts=2))
    reserve(g)
    with pytest.raises(PermissionError, match="QUOTA"):
        reserve(g, key="b")
    h = CostGovernor(scope(max_total_tokens=600, max_attempts=1))
    reserve(h)
    with pytest.raises(PermissionError, match="QUOTA"):
        reserve(h, key="b")


def test_money_cap_hard_stop():
    g = CostGovernor(scope(max_reserved_usd="0.000001"))
    with pytest.raises(PermissionError, match="QUOTA"):
        reserve(g)


def test_no_duplicate_meter_or_dispatch():
    g = CostGovernor(scope())
    reserve(g)
    with pytest.raises(ValueError, match="REPLAY"):
        reserve(g)
    g.record("a", meter())
    with pytest.raises(ValueError, match="REPLAY"):
        g.record("a", meter())


def test_cross_tenant_meter_and_unreserved_denied():
    g = CostGovernor(scope())
    reserve(g)
    with pytest.raises(PermissionError, match="CROSS"):
        g.record("a", meter(tenant="tenant-B"))
    with pytest.raises(ValueError, match="MISSING"):
        g.record("z", meter())


@pytest.mark.parametrize(
    "failure",
    [
        Failure.AUTH,
        Failure.ACL,
        Failure.REVOKED,
        Failure.RIGHTS,
        Failure.VERIFIER,
        Failure.OBLIGATION,
        Failure.BUDGET,
        Failure.UNKNOWN,
        Failure.CANCELLED,
    ],
)
def test_illegal_failover(failure):
    g = CostGovernor(scope())
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            g,
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
            fallback_reason=failure,
        )


def test_healthy_primary_never_fallback():
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            CostGovernor(scope()),
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
        )


def test_unconsented_fallback_fails_closed():
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            CostGovernor(scope(fallback_consented=False)),
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
            fallback_reason=Failure.TIMEOUT,
        )


@pytest.mark.parametrize(
    "reason", [Failure.TIMEOUT, Failure.QUOTA, Failure.UPSTREAM_5XX, Failure.CIRCUIT_OPEN]
)
def test_explicit_operational_fallback_can_reserve_fixture_only(reason):
    g = CostGovernor(scope())
    reserve(g, key="primary-witness")
    g.register_primary_operational_failure(
        reservation_key="primary-witness", reason=reason, answer_text_emitted=False
    )
    x = reserve(
        g,
        provider=FALLBACK,
        model_id="fallback-fixture",
        tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
        fallback_reason=reason,
    )
    assert x.provider == FALLBACK


def test_circuit_gate():
    g = CostGovernor(scope())
    with pytest.raises(ValueError, match="INELIGIBLE"):
        g.trip_circuit(PRIMARY, Failure.AUTH)
    g.trip_circuit(PRIMARY, Failure.TIMEOUT)
    with pytest.raises(PermissionError, match="CIRCUIT"):
        reserve(g)


@pytest.mark.parametrize(
    "kw",
    [
        {"input_tokens": -1},
        {"output_tokens": True},
        {"first_text_ns": 3, "terminal_ns": 2},
        {"billed_usd": "-1"},
        {"invoice_verified": True},
    ],
)
def test_usage_meter_rejects_malformed_or_fake_invoice(kw):
    with pytest.raises(ValueError):
        meter(**kw)


def test_monotonic_timing_from_same_clock_only():
    assert meter().latency_ms == 150


def test_provider_reported_tokens_not_invoice():
    m = meter(billed_usd="0.03")
    assert m.actual_bill_usd is None


def test_invoice_positive_needs_explicit_external_truth_flag():
    m = meter(origin="INVOICE", invoice_verified=True, billed_usd="0.002")
    assert str(m.actual_bill_usd) == "0.002"
    g = CostGovernor(scope())
    reserve(g)
    g.record("a", m)
    assert g.snapshot()["actual_bill_usd"] == "0.002"


def test_unknown_one_attempt_makes_whole_total_unknown():
    g = CostGovernor(scope())
    reserve(g)
    reserve(g, key="b")
    g.record("a", meter(origin="INVOICE", invoice_verified=True, billed_usd="0.002"))
    assert g.snapshot()["actual_bill_usd"] is None


def test_ablation_requires_all_modes_and_independent_billing():
    m = meter()
    assert cost_ablation({k: [m] for k in ("OFF", "BYPASS", "REFRESH", "AUTO")})["status"] == "HOLD"
    assert cost_ablation({"OFF": [m]})["status"] == "HOLD"


def test_ablation_requires_same_workload():
    m = meter(origin="INVOICE", invoice_verified=True, billed_usd="0.01")
    s = {k: [m] for k in ("OFF", "BYPASS", "REFRESH", "AUTO")}
    s["AUTO"] = [replace(m, task_sha256="different")]
    assert cost_ablation(s)["reason"] == "NOT_PAIRED_WORKLOADS"


def test_ablation_gated_sample_math_is_not_product_admission():
    m = meter(origin="INVOICE", invoice_verified=True, billed_usd="0.01")
    s = {k: [m] for k in ("OFF", "BYPASS", "REFRESH", "AUTO")}
    s["AUTO"] = [replace(m, billed_usd="0.008")]
    x = cost_ablation(s)
    assert x["status"] == "HOLD"
    assert x["reason"] == "INDEPENDENT_BILLING_ISSUER_AND_WORKLOAD_ADMISSION_MISSING"
    assert x["savings"] is None
    assert x["hypothetical_unadmitted_savings"]["AUTO"] == "0.2"


def test_governed_draft_evaluate_no_automatic_approval():
    engine, c = learning()
    engine.evaluate(
        c,
        evaluator="independent-evaluator",
        result_sha256="b" * 64,
        effect_verified=True,
        negative_safe=True,
    )
    assert c.status == "EVALUATED"
    with pytest.raises(PermissionError, match="APPROVAL"):
        engine.approve_nonprod(
            c,
            reviewer="reviewer",
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            authentic_approval=False,
        )


def test_governed_local_approval_and_rollback_explicitly_nonprod():
    engine, c = learning()
    engine.evaluate(
        c, evaluator="evaluator", result_sha256="b" * 64, effect_verified=True, negative_safe=True
    )
    engine.approve_nonprod(
        c,
        reviewer="reviewer",
        tenant="tenant-1",
        principal="principal-1",
        source_revision="src-v1",
        authentic_approval=True,
    )
    assert c.status == "NONPROD_APPROVED"
    engine.rollback(c, tenant="tenant-1", principal="principal-1")
    assert c.status == "ROLLED_BACK"
    assert c.approved_revision is None
    with pytest.raises(PermissionError):
        engine.approve_nonprod(
            c,
            reviewer="another",
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            authentic_approval=True,
        )


@pytest.mark.parametrize("evaluator", ["author"])
def test_learning_self_evaluation_denied(evaluator):
    engine, c = learning()
    with pytest.raises(PermissionError, match="INDEPENDENT"):
        engine.evaluate(
            c, evaluator=evaluator, result_sha256="a" * 64, effect_verified=True, negative_safe=True
        )


@pytest.mark.parametrize("verified,safe", [(False, True), (True, False), (False, False)])
def test_learning_false_improvement_or_false_safe_rejected(verified, safe):
    engine, c = learning()
    engine.evaluate(
        c,
        evaluator="evaluator",
        result_sha256="b" * 64,
        effect_verified=verified,
        negative_safe=safe,
    )
    assert c.status == "REJECTED"


def test_learning_replayed_evaluation_and_draft_denied():
    engine, c = learning()
    with pytest.raises(PermissionError, match="DUPLICATE"):
        learning_args = dict(
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            evidence_sha256="e" * 64,
            hypothesis_sha256="a" * 64,
            author="author",
        )
        engine.draft(**learning_args)
    engine.evaluate(
        c, evaluator="evaluator", result_sha256="b" * 64, effect_verified=True, negative_safe=True
    )
    with pytest.raises(PermissionError):
        engine.evaluate(
            c,
            evaluator="evaluator-2",
            result_sha256="c" * 64,
            effect_verified=True,
            negative_safe=True,
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"reviewer": "author"},
        {"reviewer": "evaluator"},
        {"tenant": "other"},
        {"principal": "other"},
        {"source_revision": "stale"},
    ],
)
def test_learning_independence_tenant_source_denied(bad):
    engine, c = learning()
    engine.evaluate(
        c, evaluator="evaluator", result_sha256="b" * 64, effect_verified=True, negative_safe=True
    )
    args = dict(
        reviewer="reviewer",
        tenant="tenant-1",
        principal="principal-1",
        source_revision="src-v1",
        authentic_approval=True,
    )
    args.update(bad)
    with pytest.raises(PermissionError):
        engine.approve_nonprod(c, **args)


def test_revoke_source_fences_restoration():
    engine, c = learning()
    engine.evaluate(
        c, evaluator="evaluator", result_sha256="b" * 64, effect_verified=True, negative_safe=True
    )
    engine.revoke_source("src-v1")
    assert c.status == "SOURCE_REVOKED"
    with pytest.raises(PermissionError):
        engine.approve_nonprod(
            c,
            reviewer="reviewer",
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            authentic_approval=True,
        )
    with pytest.raises(PermissionError):
        engine.draft(
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            evidence_sha256="d" * 64,
            hypothesis_sha256="a" * 64,
            author="author",
        )


def test_autoproduction_always_denied():
    engine, c = learning()
    with pytest.raises(PermissionError, match="NEVER_AUTO"):
        engine.promote_production(c)


def test_learning_raw_content_or_forged_digest_rejected():
    engine = GovernedLearning()
    with pytest.raises(ValueError, match="DIGEST"):
        engine.draft(
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v2",
            evidence_sha256="raw secret payload",
            hypothesis_sha256="a" * 64,
            author="author",
        )


def test_actual_failover_reserved_extra_tokens_and_cost_not_bill():
    g = CostGovernor(scope())
    reserve(g, key="primary-failed")
    g.register_primary_operational_failure(
        reservation_key="primary-failed", reason=Failure.UPSTREAM_5XX, answer_text_emitted=False
    )
    reserve(
        g,
        key="fallback-attempt",
        provider=FALLBACK,
        model_id="fallback-fixture",
        tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
        fallback_reason=Failure.UPSTREAM_5XX,
    )
    s = g.snapshot()
    assert s["attempts_reserved"] == 2
    assert s["tokens_reserved"] == 140
    assert s["quoted_usd"] == "0.00004"
    assert s["reserved_quote_by_provider_usd"][FALLBACK] == "0.00002"
    assert s["actual_bill_usd"] is None


def test_concurrent_budget_reserve_cannot_exceed_cap():
    from concurrent.futures import ThreadPoolExecutor

    g = CostGovernor(scope(max_attempts=1))

    def attempt(i):
        try:
            reserve(g, key="parallel-" + str(i))
            return True
        except PermissionError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(attempt, range(16)))
    assert sum(result) == 1
    assert g.snapshot()["attempts_reserved"] == 1


def test_independent_invoice_overrun_fences_new_spend():
    g = CostGovernor(scope())
    reserve(g)
    g.record("a", meter(origin="INVOICE", invoice_verified=True, billed_usd="0.002"))
    assert g.snapshot()["invoice_overrun_hold"] is True
    with pytest.raises(PermissionError, match="UNRECONCILED"):
        reserve(g, key="after-overrun")


def test_request_first_answer_terminal_same_clock_latencies():
    m = meter(request_start_ns=900000000)
    assert m.first_text_latency_ms == 100
    assert m.latency_ms == 150
    assert m.request_latency_ms == 250
    with pytest.raises(ValueError, match="ORDER"):
        meter(request_start_ns=1200000000)


def test_observed_provider_model_and_source_version_must_match_quote():
    g = CostGovernor(scope())
    reserve(g)
    with pytest.raises(PermissionError, match="CROSS_SCOPE"):
        g.record("a", meter(model_id="unexpected-model"))
    with pytest.raises(PermissionError, match="CROSS_SCOPE"):
        g.record("a", meter(source_revision="different-source"))
    assert g.snapshot()["actual_bill_usd"] is None


def test_reported_tokens_above_reserved_budget_halts_new_spend():
    g = CostGovernor(scope())
    reserve(g)
    g.record("a", meter(input_tokens=500, output_tokens=200))
    assert g.snapshot()["invoice_overrun_hold"]
    with pytest.raises(PermissionError, match="UNRECONCILED"):
        reserve(g, key="second")


def test_negative_token_quote_never_gets_negative_cost():
    with pytest.raises(ValueError, match="INVALID_TOKEN_QUOTE"):
        tariff().quote(-100, 50)


def test_ablation_rejects_unpaired_model_or_source():
    m = meter(origin="INVOICE", invoice_verified=True, billed_usd="0.01")
    s = {k: [m] for k in ("OFF", "BYPASS", "REFRESH", "AUTO")}
    s["AUTO"] = [replace(m, model_id="other")]
    assert cost_ablation(s)["reason"] == "NOT_PAIRED_WORKLOADS"
    s["AUTO"] = [replace(m, source_revision="other")]
    assert cost_ablation(s)["reason"] == "NOT_PAIRED_WORKLOADS"


def test_learning_rejects_forged_candidate_object():
    from knowledge_engine.m27_g05_governed_cost import LearningCandidate

    eng, c = learning()
    forgery = replace(c, status="EVALUATED")
    assert type(forgery) is LearningCandidate
    with pytest.raises(PermissionError, match="FORGED"):
        eng.approve_nonprod(
            forgery,
            reviewer="reviewer",
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            authentic_approval=True,
        )


def test_learning_detects_mutated_status_history_and_evidence():
    eng, c = learning()
    c.status = "EVALUATED"
    with pytest.raises(PermissionError, match="TAMPERED"):
        eng.approve_nonprod(
            c,
            reviewer="reviewer",
            tenant="tenant-1",
            principal="principal-1",
            source_revision="src-v1",
            authentic_approval=True,
        )
    eng2, c2 = learning()
    c2.history.append("UNAUTHORIZED")
    with pytest.raises(PermissionError, match="TAMPERED"):
        eng2.evaluate(
            c2,
            evaluator="independent",
            result_sha256="b" * 64,
            effect_verified=True,
            negative_safe=True,
        )
    eng3, c3 = learning()
    c3.evidence_sha256 = "f" * 64
    with pytest.raises(PermissionError, match="TAMPERED"):
        eng3.evaluate(
            c3,
            evaluator="independent",
            result_sha256="b" * 64,
            effect_verified=True,
            negative_safe=True,
        )


def test_self_asserted_timeout_cannot_route_to_fallback():
    g = CostGovernor(scope())
    reserve(g, key="real-primary-not-failed")
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            g,
            key="self-asserted",
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
            fallback_reason=Failure.TIMEOUT,
        )


def test_primary_failure_receipt_must_match_reason():
    g = CostGovernor(scope())
    reserve(g, key="primary")
    g.register_primary_operational_failure(
        reservation_key="primary",
        reason=Failure.UPSTREAM_5XX,
        answer_text_emitted=False,
    )
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            g,
            key="wrong-reason",
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
            fallback_reason=Failure.QUOTA,
        )


def test_primary_failure_after_any_published_text_must_not_failover():
    g = CostGovernor(scope())
    reserve(g, key="primary")
    with pytest.raises(PermissionError, match="PRIMARY_FAILURE"):
        g.register_primary_operational_failure(
            reservation_key="primary",
            reason=Failure.TIMEOUT,
            answer_text_emitted=True,
        )
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            g,
            key="forged-fallback",
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
            fallback_reason=Failure.TIMEOUT,
        )


def test_primary_failure_receipt_cannot_be_replayed_or_faked():
    g = CostGovernor(scope(max_attempts=4))
    with pytest.raises(PermissionError, match="PRIMARY_FAILURE"):
        g.register_primary_operational_failure(
            reservation_key="no-such-primary",
            reason=Failure.TIMEOUT,
            answer_text_emitted=False,
        )
    reserve(g, key="primary")
    with pytest.raises(PermissionError, match="PRIMARY_FAILURE"):
        g.register_primary_operational_failure(
            reservation_key="primary",
            reason=Failure.AUTH,
            answer_text_emitted=False,
        )
    g.register_primary_operational_failure(
        reservation_key="primary",
        reason=Failure.TIMEOUT,
        answer_text_emitted=False,
    )
    with pytest.raises(PermissionError, match="PRIMARY_FAILURE"):
        g.register_primary_operational_failure(
            reservation_key="primary",
            reason=Failure.TIMEOUT,
            answer_text_emitted=False,
        )
    reserve(
        g,
        key="fallback",
        provider=FALLBACK,
        model_id="fallback-fixture",
        tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
        fallback_reason=Failure.TIMEOUT,
    )
    with pytest.raises(PermissionError, match="ILLEGAL"):
        reserve(
            g,
            key="fallback-repeat",
            provider=FALLBACK,
            model_id="fallback-fixture",
            tariff=tariff(provider=FALLBACK, model_id="fallback-fixture"),
            fallback_reason=Failure.TIMEOUT,
        )
