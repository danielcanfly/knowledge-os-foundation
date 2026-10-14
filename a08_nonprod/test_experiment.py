"""A08 standalone stdlib positive, negative, security and regression tests."""
import copy
import unittest
from dataclasses import replace

from experiment import (ACTIVE_POLICY_ID, BASELINE, CANDIDATE, QUOTE, WORKLOAD,
                        Policy, canonical, digest, evaluate, heldout_review,
                        load_workload, propose_from_real_failure, run_case,
                        validate_source)


class A08ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load_workload()
        cls.easy = next(t for t in cls.tasks if t["kind"] == "QA")
        cls.hard = next(t for t in cls.tasks if t["kind"] == "RESEARCH")
        cls.dev = [x for x in cls.tasks if x["split"] == "development"]
        cls.holdout = [x for x in cls.tasks if x["split"] == "independent_holdout"]

    def test_01_real_source_validated(self):
        for case in self.tasks:
            validate_source(case)

    def test_02_fixed_workload_split_and_roster(self):
        self.assertEqual((len(self.dev), len(self.holdout)), (32, 16))
        self.assertEqual(len({t["id"] for t in self.tasks}), 48)

    def test_03_separate_heldout_evidence(self):
        dev_quotes = {e["quote"] for t in self.dev for e in t["source_evidence"]}
        holdout_quotes = {e["quote"] for t in self.holdout for e in t["source_evidence"]}
        self.assertFalse(dev_quotes.intersection(holdout_quotes))

    def test_04_baseline_qa_actual_fail_closed(self):
        r = run_case(self.easy, BASELINE)
        self.assertEqual(r["status"], "CALL_QUOTA_EXCEEDED")
        self.assertFalse(r["accepted"])
        self.assertEqual(r["provider_attempts"], 2)

    def test_05_baseline_research_positive(self):
        r = run_case(self.hard, BASELINE)
        self.assertEqual(r["status"], "ACCEPTED")
        self.assertEqual(r["provider_attempts"], 3)
        self.assertEqual(r["evidence_verified"], 2)

    def test_06_adaptive_qa_positive(self):
        r = run_case(self.easy, CANDIDATE)
        self.assertTrue(r["accepted"])
        self.assertEqual(r["provider_attempts"], 1)

    def test_07_adaptive_research_positive(self):
        r = run_case(self.hard, CANDIDATE)
        self.assertTrue(r["accepted"])
        self.assertEqual(r["provider_attempts"], 2)

    def test_08_quota_zero(self):
        cap = replace(CANDIDATE, max_provider_calls=1, fixed_rounds=1)
        self.assertEqual(run_case(self.hard, cap)["status"], "CALL_QUOTA_EXCEEDED")

    def test_09_cost_ceiling(self):
        p = replace(CANDIDATE, max_cost_micro_usd=1)
        self.assertEqual(run_case(self.easy, p)["status"], "COST_CAP_EXCEEDED")

    def test_10_token_ceiling(self):
        p = replace(CANDIDATE, max_input_tokens=1)
        self.assertEqual(run_case(self.easy, p)["status"], "TOKEN_CAP_EXCEEDED")

    def test_11_latency_ceiling(self):
        p = replace(CANDIDATE, max_latency_ms=1)
        self.assertEqual(run_case(self.easy, p)["status"], "LATENCY_CAP_EXCEEDED")

    def test_12_provider_unknown_effect_no_retry(self):
        r = run_case(self.easy, CANDIDATE, fault="UNKNOWN_EFFECT")
        self.assertEqual(r["status"], "UNKNOWN_EFFECT_RECONCILE_REQUIRED")
        self.assertEqual(r["provider_attempts"], 1)
        self.assertEqual([e["state"] for e in r["events"]], ["POSSIBLY_SENT_UNRESOLVED"])

    def test_13_post_send_timeout_no_retry(self):
        r = run_case(self.hard, CANDIDATE, fault="TIMEOUT_AFTER_SEND")
        self.assertEqual(r["status"], "UNKNOWN_EFFECT_RECONCILE_REQUIRED")
        self.assertEqual(len(r["events"]), 1)
        self.assertFalse(r["accepted"])

    def test_14_pre_send_timeout_safe_terminal(self):
        r = run_case(self.easy, CANDIDATE, fault="TIMEOUT_BEFORE_SEND")
        self.assertEqual(r["status"], "SAFE_NO_SEND_TIMEOUT")
        self.assertEqual(r["events"][0]["state"], "NO_SEND")

    def test_15_known_no_send_can_failover_once(self):
        r = run_case(self.easy, CANDIDATE, fault="NO_SEND")
        self.assertTrue(r["accepted"])
        self.assertEqual(r["provider_attempts"], 2)
        self.assertEqual([e["route"] for e in r["events"]], ["primary", "backup"])

    def test_16_no_send_without_permission(self):
        r = run_case(self.easy, CANDIDATE, fault="NO_SEND", failover_permission=False)
        self.assertEqual(r["status"], "FAILOVER_NOT_AUTHORIZED")
        self.assertEqual(len(r["events"]), 1)

    def test_17_failover_quota_capped(self):
        p = replace(CANDIDATE, max_provider_calls=1, fixed_rounds=1)
        self.assertEqual(run_case(self.easy, p, fault="NO_SEND")["status"], "FAILOVER_QUOTA_EXCEEDED")

    def test_18_stale_unknown_quote_rejected(self):
        q = dict(QUOTE, id="UNVERIFIED_PRICE")
        r = run_case(self.easy, CANDIDATE, quote=q)
        self.assertEqual(r["status"], "UNTRUSTED_OR_STALE_QUOTE")
        self.assertEqual(r["provider_attempts"], 0)

    def test_19_missing_usage_receipt_not_billed(self):
        r = run_case(self.easy, CANDIDATE, provider_receipt=None)
        self.assertEqual(r["status"], "USAGE_RECEIPT_UNKNOWN")
        self.assertFalse(r["accepted"])
        self.assertEqual(r["cost_micro_usd_simulated"], 0)
        self.assertEqual(r["provider_attempts"], 1)

    def test_20_mismatched_usage_receipt(self):
        r = run_case(self.easy, CANDIDATE,
                     provider_receipt={"input_tokens": 170, "output_tokens": 60, "attempt_id": "wrong"})
        self.assertEqual(r["status"], "USAGE_RECEIPT_MISMATCH")
        self.assertEqual(r["provider_attempts"], 1)
        self.assertFalse(r["accepted"])

    def test_21_exact_usage_receipt_positive(self):
        r = run_case(self.easy, CANDIDATE,
                     provider_receipt={"input_tokens": 170, "output_tokens": 60,
                                       "attempt_id": self.easy["id"] + ":0"})
        self.assertTrue(r["accepted"])
        self.assertFalse(r["has_real_invoice"])

    def test_22_source_tamper_rejected(self):
        altered = copy.deepcopy(self.easy)
        altered["source_evidence"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SOURCE_DRIFT"):
            run_case(altered, CANDIDATE)

    def test_23_source_path_escape_rejected(self):
        altered = copy.deepcopy(self.easy)
        altered["source_evidence"][0]["path"] = "../../etc/passwd"
        with self.assertRaises(ValueError):
            validate_source(altered)

    def test_24_unbounded_config_rejected(self):
        with self.assertRaises(ValueError):
            replace(CANDIDATE, max_provider_calls=200)
        with self.assertRaises(ValueError):
            replace(CANDIDATE, max_tool_calls=1)

    def test_25_development_real_failure_to_proposal(self):
        b = evaluate(self.dev, BASELINE)
        a = evaluate(self.dev, CANDIDATE)
        self.assertEqual((b["accepted"], a["accepted"]), (16, 32))
        prop = propose_from_real_failure(b, a)
        self.assertEqual(prop["origin"]["failure_status"], "CALL_QUOTA_EXCEEDED")
        self.assertFalse(prop["approved"])
        self.assertFalse(prop["autopromote"])

    def test_26_heldout_evaluation_review_only(self):
        b = evaluate(self.dev, BASELINE)
        a = evaluate(self.dev, CANDIDATE)
        prop = propose_from_real_failure(b, a)
        held = heldout_review(self.holdout, prop)
        self.assertTrue(held["eligible_for_review"])
        self.assertEqual(held["candidate"]["accepted"], 16)
        self.assertEqual(held["reference"]["accepted"], 8)
        self.assertFalse(held["candidate_deployable"])

    def test_27_policy_pointer_never_autopromotes(self):
        self.assertEqual(ACTIVE_POLICY_ID, BASELINE.policy_id)
        self.assertNotEqual(ACTIVE_POLICY_ID, CANDIDATE.policy_id)

    def test_28_rollback_is_exact_original_policy(self):
        original = digest(canonical(evaluate(self.dev, BASELINE)))
        evaluate(self.dev, CANDIDATE)
        restored = digest(canonical(evaluate(self.dev, BASELINE)))
        self.assertEqual(original, restored)

    def test_29_repeatable_result_and_fixed_workload(self):
        self.assertEqual(digest(canonical(evaluate(self.tasks, CANDIDATE))),
                         digest(canonical(evaluate(self.tasks, CANDIDATE))))
        self.assertEqual(digest(WORKLOAD.read_bytes()),
                         "0a3c79da1d7c326203406ba1fc023ae63bd352d4cad6766c1f4e2cf7fa856a4d")

    def test_30_accounting_is_explicitly_not_real(self):
        for x in evaluate(self.dev, CANDIDATE)["rows"]:
            self.assertFalse(x["has_real_provider_receipt"])
            self.assertFalse(x["has_real_invoice"])
            self.assertGreaterEqual(x["cost_micro_usd_simulated"], 0)


if __name__ == "__main__":
    unittest.main()
