"""F04 Owner Native 01 fail-closed and locked source negative tests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

APP=Path(__file__).resolve().parents[1]/"packaging/m27_f04_owner_native_01/native_entrypoint.py"
spec=importlib.util.spec_from_file_location("owner_native_app",APP)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class NativeAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name)
        self.src=self.d/"src";self.src.mkdir()
        names=["m27_c1_dev_minimax_a05_e2e.py"]+[
            "m27_fixture_%02d.py"%i for i in range(14)]
        pairs={}
        for i,name in enumerate(names):
            raw=("content=%d\n"%i).encode()
            (self.src/name).write_bytes(raw)
            pairs[name]=hashlib.sha256(raw).hexdigest()
        self.lock=self.d/"lock.json"
        self.payload={"schema":app.ABI+".source-lock/v1",
                      "head":app.C1_HEAD,"tree":app.C1_TREE,
                      "modules":pairs}
        self.save()
    def save(self):
        self.lock.write_text(json.dumps(self.payload,sort_keys=True))
    def test_lock_15_exact_bytes(self):
        self.assertEqual(app.check_source_lock(self.src,self.lock)["source_module_count"],15)
    def test_source_tampering_fail_closed(self):
        (self.src/"m27_fixture_00.py").write_text("tampered")
        with self.assertRaisesRegex(app.Denied,"IMAGE_SOURCE_SHA256_MISMATCH"):
            app.check_source_lock(self.src,self.lock)
    def test_unlisted_module_rejected(self):
        (self.src/"m27_additional.py").write_text("pass\n")
        with self.assertRaisesRegex(app.Denied,"UNLISTED_IMAGE_SOURCE_MODULE"):
            app.check_source_lock(self.src,self.lock)
    def test_different_head_rejected(self):
        self.payload["head"]="0"*40;self.save()
        with self.assertRaisesRegex(app.Denied,"IMAGE_SOURCE_LOCK_INCORRECT"):
            app.check_source_lock(self.src,self.lock)
    def test_module_deleted_rejected(self):
        (self.src/"m27_fixture_01.py").unlink()
        with self.assertRaisesRegex(app.Denied,"IMAGE_SOURCE_SHA256_MISMATCH"):
            app.check_source_lock(self.src,self.lock)
    def test_owner_only_capability(self):
        t=self.d/"token";t.write_text("placeholder")
        t.chmod(0o600)
        app.owner_only_file(t)
        t.chmod(0o644)
        with self.assertRaisesRegex(app.Denied,"CAPABILITY_FILE_OWNER_MODE_DENIED"):
            app.owner_only_file(t)
    def test_root_may_not_run(self):
        a=SimpleNamespace(provider_mode="m26-parity-direct")
        with mock.patch.object(app.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(app.Denied,"ROOT_NATIVE_PRODUCT_DENIED"):
                app.preflight(a)
    def test_unapproved_route_denied(self):
        a=SimpleNamespace(provider_mode="minimax-dev")
        with mock.patch.object(app.os,"geteuid",return_value=65532):
            with self.assertRaisesRegex(app.Denied,"UNAUTHORIZED_PROVIDER_ROUTE"):
                app.preflight(a)
    def test_valid_lock_without_git_checkout_not_task(self):
        a=SimpleNamespace(provider_mode="m26-parity-direct",source_root=str(self.src),
                          source_lock=str(self.lock),repo=str(self.d/"absent"))
        with mock.patch.object(app.os,"geteuid",return_value=65532):
            with self.assertRaisesRegex(app.Denied,"PINNED_RUNTIME_REPO_UNAVAILABLE"):
                app.preflight(a)

if __name__=="__main__":
    unittest.main()
