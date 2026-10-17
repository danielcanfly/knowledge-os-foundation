"""End-to-end H02 cache+G02 scoped adapter tests, all source modules co-located."""
import copy
import datetime as dt
import hashlib
import hmac
import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request

SOURCE = Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
sys.path.insert(0, str(SOURCE))
if "knowledge_engine" not in sys.modules:
    pkg = types.ModuleType("knowledge_engine")
    pkg.__path__ = [str(SOURCE)]
    sys.modules["knowledge_engine"] = pkg

from knowledge_engine import m27_b3_h02_cache_join as joined
from knowledge_engine import m27_b1_cache_native_adapter as ui
from knowledge_engine import m27_b0_cache_contracts as abi
from knowledge_engine import m27_b2_cache_writeback_gate as gate
from knowledge_engine import m27_b1_cache_store as store
from knowledge_engine import m27_b1_g02_native_bridge as research

EVIDENCE = Path(os.environ["G02_EVIDENCE_ROOT"])
CHECKER = Path(__file__).resolve().parents[1] / "tools/m27_b0_research_independent_check.py"


class H02JoinedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m27-b3-h02-cache-join-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        keys = ("M27_H02_CACHE_JOIN_FIXTURE_MODE", "M27_CACHE02_FIXTURE_TEST_MODE",
                "M27_CACHE05_FIXTURE_TEST_MODE")
        previous = {k: os.environ.get(k) for k in keys}
        for key in keys:
            os.environ[key] = "1"
        def restore():
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.addCleanup(restore)
        self.off = joined.H02CacheJoin()
        self.on = joined.H02CacheJoin(
            feature_enabled=True, fixture_only=True, fixture_root=self.root / "fixture")
        self.on.provision_test_source()

    def request(self, mode="AUTO", text="What does this fixture source say?",
                request_id="joined-test-1001"):
        return ui.internal_demo_envelope(mode, text, request_id)

    def server(self, *, join=None, bridge=None):
        host = joined.H02JoinedLoopback(join or self.off, research_bridge=bridge)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        return host

    def call(self, server, mode="AUTO", *, body=None, request_id="cache-join-1001",
             origin=True, cookie=True, headers=None, cancel=False):
        url = server.origin
        data = body if body is not None else dict(
            schema_version=ui.UI_SCHEMA, cache_mode=mode,
            question="What does this fixture source say?", request_id=request_id)
        cookies = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        if cookie:
            opener.open(url + "/__cache04/demo/").read()
        request_headers = {"Content-Type": "application/json", "X-Cache-Demo-Request": "1"}
        if origin:
            request_headers["Origin"] = url
        if cancel:
            request_headers["X-Cache-Demo-Cancelled"] = "1"
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url + ui.DEMO_PATH, json.dumps(data).encode(),
            headers=request_headers, method="POST")
        try:
            response = opener.open(request)
            return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def proof_fixture(self, r, now=None):
        now = now or joined.utcnow()
        answer = joined._FIXTURE_SOURCE.decode()
        sha = gate.sha(joined._FIXTURE_SOURCE)
        citation = dict(source_id="fixture-source", source_sha256=sha,
                        revision=r["source"]["corpus_revision"], citation_sha256=sha)
        claim = dict(id="claim-1", text=answer, text_sha256=gate.sha(answer.encode()),
                     verdict="ENTAILED", evidence_spans=[dict(
                         source_id="fixture-source", start=0, end=len(joined._FIXTURE_SOURCE),
                         excerpt_sha256=sha)])
        final = dict(answer=answer, citations=[citation], claims=[claim])
        snapshot, _bindings = self.on.authority.snapshot(r, actor=self.on.actor, now=now)
        proof = dict(
            schema_version=gate.VERSION, qualification_class="FIXTURE_ONLY",
            issuer_id="INDEPENDENT_TEST_FIXTURE_VERIFIER",
            generator_id="TEST_FIXTURE_GENERATOR", verifier_id="TEST_FIXTURE_VERIFIER",
            request_id=r["request_id"], request_sha256=gate.digest(r),
            final_sha256=gate.digest(final),
            auth_context_sha256=r["identity"]["auth_context_sha256"],
            source_manifest_sha256=r["source"]["source_manifest_sha256"],
            rights_snapshot_sha256=gate.sha(snapshot.encode()),
            source_bytes_sha256=gate.digest({"fixture-source": sha}),
            checked_at=gate.z(now - dt.timedelta(seconds=1)),
            expires_at=gate.z(now + dt.timedelta(seconds=45)),
            claims=copy.deepcopy(final["claims"]),
            obligations=[dict(name=name, verdict="SATISFIED", claim_ids=["claim-1"])
                         for name in r["question"]["obligations"]])
        proof["signature"] = hmac.new(
            joined._FIXTURE_PROOF_KEY, gate.canonical(proof),
            hashlib.sha256).hexdigest()
        return final, proof, now

    def seed(self, mode="AUTO"):
        r = self.request(mode)
        final, proof, now = self.proof_fixture(r)
        result = self.on.fixture_gate().admit_fixture(
            r, final, proof, source_bytes={"fixture-source": joined._FIXTURE_SOURCE},
            now=now)
        return r, final, proof, result

    def test_01_off_zero_store_init_all_modes(self):
        self.assertIsNone(self.off.store)
        for i, mode in enumerate(("AUTO", "BYPASS", "REFRESH")):
            reply = self.off.dispatch_cache(mode=mode, question="Static question",
                                             request_id=f"test-off-000{i}")
            self.assertEqual(reply["cache_status"],
                             ("DISABLED", "BYPASSED", "DISABLED")[i])
            self.assertEqual(reply["answer_cache_lookup_invocations"], 0)
            self.assertFalse(reply["answer_cache_hit_admitted"])
            self.assertFalse(reply["product_authenticated"])

    def test_02_requires_explicit_nonprod_switch(self):
        os.environ.pop("M27_H02_CACHE_JOIN_FIXTURE_MODE", None)
        with self.assertRaisesRegex(ValueError, "TEST_ONLY_SWITCH_REQUIRED"):
            joined.H02CacheJoin(feature_enabled=True, fixture_only=True,
                                fixture_root=self.root / "unapproved")

    def test_03_auto_joins_cache02_and_two_rights_authorities(self):
        self.assertTrue(self.on._current_source_rights(self.request()))
        receipt = self.on.dispatch_cache(
            mode="AUTO", question="What does this fixture source say?",
            request_id="test-auto-0003")
        self.assertEqual(receipt["cache_status"], "LOOKUP_REQUIRED")
        self.assertEqual(receipt["answer_cache_lookup_invocations"], 1)
        self.assertFalse(receipt["answer_cache_hit_admitted"])
        self.assertFalse(self.on.store.path.exists())

    def test_04_bypass_never_calls_store(self):
        receipt = self.on.dispatch_cache(
            mode="BYPASS", question="What does this fixture source say?",
            request_id="test-bypass-004")
        self.assertEqual(receipt["cache_status"], "BYPASSED")
        self.assertEqual(self.on.store_lookup_calls, 0)
        self.assertEqual(self.on.store_write_calls, 0)
        self.assertFalse(self.on.store.path.exists())

    def test_05_refresh_skips_old_answer_and_denies_write(self):
        receipt = self.on.dispatch_cache(
            mode="REFRESH", question="What does this fixture source say?",
            request_id="test-refresh-005")
        self.assertEqual(receipt["cache_status"], "REGENERATE_NO_LOOKUP")
        self.assertEqual(receipt["answer_cache_lookup_invocations"], 0)
        self.assertEqual(receipt["answer_cache_write_invocations"], 0)
        self.assertFalse(self.on.store.path.exists())

    def test_06_real_fixture_cas_is_not_product(self):
        r, final, proof, status = self.seed()
        self.assertEqual(status.status, "FIXTURE_WRITE_COMMITTED")
        self.assertFalse(status.product_write_admitted)
        self.assertFalse(status.product_hit_admitted)
        self.assertFalse(self.on.store.compare_and_swap_verified(
            r, {}, previous_revision=None))
        self.assertEqual(len(self.on.store.lookup_candidates(r)), 1)

    def test_07_auto_sees_stored_candidate_but_never_hit(self):
        self.assertEqual(self.seed()[-1].status, "FIXTURE_WRITE_COMMITTED")
        receipt = self.on.dispatch_cache(
            mode="AUTO", question="What does this fixture source say?",
            request_id="test-candidate-7")
        self.assertEqual(receipt["cache_status"], "PROVER_REQUIRED")
        self.assertEqual(receipt["candidate_count"], 1)
        self.assertFalse(receipt["answer_cache_hit_admitted"])
        self.assertFalse(receipt["answer_published"])

    def test_08_refresh_old_record_remains_without_verified_final(self):
        self.seed()
        before = self.on.store.lookup_candidates(self.request())
        self.assertEqual(len(before), 1)
        result = self.on.dispatch_cache(
            mode="REFRESH", question="What does this fixture source say?",
            request_id="test-ref-no-write-8")
        self.assertEqual(result["cache_status"], "REGENERATE_NO_LOOKUP")
        self.assertEqual(self.on.store.lookup_candidates(self.request()), before)

    def test_09_g04_revoke_physically_denies_cached_candidate(self):
        self.seed()
        witness = self.on.revocation.revoke(
            tenant="fixture-tenant", principal="fixture-principal",
            source_id="fixture-source", event_id="revoke-fixture-0009",
            reason="SOURCE_RIGHTS_REVOKED", actor="fixture-principal",
            authorized_fixture=True)
        self.assertEqual(witness.revocation_epoch, 1)
        result = self.on.dispatch_cache(
            mode="AUTO", question="What does this fixture source say?",
            request_id="test-after-revoke-9")
        self.assertEqual(result["cache_status"], "SOURCE_RIGHTS_DENIED")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["answer_cache_lookup_invocations"], 0)
        # Not cross-store deletion: independent Cache02 bytes need H01 fencing.
        self.assertTrue(self.on.store.path.exists())

    def test_10_rights_version_stale_or_principal_mismatch(self):
        request = self.request()
        bad = copy.deepcopy(request)
        bad["identity"]["principal_id"] = "another-principal"
        self.assertFalse(self.on._current_source_rights(bad))
        bad = copy.deepcopy(request)
        bad["policy"]["revocation_epoch"] = 222
        self.assertFalse(self.on._current_source_rights(bad))

    def test_11_cache03_revocation_also_blocks_retrieval(self):
        self.on.authority.mutate_fixture(
            tenant="fixture-tenant", principal="fixture-principal",
            source_id="fixture-source", event_id="policy-revoke-0011",
            kind="REVOKE", actor=self.on.actor, authorized_fixture=True)
        self.assertFalse(self.on._current_source_rights(self.request()))
        result = self.on.dispatch_cache(
            mode="AUTO", question="What does this fixture source say?",
            request_id="policy-revoke-11")
        self.assertEqual(result["cache_status"], "SOURCE_RIGHTS_DENIED")

    def test_12_forged_proof_and_false_safe_denied(self):
        r = self.request()
        final, proof, now = self.proof_fixture(r)
        proof["qualification_class"] = "EXTERNAL_QUALIFIED"
        result = self.on.fixture_gate().admit_fixture(
            r, final, proof, source_bytes={"fixture-source": joined._FIXTURE_SOURCE},
            now=now)
        self.assertEqual(result.status, "WRITE_DENIED")
        self.assertFalse(self.on.store.path.exists())

    def test_13_ui_http_cookie_origin_replay_and_privileged_field(self):
        server = self.server(join=self.on)
        code, item = self.call(server)
        self.assertEqual(code, 200)
        self.assertEqual(item["cache_status"], "LOOKUP_REQUIRED")
        self.assertEqual(item["schema"], joined.JOIN_SCHEMA)
        code, item = self.call(server)
        self.assertEqual((code, item["error"]), (409, "REPLAY_DENIED"))
        self.assertEqual(self.call(server, request_id="no-cookie-13", cookie=False)[0], 403)
        self.assertEqual(self.call(server, request_id="no-origin-13", origin=False)[0], 403)
        forged = dict(schema_version=ui.UI_SCHEMA, request_id="forged-identity-13",
                      cache_mode="AUTO", question="Q", tenant_id="forged")
        self.assertEqual(self.call(server, body=forged)[0], 400)

    def test_14_ui_http_off_bypass_refresh_actual(self):
        server = self.server()
        for mode, expected in (("AUTO", "DISABLED"), ("BYPASS", "BYPASSED"),
                               ("REFRESH", "DISABLED")):
            code, result = self.call(server, mode, request_id="native-" + mode)
            self.assertEqual(code, 200)
            self.assertEqual(result["cache_status"], expected)
            self.assertFalse(result["answer_published"])

    def test_15_http_cancel_before_planner_and_bad_mode(self):
        server = self.server(join=self.on)
        self.assertEqual(self.call(server, cancel=True)[0], 409)
        self.assertEqual(self.on.store_lookup_calls, 0)
        self.assertEqual(self.call(server, mode="INVALID")[0], 400)

    def test_16_route_abi_no_early_b3_provider_code(self):
        self.assertEqual(joined.ROUTE_CONTRACT["primary"],
                         "CUSTOM_CLOUDFLARE_WORKER_GATEWAY")
        self.assertEqual(joined.ROUTE_CONTRACT["primary_live"], "PRIMARY_LIVE_HOLD")
        self.assertFalse(joined.ROUTE_CONTRACT["activated"])
        self.assertEqual(joined.ROUTE_CONTRACT["model_calls"], 0)

    def test_17_real_joined_g02_native_client_durable_readback(self):
        contract = json.loads((EVIDENCE / "input/task_contract.json").read_bytes())
        sources = json.loads((EVIDENCE / "input/sources.json").read_bytes())
        contract_path, registry_path = self.root / "task.json", self.root / "sources.json"
        canonical = research.canonical
        contract_path.write_bytes(canonical(contract))
        registry_path.write_bytes(canonical(sources))
        results = self.root / "durable"
        results.mkdir()
        bridge = research.ResearchBridge(
            contract_path=contract_path, registry_path=registry_path,
            db_path=self.root / "research.sqlite",
            outcome_dir=results, independent_checker=CHECKER,
            tenant_id="owner-m27-nonprod", principal_id="owner-delegated-b0-02")
        server = self.server(join=self.on, bridge=bridge)
        from knowledge_engine.m27_task_contracts_v1 import sha256 as contract_sha
        q = dict(schema=research.REQUEST_SCHEMA, request_id="joined-h02-research",
                 run_id="joined-b3-research", task_id=contract["task_id"],
                 task_version=contract["task_version"],
                 tenant_id="owner-m27-nonprod", principal_id="owner-delegated-b0-02",
                 contract_sha256=contract_sha(contract),
                 registry_sha256=hashlib.sha256(canonical(sources)).hexdigest(),
                 outcome_id=contract["output_specs"][0]["outcome_id"])
        # First-party G02 execution on the joined HTTP server with session pin.
        opener = urllib.request.build_opener()
        cookie = opener.open(server.origin + "/__cache04/demo/").headers["Set-Cookie"].split(";")[0]
        request = urllib.request.Request(
            server.origin + joined.RESEARCH_PATH, canonical(q),
            headers={"Content-Type": "application/json", "Origin": server.origin,
                     "X-Cache-Demo-Request": "1", "Cookie": cookie}, method="POST")
        with opener.open(request) as resp:
            item = json.loads(resp.read())
            self.assertEqual(resp.status, 200)
        self.assertEqual(item["citations"], 4)
        self.assertEqual(item["cache_join"], "RESEARCH_NONCACHEABLE")
        self.assertEqual(item["state"], "DURABLE_SOURCE_BACKED_RESEARCH_READBACK_PASS")
        self.assertFalse(item["formal_product_qualified"])
        self.assertEqual(hashlib.sha256(Path(item["markdown_path"]).read_bytes()).hexdigest(),
                         item["markdown_sha256"])
        with sqlite3.connect(self.root / "research.sqlite") as db:
            self.assertEqual(db.execute(
                "select count(*) from g02_events where run_id=?", ("joined-b3-research",)
            ).fetchone()[0], 4)
        # Independent fresh interpreter validates OS-persisted Research against actual sources.
        check = subprocess.run(
            [sys.executable, str(CHECKER), "--help"],
            capture_output=True, text=True, timeout=10)
        self.assertNotEqual(check.returncode, -9)
        self.assertEqual(self.on.store_lookup_calls, 0)

    def test_18_http_research_is_not_answer_cache_and_denies_wrong_id(self):
        result = self.on.dispatch_cache(mode="BYPASS", question="Research must not be cached",
                                        request_id="non-cache-research")
        self.assertEqual(result["answer_cache_lookup_invocations"], 0)
        self.assertEqual(result["answer_cache_write_invocations"], 0)
        server = self.server()
        self.assertEqual(self.call(server)[0], 200)
        self.assertEqual(self.on.store_write_calls, 0)

    def test_19_store_backup_restore_revoke_fail_shut(self):
        self.seed()
        backup = self.root / "fixture-store-before-revoke.sqlite3"
        import shutil
        shutil.copy2(self.on.store.path, backup)
        self.on.revocation.revoke(
            tenant="fixture-tenant", principal="fixture-principal",
            source_id="fixture-source", event_id="restore-revoke-0019",
            reason="CONSENT_WITHDRAWN", actor="fixture-principal",
            authorized_fixture=True)
        shutil.copy2(backup, self.on.store.path)
        reply = self.on.dispatch_cache(
            mode="AUTO", question="What does this fixture source say?",
            request_id="test-stale-restore")
        self.assertEqual(reply["cache_status"], "SOURCE_RIGHTS_DENIED")
        self.assertEqual(reply["candidate_count"], 0)

    def test_20_no_same_generator_verifier_or_product_claim(self):
        r = self.request()
        final, proof, now = self.proof_fixture(r)
        proof["verifier_id"] = proof["generator_id"]
        proof["signature"] = hmac.new(
            joined._FIXTURE_PROOF_KEY,
            gate.canonical({k: v for k, v in proof.items() if k != "signature"}),
            hashlib.sha256).hexdigest()
        result = self.on.fixture_gate().admit_fixture(
            r, final, proof, source_bytes={"fixture-source": joined._FIXTURE_SOURCE}, now=now)
        self.assertEqual(result.status, "WRITE_DENIED")
        self.assertFalse(result.product_write_admitted)


if __name__ == "__main__":
    unittest.main()
