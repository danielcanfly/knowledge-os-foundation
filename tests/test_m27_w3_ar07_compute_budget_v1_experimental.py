"""W3 C07I: independent executable SQLite fixture and failure-injection oracle.

All invoices, model prices, entitlements and Provider catalogs are invented;
no real Provider or model run is permitted.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    RunIdentity,
)
from knowledge_engine.m27_ar07_compute_policy_experimental import (
    ComputeDecisionInput,
    PriceSnapshotFixture,
    ProviderCatalogFixture,
    StreamFrameFixture,
)
from knowledge_engine.m27_w3_ar07_compute_budget_v1_experimental import (
    PASS,
    Attempt,
    BudgetFence,
    InvoiceFixture,
    LocalComputeBudget,
)


def make(tmp_path, *, workload="QA-I", budget=100, fixture_mode=True):
    identity = RunIdentity("tenantA", "runA", "taskA", 1, "principalA")
    writer = DurableWriterV1(
        tmp_path / "w3_compute.sqlite3", fixture_approval_mode=fixture_mode
    )
    head = writer.create_run(
        identity, budget=budget, source_revision="rev1",
        consent_generation=1, exclusion_generation=0,
    )
    item = ComputeDecisionInput(
        tenant_id=identity.tenant_id, task_id=identity.task_id,
        run_id=identity.run_id, task_version=identity.task_version,
        lease_epoch=head.epoch, workload_kind=workload, phase="generation",
        now_ms=100, deadline_at_ms=14000, residency="TW",
        privacy_class="restricted", currency="MICROUSD",
        approved_providers=("local-fixture",), source_revision="rev1",
        authorized_revision="rev1", source_grant_valid=True,
        source_expires_at_ms=20000, context_expires_at_ms=20000,
        budget_version=head.seq, max_cost_microunits=budget,
        spent_cost_microunits=0, reserved_cost_microunits=0,
        max_tokens=100, spent_tokens=0, reserved_tokens=0,
        max_wall_ms=12000, spent_wall_ms=0, reserved_wall_ms=0,
        max_tool_calls=0, spent_tool_calls=0, reserved_tool_calls=0,
        max_attempts=3, attempts_used=0, max_retries=1, retry_index=0,
        request_tokens=10, request_wall_ms=1000, request_tool_calls=0,
        qa_verification_reserve_ms=3000, retrieval_depth=0,
        max_retrieval_depth=2, reflection_steps=0, max_reflection_steps=1,
        agent_count=1, max_agent_count=2, failure_class=None,
        cancelled=False, unknown_effect=False, billing_uncertain=False,
        late_billing_overrun=False, actual_cost_microunits=None,
        expected_marginal_value=0, verified_stream_frame=None,
    )
    route = ProviderCatalogFixture(
        "local-route", "local-fixture", "fake-model", "v1",
        ("QA-I", "RES-L", "CODE-L"), ("TW",), ("restricted",),
        True, 90, 3000, 1000, True,
    )
    price = PriceSnapshotFixture(
        "fixture-price", "local-fixture", "fake-model", "v1",
        "MICROUSD", 2, 90, 3000, True,
    )
    attempt = Attempt(
        identity, head, item, (route,), (price,), "fixture-price", 1, 0,
        "request-one", "reserve-one", "approval-one", "intent-one", "claim-one",
    )
    port = LocalComputeBudget(writer) if fixture_mode else None
    return writer, port, attempt


def invoice(**changes):
    payload = {
        "usage_id": "usage-one", "snapshot_id": "fixture-price",
        "model_version": "v1", "currency": "MICROUSD",
        "source_revision": "rev1", "consent_generation": 1,
        "actual_cost_microunits": 18, "actual_tokens": 9,
        "evidence_ref": "mock-receipt-one",
    }
    payload.update(changes)
    return InvoiceFixture(**payload)


def assert_closed(port, attempt, code=None):
    with pytest.raises((BudgetFence, FenceError)) as exc:
        port.reserve_and_fence(attempt)
    if code is not None:
        assert code in str(exc.value)


@pytest.mark.parametrize("workload", ["QA-I", "RES-L", "CODE-L"])
def test_positive_durable_reserve_spent_fresh_connection(tmp_path, workload):
    writer, port, a = make(tmp_path, workload=workload)
    out = port.reserve_and_fence(a)
    assert out.status == "RESERVED_FENCED_NO_PROVIDER"
    assert out.head.reserved == 20
    assert out.head.spent == 0
    assert not out.provider_calls and not out.client_delivered
    assert writer.recover(a.identity)["outbox"][0]["state"] == "POSSIBLY_SENT"

    reopened = LocalComputeBudget(
        DurableWriterV1(writer.path, fixture_approval_mode=True)
    )
    before = reopened.recover(a.identity, a.request_key)
    assert before.status == "RECOVERY_PAUSE_NO_RETRY"
    assert before.head.reserved == 20
    result = reopened.settle(a.identity, a.request_key, invoice(), charge_id="charge-one")
    assert result.status == PASS
    assert result.head.reserved == 0
    assert result.head.spent == 18
    durable = LocalComputeBudget(
        DurableWriterV1(writer.path, fixture_approval_mode=True)
    ).recover(a.identity, a.request_key)
    assert durable.status == PASS
    assert durable.corrected_spent_microunits == 18
    assert not durable.economically_certified and durable.provider_calls == 0


def test_qa_separate_verification_wall_and_no_stream_delivery(tmp_path):
    _, port, a = make(tmp_path)
    no_preterminal = replace(
        a.decision_input,
        verified_stream_frame=StreamFrameFixture(True, True, True, True),
    )
    # A policy-observed synthetic frame is never delivered as a client frame.
    out = port.reserve_and_fence(replace(a, decision_input=no_preterminal))
    assert out.client_delivered is False
    assert out.provider_calls == 0


def test_research_accepts_wall_unaffordable_for_qa(tmp_path):
    _, port, a = make(tmp_path, workload="RES-L")
    a = replace(a, decision_input=replace(a.decision_input, request_wall_ms=9001))
    assert port.reserve_and_fence(a).status == "RESERVED_FENCED_NO_PROVIDER"


def test_qa_wall_verifier_budget_is_preserved(tmp_path):
    _, port, a = make(tmp_path)
    a = replace(a, decision_input=replace(a.decision_input, request_wall_ms=9001))
    assert_closed(port, a, "QA_VERIFICATION_RESERVE")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("tenant_id", "other", "IDENTITY_OR_LEASE_MISMATCH"),
        ("task_id", "other", "IDENTITY_OR_LEASE_MISMATCH"),
        ("run_id", "other", "IDENTITY_OR_LEASE_MISMATCH"),
        ("task_version", 9, "IDENTITY_OR_LEASE_MISMATCH"),
        ("lease_epoch", 2, "IDENTITY_OR_LEASE_MISMATCH"),
        ("budget_version", 0, "STALE_BUDGET_CAS"),
        ("max_cost_microunits", 101, "STALE_BUDGET_CAS"),
        ("spent_cost_microunits", 1, "STALE_BUDGET_CAS"),
        ("reserved_cost_microunits", 1, "STALE_BUDGET_CAS"),
        ("source_revision", "other", "SOURCE_CONSENT_OR_ACL_DRIFT"),
        ("authorized_revision", "other", "SOURCE_CONSENT_OR_ACL_DRIFT"),
        ("source_grant_valid", False, "CONTEXT_STALE_OR_UNAUTHORIZED"),
        ("cancelled", True, "CANCELLED"),
        ("billing_uncertain", True, "BILLING_UNCERTAIN"),
        ("late_billing_overrun", True, "LATE_BILLING_OVERRUN"),
        ("unknown_effect", True, "UNKNOWN_EFFECT_RECONCILE"),
        ("deadline_at_ms", 99, "DEADLINE_EXPIRED"),
        ("max_tokens", 9, "TOKEN_CEILING"),
        ("request_tool_calls", 1, "TOOL_CEILING"),
        ("retry_index", 2, "RETRY_EXHAUSTED"),
        ("residency", "US", "NO_ELIGIBLE_ROUTE"),
        ("currency", "EUR", "NO_VALID_PRICE"),
        ("source_expires_at_ms", 99, "CONTEXT_STALE_OR_UNAUTHORIZED"),
        ("context_expires_at_ms", 99, "CONTEXT_STALE_OR_UNAUTHORIZED"),
    ],
)
def test_adversarial_policy_or_cas_binding(tmp_path, field, value, error):
    _, port, a = make(tmp_path)
    a = replace(a, decision_input=replace(a.decision_input, **{field: value}))
    assert_closed(port, a, error)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trusted_fixture", False),
        ("model_version", "new-revision"),
        ("currency", "INR"),
        ("expires_at_ms", 100),
        ("cost_per_token_microunits", 0),
        ("provider_id", "fake-elsewhere"),
    ],
)
def test_price_snapshot_untrusted_or_drifted(tmp_path, field, value):
    _, port, a = make(tmp_path)
    bad = replace(a.prices[0], **{field: value})
    assert_closed(port, replace(a, prices=(bad,)), "POLICY_NO_VALID_PRICE")


def test_price_snapshot_missing_and_ambiguous(tmp_path):
    _, port, a = make(tmp_path)
    assert_closed(port, replace(a, prices=()), "POLICY_NO_VALID_PRICE")
    assert_closed(port, replace(a, prices=(a.prices[0], a.prices[0])),
                  "UNKNOWN_OR_AMBIGUOUS_PRICE_SNAPSHOT")
    assert_closed(port, replace(a, snapshot_id="arbitrary"),
                  "UNKNOWN_OR_AMBIGUOUS_PRICE_SNAPSHOT")


@pytest.mark.parametrize("field", ["consent_generation", "exclusion_generation"])
def test_consent_exclusion_fenced(tmp_path, field):
    _, port, a = make(tmp_path)
    assert_closed(port, replace(a, **{field: 9}), "SOURCE_CONSENT_OR_ACL_DRIFT")


def test_revision_acl_drift_in_journal(tmp_path):
    writer, port, a = make(tmp_path)
    writer.update_authority(
        a.identity, a.head, source_revision="new",
        consent_generation=2, exclusion_generation=1,
    )
    assert_closed(port, a, "STALE_BUDGET_CAS")


def test_revocation_denies_even_consistent_new_head(tmp_path):
    writer, port, a = make(tmp_path)
    head = writer.update_authority(
        a.identity, a.head, source_revision="rev1",
        consent_generation=1, exclusion_generation=0, revoked=True,
    )
    patched = replace(
        a, head=head,
        decision_input=replace(a.decision_input, budget_version=head.seq),
    )
    assert_closed(port, patched, "REVOKED_OR_TERMINAL")


def test_epoch_takeover_old_head_fenced(tmp_path):
    writer, port, a = make(tmp_path)
    writer.takeover(a.identity, a.head)
    assert_closed(port, a, "STALE_BUDGET_CAS")


def test_concurrent_positive_proposals_only_one_reservation(tmp_path):
    writer, port, a = make(tmp_path, budget=20)
    b = replace(
        a, request_key="request-two", reserve_id="reserve-two",
        approval_id="approval-two", intent_id="intent-two", claim_id="claim-two",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(port.reserve_and_fence, proposal)
            for proposal in (a, b)
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except (BudgetFence, FenceError):
                continue
    assert len(results) == 1
    assert results[0].head.reserved == 20
    fresh = DurableWriterV1(writer.path, fixture_approval_mode=True)
    assert fresh.read_head(a.identity).reserved == 20
    assert fresh.read_head(a.identity).spent == 0


def test_retry_duplicate_request_does_not_double_spend(tmp_path):
    writer, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    assert_closed(port, a, "STALE_BUDGET_CAS")
    assert writer.read_head(a.identity).reserved == 20


@pytest.mark.parametrize(
    "stage", [
        "after_reserve", "after_approval", "after_claim",
        "after_ack", "after_fence",
    ],
)
def test_crash_injection_fail_closed_on_fresh_connection(tmp_path, stage):
    writer, port, a = make(tmp_path)

    def interrupt(where):
        if where == stage:
            raise RuntimeError("fixture-crash-" + where)

    with pytest.raises(RuntimeError, match="fixture-crash"):
        port.reserve_and_fence(a, fault=interrupt)
    reopened = LocalComputeBudget(
        DurableWriterV1(writer.path, fixture_approval_mode=True)
    )
    assert reopened.recover(a.identity, a.request_key).status == (
        "RECOVERY_PAUSE_NO_RETRY"
    )
    assert_closed(reopened, a, "STALE_BUDGET_CAS")
    assert reopened.writer.read_head(a.identity).reserved == 20


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_id", "price-revised"),
        ("model_version", "v2"),
        ("currency", "EUR"),
        ("source_revision", "r2"),
        ("consent_generation", 2),
    ],
)
def test_invoice_identity_price_version_source_bound(tmp_path, field, value):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    with pytest.raises(BudgetFence, match="INVOICE_PRICE_SOURCE_CONSENT_MISMATCH"):
        port.settle(
            a.identity, a.request_key, invoice(**{field: value}),
            charge_id="charge-one",
        )
    assert port.recover(a.identity, a.request_key).head.reserved == 20


def test_unknown_invoice_and_charge_replay(tmp_path):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    port.settle(a.identity, a.request_key, invoice(), charge_id="charge-one")
    original = port.recover(a.identity, a.request_key)
    assert port.settle(
        a.identity, a.request_key, invoice(), charge_id="charge-one"
    ) == original
    with pytest.raises(BudgetFence, match="DUPLICATE_OR_CONFLICTING_USAGE"):
        port.settle(
            a.identity, a.request_key, invoice(usage_id="usage-other"),
            charge_id="charge-two",
        )
    assert port.recover(a.identity, a.request_key).head.spent == 18


def test_extra_token_invoice_fail_closed(tmp_path):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    with pytest.raises(BudgetFence, match="UNPLANNED_TOKEN_USAGE"):
        port.settle(
            a.identity, a.request_key, invoice(actual_tokens=11),
            charge_id="charge-one",
        )


@pytest.mark.parametrize("actual", [-1, True])
def test_invalid_invoice_amount_rejected(tmp_path, actual):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    with pytest.raises(BudgetFence, match="INVALID_INVOICE"):
        port.settle(
            a.identity, a.request_key, invoice(actual_cost_microunits=actual),
            charge_id="charge-one",
        )


def test_overrun_charge_and_positive_audit_freezes_budget(tmp_path):
    writer, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    result = port.settle(
        a.identity, a.request_key, invoice(actual_cost_microunits=125),
        charge_id="charge-one",
    )
    assert result.status == "ECONOMIC_QUALIFICATION_OPEN"
    assert result.head.spent == 20
    assert result.corrected_spent_microunits == 125
    assert writer.recover(a.identity)["corrected_spent"] == 125
    assert port.recover(a.identity, a.request_key).status == "ECONOMIC_QUALIFICATION_OPEN"


def test_late_bill_and_duplicate_adjustment_id(tmp_path):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    port.settle(a.identity, a.request_key, invoice(), charge_id="charge-one")
    late = port.late_invoice(
        a.identity, a.request_key, adjustment_id="later1",
        evidence_ref="fixture-late", delta_microunits=50,
    )
    assert late.corrected_spent_microunits == 68
    assert late.status == "ECONOMIC_QUALIFICATION_OPEN"
    with pytest.raises(sqlite_integrity_errors()):
        port.late_invoice(
            a.identity, a.request_key, adjustment_id="later1",
            evidence_ref="fixture-late", delta_microunits=50,
        )


def sqlite_integrity_errors():
    import sqlite3

    return sqlite3.IntegrityError


def test_late_bill_requires_completed_charge(tmp_path):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    with pytest.raises(BudgetFence, match="LATE_INVOICE_WITHOUT_SETTLEMENT"):
        port.late_invoice(
            a.identity, a.request_key, adjustment_id="later1",
            evidence_ref="fixture-late", delta_microunits=1,
        )


def test_spoofed_tenant_run_cannot_read_other_contract(tmp_path):
    _, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    wrong = replace(a.identity, tenant_id="other")
    with pytest.raises(BudgetFence, match="UNKNOWN_REQUEST_KEY"):
        port.recover(wrong, a.request_key)


def test_cannot_enable_nonfixture_writer(tmp_path):
    writer, _, _ = make(tmp_path, fixture_mode=False)
    with pytest.raises(BudgetFence, match="TEST_FIXTURE_APPROVAL_REQUIRED"):
        LocalComputeBudget(writer)


def test_manual_ar02_reservation_detected_as_orphan(tmp_path):
    writer, port, a = make(tmp_path)
    writer.reserve(a.identity, a.head, reserve_id="external-reserve", amount=5)
    updated = writer.read_head(a.identity)
    a = replace(
        a, head=updated,
        decision_input=replace(
            a.decision_input,
            budget_version=updated.seq, reserved_cost_microunits=5,
        ),
    )
    assert_closed(port, a, "ECONOMIC_RECONCILIATION_REQUIRED")


def test_no_more_spending_while_unknown_outbox_even_after_invoice(tmp_path):
    writer, port, a = make(tmp_path)
    port.reserve_and_fence(a)
    port.settle(a.identity, a.request_key, invoice(), charge_id="charge-one")
    fresh = writer.read_head(a.identity)
    new_item = replace(
        a.decision_input,
        budget_version=fresh.seq,
        spent_cost_microunits=fresh.spent, reserved_cost_microunits=0,
        spent_tokens=10, spent_wall_ms=1000, attempts_used=1,
    )
    b = replace(
        a, head=fresh, decision_input=new_item,
        request_key="second", reserve_id="r-second",
        approval_id="a-second", intent_id="i-second", claim_id="c-second",
    )
    assert_closed(port, b, "UNRESOLVED_EFFECT")
