from __future__ import annotations

import hashlib
import time

import pytest

from knowledge_engine.m27_c02_native_composer import (
    C02_CLIENT_ACK_ABI,
    GeneratedClaim,
    compose_native_candidate,
)
from knowledge_engine.m27_c02_semantic_provider import (
    C02_RESPONSE_ABI,
    EvidenceClass,
    ProviderAuthority,
    SemanticDecision,
    SemanticRequest,
    SourceBinding,
    SourceBoundSemanticProvider,
    TrustStatus,
)

NOW = 2_000.0


def source(
    text: str = "Kubernetes schedules GPU workloads and restarts failed services.", **changes
):
    raw = text.encode()
    values = dict(
        source_id="source-1",
        title="Kubernetes Operations",
        revision="r7",
        raw_bytes=raw,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        byte_start=0,
        byte_end=len(raw),
        excerpt_sha256=hashlib.sha256(raw).hexdigest(),
        language="en",
        tenant_id="tenant-a",
        allowed_principals=("principal-a",),
        expires_at_epoch_s=3_000.0,
    )
    values.update(changes)
    return SourceBinding(**values)


def authority(**changes):
    values = dict(
        provider_id="fixture-provider",
        model_identity="fixture-nli",
        model_version="1.0",
        runtime_sha256="a" * 64,
        license_id="TEST_ONLY",
        license_sha256="b" * 64,
        signer_id="fixture-signer",
        qualification_receipt_sha256="c" * 64,
        trust_status=TrustStatus.VERIFIED,
        evidence_class=EvidenceClass.DETERMINISTIC_FIXTURE,
        task_bounds=("semantic_entailment",),
        languages=("en", "ja", "zh"),
        authorized_principals=("principal-a",),
        valid_until_epoch_s=3_000.0,
        max_attempts=1,
        timeout_ms=50,
        max_cost_units=2.0,
        model_architecture="fixture-nli-architecture",
        allowed_model_architectures=("fixture-nli-architecture",),
        license_scope="NONPROD_SEMANTIC_VERIFICATION",
        approved_license_ids=("TEST_ONLY",),
    )
    values.update(changes)
    return ProviderAuthority(**values)


def request(src: SourceBinding | None = None, **changes):
    values = dict(
        request_id="request-1",
        run_id="run-1",
        nonce="nonce-1",
        tenant_id="tenant-a",
        principal="principal-a",
        task="semantic_entailment",
        claim_text="Kubernetes can restart failed services.",
        claim_language="en",
        generator_model_identity="generator-model",
        sources=(src or source(),),
        budget_units=1.0,
    )
    values.update(changes)
    return SemanticRequest(**values)


def response(req: SemanticRequest, **changes):
    values = dict(
        schema_version=C02_RESPONSE_ABI,
        request_id=req.request_id,
        run_id=req.run_id,
        nonce=req.nonce,
        provider_id="fixture-provider",
        model_identity="fixture-nli",
        model_version="1.0",
        decision="ENTAILED",
        confidence=0.94,
        reason="fixture contract support",
        supporting_source_ids=[req.sources[0].source_id],
        cost_units=0.25,
        issued_at_epoch_s=1_999.0,
        expires_at_epoch_s=2_100.0,
        signer_id="fixture-signer",
        attestation_id="attestation-1",
        attestation="fixture-signed:attestation-1",
    )
    values.update(changes)
    return values


def fixture_attestation(result, _payload):
    return result["attestation"] == "fixture-signed:" + result["attestation_id"]


def provider(
    auth=None,
    transport=None,
    verifier=fixture_attestation,
    authority_verifier=lambda _authority: True,
):
    auth = auth or authority()
    if transport is None:

        def transport(payload):
            return response(
                request(
                    nonce=payload["nonce"],
                    request_id=payload["request_id"],
                    run_id=payload["run_id"],
                )
            )

    return SourceBoundSemanticProvider(auth, transport, verifier, authority_verifier)


def test_fixture_transport_can_verify_but_never_qualifies_provider():
    outcome = provider().verify(request(), now=NOW)
    assert outcome.verified is True
    assert outcome.admission_eligible is False
    assert outcome.receipt["evidence_class"] == "DETERMINISTIC_FIXTURE"


@pytest.mark.parametrize(
    ("auth_change", "reason"),
    [
        ({"trust_status": TrustStatus.NOT_PROVEN}, "PROVIDER_AUTHORITY_NOT_VERIFIED"),
        ({"trust_status": TrustStatus.EXPLICITLY_REFUSED}, "PROVIDER_AUTHORITY_NOT_VERIFIED"),
        ({"revoked": True}, "PROVIDER_POLICY_REVOKED"),
        ({"valid_until_epoch_s": 1_999.0}, "PROVIDER_AUTHORITY_EXPIRED"),
        ({"runtime_sha256": ""}, "PROVIDER_RUNTIME_OR_LICENSE_UNPROVEN"),
        ({"model_architecture": "unsupported"}, "PROVIDER_MODEL_ARCHITECTURE_UNSUPPORTED"),
        ({"license_id": "UNAPPROVED"}, "PROVIDER_LICENSE_OR_RIGHT_DENIED"),
        ({"license_scope": "GENERATION_ONLY"}, "PROVIDER_LICENSE_OR_RIGHT_DENIED"),
        ({"authorized_principals": ("someone-else",)}, "PROVIDER_PRINCIPAL_DENIED"),
        ({"task_bounds": ("translation",)}, "PROVIDER_TASK_OUT_OF_SCOPE"),
        ({"languages": ("ja",)}, "PROVIDER_LANGUAGE_UNSUPPORTED"),
        ({"max_cost_units": 0.1}, "PROVIDER_BUDGET_DENIED"),
    ],
)
def test_authority_failures_close_without_transport(auth_change, reason):
    called = False

    def transport(_payload):
        nonlocal called
        called = True
        return {}

    outcome = provider(authority(**auth_change), transport).verify(request(), now=NOW)
    assert outcome.verified is False and outcome.reason == reason
    assert called is False


@pytest.mark.parametrize(
    ("src_change", "reason"),
    [
        ({"source_sha256": "0" * 64}, "SOURCE_BYTES_TAMPERED"),
        ({"excerpt_sha256": "0" * 64}, "SOURCE_SPAN_TAMPERED"),
        ({"byte_end": 999}, "SOURCE_SPAN_INVALID"),
        ({"revoked": True}, "SOURCE_REVOKED"),
        ({"expires_at_epoch_s": 1_999.0}, "SOURCE_STALE"),
        ({"tenant_id": "tenant-b"}, "TENANT_MISMATCH"),
        ({"allowed_principals": ("other",)}, "ACL_DENIED"),
        ({"memory_citation_authority": True}, "MEMORY_IS_NOT_CITATION_AUTHORITY"),
    ],
)
def test_source_binding_failures_close_before_provider(src_change, reason):
    outcome = provider().verify(request(source(**src_change)), now=NOW)
    assert outcome.verified is False and outcome.reason == reason


def test_same_model_cannot_generate_and_independently_verify():
    outcome = provider().verify(request(generator_model_identity="fixture-nli"), now=NOW)
    assert outcome.reason == "VERIFIER_NOT_INDEPENDENT_OF_GENERATOR"


def test_malformed_request_is_rejected_before_transport():
    outcome = provider().verify(request(request_id=""), now=NOW)
    assert outcome.reason == "MALFORMED_SEMANTIC_REQUEST"


def test_timeout_is_unknown_and_never_retried():
    calls = 0

    def slow(_payload):
        nonlocal calls
        calls += 1
        time.sleep(0.1)
        return {}

    outcome = provider(authority(timeout_ms=5, max_attempts=2, retry_safe=True), slow).verify(
        request(), now=NOW
    )
    assert outcome.reason == "PROVIDER_TIMEOUT_UNKNOWN"
    assert calls == 1


def test_crash_retries_only_when_declared_safe_and_bounded():
    calls = 0

    def crash(_payload):
        nonlocal calls
        calls += 1
        raise RuntimeError("down")

    outcome = provider(authority(max_attempts=2, retry_safe=True), crash).verify(request(), now=NOW)
    assert outcome.reason == "PROVIDER_CRASH"
    assert outcome.attempts == calls == 2


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"run_id": "other-run"}, "CROSS_RUN_OR_NONCE_REPLAY"),
        ({"provider_id": "other-provider"}, "PROVIDER_OR_MODEL_IDENTITY_MISMATCH"),
        ({"signer_id": "other-signer"}, "PROVIDER_SIGNER_MISMATCH"),
        ({"expires_at_epoch_s": 1_999.0}, "PROVIDER_RESPONSE_STALE_OR_INVALID"),
        ({"decision": "OPAQUE"}, "PROVIDER_DECISION_UNKNOWN"),
        ({"supporting_source_ids": ["invented"]}, "PROVIDER_RESPONSE_FIELDS_INVALID"),
        ({"cost_units": 1.5}, "PROVIDER_RESPONSE_FIELDS_INVALID"),
    ],
)
def test_response_identity_budget_and_schema_fail_closed(change, reason):
    req = request()
    outcome = provider(transport=lambda _payload: response(req, **change)).verify(req, now=NOW)
    assert outcome.verified is False and outcome.reason == reason


def test_invalid_attestation_and_replay_fail_closed():
    req = request()
    untrusted = provider(verifier=lambda *_: False).verify(req, now=NOW)
    assert untrusted.reason == "PROVIDER_ATTESTATION_INVALID"
    adapter = provider()
    assert adapter.verify(req, now=NOW).verified is True
    replay = adapter.verify(req, now=NOW)
    assert replay.reason == "PROVIDER_ATTESTATION_REPLAY"


@pytest.mark.parametrize("decision", ["CONTRADICTED", "UNSUPPORTED", "UNKNOWN"])
def test_negative_semantic_decisions_never_verify(decision):
    req = request()
    outcome = provider(
        transport=lambda _payload: response(
            req, decision=decision, confidence=0.99, supporting_source_ids=[]
        )
    ).verify(req, now=NOW)
    assert outcome.decision is SemanticDecision(decision)
    assert outcome.verified is False


def test_low_confidence_entailment_becomes_unknown():
    req = request()
    outcome = provider(transport=lambda _payload: response(req, confidence=0.4)).verify(
        req, now=NOW
    )
    assert outcome.decision is SemanticDecision.UNKNOWN
    assert outcome.verified is False


def test_cancellation_before_and_after_provider_fails_closed():
    assert provider().verify(request(), now=NOW, cancelled=lambda: True).reason == "CANCELLED"
    checks = iter((False, True))
    outcome = provider().verify(request(), now=NOW, cancelled=lambda: next(checks))
    assert outcome.reason == "CANCELLED_AFTER_PROVIDER"


def generated(_question, _sources):
    return GeneratedClaim(
        "Kubernetes can restart failed services.",
        ("source-1",),
        "generator-model",
        "1.0",
        True,
        1.2,
    )


def ack_for(event):
    import json

    event_sha = hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return {
        "schema_version": C02_CLIENT_ACK_ABI,
        "request_id": event["request_id"],
        "run_id": event["run_id"],
        "event_sha256": event_sha,
        "client_id": "fixture-client",
        "signature": "fixture-client-signature",
    }


def verify_ack(ack, _event):
    return ack.get("signature") == "fixture-client-signature"


def compose(**changes):
    values = dict(
        request_id="request-1",
        run_id="run-1",
        question="How does Kubernetes recover?",
        tenant_id="tenant-a",
        principal="principal-a",
        sources=(source(),),
        generator=generated,
        semantic_provider=provider(),
        client_publisher=ack_for,
        verify_client_ack=verify_ack,
        budget_units=1.0,
        now=NOW,
    )
    values.update(changes)
    return compose_native_candidate(**values)


def test_nonqualifying_fixture_is_not_delivered_by_default():
    result = compose()
    assert result.publishable is False
    assert result.native_composer_admitted is False
    assert result.terminal_reason == "PROVIDER_QUALIFICATION_NOT_PROVEN"


def test_fixture_delivery_exercises_ack_but_cannot_admit_native_composer():
    result = compose(allow_nonqualifying_fixture_delivery=True)
    assert result.status == "FIXTURE_ONLY" and result.publishable is True
    assert result.native_composer_admitted is False
    assert result.provider_qualification_proven is False
    kinds = [event["type"] for event in result.events]
    assert kinds.index("verified_answer_text") < kinds.index("terminal")
    assert result.events[-1]["status"] == "FIXTURE_ONLY"


def test_missing_provider_real_model_candidate_fails_closed():
    result = compose(semantic_provider=None)
    assert result.publishable is False
    assert result.terminal_reason == "PROVIDER_QUALIFICATION_NOT_PROVEN"


def test_generator_must_be_actual_model_output():
    def fake(*_):
        return GeneratedClaim("fixture text", ("source-1",), "fixture", "1", False, 0)

    result = compose(generator=fake)
    assert result.terminal_reason == "GENERATED_CLAIM_INVALID_OR_NOT_REAL_MODEL"


def test_client_ack_replay_or_forgery_fails_closed():
    def forged(event):
        return {**ack_for(event), "run_id": "other-run"}

    result = compose(client_publisher=forged, allow_nonqualifying_fixture_delivery=True)
    assert result.publishable is False and result.terminal_reason == "CLIENT_ACK_INVALID"


def test_verifier_rejection_publishes_no_answer_text():
    req = request()
    rejecting = provider(
        transport=lambda _payload: response(
            req, decision="CONTRADICTED", confidence=0.99, supporting_source_ids=[]
        )
    )
    result = compose(semantic_provider=rejecting, allow_nonqualifying_fixture_delivery=True)
    assert result.publishable is False
    assert all(event["type"] != "verified_answer_text" for event in result.events)


def test_external_qualification_shape_can_admit_only_with_verified_receipt():
    qualified = authority(evidence_class=EvidenceClass.EXTERNAL_QUALIFICATION)
    result = compose(semantic_provider=provider(qualified))
    assert result.status == "SUCCEEDED"
    assert result.native_composer_admitted is True
    assert result.provider_qualification_proven is True


def test_external_qualification_cannot_self_assert_authority():
    qualified = authority(evidence_class=EvidenceClass.EXTERNAL_QUALIFICATION)
    adapter = provider(qualified, authority_verifier=None)
    outcome = adapter.verify(request(), now=NOW)
    assert outcome.reason == "PROVIDER_QUALIFICATION_RECEIPT_INVALID"
    assert outcome.admission_eligible is False
