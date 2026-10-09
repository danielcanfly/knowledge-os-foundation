from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar09_oracle_experimental import (
    EXPECTED_ACCEPT_FIXTURE_ONLY,
    EXPECTED_DENY,
    EXPECTED_STREAM_FAIL,
    EXPECTED_UNKNOWN_EFFECT,
    EXPECTED_UNKNOWN_PROOF,
    NOT_RUN,
    VECTOR_COVERAGE,
    NativeCitation,
    NativeSourceFixture,
    OracleConfig,
    StreamFrame,
    base_envelope,
    classify_stream,
    classify_wire,
    compare_native_source,
    default_config,
    encode_envelope,
    generate_case,
    remote_unknown_oracle,
    two_writer_cas_oracle,
)

SOURCE_BYTES = b"synthetic native source bytes"
SOURCE_SHA = hashlib.sha256(SOURCE_BYTES).hexdigest()


def native(**changes: object) -> NativeSourceFixture:
    citation = NativeCitation(
        citation_id="citation-1",
        source_id="source-1",
        source_revision="revision-1",
        source_digest=SOURCE_SHA,
        start=0,
        end=9,
    )
    value = NativeSourceFixture(
        kind="native",
        tenant_id="tenant-a",
        snapshot_id="snapshot-a",
        source_bytes=SOURCE_BYTES,
        source_digest=SOURCE_SHA,
        citations=(citation,),
    )
    return replace(value, **changes)


def classify(**changes: object):
    value = base_envelope()
    value.update(changes)
    return classify_wire(encode_envelope(value))


def test_positive_fixture_preserves_distinct_raw_and_canonical_digests() -> None:
    compact = encode_envelope(base_envelope())
    spaced = compact + b" "
    first = classify_wire(compact)
    second = classify_wire(spaced)
    assert first.label == second.label == EXPECTED_ACCEPT_FIXTURE_ONLY
    assert first.raw_bytes_sha256 != second.raw_bytes_sha256
    assert first.canonical_json_sha256 == second.canonical_json_sha256


@pytest.mark.parametrize(
    "case_id",
    [
        "V06",
        "V07",
        "V08",
        "V09",
        "V11",
        "V16",
        "V17",
        "V20",
        "V21",
        "V35",
        "V40",
        "V41",
        "V44",
        "V45",
        "V50",
    ],
)
def test_generated_denials_are_deterministic(case_id: str) -> None:
    raw_one, expected_one = generate_case(case_id, seed=71)
    raw_two, expected_two = generate_case(case_id, seed=71)
    assert (raw_one, expected_one) == (raw_two, expected_two)
    assert classify_wire(raw_one).label == EXPECTED_DENY


def test_duplicate_key_bool_unsafe_integer_and_timestamp_are_rejected() -> None:
    duplicate, _ = generate_case("V06")
    assert classify_wire(duplicate).reason == "DUPLICATE_JSON_KEY"
    assert classify(task_version=True).reason == "BOOL_OR_UNSAFE_UINT"
    assert classify(attempt=2**53).reason == "BOOL_OR_UNSAFE_UINT"
    assert classify(expires_at="2026-10-10 00:00:00").reason == "TIMESTAMP_UNCERTAIN"


def test_unsupported_record_type_is_a_named_v02_denial() -> None:
    raw, expected = generate_case("V02")
    result = classify_wire(raw)
    assert expected == EXPECTED_DENY
    assert (result.label, result.reason) == (EXPECTED_DENY, "UNSUPPORTED_RECORD_TYPE")


def test_expected_original_raw_bytes_reject_reserialization() -> None:
    original = encode_envelope(base_envelope())
    config = replace(default_config(), expected_raw_sha256=hashlib.sha256(original).hexdigest())
    assert classify_wire(original, config).label == EXPECTED_ACCEPT_FIXTURE_ONLY
    assert classify_wire(original + b" ", config).reason == "ORIGINAL_RAW_BYTES_MISMATCH"


def test_unknown_revoked_and_self_verifier_fail_closed() -> None:
    assert classify(signer_key_id="unknown").reason == "UNKNOWN_OR_REVOKED_TRUST_ROOT"
    base = default_config()
    revoked = OracleConfig(
        now=base.now,
        tenant_id=base.tenant_id,
        task_id=base.task_id,
        task_version=base.task_version,
        run_id=base.run_id,
        attempt=base.attempt,
        audience=base.audience,
        lease_epoch=base.lease_epoch,
        journal_head_seq=base.journal_head_seq,
        journal_head_hash=base.journal_head_hash,
        policy_generation=base.policy_generation,
        trusted_keys=base.trusted_keys,
        revoked_keys=frozenset({"trusted-key"}),
        forbidden_signers=base.forbidden_signers,
        expected_raw_sha256=None,
    )
    assert classify_wire(encode_envelope(base_envelope()), revoked).label == EXPECTED_DENY
    assert classify(signer_domain="answer-generator").label == EXPECTED_UNKNOWN_PROOF


@pytest.mark.parametrize(
    ("changes", "reason", "label"),
    [
        ({"task_id": "task-b"}, "IDENTITY_OR_AUDIENCE_MISMATCH", EXPECTED_DENY),
        ({"task_version": 2}, "IDENTITY_OR_AUDIENCE_MISMATCH", EXPECTED_DENY),
        ({"audience": "other"}, "IDENTITY_OR_AUDIENCE_MISMATCH", EXPECTED_DENY),
        ({"delegated_by": None}, "DELEGATION_MISSING", EXPECTED_DENY),
        (
            {"delegation_expires_at": "2026-10-09T11:00:00Z"},
            "PROOF_OR_DELEGATION_EXPIRED",
            EXPECTED_DENY,
        ),
        ({"consent_ref": None}, "CONSENT_MISSING", EXPECTED_DENY),
        ({"policy_generation": 6}, "STALE_POLICY_GENERATION", EXPECTED_UNKNOWN_PROOF),
        ({"proof_head_seq": 10}, "STALE_JOURNAL_PROOF", EXPECTED_DENY),
        ({"proof_lease_epoch": 2}, "STALE_LEASE_BINDING", EXPECTED_DENY),
        ({"price_microunits": None}, "PRICE_OR_USAGE_MISSING", EXPECTED_UNKNOWN_PROOF),
        ({"usage_microunits": None}, "PRICE_OR_USAGE_MISSING", EXPECTED_UNKNOWN_PROOF),
    ],
)
def test_authority_head_and_economic_bindings(
    changes: dict[str, object], reason: str, label: str
) -> None:
    result = classify(**changes)
    assert (result.reason, result.label) == (reason, label)


def test_tenant_source_mismatch_does_not_disclose_foreign_identity() -> None:
    value = base_envelope()
    value["source"] = {**value["source"], "tenant_id": "secret-tenant"}  # type: ignore[dict-item]
    result = classify_wire(encode_envelope(value))
    assert result.reason == "TENANT_OR_SOURCE_MISMATCH"
    assert "secret-tenant" not in result.reason


def test_native_bytes_citation_order_span_and_synthetic_mixup_are_denied() -> None:
    original = native()
    assert compare_native_source(original, original).label == EXPECTED_ACCEPT_FIXTURE_ONLY
    assert compare_native_source(
        original, replace(original, source_bytes=b"changed")
    ).label == EXPECTED_DENY
    assert compare_native_source(
        original, replace(original, kind="synthetic")
    ).reason == "NATIVE_SYNTHETIC_SUBSTITUTION"
    second = replace(
        original.citations[0], citation_id="citation-2", start=10, end=15
    )
    two = replace(original, citations=(original.citations[0], second))
    reordered = replace(two, citations=(second, original.citations[0]))
    assert compare_native_source(two, reordered).label == EXPECTED_DENY
    bad_span = replace(original, citations=(replace(original.citations[0], end=999),))
    assert compare_native_source(bad_span, bad_span).reason == "CITATION_SPAN_OR_PIN_INVALID"


def test_missing_source_attestation_is_unknown_proof() -> None:
    result = compare_native_source(native(), native(attested=False))
    assert result.label == EXPECTED_UNKNOWN_PROOF


def test_stream_oracle_distinguishes_progress_text_citation_and_delivery() -> None:
    progress_terminal = (
        StreamFrame("progress", b"working"),
        StreamFrame("terminal", b"done"),
    )
    assert classify_stream(progress_terminal) == EXPECTED_STREAM_FAIL
    uncited = (StreamFrame("verified_text", b"answer"), StreamFrame("terminal", b"done"))
    assert classify_stream(uncited) == EXPECTED_STREAM_FAIL
    server_only = (
        StreamFrame("verified_text", b"answer", ("citation-1",), False),
        StreamFrame("terminal", b"done"),
    )
    assert classify_stream(server_only) == EXPECTED_UNKNOWN_PROOF
    delivered = (
        StreamFrame("verified_text", b"answer", ("citation-1",), True),
        StreamFrame("terminal", b"done"),
    )
    assert classify_stream(delivered) == EXPECTED_ACCEPT_FIXTURE_ONLY
    assert classify_stream(
        (StreamFrame("safe_abstention", b"safe", answer_timestamp_present=True),)
    ) == EXPECTED_STREAM_FAIL


def test_two_writer_and_remote_unknown_schedules_are_deterministic_and_inert() -> None:
    first = two_writer_cas_oracle(19)
    assert first == two_writer_cas_oracle(19)
    assert first.commit_count == 1
    assert first.winner != first.loser
    assert first.send_count == 0
    unknown = remote_unknown_oracle(t3_crossed=True, ack_lost=True)
    assert unknown.label == EXPECTED_UNKNOWN_EFFECT
    assert unknown.send_count == 0


def test_v01_to_v50_coverage_is_explicit_and_never_implied() -> None:
    assert tuple(VECTOR_COVERAGE) == tuple(f"V{index:02d}" for index in range(1, 51))
    assert set(VECTOR_COVERAGE.values()) == {"IMPLEMENTED", NOT_RUN}
    assert VECTOR_COVERAGE["V03"] == NOT_RUN
    assert VECTOR_COVERAGE["V10"] == NOT_RUN
    assert VECTOR_COVERAGE["V50"] == "IMPLEMENTED"
