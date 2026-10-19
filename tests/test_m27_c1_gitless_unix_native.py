"""C1 distinct 8fb -> Gitless security and native same-netns Unix HTTP seam.

All tests are firstparty Nonprod local OS, not independent semantic signer
verification or an actual billable Provider call.
"""
from __future__ import annotations
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/knowledge_engine"))
import m27_c1_current_native_product_nonprod as c1
import m27_c1_gitless_source_proof as proof
import m27_c1_genuine_native_generation_seam as live


class UnixClientConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("c1-unix.local",timeout=10)
        self.path=path

    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.connect(str(self.path))


class C1GitlessUnix(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="c1-gitless-unix-")
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        os.chmod(self.dir,0o700)
        self.head=c1.git_field(ROOT,"HEAD")
        self.tree=c1.git_field(ROOT,"HEAD^{tree}")
        self.fence=self.dir/"fence"
        self.fence.write_text(json.dumps({
            "release_id":c1.h02.f03.A05_RELEASE_ID,"minimum_epoch":1}))
        self.fence.chmod(0o600)
        self.token=self.dir/"token"
        self.secret=os.urandom(32).hex()
        self.token.write_text(self.secret)
        self.token.chmod(0o600)
        self.journal=self.dir/"journal"
        self.sock=self.dir/"native.sock"

    def manifest(self):
        bundle=self.dir/"gitless"
        bundle.mkdir(mode=0o700,exist_ok=True)
        paths=["src/knowledge_engine/m27_c1_current_native_product_nonprod.py",
               "src/knowledge_engine/m27_c1_gitless_source_proof.py"]
        files=[]
        for rel in paths:
            target=bundle/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,target)
            target.chmod(0o644)
            raw=target.read_bytes()
            result=subprocess.run(["git","-C",str(ROOT),"hash-object",rel],
                                  text=True,capture_output=True,check=True)
            files.append({
                "path":rel,
                "sha256":hashlib.sha256(raw).hexdigest(),
                "git_blob_oid":result.stdout.strip(),
                "git_mode":"100644"})
        payload={"schema":proof.ABI,"head":self.head,"tree":self.tree,
                 "tenant":"owner-internal",
                 "source_release_id":c1.h02.f03.A05_RELEASE_ID,
                 "source_controller":"externally-required-A05-controller",
                 "expires_at":int(time.time())+120,
                 "files":files}
        return bundle,payload

    def test_01_physically_gitless_bundle_structural_integrity_not_signed(self):
        bundle,manifest=self.manifest()
        self.assertFalse((bundle/".git").exists())
        result=proof.inspect_exact_bundle(bundle,manifest,
                   expected_head=self.head,expected_tree=self.tree)
        self.assertEqual(result["files_verified"],2)
        self.assertFalse(result["signed_source_admitted"])
        self.assertEqual(result["status"],"EXACT_GIT_BLOB_SET_INSPECTED_UNSIGNED_ONLY")
        self.assertIsNone(proof.C1_GITLESS_TRUST_ROOT_SHA256)

    def test_02_gitless_tamper_extra_symlink_and_wrong_epoch_fail_closed(self):
        bundle,m=self.manifest()
        target=bundle/m["files"][0]["path"]
        target.write_bytes(target.read_bytes()+b"x")
        with self.assertRaisesRegex(proof.GitlessDenied,"SHA256_MISMATCH"):
            proof.inspect_exact_bundle(bundle,m,expected_head=self.head,
                                       expected_tree=self.tree)
        target.write_bytes((ROOT/m["files"][0]["path"]).read_bytes())
        extra=bundle/"src/knowledge_engine/unadmitted.py"
        extra.write_text("x")
        with self.assertRaisesRegex(proof.GitlessDenied,"EXTRA_OR_MISSING"):
            proof.inspect_exact_bundle(bundle,m,expected_head=self.head,
                                       expected_tree=self.tree)
        extra.unlink()
        extra.symlink_to(target)
        with self.assertRaisesRegex(proof.GitlessDenied,"UNAUTHORIZED_SYMLINK"):
            proof.inspect_exact_bundle(bundle,m,expected_head=self.head,
                                       expected_tree=self.tree)
        extra.unlink()
        m["expires_at"]=int(time.time())-1
        with self.assertRaisesRegex(proof.GitlessDenied,"EXPIRED"):
            proof.inspect_exact_bundle(bundle,m,expected_head=self.head,
                                       expected_tree=self.tree)

    def test_03_gitless_boot_requires_external_signed_root_no_self_cert(self):
        bundle,m=self.manifest()
        with self.assertRaisesRegex(c1.AdmissionDenied,"GITLESS_SIGNED_SOURCE"):
            c1.source_vector(bundle,expected_head=self.head,expected_tree=self.tree)
        sealed=self.dir/"externally-signed.json"
        sealed.write_text(json.dumps({"payload":m,"signature_b64":""}))
        pub=self.dir/"unknown-public.pem"
        pub.write_text("not a trusted public root")
        pub.chmod(0o600)
        with self.assertRaisesRegex(c1.AdmissionDenied,"EXTERNAL_SOURCE_SIGNER_NOT_ADMITTED"):
            c1.source_vector(bundle,expected_head=self.head,
                 expected_tree=self.tree,signed_gitless_manifest=sealed,
                 gitless_public_root=pub)
        self.assertFalse((bundle/".git").exists())

    def test_06_gitless_group_writable_and_hidden_bytes_rejected(self):
        bundle,m=self.manifest()
        file=bundle/m["files"][0]["path"]
        file.chmod(0o664)
        with self.assertRaisesRegex(proof.GitlessDenied,"SOURCE_MODE_OR_SYMLINK_DENIED"):
            proof.inspect_exact_bundle(bundle,m,expected_head=self.head,
                                       expected_tree=self.tree)
        file.chmod(0o644)
        (bundle/".env.production").write_text("do-not-read")
        with self.assertRaisesRegex(proof.GitlessDenied,"EXTRA_OR_MISSING"):
            proof.inspect_exact_bundle(bundle,m,expected_head=self.head,
                                       expected_tree=self.tree)

    def server(self):
        ready=self.dir/"ready.json"
        args=[sys.executable,
              str(ROOT/"src/knowledge_engine/m27_c1_current_native_product_nonprod.py"),
              "--repo",str(ROOT),"--fence",str(self.fence),"--journal",str(self.journal),
              "--token-file",str(self.token),"--expected-head",self.head,
              "--expected-tree",self.tree,"--ready-file",str(ready),
              "--unix-socket",str(self.sock)]
        proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        def stop():
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
            proc.stderr.close()
        self.addCleanup(stop)
        for _ in range(180):
            if ready.exists():break
            if proc.poll() is not None:
                output=proc.stderr.read(1000).decode(errors="replace")
                raise AssertionError("UNIX_BOOT_EXIT="+str(proc.returncode)+":"+output)
            time.sleep(0.05)
        self.assertTrue(ready.exists(),"UNIX_READY_TIMEOUT")
        data=json.loads(ready.read_text())
        self.assertEqual(data["unix_socket"],str(self.sock))
        self.assertFalse(data["product_admitted"])
        self.assertEqual(data["peer_identity"],"KERNEL_SAME_UID_LOCAL_ONLY_NOT_IDP")
        self.assertEqual(stat.S_IMODE(self.sock.lstat().st_mode),0o600)

    def request(self,path,body=None,*,host="c1-unix.local",token=None):
        c=UnixClientConnection(self.sock)
        raw=json.dumps(body).encode() if body is not None else None
        headers={"Host":host,"X-C1-Local-Capability":
                 self.secret if token is None else token}
        if raw is not None:headers["Content-Type"]="application/json"
        try:
            c.request("POST" if body is not None else "GET",path,
                      body=raw,headers=headers)
            response=c.getresponse()
            return response.status,json.loads(response.read())
        finally:c.close()

    def test_04_distinct_os_native_unix_http_task_two_acks_real_source(self):
        self.server()
        code,bad=self.request(c1.STATUS_PATH,token="wrong")
        self.assertEqual(code,403)
        self.assertEqual(bad["status"],"CLIENT_AUTH_DENIED")
        code,bad=self.request(c1.STATUS_PATH,host="forged-host")
        self.assertEqual(code,403)
        code,state=self.request(c1.STATUS_PATH)
        self.assertEqual(code,200)
        self.assertFalse(state["native_live"]["provider_called"])
        code,started=self.request(c1.SOURCE_PATH,
                        {"question":"PolicyEngine","tenant":"owner-internal"})
        self.assertEqual(code,200)
        self.assertTrue(started["independent_os_source_byte_verified"])
        self.assertFalse(started["generated_answer"])
        for claim in started["claims"]:
            code,receipt=self.request(c1.ACK_PATH,{
                "session_id":started["session_id"],"claim_id":claim["claim_id"],
                "challenge":claim["challenge"],"text_sha256":claim["text_sha256"]})
            self.assertEqual(code,200)
        code,done=self.request(c1.TERMINAL_PATH,
                    {"session_id":started["session_id"]})
        self.assertEqual(code,200)
        self.assertFalse(done["product_pass"])
        self.assertEqual([json.loads(x)["event"] for x in self.journal.read_text().splitlines()],
                         ["source_candidate_sent","client_ack","client_ack","terminal"])

    def test_05_native_unix_generation_still_signed_authority_gate(self):
        self.server()
        code,prepared=self.request(c1.LIVE_PREPARE,
                {"question":c1.g01.QUESTION,"tenant":"owner-internal",
                 "cache_mode":"OFF","max_tokens":64,"deadline_seconds":10,
                 "fallback_consent":False})
        self.assertEqual(code,200)
        self.assertEqual(prepared["prepared_source_count"],2)
        code,denied=self.request(c1.MODEL_PATH,
                                {"request_id":prepared["request_id"]})
        self.assertEqual(code,403)
        self.assertEqual(denied["status"],"INDEPENDENT_TRUST_ROOT_NOT_ADMITTED")
        self.assertFalse(denied["provider_called"])
        self.assertFalse(denied["product_pass"])


if __name__=="__main__":
    unittest.main()
