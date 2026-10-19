"""Behavioral baseline: actual F02 normalized event cannot enter G01 A05 consumer."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
import types
if "knowledge_engine" not in sys.modules:
    pkg=types.ModuleType("knowledge_engine")
    pkg.__path__=[str(ROOT / "src/knowledge_engine")]
    sys.modules["knowledge_engine"]=pkg
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
sys.path.insert(0, str(ROOT / "src"))
from knowledge_engine import m27_f02_current_native_model_events as f02
from knowledge_engine import m27_g01_current_native_consumer as g

class ActualF02G01ABIRed(unittest.TestCase):
    def test_normalized_f02_source_bound_wire_enters_g01(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)
            fence=folder/"fence.json"
            fence.write_text(json.dumps({"release_id": g.h02.f03.A05_RELEASE_ID, "minimum_epoch": 1}))
            fence.chmod(0o600)
            c=g.Consumer(repo=ROOT, fence=fence, journal=folder/"g01.jsonl")
            start=c.start({"task_id":"g01-current-task","request_id":"join-real-behavior-01",
                           "question":g.QUESTION,"tenant":"owner-internal",
                           "principal":"os-uid:"+str(os.geteuid()),
                           "cache_mode":"OFF","deadline_seconds":120})
            pins=start["pins"]
            p=f02.NativeEventProducer(f02.Pins(
                task_id=pins["task_id"],request_id=pins["request_id"],
                question_sha256=pins["question_sha256"],task_contract_sha256=pins["task_contract_sha256"],
                tenant=pins["tenant"],principal=pins["principal"],
                source_release_sha256=pins["source_release_sha256"],
                source_manifest_sha256=pins["source_manifest_sha256"],
                source_rights_epoch=pins["source_rights_epoch"],
                source_acl_sha256=pins["source_acl_sha256"],
                answer_obligation_ids=tuple(pins["answer_obligation_ids"]),
                model_route_policy_version=pins["model_route_policy_version"],max_tokens=20,
                deadline_monotonic_ns=pins["deadline"], cache_mode="OFF"),
                f02.EventJournal(folder/"f02.jsonl"))
            raw=json.dumps({"event":"request_start","request_id":pins["request_id"]}).encode()
            if os.environ.get("M27_JOIN_BEHAVIOR_BASELINE") == "1":
                # Historical real behavioral failure, not a missing import.
                observed=p.ingest(raw)[0]
                result=c.event(start["session_id"],observed)
                self.assertEqual(result["status"],"EVENT_ACCEPTED")
            else:
                from knowledge_engine import m27_h02_f02_g01_native_join_nonprod as join
                j=join.NativeFixtureJoin(start,p,lambda e:c.event(start["session_id"],e))
                self.assertEqual(j.ingest(raw),1)
                self.assertEqual(len(j.bindings),1)
                self.assertNotEqual(j.bindings[0]["upstream_raw_provider_wire_sha256"],
                                    j.bindings[0]["downstream_g01_data_sha256"])

if __name__=="__main__":unittest.main()
