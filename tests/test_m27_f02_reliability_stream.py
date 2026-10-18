"""Independent stdlib protocol tests. All provider events are fixtures, never live proof."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

P=Path(__file__).resolve().parents[1]/"src/knowledge_engine/m27_f02_reliability_stream.py"
spec=importlib.util.spec_from_file_location("f02_stage_reliability",P)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
CACHE="The semantic answer cache is initially OFF in Nonprod."
TOOL="Remote Desktop Commander is first for engineering on MacBook."
def fake(*chunks, done=True, identity=True, repeat_start=False):
    yield {"event":"request_start","model":s.b1.MODEL}
    if identity:yield {"event":"model_identity","model":s.b1.MODEL,"model_match":True}
    for c in chunks:
        yield {"event":"delta","text":c,"wall_ns":time.time_ns(),"monotonic_ns":time.monotonic_ns()}
    if repeat_start:yield {"event":"request_start","model":s.b1.MODEL}
    if done:
        yield {"event":"provider_done"}
        yield {"event":"stream_end","provider_done":True}
    else:yield {"event":"stream_end","provider_done":False}

class Reliability(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
    def exercise(self, generator, *, cancel=False, revoke_at=None, **kwargs):
        holder={}
        if revoke_at:
            def wrap():
                for ix,ev in enumerate(generator):
                    if ix==revoke_at:holder["server"].revoked=True
                    yield ev
            generator=wrap()
        srv=s.Server(self.folder,generator=lambda:generator,**kwargs)
        holder["server"]=srv
        worker=threading.Thread(target=srv.serve_forever,daemon=True);worker.start()
        try: result=s.client(srv.server_port,self.folder,cancel_after_first=cancel)
        finally:srv.shutdown();srv.server_close();worker.join(3)
        trace=[json.loads(x) for x in (self.folder/"server_vm_wire.jsonl").read_text().splitlines()]
        return result,trace
    def test_full_two_claim_early_client_ack_with_no_newlines(self):
        r,tr=self.exercise(fake(CACHE+TOOL))
        self.assertTrue(r["client_validated"],r["validation_failure"])
        self.assertEqual([r["receipts"][i]["ack_status"] for i in (1,2)],[200,200])
        self.assertLess(r["receipts"][1]["received_monotonic_ns"],r["receipts"][-1]["received_monotonic_ns"])
        self.assertEqual(r["receipts"][-1]["body"]["status"],"answered")
        self.assertEqual(len([e for e in tr if e["event"]=="claim_verified_and_sent"]),2)
    def test_split_delta_first_text_before_provider_done(self):
        r,tr=self.exercise(fake(CACHE[:18],CACHE[18:],TOOL[:23],TOOL[23:]))
        self.assertTrue(r["client_validated"],r["validation_failure"])
        wire=[i for i,e in enumerate(tr) if e["event"]=="vm_wire" and (e.get("provider_event") or {}).get("event")=="provider_done"]
        pub=[i for i,e in enumerate(tr) if e["event"]=="publish_answer_text"]
        self.assertEqual(len(wire),1)
        self.assertTrue(all(i<wire[0] for i in pub))
    def test_strict_unsupported_claim_not_published(self):
        r,tr=self.exercise(fake(CACHE+"Remote Desktop Commander is PRIMARY on MacBook."))
        self.assertFalse(r["client_validated"])
        self.assertEqual(r["receipts"][-1]["body"]["status"],"partial_terminated")
    def test_extra_unsafe_claim_tail_aborts_not_answered(self):
        r,tr=self.exercise(fake(CACHE+TOOL+"The semantic answer cache is ON in Production."))
        self.assertFalse(r["client_validated"])
        self.assertEqual(r["receipts"][-1]["body"]["status"],"partial_terminated")
        self.assertTrue(any(e["event"]=="fail_closed" and "unsupported_post_answer_tail" in e["reason"] for e in tr))
    def test_no_provider_done_fails_closed(self):
        r,_=self.exercise(fake(CACHE+TOOL,done=False))
        self.assertFalse(r["client_validated"])
        self.assertNotEqual(r["receipts"][-1]["body"]["status"],"answered")
    def test_spoofed_identity_prevents_claim(self):
        r,_=self.exercise(fake(CACHE+TOOL,identity=False))
        self.assertFalse(r["client_validated"])
        self.assertEqual(len([e for e in r["receipts"] if e["event"]=="answer_text"]),0)
    def test_second_provider_forbidden_after_first(self):
        r,tr=self.exercise(fake(CACHE+TOOL,repeat_start=True))
        self.assertFalse(r["client_validated"])
        self.assertTrue(any(e["event"]=="fail_closed" and "second_provider_start_disallowed" in e["reason"] for e in tr))
    def test_actual_http_cancel_after_first_ack(self):
        r,tr=self.exercise(fake(CACHE,TOOL),cancel=True)
        self.assertFalse(r["client_validated"])
        self.assertEqual(r["receipts"][1].get("cancel_status"),200)
        self.assertNotEqual(r["receipts"][-1]["body"]["status"],"answered")
        self.assertTrue(any(e["event"]=="cancel_request" and e["accepted"] for e in tr))
    def test_rights_revoke_after_first(self):
        # one generator event after the first ACK but before the second claim
        r,tr=self.exercise(fake(CACHE,TOOL),revoke_at=3)
        self.assertFalse(r["client_validated"])
        self.assertNotEqual(r["receipts"][-1]["body"]["status"],"answered")
    def test_acl_denied_preflight(self):
        r,_=self.exercise(fake(CACHE+TOOL),rights=False)
        self.assertFalse(r["client_validated"])
        self.assertFalse(any(e["event"]=="answer_text" for e in r["receipts"]))
    def test_paraphrase_true_and_false(self):
        b=s.source_bindings()
        self.assertTrue(s.verify_claim("All new engineering work is required to use Remote Desktop Commander first on MacBook.",b[1])["accepted"])
        self.assertFalse(s.verify_claim("The primary tool for engineering on MacBook is Remote Desktop Commander.",b[1])["accepted"])
        self.assertFalse(s.verify_claim("The semantic answer cache is permanently OFF in Nonprod.",b[0])["accepted"])
        self.assertFalse(s.verify_claim("The semantic answer cache is ON in Nonprod.",b[0])["accepted"])
    def test_revocation_between_second_ack_and_terminal(self):
        holder={}
        def gen():
            yield from fake(CACHE+TOOL,done=False)
            holder["server"].revoked=True
            yield {"event":"provider_done"}
            yield {"event":"stream_end","provider_done":True}
        srv=s.Server(self.folder,generator=gen)
        holder["server"]=srv
        th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
        try:r=s.client(srv.server_port,self.folder)
        finally:srv.shutdown();srv.server_close();th.join(3)
        self.assertFalse(r["client_validated"])
        self.assertNotEqual(r["receipts"][-1]["body"]["status"],"answered")
if __name__=="__main__":
    unittest.main(verbosity=2)
