"""Current G01 consumer: real A05 OS source+independent HTTP; synthetic events only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_g01_current_native_consumer as g

QUESTION = g.QUESTION
C1 = "Verification belongs to the Execution & Governance Plane."
C2 = "PolicyEngine decides deterministic enforcement."
TARGET = ROOT / "src/knowledge_engine/m27_g01_current_native_consumer.py"
OLD = ROOT / "src/knowledge_engine/m27_h02_f03_cache_seam_join_nonprod.py"

def body(request_id="g01-new-req-001", **overrides):
    return {"task_id": "g01-current-task", "request_id": request_id, "question": QUESTION,
            "tenant": "owner-internal", "principal": "os-uid:" + str(os.geteuid()),
            "cache_mode": "OFF", "deadline_seconds": 240, **overrides}

def make_event(consumer, sid, kind, data, *, seq=None, **overrides):
    e = consumer.sessions[sid]
    number = e["seq"] + 1 if seq is None else seq
    value = {"event_id": "event-" + str(number) + "-" + str(time.monotonic_ns()),
             "task_id": e["pins"]["task_id"], "request_id": e["pins"]["request_id"],
             "seq": number, "monotonic_ns": max(time.monotonic_ns(), e["monotonic_ns"] + 1),
             "event_kind": kind, "model_origin_class": "SYNTHETIC_FIXTURE",
             "data": data, "raw_event_sha256": g.sha(g.canonical(data))}
    value.update(overrides)
    return value

def ack_fields(consumer, sid, claim_id):
    c = consumer.next_text(sid)
    assert c["claim_id"] == claim_id
    p = consumer.sessions[sid]["pins"]
    return {"sid": sid, "claim_id": claim_id, "challenge": c["challenge"],
            "text_sha256": c["text_sha256"],
            "ack_sha256": g.sha((p["request_id"] + "|" + claim_id + "|"
                                + c["challenge"] + "|" + c["text_sha256"]).encode())}

def fixture_claim(consumer, sid, ix, text):
    oid = g.OBLIGATIONS[ix][0]
    return make_event(consumer, sid, "claim_proposed",
                      {"obligation_id": oid, "text": text,
                       "citation": dict(consumer.sessions[sid]["proofs"][ix]["citation"])})

def push(c, sid, kind, data):
    return c.event(sid, make_event(c, sid, kind, data))

def start_model(c, sid, texts=C1 + "\n" + C2):
    push(c, sid, "provider_start", {"provider": "SYNTHETIC_FIXTURE"})
    push(c, sid, "provider_delta", {"text": texts})

CLIENT_SCRIPT = r'''
import hashlib,json,os,sys,time
from urllib.request import Request,urlopen
host,token=sys.argv[1:]
h={"Content-Type":"application/json","X-G01-Local-Capability":token}
def req(route,body=None):
    url=host+route
    if body is None: request=Request(url,headers={"X-G01-Local-Capability":token})
    else: request=Request(url,data=json.dumps(body).encode(),headers=h,method="POST")
    with urlopen(request,timeout=35) as resp:return resp.status,json.loads(resp.read())
def dig(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
q="Which plane includes Verification, and who decides deterministic policy enforcement?"
body={"task_id":"g01-current-task","request_id":"g01-native-os-client-001",
      "question":q,"tenant":"owner-internal","principal":"os-uid:"+str(os.geteuid()),
      "cache_mode":"OFF","deadline_seconds":240}
startstatus,start=req("/nonprod/g01-current/start",body)
sid=start["session_id"];pins=start["pins"]
seq=0;last=0;timeline=[]
def ev(kind,data):
    global seq,last
    seq+=1;last=max(time.monotonic_ns(),last+1)
    event={"event_id":"os-client-%d"%seq,"task_id":pins["task_id"],
           "request_id":pins["request_id"],"seq":seq,"monotonic_ns":last,
           "event_kind":kind,"model_origin_class":"SYNTHETIC_FIXTURE",
           "raw_event_sha256":dig(data),"data":data}
    _,out=req("/nonprod/g01-current/event",{"session_id":sid,"event":event})
    timeline.append({"kind":kind,"status":out["status"],"seq":seq})
    assert out["status"]=="EVENT_ACCEPTED",out
ev("provider_start",{"provider":"SYNTHETIC_FIXTURE"})
c1="Verification belongs to the Execution & Governance Plane."
c2="PolicyEngine decides deterministic enforcement."
ev("provider_delta",{"text":c1+"\n"+c2})
assert req("/nonprod/g01-current/next?session_id="+sid)[1]["status"]=="NO_VERIFIED_TEXT"
for idx,oid in enumerate(pins["answer_obligation_ids"]):
    text=[c1,c2][idx]
    ev("claim_proposed",{"obligation_id":oid,"text":text,
                         "citation":start["citations"][oid]})
    _,item=req("/nonprod/g01-current/next?session_id="+sid)
    assert item["status"]=="VERIFIED_ANSWER_TEXT_READY" and item["answer_text"]==text,item
    ack_digest=hashlib.sha256((pins["request_id"]+"|"+oid+"|"+item["challenge"]+"|"+item["text_sha256"]).encode()).hexdigest()
    _,receipt=req("/nonprod/g01-current/ack",
                  {"session_id":sid,"claim_id":oid,"challenge":item["challenge"],
                   "text_sha256":item["text_sha256"],"ack_sha256":ack_digest})
    assert receipt["status"]=="CLIENT_ACK_ACCEPTED",receipt
    timeline.append({"kind":"answer_text","text_sha256":item["text_sha256"],
                     "citation_sha256":item["citation"]["excerpt_sha256"]})
    timeline.append({"kind":"client_ack","status":receipt["status"]})
ev("provider_done",{"done":True})
_,terminal=req("/nonprod/g01-current/terminal",{"session_id":sid})
timeline.append({"kind":"terminal","status":terminal["status"]})
assert terminal["status"]=="LOCAL_FIXTURE_ANSWERED",terminal
print(json.dumps({"client_pid":os.getpid(),"start":startstatus,"task_pins":pins,
  "received_texts":[c1,c2],"terminal":terminal,
  "timeline":timeline,"model_origin_class":"SYNTHETIC_FIXTURE"},sort_keys=True))
'''

class NativeCurrentG01(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="m27-g01-current-")
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.fence = self.tmp / "fence.json"
        self.write_fence(1)
        self.journal = self.tmp / "journal.jsonl"
        self.c = g.Consumer(repo=ROOT, fence=self.fence, journal=self.journal)

    def write_fence(self, n):
        self.fence.write_text(json.dumps({"release_id": g.h02.f03.A05_RELEASE_ID,
                                          "minimum_epoch": n}))
        self.fence.chmod(0o600)

    def start(self):
        return self.c.start(body())["session_id"]

    def run_server(self, baseline=False):
        ready = self.tmp / "server-ready.json"
        file = OLD if baseline else TARGET
        proc = subprocess.Popen([sys.executable, str(file), "--repo", str(ROOT),
            "--fence", str(self.fence), "--journal", str(self.journal),
            "--ready-file", str(ready)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def clean():
            if proc.poll() is None:
                proc.terminate()
            try: proc.communicate(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.communicate()
        self.addCleanup(clean)
        for _ in range(180):
            if ready.exists(): break
            if proc.poll() is not None:
                self.fail("OS_SERVER_FAILED " + proc.communicate()[1].decode()[:1200])
            time.sleep(.05)
        self.assertTrue(ready.exists(), "OS_SERVER_NOT_READY")
        ready_obj = json.loads(ready.read_text())
        return proc, "http://127.0.0.1:" + str(ready_obj["port"]), ready_obj["transport_token"]

    def http(self, host, token, route, payload):
        h = {"Content-Type": "application/json", "X-G01-Local-Capability": token,
             "X-H02-F03-Token": token}
        req = Request(host + route, data=json.dumps(payload).encode(), headers=h,
                      method="POST")
        try:
            with urlopen(req, timeout=25) as resp:
                return resp.status, json.loads(resp.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_01_actual_h02_f03_to_new_g01_behavioral_red_green_os_http(self):
        # BEFORE: actual accepted H02-F03 service returns no G01 task outcome route
        # (HTTP 403); AFTER: a *different* first-party source-bound QA route works.
        old = os.environ.get("M27_G01_BASELINE") == "1"
        proc, host, token = self.run_server(baseline=old)
        status, result = self.http(host, token, g.ROUTE, body())
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "TASK_FROZEN_SOURCE_VERIFIED")
        self.assertEqual(result["model_origin_class"], "SYNTHETIC_FIXTURE")
        # Separate OS/TCP Client connects to new port. Baseline intentionally
        # stops above as the *real behavioral* RED proof, not missing import.
        if old: return
        # A second session is forbidden, so run OS client against a new server.
        # Terminate first server cleanly before creating separate journal.
        proc.terminate(); proc.wait(timeout=5)
        (self.tmp / "server-ready.json").unlink()
        self.journal.unlink()
        new, host, token = self.run_server()
        client = subprocess.run([sys.executable, "-c", CLIENT_SCRIPT, host, token],
                                capture_output=True, text=True, timeout=160)
        self.assertEqual(client.returncode, 0, client.stderr)
        receipt = json.loads(client.stdout)
        self.assertNotEqual(receipt["client_pid"], new.pid)
        self.assertEqual(receipt["terminal"]["status"], "LOCAL_FIXTURE_ANSWERED")
        self.assertFalse(receipt["terminal"]["product_pass"])
        self.assertFalse(receipt["terminal"]["fresh_generated_provenance"])
        kinds = [e["kind"] for e in receipt["timeline"]]
        self.assertLess(kinds.index("answer_text"), kinds.index("provider_done"))
        self.assertLess(kinds.index("client_ack"), kinds.index("terminal"))
        rows = [json.loads(x) for x in self.journal.read_text().splitlines()]
        self.assertEqual(rows[-2]["event"], "final_source_recheck")
        self.assertEqual(rows[-1]["event"], "terminal")
        self.assertEqual(len([x for x in rows if x["event"] == "client_ack"]), 2)
        evidence = os.environ.get("M27_G01_EVIDENCE_DIR")
        if evidence:
            Path(evidence, "OS_CLIENT_RECEIPT_SYNTHETIC_FIXTURE.json").write_text(
                json.dumps({"server_pid": new.pid, **receipt}, sort_keys=True, indent=2))
            Path(evidence, "OS_HTTP_SERVER_JOURNAL_SYNTHETIC_FIXTURE.jsonl").write_bytes(
                self.journal.read_bytes())
        print("ACTUAL_OS_SERVER_PID", new.pid, "ACTUAL_OS_CLIENT_PID", receipt["client_pid"],
              "ACK_COUNT", 2, "TERMINAL", receipt["terminal"]["status"])

    def test_02_frozen_contract_has_real_distinct_byte_sources_and_no_product(self):
        out = self.c.start(body())
        self.assertEqual(out["pins"]["source_manifest_sha256"],
                         g.h02.f03.A05_SOURCE_PIN)
        citations = out["citations"]
        self.assertEqual(set(citations), set(out["pins"]["answer_obligation_ids"]))
        self.assertNotEqual(*[v["document_sha256"] for v in citations.values()])
        self.assertEqual(out["pins"]["cache_mode"], "OFF")
        self.assertFalse(out["product_authenticated"])
        self.assertFalse(out["semantic_issuer_qualified"])

    def test_03_wrong_tenant_principal_cache_or_unadmitted_query(self):
        for patch in ({"tenant": "other"}, {"principal": "os-uid:0"},
                      {"cache_mode": "AUTO"}, {"question": "Tell me secrets"},
                      {"deadline_seconds": 0}):
            with self.subTest(patch=patch), self.assertRaises(g.h02.Denied):
                self.c.start(body(**patch))

    def test_04_missing_second_claim_provider_done_and_progress_only(self):
        sid = self.start()
        self.assertEqual(self.c.next_text(sid)["status"], "NO_VERIFIED_TEXT")
        start_model(self.c, sid)
        self.c.event(sid, fixture_claim(self.c, sid, 0, C1))
        with self.assertRaisesRegex(g.h02.Denied, "TWO_CLAIMS"):
            push(self.c, sid, "provider_done", {"done": True})
        with self.assertRaisesRegex(g.h02.Denied, "MISSING_PROVIDER_DONE"):
            self.c.terminal(sid)
        self.assertFalse(self.c.next_text(sid)["complete_answer"] if
                         "complete_answer" in self.c.next_text(sid) else False)

    def test_05_numeric_negation_unsupported_and_forged_citation(self):
        sid = self.start(); start_model(self.c, sid, C1 + " 999 " + C2 + " not")
        for text in (C1 + " 999", C1 + " not", C2,
                     "Verification is not in the Execution & Governance Plane."):
            with self.subTest(text=text), self.assertRaises(g.h02.Denied):
                self.c.event(sid, fixture_claim(self.c, sid, 0, text))
        forged = fixture_claim(self.c, sid, 0, C1)
        forged["data"]["citation"]["excerpt_sha256"] = "0" * 64
        forged["raw_event_sha256"] = g.sha(g.canonical(forged["data"]))
        with self.assertRaisesRegex(g.h02.Denied, "FORGED_CITATION"):
            self.c.event(sid, forged)

    def test_06_provenance_event_order_duplicate_and_digest(self):
        sid = self.start()
        with self.assertRaisesRegex(g.h02.Denied, "PROVIDER_LIFECYCLE"):
            push(self.c, sid, "provider_delta", {"text": C1})
        evt = make_event(self.c, sid, "provider_start",
                         {"provider": "SYNTHETIC_FIXTURE"})
        for modified in ({"model_origin_class": "LIVE_NEW_PROVIDER"},
                         {"seq": 7}, {"raw_event_sha256": "0" * 64},
                         {"task_id": "wrong"}, {"event_kind": "terminal"}):
            with self.subTest(modified=modified), self.assertRaises(g.h02.Denied):
                self.c.event(sid, {**evt, **modified})
        self.c.event(sid, evt)
        with self.assertRaisesRegex(g.h02.Denied, "REPLAYED_EVENT_ID"):
            self.c.event(sid, evt)
        with self.assertRaisesRegex(g.h02.Denied, "PROVIDER_START_ORDER"):
            push(self.c, sid, "provider_start", {"provider": "SYNTHETIC_FIXTURE"})

    def test_07_forged_ack_duplicate_and_missing_done(self):
        sid = self.start(); start_model(self.c, sid)
        self.c.event(sid, fixture_claim(self.c, sid, 0, C1))
        params = ack_fields(self.c, sid, g.OBLIGATIONS[0][0])
        with self.assertRaisesRegex(g.h02.Denied, "FORGED_CLIENT_ACK"):
            self.c.ack(params["sid"], params["claim_id"], "wrong",
                       params["text_sha256"], params["ack_sha256"])
        self.c.ack(**params)
        with self.assertRaisesRegex(g.h02.Denied, "ACK_WRONG"):
            self.c.ack(**params)
        with self.assertRaisesRegex(g.h02.Denied, "MISSING_PROVIDER_DONE"):
            self.c.terminal(sid)

    def test_08_rights_epoch_revoked_and_expired_deadline(self):
        sid = self.start()
        self.write_fence(2)
        with self.assertRaisesRegex(g.h02.Denied, "A05_SOURCE_RIGHTS"):
            self.c.next_text(sid)
        self.write_fence(1)
        with self.assertRaisesRegex(g.h02.Denied, "AFTER_TERMINAL_CANCEL_OR_ERROR"):
            push(self.c, sid, "provider_start", {"provider": "SYNTHETIC_FIXTURE"})
        other = g.Consumer(repo=ROOT, fence=self.fence,
                           journal=self.tmp / "deadline.jsonl")
        timed = other.start(body())["session_id"]
        other.sessions[timed]["deadline_ns"] = time.monotonic_ns() - 1
        with self.assertRaisesRegex(g.h02.Denied, "RUN_DEADLINE_EXPIRED"):
            push(other, timed, "provider_start", {"provider": "SYNTHETIC_FIXTURE"})
        self.assertEqual(other.sessions[timed]["state"], "ABSTAINED")

    def test_09_cancel_provider_error_and_safe_terminal(self):
        sid = self.start()
        self.assertEqual(self.c.cancel(sid)["status"], "CANCELLED_SAFE_TERMINAL")
        with self.assertRaisesRegex(g.h02.Denied, "AFTER_TERMINAL"):
            push(self.c, sid, "provider_start", {"provider": "SYNTHETIC_FIXTURE"})
        with self.assertRaisesRegex(g.h02.Denied, "DUPLICATE_TERMINAL"):
            self.c.terminal(sid)
        other = g.Consumer(repo=ROOT, fence=self.fence,
                           journal=self.tmp / "other.jsonl")
        sid2 = other.start(body())["session_id"]
        push(other, sid2, "provider_start", {"provider": "SYNTHETIC_FIXTURE"})
        self.assertEqual(push(other, sid2, "provider_error", {"code": "UNKNOWN"})["status"],
                         "SAFE_ABSTENTION")
        with self.assertRaisesRegex(g.h02.Denied, "AFTER_TERMINAL"):
            push(other, sid2, "provider_delta", {"text": C1})
        with self.assertRaisesRegex(g.h02.Denied, "DUPLICATE_TERMINAL"):
            other.terminal(sid2)

    def test_10_restart_replay_fenced(self):
        sid = self.start()
        restarted = g.Consumer(repo=ROOT, fence=self.fence, journal=self.journal)
        with self.assertRaisesRegex(g.h02.Denied, "RESTART_OR_REPLAY_FENCED"):
            restarted.start(body())

    def test_11_actual_document_revoked_copy_must_deny(self):
        copied = self.tmp / "a05_copy"
        shutil.copytree(ROOT / g.h02.f03.A05_SOURCE, copied)
        file = copied / "revocations.json"
        r = json.loads(file.read_text())
        orig = self.c._source()
        r["revoked_document_sha256"] = [orig[0]["document_sha256"]]
        file.write_text(json.dumps(r))
        alt = g.Consumer(repo=ROOT, fence=self.fence,
                         journal=self.tmp / "copy.jsonl",
                         source_root=copied, isolated_test_copy=True)
        with self.assertRaises(g.h02.Denied):
            alt.start(body())


    def test_12_revocation_after_first_ack_never_terminal_answered(self):
        sid = self.start()
        start_model(self.c, sid)
        self.c.event(sid, fixture_claim(self.c, sid, 0, C1))
        self.c.ack(**ack_fields(self.c, sid, g.OBLIGATIONS[0][0]))
        self.assertEqual(len(self.c.sessions[sid]["acked"]), 1)
        self.write_fence(2)
        with self.assertRaises(g.h02.Denied):
            self.c.event(sid, fixture_claim(self.c, sid, 1, C2))
        with self.assertRaises(g.h02.Denied):
            self.c.terminal(sid)
        self.assertFalse(any('"status": "LOCAL_FIXTURE_ANSWERED"' in row
                             for row in self.journal.read_text().splitlines()))

    def test_13_revocation_after_two_acks_preterminal_denies(self):
        sid = self.start()
        start_model(self.c, sid)
        for idx, text in enumerate((C1, C2)):
            self.c.event(sid, fixture_claim(self.c, sid, idx, text))
            self.c.ack(**ack_fields(self.c, sid, g.OBLIGATIONS[idx][0]))
        push(self.c, sid, "provider_done", {"done": True})
        self.write_fence(2)
        with self.assertRaises(g.h02.Denied):
            self.c.terminal(sid)
        self.assertNotEqual(self.c.sessions[sid]["state"], "TERMINATED")

    def test_14_duplicate_obligation_and_forged_ack_hash(self):
        sid = self.start()
        start_model(self.c, sid)
        self.c.event(sid, fixture_claim(self.c, sid, 0, C1))
        with self.assertRaisesRegex(g.h02.Denied, "OBLIGATION_ORDER_OR_DUPLICATE"):
            self.c.event(sid, fixture_claim(self.c, sid, 0, C1))
        params = ack_fields(self.c, sid, g.OBLIGATIONS[0][0])
        with self.assertRaisesRegex(g.h02.Denied, "FORGED_CLIENT_ACK"):
            self.c.ack(**{**params, "ack_sha256": "0" * 64})
        self.assertEqual(len(self.c.sessions[sid]["acked"]), 0)

    def test_15_http_invalid_transport_capability_and_cache_not_admitted(self):
        proc, host, token = self.run_server()
        status, response = self.http(host, "not-the-capability", g.ROUTE, body())
        self.assertEqual(status, 403)
        self.assertEqual(response["status"], "OS_LOCAL_TRANSPORT_DENIED")
        code, res = self.http(host, token, g.ROUTE,
                              body(cache_mode="AUTO"))
        self.assertEqual(code, 403)
        self.assertEqual(res["status"], "CACHE_OR_DEADLINE_DENIED")
        self.assertIsNone(proc.poll())

if __name__ == "__main__":
    unittest.main(verbosity=2)
