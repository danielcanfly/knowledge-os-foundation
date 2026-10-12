"""Synthetic E24 calibration; deliberately NEVER an official original-523 run."""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine import m27_w5_e24_original523_evidence_scorer_v1_experimental as e24

NOW = datetime(2026, 10, 12, tzinfo=UTC)
DUMMY_SHA = "a" * 64
ROLES = ("rights_issuer", "evaluator", "observer", "source_verifier", "grader")


@pytest.fixture(scope="module")
def private_fixture():
    keys = {role: Ed25519PrivateKey.generate() for role in ROLES}
    registry = {"schema": e24.REGISTRY_VERSION, "roots": {
        role: {
            "key_id": f"e24-fixture-{role}",
            "role": role,
            "principal": f"fixture-person-{role}",
            "tier": "SYNTHETIC_FIXTURE",
            "public_key_hex": keys[role].public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ).hex(),
        } for role in ROLES
    }}

    def sign(payload, role):
        return {"payload": payload, "signature": {
            "key_id": registry["roots"][role]["key_id"],
            "signature_hex": keys[role].sign(e24.canonical(payload)).hex(),
        }}

    roster = {"schema": e24.ROSTER_VERSION, "cases": []}
    for (mode, expectation), n in e24.BUCKETS.items():
        for _ in range(n):
            roster["cases"].append({
                "case_id": f"fixture-e24-{len(roster['cases']):03d}",
                "mode": mode, "expectation": expectation,
            })
    run = "synthetic.20261012.e24"
    entries = []
    for case in roster["cases"]:
        cid, mode, expectation = (
            case["case_id"], case["mode"], case["expectation"]
        )
        answer_sha = e24.sha({"synthetic-answer-for": cid})
        src = None
        status = {
            "verified_cited_answer": "COMPLETE_CITED_FINAL",
            "safe_abstention": "SAFE_ABSTENTION",
            "rejected_before_provider": "REJECTED_BEFORE_PROVIDER",
        }.get(expectation, "REPLAY_PASS")
        grade = {
            "case_id": cid, "run_id": run, "answer_sha256": answer_sha,
            "source_claim_sha256": None, "score": None,
            "critical_error": False, "pass": True, "category": expectation,
        }
        if expectation == "verified_cited_answer":
            proof = {
                "case_id": cid, "run_id": run, "answer_sha256": answer_sha,
                "source_sha256": e24.sha({"fixture-source": cid}),
                "revision": "synthetic-r1", "span_start": 10, "span_end": 30,
                "source_index_sha256": "b" * 64,
                "permission_grant_sha256": "c" * 64, "valid": True,
            }
            src = sign(proof, "source_verifier")
            grade["source_claim_sha256"] = e24.sha(proof)
            grade["score"] = 85
        timing = (
            {"start_ns": 1000000, "end_ns": 2000000,
             "first_substantive_ns": 1500000 if status ==
             "COMPLETE_CITED_FINAL" else None}
            if mode == "live" else None
        )
        entries.append({
            **case, "status": status, "timing": timing,
            "client_complete": mode == "live",
            "client_ack_sha256": e24.sha({"fixture-client": cid})
            if mode == "live" else None,
            "answer_sha256": answer_sha,
            "provider_dispatch_count": 0,
            "provider_telemetry_proven": True,
            "authority_trace_sha256": e24.sha({"fixture-trace": cid}),
            "leak_detected": False,
            "source_assertion": src,
            "grader_assertion": sign(grade, "grader"),
        })
    outcome_payload = {
        "run_id": run,
        "candidate_image_sha256": "d" * 64,
        "roster_sha256": e24.sha(roster),
        "receipts": entries,
    }
    outcomes = {"schema": e24.OUTCOMES_VERSION,
                "signed": sign(outcome_payload, "observer")}
    manifest_payload = {
        "source_corpus_sha256": e24.HISTORICAL_SHA256,
        "roster_sha256": e24.sha(roster),
        "outcomes_sha256": e24.sha(outcomes),
        "official_run_id": run,
        "purpose": "ORIGINAL523_CURRENT_EVALUATION_ONE_SHOT",
        "mode_counts": {
            f"{m}/{b}": n for (m, b), n in e24.BUCKETS.items()
        },
        "rights_grant_sha256": "c" * 64,
        "rubric_sha256": "e" * 64, "source_index_sha256": "b" * 64,
        "image_sha256": "d" * 64, "runner_sha256": "f" * 64,
        "build_sha256": "1" * 64,
        "client_instrumentation_sha256": "2" * 64,
        "candidate_git40": "3" * 40, "candidate_tree40": "4" * 40,
        "license_scope": "EVALUATION_ONLY",
        "independent_native_client": True, "independent_grader": True,
        "issued_at_utc": "2026-10-01T00:00:00Z",
        "expires_at_utc": "2026-11-01T00:00:00Z",
    }
    manifest = {
        "schema": e24.VERSION, "contract_status": "APPROVED",
        "payload": manifest_payload,
        "signatures": {
            role: sign(manifest_payload, role)["signature"]
            for role in ("rights_issuer", "evaluator")
        },
    }
    return manifest, roster, outcomes, registry, sign


def get_payload(private_fixture):
    manifest, roster, outcomes, registry, sign = private_fixture
    return (copy.deepcopy(manifest), copy.deepcopy(roster),
            copy.deepcopy(outcomes), copy.deepcopy(registry), sign)


def reseal(manifest, roster, outcomes, sign):
    data = outcomes["signed"]["payload"]
    data["roster_sha256"] = e24.sha(roster)
    outcomes["signed"] = sign(data, "observer")
    mp = manifest["payload"]
    mp["roster_sha256"] = e24.sha(roster)
    mp["outcomes_sha256"] = e24.sha(outcomes)
    manifest["signatures"] = {
        role: sign(mp, role)["signature"]
        for role in ("rights_issuer", "evaluator")
    }


def evaluate(*items):
    manifest, roster, outcomes, registry, _ = items
    return e24.evaluate(manifest, roster, outcomes, registry,
                        e24.sha(registry), now=NOW)


def current(*items):
    return items[2]["signed"]["payload"]["receipts"]


def resign_grade(case, sign):
    case["grader_assertion"] = sign(
        case["grader_assertion"]["payload"], "grader"
    )


def resign_source(case, sign):
    case["source_assertion"] = sign(
        case["source_assertion"]["payload"], "source_verifier"
    )
    case["grader_assertion"]["payload"]["source_claim_sha256"] = e24.sha(
        case["source_assertion"]["payload"]
    )
    resign_grade(case, sign)


def asserted_failure(items, expected):
    manifest, roster, outcomes, _, sign = items
    reseal(manifest, roster, outcomes, sign)
    result = evaluate(*items)
    assert result["status"] == "SYNTHETIC_CALIBRATION_ONLY"
    assert result["official_523_run_certified"] is False
    # A single cited-final failure can still clear the *proposed* 226/237 gate.
    # Qualification and the aggregate release-threshold predicate are distinct.
    assert expected in {d["reason"] for d in result["reasons_by_case"]}
    return result


def test_523_synthetic_calibration_not_official(private_fixture):
    result = evaluate(*get_payload(private_fixture))
    assert result["status"] == "SYNTHETIC_CALIBRATION_ONLY"
    assert result["all_draft_gates_met"]
    assert result["counts"] == {
        "assigned": 523, "live": 341, "replay": 182,
        "cited_qualified": 237, "cited_denominator": 237,
        "safe_qualified": 52, "safe_denominator": 52,
        "preprovider_qualified": 52, "preprovider_denominator": 52,
        "replay_qualified": 182, "replay_denominator": 182,
        "outcomes_supplied": 523,
    }
    assert result["p95_ms"] == {"live341": 1.0, "cited237": 1.0}
    assert all(v is False for k, v in result.items()
               if k.endswith("_authorized") or k.endswith("_certified"))
    assert len(result["reasons_by_case"]) == 523
    assert "case_id" not in str(result["reasons_by_case"])


@pytest.mark.parametrize("bad", [
    "DRAFT_NOT_APPROVED", "DRAFT", "SUPERSEDED", "", None,
])
def test_draft_manifest_rejected(private_fixture, bad):
    items = get_payload(private_fixture)
    items[0]["contract_status"] = bad
    with pytest.raises(e24.Denied, match="DRAFT_OR_UNAPPROVED_CONTRACT"):
        evaluate(*items)


@pytest.mark.parametrize("kind", [
    "duplicate_case", "wrong_mode", "drop_case", "add_case",
    "extra_question", "incorrect_expectation",
])
def test_roster_denominator_mutation(private_fixture, kind):
    items = get_payload(private_fixture)
    cases = items[1]["cases"]
    if kind == "duplicate_case":
        cases[1]["case_id"] = cases[0]["case_id"]
    elif kind == "wrong_mode":
        cases[0]["mode"] = "replay"
    elif kind == "drop_case":
        cases.pop()
    elif kind == "add_case":
        cases.append(copy.deepcopy(cases[0]))
    elif kind == "extra_question":
        cases[0]["question"] = "forbidden synthetic fixture text"
    else:
        cases[0]["expectation"] = "governance_contract"
    reseal(items[0], items[1], items[2], items[4])
    with pytest.raises(e24.Denied):
        evaluate(*items)


@pytest.mark.parametrize("index", range(24))
def test_quality_below_85_fails_independently(private_fixture, index):
    items = get_payload(private_fixture)
    entry = current(*items)[index]
    entry["grader_assertion"]["payload"]["score"] = 84 - index
    resign_grade(entry, items[4])
    result = asserted_failure(items, "INDEPENDENT_QUALITY_BELOW_85_OR_CRITICAL")
    assert result["counts"]["cited_qualified"] == 236


@pytest.mark.parametrize("index", range(24, 48))
def test_wrong_source_permission_span_or_revision(private_fixture, index):
    items = get_payload(private_fixture)
    entry = current(*items)[index]
    source = entry["source_assertion"]["payload"]
    if index % 4 == 0:
        source["span_end"] = source["span_start"]
    elif index % 4 == 1:
        source["permission_grant_sha256"] = "0" * 64
    elif index % 4 == 2:
        source["source_index_sha256"] = "9" * 64
    else:
        source["revision"] = ""
    resign_source(entry, items[4])
    result = asserted_failure(items, "SOURCE_NATIVE_SPAN_REVISION_PERMISSION_INVALID")
    assert result["counts"]["cited_qualified"] == 236


@pytest.mark.parametrize("index", range(237, 253))
def test_preprovider_proof_and_unauthorized_dispatch(private_fixture, index):
    items = get_payload(private_fixture)
    entry = current(*items)[index + 52]
    variant = index - 237
    if variant % 4 == 0:
        entry["provider_dispatch_count"] = variant + 1
    elif variant % 4 == 1:
        entry["provider_telemetry_proven"] = False
    elif variant % 4 == 2:
        entry["authority_trace_sha256"] = None
    else:
        entry["provider_dispatch_count"] = None
    result = asserted_failure(items, "PROVIDER_DISPATCH_NOT_INDEPENDENTLY_ZERO")
    assert result["counts"]["preprovider_qualified"] == 51


@pytest.mark.parametrize("index", range(341, 353))
def test_replay_never_pads_live_numerator(private_fixture, index):
    items = get_payload(private_fixture)
    entry = current(*items)[index]
    entry["grader_assertion"]["payload"]["pass"] = False
    resign_grade(entry, items[4])
    result = asserted_failure(items, "REPLAY_CONTROL_FAILED")
    assert result["counts"]["cited_qualified"] == 237
    assert result["counts"]["replay_qualified"] == 181


@pytest.mark.parametrize("mutation,expected", [
    ("critical", "INDEPENDENT_QUALITY_BELOW_85_OR_CRITICAL"),
    ("no_first_text", "CLIENT_PRETERMINAL_SUBSTANTIVE_ACK_MISSING"),
    ("progress_only", "CLIENT_PRETERMINAL_SUBSTANTIVE_ACK_MISSING"),
    ("no_client_ack", "CLIENT_PRETERMINAL_SUBSTANTIVE_ACK_MISSING"),
    ("not_client_complete", "CLIENT_PRETERMINAL_SUBSTANTIVE_ACK_MISSING"),
    ("wrong_terminal", "NO_COMPLETE_CITED_FINAL"),
    ("missing_latency", "CLIENT_LATENCY_UNKNOWN"),
    ("protected_leak", "PROTECTED_ANSWER_LEAK_OR_UNKNOWN"),
    ("leak_unknown", "PROTECTED_ANSWER_LEAK_OR_UNKNOWN"),
    ("unknown_quality", "INDEPENDENT_QUALITY_BELOW_85_OR_CRITICAL"),
    ("unverified_span", "SOURCE_NATIVE_SPAN_REVISION_PERMISSION_INVALID"),
])
def test_cited_terminal_faults(private_fixture, mutation, expected):
    items = get_payload(private_fixture)
    entry = current(*items)[12]
    if mutation == "critical":
        entry["grader_assertion"]["payload"]["critical_error"] = True
    elif mutation == "no_first_text":
        entry["timing"]["first_substantive_ns"] = None
    elif mutation == "progress_only":
        entry["timing"]["first_substantive_ns"] = entry["timing"]["end_ns"]
    elif mutation == "no_client_ack":
        entry["client_ack_sha256"] = None
    elif mutation == "not_client_complete":
        entry["client_complete"] = False
    elif mutation == "wrong_terminal":
        entry["status"] = "WRONG_ABSTENTION"
    elif mutation == "missing_latency":
        entry["timing"] = None
    elif mutation == "protected_leak":
        entry["leak_detected"] = True
    elif mutation == "leak_unknown":
        entry["leak_detected"] = None
    elif mutation == "unknown_quality":
        entry["grader_assertion"]["payload"]["score"] = None
    elif mutation == "unverified_span":
        entry["source_assertion"]["payload"]["valid"] = False
        resign_source(entry, items[4])
    if mutation in {"critical", "unknown_quality"}:
        resign_grade(entry, items[4])
    result = asserted_failure(items, expected)
    assert result["counts"]["cited_qualified"] == 236


def test_226_of_237_pass_boundary(private_fixture):
    items = get_payload(private_fixture)
    for i in range(11):
        entry = current(*items)[i]
        entry["status"] = "TIMEOUT"
    reseal(items[0], items[1], items[2], items[4])
    result = evaluate(*items)
    assert result["counts"]["cited_qualified"] == 226
    assert result["gates"]["cited_at_least_226_of_237"]


def test_225_of_237_fails_boundary(private_fixture):
    items = get_payload(private_fixture)
    for i in range(12):
        current(*items)[i]["status"] = "TIMEOUT"
    reseal(items[0], items[1], items[2], items[4])
    result = evaluate(*items)
    assert result["counts"]["cited_qualified"] == 225
    assert not result["gates"]["cited_at_least_226_of_237"]


@pytest.mark.parametrize("missing", [1, 2, 10])
def test_missing_outcome_keeps_denominator(private_fixture, missing):
    items = get_payload(private_fixture)
    del current(*items)[:missing]
    result = asserted_failure(items, "MISSING_SIGNED_CURRENT_OUTCOME")
    assert result["counts"]["assigned"] == 523
    assert result["counts"]["outcomes_supplied"] == 523 - missing
    assert result["p95_ms"]["live341"] is None


@pytest.mark.parametrize("bad", [
    "duplicate_receipt", "unknown_id", "extra_raw_answer",
    "replay_timing", "bad_status", "wrong_expectation",
])
def test_outcome_structural_refusal(private_fixture, bad):
    items = get_payload(private_fixture)
    entries = current(*items)
    if bad == "duplicate_receipt":
        entries.append(copy.deepcopy(entries[0]))
    elif bad == "unknown_id":
        entries[0]["case_id"] = "not-in-frozen-cohort"
    elif bad == "extra_raw_answer":
        entries[0]["hidden_answer"] = "must never accept this field"
    elif bad == "replay_timing":
        entries[-1]["timing"] = entries[0]["timing"]
    elif bad == "bad_status":
        entries[0]["status"] = "HTTP_200_NOT_GRADED"
    else:
        entries[0]["expectation"] = "budget_terminal"
    reseal(items[0], items[1], items[2], items[4])
    if bad in {"duplicate_receipt", "unknown_id", "extra_raw_answer",
               "replay_timing", "bad_status", "wrong_expectation"}:
        with pytest.raises(e24.Denied):
            evaluate(*items)


@pytest.mark.parametrize("target", [
    "rights_issuer", "evaluator", "observer", "grader", "source_verifier",
])
def test_missing_independent_signature(private_fixture, target):
    items = get_payload(private_fixture)
    if target in {"rights_issuer", "evaluator"}:
        items[0]["signatures"][target]["signature_hex"] = "0" * 128
    elif target == "observer":
        items[2]["signed"]["signature"]["signature_hex"] = "0" * 128
        items[0]["payload"]["outcomes_sha256"] = e24.sha(items[2])
        for role in ("rights_issuer", "evaluator"):
            items[0]["signatures"][role] = items[4](
                items[0]["payload"], role
            )["signature"]
    elif target == "grader":
        current(*items)[0]["grader_assertion"]["signature"]["signature_hex"] = (
            "0" * 128
        )
        reseal(items[0], items[1], items[2], items[4])
    else:
        current(*items)[0]["source_assertion"]["signature"]["signature_hex"] = (
            "0" * 128
        )
        reseal(items[0], items[1], items[2], items[4])
    with pytest.raises(e24.Denied, match="SIGNATURE_VERIFICATION_FAILED"):
        evaluate(*items)


@pytest.mark.parametrize("tamper", [
    "source_corpus", "image", "rubric", "roster", "contract",
    "license", "run_id", "status", "mode_counts", "expired",
])
def test_unsigned_or_mismatched_approval(private_fixture, tamper):
    items = get_payload(private_fixture)
    mp = items[0]["payload"]
    if tamper == "source_corpus":
        mp["source_corpus_sha256"] = DUMMY_SHA
    elif tamper == "image":
        mp["image_sha256"] = DUMMY_SHA
    elif tamper == "rubric":
        mp["rubric_sha256"] = DUMMY_SHA
    elif tamper == "roster":
        mp["roster_sha256"] = DUMMY_SHA
    elif tamper == "contract":
        items[0]["schema"] = "m27.w5.a19.historical523.benchmark_candidate.v2"
    elif tamper == "license":
        mp["license_scope"] = "PRODUCTION"
    elif tamper == "run_id":
        mp["official_run_id"] = "historical.Stage30O"
    elif tamper == "status":
        items[0]["contract_status"] = "DRAFT_NOT_APPROVED"
    elif tamper == "mode_counts":
        mp["mode_counts"]["live/verified_cited_answer"] = 238
    else:
        mp["expires_at_utc"] = "2026-10-01T00:00:00Z"
    if tamper != "contract" and tamper != "status":
        items[0]["signatures"] = {
            role: items[4](mp, role)["signature"]
            for role in ("rights_issuer", "evaluator")
        }
    if tamper == "rubric":
        # Manifest-only changes may be deliberate but cannot certify provenance.
        # Neither creates a self-attested official benchmark right.
        result = evaluate(*items)
        assert result["official_523_run_certified"] is False
        return
    with pytest.raises(e24.Denied):
        evaluate(*items)


def test_85_quality_boundary_inclusive(private_fixture):
    items = get_payload(private_fixture)
    current(*items)[0]["grader_assertion"]["payload"]["score"] = 85.0
    resign_grade(current(*items)[0], items[4])
    reseal(items[0], items[1], items[2], items[4])
    assert evaluate(*items)["counts"]["cited_qualified"] == 237


def test_p95_live341_failure_includes_abstentions_and_rejects(private_fixture):
    items = get_payload(private_fixture)
    # 18 slow cases => only 323 of 341 <= 15 s; nearest rank 324 fails.
    for entry in current(*items)[237:255]:
        entry["timing"]["end_ns"] = 16_000_001_000
    reseal(items[0], items[1], items[2], items[4])
    result = evaluate(*items)
    assert result["p95_ms"]["live341"] > 15000
    assert not result["gates"]["p95_live341_at_most_15000ms"]


def test_p95_cited237_rank226_failure(private_fixture):
    items = get_payload(private_fixture)
    # 12 slow eligible cases => only 225 fast, rank 226 is slow.
    for entry in current(*items)[:12]:
        entry["timing"]["end_ns"] = 16_000_001_000
    reseal(items[0], items[1], items[2], items[4])
    result = evaluate(*items)
    assert result["p95_ms"]["cited237"] > 15000
    assert not result["gates"]["p95_cited237_at_most_15000ms"]


def test_cli_draft_denial_and_actual_sha(private_fixture, tmp_path):
    _, roster, outcomes, registry, _ = get_payload(private_fixture)
    draft = {"contract_status": "DRAFT_NOT_APPROVED",
             "schema": "m27.w5.a19.historical523.benchmark_candidate.v2"}
    paths = {}
    for name, payload in [("manifest", draft), ("roster", roster),
                          ("outcomes", outcomes), ("registry", registry)]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "result.json"
    argv = [
        "--manifest", str(paths["manifest"]),
        "--roster", str(paths["roster"]),
        "--outcomes", str(paths["outcomes"]),
        "--trusted-registry", str(paths["registry"]),
        "--trusted-registry-sha256", e24.sha(registry),
        "--output", str(output),
    ]
    assert e24.main(argv) == 20
    body = json.loads(output.read_text())
    assert body["admission_denied_reason"] == "DRAFT_OR_UNAPPROVED_CONTRACT"
    assert body["official_523_run_certified"] is False
    assert e24.main(argv) == 21  # immutable output; no overwritten evidence


@pytest.mark.parametrize("what", [
    "untrusted_registry_sha", "cross_role_principal", "fixture_tier_mixed",
    "duplicate_signer_key", "wrong_registry_schema",
])
def test_root_authenticity_gates(private_fixture, what):
    items = get_payload(private_fixture)
    if what == "untrusted_registry_sha":
        with pytest.raises(e24.Denied, match="EXTERNALLY_PINNED"):
            e24.evaluate(*items[:4], "0" * 64, now=NOW)
        return
    registry = items[3]
    if what == "cross_role_principal":
        registry["roots"]["grader"]["principal"] = (
            registry["roots"]["observer"]["principal"]
        )
    elif what == "fixture_tier_mixed":
        registry["roots"]["grader"]["tier"] = "AUTHENTICATED_EXTERNAL"
    elif what == "duplicate_signer_key":
        registry["roots"]["grader"]["key_id"] = (
            registry["roots"]["observer"]["key_id"]
        )
    else:
        registry["schema"] = "unverified"
    with pytest.raises(e24.Denied):
        evaluate(*items)


def test_no_duplicate_json_keys_and_symlink_input(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"x":1,"x":2}')
    with pytest.raises(e24.Denied, match="DUPLICATE_JSON_KEY"):
        e24.read_json(str(path))
    target = tmp_path / "link.json"
    target.symlink_to(path)
    with pytest.raises((OSError, e24.Denied)):
        e24.read_json(str(target))
