from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from knowledge_engine import m26_aq_semantic_contract as c01_canonical
from knowledge_engine import m26_pa7_arbitrary_query_runtime as c01_legacy
from knowledge_engine.m27_c02_native_composer import C02_CLIENT_ACK_ABI, GeneratedClaim
from knowledge_engine.m27_c02_semantic_provider import (
    C02_RESPONSE_ABI,
    EvidenceClass,
    ProviderAuthority,
    SourceBoundSemanticProvider,
    TrustStatus,
)
from knowledge_engine.m27_d01_nonprod_integration import (
    D01Policy,
    D01SourceSpec,
    run_d01_nonprod_e2e,
)

NOW = 4_000.0
SOURCE_TEXT = "Kubernetes restarts failed services to restore the desired state.\n"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source(tmp_path: Path, **changes) -> D01SourceSpec:
    path = tmp_path / "source.txt"
    path.write_text(SOURCE_TEXT, encoding="utf-8")
    raw = path.read_bytes()
    values = dict(
        path=path,
        source_id="d01-source",
        title="D01 first-party Nonprod source",
        observed_revision="r1",
        expected_revision="r1",
        expected_source_sha256=_sha(raw),
        byte_start=0,
        byte_end=len(raw),
        expected_excerpt_sha256=_sha(raw),
        language="en",
        tenant_id="tenant-a",
        allowed_principals=("principal-a",),
        expires_at_epoch_s=5_000.0,
        license_id="FIRST_PARTY_NONPROD",
        rights_grant_id="owner-nonprod-dispatch",
        rights_valid_until_epoch_s=5_000.0,
    )
    values.update(changes)
    return D01SourceSpec(**values)


def _authority(**changes) -> ProviderAuthority:
    values = dict(
        provider_id="fixture-provider",
        model_identity="fixture-verifier",
        model_version="1",
        runtime_sha256="a" * 64,
        license_id="TEST_ONLY",
        license_sha256="b" * 64,
        signer_id="fixture-signer",
        qualification_receipt_sha256="c" * 64,
        trust_status=TrustStatus.VERIFIED,
        evidence_class=EvidenceClass.DETERMINISTIC_FIXTURE,
        task_bounds=("semantic_entailment",),
        languages=("en",),
        authorized_principals=("principal-a",),
        valid_until_epoch_s=5_000.0,
        max_attempts=1,
        timeout_ms=50,
        max_cost_units=1.0,
        model_architecture="fixture-nli",
        allowed_model_architectures=("fixture-nli",),
        license_scope="NONPROD_SEMANTIC_VERIFICATION",
        approved_license_ids=("TEST_ONLY",),
    )
    values.update(changes)
    return ProviderAuthority(**values)


def _response(payload, auth: ProviderAuthority, **changes):
    values = {
        "schema_version": C02_RESPONSE_ABI,
        "request_id": payload["request_id"],
        "run_id": payload["run_id"],
        "nonce": payload["nonce"],
        "provider_id": auth.provider_id,
        "model_identity": auth.model_identity,
        "model_version": auth.model_version,
        "decision": "ENTAILED",
        "confidence": 0.99,
        "reason": "fixture transport support only",
        "supporting_source_ids": ["d01-source"],
        "cost_units": 0.25,
        "issued_at_epoch_s": NOW - 1,
        "expires_at_epoch_s": NOW + 100,
        "signer_id": auth.signer_id,
        "attestation_id": "attestation-1",
        "attestation": "fixture:attestation-1",
    }
    values.update(changes)
    return values


def _provider(auth=None, response_changes=None, transport=None, authority_verifier=None):
    authority = auth or _authority()
    if transport is None:
        def transport(payload):
            return _response(payload, authority, **(response_changes or {}))

    return SourceBoundSemanticProvider(
        authority,
        transport,
        lambda result, _payload: result["attestation"]
        == "fixture:" + result["attestation_id"],
        authority_verifier,
    )


def _generator(_question, _sources):
    return GeneratedClaim(
        "Kubernetes restores desired state by restarting failed services.",
        ("d01-source",),
        "local-generator",
        "1",
        True,
        1.0,
    )


def _event_sha(event) -> str:
    raw = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return _sha(raw)


def _ack(event):
    return {
        "schema_version": C02_CLIENT_ACK_ABI,
        "request_id": event["request_id"],
        "run_id": event["run_id"],
        "event_sha256": _event_sha(event),
        "client_id": "ephemeral-fixture-client",
        "signature": "fixture-signature",
        "qualification_class": "DETERMINISTIC_FIXTURE",
    }


def _verify_ack(ack, _event):
    return ack.get("signature") == "fixture-signature"


def _run(tmp_path: Path, **changes):
    values = dict(
        request_id="request-1",
        run_id="run-1",
        question="How does Kubernetes recover?",
        tenant_id="tenant-a",
        principal="principal-a",
        source_specs=(_source(tmp_path),),
        generator=_generator,
        semantic_provider=_provider(),
        client_publisher=_ack,
        verify_client_ack=_verify_ack,
        budget_units=0.5,
        policy=D01Policy(opt_in_enabled=True, allow_ephemeral_fixture_client=True),
        now=NOW,
    )
    values.update(changes)
    return run_d01_nonprod_e2e(**values)


def test_joined_source_verifier_client_outcome_keeps_fixture_nonformal(tmp_path):
    result = _run(tmp_path)
    assert result.status == "FIXTURE_ONLY"
    assert result.fixture_transport_delivery is True
    assert result.official_client_publication is False
    assert result.c02_semantic_admission is False
    assert result.native_composer_admission is False
    assert result.formal_product_go is result.c28 is result.f35 is result.rel01 is False
    assert result.production == "NO_GO"
    assert result.request_id == "request-1" and result.run_id == "run-1"
    assert set(result.stage_timings) == {
        "source_retrieval",
        "generator",
        "verifier",
        "client",
    }
    assert result.source_receipt["sources"][0]["source_sha256"] == _sha(
        SOURCE_TEXT.encode()
    )
    assert result.composer_result["provider_receipt"]["run_id"] == "run-1"
    assert result.composer_result["client_receipt"]["run_id"] == "run-1"


def test_optional_module_requires_explicit_nonprod_opt_in(tmp_path):
    called = False

    def generator(*_args):
        nonlocal called
        called = True
        return _generator(*_args)

    result = _run(tmp_path, generator=generator, policy=D01Policy(opt_in_enabled=False))
    assert result.terminal_reason == "C02_OPTIONAL_MODULE_NOT_EXPLICITLY_ENABLED"
    assert called is False


def test_c01_compatibility_bundle_cannot_bypass_c02_provider_gate(tmp_path, monkeypatch):
    bundle = object()
    monkeypatch.setattr(c01_legacy, "load_production_answer_bundle", lambda: bundle)
    assert c01_canonical._resolve_production_answer_bundle(None) is bundle

    result = _run(
        tmp_path,
        semantic_provider=None,
        client_publisher=lambda _event: pytest.fail("Client must not receive unverified text"),
    )
    assert result.terminal_reason == "PROVIDER_QUALIFICATION_NOT_PROVEN"
    assert result.official_client_publication is False
    assert result.fixture_transport_delivery is False


def test_optional_modules_are_not_imported_by_default_product_runtime():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/knowledge_engine/m27_runtime_execution.py",
        "src/knowledge_engine/m27_agent_product_runtime.py",
        "src/knowledge_engine/m26_aq_semantic_contract.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "m27_c02_" not in text
        assert "m27_d01_nonprod_integration" not in text


@pytest.mark.parametrize(
    ("source_change", "run_change", "reason"),
    [
        ({"tenant_id": "tenant-b"}, {}, "TENANT_MISMATCH"),
        ({"allowed_principals": ("other",)}, {}, "ACL_DENIED"),
        ({"expected_source_sha256": "0" * 64}, {}, "SOURCE_DATA_SHA_MISMATCH"),
        ({"observed_revision": "r0"}, {}, "SOURCE_REVISION_MISMATCH"),
        ({"expected_excerpt_sha256": "0" * 64}, {}, "SOURCE_EXCERPT_SHA_MISMATCH"),
        ({"byte_end": 999}, {}, "SOURCE_SPAN_INVALID"),
        ({"source_revoked": True}, {}, "SOURCE_REVOKED"),
        ({"rights_revoked": True}, {}, "SOURCE_RIGHTS_REVOKED"),
        ({"rights_valid_until_epoch_s": NOW}, {}, "SOURCE_RIGHTS_STALE"),
        ({}, {"tenant_id": "tenant-b"}, "TENANT_MISMATCH"),
        ({}, {"principal": "other"}, "ACL_DENIED"),
    ],
)
def test_source_identity_rights_and_acl_fail_before_generation(
    tmp_path, source_change, run_change, reason
):
    called = False

    def generator(*_args):
        nonlocal called
        called = True
        return _generator(*_args)

    result = _run(
        tmp_path,
        source_specs=(_source(tmp_path, **source_change),),
        generator=generator,
        **run_change,
    )
    assert result.terminal_reason == reason
    assert result.official_client_publication is False
    assert called is False


@pytest.mark.parametrize(
    ("auth_change", "reason"),
    [
        ({"valid_until_epoch_s": NOW}, "PROVIDER_AUTHORITY_EXPIRED"),
        ({"revoked": True}, "PROVIDER_POLICY_REVOKED"),
        ({"authorized_principals": ("other",)}, "PROVIDER_PRINCIPAL_DENIED"),
        ({"max_cost_units": 0.1}, "PROVIDER_BUDGET_DENIED"),
        ({"model_version": "wrong-version"}, "PROVIDER_OR_MODEL_IDENTITY_MISMATCH"),
    ],
)
def test_provider_authority_and_budget_fail_closed(tmp_path, auth_change, reason):
    auth = _authority(**auth_change)
    response_changes = {"model_version": "1"} if "model_version" in auth_change else None
    result = _run(
        tmp_path,
        semantic_provider=_provider(auth=auth, response_changes=response_changes),
    )
    assert result.terminal_reason == reason
    assert result.official_client_publication is False


@pytest.mark.parametrize(
    ("response_change", "reason"),
    [
        ({"signer_id": "wrong-signer"}, "PROVIDER_SIGNER_MISMATCH"),
        ({"schema_version": "wrong/v0"}, "CROSS_RUN_OR_NONCE_REPLAY"),
        ({"run_id": "replayed-run"}, "CROSS_RUN_OR_NONCE_REPLAY"),
        ({"nonce": "replayed-nonce"}, "CROSS_RUN_OR_NONCE_REPLAY"),
        ({"decision": "OPAQUE"}, "PROVIDER_DECISION_UNKNOWN"),
        (
            {"decision": "UNKNOWN", "supporting_source_ids": []},
            "fixture transport support only",
        ),
    ],
)
def test_response_identity_schema_replay_and_unknown_fail_closed(
    tmp_path, response_change, reason
):
    result = _run(tmp_path, semantic_provider=_provider(response_changes=response_change))
    assert result.terminal_reason == reason
    assert result.official_client_publication is False
    assert result.fixture_transport_delivery is False


def test_malformed_semantic_response_missing_field_is_denied(tmp_path):
    auth = _authority()

    def malformed(payload):
        value = _response(payload, auth)
        value.pop("confidence")
        return value

    result = _run(tmp_path, semantic_provider=_provider(auth=auth, transport=malformed))
    assert result.terminal_reason == "PROVIDER_MALFORMED_RESPONSE"
    assert result.official_client_publication is False


def test_timeout_and_cancellation_never_reach_client(tmp_path):
    def slow(_payload):
        time.sleep(0.05)
        return {}

    timeout = _run(
        tmp_path,
        semantic_provider=_provider(auth=_authority(timeout_ms=2), transport=slow),
    )
    assert timeout.terminal_reason == "PROVIDER_TIMEOUT_UNKNOWN"
    cancelled = _run(tmp_path, cancelled=lambda: True)
    assert cancelled.terminal_reason == "CANCELLED_BEFORE_GENERATION"
    assert timeout.official_client_publication is cancelled.official_client_publication is False


def test_rejected_verdict_emits_no_substantive_text(tmp_path):
    rejecting = _provider(
        response_changes={
            "decision": "CONTRADICTED",
            "confidence": 0.99,
            "supporting_source_ids": [],
        }
    )
    result = _run(tmp_path, semantic_provider=rejecting)
    events = result.composer_result["events"]
    assert all(event["type"] != "verified_answer_text" for event in events)
    candidate = next(event for event in events if event["type"] == "generated_claim_candidate")
    assert "text" not in candidate and "text_sha256" in candidate


def test_provider_attestation_replay_and_client_ack_spoof_are_denied(tmp_path):
    adapter = _provider()
    first = _run(tmp_path, semantic_provider=adapter)
    second = _run(tmp_path, semantic_provider=adapter, request_id="request-2")
    assert first.status == "FIXTURE_ONLY"
    assert second.terminal_reason == "PROVIDER_ATTESTATION_REPLAY"

    def forged(event):
        return {**_ack(event), "run_id": "spoofed-run"}

    spoof = _run(tmp_path, semantic_provider=_provider(), client_publisher=forged)
    assert spoof.terminal_reason == "CLIENT_ACK_INVALID"
    assert spoof.fixture_transport_delivery is False


def test_external_qualification_shape_cannot_self_promote_without_d01_authority(tmp_path):
    auth = _authority(evidence_class=EvidenceClass.EXTERNAL_QUALIFICATION)
    adapter = _provider(auth=auth, authority_verifier=lambda _authority: True)
    result = _run(tmp_path, semantic_provider=adapter)
    assert result.terminal_reason == "D01_AUTHORITY_LEDGER_DENIED_NATIVE_ADMISSION"
    assert result.official_client_publication is False
    assert result.native_composer_admission is False
    assert result.production == "NO_GO"
