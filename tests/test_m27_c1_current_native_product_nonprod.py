"""C1 current real OS native candidate boot and fail-closed contract regression."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import datetime as dt
from unittest import mock
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))

import m27_c1_current_native_product_nonprod as c1


class C1NativeApp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="m27-c1-real-client-")
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        self.token = os.urandom(32).hex()
        self.token_file = self.t / "os-client-capability"
        self.token_file.write_bytes(self.token.encode())
        self.token_file.chmod(0o600)
        self.fence = self.t / "fence.json"
        self.fence.write_text(json.dumps({
            "release_id": c1.h02.f03.A05_RELEASE_ID,
            "minimum_epoch": 1}))
        self.fence.chmod(0o600)
        self.head = c1.git_field(ROOT, "HEAD")
        self.tree = c1.git_field(ROOT, "HEAD^{tree}")
        self.journal = self.t / "journal.jsonl"

    def version(self):
        return c1.source_vector(ROOT, expected_head=self.head,
                                expected_tree=self.tree)

    def test_01_precise_source_abi_task_rights_vector(self):
        vector = self.version()
        self.assertEqual(vector["head"], self.head)
        self.assertEqual(vector["tree"], self.tree)
        self.assertEqual(vector["h02_abi"], c1.h02.ABI)
        self.assertEqual(vector["f02_abi"], c1.f02.ABI)
        self.assertEqual(vector["g01_abi"], c1.g01.ABI)
        self.assertIsNone(vector["task_contract_sha256"])
        self.assertEqual(vector["task_contract_sha256_kind"],
                         "PER_ADMITTED_SESSION_ONLY")
        self.assertEqual(vector["task_contract_template_sha256"],
                         c1.current_task_template("os-uid:" + str(os.geteuid())))
        self.assertEqual(vector["cache"], "OFF")
        self.assertFalse(vector["product_pass"])
        self.assertIsNone(vector["current_signed_image"])
        self.assertEqual(vector["generation"], "NOT_RUN")

    def test_02_wrong_commit_tree_denied(self):
        with self.assertRaisesRegex(c1.AdmissionDenied, "SOURCE_VERSION_MISMATCH"):
            c1.source_vector(ROOT, expected_head="0" * 40,
                             expected_tree=self.tree)
        with self.assertRaisesRegex(c1.AdmissionDenied, "SOURCE_VERSION_MISMATCH"):
            c1.source_vector(ROOT, expected_head=self.head,
                             expected_tree="0" * 40)

    def test_03_client_token_file_symlink_and_mode_denied(self):
        self.token_file.chmod(0o644)
        with self.assertRaisesRegex(c1.AdmissionDenied, "CLIENT_TOKEN_FILE"):
            c1.read_client_capability(self.token_file)
        self.token_file.chmod(0o600)
        linked = self.t / "link"
        linked.symlink_to(self.token_file)
        with self.assertRaisesRegex(c1.AdmissionDenied, "CLIENT_TOKEN_FILE"):
            c1.read_client_capability(linked)

    def server(self):
        ready = self.t / "ready.json"
        cmd = [sys.executable,
               str(ROOT / "src/knowledge_engine/m27_c1_current_native_product_nonprod.py"),
               "--repo", str(ROOT), "--fence", str(self.fence),
               "--journal", str(self.journal), "--token-file", str(self.token_file),
               "--expected-head", self.head, "--expected-tree", self.tree,
               "--ready-file", str(ready), "--port", "0"]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=4)
            if proc.stderr:
                proc.stderr.close()
        self.addCleanup(cleanup)
        for _ in range(160):
            if ready.exists():
                break
            if proc.poll() is not None:
                raise AssertionError("SERVER_BOOT_FAILED;exit=" + str(proc.returncode))
            time.sleep(0.05)
        self.assertTrue(ready.exists(), "SERVER_BOOT_TIMEOUT")
        info = json.loads(ready.read_text())
        self.assertFalse(info["product_admitted"])
        self.assertEqual(info["source_head"], self.head)
        return "http://127.0.0.1:" + str(info["port"])

    def request(self, url, method="GET", data=None, token=None):
        headers = {"Host": "127.0.0.1", "X-C1-Local-Capability":
                   self.token if token is None else token}
        payload = (None if data is None else json.dumps(data).encode())
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, method=method, headers=headers, data=payload)
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_04_booted_native_app_independent_http_client_and_two_acks(self):
        base = self.server()
        code, state = self.request(base + c1.STATUS_PATH)
        self.assertEqual(code, 200)
        self.assertEqual(state["status"], "BOOTED_SOURCE_CLIENT_CANDIDATE_NOT_PRODUCT")
        self.assertEqual(state["version"]["head"], self.head)
        self.assertFalse(state["provider_called"])
        code, started = self.request(base + c1.SOURCE_PATH, "POST",
                                     {"question": "PolicyEngine",
                                      "tenant": "owner-internal"})
        self.assertEqual(code, 200)
        self.assertEqual(started["candidate_abi"], c1.ABI)
        self.assertEqual(started["task_sha256"],
                         started["pinned_task_contract_sha256"])
        self.assertEqual(started["task_contract_template_sha256"],
                         state["version"]["task_contract_template_sha256"])
        self.assertEqual(len(started["task_sha256"]), 64)
        self.assertTrue(started["independent_os_source_byte_verified"])
        self.assertFalse(started["generated_answer"])
        self.assertFalse(started["product_pass"])
        for clause in started["claims"]:
            code, receipt = self.request(base + c1.ACK_PATH, "POST", {
                "session_id": started["session_id"],
                "claim_id": clause["claim_id"],
                "challenge": clause["challenge"],
                "text_sha256": clause["text_sha256"]})
            self.assertEqual(code, 200)
            self.assertEqual(receipt["status"], "LOCAL_CLIENT_ACK_RECEIVED")
        code, done = self.request(base + c1.TERMINAL_PATH, "POST",
                                  {"session_id": started["session_id"]})
        self.assertEqual(code, 200)
        self.assertFalse(done["product_pass"])
        events = [json.loads(x) for x in self.journal.read_text().splitlines()]
        self.assertEqual([x["event"] for x in events],
                         ["source_candidate_sent", "client_ack",
                          "client_ack", "terminal"])

    def test_05_bad_client_or_scope_denied_and_no_model_probe(self):
        base = self.server()
        code, _ = self.request(base + c1.STATUS_PATH, token="wrong")
        self.assertEqual(code, 403)
        code, bad = self.request(base + c1.SOURCE_PATH, "POST",
                                 {"question": "PolicyEngine",
                                  "tenant": "another"}, token=self.token)
        self.assertEqual(code, 403)
        self.assertFalse(bad["product_pass"])
        code, denied = self.request(base + c1.MODEL_PATH, "POST",
                                    {"model": "cloudflare-custom"})
        self.assertEqual(code, 403)
        self.assertEqual(denied["status"], "LIVE_TASKCONTRACT_SHAPE_DENIED")
        self.assertFalse(denied["provider_called"])
        self.assertFalse(denied["fallback_called"])
        self.assertFalse(self.journal.exists())

    def test_06_second_ack_missing_and_no_fixture_promotion(self):
        base = self.server()
        code, entry = self.request(base + c1.SOURCE_PATH, "POST",
                                   {"question": "PolicyEngine",
                                    "tenant": "owner-internal"})
        self.assertEqual(code, 200)
        code, done = self.request(base + c1.TERMINAL_PATH, "POST",
                                  {"session_id": entry["session_id"]})
        self.assertEqual(code, 403)
        self.assertFalse(done["product_pass"])
        self.assertNotIn("answer_text", json.dumps(done))
        self.assertNotIn("answer_text", json.dumps(entry))

    def test_07_incomplete_journal_restart_fail_closed(self):
        self.journal.write_text(json.dumps({"event": "source_candidate_sent",
                                             "sid": "aborted"}) + "\n")
        with self.assertRaisesRegex(c1.AdmissionDenied, "INCOMPLETE_PREVIOUS_TASK"):
            c1.Candidate(repo=ROOT, fence=self.fence, journal=self.journal,
                         token_file=self.token_file,
                         expected_head=self.head, expected_tree=self.tree)

    def test_08_old_clock_boundary_is_actual_causal_red_and_template_green(self):
        original = c1.h02.g01.task_contract
        a = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
        b = a + dt.timedelta(seconds=2)
        # H02 still validates each admitted full live TaskContract. Only the
        # comparison across distinct instants changes to stable policy template.
        with mock.patch.object(c1.h02.g01, "task_contract", side_effect=lambda: original(when=a)):
            old = c1.h02.local_task("PolicyEngine", "os-uid:" + str(os.geteuid()))
        with mock.patch.object(c1.h02.g01, "task_contract", side_effect=lambda: original(when=b)):
            later = c1.h02.local_task("PolicyEngine", "os-uid:" + str(os.geteuid()))
        self.assertNotEqual(c1.contract.sha256(old), c1.contract.sha256(later),
                            "PREVIOUS_BOOT_SHA_EQUIVALENCE_MUST_FAIL_ACROSS_CLOCK")
        self.assertEqual(c1.contract_template_sha256(old),
                         c1.contract_template_sha256(later),
                         "SOURCE_POLICY_TEMPLATE_MUST_BE_TIMESTAMP_INDEPENDENT")
        self.assertEqual(old["tenant_id"], later["tenant_id"])
        self.assertEqual(old["authority"], later["authority"])
        self.assertEqual(old["context_scopes"], later["context_scopes"])

    def test_09_real_os_http_delayed_clock_boundary_no_403(self):
        base = self.server()
        code, state = self.request(base + c1.STATUS_PATH)
        self.assertEqual(code, 200)
        time.sleep(1.20)
        code, started = self.request(base + c1.SOURCE_PATH, "POST",
                                     {"question": "PolicyEngine",
                                      "tenant": "owner-internal"})
        self.assertEqual(code, 200, "TASK_SHA_CANNOT_BE_FIXED_AT_APP_BOOT")
        self.assertEqual(started["task_contract_template_sha256"],
                         state["version"]["task_contract_template_sha256"])
        self.assertEqual(len(started["task_sha256"]), 64)
        self.assertFalse(started["product_pass"])

    def test_10_per_run_sha_and_rights_still_fail_closed(self):
        candidate = c1.Candidate(repo=ROOT, fence=self.fence, journal=self.journal,
                                 token_file=self.token_file, expected_head=self.head,
                                 expected_tree=self.tree)
        result = candidate.begin({"question": "PolicyEngine",
                                  "tenant": "owner-internal"})
        sid = result["session_id"]
        self.assertEqual(candidate.contract_instances[sid]["task_sha256"],
                         result["task_sha256"])
        candidate.contract_instances[sid]["task_sha256"] = "0" * 64
        with self.assertRaisesRegex(c1.AdmissionDenied, "ADMITTED_TASK_OR_RIGHTS_PIN_INVALID"):
            candidate.ack({"session_id": sid,
                           "claim_id": result["claims"][0]["claim_id"],
                           "challenge": result["claims"][0]["challenge"],
                           "text_sha256": result["claims"][0]["text_sha256"]})
        with self.assertRaisesRegex(c1.AdmissionDenied, "ADMITTED_TASK_OR_RIGHTS_PIN_INVALID"):
            candidate.terminal({"session_id": sid})


if __name__ == "__main__":
    unittest.main()
