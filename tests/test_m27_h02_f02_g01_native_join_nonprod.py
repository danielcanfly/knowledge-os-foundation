"""Actually crossed F02 raw wire -> G01 A05 first-party verifier -> separate OS HTTP Client.

All origin labels permanently SYNTHETIC_FIXTURE. No live provider requests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

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
from knowledge_engine import m27_h02_f02_g01_native_join_nonprod as j

C1="Verification belongs to the Execution & Governance Plane."
C2="PolicyEngine decides deterministic enforcement."

def wire(name,**kw):
    return json.dumps({"event":name,**kw},sort_keys=True).encode("utf-8")

def request(req):
    return {"task_id":"h02-joined-task", "request_id":req,"question":g.QUESTION,
            "tenant":"owner-internal","principal":"os-uid:"+str(os.geteuid()),
            "cache_mode":"OFF","deadline_seconds":90}

def f02_pins(start, **changes):
    p=start["pins"]
    pins=dict(
        task_id=p["task_id"],request_id=p["request_id"],
        question_sha256=p["question_sha256"],task_contract_sha256=p["task_contract_sha256"],
        tenant=p["tenant"],principal=p["principal"],
        source_release_sha256=p["source_release_sha256"],
        source_manifest_sha256=p["source_manifest_sha256"],
        source_rights_epoch=p["source_rights_epoch"],
        source_acl_sha256=p["source_acl_sha256"],
        answer_obligation_ids=tuple(p["answer_obligation_ids"]),
        model_route_policy_version=p["model_route_policy_version"],
        max_tokens=32,deadline_monotonic_ns=p["deadline"],cache_mode="OFF")
    pins.update(changes)
    return f02.Pins(**pins)

class NativeABIFanIn(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="m27-native-fanin-")
        self.addCleanup(tmp.cleanup)
        self.folder=Path(tmp.name)
        self.fence=self.folder/"fence.json"
        self.fence_rev(1)
        self.c=g.Consumer(repo=ROOT,fence=self.fence,journal=self.folder/"g.jsonl")
        self.start=self.c.start(request("join-task-request-001"))
        self.sid=self.start["session_id"]
        self.p=f02.NativeEventProducer(f02_pins(self.start),
              f02.EventJournal(self.folder/"f.jsonl"))
        self.join=j.NativeFixtureJoin(self.start,self.p,
                    lambda event:self.c.event(self.sid,event),
                    cancel=lambda:self.c.cancel(self.sid))

    def fence_rev(self,n):
        self.fence.write_text(json.dumps({"release_id":g.h02.f03.A05_RELEASE_ID,
                                          "minimum_epoch":n}))
        self.fence.chmod(0o600)

    def begin(self):
        self.join.ingest(wire("request_start",request_id=self.start["pins"]["request_id"]))
        self.join.ingest(wire("model_identity",provider="nonprod-observed-fixture",
                              model="fixture-model-v1"))

    def claim(self,idx):
        text=(C1,C2)[idx]
        self.join.ingest(wire("delta",text=text+"\n"))

    def complete(self):
        self.join.ingest(wire("provider_done"))
        return self.join.finalize(wire("stream_end",provider_done=True))

    def ack(self,idx):
        c=self.c.next_text(self.sid)
        self.assertEqual(c["status"],"VERIFIED_ANSWER_TEXT_READY")
        oid=self.start["pins"]["answer_obligation_ids"][idx]
        self.assertEqual(c["claim_id"],oid)
        self.assertEqual(c["answer_text"],(C1,C2)[idx])
        sha=g.sha((self.start["pins"]["request_id"]+"|"+oid+"|"+
                   c["challenge"]+"|"+c["text_sha256"]).encode())
        return self.c.ack(self.sid,oid,c["challenge"],c["text_sha256"],sha)

    def test_01_join_same_task_source_verified_two_acks_terminal(self):
        self.begin()
        self.claim(0)
        self.assertEqual(self.ack(0)["status"],"CLIENT_ACK_ACCEPTED")
        self.claim(1)
        self.assertEqual(self.ack(1)["status"],"CLIENT_ACK_ACCEPTED")
        done=self.complete()
        self.assertEqual(done["status"],"F02_SYNTHETIC_STREAM_END_G01_DONE")
        terminal=self.join.terminal(lambda:self.c.terminal(self.sid))
        self.assertEqual(terminal["status"],"LOCAL_FIXTURE_ANSWERED")
        self.assertFalse(terminal["fresh_generated_provenance"])
        self.assertEqual(len(self.join.bindings),6)
        self.assertEqual(self.join.bindings[-1]["event_kind"],"provider_done")
        self.assertEqual(self.join.bindings[-1]["upstream_raw_provider_wire_sha256"],
                         self.join.pending_done["raw_event_sha256"])
        self.assertNotEqual(self.join.bindings[-1]["upstream_raw_provider_wire_sha256"],
                            self.join.bindings[-1]["downstream_g01_data_sha256"])
        self.assertEqual(self.join.seq,6)
        self.assertEqual(self.p.origin_class,f02.SYNTHETIC)
        self.assertEqual(self.start["pins"]["max_tokens"],0)
        self.assertGreater(self.p.pins.max_tokens,0)
        self.assertEqual(self.p.pins.task_contract_sha256,
                         self.start["pins"]["task_contract_sha256"])
        rows=[json.loads(s) for s in (self.folder/"g.jsonl").read_text().splitlines()]
        self.assertEqual(len([r for r in rows if r["event"]=="client_ack"]),2)
        self.assertEqual(rows[-1]["event"],"terminal")
        with self.assertRaisesRegex(j.JoinDenied,"REPLAY"):
            self.join.terminal(lambda: self.c.terminal(self.sid))

    def test_02_reject_cross_task_and_source_snapshot_or_budget(self):
        for values in ({"task_id":"other-task"},
                       {"task_contract_sha256":"0"*64},
                       {"source_release_sha256":"0"*64},
                       {"source_manifest_sha256":"0"*64},
                       {"source_rights_epoch":99},
                       {"source_acl_sha256":"0"*64},
                       {"answer_obligation_ids":("x","y")},
                       {"max_tokens":129}):
            with self.subTest(values=values):
                p=f02.NativeEventProducer(f02_pins(self.start,**values),
                    f02.EventJournal(self.folder/("f"+str(len(list(self.folder.glob("f*.jsonl"))))+".jsonl")))
                with self.assertRaises(j.JoinDenied):
                    j.NativeFixtureJoin(self.start,p,lambda ev:self.c.event(self.sid,ev))

    def test_03_model_identity_observed_never_authorizes_live(self):
        self.begin()
        self.assertEqual(self.join.bindings[0]["event_kind"],"provider_start")
        self.assertTrue(any(x["f02_kind"]=="model_identity_observed"
                            and not x["mapped"] for x in self.join.raw_history))
        self.assertEqual(self.join.bindings[0]["origin"],"SYNTHETIC_FIXTURE")
        with self.assertRaisesRegex(f02.Refused,"NEW_LIVE_GRANT"):
            f02.NativeEventProducer(f02_pins(self.start),
               f02.EventJournal(self.folder/"unauth-live.jsonl"),
               origin_class=f02.LIVE,
               live_receipt_verifier=lambda receipt:True,
               authenticated_provider_receipt={"self_declared":"ok"})

    def test_04_revocation_before_claim_sticky_no_restore(self):
        self.begin()
        self.fence_rev(2)
        with self.assertRaises(g.h02.Denied):
            self.claim(0)
        self.fence_rev(1)
        with self.assertRaises(j.JoinDenied):
            self.join.terminal(lambda: self.c.terminal(self.sid))
        self.assertEqual(self.c.sessions[self.sid]["state"],"ABSTAINED")

    def test_05_revocation_after_first_ack(self):
        self.begin();self.claim(0);self.ack(0)
        self.fence_rev(2)
        with self.assertRaises(g.h02.Denied):
            self.claim(1)
        self.assertEqual(self.c.sessions[self.sid]["state"],"ABSTAINED")

    def test_06_revocation_after_two_ack_before_terminal(self):
        self.begin();self.claim(0);self.ack(0);self.claim(1);self.ack(1)
        self.complete()
        self.fence_rev(2)
        with self.assertRaises(g.h02.Denied):
            self.join.terminal(lambda:self.c.terminal(self.sid))
        self.assertNotEqual(self.c.sessions[self.sid]["state"],"TERMINATED")

    def test_07_missing_done_cannot_terminate(self):
        self.begin();self.claim(0);self.ack(0);self.claim(1);self.ack(1)
        with self.assertRaisesRegex(j.JoinDenied,"PROVIDER_DONE_REQUIRED"):
            self.join.finalize(wire("stream_end",provider_done=True))
        with self.assertRaisesRegex(j.JoinDenied,"UNVERIFIED_STREAM_END"):
            self.join.terminal(lambda:self.c.terminal(self.sid))

    def test_08_extra_tail_and_replay_rejected(self):
        self.begin();self.claim(0);self.claim(1)
        with self.assertRaises(f02.Refused):
            self.join.ingest(wire("delta",text="Third unsupported tail.\n"))
        self.assertTrue(self.join.aborted)
        self.assertNotEqual(self.c.sessions[self.sid]["state"],"TERMINATED")
        with self.assertRaises(j.JoinDenied):
            self.join.ingest(wire("provider_done"))

    def test_09_timeout_and_cancel_terminal_forbidden(self):
        self.join.abort()
        with self.assertRaises(j.JoinDenied):
            self.join.ingest(wire("request_start",request_id=self.start["pins"]["request_id"]))
        self.assertEqual(self.c.sessions[self.sid]["state"],"CANCELLED")
        with self.assertRaises(j.JoinDenied):
            self.join.terminal(lambda:self.c.terminal(self.sid))

    def test_10_event_hash_domains_and_unsupported_semantic(self):
        self.begin()
        self.claim(0)
        self.assertTrue(self.join.bindings)
        for bind in self.join.bindings:
            self.assertEqual(bind["origin"],f02.SYNTHETIC)
        self.assertNotEqual(self.join.bindings[0]["upstream_raw_provider_wire_sha256"],
                            self.join.bindings[0]["downstream_g01_data_sha256"])
        self.assertEqual(self.join.bindings[-1]["event_kind"],"claim_proposed")

    def test_11_source_snapshot_cache_auto_refresh_bypass_all_off(self):
        for mode in ("AUTO","REFRESH","BYPASS"):
            with self.subTest(mode=mode):
                with self.assertRaises(g.h02.Denied):
                    self.c.start({**request("other-request"),"cache_mode":mode})
        self.assertEqual(self.start["cache"],"OFF")
        self.assertFalse(self.start["product_pass"])
        self.assertEqual(self.join.start["pins"]["cache_mode"],"OFF")
        self.assertEqual(self.join.producer.pins.cache_mode,"OFF")

    def test_12_cross_request_replay_rejected_sticky(self):
        self.begin()
        with self.assertRaisesRegex(f02.Refused,"DUPLICATE_START"):
            self.join.ingest(wire("request_start",request_id=self.start["pins"]["request_id"]))
        self.assertTrue(self.join.aborted)
        self.assertEqual(self.c.sessions[self.sid]["state"],"CANCELLED")

    def test_13_forged_origin_or_identity_fields_not_promoted(self):
        with self.assertRaisesRegex(f02.Refused,"PROVENANCE_OR_AUTHORITY_SPOOF"):
            self.join.ingest(wire("request_start",request_id=self.start["pins"]["request_id"],
                                   model_origin_class="LIVE_NEW_PROVIDER"))
        self.assertTrue(self.join.aborted)
        self.assertNotEqual(self.c.sessions[self.sid]["state"],"TERMINATED")

    def test_14_expired_deadline_fails_local_source_publication(self):
        self.begin()
        self.c.sessions[self.sid]["deadline_ns"]=time.monotonic_ns()-1
        with self.assertRaisesRegex(g.h02.Denied,"RUN_DEADLINE_EXPIRED"):
            self.claim(0)
        self.assertEqual(self.c.sessions[self.sid]["state"],"ABSTAINED")
        with self.assertRaises(j.JoinDenied):
            self.join.terminal(lambda:self.c.terminal(self.sid))

    def test_15_missing_second_obligation_early_done_rejected(self):
        self.begin();self.claim(0);self.ack(0)
        with self.assertRaisesRegex(f02.Refused,"INCOMPLETE_OBLIGATIONS"):
            self.join.ingest(wire("provider_done"))
        self.assertTrue(self.join.aborted)
        self.assertNotEqual(self.c.sessions[self.sid]["state"],"TERMINATED")

CLIENT=r'''
import hashlib,json,os,sys,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
host,token,sid,reqid,marker=sys.argv[1:]
opener=build_opener(ProxyHandler({}))
def call(path,body=None):
    h={"X-G01-Local-Capability":token,"Host":host.split("//")[1]}
    if body is None:request=Request(host+path,headers=h)
    else:
        h["Content-Type"]="application/json"
        request=Request(host+path,data=json.dumps(body).encode(),headers=h,method="POST")
    with opener.open(request,timeout=10) as r:return json.loads(r.read())
claims=[]
for i in range(2):
    limit=time.monotonic()+25
    while time.monotonic()<limit:
        item=call("/nonprod/g01-current/next?session_id="+sid)
        if item["status"]=="VERIFIED_ANSWER_TEXT_READY":break
        time.sleep(.02)
    assert item["status"]=="VERIFIED_ANSWER_TEXT_READY",item
    claim=item["claim_id"];sha=item["text_sha256"];ch=item["challenge"]
    ack=hashlib.sha256((reqid+"|"+claim+"|"+ch+"|"+sha).encode()).hexdigest()
    receipt=call("/nonprod/g01-current/ack",{"session_id":sid,"claim_id":claim,
       "challenge":ch,"text_sha256":sha,"ack_sha256":ack})
    assert receipt["status"]=="CLIENT_ACK_ACCEPTED",receipt
    claims.append({"claim":claim,"text_sha256":sha,"citation":item["citation"],
                   "ack_status":receipt["status"],"client_pid":os.getpid()})
    Path(marker).write_text(json.dumps({"acks":claims,"last_ns":time.monotonic_ns()}))
print(json.dumps({"client_pid":os.getpid(),"acks":claims,"origin":"SYNTHETIC_FIXTURE"}))
'''

class NativeOSHTTPFanIn(unittest.TestCase):
    def test_12_real_separate_os_http_client_and_f02_source_join(self):
        with tempfile.TemporaryDirectory(prefix="m27-native-join-http-") as t:
            tmp=Path(t)
            fence=tmp/"fence.json"
            fence.write_text(json.dumps({"release_id":g.h02.f03.A05_RELEASE_ID,
                                         "minimum_epoch":1}))
            fence.chmod(0o600)
            ready=tmp/"server-ready.json";journal=tmp/"server-journal.jsonl"
            server=subprocess.Popen([sys.executable,
                  str(ROOT/"src/knowledge_engine/m27_g01_current_native_consumer.py"),
                  "--repo",str(ROOT),"--fence",str(fence),"--journal",str(journal),
                  "--ready-file",str(ready)],
                  stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            self.addCleanup(lambda:server.terminate() if server.poll() is None else None)
            for _ in range(250):
                if ready.exists():break
                if server.poll() is not None:
                    self.fail("OS_SERVER_EXIT "+server.communicate()[1].decode()[:900])
                time.sleep(.04)
            self.assertTrue(ready.exists())
            info=json.loads(ready.read_text())
            host="http://127.0.0.1:"+str(info["port"])
            token=info["transport_token"]
            opener=build_opener(ProxyHandler({}))
            def http(path,payload):
                headers={"X-G01-Local-Capability":token,"Host":"127.0.0.1:"+str(info["port"]),
                         "Content-Type":"application/json"}
                req=Request(host+path,data=json.dumps(payload).encode(),
                            headers=headers,method="POST")
                with opener.open(req,timeout=15) as resp:
                    return json.loads(resp.read())
            start=http(g.ROUTE,request("joined-real-os-req-01"))
            sid=start["session_id"]
            p=f02.NativeEventProducer(f02_pins(start),
                 f02.EventJournal(tmp/"f02-journal.jsonl"))
            join=j.NativeFixtureJoin(start,p,
                 lambda event:http(g.EVENT,{"session_id":sid,"event":event}),
                 cancel=lambda:http(g.CANCEL,{"session_id":sid}))
            client_marker=tmp/"ack-marker.json"
            client=subprocess.Popen([sys.executable,"-u","-c",CLIENT,
                 host,token,sid,start["pins"]["request_id"],str(client_marker)],
                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.addCleanup(lambda:client.kill() if client.poll() is None else None)
            def until_ack(n):
                limit=time.monotonic()+30
                while time.monotonic()<limit:
                    if client.poll() is not None and not client_marker.exists():
                        self.fail("CLIENT_EXIT "+client.communicate()[1][:1000])
                    if client_marker.exists():
                        try:
                            r=json.loads(client_marker.read_text())
                            if len(r["acks"])>=n:return r
                        except (OSError, ValueError):
                            pass
                    time.sleep(.03)
                self.fail("OS_CLIENT_ACK_TIMEOUT")
            join.ingest(wire("request_start",request_id=start["pins"]["request_id"]))
            join.ingest(wire("model_identity",provider="os-fixture-observed",
                             model="fiction-v1"))
            join.ingest(wire("delta",text=C1+"\n"))
            first=until_ack(1)
            first_ack_ns=first["last_ns"]
            join.ingest(wire("delta",text=C2+"\n"))
            second=until_ack(2)
            self.assertLess(first_ack_ns,second["last_ns"])
            before_done_ns=time.monotonic_ns()
            join.ingest(wire("provider_done"))
            done=join.finalize(wire("stream_end",provider_done=True))
            terminal=join.terminal(lambda:http(g.TERMINAL,{"session_id":sid}))
            stdout,stderr=client.communicate(timeout=20)
            self.assertEqual(client.returncode,0,stderr)
            receipt=json.loads(stdout)
            self.assertNotEqual(receipt["client_pid"],info["server_pid"])
            self.assertEqual(len(receipt["acks"]),2)
            self.assertEqual(terminal["status"],"LOCAL_FIXTURE_ANSWERED")
            self.assertFalse(terminal["fresh_generated_provenance"])
            self.assertEqual(done["model_origin_class"],"SYNTHETIC_FIXTURE")
            self.assertLess(second["last_ns"],before_done_ns)
            if os.environ.get("M27_JOIN_EVIDENCE_DIR"):
                out=Path(os.environ["M27_JOIN_EVIDENCE_DIR"])
                (out/"OS_JOIN_CLIENT_RECEIPT_SYNTHETIC_FIXTURE.json").write_text(
                    json.dumps({"server_pid":info["server_pid"],"client":receipt,
                      "start_pins":start["pins"],"join_stream_end":done,
                      "terminal":terminal,"upstream_downstream_bindings":join.bindings,
                      "preterminal_acks":2},sort_keys=True,indent=2))
                (out/"OS_JOIN_SERVER_JOURNAL_SYNTHETIC_FIXTURE.jsonl").write_bytes(
                    journal.read_bytes())
                (out/"OS_JOIN_F02_JOURNAL_SYNTHETIC_FIXTURE.jsonl").write_bytes(
                    (tmp/"f02-journal.jsonl").read_bytes())
            print("JOIN_OS_SERVER_PID",info["server_pid"],"CLIENT_PID",receipt["client_pid"],
                  "ACKS",len(receipt["acks"]),"TERMINAL",terminal["status"],
                  "PROVIDER_NOT_CALLED_SYNTHETIC_FIXTURE")
            server.terminate();server.communicate(timeout=10)

if __name__=="__main__":unittest.main()
