"""Python ⇆ independently implemented Node C1 candidate wire tests, offline only."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_engine.m27_ar09_oracle_experimental import (
    EXPECTED_ACCEPT_FIXTURE_ONLY,
    NativeCitation,
    NativeSourceFixture,
    compare_native_source,
)
from knowledge_engine.m27_canonical_wire_experimental import (
    MAGIC,
    C1Denied,
    bind_candidate,
    canonical_new_body,
    inspect_legacy_json,
    legacy_wire_ref,
)
from knowledge_engine.m27_cross_module_abi_experimental import (
    LegacyBoundEnvelope,
    OfflineAuthorityGate,
)

NODE_FILE = Path(__file__).with_name("m27_wire_oracle.mjs")
LEGACY = b'{ "legacy": true,  "historically_omitted":null }'
DOMAIN = "m27.envelope.binding.c1"
FIXED_GOLDEN_SHA = "b865539b7ccf3490726c33688ae4db68dd83461594302ffbe2cdadc26346b339"


def fixture(**overrides):
    body = {
        "schema_id": "m27.c1.envelope",
        "tenant_id": "tenant-a",
        "run_id": "run-a",
        "task_id": "task-a",
        "attempt": 1,
        "issued_at": "2026-10-10T00:00:00.000Z",
        "expires_at": "2026-10-11T00:00:00.000Z",
        "consent_ref": None,
        "payload": {"z": 1, "a": "🌏", "control": "\n\t"},
        "sidecars": ["sidecar-a"],
    }
    return {**body, **overrides}


def encode(body, **kwargs):
    options = {"ensure_ascii": False, "separators": (",", ":")}
    options.update(kwargs)
    return json.dumps(body, **options).encode()


def args(raw=None, *, body=None, legacy=LEGACY, **kwargs):
    if raw is None:
        raw = encode(body if body is not None else fixture())
    data = {
        "raw_hex": raw.hex(),
        "legacy_hex": legacy.hex(),
        "domain": DOMAIN,
        "tenant_id": "tenant-a",
        "run_id": "run-a",
        "task_id": "task-a",
        "attempt": 1,
    }
    return {**data, **kwargs}


def node_results(vectors):
    result = subprocess.run(
        ["/opt/homebrew/bin/node", str(NODE_FILE), "--batch"],
        input=json.dumps({"vectors": vectors}), text=True,
        capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def python_result(vector):
    try:
        kwargs = {
            "domain": vector["domain"],
            "tenant_id": vector["tenant_id"],
            "run_id": vector["run_id"],
            "task_id": vector["task_id"],
            "attempt": vector["attempt"],
        }
        if "expected_legacy_sha256" in vector:
            kwargs["expected_legacy_sha256"] = vector["expected_legacy_sha256"]
        outcome = bind_candidate(
            bytes.fromhex(vector["raw_hex"]), bytes.fromhex(vector["legacy_hex"]), **kwargs
        )
        return {"ok": True, **outcome.__dict__} if hasattr(outcome, "__dict__") else {
            "ok": True,
            "status": outcome.status,
            "canonical_hex": outcome.canonical_hex,
            "canonical_sha256": outcome.canonical_sha256,
            "legacy_raw_sha256": outcome.legacy_raw_sha256,
            "binding_hex": outcome.binding_hex,
            "binding_sha256": outcome.binding_sha256,
        }
    except C1Denied as exc:
        return {"ok": False, "error": exc.code}


def test_node_own_golden_and_independent_negative_selftest() -> None:
    result = subprocess.run(
        ["/opt/homebrew/bin/node", str(NODE_FILE), "--selftest"],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    assert data["selftest"] == "PASS"
    assert data["assertions"] == 6
    assert data["golden_binding_sha256"] == FIXED_GOLDEN_SHA


def test_fixed_independent_golden_bytes_and_digest() -> None:
    raw = encode(fixture())
    result = bind_candidate(
        raw, b'{"v":1 }', domain=DOMAIN, tenant_id="tenant-a",
        run_id="run-a", task_id="task-a", attempt=1,
    )
    node = node_results([args(raw=raw, legacy=b'{"v":1 }')])[0]
    assert node == {"ok": True, "status": result.status,
                    "canonical_hex": result.canonical_hex,
                    "canonical_sha256": result.canonical_sha256,
                    "legacy_raw_sha256": result.legacy_raw_sha256,
                    "binding_hex": result.binding_hex,
                    "binding_sha256": result.binding_sha256}
    assert result.binding_sha256 == FIXED_GOLDEN_SHA
    assert bytes.fromhex(result.binding_hex).startswith(MAGIC)
    assert bytes.fromhex(result.canonical_hex) == canonical_new_body(raw)


def test_positive_cross_language_vector_matrix() -> None:
    original = fixture()
    vectors = [
        args(),
        args(body=fixture(payload={"quote": '"\\/', "backslash": "\\", "form": "\f"})),
        args(body=fixture(payload={"nested": [{"unicode": "é"}, {"safe": 9007199254740991}]})),
        args(body=fixture(payload={"integer": 0, "list": [None, False, True]})),
        args(body=fixture(memo=None)),
        args(body=fixture(memo="")),
        args(body=fixture(memo="á🌈")),
        args(body=fixture(sidecars=["sidecar-a", "sidecar-b"])),
        args(body=fixture(schema_id="m27.c1.sidecar"),
             domain="m27.sidecar.binding.c1"),
        args(body=fixture(payload={"payload_b": {"a": 1, "z": 2}, "payload_a": []})),
        args(body=fixture(payload={"control": "\b\n\t\f\r\u0000\u001f"})),
        args(raw=json.dumps(original, sort_keys=True, indent=2, ensure_ascii=False).encode()),
    ]
    assert len(vectors) == 12
    from_node = node_results(vectors)
    from_python = [python_result(v) for v in vectors]
    assert from_node == from_python
    assert all(row["ok"] and row["status"] == "CANDIDATE_DIGEST_UNRATIFIED" for row in from_node)
    assert from_node[0]["binding_sha256"] == from_node[-1]["binding_sha256"]


@pytest.mark.parametrize(("bad", "code"), [
    (b'{"tenant_id":"t","tenant_id":"t"}', "DUPLICATE_JSON_KEY"),
    (b"\xff", "INVALID_UTF8"),
    (b"\xef\xbb\xbf{}", "UTF8_BOM_UNSUPPORTED"),
    (b"{}", "MISSING_REQUIRED_FIELD"),
    (encode(fixture(issued_at="2026-10-10T08:00:00+08:00")), "AMBIGUOUS_TIMESTAMP"),
    (encode(fixture(expires_at="2026-02-30T00:00:00.000Z")), "INVALID_CALENDAR_TIMESTAMP"),
    (encode(fixture(issued_at="2026-10-10T00:00:60.000Z")), "INVALID_CALENDAR_TIMESTAMP"),
    (encode(fixture(expires_at="2026-10-10T00:00:00.000Z")), "TIMESTAMP_ORDER_INVALID"),
    (encode(fixture(attempt=True)), "ATTEMPT_NOT_UNSIGNED_INT"),
    (encode(fixture(payload={"amount_microunits": True})), "UNSIGNED_FIELD_NOT_INT"),
    (encode(fixture(payload={"amount_microunits": None})), "UNSIGNED_FIELD_NOT_INT"),
    (encode(fixture(payload={"amount_microunits": 1.5})), "FLOAT_OR_EXPONENT_UNSUPPORTED"),
    (encode(fixture(attempt=None)), "ATTEMPT_NOT_UNSIGNED_INT"),
    (encode(fixture(attempt=9007199254740992)), "UNSAFE_OR_NEGATIVE_INTEGER"),
    (encode(fixture(attempt=-1)), "UNSAFE_OR_NEGATIVE_INTEGER"),
    (encode(fixture(attempt=1.0)), "FLOAT_OR_EXPONENT_UNSUPPORTED"),
    (encode(fixture(payload={"a": 1.5})), "FLOAT_OR_EXPONENT_UNSUPPORTED"),
    (encode(fixture(payload={"a": "\ud800"}), ensure_ascii=True), "UNPAIRED_SURROGATE"),
    (encode(fixture(payload={"a": "e\u0301"})), "NON_NFC_VALUE"),
    (encode(fixture(payload={"tenant_id": "shadow"})), "NESTED_AUTHORITY_SHADOW"),
    (encode(fixture(payload={"items": [{"allow_write": True}]})),
     "NESTED_AUTHORITY_SHADOW"),
    (encode(fixture(unknown_authority=True)), "UNKNOWN_AUTHORITY_OR_BODY_FIELD"),
    (encode(fixture(sidecars=["a", "a"])), "DUPLICATE_SIDECAR_ID"),
    (encode(fixture(sidecars=[])), "REQUIRED_SIDECARS_MISSING"),
    (encode(fixture(tenant_id=None)), "SCOPE_OR_NULL_UNBOUND"),
    (encode(fixture(consent_ref="")), "CONSENT_REF_INVALID"),
    (encode(fixture(schema_id="m27.c1.envelope.v2")), "UNRATIFIED_SCHEMA_UNSUPPORTED"),
    (encode(fixture(payload={"a": { "a-b": 1 }})), "UNSUPPORTED_KEY_OR_NORMALIZATION"),
])
def test_invalid_c1_vectors_deny_and_parity(bad, code: str) -> None:
    py = python_result(args(raw=bad))
    node = node_results([args(raw=bad)])[0]
    assert py == {"ok": False, "error": code}
    assert node == py


def test_mutations_domain_scope_legacy_and_null_boundaries() -> None:
    first = args()
    variants = [
        (args(domain="m27.sidecar.binding.c1"), "DOMAIN_SCHEMA_MISMATCH"),
        (args(tenant_id="tenant-b"), "IDENTITY_TUPLE_MISMATCH"),
        (args(run_id="run-b"), "IDENTITY_TUPLE_MISMATCH"),
        (args(task_id="task-b"), "IDENTITY_TUPLE_MISMATCH"),
        (args(attempt=2), "IDENTITY_TUPLE_MISMATCH"),
        (args(expected_legacy_sha256="0" * 64), "LEGACY_DIGEST_MISMATCH"),
        (args(raw=encode({k: v for k, v in fixture().items() if k != "consent_ref"})),
         "MISSING_REQUIRED_FIELD"),
        (args(raw=encode(fixture(consent_ref="other-consent"))), None),
        (args(raw=encode(fixture(memo=None))), None),
        (args(raw=encode(fixture(memo="memo"))), None),
        (args(legacy=LEGACY + b" "), None),
    ]
    results = node_results([first] + [v for v, _ in variants])
    assert results == [python_result(v) for v in [first] + [v for v, _ in variants]]
    for (_, denial), outcome in zip(variants, results[1:], strict=True):
        if denial:
            assert outcome == {"ok": False, "error": denial}
        else:
            assert outcome["ok"] and outcome["binding_sha256"] != results[0]["binding_sha256"]
    # Null is intentional and not equivalent to omitted.
    assert python_result(first)["binding_sha256"] != python_result(
        args(raw=encode(fixture(memo=None)))
    )["binding_sha256"]


def test_legacy_original_bytes_hash_unchanged_and_external_reader() -> None:
    original, digest, length = legacy_wire_ref(LEGACY)
    assert original is LEGACY
    assert digest == hashlib.sha256(LEGACY).hexdigest()
    assert length == len(LEGACY)
    inspect_legacy_json(LEGACY)
    historical = br'{"v":1, "old_text":"e\u0301"}'
    inspect_legacy_json(historical)
    assert legacy_wire_ref(historical)[0] == historical
    with pytest.raises(C1Denied, match="LEGACY_DUPLICATE_KEY"):
        inspect_legacy_json(b'{"a":1,"a":2}')
    with pytest.raises(C1Denied, match="LEGACY_INVALID_UTF8"):
        inspect_legacy_json(b"\xff")
    sidecars = (hashlib.sha256(b"required-sidecar").hexdigest(),)
    envelope = LegacyBoundEnvelope(
        envelope_id="env-1", tenant_id="tenant-a", run_id="run-a",
        legacy_type="RunEvent", legacy_raw_sha256=digest,
        raw_byte_length=length, required_sidecar_digests=sidecars,
        policy_generation=4, revocation_generation=0,
    )
    original_gate = OfflineAuthorityGate(trusted_keys={})
    original_gate.validate_legacy(
        envelope=envelope, raw_bytes=LEGACY, supplied_sidecar_digests=sidecars
    )
    assert legacy_wire_ref(LEGACY + b" ")[1] != digest


def test_readonly_original_ar09_native_oracle_is_preserved() -> None:
    raw = b"literal native fixture only"
    digest = hashlib.sha256(raw).hexdigest()
    citation = NativeCitation("citation-a", "source-a", "rev-1", digest, 0, 7)
    native = NativeSourceFixture(
        kind="native", tenant_id="tenant-a", snapshot_id="snapshot-a",
        source_bytes=raw, source_digest=digest, citations=(citation,),
    )
    assert compare_native_source(native, native).label == EXPECTED_ACCEPT_FIXTURE_ONLY
    assert compare_native_source(
        native, replace(native, citations=(replace(citation, start=1),))
    ).label != EXPECTED_ACCEPT_FIXTURE_ONLY


def test_swapped_binding_tuple_and_length_prefix_no_ambiguity() -> None:
    correct = python_result(args())
    assert correct["ok"]
    bytestring = bytes.fromhex(correct["binding_hex"])
    assert bytestring.startswith(MAGIC)
    cursor = len(MAGIC)
    frames = []
    for _ in range(8):
        count = int.from_bytes(bytestring[cursor:cursor + 4], "big")
        cursor += 4
        frames.append(bytestring[cursor:cursor + count])
        cursor += count
    assert cursor == len(bytestring)
    assert frames[0] == DOMAIN.encode()
    assert frames[1] == b"m27.c1.envelope"
    assert frames[2] == bytes.fromhex(correct["canonical_hex"])
    assert frames[3] == bytes.fromhex(correct["legacy_raw_sha256"])
    assert frames[4:] == [b"tenant-a", b"run-a", b"task-a", b"1"]

    swapped = [*frames]
    swapped[5], swapped[6] = swapped[6], swapped[5]
    forged = MAGIC + b"".join(len(item).to_bytes(4, "big") + item for item in swapped)
    assert hashlib.sha256(forged).hexdigest() != correct["binding_sha256"]
    variant = args(run_id="task-a", task_id="run-a")
    assert node_results([variant])[0] == python_result(variant) == {
        "ok": False, "error": "IDENTITY_TUPLE_MISMATCH"
    }


def test_unsupported_json_tokens_are_deny_only_not_fake_parity() -> None:
    source = encode(fixture())
    cases = [
        (source.replace(b'"attempt":1', b'"attempt":-0'),
         "NEGATIVE_ZERO_UNSUPPORTED", "NEGATIVE_ZERO_UNSUPPORTED"),
        (source.replace(b'"attempt":1', b'"attempt":1e0'),
         "FLOAT_OR_EXPONENT_UNSUPPORTED", "FLOAT_OR_EXPONENT_UNSUPPORTED"),
        (source.replace(b'"attempt":1', b'"attempt":NaN'),
         "NONFINITE_NUMBER", "INVALID_JSON"),
        (source.replace(b'"attempt":1', b'"attempt":Infinity'),
         "NONFINITE_NUMBER", "INVALID_JSON"),
    ]
    for raw, python_denial, node_denial in cases:
        candidate = args(raw=raw)
        assert python_result(candidate) == {"ok": False, "error": python_denial}
        assert node_results([candidate])[0] == {"ok": False, "error": node_denial}
    # Rejection-code differences on invalid non-JSON tokens are explicitly
    # UNSUPPORTED, not accepted or marketed as ratified error ABI.
