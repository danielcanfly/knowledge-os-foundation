"""D28 X01-X09 bounded Python + independent Node golden regression.

No authority assertions. Cross-module AR02/AR04/AR05 tests run separately.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from knowledge_engine.m27_d28_dual_envelope_v1_experimental import (
    LEGACY_NS,
    NEW_NS,
    VERSION,
    D28Denied,
    load_wire,
    make_legacy,
    make_new,
    negotiate_reader,
    validate_wire,
)

LEGACY = b'{ "event_id":"evt-1",  "occurred_at":"2026-10-09T05:00:00Z", "legacy":null }'
# The original event's SHA is an externally supplied original journal hash.
OLD_EVENT = "a" * 64
HEAD = "b" * 64
PROOF = "c" * 64
SIDECARS = [{"namespace": "ar02.effective-auth", "schema_version": VERSION,
             "body_sha256": PROOF}]
BASE = dict(record_id="record-1", tenant_id="tenant-1", run_id="run-1",
            policy_generation=3, revocation_generation=4,
            checkpoint_seq=8, checkpoint_head=HEAD)
DATA = Path(__file__).with_name("fixtures") / "d28_ar01_dual_envelope_goldens.json"
NODE = Path(__file__).with_name("d28_ar01_node_oracle.mjs")


def legacy(**changes):
    return make_legacy(raw_legacy=LEGACY, original_event_hash=OLD_EVENT,
                       required_sidecars=SIDECARS, **(BASE | changes))


def new(kind="postterminal", body=None, **changes):
    if body is None:
        body = {
            "original_terminal_head_hash": HEAD, "notice_seq": 1,
            "notice_prev_hash": "0" * 64, "client_cursor": 1,
            "supersedes_segment_id": "seg-1", "kind": "retraction",
        }
    return make_new(new_record_kind=kind,
                    new_record_namespace={
                        "postterminal": "ar05r.notice",
                        "revocation": "ar06.revocation-control",
                        "billing": "ar02.billing-ledger",
                    }[kind],
                    body=body, **(BASE | changes))


def tamper(raw, **changes):
    body = json.loads(raw)
    body.update(changes)
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode()


def error(code, fn):
    with pytest.raises(D28Denied, match=code) as raised:
        fn()
    assert raised.value.code == code


def test_x01_preserves_legacy_exact_original_bytes_and_digest():
    raw = legacy()
    ref = validate_wire(raw, raw_legacy=LEGACY)["legacy_ref"]
    assert ref == {"raw_sha256": hashlib.sha256(LEGACY).hexdigest(),
                   "raw_byte_length": len(LEGACY), "original_event_hash": OLD_EVENT}
    assert b'"created_at"' not in LEGACY
    assert b'  ' in LEGACY
    assert json.dumps(json.loads(LEGACY), sort_keys=True).encode() != LEGACY


def test_x01_new_only_revocation_not_conflated_with_legacy():
    raw = new(kind="revocation",
              body={"exclusion_generation": 5, "subject_ref": "subject-1",
                    "reason_code": "consent-withdrawn"})
    item = validate_wire(raw)
    assert item["namespace"] == NEW_NS
    assert not any(k.startswith("legacy") for k in item)
    error("NEW_RECORD_CANNOT_BIND_LEGACY", lambda: validate_wire(raw, raw_legacy=LEGACY))


def test_x01_bad_raw_digest_and_length():
    error("LEGACY_RAW_HASH_MISMATCH", lambda: validate_wire(
        legacy(), raw_legacy=LEGACY[:-1] + b" "
    ))
    alt = json.loads(legacy())
    alt["legacy_ref"]["raw_byte_length"] += 1
    error("LEGACY_LENGTH_MISMATCH", lambda: validate_wire(
        json.dumps(alt, sort_keys=True, separators=(",", ":")).encode(), raw_legacy=LEGACY,
    ))


@pytest.mark.parametrize("value", [b'{"x":1,"x":2}', b'{"x":1.0}',
                                   b'{"x":NaN}', b'\xef\xbb\xbf{"x":1}',
                                   b'{"x":-1}', b'{"x":9007199254740992}'])
def test_x01_strict_new_canonical_json_negative(value):
    with pytest.raises(D28Denied):
        load_wire(value)


def test_x01_noncanonical_order_refused():
    raw = legacy()
    error("NONCANONICAL_NEW_WIRE",
          lambda: validate_wire(json.dumps(json.loads(raw), ensure_ascii=False).encode(),
                                raw_legacy=LEGACY))


def test_x01_missing_legacy_binding():
    raw = legacy()
    item = json.loads(raw)
    item.pop("legacy_ref")
    error("ENVELOPE_FIELDS_OR_KIND", lambda: validate_wire(
        json.dumps(item, sort_keys=True, separators=(",", ":")).encode(), raw_legacy=LEGACY
    ))


@pytest.mark.parametrize("mod", [{"schema_version": "2.0.0"},
                                  {"schema_version": "1.0.0-proposal"},
                                  {"namespace": "ar01v.envelope/v1"}])
def test_x01_unsupported_version_or_namespace_no_downgrade(mod):
    error("UNSUPPORTED_VERSION_NO_DOWNGRADE",
          lambda: validate_wire(tamper(legacy(), **mod), raw_legacy=LEGACY))


def test_x02_no_mock_hash_as_identity():
    # No API here issues an auth permit: a hash can only detect tampering.
    item = validate_wire(legacy(), raw_legacy=LEGACY)
    assert "signature" not in item
    assert "issuer" not in item
    error("OLD_READER_REQUIRES_GATEWAY_NO_FALLBACK",
          lambda: negotiate_reader(legacy(), raw_legacy=LEGACY,
                                   supported={LEGACY_NS: {VERSION}},
                                   understood_sidecars={"ar02.effective-auth"},
                                   old_native_reader=True))


def test_x02_x03_missing_mandatory_read_authority_fail_closed():
    error("UNKNOWN_REQUIRED_AUTHORITY_NO_DOWNGRADE",
          lambda: negotiate_reader(legacy(), raw_legacy=LEGACY,
                                   supported={LEGACY_NS: {VERSION}},
                                   understood_sidecars=set()))
    error("READER_UNSUPPORTED_NO_DOWNGRADE",
          lambda: negotiate_reader(legacy(), raw_legacy=LEGACY,
                                   supported={LEGACY_NS: {"0.9.0"}},
                                   understood_sidecars={"ar02.effective-auth"}))


def test_x04_field_hash_and_head_checkpoint_binding():
    item = json.loads(legacy())
    item["checkpoint"]["seq"] = 9
    error("FIELD_HASH_MISMATCH", lambda: validate_wire(
        json.dumps(item, sort_keys=True, separators=(",", ":")).encode(), raw_legacy=LEGACY))
    item = json.loads(legacy())
    item["envelope_digest"] = "0" * 64
    error("ENVELOPE_HASH_MISMATCH", lambda: validate_wire(
        json.dumps(item, sort_keys=True, separators=(",", ":")).encode(), raw_legacy=LEGACY))


def test_x05_postterminal_notice_cursor_and_head_only_new_record():
    item = validate_wire(new())
    assert item["body"]["original_terminal_head_hash"] == HEAD
    assert item["body"]["notice_seq"] == item["body"]["client_cursor"] == 1
    assert "legacy_ref" not in item
    bad = json.loads(new())
    bad["body"]["client_cursor"] = 2
    error("NOTICE_CURSOR", lambda: validate_wire(
        json.dumps(bad, sort_keys=True, separators=(",", ":")).encode()))


def test_x06_revocation_generation_negative():
    error("REVOCATION_GENERATION", lambda: new(
        kind="revocation", body={
            "exclusion_generation": 0, "subject_ref": "subject-1",
            "reason_code": "withdrawn",
        }))
    error("GENERATION_UNBOUND", lambda: legacy(revocation_generation=-1))


def test_x07_billing_unknown_is_explicit_not_zero():
    valid = new(kind="billing",
                body={"charge_id": "charge-1", "billing_status": "UNKNOWN",
                      "usage_ref": "usage-1"})
    assert validate_wire(valid)["body"]["billing_status"] == "UNKNOWN"
    error("BILLING_STATUS", lambda: new(
        kind="billing", body={"charge_id": "charge-1", "billing_status": "ZERO",
                              "usage_ref": "usage-1"}))


def test_x08_x09_identity_binding_and_native_no_mutation():
    assert validate_wire(legacy(), raw_legacy=LEGACY)["tenant_id"] == "tenant-1"
    error("ENVELOPE_HASH_MISMATCH",
          lambda: validate_wire(tamper(legacy(), tenant_id="tenant-2"), raw_legacy=LEGACY))
    accepted = negotiate_reader(legacy(), raw_legacy=LEGACY,
                                supported={LEGACY_NS: {VERSION}},
                                understood_sidecars={"ar02.effective-auth"})
    assert accepted["record_type"] == "legacy-bound"
    assert negotiate_reader(new(), supported={NEW_NS: {VERSION}},
                            understood_sidecars=set())["record_type"] == "new-record"


def test_x09_new_record_downgrade_never_accepted_by_old_reader():
    error("READER_UNSUPPORTED_NO_DOWNGRADE",
          lambda: negotiate_reader(new(), supported={LEGACY_NS: {VERSION}},
                                   understood_sidecars=set()))
    error("OLD_READER_REQUIRES_GATEWAY_NO_FALLBACK",
          lambda: negotiate_reader(new(), supported={NEW_NS: {VERSION}},
                                   understood_sidecars=set(), old_native_reader=True))


def test_static_golden_vector_pinned_and_independent_node_oracle():
    vectors = json.loads(DATA.read_text())
    wires = {
        "legacy": legacy(),
        "postterminal": new(),
        "revocation": new(kind="revocation", body={
            "exclusion_generation": 5, "subject_ref": "subject-1",
            "reason_code": "consent-withdrawn",
        }),
        "billing_unknown": new(kind="billing", body={
            "charge_id": "charge-1", "billing_status": "UNKNOWN",
            "usage_ref": "usage-1",
        }),
    }
    assert set(wires) == set(vectors)
    for name, raw in wires.items():
        assert raw.hex() == vectors[name]["wire_hex"]
        assert hashlib.sha256(raw).hexdigest() == vectors[name]["wire_sha256"]
        assert json.loads(raw)["envelope_digest"] == vectors[name]["envelope_digest"]
    result = subprocess.run(["node", str(NODE), str(DATA)], check=True,
                            capture_output=True, text=True, timeout=15)
    assert json.loads(result.stdout) == {"verified": 4, "errors": 0}


@pytest.mark.parametrize("field,bad,code", [
    ("record_type", ["legacy-bound"], "ENVELOPE_FIELDS_OR_KIND"),
    ("checkpoint", [], "CHECKPOINT_FIELD_SET"),
])
def test_malformed_authenticity_fields_fail_closed(field, bad, code):
    error(code, lambda: validate_wire(tamper(legacy(), **{field: bad}), raw_legacy=LEGACY))


def test_notice_boolean_cursor_rejected_and_type_namespace_confusion_rejected():
    item = json.loads(new())
    item["body"]["client_cursor"] = True
    error("NOTICE_CURSOR", lambda: validate_wire(
        json.dumps(item, sort_keys=True, separators=(",", ":")).encode()))
    item = json.loads(new())
    item["new_record_namespace"] = "ar02.billing-ledger"
    error("NEW_RECORD_KIND_OR_NAMESPACE", lambda: validate_wire(
        json.dumps(item, sort_keys=True, separators=(",", ":")).encode()))
