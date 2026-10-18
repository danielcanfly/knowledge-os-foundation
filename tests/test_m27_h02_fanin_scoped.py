"""H02 unique source-fanin guard regression. Offline, unsigned, NOT a Product E2E."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "knowledge_engine"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(ROOT / "tools"))
pkg = sys.modules.get("knowledge_engine")
if pkg is None:
    pkg = types.ModuleType("knowledge_engine")
    pkg.__path__ = [str(SOURCE)]
    sys.modules["knowledge_engine"] = pkg

from knowledge_engine import m27_b3_provider_router as routing
from knowledge_engine import m27_g05_governed_cost as cost
import m27_b0_cache_contracts as cache
import m27_f03_source_rights_admission as rights
import m27_g01_qa_outcome as qa
import m27_f02_reliability_stream as stream


class ScopedAdmission(unittest.TestCase):
    def scope(self, **changes):
        kw = dict(task_sha256="task-local-only", tenant="owner-nonprod",
                  principal="os-local", source_sha256="source-revision",
                  acl_epoch="lease-1", max_total_tokens=200,
                  max_attempts=2, max_wall_ms=1000,
                  max_reserved_usd="0.1", fallback_consented=True)
        kw.update(changes)
        return cost.BudgetScope(**kw)

    def tariff(self, **changes):
        kw = dict(provider=routing.PRIMARY, model_id="fixture-not-deployed",
                  version="v1", source_timestamp="2026-10-18T00:00Z",
                  input_per_million_usd="0.2", output_per_million_usd="0.5",
                  independently_verified=True, evidence_sha256="a" * 64)
        kw.update(changes)
        return cost.Tariff(**kw)

    def reserve(self, governor, *, key="only", provider=None, model_id=None,
                tariff=None, fallback_reason=None, **changes):
        kw = dict(key=key, provider=provider or routing.PRIMARY,
                  model_id=model_id or "fixture-not-deployed",
                  tariff=tariff or self.tariff(), input_tokens=30,
                  output_tokens=10, task_sha256="task-local-only",
                  tenant="owner-nonprod", principal="os-local",
                  source_sha256="source-revision", acl_epoch="lease-1",
                  elapsed_ms=20, fallback_reason=fallback_reason)
        kw.update(changes)
        return governor.reserve(**kw)

    def test_fanin_has_exact_primary_and_only_conditional_fallback(self):
        self.assertEqual(routing.PRIMARY, "cloudflare_custom_worker_gateway")
        self.assertEqual(routing.FALLBACK, "minimax")
        self.assertEqual(qa.decide_provider(primary_provenance=False,
                         first_failure=None, fallback_consent=True,
                         published_claims=0), "PRIMARY_LIVE_HOLD")

    def test_g01_synthetic_does_not_create_real_provider(self):
        self.assertEqual(qa.ABI, "m27.g01.qa-independent/v1")
        self.assertEqual(qa.decide_provider(primary_provenance=True,
                         first_failure="AUTH", fallback_consent=True,
                         published_claims=0), "NO_FALLBACK")

    def test_g01_no_mid_answer_fallback(self):
        self.assertEqual(qa.decide_provider(primary_provenance=True,
                         first_failure="TIMEOUT", fallback_consent=True,
                         published_claims=1), "NO_FALLBACK")

    def test_f03_real_owner_data_never_licenses_product(self):
        self.assertIn("MISSING_INDEPENDENT_PRODUCT_IDP_RIGHTS_ISSUER",
                      str(rights.product_source_admission()))
        self.assertIn("BYPASS", SOURCE.joinpath(
                      "m27_f03_source_rights_admission.py").read_text())

    def test_default_cache_off_not_product_write(self):
        self.assertFalse(cache.DEFAULT_NONPROD_CACHE_ENABLED)

    def test_f02_source_bound_two_claims_not_general_semantic_grant(self):
        a, b = stream.source_bindings()
        self.assertTrue(stream.verify_claim(
            "The semantic answer cache is initially OFF in Nonprod.", a)["accepted"])
        self.assertTrue(stream.verify_claim(
            "Remote Desktop Commander is first for engineering on MacBook.", b)["accepted"])
        self.assertFalse(stream.verify_claim(
            "The semantic answer cache is ON in Production.", a)["accepted"])

    def test_f02_empty_or_unverified_stream_fails_closed(self):
        with self.assertRaises(ValueError):
            stream.validate([], require_live=True)

    def test_g05_primary_quote_not_actual_invoice(self):
        g = cost.CostGovernor(self.scope())
        self.reserve(g)
        s = g.snapshot()
        self.assertEqual(s["attempts_reserved"], 1)
        self.assertIsNone(s["actual_bill_usd"])
        self.assertEqual(s["unknown_bill_count"], 1)
        self.assertTrue(s["fixture_not_bill"])

    def test_g05_no_unapproved_minimax_shortcut(self):
        g = cost.CostGovernor(self.scope())
        with self.assertRaisesRegex(PermissionError, "ILLEGAL_FALLBACK"):
            self.reserve(g, provider=routing.FALLBACK,
                         model_id="minimax-fixture",
                         tariff=self.tariff(provider=routing.FALLBACK,
                                            model_id="minimax-fixture"),
                         fallback_reason=routing.Failure.TIMEOUT)

    def test_g05_source_version_acl_deny(self):
        with self.assertRaisesRegex(PermissionError, "SCOPE"):
            self.reserve(cost.CostGovernor(self.scope()),
                         source_sha256="other-version")
        with self.assertRaisesRegex(PermissionError, "SCOPE"):
            self.reserve(cost.CostGovernor(self.scope()), tenant="cross-tenant")

    def test_g05_issuer_missing_tariff_denies(self):
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_TARIFF"):
            self.reserve(cost.CostGovernor(self.scope()),
                         tariff=self.tariff(independently_verified=False))

    def test_g05_negative_no_replay_and_budget(self):
        g = cost.CostGovernor(self.scope())
        self.reserve(g)
        with self.assertRaisesRegex(ValueError, "REPLAY"):
            self.reserve(g)
        with self.assertRaisesRegex(PermissionError, "QUOTA"):
            self.reserve(cost.CostGovernor(self.scope(max_total_tokens=30)))

    def test_g05_no_post_first_text_fallback_attestation(self):
        g = cost.CostGovernor(self.scope())
        self.reserve(g)
        with self.assertRaisesRegex(PermissionError, "PRIMARY_FAILURE_PROOF"):
            g.register_primary_operational_failure(
                reservation_key="only", reason=routing.Failure.TIMEOUT,
                answer_text_emitted=True)

    def test_g05_production_learning_denied(self):
        with self.assertRaises((PermissionError, ValueError, RuntimeError)):
            cost.GovernedLearning().promote_production()


if __name__ == "__main__":
    unittest.main()
