"""S-H02/F03 uniquely owned real H02 first-party source route fan-in, Cache OFF.
Uses the actual A05 reader, OS byte verifier, local revocation fence and TCP.
No real Product IdP, model call, cache store, or semantic issuer.
"""
from __future__ import annotations
import concurrent.futures
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
if "knowledge_engine" not in sys.modules:
    p = types.ModuleType("knowledge_engine")
    p.__path__ = [str(ROOT / "src/knowledge_engine")]
    sys.modules["knowledge_engine"] = p
import m27_h02_native_nonprod_consumer as h02
from knowledge_engine import m27_f03_product_cache_seam_protocol as seam
TARGET = ROOT / "src/knowledge_engine/m27_h02_f03_cache_seam_join_nonprod.py"
ROUTE = "/nonprod/h02-f03/source-candidate"
SCHEMA = seam.CLIENT_SCHEMA


def packet(mode="AUTO", ident="h02-f03-req-000001", **overrides):
    return {"schema_version": SCHEMA, "request_id": ident,
            "cache_mode": mode, "question": "PolicyEngine", **overrides}


class H02F03RealJoin(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="h02f03-fanin-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.fence = self.dir / "fence.json"
        self.journal = self.dir / "journal.jsonl"
        self.write_fence(1)

    def write_fence(self, epoch):
        self.fence.write_text(json.dumps({"release_id": h02.f03.A05_RELEASE_ID,
                                         "minimum_epoch": epoch}))
        self.fence.chmod(0o600)

    def module(self):
        return importlib.import_module("knowledge_engine.m27_h02_f03_cache_seam_join_nonprod")

    def local(self):
        return self.module().JoinedConsumer(repo=ROOT, fence=self.fence, journal=self.journal)

    @staticmethod
    def cleanup_proc(proc):
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=4)

    def run_server(self, baseline=False):
        ready = self.dir / ("old-ready.json" if baseline else "joined-ready.json")
        path = ROOT / "src/knowledge_engine/m27_h02_native_nonprod_consumer.py" if baseline else (
            TARGET if TARGET.exists() else ROOT / "src/knowledge_engine/m27_h02_native_nonprod_consumer.py")
        cmd = [sys.executable, str(path), "--repo", str(ROOT), "--fence", str(self.fence),
               "--journal", str(self.journal), "--ready-file", str(ready)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup_proc, proc)
        for _ in range(140):
            if proc.poll() is not None:
                raise AssertionError("OS_SERVER_EXIT=" + str(proc.returncode) + ":" +
                                     proc.communicate()[1].decode(errors="replace")[:1200])
            if ready.exists():
                break
            time.sleep(0.05)
        self.assertTrue(ready.exists(), "SERVER_READY_TIMEOUT")
        data = json.loads(ready.read_text())
        return "http://127.0.0.1:" + str(data["port"]), data.get("transport_token")

    def post(self, host, path, request, token=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if token:
            h["X-H02-F03-Token"] = token
        data = json.dumps(request).encode()
        r = Request(host + path, data=data, headers=h, method="POST")
        try:
            with urlopen(r, timeout=25) as response:
                return response.status, json.loads(response.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_01_before_after_genuine_h02_tcp_route(self):
        # On pinned F03-only commit, the only running real H02 router rejects
        # the joined protocol path; this fails RED BEFORE join module exists.
        host, token = self.run_server()
        status, response = self.post(host, ROUTE, packet(), token)
        self.assertEqual(status, 200, response)
        self.assertEqual(response["status"], "LOCAL_FIRSTPARTY_SOURCE_CANDIDATE")
        self.assertEqual(response["source_manifest_sha256"], h02.f03.A05_SOURCE_PIN)
        self.assertEqual(response["cache_plan"]["product_cache_enabled"], False)
        self.assertEqual(response["cache_plan"]["cache_status"], "DISABLED")
        self.assertEqual(response["cache_plan"]["proposed_mode_decision"], "LOOKUP_REQUIRED")
        self.assertFalse(response["model_generated"])
        self.assertFalse(response["complete_answer"])
        self.assertEqual(response["provider"], "NOT_RUN")
        self.assertEqual(response["cache"], "OFF")
        self.assertEqual(len(response["claims"]), 2)

    def test_02_os_tcp_modes_same_source_and_zero_cache_io(self):
        host, token = self.run_server()
        outputs = []
        for idx, mode in enumerate(("AUTO", "BYPASS", "REFRESH"), 11):
            status, response = self.post(host, ROUTE, packet(mode, f"h02f03-mode-{idx:04d}"), token)
            self.assertEqual(status, 200, response)
            plan = response["cache_plan"]
            self.assertEqual(plan["cache_mode"], mode)
            self.assertEqual(plan["cache_status"], "BYPASSED" if mode == "BYPASS" else "DISABLED")
            self.assertEqual(plan["proposed_mode_decision"], {
                "AUTO": "LOOKUP_REQUIRED", "BYPASS": "BYPASSED",
                "REFRESH": "REGENERATE_NO_LOOKUP"}[mode])
            self.assertFalse(plan["cache_io_performed"])
            self.assertFalse(plan["answer_cache_hit_admitted"])
            self.assertFalse(plan["answer_cache_write_admitted"])
            self.assertEqual(plan["answer_cache_lookup_invocations"], 0)
            self.assertEqual(plan["answer_cache_write_invocations"], 0)
            self.assertEqual(plan["real_issuer_admission"], "HOLD")
            self.assertEqual(response["cache"], "OFF")
            outputs.append(response)
        self.assertEqual([[c["text"] for c in x["claims"]] for x in outputs],
                         [[c["text"] for c in outputs[0]["claims"]]] * 3)
        self.assertEqual({x["source_manifest_sha256"] for x in outputs},
                         {h02.f03.A05_SOURCE_PIN})

    def test_03_client_authority_injection_invalid_and_transport(self):
        host, token = self.run_server()
        for bad in (
            packet(ident="h02f03-inject1", tenant_id="owner-internal"),
            packet(ident="h02f03-inject2", principal_id="os-uid:0"),
            packet(ident="h02f03-inject3", source_manifest_sha256="0" * 64),
            packet(ident="h02f03-inject4", verifier="signed"),
            packet(ident="h02f03-inject5", cache_enabled=True),
            packet("ON", "h02f03-inject6"),
            packet(ident="h02f03-inject7", question="PolicyEngine not"),
            packet(ident="h02f03-inject8", question="PolicyEngine 42"),
        ):
            code, resp = self.post(host, ROUTE, bad, token)
            self.assertGreaterEqual(code, 400, resp)
            self.assertNotIn("claims", resp)
        code, resp = self.post(host, ROUTE, packet(ident="h02f03-no-token"))
        self.assertEqual(code, 403, resp)
        code, resp = self.post(host, ROUTE, packet(ident="h02f03-bad-token"), "incorrect")
        self.assertEqual(code, 403, resp)
        code, resp = self.post(host, ROUTE, packet(ident="h02f03-forged-host"), token,
                               {"Host": "example.invalid"})
        self.assertEqual(code, 403, resp)

    def test_04_tcp_ack_terminal_cancel_and_parity(self):
        host, token = self.run_server()
        status, r = self.post(host, ROUTE, packet("BYPASS", "h02f03-ack-001"), token)
        self.assertEqual(status, 200, r)
        wrong, denial = self.post(host, h02.ACK, {
            "session_id": r["session_id"], "claim_id": r["claims"][0]["claim_id"],
            "challenge": "invalid", "text_sha256": r["claims"][0]["text_sha256"]})
        self.assertEqual(wrong, 403, denial)
        for claim in r["claims"]:
            code, ack = self.post(host, h02.ACK, {
                "session_id": r["session_id"], "claim_id": claim["claim_id"],
                "challenge": claim["challenge"], "text_sha256": claim["text_sha256"]})
            self.assertEqual(code, 200, ack)
        code, end = self.post(host, h02.TERMINAL, {"session_id": r["session_id"]})
        self.assertEqual(code, 200, end)
        self.assertEqual(end["status"], "LOCAL_SOURCE_TWO_CLAUSES_ACKED_NOT_PRODUCT")
        self.assertFalse(end["product_pass"])
        code, r2 = self.post(host, ROUTE, packet("AUTO", "h02f03-cancel-01"), token)
        self.assertEqual(code, 200, r2)
        code, cancelled = self.post(host, h02.CANCEL, {"session_id": r2["session_id"]})
        self.assertEqual(code, 200, cancelled)
        code, _ = self.post(host, h02.TERMINAL, {"session_id": r2["session_id"]})
        self.assertEqual(code, 403)

    def test_05_tcp_replay_and_concurrent_shared_id(self):
        host, token = self.run_server()
        req = packet(ident="h02f03-concurrent-01")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.post, host, ROUTE, req, token) for _ in range(2)]
            values = [f.result(timeout=25) for f in futures]
        self.assertEqual(sorted(x[0] for x in values), [200, 409], values)
        code, resp = self.post(host, ROUTE, req, token)
        self.assertEqual(code, 409, resp)
        self.assertEqual(resp["error"], "REPLAY_DENIED")

    def test_06_local_os_rights_stale_after_delivery(self):
        joined = self.local()
        r = joined.start_with_mode(packet(ident="h02f03-local-epoch1"))
        self.assertEqual(r["cache_plan"]["cache_status"], "DISABLED")
        self.write_fence(2)
        with self.assertRaises(h02.Denied):
            joined.delivery_recheck(r["session_id"])
        with self.assertRaises(h02.Denied):
            joined.ack(r["session_id"], r["claims"][0]["claim_id"],
                       r["claims"][0]["challenge"], r["claims"][0]["text_sha256"])

    def test_07_revocation_between_plan_and_client_delivery(self):
        joined = self.local()
        joined.before_delivery = lambda: self.write_fence(2)
        with self.assertRaises(h02.Denied):
            joined.start_with_mode(packet(ident="h02f03-race-001"))
        self.assertFalse(any(entry["state"] == "AWAITING_ACK"
                             for entry in joined.entries.values()))

    def test_08_os_verifier_failure_and_recovery(self):
        joined = self.local()
        original = joined.verifier
        joined.verifier = self.dir / "nonexistent_verify.py"
        with self.assertRaisesRegex(seam.NativeCacheProtocolError,
                                    "UPSTREAM_NATIVE_AUTHORITY_UNAVAILABLE"):
            joined.start_with_mode(packet(ident="h02f03-verifier-bad"))
        joined.verifier = original
        r = joined.start_with_mode(packet(ident="h02f03-verifier-good"))
        self.assertFalse(r["cache_plan"]["product_cache_enabled"])
        self.assertEqual(r["provider"], "NOT_RUN")

    def test_09_replay_fail_close_across_process_restart(self):
        first = self.local()
        r = first.start_with_mode(packet(ident="h02f03-no-replay-restart"))
        second = self.local()
        with self.assertRaises(h02.Denied):
            second.delivery_recheck(r["session_id"])
        self.assertEqual(second.recovery, "INCOMPLETE_NO_REPLAY")
        # Seam reqid set is intentionally only process-local, not distributed.
        self.assertEqual(second.seam.last_envelope, None)

    def test_10_lease_expiry_enforced_before_start(self):
        joined = self.local()
        joined.seam.clock = lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc) + __import__("datetime").timedelta(days=1)
        with self.assertRaises(seam.NativeCacheProtocolError):
            joined.start_with_mode(packet(ident="h02f03-expired-001"))
        self.assertFalse(any(e["state"] == "AWAITING_ACK" for e in joined.entries.values()))

    def test_11_cross_principal_and_unqualified_issuer(self):
        joined = self.local()
        with self.assertRaises(h02.Denied):
            joined.start("PolicyEngine", tenant="other-tenant")
        with self.assertRaises(h02.Denied):
            joined.start("PolicyEngine", principal="oidc-fake")
        with self.assertRaises(h02.Denied):
            joined.start("PolicyEngine", issuer="unsigned-semantic-verifier")
        with self.assertRaises(ValueError):
            seam.NativeProductCacheSeam(authority=joined.authority, feature_enabled=True)
        self.assertEqual(joined.seam._store_factory, None)

    def test_12_first_party_source_manifest_tamper_in_isolated_copy(self):
        local = self.dir / "copied_a05"
        shutil.copytree(ROOT / h02.f03.A05_SOURCE, local)
        corpus = local / "corpus.json"
        corpus.write_bytes(corpus.read_bytes() + b"\\n")
        # Real H02 file and pinned Git source remain unchanged.
        c = self.module().JoinedConsumer(repo=ROOT, fence=self.fence,
                  journal=self.dir / "tamper_journal.jsonl",
                  source_root=local, isolated_test_copy=True)
        with self.assertRaises(seam.NativeCacheProtocolError):
            c.start_with_mode(packet(ident="h02f03-tamper-source"))
        self.assertEqual(c.seam.last_envelope, None)

    def test_13_first_party_revoked_document_in_isolated_copy(self):
        local = self.dir / "revoked_a05"
        shutil.copytree(ROOT / h02.f03.A05_SOURCE, local)
        corpus = json.loads((local / "corpus.json").read_text())
        revoked = local / "revocations.json"
        data = json.loads(revoked.read_text())
        data["revoked_document_sha256"] = [x["sha256"] for x in corpus["docs"]]
        revoked.write_text(json.dumps(data))
        c = self.module().JoinedConsumer(repo=ROOT, fence=self.fence,
                  journal=self.dir / "revoked_journal.jsonl",
                  source_root=local, isolated_test_copy=True)
        with self.assertRaises(seam.NativeCacheProtocolError):
            c.start_with_mode(packet(ident="h02f03-revoked-source"))
        self.assertFalse(any(x["state"] == "AWAITING_ACK"
                             for x in c.entries.values()))

    def test_14_cancel_blocks_join_delivery_and_first_party_ack(self):
        c = self.local()
        r = c.start_with_mode(packet("REFRESH", "h02f03-cancel-test"))
        self.assertEqual(c.cancel(r["session_id"])["status"], "CANCELLED_NO_REPLAY")
        with self.assertRaises(h02.Denied):
            c.delivery_recheck(r["session_id"])
        with self.assertRaises(h02.Denied):
            claim = r["claims"][0]
            c.ack(r["session_id"], claim["claim_id"],
                  claim["challenge"], claim["text_sha256"])

    def test_15_no_global_fake_product_auth_or_cache_store(self):
        c = self.local()
        receipt = c.start_with_mode(packet(ident="h02f03-local-native-contract"))
        self.assertEqual(c.authority.initial_source["source_manifest_sha256"],
                         h02.f03.A05_SOURCE_PIN)
        self.assertEqual(c.seam.last_envelope["identity"]["principal_id"],
                         c.principal)
        self.assertEqual(c.seam.last_envelope["source"]["corpus_revision"],
                         h02.f03.A05_REVISION)
        self.assertEqual(c.seam.last_envelope["policy"]["revocation_epoch"], 1)
        self.assertEqual(c.seam.last_envelope["source"]["rights_sha256"],
                         c.authority.initial_source["source"]["rights_sha256"])
        self.assertEqual(c.seam.last_envelope["source"]["acl_sha256"],
                         c.authority.initial_source["source"]["acl_sha256"])
        self.assertEqual(c.seam.last_envelope["identity"]["tenant_id"], "owner-internal")
        self.assertFalse(receipt["product_authenticated"])
        self.assertFalse(receipt["semantic_verifier_qualified"])
        self.assertIsNone(receipt["cache_plan"]["answer"])
        self.assertEqual(receipt["cache_plan"]["citations"], [])
        self.assertFalse(c.seam._store_factory)

    def test_16_true_tcp_external_rights_revoke_after_candidate(self):
        host, token = self.run_server()
        code, r = self.post(host, ROUTE, packet("AUTO", "h02f03-tcp-revoke-001"), token)
        self.assertEqual(code, 200, r)
        self.write_fence(2)  # independent OS-owned local fence, not original source
        claim = r["claims"][0]
        code, denied = self.post(host, h02.ACK, {
            "session_id": r["session_id"], "claim_id": claim["claim_id"],
            "challenge": claim["challenge"], "text_sha256": claim["text_sha256"]})
        self.assertEqual(code, 403, denied)
        code, denied = self.post(host, h02.TERMINAL, {"session_id": r["session_id"]})
        self.assertEqual(code, 403, denied)
        self.assertFalse(denied.get("product_pass", False))

    def test_17_true_tcp_malformed_json_and_private_ready_token(self):
        host, token = self.run_server()
        ready = self.dir / "joined-ready.json"
        self.assertEqual(ready.stat().st_mode & 0o077, 0)
        self.assertTrue(len(token) >= 32)
        data = b'{"schema_version":'
        req = Request(host + ROUTE, data=data,
                      headers={"Content-Type": "application/json",
                               "X-H02-F03-Token": token}, method="POST")
        with self.assertRaises(HTTPError) as e:
            urlopen(req, timeout=20)
        self.assertEqual(e.exception.code, 400)
        self.assertNotIn("claims", json.loads(e.exception.read()))

    def test_18_baseline_h02_route_unchanged(self):
        host, _ = self.run_server(baseline=True)
        code, response = self.post(host, h02.ROUTE, {"question": "PolicyEngine"})
        self.assertEqual(code, 200, response)
        self.assertEqual(response["status"], "LOCAL_FIRSTPARTY_SOURCE_CANDIDATE")
        self.assertEqual(response["cache"], "OFF")
        self.assertEqual(response["provider"], "NOT_RUN")

if __name__ == "__main__":
    unittest.main()
