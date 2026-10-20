"""Offline HTTPX simulation of the actual VM's bounded Cloudflare wire.

No request to Cloudflare is ever made by these tests.
"""
import contextlib,io,json,os,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_m26_provider_parity_nonprod as p
PROMPT="Answer the two owner-firstparty A05 source-bound requirements: Verification belongs to Governance and PolicyEngine decides enforcement."
MODEL=p.MODEL

def frame(t="",finish=None,model=MODEL):
    return "data: "+json.dumps({"model":model,"choices":[{
        "delta":{"content":t},"finish_reason":finish}]})
def good():
    return [frame("Verification is in the Execution & Governance Plane.\n"),
            frame("PolicyEngine decides deterministic enforcement."),
            frame(finish="stop"),"data: [DONE]"]
def usage():
    return "data: "+json.dumps({"model":MODEL,"choices":[],
      "usage":{"prompt_tokens":12,"completion_tokens":21,"total_tokens":33}})
def simulate(lines):
    class Response:
        status_code=200
        headers={"content-type":"text/event-stream"}
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_lines(self):return iter(lines)
    class FakeHTTPX(types.ModuleType):
        TimeoutException=TimeoutError
        NetworkError=ConnectionError
        def Timeout(self,*a,**k):return None
        def stream(self,*a,**kw):return Response()
    mock=FakeHTTPX("httpx")
    outputs=io.StringIO()
    env={"CLOUDFLARE_ACCOUNT_ID":"acct12345678",
         "CLOUDFLARE_AI_TOKEN":"SYNTHETIC_TEST_NOT_A_KEY"}
    with patch.dict(os.environ,env),patch.dict(sys.modules,{"httpx":mock}),\
         patch.object(sys,"stdin",io.StringIO(json.dumps(PROMPT)+"\n")),\
         contextlib.redirect_stdout(outputs):
        exec(p.VM_STREAM_SCRIPT,{"__name__":"__synthetic_test__"})
    return [json.loads(l) for l in outputs.getvalue().splitlines()]

class WireDoesNotReuseOldUnsafeEnd(unittest.TestCase):
    def test_01_normal_stopped_and_eof_done(self):
        items=simulate(good())
        self.assertEqual(items[-1]["event"],"stream_end")
        self.assertTrue(items[-1]["provider_done"])
        self.assertEqual(sum(x["event"]=="delta" for x in items),2)
        self.assertFalse(any(x["event"]=="error" for x in items))
    def test_02_one_usage_only_postfinish_is_safe(self):
        x=simulate(good()[:-1]+[usage()]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(y["event"]=="provider_done" for y in x),1)
    def test_03_duplicate_done_denied(self):
        x=simulate(good()+["data: [DONE]"])
        self.assertNotIn("provider_done",[y["event"] for y in x])
        self.assertTrue(any(y.get("category")=="CLOUDFLARE_FRAME_AFTER_DONE_DENIED" for y in x))
    def test_04_late_text_after_done_denied(self):
        x=simulate(good()+[frame("LATE FORGED CLAIM")])
        self.assertNotIn("stream_end",[y["event"] for y in x])
    def test_05_late_malformed_json_after_done_denied(self):
        x=simulate(good()+["data: {BROKEN"])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_06_late_text_before_done_denied(self):
        x=simulate(good()[:-1]+[frame("LATE FORGED CLAIM")]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
        self.assertTrue(any(y.get("category")=="CLOUDFLARE_POSTFINISH_DATA_DENIED" for y in x))
    def test_07_duplicated_usage_denied(self):
        x=simulate(good()[:-1]+[usage(),usage()]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_08_early_done_denied(self):
        x=simulate([frame("partial"),"data: [DONE]"])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_09_missing_terminal_denied(self):
        x=simulate(good()[:-1])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_10_wrong_identity_denied(self):
        x=simulate([frame("bad",model="totally-wrong")]+good())
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_11_no_acceptance_after_event_budget_overflow_even_if_done_seen(self):
        x=simulate(good()+[": harmless keepalive"]*260)
        self.assertNotIn("provider_done",[y["event"] for y in x])
        self.assertTrue(any(y.get("category")=="CLOUDFLARE_EVENT_BUDGET" for y in x))
    def test_12_one_empty_stop_metadata_frame_after_finish(self):
        x=simulate(good()[:-1]+[frame("",finish="stop")]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(y["event"]=="delta" for y in x),2)
        self.assertFalse(any(y["event"]=="error" for y in x))
    def test_13_empty_control_plus_usage_once_but_never_new_text(self):
        x=simulate(good()[:-1]+[frame("",finish="stop"),usage()]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertNotIn("LATE",json.dumps(x))
    def test_14_two_empty_control_frames_deny(self):
        x=simulate(good()[:-1]+[frame("",finish="stop"),frame("",finish="stop")]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_15_nonempty_postfinish_delta_even_if_stop_is_rejected(self):
        x=simulate(good()[:-1]+[frame("LATE FORGED CLAIM",finish="stop")]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_16_other_role_or_malformed_terminal_control_is_rejected(self):
        tail="data: "+json.dumps({"model":MODEL,"choices":[{
          "delta":{"role":"system"},"finish_reason":"stop","index":0}]})
        x=simulate(good()[:-1]+[tail]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
if __name__=="__main__":unittest.main()
