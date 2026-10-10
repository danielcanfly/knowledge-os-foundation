"""P09 T0 deterministic fixture tests, with no external evidence or paid calls."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from knowledge_engine.m27_w4_p09_external_evidence_v1_experimental import (
    FIXTURE_ALGORITHM,
    REQUIRED_ROLES,
    Admission,
    AdmissionPacket,
    Anchor,
    EconomicRollup,
    EvidenceIntake,
    FrozenCandidate,
    Identity,
    SignedRecord,
    canonical,
    reconcile_economics,
    sha256,
)
from knowledge_engine.m27_w4_p09_external_evidence_v1_experimental import (
    test_only_seal as synthetic_seal,
)

COMMIT = "0cd2b74baa2c892b163ffe5138de2df863417889"
TREE = "4c352e7ae1e25ecbb023151e7e95722193d2c7a9"
IMAGE = "sha256:" + "a" * 64
BUILD = "b" * 64
SOURCE_HASH = "c" * 64
WIRE_HASH = "d" * 64


def source_bodies() -> dict[str, dict]:
    bodies = {
        "source": {
            "tenant": "tenant-1", "source_id": "opaque-source-1",
            "revision": "source-v1", "native_sha256": SOURCE_HASH,
            "acl_tenants": ["tenant-1"], "acl_valid_until_ms": 1200,
            "license": "owner-permitted-test-fixture", "revoked": False,
        },
        "consent": {
            "tenant": "tenant-1", "source_revision": "source-v1",
            "granted": True, "expires_ms": 1200,
        },
        "retention": {
            "policy_id": "fixture-retention", "permitted_until_ms": 1200,
            "revoked": False,
        },
        "price": {
            "provider": "test-provider", "model": "test-model",
            "model_version": "model-v1", "currency": "USD",
            "effective_ms": 100, "until_ms": 1200,
            "input_micros_per_token": "3", "output_micros_per_token": "4",
            "reasoning_micros_per_token": "1",
            "cached_micros_per_token": "1",
            "issued_by_provider": True,
        },
        "usage": {
            "boundary_complete": True,
            "calls": [
                {
                    "call_id": "call-failed", "attempt": "attempt-1",
                    "provider": "test-provider", "model_version": "model-v1",
                    "status": "FAILED", "provider_request_id": "opaque-1",
                    "clock_domain": "clock-1", "time_ms": 900,
                    "input_tokens": 1, "output_tokens": 0,
                    "reasoning_tokens": 0, "cached_tokens": 0,
                    "retry_of": None,
                },
                {
                    "call_id": "call-retry", "attempt": "attempt-1",
                    "provider": "test-provider", "model_version": "model-v1",
                    "status": "OK", "provider_request_id": "opaque-2",
                    "clock_domain": "clock-1", "time_ms": 950,
                    "input_tokens": 1, "output_tokens": 1,
                    "reasoning_tokens": 0, "cached_tokens": 0,
                    "retry_of": "call-failed",
                },
            ],
        },
        "invoice": {
            "billing_complete": True,
            "bills": [
                {
                    "call_id": "call-failed", "attempt": "attempt-1",
                    "currency": "USD", "model_version": "model-v1",
                    "issued_ms": 970, "micros": 3,
                    "external_invoice_id": "invoice-failed",
                },
                {
                    "call_id": "call-retry", "attempt": "attempt-1",
                    "currency": "USD", "model_version": "model-v1",
                    "issued_ms": 980, "micros": 7,
                    "external_invoice_id": "invoice-retry",
                },
            ],
        },
        "client": {
            "ack": True, "request": "request-1",
            "clock_domain": "clock-1", "wire_payload_sha256": WIRE_HASH,
            "received_ms": 960,
        },
        "route": {
            "instrumented_native_route": "native-fixture-only",
            "candidate_commit": COMMIT, "client_ack_request": "request-1",
        },
        "build": {
            "source_commit": COMMIT, "source_tree": TREE,
            "image_digest": IMAGE, "build_digest": BUILD,
        },
        **{
            role: {
                "decision": "PASS", "candidate_commit": COMMIT,
                "task_attempt": "attempt-1",
            }
            for role in ("reviewer", "verifier", "ci", "observer", "outcome")
        },
    }
    bodies["outcome"].update(effect_state="RESOLVED", independently_verified=True)
    return bodies


def provision(*, image: bool = True) -> tuple[EvidenceIntake, AdmissionPacket]:
    identity = Identity(
        tenant="tenant-1", run="run-1", request="request-1",
        attempt="attempt-1", revision="rev-1", clock_domain="clock-1",
        event_ms=800, source_commit=COMMIT, source_tree=TREE,
        image_digest=IMAGE if image else None,
        build_digest=BUILD if image else None,
        provider="test-provider", model="test-model",
        model_version="model-v1", native_route="native-fixture-only",
        executor="fixture-worker",
    )
    anchors = tuple(
        Anchor(role, role + "-signer", role + "-key", role.encode(),
               FIXTURE_ALGORITHM, "FIXTURE", "synthetic-test-issuer")
        for role in sorted(REQUIRED_ROLES)
    )
    frozen = FrozenCandidate(COMMIT, TREE, IMAGE if image else None,
                             BUILD if image else None)
    intake = EvidenceIntake(frozen, anchors, now_ms=1000, invoice_close_ms=1000)
    packet = AdmissionPacket(identity, (), ("attempt-1",))
    packet = resubmit(packet, source_bodies())
    return intake, packet


def resubmit(packet: AdmissionPacket, bodies: dict[str, dict]) -> AdmissionPacket:
    """New canonical digest+chain+HMAC after each deliberate semantic corruption."""
    records: list[SignedRecord] = []
    previous = None
    for role, body in sorted(bodies.items()):
        unsigned = SignedRecord(
            role=role, signer=role + "-signer", key_id=role + "-key",
            algorithm=FIXTURE_ALGORITHM,
            tenant=packet.identity.tenant, run=packet.identity.run,
            request=packet.identity.request, attempt=packet.identity.attempt,
            revision=packet.identity.revision, issued_ms=700,
            expires_ms=1100, previous_digest=previous,
            body=body, digest="", signature="",
        )
        digest = sha256(canonical({
            "role": unsigned.role, "signer": unsigned.signer,
            "key_id": unsigned.key_id, "algorithm": unsigned.algorithm,
            "tenant": unsigned.tenant, "run": unsigned.run,
            "request": unsigned.request, "attempt": unsigned.attempt,
            "revision": unsigned.revision, "issued_ms": unsigned.issued_ms,
            "expires_ms": unsigned.expires_ms,
            "previous_digest": unsigned.previous_digest, "body": unsigned.body,
        }))
        unsigned = replace(unsigned, digest=digest)
        unsigned = replace(unsigned, signature=synthetic_seal(unsigned, role.encode()))
        records.append(unsigned)
        previous = digest
    return replace(packet, records=tuple(records))


def altered_body(role: str, field: str, value: object) -> AdmissionPacket:
    _, pkt = provision()
    bodies = source_bodies()
    bodies[role][field] = value
    return resubmit(pkt, bodies)


def assert_rejected_reason(packet: AdmissionPacket, expected: str) -> None:
    intake, _ = provision()
    receipt = intake.inspect(packet)
    assert receipt.verdict == "P09_AUTHORITY_EVIDENCE_NOT_ADMITTED"
    assert any(expected in r for r in receipt.reasons), receipt.reasons
    assert receipt.cost_micros is None
    assert not receipt.accepted_outcome


def test_signed_local_fixture_is_never_real_authority() -> None:
    intake, packet = provision()
    receipt = intake.inspect(packet)
    assert receipt.verdict == "P09_AUTHORITY_EVIDENCE_NOT_ADMITTED"
    assert "EXTERNAL_ROOT_OR_RECEIPT_MISSING" in receipt.reasons
    assert "PHASE_B_INDEPENDENT_OUTCOME_MISSING" in receipt.reasons
    assert "ACTUAL_COST_UNKNOWN" in receipt.reasons
    assert all(x == "NOT_VERIFIED" for x in receipt.classifications.values())
    assert len(receipt.evidence_digest or "") == 64
    assert set(receipt.classifications) == REQUIRED_ROLES
    # A complete *synthetic* usage ledger includes the failed call and retry.
    assert intake._reconcile(packet, {r.role: r for r in packet.records}) == (10, set())


@pytest.mark.parametrize(("role", "field", "value", "reason"), [
    ("source", "tenant", "tenant-2", "SOURCE_ACL"),
    ("source", "source_id", "", "SOURCE_ACL"),
    ("source", "revision", "", "SOURCE_ACL"),
    ("source", "native_sha256", "not-sha", "SOURCE_ACL"),
    ("source", "acl_tenants", ["tenant-2"], "SOURCE_ACL"),
    ("source", "acl_tenants", None, "SOURCE_ACL"),
    ("source", "acl_valid_until_ms", 1000, "SOURCE_ACL"),
    ("source", "license", None, "SOURCE_ACL"),
    ("source", "license", 100, "SOURCE_ACL"),
    ("source", "license", "UNKNOWN", "SOURCE_ACL"),
    ("source", "revoked", True, "SOURCE_ACL"),
    ("consent", "granted", False, "CONSENT_INVALID"),
    ("consent", "tenant", "tenant-2", "CONSENT_INVALID"),
    ("consent", "source_revision", "v2", "CONSENT_INVALID"),
    ("consent", "expires_ms", 1000, "CONSENT_INVALID"),
    ("consent", "expires_ms", "10000", "CONSENT_INVALID"),
    ("retention", "policy_id", "", "RETENTION_INVALID"),
    ("retention", "permitted_until_ms", 999, "RETENTION_INVALID"),
    ("retention", "permitted_until_ms", None, "RETENTION_INVALID"),
    ("retention", "revoked", True, "RETENTION_INVALID"),
    ("reviewer", "decision", "UNKNOWN", "INDEPENDENT_PROOF_INVALID"),
    ("verifier", "candidate_commit", "f" * 40, "INDEPENDENT_PROOF_INVALID"),
    ("ci", "task_attempt", "wrong", "INDEPENDENT_PROOF_INVALID"),
    ("observer", "decision", "FAIL", "INDEPENDENT_PROOF_INVALID"),
    ("outcome", "decision", "UNKNOWN", "INDEPENDENT_PROOF_INVALID"),
    ("outcome", "effect_state", "UNKNOWN", "INDEPENDENT_PROOF_INVALID"),
    ("outcome", "independently_verified", False, "INDEPENDENT_PROOF_INVALID"),
    ("client", "ack", False, "CLIENT_ACK_NOT_VERIFIED"),
    ("client", "request", "wrong", "CLIENT_ACK_NOT_VERIFIED"),
    ("client", "clock_domain", "other-clock", "CLIENT_ACK_NOT_VERIFIED"),
    ("client", "wire_payload_sha256", "unhashable", "CLIENT_ACK_NOT_VERIFIED"),
    ("client", "received_ms", 700, "CLIENT_ACK_NOT_VERIFIED"),
    ("client", "received_ms", 1001, "CLIENT_ACK_NOT_VERIFIED"),
    ("route", "instrumented_native_route", "untrusted", "NATIVE_ROUTE_NOT_VERIFIED"),
    ("route", "candidate_commit", "f" * 40, "NATIVE_ROUTE_NOT_VERIFIED"),
    ("route", "client_ack_request", "wrong", "NATIVE_ROUTE_NOT_VERIFIED"),
    ("build", "source_commit", "f" * 40, "BUILD_PROVENANCE_NOT_VERIFIED"),
    ("build", "source_tree", "f" * 40, "BUILD_PROVENANCE_NOT_VERIFIED"),
    ("build", "image_digest", "mutable:latest", "BUILD_PROVENANCE_NOT_VERIFIED"),
    ("build", "build_digest", "f" * 64, "BUILD_PROVENANCE_NOT_VERIFIED"),
    ("price", "currency", "EUR", "INVOICE_CURRENCY"),
    ("price", "currency", "usd", "CURRENCY_INVALID"),
    ("price", "provider", "wrong", "PRICE_VERSION"),
    ("price", "model", "wrong", "PRICE_VERSION"),
    ("price", "model_version", "old", "PRICE_VERSION"),
    ("price", "effective_ms", 801, "PRICE_VERSION"),
    ("price", "until_ms", 800, "PRICE_VERSION"),
    ("price", "input_micros_per_token", "-1", "PRICE_RATE_INVALID"),
    ("price", "cached_micros_per_token", "NaN", "PRICE_RATE_INVALID"),
    ("price", "issued_by_provider", False, "PROVIDER_BOUNDARY"),
    ("usage", "boundary_complete", False, "PROVIDER_BOUNDARY"),
    ("invoice", "billing_complete", False, "PROVIDER_BOUNDARY"),
    ("usage", "calls", [], "INCOMPLETE_CALL"),
    ("invoice", "bills", [], "INCOMPLETE_CALL"),
])
def test_independent_semantic_negative_vectors(
    role: str, field: str, value: object, reason: str
) -> None:
    assert_rejected_reason(altered_body(role, field, value), reason)


@pytest.mark.parametrize(("role", "field", "value", "reason"), [
    ("usage", "status", "NOT_A_STATUS", "USAGE_IDENTITY"),
    ("usage", "provider_request_id", "", "USAGE_IDENTITY"),
    ("usage", "model_version", "wrong", "USAGE_IDENTITY"),
    ("usage", "clock_domain", "clock-2", "USAGE_IDENTITY"),
    ("usage", "attempt", "unassigned", "USAGE_IDENTITY"),
    ("usage", "input_tokens", -1, "TOKEN_METER"),
    ("usage", "output_tokens", -1, "TOKEN_METER"),
    ("usage", "reasoning_tokens", True, "TOKEN_METER"),
    ("usage", "cached_tokens", 2, "CACHE_METER"),
    ("usage", "retry_of", "unknown", "RETRY_CHAIN"),
    ("usage", "time_ms", 1001, "USAGE_IDENTITY"),
    ("usage", "call_id", "call-failed", "DUPLICATE_USAGE"),
    ("invoice", "currency", "EUR", "INVOICE_CURRENCY"),
    ("invoice", "attempt", "wrong", "INVOICE_CURRENCY"),
    ("invoice", "model_version", "wrong", "INVOICE_CURRENCY"),
    ("invoice", "issued_ms", 1001, "INVOICE_CURRENCY"),
    ("invoice", "issued_ms", 900, "INVOICE_CURRENCY"),
    ("invoice", "micros", -1, "INVOICE_CURRENCY"),
    ("invoice", "micros", 999, "INVOICE_TOTAL"),
    ("invoice", "external_invoice_id", "", "INVOICE_CURRENCY"),
    ("invoice", "call_id", "wrong", "INVOICE_COVERAGE"),
])
def test_usage_invoice_faults(
    role: str, field: str, value: object, reason: str
) -> None:
    bodies = source_bodies()
    if role == "usage":
        index = 1
        bodies["usage"]["calls"][index][field] = value
    else:
        bodies["invoice"]["bills"][1][field] = value
    _, packet = provision()
    assert_rejected_reason(resubmit(packet, bodies), reason)


@pytest.mark.parametrize("role", sorted(REQUIRED_ROLES))
def test_missing_independent_role_is_closed(role: str) -> None:
    bodies = source_bodies()
    del bodies[role]
    _, packet = provision()
    updated = resubmit(packet, bodies)
    result = EvidenceIntake(
        FrozenCandidate(COMMIT, TREE, IMAGE, BUILD)
    ).inspect(updated)
    assert result.classifications[role] == "MISSING"
    assert "REQUIRED_ROLES_MISSING" in result.reasons


def test_wrong_tenant_identity() -> None:
    _, packet = provision()
    assert_rejected_reason(
        replace(packet, identity=replace(packet.identity, tenant="tenant-2")),
        "IDENTITY_OR_ISSUER_MISMATCH",
    )


def test_wrong_revision_and_frozen_commit() -> None:
    _, packet = provision()
    assert_rejected_reason(
        replace(packet, identity=replace(packet.identity, source_commit="e" * 40)),
        "I02_FROZEN_REVISION_CONFLICT",
    )


def test_missing_image_is_not_implicitly_mapped_from_git() -> None:
    intake, packet = provision(image=False)
    result = intake.inspect(packet)
    assert "IMMUTABLE_IMAGE_OR_BUILD_MISSING" in result.reasons


def test_mutable_tag_rejected() -> None:
    _, packet = provision()
    assert_rejected_reason(
        replace(packet, identity=replace(packet.identity, image_digest="latest")),
        "IMMUTABLE_IMAGE_OR_BUILD_CONFLICT",
    )


def test_missing_assigned_attempts() -> None:
    _, packet = provision()
    assert_rejected_reason(replace(packet, assigned_attempts=()), "ASSIGNMENT")


def test_duplicates_in_frozen_denominator() -> None:
    _, packet = provision()
    assert_rejected_reason(
        replace(packet, assigned_attempts=("attempt-1", "attempt-1")), "ASSIGNMENT",
    )


def test_unobserved_failed_attempt_is_cost_unknown() -> None:
    _, packet = provision()
    assert_rejected_reason(
        replace(packet, assigned_attempts=("attempt-1", "failed-unmetered")),
        "ASSIGNED_FAILURE_OR_ATTEMPT_NOT_METERED",
    )


def test_tampered_record_sha_is_rejected() -> None:
    _, packet = provision()
    records = list(packet.records)
    records[0] = replace(records[0], digest="0" * 64)
    assert_rejected_reason(replace(packet, records=tuple(records)), "DIGEST_CONFLICT")


def test_chain_collision_is_rejected() -> None:
    _, packet = provision()
    records = list(packet.records)
    records[1] = replace(records[1], previous_digest="e" * 64)
    assert_rejected_reason(replace(packet, records=tuple(records)), "CHAIN_OR_DUPLICATE")


def test_forged_hmac_fixture_rejected() -> None:
    _, packet = provision()
    records = list(packet.records)
    records[1] = replace(records[1], signature="0" * 64)
    assert_rejected_reason(replace(packet, records=tuple(records)), "SIGNATURE_OR_ROOT")


def test_self_issued_signer_rejected() -> None:
    _, packet = provision()
    records = list(packet.records)
    records[0] = replace(records[0], signer="fixture-worker")
    assert_rejected_reason(replace(packet, records=tuple(records)), "IDENTITY_OR_ISSUER")


def test_expired_issuer_record_rejected() -> None:
    _, packet = provision()
    records = list(packet.records)
    records[0] = replace(records[0], expires_ms=999)
    assert_rejected_reason(replace(packet, records=tuple(records)), "EXPIRED_FUTURE")


def test_unknown_root_cannot_verify_signature() -> None:
    _, packet = provision()
    intake = EvidenceIntake(FrozenCandidate(COMMIT, TREE, IMAGE, BUILD))
    result = intake.inspect(packet)
    assert "SIGNATURE_OR_ROOT_INVALID_BUILD" in result.reasons


def test_mock_phase_b_flag_does_not_upgrade_fixture() -> None:
    intake, packet = provision()
    fake = replace(packet, phase_b_independent_outcome=True)
    upgraded = EvidenceIntake(
        intake.frozen, tuple(intake.anchors.values()),
        authorized_external_custodian=True,
    ).inspect(fake)
    assert upgraded.verdict == "P09_AUTHORITY_EVIDENCE_NOT_ADMITTED"
    assert "EXTERNAL_ROOT_OR_RECEIPT_MISSING" in upgraded.reasons


def test_duplicate_invoice_line_must_not_lower_cost() -> None:
    bodies = source_bodies()
    bodies["invoice"]["bills"][1]["call_id"] = "call-failed"
    _, packet = provision()
    assert_rejected_reason(resubmit(packet, bodies), "DUPLICATE_OR_FORGED_INVOICE")


def test_duplicate_call_usage_must_not_double_count() -> None:
    bodies = source_bodies()
    bodies["usage"]["calls"][1]["call_id"] = "call-failed"
    _, packet = provision()
    assert_rejected_reason(resubmit(packet, bodies), "DUPLICATE_USAGE_OR_CALL_ID")


def test_failed_attempt_still_in_arithmetic_denominator() -> None:
    # Synthetic arithmetic-only objects, never recognized as real issuer bills.
    receipt_ok = Admission("P09_EXTERNAL_EVIDENCE_ADMITTED", (), {}, 7, True, "x", "a1")
    receipt_failed = Admission("P09_EXTERNAL_EVIDENCE_ADMITTED", (), {}, 3, False, "y", "a2")
    result = reconcile_economics(("a1", "a2"), (receipt_ok, receipt_failed), "USD")
    assert isinstance(result, EconomicRollup)
    assert result.total_cost_micros == 10
    assert result.verified_outcomes == 1
    assert result.cost_per_verified_outcome_micros == Decimal("10")


def test_unknown_bill_never_equals_zero_cost() -> None:
    fake = Admission("P09_AUTHORITY_EVIDENCE_NOT_ADMITTED", (), {}, None, False, None, "a1")
    result = reconcile_economics(("a1",), (fake,), "USD")
    assert result.total_cost_micros is None
    assert result.cost_per_verified_outcome_micros is None
    assert "UNKNOWN_ACTUAL_COST" in result.reasons


def test_zero_verified_denominator_is_undefined() -> None:
    failure = Admission("P09_EXTERNAL_EVIDENCE_ADMITTED", (), {}, 100, False, "x", "a1")
    result = reconcile_economics(("a1",), (failure,), "USD")
    assert result.total_cost_micros == 100
    assert result.cost_per_verified_outcome_micros is None
    assert "ZERO_VERIFIED_OUTCOMES" in result.reasons


def test_missing_assignment_coverage_in_batch() -> None:
    failure = Admission("P09_AUTHORITY_EVIDENCE_NOT_ADMITTED", (), {}, None, False, None)
    result = reconcile_economics(("a1", "a2"), (failure,), "USD")
    assert "ELIGIBLE_DENOMINATOR_OR_COVERAGE_INVALID" in result.reasons


def test_compensating_invoice_forgery_same_total_is_rejected() -> None:
    bodies = source_bodies()
    bodies["invoice"]["bills"][0]["micros"] = 4
    bodies["invoice"]["bills"][1]["micros"] = 6
    _, packet = provision()
    assert_rejected_reason(resubmit(packet, bodies), "INVOICE_LINE_MISMATCH")


def test_duplicate_attempt_identity_in_economic_rollup_is_rejected() -> None:
    one = Admission("P09_EXTERNAL_EVIDENCE_ADMITTED", (), {}, 5, True, "x", "a1")
    two = Admission("P09_EXTERNAL_EVIDENCE_ADMITTED", (), {}, 7, True, "y", "a1")
    rollup = reconcile_economics(("a1", "a2"), (one, two), "USD")
    assert rollup.cost_per_verified_outcome_micros is None
    assert "ELIGIBLE_DENOMINATOR_OR_COVERAGE_INVALID" in rollup.reasons


def test_invalid_future_event_clock_is_rejected() -> None:
    _, packet = provision()
    assert_rejected_reason(
        replace(packet, identity=replace(packet.identity, event_ms=1200)),
        "BAD_CLOCK",
    )


def test_signed_but_malformed_role_body_is_not_an_exception() -> None:
    _, packet = provision()
    bodies = source_bodies()
    bodies["source"] = []
    assert_rejected_reason(resubmit(packet, bodies), "MALFORMED_BODY_SOURCE")


def test_price_interval_must_cover_every_retried_call() -> None:
    bodies = source_bodies()
    bodies["price"]["until_ms"] = 920
    _, packet = provision()
    assert_rejected_reason(resubmit(packet, bodies), "USAGE_IDENTITY_METER_OR_CLOCK")


def test_sha_and_canonical_contract() -> None:
    assert sha256(canonical({"b": 1, "a": 2})) == sha256(
        canonical({"a": 2, "b": 1})
    )
    with pytest.raises(ValueError):
        canonical({"not_allowed": float("nan")})
