"""Independent F03-only firstparty A05 Gitless source admission safety tests.

Real BASE_H02 A05 11 documents / 21 citation spans, actual copied bytes,
OS process, revocation and a distinct source issuer authority HOLD.
Neither test mints Ed25519 keys nor claims any Product/source signature.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/"src/knowledge_engine"))
import m27_f03_source_rights_admission as f03


class RealGitlessA05Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="m27-f03-true-gitless-a05-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.stage=self.root/"packaged_source_without_git"
        self.stage.mkdir(mode=0o700)
        self.fence=self.root/"owner_a05_fence.json"
        self.epoch=1
        self.fence.write_text(json.dumps({
            "release_id":f03.A05_RELEASE_ID,"minimum_epoch":1}))
        self.fence.chmod(0o600)
        self.files={}
        for rel in sorted(f03.F03_GITLESS_ALLOWED_A05):
            target=self.stage/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            raw=(REPO/rel).read_bytes()
            self.assertEqual(raw,subprocess.run([
                "git","-C",str(REPO),"cat-file","blob",f03.BASE_H02+":"+rel],
                capture_output=True,check=True).stdout)
            target.write_bytes(raw)
            target.chmod(0o644)
            self.files[rel]={"path":rel,"sha256":f03.sha(raw),
                  "git_blob_oid":f03._f03_git_blob_oid(raw),"git_mode":"100644"}
        mutable=f03.A05_SOURCE+"/revocations.json"
        p=self.stage/mutable
        p.write_bytes((REPO/mutable).read_bytes())
        p.chmod(0o644)
        self.head=subprocess.run(["git","-C",str(REPO),"rev-parse","HEAD"],
                                 check=True,capture_output=True,text=True).stdout.strip()
        self.tree=subprocess.run(["git","-C",str(REPO),"rev-parse","HEAD^{tree}"],
                                 check=True,capture_output=True,text=True).stdout.strip()
        now=int(time.time())
        self.payload={
            "schema":f03.F03_GITLESS_ABI,"kind":"a05",
            "head":self.head,"tree":self.tree,"base_h02":f03.BASE_H02,
            "a05_release_id":f03.A05_RELEASE_ID,
            "a05_manifest_sha256":f03.A05_SOURCE_PIN,
            "a05_revision":f03.A05_REVISION,
            "source_controller":"REAL_EXTERNAL_CONTROLLER_MISSING",
            "tenant":"owner-internal",
            "principal":"os-uid:"+str(os.geteuid()),
            "epoch":self.epoch,"issued_at":now-1,"expires_at":now+300,
            "rights_scope":f03.A05_LOCAL_SCOPE,
            "files":list(self.files.values())}

    def structural(self, **changes):
        return f03.inspect_a05_gitless_bytes_unsigned(
             self.stage,{**self.payload,**changes},
             expected_head=self.head,expected_tree=self.tree,
             expected_epoch=self.epoch)

    def reader(self):
        return f03.A05OwnerCorpusAdmission(self.stage,fence=self.fence)

    def retrieve(self):
        return self.reader().source_retrieval(
            "PolicyEngine",tenant="owner-internal",
            principal="os-uid:"+str(os.geteuid()),
            obligations=["PolicyEngine decides."])

    def test_01_real_A05_all_11_document_21_span_git_oid_SHA_structural(self):
        corpus=json.loads((self.stage/f03.A05_SOURCE/"corpus.json").read_bytes())
        release=json.loads((self.stage/f03.A05_SOURCE/"release.json").read_bytes())
        self.assertEqual(len(corpus["docs"]),11)
        self.assertEqual(len(corpus["chunks"]),21)
        self.assertEqual(release["source_manifest_sha256"],f03.A05_SOURCE_PIN)
        self.assertEqual(f03.sha((self.stage/f03.A05_SOURCE/"corpus.json").read_bytes()),
                         f03.A05_SOURCE_PIN)
        self.assertFalse((self.stage/".git").exists())
        checked=self.structural()
        self.assertEqual(checked["verified_immutable_files"],14)
        self.assertFalse(checked["source_authorized"])
        self.assertFalse(checked["product_admitted"])
        for rel,meta in self.files.items():
            git_oid=subprocess.run([
                "git","-C",str(REPO),"rev-parse",f03.BASE_H02+":"+rel],
                text=True,capture_output=True,check=True).stdout.strip()
            self.assertEqual(git_oid,meta["git_blob_oid"])

    def test_02_baseline_actual_original_F03_git_cat_file_fail_without_git(self):
        # Load unmodified original F03 directly from immutable accepted c9 commit.
        blob=subprocess.run([
            "git","-C",str(REPO),"show",
            "c9ebdfc0d8ce58c981488a12927099cb2b71ab3e:"
            "src/knowledge_engine/m27_f03_source_rights_admission.py"],
            capture_output=True,check=True).stdout
        old=self.root/"f03_old_module.py"
        old.write_bytes(blob)
        spec=importlib.util.spec_from_file_location("real_previous_f03",old)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cmd=subprocess.run(["git","-C",str(self.stage),"cat-file","blob",
                            f03.BASE_H02+":"+f03.A05_SOURCE+"/corpus.json"],
                           capture_output=True)
        self.assertEqual(cmd.returncode,128)
        previous=module.A05OwnerCorpusAdmission(self.stage,fence=self.fence)
        result=previous.source_retrieval(
            "PolicyEngine",tenant="owner-internal",
            principal="os-uid:"+str(os.geteuid()),
            obligations=["PolicyEngine decides."])
        self.assertEqual(result["decision"],"DENY_MISSING_PINNED_SOURCE")
        self.assertFalse(result["candidate_only"])

    def test_03_current_explicit_controller_hold_real_A05(self):
        result=self.retrieve()
        self.assertEqual(result["decision"],"DENY_SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        self.assertFalse(result["candidate_only"])
        self.assertFalse(result["product_admitted"])
        self.assertEqual(len(self.files),14)
        self.assertIsNone(f03.F03_EXTERNAL_SOURCE_ROOT_SHA256)

    def test_04_unsigned_receipt_not_promoted_to_separately_signed_reader(self):
        manifest=self.root/"owner_self_claimed.json"
        manifest.write_text(json.dumps({"payload":self.payload,"signature_b64":""}))
        key=self.root/"non_authorized.pem"
        key.write_text("NOT A TRUSTED EXTERNAL SOURCE ROOT")
        key.chmod(0o600)
        with self.assertRaisesRegex(f03.Rejected,
                                   "SOURCE_CONTROLLER_READER_NOT_ADMITTED"):
            f03.F03ExternalGitlessByteReader(
                self.stage,signed_manifest=manifest,public_root=key,
                expected_head=self.head,expected_tree=self.tree,
                expected_epoch=1,kind="a05")
        self.assertEqual(self.retrieve()["decision"],
                         "DENY_SOURCE_CONTROLLER_READER_NOT_ADMITTED")

    def test_05_tamper_document_extra_file_and_symlink_deny(self):
        rel=sorted(x for x in self.files if x.endswith(".md"))[0]
        file=self.stage/rel
        original=file.read_bytes()
        file.write_bytes(original+b"\nUNAUTHORIZED CHANGE")
        with self.assertRaisesRegex(f03.Rejected,"SHA_OR_GIT_OID_DRIFT"):
            self.structural()
        file.write_bytes(original)
        extra=file.parent/".env.secret"
        extra.write_text("INERT_NEGATIVE_ONLY")
        with self.assertRaisesRegex(f03.Rejected,"UNDECLARED_OR_UNSAFE"):
            self.structural()
        extra.unlink()
        link=file.parent/"unauthorized.md"
        link.symlink_to(file)
        with self.assertRaisesRegex(f03.Rejected,"UNDECLARED_OR_UNSAFE"):
            self.structural()
        link.unlink()
        self.assertEqual(self.structural()["verified_immutable_files"],14)

    def test_06_tenant_revision_epoch_expiry_wrong_source_denials(self):
        for changed in (
           {"tenant":"foreign-tenant"},
           {"base_h02":"f"*40},
           {"epoch":2},
           {"rights_scope":"REMOTE_PRODUCT_PUBLISH"},
           {"expires_at":int(time.time())-1},
           {"head":"a"*40}):
            with self.subTest(change=changed),self.assertRaises(f03.Rejected):
                self.structural(**changed)
        with self.assertRaisesRegex(f03.Rejected,
                                    "GITLESS_A05_INCOMPLETE_IMMUTABLE_SET"):
            self.structural(files=self.payload["files"][:-1])

    def test_07_separate_actual_OS_process_real_source_structural_and_denied(self):
        code=(
            "import sys,json;from pathlib import Path;"
            "sys.path.insert(0,sys.argv[1]);"
            "import m27_f03_source_rights_admission as f;"
            "p=json.loads(Path(sys.argv[3]).read_text());"
            "x=f.inspect_a05_gitless_bytes_unsigned("
            "Path(sys.argv[2]),p,expected_head=p['head'],"
            "expected_tree=p['tree'],expected_epoch=1);"
            "r=f.A05OwnerCorpusAdmission(Path(sys.argv[2]),"
            "fence=Path(sys.argv[4])).source_retrieval("
            "'PolicyEngine',tenant='owner-internal',"
            "principal='os-uid:'+str(__import__('os').geteuid()),"
            "obligations=['PolicyEngine decides.']);"
            "print(json.dumps({'files':x['verified_immutable_files'],"
            "'source_authorized':x['source_authorized'],"
            "'decision':r['decision'],'product':r['product_admitted']}))"
        )
        packet=self.root/"unsigned_metadata_for_structural_inspection.json"
        packet.write_text(json.dumps(self.payload))
        proc=subprocess.run([
            sys.executable,"-c",code,str(REPO/"src/knowledge_engine"),
            str(self.stage),str(packet),str(self.fence)],
            capture_output=True,text=True,check=True,timeout=15)
        data=json.loads(proc.stdout)
        self.assertEqual(data["files"],14)
        self.assertFalse(data["source_authorized"])
        self.assertEqual(data["decision"],"DENY_SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        self.assertFalse(data["product"])

    def test_08_epoch_fence_revoke_cannot_be_promoted_by_unsigned_A05(self):
        rev=self.stage/f03.A05_SOURCE/"revocations.json"
        state=json.loads(rev.read_text())
        state["epoch"]=2
        rev.write_text(json.dumps(state))
        self.fence.write_text(json.dumps({
            "release_id":f03.A05_RELEASE_ID,"minimum_epoch":2}))
        self.fence.chmod(0o600)
        self.assertEqual(self.retrieve()["decision"],
                         "DENY_SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        with self.assertRaisesRegex(f03.Rejected,
                                    "GITLESS_C1_A05_OR_RIGHTS_BINDING_DENIED"):
            f03.inspect_a05_gitless_bytes_unsigned(
                self.stage, self.payload, expected_head=self.head,
                expected_tree=self.tree, expected_epoch=2)
        self.assertFalse(f03.PRODUCT_ADMITTED)
        self.assertFalse(f03.CACHE_ENABLED)


    def test_09_legacy_local_source_gitless_path_also_gated(self):
        # F03's second historical git cat-file line is a distinct local-lease
        # reader. It can structurally inspect the real two BASE_H02 documents
        # but cannot self-issue a Source Controller credential.
        docs={}
        for rel in sorted(f03.ALLOWED_SOURCES):
            p=self.stage/rel
            p.parent.mkdir(parents=True,exist_ok=True)
            raw=(REPO/rel).read_bytes()
            pinned=subprocess.run([
                "git","-C",str(REPO),"cat-file","blob",f03.BASE_H02+":"+rel],
                capture_output=True,check=True).stdout
            self.assertEqual(raw,pinned)
            p.write_bytes(raw)
            p.chmod(0o644)
            docs[rel]={"path":rel,"sha256":f03.sha(raw),
                       "git_blob_oid":f03._f03_git_blob_oid(raw),
                       "git_mode":"100644"}
        packet={**self.payload,"kind":"local",
                "rights_scope":f03.SCOPE,"files":list(docs.values())}
        checked=f03.inspect_a05_gitless_bytes_unsigned(
            self.stage,packet,expected_head=self.head,
            expected_tree=self.tree,kind="local",expected_epoch=1)
        self.assertEqual(checked["verified_immutable_files"],2)
        self.assertFalse(checked["source_authorized"])
        doc=sorted(f03.ALLOWED_SOURCES)[0]
        registry=self.root/"local_lease.json"
        local_fence=self.root/"local_revocation_fence.json"
        now=int(time.time())
        lease={"scope":f03.SCOPE,"tenant":"owner-nonprod",
               "principal":"os-uid:"+str(os.geteuid()),
               "source_id":doc,"source_sha256":f03.sha((self.stage/doc).read_bytes()),
               "revision":f03.BASE_H02,"epoch":1,
               "expires_at":now+900,"retention_seconds":60,
               "status":"ACTIVE","rights_class":"owner-local-repo-read"}
        registry.write_text(json.dumps(lease))
        registry.chmod(0o600)
        local_fence.write_text(json.dumps({"source_id":doc,"minimum_epoch":1}))
        local_fence.chmod(0o600)
        reader=f03.LocalFirstPartySourceReader(self.stage,registry,local_fence)
        receipt=reader.read_source(doc,tenant="owner-nonprod",
              principal="os-uid:"+str(os.geteuid()),now=now)
        self.assertEqual(receipt["decision"],
                         "DENY_SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        self.assertFalse(receipt["product_admitted"])


if __name__=="__main__":
    unittest.main()
