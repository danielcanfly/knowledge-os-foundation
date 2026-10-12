"""Synthetic-only B24 negative/fault tests. Never import a hidden corpus."""
from __future__ import annotations

import base64
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine import m27_w5_b24_blind200_admission_v1_experimental as b24

NOW = 1_800_000_000_000
KEY_IDS = {r: "external-" + r + "-key" for r in b24.ROLES}
ACTORS = {r: "independent-" + r + "-actor" for r in b24.ROLES}


def _signed(role, payload, keys):
    sig = keys[role].sign(b24._signed_bytes(role, payload))
    return {"role": role, "key_id": KEY_IDS[role], "payload": payload,
            "signature": base64.b64encode(sig).decode("ascii")}


def _sign_all(payloads, keys):
    return {r: _signed(r, payloads[r], keys) for r in b24.ROLES}


@pytest.fixture
def synthetic():
    keys = {r: Ed25519PrivateKey.generate() for r in b24.ROLES}
    roots = {r: {KEY_IDS[r]: base64.b64encode(
        keys[r].public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )).decode()} for r in b24.ROLES}
    cases = [f"fresh-synthetic-{i:03}" for i in range(200)]
    roster = b24.digest(cases)
    src = "a" * 64
    image = "b" * 64
    runner_sha = "c" * 64
    auth = "d" * 64
    rubric_sha = "e" * 64
    rights = {
        "actor_id": ACTORS["rights_issuer"], "evaluation_id": "synthetic-eval-b24",
        "scope": b24.PHASE, "lawful_controller": True, "can_use_unseen_corpus": True,
        "valid_until_ms": NOW + 100_000, "source_revision_index_sha256": src,
        "cohort_roster_sha256": roster, "allowed_image_sha256": image,
    }
    payloads = {
        "custodian": {
            "actor_id": ACTORS["custodian"], "evaluation_id": "synthetic-eval-b24",
            "population": b24.PHASE, "historical_m26_reuse": False,
            "case_ids": cases, "case_count": 200, "roster_sha256": roster,
            "sealed_corpus_sha256": "f" * 64,
            "history_exclusion_sha256": "1" * 64,
            "source_revision_index_sha256": src,
            "history_overlap_count": 0, "previously_exposed": False,
            "sealed_by_independent_custodian": True, "developer_has_case_access": False,
            "answer_keys_exposed": False, "sealed_at_ms": NOW - 5000,
            "rubric_sha256": rubric_sha, "rights_grant_sha256": b24.digest(rights),
        },
        "rights_issuer": rights,
        "builder": {
            "actor_id": ACTORS["builder"], "evaluation_id": "synthetic-eval-b24",
            "image_sha256": image, "runner_sha256": runner_sha,
            "client_auth_sha256": auth, "signed_oci_digest": "2" * 64,
            "signed_image": True, "candidate_lock_at_ms": NOW - 1000,
        },
        "runner": {
            "actor_id": ACTORS["runner"], "evaluation_id": "synthetic-eval-b24",
            "runner_sha256": runner_sha, "sealed_execution": True,
            "one_shot": True, "developer_can_read_cases": False,
            "can_read_answer_keys": False, "authorized_until_ms": NOW + 100_000,
            "nonce": "synthetic-nonce-001", "intent": "RUN_ONCE_BLINDED",
        },
        "client": {
            "actor_id": ACTORS["client"], "evaluation_id": "synthetic-eval-b24",
            "client_auth_sha256": auth, "native_client_ack": True,
            "ack_digest": "3" * 64, "authorized_until_ms": NOW + 100_000,
            "nonce": "synthetic-nonce-001", "intent": "RUN_ONCE_BLINDED",
        },
        "rubric": {
            "actor_id": ACTORS["rubric"], "evaluation_id": "synthetic-eval-b24",
            "rubric_sha256": rubric_sha, "frozen_at_ms": NOW - 3000,
            "approved_independent_grader": True, "grade_only_output": True,
            "zero_critical_errors": True, "passing_grade": 85,
            "authorized_until_ms": NOW + 100_000,
        },
    }
    return keys, roots, payloads


def _admit(synthetic, edits=None):
    keys, roots, payloads = synthetic
    new = copy.deepcopy(payloads)
    if edits:
        edits(new)
    env = _sign_all(new, keys)
    return b24.admit(env, roots, now_ms=NOW,
                     pinned_root_sha256=b24.digest(roots))


def test_synthetic_metadata_can_be_eligible_but_never_pass(synthetic):
    result = _admit(synthetic)
    assert result["admission"] == "EXTERNAL_CUSTODIAN_ELIGIBLE_METADATA_ONLY"
    assert result["evaluation"] == b24.NOT_EXECUTED
    assert result["official_score"] is None and not result["production_authorized"]


def test_unpinned_developer_supplied_root_rejected(synthetic):
    keys, roots, payloads = synthetic
    assert b24.admit(_sign_all(payloads, keys), roots, now_ms=NOW)["admission"] == b24.NOT_ADMITTED


def test_untrusted_signed_key_injected_fails(synthetic):
    keys, roots, payloads = synthetic
    env = _sign_all(payloads, keys)
    env["custodian"]["key_id"] = "self-certifying-attacker-key"
    assert b24.admit(env, roots, now_ms=NOW,
                     pinned_root_sha256=b24.digest(roots))["admission"] == b24.NOT_ADMITTED


def test_owner_controlled_grader_key_must_not_be_runner_key(synthetic):
    keys, roots, payloads = synthetic
    env = _sign_all(payloads, keys)
    env["rubric"]["key_id"] = env["runner"]["key_id"]
    assert b24.admit(env, roots, now_ms=NOW,
                     pinned_root_sha256=b24.digest(roots))["admission"] == b24.NOT_ADMITTED


def test_tampered_cryptographic_signature_fails(synthetic):
    keys, roots, payloads = synthetic
    env = _sign_all(payloads, keys)
    env["custodian"]["payload"]["roster_sha256"] = "0" * 64
    assert b24.admit(env, roots, now_ms=NOW,
                     pinned_root_sha256=b24.digest(roots))["admission"] == b24.NOT_ADMITTED


def test_atomic_one_shot_nonce_replay_denied(tmp_path, synthetic):
    result = _admit(synthetic)
    assert b24.reserve_one_shot(result, tmp_path)
    assert not b24.reserve_one_shot(result, tmp_path)
    assert not b24.reserve_one_shot({"admission": b24.NOT_ADMITTED}, tmp_path)


def test_denied_run_reservation_does_not_create_state(tmp_path):
    assert not b24.reserve_one_shot({"admission": b24.NOT_ADMITTED}, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_cli_no_sealed_manifest_denies_without_leak():
    root = Path(__file__).resolve().parents[1]
    mod = root / "src/knowledge_engine/m27_w5_b24_blind200_admission_v1_experimental.py"
    result = subprocess.run([sys.executable, str(mod)], capture_output=True, text=True,
                            check=False)
    assert result.returncode == 20
    assert json.loads(result.stdout)["evaluation"] == b24.NOT_EXECUTED
    assert result.stderr == ""


@pytest.mark.parametrize(("role", "field", "value"), [
    ("custodian", "population", "M26_FROZEN200"),
    ("custodian", "population", "ORIGINAL_523"),
    ("custodian", "historical_m26_reuse", True),
    ("custodian", "historical_m26_reuse", None),
    ("custodian", "case_ids", []),
    ("custodian", "case_ids", ["new-case-000"] * 200),
    ("custodian", "case_ids", [f"new-{i:03}" for i in range(199)]),
    ("custodian", "case_ids", [f"new-{i:03}" for i in range(201)]),
    ("custodian", "case_ids", [f"new-{i:03}" for i in range(199)] + ["../escape"]),
    ("custodian", "case_count", 199),
    ("custodian", "case_count", 201),
    ("custodian", "roster_sha256", "0" * 64),
    ("custodian", "roster_sha256", "not-a-commitment"),
    ("custodian", "sealed_corpus_sha256", None),
    ("custodian", "history_exclusion_sha256", "invalid"),
    ("custodian", "source_revision_index_sha256", "short"),
    ("custodian", "history_overlap_count", 1),
    ("custodian", "history_overlap_count", -1),
    ("custodian", "previously_exposed", True),
    ("custodian", "sealed_by_independent_custodian", False),
    ("custodian", "developer_has_case_access", True),
    ("custodian", "answer_keys_exposed", True),
    ("custodian", "sealed_at_ms", NOW + 1000),
    ("custodian", "sealed_at_ms", NOW - 1000),
    ("custodian", "sealed_at_ms", "yesterday"),
    ("custodian", "rubric_sha256", "a" * 64),
    ("custodian", "rights_grant_sha256", "b" * 64),
    ("rights_issuer", "scope", "DATA_REPLAY"),
    ("rights_issuer", "lawful_controller", False),
    ("rights_issuer", "can_use_unseen_corpus", False),
    ("rights_issuer", "valid_until_ms", NOW),
    ("rights_issuer", "valid_until_ms", NOW - 100),
    ("rights_issuer", "source_revision_index_sha256", "b" * 64),
    ("rights_issuer", "cohort_roster_sha256", "e" * 64),
    ("rights_issuer", "allowed_image_sha256", "9" * 64),
    ("builder", "candidate_lock_at_ms", NOW + 1),
    ("builder", "candidate_lock_at_ms", NOW - 5001),
    ("builder", "image_sha256", ""),
    ("builder", "runner_sha256", "no"),
    ("builder", "client_auth_sha256", 123),
    ("builder", "signed_oci_digest", ""),
    ("builder", "signed_image", False),
    ("runner", "runner_sha256", "d" * 64),
    ("runner", "sealed_execution", False),
    ("runner", "one_shot", False),
    ("runner", "developer_can_read_cases", True),
    ("runner", "can_read_answer_keys", True),
    ("runner", "authorized_until_ms", NOW),
    ("runner", "nonce", "../../nonce"),
    ("runner", "intent", "REUSABLE"),
    ("client", "client_auth_sha256", "a" * 64),
    ("client", "native_client_ack", False),
    ("client", "ack_digest", "invalid"),
    ("client", "authorized_until_ms", NOW - 1),
    ("client", "nonce", "replayed-nonce"),
    ("client", "intent", "REPLAY"),
    ("rubric", "rubric_sha256", "0" * 64),
    ("rubric", "frozen_at_ms", NOW - 1),
    ("rubric", "approved_independent_grader", False),
    ("rubric", "grade_only_output", False),
    ("rubric", "zero_critical_errors", False),
    ("rubric", "passing_grade", 101),
    ("rubric", "passing_grade", -1),
    ("rubric", "authorized_until_ms", NOW),
    ("custodian", "evaluation_id", "another-eval"),
    ("client", "actor_id", ACTORS["runner"]),
    ("runner", "actor_id", "developer-owned"),
])
def test_distinct_preflight_fails_closed(synthetic, role, field, value):
    result = _admit(synthetic, lambda p: p[role].__setitem__(field, value))
    assert result["admission"] == b24.NOT_ADMITTED
    assert result["official_score"] is None


def _valid_results(synthetic):
    keys, roots, payloads = synthetic
    env = _sign_all(payloads, keys)
    ids = payloads["custodian"]["case_ids"]
    run = {"evaluation_id": "synthetic-eval-b24", "nonce": "synthetic-nonce-001",
           "roster_sha256": b24.digest(ids), "image_sha256": "b" * 64,
           "attempt_ids": list(ids), "terminal_ids": list(ids)}
    graded = [{"id": i, "outcome": "ANSWER", "grade": 90, "critical": False,
               "source_revision": "revision-1", "source_id": "synthetic-source-1",
               "citation_start": 0, "citation_end": 10,
               "span_verified": True} for i in ids]
    grade = {"evaluation_id": run["evaluation_id"], "nonce": run["nonce"],
             "roster_sha256": run["roster_sha256"], "runner_digest": b24.digest(run),
             "results": graded}
    src = {"evaluation_id": run["evaluation_id"], "nonce": run["nonce"],
           "roster_sha256": run["roster_sha256"], "grade_digest": b24.digest(grade),
           "source_span_audit": True, "critical_error_audit": True,
           "signed_grading_keys_kept_private": True}
    return keys, roots, env, run, grade, src


def _grade_run(synthetic, modify=None):
    keys, roots, env, run, grade, src = _valid_results(synthetic)
    if modify:
        old_runner_digest = grade["runner_digest"]
        old_grade_digest = src["grade_digest"]
        modify(run, grade, src)
        # Rebind honest changed test receipts before signing, exercising
        # denominator/source guards rather than failing only at the hash chain.
        if grade["runner_digest"] == old_runner_digest:
            grade["runner_digest"] = b24.digest(run)
        if src["grade_digest"] == old_grade_digest:
            src["grade_digest"] = b24.digest(grade)
    # Independently re-sign each synthetic role to test semantic checks,
    # without suggesting these fake roots or grader are externally enrolled.
    result = b24.verify_grade_only(
        env, roots, _signed("rubric", grade, keys), _signed("runner", run, keys),
        _signed("custodian", src, keys), now_ms=NOW,
        pinned_root_sha256=b24.digest(roots),
    )
    return result


def test_complete_synthetic_grade_not_certified(synthetic):
    res = _grade_run(synthetic)
    assert res["attempted"] == res["terminal"] == res["graded"] == 200
    assert res["passing"] == 200
    assert res["official_score"] is None and res["certified"] is False


@pytest.mark.parametrize("fault", [
    "attempt199", "terminal199", "attempt_duplicates", "terminal_duplicates",
    "attempt_unknown", "terminal_unknown", "graded199", "graded_duplicates",
    "postfreeze_roster_swap", "image_swap", "grade_digest_swap", "source_digest_swap",
    "nonce_replay", "answer_key_leak", "source_span_mismatch", "empty_source_revision",
    "critical_scored", "timeout_scored", "missing_scored", "error_scored",
    "negative_grade", "over100_grade", "source_start_negative", "span_zero",
    "span_end_before_start", "source_audit_missing", "critical_audit_missing",
    "source_keys_leaked", "missing_outcome", "unknown_outcome", "missing_terminal",
])
def test_signed_result_faults_rejected(synthetic, fault):
    def mutate(run, grade, source):
        results = grade["results"]
        if fault == "attempt199":
            run["attempt_ids"].pop()
        elif fault == "terminal199":
            run["terminal_ids"].pop()
        elif fault == "attempt_duplicates":
            run["attempt_ids"][-1] = run["attempt_ids"][0]
        elif fault == "terminal_duplicates":
            run["terminal_ids"][-1] = run["terminal_ids"][0]
        elif fault == "attempt_unknown":
            run["attempt_ids"][-1] = "unknown-case-id"
        elif fault == "terminal_unknown":
            run["terminal_ids"][-1] = "unknown-case-id"
        elif fault == "graded199":
            results.pop()
        elif fault == "graded_duplicates":
            results[-1]["id"] = results[0]["id"]
        elif fault == "postfreeze_roster_swap":
            run["roster_sha256"] = "0" * 64
        elif fault == "image_swap":
            run["image_sha256"] = "0" * 64
        elif fault == "grade_digest_swap":
            grade["runner_digest"] = "0" * 64
        elif fault == "source_digest_swap":
            source["grade_digest"] = "0" * 64
        elif fault == "nonce_replay":
            grade["nonce"] = "replayed-nonce"
        elif fault == "answer_key_leak":
            results[0]["answer_key"] = "forbidden"
        elif fault == "source_span_mismatch":
            results[0]["span_verified"] = False
            # A false span flag is counted as failure, not accepted as a correct answer.
            return
        elif fault == "empty_source_revision":
            results[0]["source_revision"] = ""
        elif fault == "critical_scored":
            results[0]["critical"] = True
        elif fault == "timeout_scored":
            results[0]["outcome"] = "TIMEOUT"
        elif fault == "missing_scored":
            results[0]["outcome"] = "ABSTAIN"
        elif fault == "error_scored":
            results[0]["outcome"] = "ERROR"
        elif fault == "negative_grade":
            results[0]["grade"] = -1
        elif fault == "over100_grade":
            results[0]["grade"] = 101
        elif fault == "source_start_negative":
            results[0]["citation_start"] = -1
        elif fault == "span_zero":
            results[0]["citation_end"] = results[0]["citation_start"]
        elif fault == "span_end_before_start":
            results[0]["citation_end"] = -1
        elif fault == "source_audit_missing":
            source["source_span_audit"] = False
        elif fault == "critical_audit_missing":
            source["critical_error_audit"] = False
        elif fault == "source_keys_leaked":
            source["signed_grading_keys_kept_private"] = False
        elif fault == "missing_outcome":
            del results[0]["outcome"]
        elif fault == "unknown_outcome":
            results[0]["outcome"] = "NOT_ATTEMPTED"
        elif fault == "missing_terminal":
            run["terminal_ids"].remove(run["terminal_ids"][1])

    got = _grade_run(synthetic, mutate)
    assert got["admission"] == b24.NOT_ADMITTED or (
        fault == "source_span_mismatch" and got.get("failing") == 1
        and got["passing"] == 199 and got["official_score"] is None
    )


def test_faults_with_signed_zero_scores_stay_in_denominator(synthetic):
    def faults(run, grade, source):
        del run, source
        for index, outcome, critical, span in (
            (0, "TIMEOUT", False, True),
            (1, "ERROR", True, True),
            (2, "ANSWER", False, False),
        ):
            result = grade["results"][index]
            result["outcome"] = outcome
            result["critical"] = critical
            result["span_verified"] = span
            result["grade"] = 0

    result = _grade_run(synthetic, faults)
    assert result["attempted"] == result["graded"] == result["terminal"] == 200
    assert result["passing"] == 197 and result["failing"] == 3
    assert result["critical_errors"] == 1 and result["official_score"] is None


def test_preflight_rejects_unapproved_extra_answer_keys(synthetic):
    result = _admit(synthetic, lambda p: p["custodian"].__setitem__(
        "answers", ["synthetic-leak"]
    ))
    assert result["admission"] == b24.NOT_ADMITTED
    assert result["reason"] == "MANIFEST_SCHEMA_VIOLATION"


def test_no_current_external_approval_from_synthetic_signers(synthetic):
    _, _, payloads = synthetic
    assert payloads["custodian"]["population"] == b24.PHASE
    assert _admit(synthetic)["evaluation"] == b24.NOT_EXECUTED


def test_invalid_result_source_case_body_denied(synthetic):
    def leak(run, grade, source):
        del run, grade
        source["case_body"] = "FORBIDDEN"

    assert _grade_run(synthetic, leak)["admission"] == b24.NOT_ADMITTED


def test_unlinked_signed_result_unknown_case_denied(synthetic):
    def mutate(run, grade, source):
        del run, source
        grade["results"][0]["id"] = "unrelated-historical-m26"

    assert _grade_run(synthetic, mutate)["admission"] == b24.NOT_ADMITTED
