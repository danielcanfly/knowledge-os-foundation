"""Independent G25R F25 60+ fault classes against new five-lane receipt contract."""
from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_engine import m27_w5_g25r_five_lane_local_runtime_v1_experimental as f
from knowledge_engine import m27_w5_i25_four_lane_staging_v1_experimental as i25

ROOT = Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009")
WORKTREE = ROOT / "06_WORKSITES/W5_G25R_FIVE_LANE_INTEGRATION"
M24 = ROOT / "06_WORKSITES/W5_M24_ADMISSION_BRIDGE"


def good():
    return {
        "schema": "m27.w5.g25r.five_lane_local.v1",
        "status": f.PASS, "fixture_only": True,
        "source_provenance": {
            "staging_clean": True, "original_clean": True,
            "i25_source_commit": f.I25_COMMIT,
            "m24_original_commit": f.M24_COMMIT,
            "source_origins": {**{k: {"origin": v}
                                 for k, v in i25.ORIGINS.items()},
                               "m24": f.M24_SHA},
        },
        "m24": {"admission_decision": "NOT_ADMITTED",
                "synthetic_local_status": "COMPLETE",
                "external_gates_admitted": False},
        "four_lanes": {"status": i25.PASS, "sha256": "f" * 64,
                       "problems": []},
        "physical_counts": {
            "attempted": 28, "completed": 12, "expected_denied": 16,
            "overlap_attempted": 6, "overlap_completed": 3,
            "overlap_denied": 3, "late_client_ms": 5000.,
            "c24_client_preterminal": True,
        },
        "gates": dict(f.GATES), "real_app_client_p95_ms": None,
        "official_release_admitted": False, "real_provider_calls": 0,
    }


def test_positive_local_receipt_stays_external_denied():
    out = f.audit_completed_receipt(good())
    assert out["five_source_lanes"] == 5
    assert out["external_qualified"] is False


@pytest.mark.parametrize("mutation", [
    "not_dict", "wrong_pass", "not_fixture", "gate_missing", "gate_extra",
    "gate_value_nonbool", "release_true", "real_product_p95", "real_provider",
    "source_missing", "m24_origin", "i25_origin", "source_missing_lane",
    "source_extra_lane", "staging_dirty", "original_dirty",
    "m24_missing", "m24_admitted", "m24_unknown", "m24_local_denied",
    "m24_local_error", "m24_external_true", "four_missing", "four_wrong_pass",
    "four_wrong_sha", "four_errors",
    "physical_missing", "attempted_small", "attempted_big", "completed_small",
    "completed_large", "denied_small", "denied_large", "overlap_small",
    "overlap_large", "overlap_completed_small", "overlap_completed_large",
    "overlap_denied_small", "overlap_denied_large", "late_early",
    "late_missing", "late_negative", "late_string", "preterminal_false",
    "preterminal_none", "count_bools", "extra_bad_gate",
    "gate_p16_true", "gate_b13_true", "gate_m16_true",
    "gate_523_true", "gate_b200_true", "gate_client_p95_true",
    "gate_w5_true", "gate_w6_true", "gate_rel01_true",
    "gate_rel02_true", "gate_prod_true",
    "wrong_four_problems", "missing_source_origins",
    "origin_none", "source_clean_missing", "official_release_string",
    "fixture_string", "provider_bool",
])
def test_five_lane_receipt_negative_classes(mutation):
    doc = good()
    src = doc["source_provenance"]
    m = doc["m24"]
    four = doc["four_lanes"]
    phy = doc["physical_counts"]
    if mutation == "not_dict":
        doc = None
    elif mutation == "wrong_pass":
        doc["status"] = "NOT_VERIFIED"
    elif mutation == "not_fixture":
        doc["fixture_only"] = False
    elif mutation == "gate_missing":
        doc["gates"].pop("P16_ORIGINAL_PASS")
    elif mutation == "gate_extra":
        doc["gates"]["AUTHORIZE_ANYTHING"] = False
    elif mutation == "gate_value_nonbool":
        doc["gates"]["P16_ORIGINAL_PASS"] = 0
    elif mutation == "release_true":
        doc["official_release_admitted"] = True
    elif mutation == "real_product_p95":
        doc["real_app_client_p95_ms"] = 9
    elif mutation == "real_provider":
        doc["real_provider_calls"] = 1
    elif mutation == "source_missing":
        doc.pop("source_provenance")
    elif mutation == "m24_origin":
        src["m24_original_commit"] = "0" * 40
    elif mutation == "i25_origin":
        src["i25_source_commit"] = "0" * 40
    elif mutation == "source_missing_lane":
        src["source_origins"].pop("m24")
    elif mutation == "source_extra_lane":
        src["source_origins"]["m25"] = {}
    elif mutation == "staging_dirty":
        src["staging_clean"] = False
    elif mutation == "original_dirty":
        src["original_clean"] = False
    elif mutation == "m24_missing":
        doc.pop("m24")
    elif mutation == "m24_admitted":
        m["admission_decision"] = "ADMITTED"
    elif mutation == "m24_unknown":
        m["admission_decision"] = "UNKNOWN"
    elif mutation == "m24_local_denied":
        m["synthetic_local_status"] = "DENIED"
    elif mutation == "m24_local_error":
        m["synthetic_local_status"] = "ERROR"
    elif mutation == "m24_external_true":
        m["external_gates_admitted"] = True
    elif mutation == "four_missing":
        doc.pop("four_lanes")
    elif mutation == "four_wrong_pass":
        four["status"] = i25.FAIL
    elif mutation == "four_wrong_sha":
        four["sha256"] = None
    elif mutation in ("four_errors", "wrong_four_problems"):
        four["problems"] = ["REAL_FAULT"]
    elif mutation == "physical_missing":
        doc.pop("physical_counts")
    elif mutation == "attempted_small":
        phy["attempted"] = 27
    elif mutation == "attempted_big":
        phy["attempted"] = 29
    elif mutation == "completed_small":
        phy["completed"] = 11
    elif mutation == "completed_large":
        phy["completed"] = 13
    elif mutation == "denied_small":
        phy["expected_denied"] = 15
    elif mutation == "denied_large":
        phy["expected_denied"] = 17
    elif mutation == "overlap_small":
        phy["overlap_attempted"] = 5
    elif mutation == "overlap_large":
        phy["overlap_attempted"] = 7
    elif mutation == "overlap_completed_small":
        phy["overlap_completed"] = 2
    elif mutation == "overlap_completed_large":
        phy["overlap_completed"] = 4
    elif mutation == "overlap_denied_small":
        phy["overlap_denied"] = 2
    elif mutation == "overlap_denied_large":
        phy["overlap_denied"] = 4
    elif mutation == "late_early":
        phy["late_client_ms"] = 4499
    elif mutation == "late_missing":
        phy["late_client_ms"] = None
    elif mutation == "late_negative":
        phy["late_client_ms"] = -1
    elif mutation == "late_string":
        phy["late_client_ms"] = "5000"
    elif mutation == "preterminal_false":
        phy["c24_client_preterminal"] = False
    elif mutation == "preterminal_none":
        phy["c24_client_preterminal"] = None
    elif mutation == "count_bools":
        phy["attempted"] = True
    elif mutation == "extra_bad_gate":
        doc["gates"]["any"] = True
    elif mutation.startswith("gate_") and mutation.endswith("_true"):
        mapping = {
            "gate_p16_true": "P16_ORIGINAL_PASS",
            "gate_b13_true": "B13_ORIGINAL_PASS",
            "gate_m16_true": "M16_CANONICAL_ACCEPTED",
            "gate_523_true": "OFFICIAL_523_PASS",
            "gate_b200_true": "PHASE_B200_OFFICIAL_PASS",
            "gate_client_p95_true": "REAL_APP_CLIENT_P95_PASS",
            "gate_w5_true": "W5_FULL_COMPLETE",
            "gate_w6_true": "W6_AUTHORIZED",
            "gate_rel01_true": "REL01_CERTIFIED",
            "gate_rel02_true": "REL02_AUTHORIZED",
            "gate_prod_true": "PRODUCTION_AUTHORIZED",
        }
        doc["gates"][mapping[mutation]] = True
    elif mutation == "missing_source_origins":
        src.pop("source_origins")
    elif mutation == "origin_none":
        src["source_origins"] = None
    elif mutation == "source_clean_missing":
        src.pop("staging_clean")
    elif mutation == "official_release_string":
        doc["official_release_admitted"] = "false"
    elif mutation == "fixture_string":
        doc["fixture_only"] = "true"
    elif mutation == "provider_bool":
        doc["real_provider_calls"] = True
    else:
        raise AssertionError(mutation)
    with pytest.raises((f.FiveDenied, TypeError)):
        f.audit_completed_receipt(doc)


def test_distinct_m24_tracked_original_is_direct_i23_child():
    if not M24.exists():
        pytest.skip("original not mounted")
    assert f.git(M24, "rev-parse", "HEAD").decode().strip() == f.M24_COMMIT
    assert f.git(M24, "rev-parse", "HEAD^").decode().strip() == f.I23_COMMIT


def test_actual_five_origin_parity_when_worktree_is_committed():
    if not WORKTREE.exists():
        pytest.skip("staging not mounted")
    if f.git(WORKTREE, "status", "--porcelain=v1").strip():
        pytest.skip("initial precommit tests before adapter is committed")
    data = f.attest_five_sources(WORKTREE, M24)
    assert len(data["source_origins"]) == 5
    assert data["m24_candidate"].head == f.M24_COMMIT


@pytest.mark.parametrize("case", [
    ("relative_worktree", Path("relative"), M24),
    ("relative_m24", WORKTREE, Path("relative")),
    ("missing_worktree", Path("/this/does/not/exist"), M24),
    ("missing_m24", WORKTREE, Path("/this/does/not/exist")),
])
def test_reject_wrong_source_locations(case):
    _, worktree, m24 = case
    with pytest.raises(f.FiveDenied):
        f.attest_five_sources(worktree, m24)


@pytest.mark.parametrize("namespace", ["", "HAS SPACE", "_abc", "x" * 25,
                                      "📎", "bad/slash", "2bad"])
def test_invalid_namespace_denied(namespace, tmp_path):
    with pytest.raises((f.FiveDenied, IndexError)):
        f.run(WORKTREE, M24, tmp_path / "temp", namespace)


def test_unknown_release_never_true():
    assert not any(f.GATES.values())
    assert f.M24_COMMIT != f.I25_COMMIT
    assert set(f.M24_PATHS) == set(f.M24_SHA)
