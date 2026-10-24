"""Bounded adapter class reuse, with fresh Git pin comparison on every query."""
import importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_f03_source_rights_admission as f03

class AdapterReuseSafety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="c1-adapter-")
        self.addCleanup(self.tmp.cleanup)
        fence=Path(self.tmp.name)/"fence.json"
        fence.write_text(json.dumps({"release_id":f03.A05_RELEASE_ID,"minimum_epoch":1}))
        fence.chmod(0o600)
        self.reader=f03.A05OwnerCorpusAdmission(ROOT,fence=fence)
    def read(self):
        return self.reader.source_retrieval(
            "PolicyEngine",tenant="owner-internal",
            principal="os-uid:"+str(os.geteuid()),
            obligations=["PolicyEngine decides."])
    def test_adapter_loaded_once_but_pinned_checked_twice(self):
        loads=[]
        pins=[]
        original_loader=importlib.util.module_from_spec
        original_pin=self.reader._pinned
        def load(spec):
            if spec.name=="m27_a05_f03_owned_reader": loads.append(spec.name)
            return original_loader(spec)
        def pin(path):
            if path==f03.A05_ADAPTER: pins.append(path)
            return original_pin(path)
        with patch.object(importlib.util,"module_from_spec",side_effect=load), patch.object(self.reader,"_pinned",side_effect=pin):
            a=self.read()
            c=self.reader._adapter_class
            d=self.read()
        self.assertEqual(a["decision"],"A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",a)
        self.assertEqual(d["decision"],a["decision"])
        self.assertIs(self.reader._adapter_class,c)
        self.assertEqual(len(loads),1)
        self.assertEqual(len(pins),2)
    def test_cached_adapter_does_not_accept_changed_pinned_bytes(self):
        a=self.read()
        self.assertEqual(a["decision"],"A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",a)
        original_pin=self.reader._pinned
        def altered(path):
            if path==f03.A05_ADAPTER:return b"not the pinned adapter bytes"
            return original_pin(path)
        with patch.object(self.reader,"_pinned",side_effect=altered):
            denied=self.read()
        self.assertNotEqual(denied["decision"],"A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",denied)
        self.assertIn("ADAPTER_VERSION_DRIFT",denied["decision"])

if __name__=="__main__":unittest.main()
