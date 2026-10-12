"""A26 offline mutation fixtures: synthetic crypto never grants external authority."""
from __future__ import annotations

import base64
import copy
import itertools

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine.m27_w5_a26_external_authority_native_app_v1_experimental import (
    NOT_PROVISIONED,
    AuthorityDenied,
    claim_nonce,
    cohort_integrity,
    digest,
    loads_strict,
    observe_client_chunks,
    verify_signed_authority,
)
from knowledge_engine.m27_w5_c24_client_observation_v1_experimental import (
    CasePlan,
    SourcePin,
    make_test_frame,
)
from knowledge_engine.m27_w5_n25_native_client_trial_v1_experimental import AppAttachment

NOW = 1_000_000


def assignments(purpose="current523"):
    counts = ({
        "live_cited": 237, "live_safe_abstain": 52,
        "live_preprovider_deny": 52, "replay_budget": 26,
        "replay_invariant": 26, "replay_governance": 130,
    } if purpose == "current523" else {"blind": 200})
    return ([{"case_id": f"synthetic-{role}-{i:03}", "role": role}
             for role, n in counts.items() for i in range(n)], counts)


def fixtures(purpose="current523"):
    roster, counts = assignments(purpose)
    h = digest({"fixture": "synthetic"})
    payload = {
        "schema": "m27.w5.a26.signed_evaluation_authority.v1",
        "purpose": purpose, "run_id": "test-run", "nonce": "test-nonce",
        "app_id": "fixture-native-app", "endpoint_id": "fixture-loopback",
        "issued_at": NOW - 100, "expires_at": NOW + 1000,
        "revocation_checked_at": NOW, "revoked": False,
        "candidate_image_sha256": h, "runner_sha256": h,
        "app_build_sha256": h, "client_instrumentation_sha256": h,
        "source_roster_sha256": h, "source_revision_index_sha256": h,
        "source_rights_grant_sha256": h, "rubric_sha256": h,
        "assignment_roster_sha256": digest(roster),
        "assignments": roster, "role_counts": counts,
        "rights": {
            "consent": True, "revoked": False,
            "permission_scope": "nonprod_evaluation",
            "retention_expires_at": NOW + 1000,
            "source_revision_index_sha256": h,
        },
        "budget": {
            "max_cost_cents": 100, "max_attempts": len(roster),
            "provider_price_attestation_sha256": h,
        },
        "one_shot": True, "nonproduction": True,
        "unseen_independent": purpose == "phaseb200",
    }
    roles = [
        "source_rights", "app_controller", "evaluation_controller", "grader",
        "native_observer", "candidate_builder", "budget_controller",
    ]
    if purpose == "phaseb200":
        roles.append("blind_custodian")
    registry = {"schema": "m27.w5.external_trust_roots.v1",
                "independent_issuer": True, "roots": []}
    signatures = []
    keys = {}
    for role in roles:
        key = Ed25519PrivateKey.generate()
        keys[role] = key
        key_id = "fixture-" + role
        pub = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        registry["roots"].append({
            "key_id": key_id, "public_key_b64": base64.b64encode(pub).decode(),
            "roles": [role], "not_before": NOW - 100,
            "expires_at": NOW + 1000, "revoked": False,
        })
        signatures.append({
            "role": role, "key_id": key_id,
            "signature_b64": base64.b64encode(key.sign(
                __import__("knowledge_engine.m27_w5_c24_client_observation_v1_experimental",
                           fromlist=["canonical"]).canonical(payload)
            )).decode(),
        })
    packet = {"payload": payload, "signatures": signatures}
    return packet, registry, keys


def check(packet, registry, *, now=NOW, pin_packet=None, pin_registry=None):
    return verify_signed_authority(
        packet, registry,
        packet_sha256_from_independent_channel=(
            digest(packet) if pin_packet is None else pin_packet
        ),
        registry_sha256_from_independent_channel=(
            digest(registry) if pin_registry is None else pin_registry
        ),
        now=now,
    )


def test_absent_authority_denies_without_network():
    result = verify_signed_authority(
        None, None, packet_sha256_from_independent_channel=None,
        registry_sha256_from_independent_channel=None, now=NOW,
    )
    assert result["status"] == NOT_PROVISIONED
    assert result["external_call_permitted"] is False


@pytest.mark.parametrize("purpose", ["current523", "phaseb200"])
def test_local_signatures_prove_only_mechanics_not_rights(purpose):
    packet, registry, _ = fixtures(purpose)
    r = check(packet, registry)
    assert r["status"] == "A26_MECHANICAL_SIGNATURE_PREFLIGHT_ONLY"
    assert r["mechanical_signatures_verified"] is True
    assert r["independent_real_world_authority_admitted"] is False
    assert r["external_call_permitted"] is False
    assert r["official_e26_pass"] is False and r["official_b26_pass"] is False
    assert r["w5_full_complete"] is False


@pytest.mark.parametrize("change", [
    "missing_signer", "alter_payload", "wrong_registry_pin", "wrong_packet_pin",
    "expired", "stale_revocation", "source_revoked", "missing_consent",
    "bad_scope", "roster_522", "duplicate_case", "wrong_roster_digest",
    "wrong_candidate", "budget_missing", "wrong_attempts", "unsafe_endpoint",
    "self_signer_role", "key_revoked", "nonce_blank", "wrong_schema",
])
def test_tampered_or_untrusted_inputs_fail_closed(change):
    packet, registry, _ = fixtures()
    original_packet_pin = digest(packet)
    original_registry_pin = digest(registry)
    p = packet["payload"]
    if change == "missing_signer":
        packet["signatures"].pop()
    elif change == "alter_payload":
        p["app_id"] = "different-app"
    elif change == "wrong_registry_pin":
        registry["roots"][0]["key_id"] = "untrusted"
    elif change == "wrong_packet_pin":
        packet["signatures"][0]["signature_b64"] = "abc"
    elif change == "expired":
        p["expires_at"] = NOW
    elif change == "stale_revocation":
        p["revocation_checked_at"] = NOW - 7200
    elif change == "source_revoked":
        p["rights"]["revoked"] = True
    elif change == "missing_consent":
        p["rights"]["consent"] = False
    elif change == "bad_scope":
        p["rights"]["permission_scope"] = "production"
    elif change == "roster_522":
        p["assignments"].pop()
    elif change == "duplicate_case":
        p["assignments"][0]["case_id"] = p["assignments"][1]["case_id"]
    elif change == "wrong_roster_digest":
        p["assignment_roster_sha256"] = digest({"wrong": "roster"})
    elif change == "wrong_candidate":
        p["candidate_image_sha256"] = "not-a-digest"
    elif change == "budget_missing":
        p["budget"]["provider_price_attestation_sha256"] = None
    elif change == "wrong_attempts":
        p["budget"]["max_attempts"] = 1
    elif change == "unsafe_endpoint":
        p["endpoint_id"] = "https://fixture.example/token"
    elif change == "self_signer_role":
        packet["signatures"][1]["key_id"] = packet["signatures"][0]["key_id"]
    elif change == "key_revoked":
        registry["roots"][0]["revoked"] = True
    elif change == "nonce_blank":
        p["nonce"] = ""
    elif change == "wrong_schema":
        p["schema"] = "arbitrary.v1"
    r = check(packet, registry, pin_packet=original_packet_pin,
              pin_registry=original_registry_pin)
    assert r["status"] == NOT_PROVISIONED
    assert r["external_call_permitted"] is False


@pytest.mark.parametrize("bad", [
    b'{"same": 1, "same": 2}', b'{"bad":NaN}', b'{"bad":Infinity}',
])
def test_json_rejects_duplicate_and_nonfinite(bad):
    with pytest.raises(AuthorityDenied):
        loads_strict(bad)


def test_private_replay_nonce_claim_is_one_shot(tmp_path):
    tmp_path.chmod(0o700)
    digest_one = claim_nonce(tmp_path, "synthetic-run", "synthetic-nonce")
    assert len(digest_one) == 64
    assert list(tmp_path.iterdir())[0].stat().st_mode & 0o777 == 0o600
    with pytest.raises(AuthorityDenied, match="REPLAY_NONCE_CONSUMED"):
        claim_nonce(tmp_path, "synthetic-run", "synthetic-nonce")


def test_world_accessible_claim_root_fails(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(AuthorityDenied, match="PRIVATE_CLAIM_DIRECTORY_REQUIRED"):
        claim_nonce(tmp_path, "case", "nonce")


def test_structural_523_full_denominator_does_not_award_authentication():
    roster, _ = assignments()
    receipts = []
    for row in roster:
        r = {
            "case_id": row["case_id"],
            "n25_schema": "m27.w5.n25.native_client_trial.v1",
            "synthetic": False, "status": "COMPLETE",
            "request_admitted_ns": 0, "first_substantive_text_ns": 1_000_000,
            "terminal_ns": 5_000_000, "client_closed_ns": 7_000_000,
            "outcome_latency_ms": 5.0,
            "source_native_citations": [{
                "revision": "fixture-r1",
                "source_sha256": digest("synthetic-source"),
                "quote_sha256": digest("synthetic-span"),
                "source_start": 0, "source_end": 10,
            }] if row["role"] == "live_cited" else [],
        }
        receipts.append({"client_receipt": r, "client_receipt_sha256": digest(r)})
    result = cohort_integrity(roster, receipts, "current523")
    assert result["status"] == "A26_LOCAL_CLIENT_RECEIPTS_STRUCTURALLY_COMPLETE_ONLY"
    assert result["all_outcome_nearest_rank"] == 324
    assert result["cited_expected_nearest_rank"] == 226
    assert result["official_qualified"] is False
    assert result["independent_client_ack_verified"] is False
    receipts.pop()
    assert cohort_integrity(roster, receipts, "current523")["all_outcome_p95_ms"] is None


def test_tampered_native_receipt_fails_closed():
    roster, _ = assignments("phaseb200")
    r = {"case_id": roster[0]["case_id"], "n25_schema": "m27.w5.n25.native_client_trial.v1",
         "synthetic": False, "status": "COMPLETE", "request_admitted_ns": 1,
         "client_closed_ns": 2, "terminal_ns": 2, "outcome_latency_ms": 1e-6}
    entry = {"client_receipt": r, "client_receipt_sha256": digest(r)}
    r["status"] = "ERROR"
    assert cohort_integrity(roster, [entry], "phaseb200")["status"] == (
        "A26_INCOMPLETE_CLIENT_CUSTODY"
    )


def test_real_client_aware_fixture_recv_capture_and_missing_terminal():
    raw = b"Authorized fixture citation source"
    h = __import__("hashlib").sha256
    source = SourcePin("citation-1", "source-1", "fixture-r1",
                       h(raw).hexdigest(), raw, authorized=True)
    case = CasePlan("fixture-case", "request-1", "nonce-1",
                    h(b"runner").hexdigest(), h(b"candidate").hexdigest(), True)
    attachment = AppAttachment("fixture-app", h(b"app").hexdigest(),
                               h(b"instrument").hexdigest(), "fixture-loopback")
    common = {
        "case_id": case.case_id, "request_id": case.request_id,
        "nonce": case.nonce, "runner_sha256": case.runner_sha256,
        "candidate_sha256": case.candidate_sha256,
    }
    answer = b"Fixture cited answer"
    cited = {
        "citation_id": source.citation_id, "source_id": source.source_id,
        "revision": source.revision, "source_sha256": source.source_sha256,
        "source_start": 0, "source_end": len(raw),
        "quote_sha256": h(raw).hexdigest(), "answer_start": 0,
        "answer_end": len(answer),
    }
    frames = [
        b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream; charset=utf-8\r\n\r\n",
        make_test_frame("progress", {**common, "phase": "preparing"}),
        make_test_frame("answer", {**common, "sequence": 0, "start": 0,
                                  "end": len(answer), "sha256": h(answer).hexdigest(),
                                  "text": answer.decode(), "citations": [cited]}),
        make_test_frame("terminal", {**common, "status": "completed",
                                    "answer_bytes": len(answer),
                                    "answer_sha256": h(answer).hexdigest()}),
    ]
    result = observe_client_chunks(
        case, [source], attachment, frames,
        clock_ns=itertools.count(1_000_000, 1_000_000).__next__,
    )
    receipt = result["client_receipt"]
    assert receipt["status"] == "COMPLETE", receipt["errors"]
    assert receipt["first_substantive_before_terminal"] is True
    assert receipt["progress_events"] == 1
    assert len(receipt["source_native_citations"]) == 1
    assert result["official_qualified"] is False
    fault = observe_client_chunks(
        case, [source], attachment, frames[:2],
        clock_ns=itertools.count(1_000_000, 1_000_000).__next__,
        close_reason="timeout",
    )
    assert fault["client_receipt"]["status"] == "TIMEOUT"
    assert fault["client_receipt"]["full_final_answer_latency_ms"] is None
    assert fault["official_qualified"] is False


def test_phaseb_negative_missing_blind_custodian_signature():
    packet, registry, _ = fixtures("phaseb200")
    packet["signatures"] = [x for x in packet["signatures"]
                            if x["role"] != "blind_custodian"]
    assert check(packet, registry)["status"] == NOT_PROVISIONED


def test_local_fixture_signed_grant_cannot_authorize_a_real_call():
    packet, registry, _ = fixtures()
    copy_packet = copy.deepcopy(packet)
    assert check(copy_packet, registry)["external_call_permitted"] is False


@pytest.mark.parametrize("mutation", ["valid", "wrong_key", "wrong_pin", "tamper",
                                      "expired", "revoked", "clock", "missing"])
def test_native_observer_external_ack_crypto_is_not_self_admission(mutation):
    from knowledge_engine.m27_w5_a26_external_authority_native_app_v1_experimental import (
        sha256,
        verify_independent_client_ack,
    )
    from knowledge_engine.m27_w5_c24_client_observation_v1_experimental import canonical

    pub_priv = Ed25519PrivateKey.generate()
    key = pub_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    base = {
        "case_id": "fixture-1", "request_id": "request-1", "nonce": "nonce-1",
        "status": "COMPLETE", "terminal_ns": 100, "client_closed_ns": 101,
        "source_native_citations": [{"revision": "fixture", "source_sha256": digest("x")}],
    }
    wrapped = {"client_receipt": base, "client_receipt_sha256": digest(base)}
    payload = {
        "schema": "m27.w5.a26.independent_client_ack.v1",
        "observer_role": "native_observer", "observer_key_id": "observer-1",
        "case_id": base["case_id"], "request_id": base["request_id"],
        "nonce": base["nonce"], "status": base["status"],
        "client_receipt_sha256": digest(base),
        "source_native_citations_sha256": digest(base["source_native_citations"]),
        "terminal_ns": base["terminal_ns"], "client_closed_ns": base["client_closed_ns"],
        "issued_at": NOW - 100, "expires_at": NOW + 1000, "revoked": False,
    }
    ack = {"payload": payload, "signature_b64": base64.b64encode(
        pub_priv.sign(canonical(payload))).decode()}
    pin = sha256(key)
    if mutation == "wrong_key":
        key = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        pin = sha256(key)
    elif mutation == "wrong_pin":
        pin = digest("not-observer")
    elif mutation == "tamper":
        payload["client_receipt_sha256"] = digest("tampered")
    elif mutation == "expired":
        payload["expires_at"] = NOW
    elif mutation == "revoked":
        payload["revoked"] = True
    elif mutation == "clock":
        payload["client_closed_ns"] = 9999
    elif mutation == "missing":
        ack = None
    result = verify_independent_client_ack(
        wrapped, ack,
        trusted_observer_public_b64=base64.b64encode(key).decode(),
        trusted_observer_public_sha256=pin,
        expected_observer_key_id="observer-1", now=NOW,
    )
    if mutation == "valid":
        assert result["status"] == "A26_ACK_CRYPTO_VERIFIED_EXTERNAL_ADMISSION_REQUIRED"
        assert result["mechanical_ack_signature_verified"]
    else:
        assert result["status"] == "A26_CLIENT_ACK_NOT_PROVISIONED"
    assert result["independent_real_world_ack_admitted"] is False
    assert result["official_qualified"] is False
