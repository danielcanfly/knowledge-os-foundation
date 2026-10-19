"""One-Session true A05/F03 TaskContract+Native Unix OS run / fail closed.

NOT an external LLM or independent semantic issuer; no synthetic provider
tokens, signer keys, cost receipts or Product PASS are generated here.
"""
from __future__ import annotations
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/knowledge_engine"))
import m27_c1_current_native_product_nonprod as c1
import m27_c1_genuine_native_generation_seam as live
import m27_f03_source_rights_admission as f03


class UnixC1Client(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__("c1-unix.local",timeout=14)
        self.path=path

    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.connect(str(self.path))


class SingleSessionActualNonprodOS(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="m27-f03-c1-one-os-task-")
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.dir.chmod(0o700)
        self.head=c1.git_field(ROOT,"HEAD")
        self.tree=c1.git_field(ROOT,"HEAD^{tree}")
        self.fence=self.dir/"source-fence"
        self.fence.write_text(json.dumps({
          "release_id":f03.A05_RELEASE_ID,"minimum_epoch":1}))
        self.fence.chmod(0o600)
        self.token_file=self.dir/"private-local-client"
        self.token=os.urandom(32).hex()
        self.token_file.write_text(self.token)
        self.token_file.chmod(0o600)
        self.sock=self.dir/"native-client.sock"
        self.journal=self.dir/"native-journal.jsonl"

    def boot(self):
        ready=self.dir/"ready.json"
        args=[sys.executable,str(ROOT/"src/knowledge_engine/m27_c1_current_native_product_nonprod.py"),
              "--repo",str(ROOT),"--fence",str(self.fence),
              "--journal",str(self.journal),"--token-file",str(self.token_file),
              "--expected-head",self.head,"--expected-tree",self.tree,
              "--ready-file",str(ready),"--unix-socket",str(self.sock)]
        proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        def shutdown():
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait(timeout=4)
            proc.stderr.close()
        self.addCleanup(shutdown)
        for _ in range(180):
            if ready.exists():break
            if proc.poll() is not None:
                raise AssertionError("OS_NATIVE_BOOT_DENIED_EXIT_"+str(proc.returncode))
            time.sleep(0.05)
        self.assertTrue(ready.exists())
        self.assertEqual(json.loads(ready.read_text())["source_head"],self.head)

    def call(self,path,body=None,token=None):
        connection=UnixC1Client(self.sock)
        headers={"Host":"c1-unix.local",
                 "X-C1-Local-Capability":self.token if token is None else token}
        payload=None if body is None else json.dumps(body).encode()
        if payload is not None:
            headers["Content-Type"]="application/json"
        try:
            connection.request("GET" if payload is None else "POST",path,
                               headers=headers,body=payload)
            response=connection.getresponse()
            return response.status,json.loads(response.read())
        finally:connection.close()

    def allowed(self):
        return {"question":c1.g01.QUESTION,"tenant":"owner-internal",
                "cache_mode":"OFF","max_tokens":64,
                "deadline_seconds":10,"fallback_consent":False}

    def test_01_true_single_task_f03_two_sources_native_client_no_fake_model(self):
        self.boot()
        status,current=self.call(c1.STATUS_PATH)
        self.assertEqual(status,200)
        self.assertEqual(current["version"]["head"],self.head)
        self.assertFalse(current["native_live"]["provider_called"])
        code,prepared=self.call(c1.LIVE_PREPARE,self.allowed())
        self.assertEqual(code,200)
        self.assertEqual(prepared["prepared_source_count"],2)
        self.assertEqual(len(prepared["source_obligation_ids"]),2)
        self.assertEqual(set(prepared["source_obligation_ids"]),
                         set(live.OBLIGATIONS))
        self.assertEqual(len(prepared["source_binding_sha256"]),64)
        self.assertEqual(len(prepared["task_contract_sha256"]),64)
        self.assertEqual(prepared["source_manifest_sha256"],f03.A05_SOURCE_PIN)
        self.assertFalse(prepared["provider_called"])
        self.assertFalse(prepared["product_pass"])
        self.assertIsNone(prepared["answer_text"])
        # Full current F03 physical Source Controller local candidate: exact
        # independent original A05 11-doc, 21-span and citation hash proof.
        direct=f03.A05OwnerCorpusAdmission(ROOT,fence=self.fence)
        corpus,release,release_sha=direct._pinned_release()
        self.assertEqual(len(corpus["docs"]),11)
        self.assertEqual(len(corpus["chunks"]),21)
        self.assertFalse(release["source_release_ci_signed"])
        self.assertEqual(prepared["rights_epoch"],1)
        for _,q,obligation,source_file in c1.g01.OBLIGATIONS:
            r=direct.source_retrieval(q,tenant="owner-internal",
                  principal="os-uid:"+str(os.geteuid()),
                  obligations=[obligation],ttl_seconds=120)
            self.assertEqual(r["decision"],"A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
            self.assertTrue(any(c["document"]==source_file for c in r["sources"]))
            self.assertEqual(r["source_manifest_sha256"],f03.A05_SOURCE_PIN)
        q=urlencode({"request_id":prepared["request_id"],
                     "claim_id":live.OBLIGATIONS[0]})
        code,text=self.call(c1.LIVE_VERIFIED_NEXT+"?"+q)
        self.assertEqual(code,403)
        self.assertEqual(text["status"],"VERIFIED_CLIENT_TEXT_NOT_ADMITTED")
        self.assertIsNone(text["answer_text"])
        code,denied=self.call(c1.MODEL_PATH,
                              {"request_id":prepared["request_id"]})
        self.assertEqual(code,403)
        self.assertEqual(denied["status"],"INDEPENDENT_TRUST_ROOT_NOT_ADMITTED")
        self.assertFalse(denied["provider_called"])
        self.assertFalse(denied["product_pass"])
        # This single same-task journal contains SOURCE+Task freeze and nothing
        # resembling a generated delta or verified semantic/client ACK.
        log=self.dir/"native-journal.jsonl.native-live.jsonl"
        entries=[json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["task_sha256"],prepared["task_contract_sha256"])
        self.assertEqual(entries[0]["request_id"],prepared["request_id"])
        self.assertEqual(entries[0]["event"],
                         "real_a05_source_and_task_prepared_NOT_PROVIDER")
        self.assertFalse(entries[0]["provider_called"])

    def test_02_client_cannot_pull_unverified_text_or_forge_endpoints(self):
        self.boot()
        for route in (
            c1.LIVE_VERIFIED_NEXT,
            c1.LIVE_VERIFIED_NEXT+"?request_id=bogus&claim_id="+live.OBLIGATIONS[0],
            c1.LIVE_VERIFIED_NEXT+"?request_id="+"f"*48+"&claim_id="+live.OBLIGATIONS[0],
            c1.LIVE_VERIFIED_NEXT+"?request_id="+"f"*48+"&claim_id=foreign",
            c1.LIVE_VERIFIED_NEXT+"?request_id="+"f"*48+"&claim_id="+live.OBLIGATIONS[0]+"&extra=1",
        ):
            code,result=self.call(route)
            self.assertEqual(code,403)
            self.assertFalse(result["product_pass"])
        code,bad=self.call(c1.LIVE_VERIFIED_NEXT+"?request_id="+"f"*48+
                           "&claim_id="+live.OBLIGATIONS[0],token="wrong")
        self.assertEqual(code,403)
        self.assertEqual(bad["status"],"CLIENT_AUTH_DENIED")
        # The existing source-only Native ACK does not authenticate model text.
        code,bad=self.call(c1.LIVE_ACK,{"request_id":"f"*48,
                     "claim_id":live.OBLIGATIONS[0],
                     "challenge":"forged", "text_sha256":"0"*64,
                     "signed_client_ack":{"payload":{},"signature_b64":""}})
        self.assertEqual(code,403)

    def test_03_revoked_A05_after_prepare_does_not_publish_any_model(self):
        self.boot()
        code,prepared=self.call(c1.LIVE_PREPARE,self.allowed())
        self.assertEqual(code,200)
        self.fence.write_text(json.dumps({
          "release_id":f03.A05_RELEASE_ID,"minimum_epoch":2}))
        self.fence.chmod(0o600)
        # Real firstparty Reader must refuse restored/stale epoch.
        direct=f03.A05OwnerCorpusAdmission(ROOT,fence=self.fence)
        source=direct.source_retrieval("PolicyEngine",tenant="owner-internal",
                     principal="os-uid:"+str(os.geteuid()),
                     obligations=["PolicyEngine decides."])
        self.assertEqual(source["decision"],
                         "DENY_STALE_RESTORED_OR_INVALID_REVOCATION")
        code,denied=self.call(c1.MODEL_PATH,
                              {"request_id":prepared["request_id"]})
        self.assertEqual(code,403)
        self.assertEqual(denied["status"],"INDEPENDENT_TRUST_ROOT_NOT_ADMITTED")
        self.assertFalse(denied["provider_called"])


    def test_04_external_receipt_expiry_cannot_retroactively_authorize(self):
        """Pure time-window policy; zero generated or self-signed issuer data."""
        now=int(time.time())
        good=live.valid_independent_receipt_window(now-5,now+60,now=now)
        self.assertTrue(good)
        for issued,expiry in (
            (now-301,now+30),
            (now+1,now+60),
            (now-5,now+301),
            (now-5,now-1),
            (now-5,now+296),
        ):
            self.assertFalse(live.valid_independent_receipt_window(
                issued,expiry,now=now))
        self.assertIsNone(live.TRUST_ROOT_MANIFEST_SHA256)


if __name__=="__main__":
    unittest.main()
