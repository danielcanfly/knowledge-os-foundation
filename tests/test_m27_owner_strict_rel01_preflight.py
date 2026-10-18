"""Adversarial exact-boundary and absent-formal-authority tests.

Synthetic rows are numeric unit fixtures and MUST NEVER count as official 523,
blind200, model answers, scorer custody, or Production evidence.
"""
from __future__ import annotations

from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
# An isolated new Nonprod release gate must not import package __init__,
# which loads old Provider side-effect modules outside this test's scope.
source = ROOT / "src/knowledge_engine/m27_owner_strict_rel01_preflight.py"
spec = importlib.util.spec_from_file_location("m27_strict_rel01_isolated", source)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
RUBRIC_SHA256 = guard.RUBRIC_SHA256
check_owner_strict_metrics = guard.check_owner_strict_metrics
current_formal_admission = guard.current_formal_admission
evaluate_current_official_paths = guard.evaluate_current_official_paths

HEAD = "a" * 40
IMAGE = "sha256:" + "b" * 64


def fixture(nsuccess=497, latency=14999.0, quality_score=86.0):
    cases = []
    for i in range(523):
        passed = i < nsuccess
        cases.append({
            "case_id": f"synthetic-nonofficial-{i:03d}",
            "source_head": HEAD,
            "signed_image_digest": IMAGE,
            "final_answer_latency_ms": latency,
            "independent_result": "verified_success" if passed else "failed",
            "cited_final": passed,
            "claim_supported": passed,
            "timed_out": False,
            "terminal_error": False,
        })
    quality = {
        "score": quality_score,
        "rubric_sha256": RUBRIC_SHA256,
        "rubric_scope": "homepage_suggested_questions",
        "independent_evaluator_attested": True,  # synthetic, not cryptographic
        "same_source_head": HEAD,
        "same_signed_image_digest": IMAGE,
    }
    return cases, quality


class OwnerStrictBoundaries(unittest.TestCase):
    def test_numeric_strict_497_passes_but_never_certifies_release(self):
        a,b = fixture()
        outcome = check_owner_strict_metrics(a,b)
        self.assertTrue(outcome["metrics_consistent"],outcome["reason_codes"])
        self.assertEqual(outcome["independent_successes_with_citations"],497)
        self.assertFalse(outcome["formal_rel01_certified"])
        self.assertFalse(outcome["production_deployment_authorized"])

    def test_496_of_523_fails(self):
        a,b = fixture(nsuccess=496)
        result=check_owner_strict_metrics(a,b)
        self.assertFalse(result["metrics_consistent"])
        self.assertIn("STRICT_SUCCESS_COUNT_BELOW_497",result["reason_codes"])

    def test_95_percent_boundary_never_passes(self):
        a,b=fixture(nsuccess=496)
        self.assertLessEqual(check_owner_strict_metrics(a,b)["success_rate"],0.95)

    def test_15_seconds_exactly_fails(self):
        a,b=fixture(latency=15000.0)
        result=check_owner_strict_metrics(a,b)
        self.assertFalse(result["metrics_consistent"])
        self.assertIn("COMPLETE_ANSWER_P95_NOT_STRICTLY_BELOW_15S",result["reason_codes"])

    def test_95th_percentile_calculates_full_denominator(self):
        a,b=fixture(latency=10.0)
        for case in a[:27]:case["final_answer_latency_ms"]=60000.0
        result=check_owner_strict_metrics(a,b)
        self.assertEqual(result["measured_complete_answer_p95_ms"],60000.0)
        self.assertFalse(result["metrics_consistent"])

    def test_quality_85_exactly_fails(self):
        a,b=fixture(quality_score=85.0)
        result=check_owner_strict_metrics(a,b)
        self.assertIn("QUALITY_NOT_STRICTLY_ABOVE_85",result["reason_codes"])

    def test_quality_85_point_one_passes_numeric(self):
        a,b=fixture(quality_score=85.1)
        self.assertTrue(check_owner_strict_metrics(a,b)["metrics_consistent"])

    def test_missing_cases_never_granted_by_claimed_summary(self):
        result=check_owner_strict_metrics(None,{"score":100.0})
        self.assertFalse(result["metrics_consistent"])
        self.assertIn("FORMAL_523_RAW_CASES_MISSING",result["reason_codes"])

    def test_tampered_duplicate_and_cross_version_rejected(self):
        a,b=fixture()
        a[7]["case_id"]=a[6]["case_id"]
        a[9]["source_head"]="c"*40
        result=check_owner_strict_metrics(a,b)
        self.assertIn("CASE_ID_MISSING_OR_DUPLICATE",result["reason_codes"])
        self.assertIn("SOURCE_IMAGE_NOT_SAME_VERSION",result["reason_codes"])

    def test_nan_latency_and_timeout_denied(self):
        a,b=fixture()
        a[4]["final_answer_latency_ms"]=float("nan")
        a[5]["timed_out"]=True
        result=check_owner_strict_metrics(a,b)
        self.assertIn("LATENCY_MISSING_INVALID_OR_TIMEOUT_EXCLUDED",result["reason_codes"])
        self.assertIn("TIMEOUT_OR_TERMINAL_ERROR_MUST_BE_ACCOUNTED",result["reason_codes"])

    def test_original_homepage_rubric_cannot_be_renamed_generic(self):
        a,b=fixture()
        b["rubric_scope"]="all_runtime_tasks"
        outcome=check_owner_strict_metrics(a,b)
        self.assertIn("RUBRIC_IS_NOT_A_GENERIC_TASK_QUALITY_STANDARD",outcome["reason_codes"])

    def test_rubric_digest_and_image_mismatch_denied(self):
        a,b=fixture()
        b["rubric_sha256"]="0"*64
        b["same_signed_image_digest"]="sha256:"+"c"*64
        r=check_owner_strict_metrics(a,b)
        self.assertIn("OWNER_RUBRIC_SHA_MISMATCH",r["reason_codes"])
        self.assertIn("QUALITY_IMAGE_MISMATCH",r["reason_codes"])

    def test_metrics_pass_and_fake_signed_receipts_still_hold(self):
        a,b=fixture()
        m=check_owner_strict_metrics(a,b)
        fake={"signature_valid":True,"independent":True,"rel01_pass":True}
        admission=current_formal_admission(
            m,
            trusted_registry={"schema":"m27.d02.trust-registry/v1",
                              "formal_enabled_issuer_count":0,"issuers":{}},
            official_gates={"delivery":{"C28":"PASS","E27":"PASS","B27":"PASS",
                                        "F35":"PASS","REL01":"PASS"}},
            validated_independent_receipts=fake)
        self.assertFalse(admission["rel01_certified"])
        self.assertFalse(admission["rel02_authorized"])
        self.assertIn("NO_INDEPENDENT_CRYPTOGRAPHIC_RECEIPT_VERIFIER",
                      admission["reason_codes"])
        self.assertTrue(admission["untrusted_receipt_fields_ignored"])

    def test_missing_official_gates_hold_even_if_metrics_good(self):
        a,b=fixture()
        result=current_formal_admission(
            check_owner_strict_metrics(a,b),
            trusted_registry={},
            official_gates={})
        self.assertEqual(result["status"],"HOLD")
        self.assertIn("C28_OFFICIAL_RECEIPT_NOT_PASS",result["reason_codes"])

    def test_current_actual_official_authority_holds(self):
        # Only public/non-secret trust metadata and official state, never Gold.
        m27=ROOT
        for _ in range(6):
            if (m27/"02_MASTER_GATE_STATE.json").exists():break
            m27=m27.parent
        self.assertTrue((m27/"02_MASTER_GATE_STATE.json").exists())
        registry=m27/"06_WORKSITES/PARALLEL_VNEXT_20261014/D02/D02_AUTHORITY_TRUST_REGISTRY.json"
        result=evaluate_current_official_paths(
            trust_registry=registry,
            gate_state=m27/"02_MASTER_GATE_STATE.json")
        self.assertFalse(result["rel01_certified"])
        self.assertFalse(result["production_deployed"])
        self.assertIn("NO_INDEPENDENT_ENABLED_TRUST_ROOT",result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
