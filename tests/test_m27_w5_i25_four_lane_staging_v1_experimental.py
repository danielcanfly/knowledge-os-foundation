"""Fresh I25 integration adversarial cases only, no P16/B13 original/hidden corpus."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_b24_blind200_admission_v1_experimental as b24
from knowledge_engine import m27_w5_c24_client_observation_v1_experimental as c24
from knowledge_engine import m27_w5_e24_original523_evidence_scorer_v1_experimental as e24
from knowledge_engine import m27_w5_i25_four_lane_staging_v1_experimental as i25
from knowledge_engine import m27_w5_p24_p16_b13_witness_gate_v1_experimental as p24


@pytest.fixture(scope="module")
def worktree() -> Path:
    return Path(__file__).resolve().parents[1]


def test_all_four_real_source_origins_match_committed_bytes(worktree):
    physical = i25.attest_four_origins(worktree)
    assert set(physical) == {"p24", "c24", "e24", "b24"}
    assert all(len(files) == 3 for files in physical.values())


def test_i23_existing_pin_still_matches(worktree):
    assert len(i25.i23.attest_sources(worktree)) == 7


def test_boundary_entrypoints_reject_fabricated_external_authority():
    results = i25.authority_boundaries()
    assert results["p24"]["decision"] == p24.STATUS_UNVERIFIED
    assert results["b24"]["admission"] == b24.NOT_ADMITTED
    assert results["e24"]["status"].startswith("OFFICIAL_523_NOT_RUN")
    assert results["c24"]["status"] == c24.UNKNOWN
    assert not any(i25.GATES.values())


@pytest.mark.parametrize("fault", range(24))
def test_p24_admission_rejects_24_distinct_incomplete_witness_shapes(fault):
    candidate = {"schema": p24.SCHEMA, "witness_id": "fixture_id",
                 "scope": "P16", "origin": {}, "authorization": {},
                 "native": {}, "detail": {}, "signature": {}}
    key = ["schema", "witness_id", "scope", "origin", "authorization",
           "native", "detail", "signature"][fault % 8]
    if fault < 8:
        candidate.pop(key)
    elif fault < 16:
        candidate[key] = None
    else:
        candidate[key] = ("invalid-root-" + str(fault)) if fault % 2 else []
    result = p24.verify_existing_witness(candidate, {})
    assert result["decision"] == p24.STATUS_UNVERIFIED
    assert not result["original_p16_pass"]
    assert not result["original_b13_pass"]


@pytest.mark.parametrize("fault", range(18))
def test_b24_untrusted_or_incomplete_seal_denied(fault):
    schemes = [None, {}, [], False, "bad", 0, {"custodian": {}},
               {"rights_issuer": {}}, {"builder": {}}, {"runner": {}},
               {"client": {}}, {"rubric": {}}, {"unknown": {}},
               {"developer": True}, {"case_count": 200}, {"approved": True},
               [1] * 200, 123]
    roots = {"bad": "keys"} if fault % 2 else {}
    probe = b24.admit(schemes[fault], roots,
                      pinned_root_sha256=(b24.digest(roots) if fault % 2 else None))
    assert probe["admission"] == b24.NOT_ADMITTED
    assert probe["official_score"] is None


@pytest.mark.parametrize("fault", range(16))
def test_e24_root_registry_missing_external_signer(fault):
    candidate = {"schema": e24.REGISTRY_VERSION}
    changes = [None, {}, [], False, 10, "not-a-root", {"roots": []},
               {"roots": {}}, {"roots": None}, {"extra": []},
               {"schema": "wrong"}, {"schema": e24.REGISTRY_VERSION, "roots": []},
               {"schema": e24.REGISTRY_VERSION, "roots": {}},
               {"schema": e24.REGISTRY_VERSION, "roots": None},
               {"schema": e24.REGISTRY_VERSION, "roots": [{"tier": "fixture"}]},
               {"schema": e24.REGISTRY_VERSION, "roots": {"a": "b"}}]
    candidate = changes[fault]
    with pytest.raises((e24.Denied, TypeError, ValueError)):
        e24.trusted_roots(candidate, "0" * 64)


@pytest.mark.parametrize("fault", range(16))
def test_c24_plan_identity_and_digest_mutation_rejected(fault):
    base = c24.CasePlan(
        "i25-valid", "i25-request", "i25-nonce", "a" * 64, "b" * 64, True
    )
    fields = ["case_id", "request_id", "nonce", "runner_sha256",
              "candidate_sha256", "client_role", "cohort", "expected_citation"]
    bad = [None, [], "", "$invalid!", None, False, {}, 34]
    change = {fields[fault % 8]: bad[fault % 8]}
    if fault >= 8:
        change = {fields[fault % 8]: ("x" * 129 if fault % 8 not in (3, 4, 7)
                                    else ("z" * 64 if fault % 8 in (3, 4)
                                          else "true"))}
    with pytest.raises(c24.ObservationDenied):
        replace(base, **change).validate()


@pytest.mark.parametrize("fault", range(12))
def test_c24_source_rights_and_digest_faults(fault):
    base = c24.SourcePin("cit", "doc", "rev", c24.sha(b"source"), b"source",
                         authorized=True)
    bad = [
        {"authorized": False}, {"revoked": True}, {"source_sha256": "a" * 64},
        {"original_bytes": b"other"}, {"source_id": ""}, {"citation_id": ""},
        {"revision": ""}, {"source_sha256": ""}, {"original_bytes": b""},
        {"source_sha256": None}, {"source_id": None}, {"revision": None},
    ]
    with pytest.raises(c24.ObservationDenied):
        replace(base, **bad[fault]).check()


@pytest.mark.parametrize("fault", ["citation", "terminal", "progress_only"])
def test_c24_physical_os_client_fault_denied(fault, worktree, tmp_path):
    result = i25.c24_physical_client(worktree, tmp_path, corrupt=fault)
    assert result["exit_code"] == 20
    assert result["status"] != "COMPLETE"
    assert result["official_qualified"] is False


def test_c24_physical_os_client_observed_source_bytes(worktree, tmp_path):
    result = i25.c24_physical_client(worktree, tmp_path)
    assert result["exit_code"] == 0
    assert result["status"] == "COMPLETE"
    assert result["recv_calls"] > 1
    assert result["client_pid"] != result["parent_pid"]
    assert result["first_text_ns"] < result["terminal_ns"]
    assert result["official_qualified"] is False


@pytest.mark.parametrize("kind", ["p24", "c24", "e24", "b24"])
def test_source_origin_missing_or_bad_git_blob_is_denied(worktree, monkeypatch, kind):
    real = i25.subprocess.run
    def inject(cmd, *args, **kwargs):
        if cmd[-1].startswith(i25.ORIGINS[kind] + ":"):
            return type("FakeGit", (), {"returncode": 1, "stdout": b""})()
        return real(cmd, *args, **kwargs)
    monkeypatch.setattr(i25.subprocess, "run", inject)
    with pytest.raises(i25.IntegrationDenied, match="ORIGIN_GIT_BLOB_MISSING"):
        i25.attest_four_origins(worktree)


@pytest.mark.parametrize("status", [None, {}, [], 123, False, "SUCCESS"])
def test_i25_nonpass_never_maps_to_success(status):
    assert status != i25.PASS
    assert not any(i25.GATES.values())


def test_i25_json_gates_and_names():
    assert i25.FAIL != i25.PASS
    assert i25.ORIGINS["p24"].startswith("e7dedb59")
    assert len(i25.PATHS) == 4
    assert all(len(v) == 3 for v in i25.PATHS.values())
    assert json.loads(json.dumps(i25.GATES)) == i25.GATES


def test_c24_custody_cannot_claim_external_from_synthetic():
    assert c24.independent_custody({"synthetic": True}, {}, {}, {})["status"] == c24.UNKNOWN


def test_b24_one_shot_denied_without_admission(tmp_path):
    assert b24.reserve_one_shot({"admission": b24.NOT_ADMITTED}, tmp_path) is False


def test_p24_not_accepted_with_empty_independent_registry():
    assert p24.verify_existing_witness({}, {})["decision"] == p24.STATUS_UNVERIFIED


def test_e24_denied_missing_approval():
    with pytest.raises((e24.Denied, TypeError, ValueError)):
        e24.evaluate({}, {}, {}, {}, "0" * 64)


def test_i25_source_path_no_untracked_m24(worktree):
    assert not (worktree / "src/knowledge_engine/"
                "m27_w5_m24_m16_admission_boundary_v1_experimental.py").exists()


def test_gates_match_full_release_scope():
    for name in ("OFFICIAL_523_PASS", "PHASE_B200_OFFICIAL_PASS",
                 "P16_ORIGINAL_PASS", "B13_ORIGINAL_PASS",
                 "M16_CANONICAL_ACCEPTED", "REAL_APP_CLIENT_P95_PASS",
                 "PRODUCTION_AUTHORIZED"):
        assert i25.GATES[name] is False
