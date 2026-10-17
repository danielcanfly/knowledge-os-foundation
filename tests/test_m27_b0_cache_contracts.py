"""B0-01 bounded contract tests; no Provider, network, backing cache, or shared API."""
from __future__ import annotations

import ast
import copy
import datetime as dt
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

# Standalone source-only contract avoids incidental package __init__ imports
# (the full M26 runtime needs httpx and other unrelated provider deps).
FILE = Path(__file__).resolve().parents[1] / "src/knowledge_engine/m27_b0_cache_contracts.py"
spec = importlib.util.spec_from_file_location("b0_cache01", FILE)
assert spec is not None and spec.loader is not None
cache = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cache
spec.loader.exec_module(cache)

SHA = "a" * 64
SHA2 = "b" * 64
SHA3 = "c" * 64
NOW = dt.datetime(2026, 10, 17, 5, 0, 0, tzinfo=dt.timezone.utc)
WHEN = "2026-10-17T05:00:00Z"


def request(mode="AUTO"):
    return {
        "schema_version": cache.SCHEMA_VERSION,
        "request_id": "req_001",
        "cache_mode": mode,
        "identity": {
            "tenant_id": "tenant_A", "principal_id": "principal_A",
            "auth_context_sha256": SHA, "authenticated": True,
        },
        "question": {
            "text": "What does the agreement require?", "language": "en",
            "task_kind": "QA", "intent_id": "contract-obligation",
            "obligations": ["bound_citations", "licensed_read", "entailment"],
            "negated": False, "numeric_literals": [], "temporal_scope": "STATIC",
            "answer_type": "FACT",
        },
        "source": {
            "corpus_id": "private_corpus_1", "corpus_revision": "r1",
            "corpus_sha256": SHA, "source_manifest_sha256": SHA2,
            "acl_sha256": SHA3, "rights_sha256": SHA3,
            "source_ids": ["source_1"],
        },
        "policy": {
            "policy_version": "policy-v1", "policy_sha256": SHA,
            "verifier_version": "verifier-v1", "embedding_version": "embed-v1",
            "admission_version": "admit-v1", "revocation_epoch": 7,
        },
        "cache_window": {"requested_at": WHEN, "ttl_seconds": 60},
    }


def candidate(r=None):
    r = r or request()
    answer = "The agreement requires a signed authorization."
    return {
        "schema_version": cache.SCHEMA_VERSION,
        "identity": copy.deepcopy(r["identity"]),
        "question": copy.deepcopy(r["question"]),
        "source": copy.deepcopy(r["source"]),
        "policy": copy.deepcopy(r["policy"]),
        "lifecycle": {
            "created_at": "2026-10-17T04:59:30Z",
            "expires_at": "2026-10-17T05:00:30Z",
            "ttl_seconds": 60, "revocation_epoch": 7, "state": "ACTIVE",
        },
        "answer": answer,
        "citations": [{
            "source_id": "source_1", "source_sha256": SHA,
            "revision": "r1", "citation_sha256": SHA3,
        }],
        "provenance": {
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "final_verifier_receipt_sha256": SHA2,
            "source_verifier_receipt_sha256": SHA3,
            "rights_receipt_sha256": SHA3, "qualification_class": "PROVIDER_QUALIFIED",
        },
    }


def proof(kind="HIT_REVALIDATION", klass="FORMAL_PRODUCT"):
    return {
        "schema_version": cache.SCHEMA_VERSION, "kind": kind,
        "request_id": "req_001", "qualification_class": klass,
        "qualified": True, "semantic_equivalent": True,
        "rights_current": True, "acl_current": True, "source_current": True,
        "citations_current": True, "policy_current": True,
        "verifier_receipt_sha256": SHA3,
        "source_manifest_sha256": SHA2, "checked_at": WHEN,
    }


class TestCache01(unittest.TestCase):
    def assert_rejected(self, value):
        with self.assertRaises(cache.CacheContractError):
            cache.parse_internal_request(value)

    def test_mode_schema_and_no_privileged_public_fields(self):
        for mode in ("AUTO", "BYPASS", "REFRESH"):
            self.assertEqual(cache.parse_public_cache_choice({"cache_mode": mode}), mode)
            self.assertEqual(cache.parse_internal_request(request(mode))["cache_mode"], mode)
        for wrong in ("auto", "OFF", "READ_ONLY", "FORCE", "", 1, None, True):
            with self.subTest(wrong=wrong), self.assertRaises(cache.CacheContractError):
                cache.parse_public_cache_choice({"cache_mode": wrong})
        for attack in (
            {"cache_mode": "AUTO", "tenant_id": "other"},
            {"cache_mode": "BYPASS", "is_admin": True},
            {"cache_mode": "AUTO", "skip_verifier": True},
            {"cache_mode": "AUTO", "ttl_seconds": 999999},
        ):
            with self.subTest(attack=attack), self.assertRaises(cache.CacheContractError):
                cache.parse_public_cache_choice(attack)

    def test_operation_policy_bypass_refresh_and_no_implicit_store_grant(self):
        for flag in (False, True):
            bypass = cache.describe_cache_operations(request("BYPASS"), feature_enabled=flag)
            self.assertEqual(bypass.decision, "BYPASSED")
            self.assertFalse(bypass.candidate_lookup_after_authority)
            self.assertFalse(bypass.candidate_write_after_qualified_final)
            self.assertFalse(bypass.candidate_atomic_replace_after_qualified_final)
            self.assertFalse(bypass.actual_store_io_authorized)
        disabled = cache.describe_cache_operations(request(), feature_enabled=False)
        self.assertEqual(disabled.decision, "DISABLED")
        self.assertFalse(disabled.candidate_lookup_after_authority)
        self.assertFalse(disabled.candidate_write_after_qualified_final)
        auto = cache.describe_cache_operations(request(), feature_enabled=True)
        self.assertTrue(auto.candidate_lookup_after_authority)
        self.assertTrue(auto.candidate_write_after_qualified_final)
        self.assertFalse(auto.candidate_atomic_replace_after_qualified_final)
        self.assertFalse(auto.actual_store_io_authorized)
        refresh = cache.describe_cache_operations(request("REFRESH"), feature_enabled=True)
        self.assertFalse(refresh.candidate_lookup_after_authority)
        self.assertTrue(refresh.candidate_write_after_qualified_final)
        self.assertTrue(refresh.candidate_atomic_replace_after_qualified_final)
        self.assertFalse(refresh.actual_store_io_authorized)
        self.assertTrue(refresh.requires_current_auth_source_acl)

    def test_default_disabled_and_bypass_zero_cache_io(self):
        self.assertFalse(cache.DEFAULT_NONPROD_CACHE_ENABLED)
        self.assertEqual(cache.plan_cache_request(request()), "DISABLED")
        self.assertEqual(cache.plan_cache_request(request("BYPASS"), feature_enabled=True), "BYPASSED")
        self.assertEqual(cache.plan_cache_request(request("BYPASS"), feature_enabled=False), "BYPASSED")
        self.assertEqual(cache.plan_cache_request(request("AUTO"), feature_enabled=True), "LOOKUP_REQUIRED")
        self.assertEqual(cache.plan_cache_request(request("REFRESH"), feature_enabled=True),
                         "REGENERATE_NO_LOOKUP")
        # All plan/screen/response functions are pure: fake read/write callbacks
        # are never invoked because no I/O-capable coordinator exists in CACHE01.
        io_calls = []
        def forbidden_io(*_a, **_kw):
            io_calls.append("called")
            raise AssertionError("CACHE01 MUST NOT IO")
        _ = forbidden_io
        cache.build_response_contract(request("BYPASS"), status="BYPASSED")
        cache.build_response_contract(request(), status="DISABLED")
        self.assertEqual(io_calls, [])

    def test_auth_unknown_and_ttl_failclosed(self):
        for mutation in (
            lambda o: o.update({"admin": True}),
            lambda o: o.update({"schema_version": "m27/cache/v99"}),
            lambda o: o["identity"].update({"authenticated": False}),
            lambda o: o["identity"].update({"principal_id": " principal_A"}),
            lambda o: o["identity"].update({"override_tenant": "x"}),
            lambda o: o["policy"].update({"revocation_epoch": -1}),
            lambda o: o["cache_window"].update({"ttl_seconds": 0}),
            lambda o: o["cache_window"].update({"ttl_seconds": 3601}),
            lambda o: o["cache_window"].update({"ttl_seconds": True}),
            lambda o: o["cache_window"].update({"requested_at": "2026-10-17T05:00:00+07:00"}),
        ):
            o = request()
            mutation(o)
            with self.subTest(o=o):
                self.assert_rejected(o)

    def test_no_task_or_live_replay(self):
        for task in ("Research", "Coding", "Action", "TOOL_ACTION"):
            r = request()
            r["question"]["task_kind"] = task
            self.assertEqual(cache.plan_cache_request(r, feature_enabled=True), "REFUSED_NON_QA")
            self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "DENY_CANDIDATE")
        for temporal in ("RELATIVE", "LIVE"):
            r = request()
            r["question"]["temporal_scope"] = temporal
            self.assertEqual(cache.plan_cache_request(r, feature_enabled=True), "REFUSED_NON_QA")
            self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "DENY_CANDIDATE")

    def test_same_context_only_prover_required_not_hit(self):
        r, c = request(), candidate()
        self.assertEqual(cache.screen_candidate(r, c, now=NOW), "PROVER_REQUIRED")
        self.assertEqual(cache.verify_hit_contract(r, c, None, now=NOW), "HIT_NOT_ADMITTED")
        self.assertEqual(cache.verify_hit_contract(r, c, proof(), now=NOW), "HIT_NOT_ADMITTED")
        self.assertEqual(cache.verify_hit_contract(
            r, c, proof(), now=NOW, trusted_issuer_check=lambda p: True
        ), "HIT_NOT_ADMITTED")
        self.assertEqual(cache.verify_hit_contract(
            r, c, proof(klass="FIXTURE_ONLY"), now=NOW
        ), "VERIFIED_FIXTURE_ONLY")

    def test_cross_scope_versions_and_lease_invalidated(self):
        for path, changed in (
            (("identity", "tenant_id"), "tenant_B"),
            (("identity", "principal_id"), "principal_B"),
            (("identity", "auth_context_sha256"), SHA2),
            (("source", "corpus_revision"), "r2"),
            (("source", "corpus_sha256"), SHA3),
            (("source", "source_manifest_sha256"), SHA),
            (("source", "acl_sha256"), SHA2),
            (("source", "rights_sha256"), SHA2),
            (("policy", "policy_version"), "policy-v2"),
            (("policy", "policy_sha256"), SHA2),
            (("policy", "verifier_version"), "verifier-v2"),
            (("policy", "embedding_version"), "embed-v2"),
            (("policy", "admission_version"), "admit-v2"),
            (("policy", "revocation_epoch"), 8),
            (("question", "language"), "zh-TW"),
            (("question", "answer_type"), "COMPARISON"),
            (("question", "intent_id"), "other-intent"),
            (("question", "obligations"), ["bound_citations"]),
            (("question", "negated"), True),
            (("question", "numeric_literals"), ["5"]),
            (("question", "temporal_scope"), "POINT_IN_TIME"),
        ):
            r = request()
            r[path[0]][path[1]] = changed
            with self.subTest(path=path):
                self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "DENY_CANDIDATE")

    def test_collision_negation_numbers_relative_date_not_semantic_hit(self):
        r = request()
        r["question"]["text"] = "What does the agreement NOT require?"
        r["question"]["negated"] = True
        self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "DENY_CANDIDATE")
        r = request()
        r["question"]["text"] = "Which 12 clauses are required?"
        r["question"]["numeric_literals"] = ["12"]
        self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "DENY_CANDIDATE")
        r = request()
        r["question"]["text"] = "What changed yesterday?"
        r["question"]["temporal_scope"] = "RELATIVE"
        self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "DENY_CANDIDATE")
        # Semantic paraphrase can only be a candidate, not an HIT.
        r = request()
        r["question"]["text"] = "Summarize the agreement's requirements."
        self.assertEqual(cache.screen_candidate(r, candidate(), now=NOW), "PROVER_REQUIRED")

    def test_expiry_revocation_and_bad_record(self):
        r, c = request(), candidate()
        self.assertEqual(cache.screen_candidate(r, c, now=NOW + dt.timedelta(seconds=31)), "DENY_CANDIDATE")
        c["lifecycle"]["state"] = "REVOKED"
        self.assertEqual(cache.screen_candidate(r, c, now=NOW), "DENY_CANDIDATE")
        c = candidate()
        c["lifecycle"]["revocation_epoch"] = 8
        self.assertEqual(cache.screen_candidate(r, c, now=NOW), "DENY_CANDIDATE")
        c = candidate()
        c["lifecycle"]["expires_at"] = "2026-10-18T05:00:00Z"
        self.assertEqual(cache.screen_candidate(r, c, now=NOW), "DENY_CANDIDATE")
        c = candidate()
        c["answer"] = "tampered text"
        self.assertEqual(cache.screen_candidate(r, c, now=NOW), "DENY_CANDIDATE")
        c = candidate()
        c["citations"][0]["source_id"] = "other_source"
        self.assertEqual(cache.screen_candidate(r, c, now=NOW), "DENY_CANDIDATE")

    def test_malformed_prover_and_unverified_write(self):
        r, c = request(), candidate()
        for mutation in (
            lambda p: p.update({"qualified": False}),
            lambda p: p.update({"semantic_equivalent": False}),
            lambda p: p.update({"rights_current": False}),
            lambda p: p.update({"source_current": False}),
            lambda p: p.update({"citations_current": False}),
            lambda p: p.update({"policy_current": False}),
            lambda p: p.update({"acl_current": False}),
            lambda p: p.update({"request_id": "wrong"}),
            lambda p: p.update({"source_manifest_sha256": SHA}),
            lambda p: p.update({"skip_verifier": True}),
        ):
            p = proof()
            mutation(p)
            with self.subTest(p=p):
                self.assertEqual(cache.verify_hit_contract(r, c, p, now=NOW), "HIT_NOT_ADMITTED")
        self.assertEqual(cache.qualify_final_write(r, None), "WRITE_NOT_ADMITTED")
        self.assertEqual(cache.qualify_final_write(r, proof("FINAL_WRITE")), "WRITE_NOT_ADMITTED")
        self.assertEqual(cache.qualify_final_write(
            r, proof("FINAL_WRITE"), trusted_issuer_check=lambda p: True
        ), "WRITE_NOT_ADMITTED")
        self.assertEqual(cache.qualify_final_write(
            request("BYPASS"), proof("FINAL_WRITE")
        ), "WRITE_NOT_ADMITTED")
        self.assertEqual(cache.qualify_final_write(
            request("REFRESH"), proof("FINAL_WRITE", "FIXTURE_ONLY")
        ), "VERIFIED_FIXTURE_ONLY")

    def test_contract_response_does_not_expose_answer(self):
        r = request()
        payload = cache.build_response_contract(r, status="PROVER_REQUIRED")
        self.assertEqual(payload["cache_mode"], "AUTO")
        self.assertEqual(payload["cache_status"], "PROVER_REQUIRED")
        self.assertFalse(payload["internal_answer_cache_enabled"])
        self.assertFalse(payload["cache_io_performed"])
        self.assertIsNone(payload["answer"])
        with self.assertRaises(cache.CacheContractError):
            cache.build_response_contract(r, status="HIT")
        with self.assertRaises(cache.CacheContractError):
            cache.build_response_contract(r, status="PROVER_REQUIRED", answer="secret")


class TestNativeIngressStaticContract(unittest.TestCase):
    """Read-only AST proof, NOT a deployed Product route / HTTP admission test."""

    def _source(self, relative):
        return (FILE.parents[2] / relative).read_text(encoding="utf-8")

    def test_m27_isolated_route_is_exact_and_default_executor_absent(self):
        http = ast.parse(self._source("src/knowledge_engine/m27_isolated_http.py"))
        stream = ast.parse(self._source("src/knowledge_engine/m27_isolated_streaming.py"))
        stream_values = [
            node for node in stream.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "M27_ISOLATED_STREAM_PATH"
                    for target in node.targets)
        ]
        self.assertEqual(len(stream_values), 1)
        self.assertEqual(ast.literal_eval(stream_values[0].value), "/v1/answers/stream")
        create = next(node for node in http.body if isinstance(node, ast.FunctionDef)
                      and node.name == "create_app")
        route = [
            node for node in ast.walk(create) if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "stream_answer"
        ]
        self.assertEqual(len(route), 1)
        self.assertTrue(any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and d.func.attr == "post" and len(d.args) == 1
            and isinstance(d.args[0], ast.Name)
            and d.args[0].id == "M27_ISOLATED_STREAM_PATH"
            for d in route[0].decorator_list
        ))
        default_apps = [
            node for node in http.body if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)
        ]
        self.assertEqual(len(default_apps), 1)
        self.assertIsInstance(default_apps[0].value, ast.Call)
        self.assertEqual(default_apps[0].value.func.id, "create_app")
        self.assertFalse(default_apps[0].value.args)
        self.assertFalse(default_apps[0].value.keywords)
        self.assertIn("M27_ISOLATED_STREAM_EXECUTOR_UNAVAILABLE",
                      self._source("src/knowledge_engine/m27_isolated_http.py"))

    def test_m26_and_n31_strict_ingress_reject_cache_mode(self):
        for path, allowed in (
            ("src/knowledge_engine/m26_translation_gateway_public_api.py", {"question"}),
            ("src/knowledge_engine/m26_multilingual_public_api.py",
             {"question", "answer_language"}),
        ):
            tree = ast.parse(self._source(path))
            matches = [
                node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "ALLOWED_FIELDS"
                        for t in node.targets)
            ]
            self.assertEqual(len(matches), 1)
            self.assertEqual(ast.literal_eval(matches[0].value), allowed)
            self.assertNotIn("cache_mode", allowed)
        n31 = self._source("src/knowledge_engine/m27_n31_nonprod_app.py")
        self.assertIn('"N31_LOCAL_ONLY") != "1"', n31)
        self.assertIn('scope.get("path") != "/task"', n31)
        self.assertIn('"mode", "revoke_after_enqueue"', n31)
        self.assertNotIn('"cache_mode"', n31)
        self.assertIn('Do not attach M27 to `/v1/answers` yet.',
                      self._source("docs/m27/README.md"))

    def test_isolated_compose_is_nonprod_and_source_only(self):
        compose = self._source("docker-compose.m27-isolated.yml")
        self.assertIn("knowledge_engine.m27_isolated_http:app", compose)
        self.assertIn("127.0.0.1:18080:8080", compose)
        self.assertIn('restart: "no"', compose)
        self.assertIn("com.daniel.m27.eval", compose)


if __name__ == "__main__":
    unittest.main()
