"""B3-05 isolated integrated source+loopback client tests. Never calls cloud providers."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
sys.path.insert(0, str(SRC))
pkg = types.ModuleType("knowledge_engine")
pkg.__path__ = [str(SRC)]
sys.modules["knowledge_engine"] = pkg
from knowledge_engine import m27_b3_h02_cache_join as h02
from knowledge_engine import m27_b3_h02_routing_successor as rt
from knowledge_engine import m27_b3_provider_router as pol
from knowledge_engine import m27_b3_gateway_route_spec as spec
from knowledge_engine import m27_b1_cache_native_adapter as ui

CLIENT = Path(__file__).resolve().parents[1] / "tools/m27_b3_h02_routing_independent_client.py"
S1 = "Fixture-only source for local CACHE03/CACHE05 tests"
S2 = "not a signed claim."


def frame(who, kind, **kw):
    carrier = ({"carrier": "custom_cloudflare_worker_gateway",
                "route_id": rt.GATEWAY_FIXTURE_ROUTE_ID} if who == "cf"
               else {"carrier": "minimax", "protocol": "anthropic_messages"})
    return dict(carrier, kind=kind, **kw)


def success(who):
    return [
        frame(who, "meta", actual_upstream_model_id="fixture-upstream-" + who),
        frame(who, "candidate_claim", obligation_id=rt.OBLIGATIONS[0],
              text=S1, citation_ids=["fixture-source"]),
        frame(who, "candidate_claim", obligation_id=rt.OBLIGATIONS[1],
              text=S2, citation_ids=["fixture-source"]),
        frame(who, "done", observed_input_tokens=55,
              observed_output_tokens=28, observed_cost_usd=0.01),
    ]


def error(who, http_status, error_code=""):
    return [frame(who, "error", http_status=http_status, error_code=error_code)]


class ScriptedEndpoint:
    def __init__(self, sequence):
        self.responses = list(sequence)
        self.calls = 0
        self.after_frame = None

    def stream(self, request, timeout_s):
        self.calls += 1
        if not self.responses:
            raise ConnectionError("SCRIPT_EXHAUSTED_NO_NETWORK")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for pos, f in enumerate(response):
            if self.after_frame:
                self.after_frame(pos, f)
            if isinstance(f, Exception):
                raise f
            yield f


class Integrated(unittest.TestCase):
    def setUp(self):
        self.root_obj = tempfile.TemporaryDirectory(prefix="m27-b305-fixture-")
        self.addCleanup(self.root_obj.cleanup)
        self.root = Path(self.root_obj.name)
        keys = ["M27_H02_CACHE_JOIN_FIXTURE_MODE", "M27_CACHE02_FIXTURE_TEST_MODE",
                "M27_CACHE05_FIXTURE_TEST_MODE", "M27_B3_H02_ROUTE_FIXTURE_MODE"]
        old = {k: os.environ.get(k) for k in keys}
        for k in keys:
            os.environ[k] = "1"
        def restore():
            for k, value in old.items():
                if value is None: os.environ.pop(k, None)
                else: os.environ[k] = value
        self.addCleanup(restore)
        self.join = h02.H02CacheJoin(feature_enabled=True, fixture_only=True,
                                     fixture_root=self.root / "fixture")
        self.join.provision_test_source()
        self.sent = []

    def body(self, rid="b305test1001", mode="BYPASS"):
        return {"schema_version": ui.UI_SCHEMA, "request_id": rid,
                "cache_mode": mode, "question": "What does this fixture source say?"}

    def setup_route(self, cf=None, mm=None, fallback=True):
        cf = ScriptedEndpoint(cf if cf is not None else [success("cf")])
        mm = ScriptedEndpoint(mm if mm is not None else [success("mm")])
        pair = rt.StrictEnvelopePair(cf, mm)
        succ = rt.H02RoutingSuccessor(self.join, fixture_pair=pair,
                                      allow_test_fallback=fallback)
        return succ, pair, cf, mm

    def dispatch(self, succ, rid="b305test1001", mode="BYPASS", **kw):
        return succ.dispatch(body=self.body(rid, mode),
                             publish=lambda ob, txt: self.sent.append((ob,txt)), **kw)

    def assert_primary_only(self, pair):
        self.assertEqual([r["provider"] for r in pair.calls], [pol.PRIMARY])

    def revoke(self):
        return self.join.revocation.revoke(
            tenant="fixture-tenant", principal="fixture-principal",
            source_id="fixture-source", event_id="event-b305-rev-001",
            reason="SOURCE_RIGHTS_REVOKED", actor="fixture-principal",
            authorized_fixture=True)

    def test_01_default_cache_off_and_live_hold(self):
        off = h02.H02CacheJoin()
        successor = rt.H02RoutingSuccessor(off)
        self.assertIsNone(off.store)
        for mode in ("AUTO", "BYPASS", "REFRESH"):
            out, receipt = successor.dispatch(body=self.body(mode=mode), publish=lambda *_: None)
            self.assertIsNone(out)
            self.assertEqual(receipt["primary_live"], "PRIMARY_LIVE_HOLD")
            self.assertEqual(receipt["actual_provider_calls"], 0)
            self.assertFalse(receipt["route_activated"])
        self.assertEqual(off.store_lookup_calls, 0)
        self.assertEqual(off.store_write_calls, 0)

    def test_02_fixture_must_be_opted_in(self):
        os.environ.pop("M27_B3_H02_ROUTE_FIXTURE_MODE", None)
        with self.assertRaisesRegex(ValueError, "FIXTURE_ONLY"):
            rt.H02RoutingSuccessor(self.join, fixture_pair=rt.StrictEnvelopePair(
                ScriptedEndpoint([]), ScriptedEndpoint([])))

    def test_03_healthy_primary_no_fallback_and_2_verified_claims(self):
        succ, pair, _, mm = self.setup_route()
        out, receipt = self.dispatch(succ)
        self.assertEqual(out.status, "answered")
        self.assertEqual(len(self.sent), 2)
        self.assertEqual([x[0] for x in self.sent], list(rt.OBLIGATIONS))
        self.assert_primary_only(pair)
        self.assertEqual(mm.calls, 0)
        self.assertEqual(out.attempted[0].actual_upstream_model_id, "fixture-upstream-cf")
        self.assertEqual(receipt["observed_input_tokens"], 55)
        self.assertEqual(receipt["observed_output_tokens"], 28)
        self.assertEqual(receipt["observed_cost_usd"], 0.01)
        self.assertFalse(receipt["issued_by_independent_verifier"])
        self.assertEqual(receipt["cache_receipt"]["answer_cache_lookup_invocations"], 0)

    def test_04_eligible_failovers_timeout_429_5xx(self):
        for reason, failure in (
            ("TIMEOUT", TimeoutError("fixture timeout")),
            ("QUOTA", error("cf", 429)),
            ("UPSTREAM_5XX", error("cf", 503)),
            ("UNAVAILABLE", ConnectionError("fixture unreachable")),
        ):
            with self.subTest(reason=reason):
                succ, pair, _, _ = self.setup_route([failure, failure])
                out, receipt = self.dispatch(succ, rid="route" + reason.lower() + "100")
                self.assertEqual(out.status, "answered")
                self.assertEqual(out.fallback_reason, reason)
                self.assertEqual([x["provider"] for x in pair.calls],
                                 [pol.PRIMARY, pol.PRIMARY, pol.FALLBACK])
                self.assertEqual(len(set((x["provider"], x["billing_idempotency_key_sha256"])
                                         for x in pair.calls)), 2)
                self.sent.clear()

    def test_05_401_403_acl_and_config_do_not_bypass(self):
        for status in (401, 403, 400, 422):
            with self.subTest(status=status):
                succ, pair, _, _ = self.setup_route([error("cf", status)])
                out, _ = self.dispatch(succ, rid="authcase" + str(status))
                self.assertEqual(out.status, "safe_abstention")
                self.assertEqual(len(pair.calls), 1)
                self.assertEqual(out.reason, "AUTH" if status in (401,403) else "CONFIG")

    def test_06_done_200_no_text_refused(self):
        succ, pair, *_ = self.setup_route([[
            frame("cf", "meta", actual_upstream_model_id="fixture-upstream-cf"),
            frame("cf", "done")]])
        out, _ = self.dispatch(succ)
        self.assertEqual(out.reason, "EMPTY_GENERATION")
        self.assertEqual(len(pair.calls), 1)
        self.assertFalse(self.sent)

    def test_07_malformed_direct_workers_ai_and_unknown_source(self):
        broken = [dict(x) for x in success("cf")]
        broken[0]["carrier"] = "workers_ai_direct"
        succ, pair, *_ = self.setup_route([broken])
        out, _ = self.dispatch(succ)
        self.assertEqual(out.reason, "UNKNOWN")
        self.assertFalse(self.sent)
        self.assertEqual(len(pair.calls), 1)
        self.assertFalse(spec.audit_route_registry({}).shape_valid)

    def test_08_false_safe_verification_fails_closed(self):
        broken = success("cf")
        broken[1]["text"] = "Completely fabricated external outcome"
        succ, pair, *_ = self.setup_route([broken])
        out, _ = self.dispatch(succ)
        self.assertEqual(out.reason, "VERIFIER")
        self.assertEqual(len(pair.calls), 1)
        self.assertFalse(self.sent)

    def test_09_source_revoke_before_provider(self):
        succ, pair, *_ = self.setup_route()
        self.revoke()
        out, receipt = self.dispatch(succ)
        self.assertEqual(out.status, "safe_abstention")
        self.assertEqual(receipt["reason"], "REVOKED")
        self.assertFalse(pair.calls)

    def test_10_source_revoke_midstream_prevents_second_claim_and_fallback(self):
        succ, pair, cf, mm = self.setup_route()
        def callback(pos, f):
            if pos == 2:
                self.revoke()
        cf.after_frame = callback
        out, receipt = self.dispatch(succ)
        self.assertEqual(out.status, "partial_terminated")
        self.assertEqual(out.reason, "REVOKED")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(mm.calls, 0)
        self.assertEqual(receipt["primary_live"], "PRIMARY_LIVE_HOLD")

    def test_11_partial_model_loss_never_silent_replay(self):
        broken = success("cf")[:2] + [ConnectionError("fixture mid-stream")]
        succ, pair, *_ = self.setup_route([broken])
        out, _ = self.dispatch(succ)
        self.assertEqual(out.status, "partial_terminated")
        self.assertEqual(out.reason, "UNAVAILABLE")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(pair.calls), 1)

    def test_12_client_cancel_after_first_verified_answer(self):
        succ, pair, *_ = self.setup_route()
        cancelled = [False]
        def on_publish(ob, txt):
            self.sent.append((ob, txt)); cancelled[0] = True
        out, _ = succ.dispatch(body=self.body(), publish=on_publish,
                               cancelled=lambda: cancelled[0])
        self.assertEqual(out.status, "partial_terminated")
        self.assertEqual(out.reason, "CANCELLED")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(pair.calls), 1)

    def test_13_unknown_rights_and_cross_tenant_denied(self):
        succ, pair, *_ = self.setup_route()
        bad = self.body()
        bad["tenant"] = "other"
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            succ.dispatch(body=bad, publish=lambda *_: None)
        self.assertFalse(pair.calls)
        self.join.revocation.downgrade_acl_fixture(
            tenant="fixture-tenant", principal="fixture-principal",
            source_id="fixture-source", actor="fixture-principal",
            authorized_fixture=True)
        out, rec = self.dispatch(succ)
        self.assertEqual(out.status, "safe_abstention")
        self.assertEqual(rec["reason"], "REVOKED")

    def test_14_cache_modes_never_release_hit_or_write(self):
        succ, pair, *_ = self.setup_route(cf=[success("cf")] * 3)
        for index, mode in enumerate(("AUTO", "BYPASS", "REFRESH")):
            out, receipt = self.dispatch(succ, rid=f"cachemode{index+1}xyz", mode=mode)
            cr = receipt["cache_receipt"]
            self.assertEqual(out.status, "answered")
            self.assertFalse(cr["answer_cache_hit_admitted"])
            self.assertEqual(cr["answer_cache_write_invocations"], 0)
            self.assertEqual(cr["answer_cache_lookup_invocations"], 1 if mode=="AUTO" else 0)
        self.assertEqual(self.join.store_write_calls, 0)
        self.assertEqual(len(pair.calls), 3)

    def test_15_circuit_breaker_fallback_after_primary_failures(self):
        succ, pair, *_ = self.setup_route(
            cf=[error("cf", 503), error("cf", 503)],
            mm=[success("mm"), success("mm")])
        first, _ = self.dispatch(succ, rid="circuitfirst100")
        self.assertEqual(first.status, "answered")
        self.sent.clear()
        second, _ = self.dispatch(succ, rid="circuitsecond101")
        self.assertEqual(second.status, "answered")
        self.assertEqual(second.fallback_reason, "CIRCUIT_OPEN")
        self.assertEqual([x["provider"] for x in pair.calls],
                         [pol.PRIMARY, pol.PRIMARY, pol.FALLBACK, pol.FALLBACK])

    def test_16_no_fallback_consent_safe_abstention(self):
        succ, pair, *_ = self.setup_route(
            cf=[error("cf", 503), error("cf", 503)], fallback=False)
        out, _ = self.dispatch(succ)
        self.assertEqual(out.reason, "FALLBACK_NOT_AUTHORIZED")
        self.assertEqual(len(pair.calls), 2)

    def test_17_both_providers_fail_abstention(self):
        succ, pair, *_ = self.setup_route(
            cf=[error("cf", 502), error("cf", 503)], mm=[error("mm", 503)])
        out, _ = self.dispatch(succ)
        self.assertEqual(out.status, "safe_abstention")
        self.assertEqual([x["provider"] for x in pair.calls],
                         [pol.PRIMARY, pol.PRIMARY, pol.FALLBACK])

    def test_18_token_budget_and_model_usage_limits(self):
        succ, pair, *_ = self.setup_route()
        succ.router.config = pol.RouteConfig(max_total_attempt_tokens=10)
        out, _ = self.dispatch(succ)
        self.assertEqual(out.reason, "BUDGET")
        self.assertFalse(pair.calls)

    def test_19_missing_usage_receipt_aborts_without_secondary_charge(self):
        no_usage = success("cf")[:-1] + [frame("cf", "done")]
        succ, pair, *_ = self.setup_route(cf=[no_usage])
        out, receipt = self.dispatch(succ)
        self.assertEqual(out.status, "partial_terminated")
        self.assertEqual(out.reason, "USAGE_RECEIPT_MISSING_AFTER_TEXT")
        self.assertEqual(len(pair.calls), 1)
        self.assertEqual(len(self.sent), 2)
        self.assertIsNone(receipt["observed_cost_usd"])

    def test_20_real_os_client_streams_and_acknowledges(self):
        succ, pair, *_ = self.setup_route()
        host = rt.H02RoutedLoopback(succ)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        os_client = subprocess.run(
            [sys.executable, str(CLIENT), host.origin, "osclient1001", "BYPASS"],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(os_client.returncode, 0, os_client.stderr)
        evidence = json.loads(os_client.stdout)
        self.assertNotEqual(evidence["client_process_pid"], os.getpid())
        self.assertEqual(evidence["http_status"], 200)
        self.assertEqual([x["kind"] for x in evidence["events"]],
                         ["answer_text", "answer_text", "terminal"])
        self.assertTrue(evidence["client_first_text_before_terminal"])
        self.assertEqual(evidence["terminal"]["status"], "answered")
        self.assertEqual(evidence["ack"]["http_status"], 200)
        self.assertEqual(evidence["ack"]["ack_count"], 2)
        self.assertEqual(len(pair.calls), 1)
        dest = os.environ.get("B305_EVIDENCE_DIR")
        if dest:
            Path(dest).mkdir(parents=True, exist_ok=True)
            (Path(dest) / "b305_real_os_independent_client.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def test_20_real_os_client_default_off_503_no_calls(self):
        off = rt.H02RoutingSuccessor(h02.H02CacheJoin())
        host = rt.H02RoutedLoopback(off)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        os_client = subprocess.run(
            [sys.executable, str(CLIENT), host.origin, "osclienthold1002", "AUTO"],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(os_client.returncode, 0, os_client.stderr)
        evidence = json.loads(os_client.stdout)
        self.assertEqual(evidence["http_status"], 503)
        self.assertIsNone(evidence["ack"])
        self.assertIsNone(evidence["terminal"])
        self.assertIsNone(off.join.store)

    def test_21_replay_ack_and_auth_bypass_denied(self):
        succ, pair, *_ = self.setup_route()
        host = rt.H02RoutedLoopback(succ)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        body = json.dumps(self.body("httpbad1001")).encode()
        req = urllib.request.Request(
            host.origin + rt.ROUTE_PATH, data=body,
            headers={"Content-Type":"application/json","Origin":host.origin,
                     "X-Cache-Demo-Request":"1"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(err.exception.code, 403)
        self.assertFalse(pair.calls)


    def test_22_partial_done_missing_obligation_no_provider_switch(self):
        early = success("cf")[:2] + [success("cf")[-1]]
        succ, pair, *_ = self.setup_route(cf=[early])
        out, receipt = self.dispatch(succ)
        self.assertEqual(out.status, "partial_terminated")
        self.assertEqual(out.reason, "OBLIGATION")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(pair.calls), 1)

    def test_23_external_os_client_qualified_fallback_receipt(self):
        succ, pair, *_ = self.setup_route(
            cf=[error("cf", 502), error("cf", 503)],
            mm=[success("mm")])
        host = rt.H02RoutedLoopback(succ)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        proc = subprocess.run(
            [sys.executable, str(CLIENT), host.origin, "osclientfallbk1003", "REFRESH"],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ev = json.loads(proc.stdout)
        self.assertEqual(ev["terminal"]["status"], "answered")
        self.assertEqual(ev["terminal"]["fallback_reason"], "UPSTREAM_5XX")
        self.assertEqual([x["provider"] for x in pair.calls],
                         [pol.PRIMARY, pol.PRIMARY, pol.FALLBACK])
        self.assertEqual([a["provider_attempted"] for a in ev["terminal"]["attempts"]],
                         [pol.PRIMARY, pol.PRIMARY, pol.FALLBACK])
        self.assertEqual(ev["ack"]["ack_count"], 2)
        self.assertEqual(ev["terminal"]["cache_receipt"]["answer_cache_lookup_invocations"], 0)
        self.assertFalse(ev["terminal"]["answer_cache_hit_admitted"])
        dest = os.environ.get("B305_EVIDENCE_DIR")
        if dest:
            (Path(dest) / "b305_real_os_independent_client_fallback.json").write_text(
                json.dumps(ev, indent=2, sort_keys=True), encoding="utf-8")

    def test_24_external_os_client_401_abstain_without_fallback(self):
        succ, pair, *_ = self.setup_route(cf=[error("cf", 401)])
        host = rt.H02RoutedLoopback(succ)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        proc = subprocess.run(
            [sys.executable, str(CLIENT), host.origin, "osclientauth4014", "AUTO"],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ev = json.loads(proc.stdout)
        self.assertEqual(ev["terminal"]["status"], "safe_abstention")
        self.assertEqual(ev["terminal"]["reason"], "AUTH")
        self.assertEqual([x["kind"] for x in ev["events"]], ["terminal"])
        self.assertIsNone(ev["ack"])
        self.assertEqual([x["provider"] for x in pair.calls], [pol.PRIMARY])
        self.assertFalse(ev["terminal"]["answer_cache_hit_admitted"])
        dest = os.environ.get("B305_EVIDENCE_DIR")
        if dest:
            (Path(dest) / "b305_real_os_independent_client_auth_denied.json").write_text(
                json.dumps(ev, indent=2, sort_keys=True), encoding="utf-8")

    def test_25_research_preserved_through_successor_http(self):
        from knowledge_engine import m27_b1_g02_native_bridge as research
        from knowledge_engine.m27_task_contracts_v1 import sha256 as sha_contract
        inp = Path(os.environ["G02_EVIDENCE_ROOT"]) / "input"
        contract = json.loads((inp / "task_contract.json").read_bytes())
        sources = json.loads((inp / "sources.json").read_bytes())
        a, b = self.root / "successor_task.json", self.root / "successor_sources.json"
        a.write_bytes(research.canonical(contract))
        b.write_bytes(research.canonical(sources))
        outdir = self.root / "research_outcome"
        outdir.mkdir()
        checker = Path(__file__).resolve().parents[1] / "tools/m27_b0_research_independent_check.py"
        bridge = research.ResearchBridge(
            contract_path=a, registry_path=b,
            db_path=self.root / "g02_successor.sqlite3",
            outcome_dir=outdir, independent_checker=checker,
            tenant_id="owner-m27-nonprod", principal_id="owner-delegated-b0-02")
        succ = rt.H02RoutingSuccessor(self.join)
        server = rt.H02RoutedLoopback(succ, research_bridge=bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        cookie = urllib.request.urlopen(
            server.origin + "/__cache04/demo/", timeout=3).headers[
            "Set-Cookie"].split(";")[0]
        request = {
            "schema": research.REQUEST_SCHEMA,
            "request_id": "b305-successor-research",
            "run_id": "b305-real-research",
            "task_id": contract["task_id"],
            "task_version": contract["task_version"],
            "tenant_id": "owner-m27-nonprod",
            "principal_id": "owner-delegated-b0-02",
            "contract_sha256": sha_contract(contract),
            "registry_sha256": hashlib.sha256(research.canonical(sources)).hexdigest(),
            "outcome_id": contract["output_specs"][0]["outcome_id"],
        }
        req = urllib.request.Request(
            server.origin + h02.RESEARCH_PATH,
            data=research.canonical(request),
            headers={"Content-Type": "application/json", "Origin": server.origin,
                     "X-Cache-Demo-Request": "1", "Cookie": cookie}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            outcome = json.loads(resp.read())
        self.assertEqual(outcome["state"], "DURABLE_SOURCE_BACKED_RESEARCH_READBACK_PASS")
        self.assertEqual(outcome["citations"], 4)
        self.assertEqual(outcome["cache_join"], "RESEARCH_NONCACHEABLE")
        self.assertFalse(outcome["formal_product_qualified"])
        self.assertFalse(outcome["product_authenticated"])
        self.assertEqual(hashlib.sha256(Path(outcome["markdown_path"]).read_bytes()).hexdigest(),
                         outcome["markdown_sha256"])
        self.assertEqual(self.join.store_lookup_calls, 0)
        self.assertEqual(self.join.store_write_calls, 0)
        dest = os.environ.get("B305_EVIDENCE_DIR")
        if dest:
            snapshot = {
                "run_id": request["run_id"],
                "citation_count": outcome["citations"],
                "state": outcome["state"],
                "markdown_sha256": outcome["markdown_sha256"],
                "outcome_path_kind": "isolated_local_durable",
                "cache_join": outcome["cache_join"],
                "product_authenticated": outcome["product_authenticated"],
                "provider_calls": 0,
            }
            (Path(dest) / "b305_successor_research_durable_receipt.json").write_text(
                json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    def test_26_ack_cancel_and_replay_denied(self):
        succ, pair, *_ = self.setup_route()
        host = rt.H02RoutedLoopback(succ)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        proc = subprocess.run([sys.executable, str(CLIENT), host.origin,
                               "ackreplay1001", "BYPASS"],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        client = json.loads(proc.stdout)
        self.assertEqual(client["ack"]["http_status"], 200)
        self.assertIn("ackreplay1001", host.acked)
        claims = [
            {"obligation_id": rt.OBLIGATIONS[i],
             "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
            for i, text in enumerate((S1, S2))]
        import http.cookiejar
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        opener.open(host.origin + "/nonprod/h02/session").read()
        hdr = {"Content-Type": "application/json", "Origin": host.origin,
               "X-Cache-Demo-Request": "1"}
        for altered in (
            {"request_id": "ackreplay1001", "claims": claims},
            {"request_id": "unknowncancel1001", "claims": claims},
        ):
            req = urllib.request.Request(
                host.origin + rt.ACK_PATH, data=json.dumps(altered).encode(),
                headers=hdr, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as error:
                opener.open(req, timeout=3)
            self.assertEqual(error.exception.code, 409)
            error.exception.close()
        self.assertEqual(len(pair.calls), 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
