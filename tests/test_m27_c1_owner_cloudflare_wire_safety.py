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
def native_tail(response="",usage_value=None):
    if usage_value is None:usage_value={"prompt_tokens":12,"completion_tokens":21,"total_tokens":33}
    return "data: "+json.dumps({"response":response,"usage":usage_value})
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
    def test_17_cloudflare_native_empty_response_usage_tail(self):
        x=simulate(good()[:-1]+[native_tail()]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(y["event"]=="delta" for y in x),2)
        self.assertEqual(sum(y["event"]=="provider_done" for y in x),1)
    def test_18_native_nonempty_response_refused(self):
        x=simulate(good()[:-1]+[native_tail("FORGED CLAIM")]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_19_two_native_tails_refused(self):
        x=simulate(good()[:-1]+[native_tail(),native_tail()]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_20_native_tail_after_done_refused(self):
        x=simulate(good()+[native_tail()])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_21_single_empty_heartbeat_postfinish_only(self):
        heartbeat="data: "+json.dumps({"choices":[]})
        x=simulate(good()[:-1]+[heartbeat,native_tail()]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(y["event"]=="delta" for y in x),2)
    def test_22_repeated_empty_heartbeat_denied(self):
        heartbeat="data: "+json.dumps({"choices":[]})
        x=simulate(good()[:-1]+[heartbeat,heartbeat]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_23_exact_repeated_response_tail_is_nonanswer_metadata(self):
        emitted="Verification is in the Execution & Governance Plane.\n"+"PolicyEngine decides deterministic enforcement."
        x=simulate(good()[:-1]+[native_tail(emitted)]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(y["event"]=="delta" for y in x),2)
    def test_24_modified_last_claim_is_rejected(self):
        emitted="Verification is in the Execution & Governance Plane.\n"+"PolicyEngine decides NEW policy."
        x=simulate(good()[:-1]+[native_tail(emitted)]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_25_duplicated_exact_repeated_response_is_rejected(self):
        emitted="Verification is in the Execution & Governance Plane.\n"+"PolicyEngine decides deterministic enforcement."
        x=simulate(good()[:-1]+[native_tail(emitted),native_tail(emitted)]+good()[-1:])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_26_repeated_response_without_done_is_rejected(self):
        emitted="Verification is in the Execution & Governance Plane.\n"+"PolicyEngine decides deterministic enforcement."
        x=simulate(good()[:-1]+[native_tail(emitted)])
        self.assertNotIn("provider_done",[y["event"] for y in x])
    def test_27_accounting_on_final_empty_choice_with_repeat_stop(self):
        final="data: "+json.dumps({"model":MODEL,"choices":[{
            "index":0,"delta":{"role":"assistant","content":""},
            "finish_reason":"stop","native_finish_reason":"stop"}],
            "usage":{"prompt_tokens":12,"completion_tokens":21,
                     "total_tokens":33,"neurons":0.12}})
        x=simulate(good()[:-1]+[final]+good()[-1:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(v["event"]=="delta" for v in x),2)
        self.assertEqual(sum(v["event"]=="provider_done" for v in x),1)
    def test_28_final_choice_with_usage_cannot_append_new_text(self):
        final="data: "+json.dumps({"model":MODEL,"choices":[{
            "index":0,"delta":{"content":"LATE MALICIOUS WORDS"},
            "finish_reason":"stop"}],
            "usage":{"prompt_tokens":12,"completion_tokens":21,
                     "total_tokens":33}})
        x=simulate(good()[:-1]+[final]+good()[-1:])
        self.assertNotIn("provider_done",[v["event"] for v in x])
    def test_29_final_choice_with_wrong_native_finish_rejected(self):
        final="data: "+json.dumps({"model":MODEL,"choices":[{
            "index":0,"delta":{"content":""},
            "finish_reason":"stop","native_finish_reason":"length"}],
            "usage":{"prompt_tokens":12,"completion_tokens":21,
                     "total_tokens":33}})
        x=simulate(good()[:-1]+[final]+good()[-1:])
        self.assertNotIn("provider_done",[v["event"] for v in x])
    def test_30_duplicate_final_choice_with_usage_rejected(self):
        final="data: "+json.dumps({"model":MODEL,"choices":[{
            "index":0,"delta":{"content":""},"finish_reason":"stop"}],
            "usage":{"prompt_tokens":12,"completion_tokens":21,
                     "total_tokens":33}})
        x=simulate(good()[:-1]+[final,final]+good()[-1:])
        self.assertNotIn("provider_done",[v["event"] for v in x])
    def test_31_missing_done_even_with_valid_final_usage_denied(self):
        final="data: "+json.dumps({"model":MODEL,"choices":[{
            "index":0,"delta":{"content":""},"finish_reason":"stop"}],
            "usage":{"prompt_tokens":12,"completion_tokens":21,
                     "total_tokens":33}})
        x=simulate(good()[:-1]+[final])
        self.assertNotIn("provider_done",[v["event"] for v in x])
    def test_32_denied_tail_provides_nonsecret_structure_not_content(self):
        private="PRIVATE_MODEL_RESPONSE_NEVER_LOG_789"
        injected_key="PRIVATE_UNEXPECTED_KEY_NEVER_LOG_789"
        final="data: "+json.dumps({"model":MODEL,
            "choices":[{"index":0,
              "delta":{"content":private,"reasoning_content":"PRIVATE_THOUGHTS"},
              "finish_reason":"stop"}],
            injected_key:"PRIVATE_VALUE"})
        x=simulate(good()[:-1]+[final]+good()[-1:])
        self.assertNotIn("provider_done",[v["event"] for v in x])
        diag=[v for v in x if v["event"]=="stream_diagnostic" and
              "rejected_tail_shape" in v]
        self.assertEqual(len(diag),1)
        self.assertEqual(diag[0]["rejected_tail_shape"]["content_state"],"nonempty")
        self.assertEqual(diag[0]["rejected_tail_shape"]["top_unknown_count"],1)
        self.assertEqual(len(diag[0]["rejected_tail_wire_sha256"]),64)
        self.assertNotIn(private,json.dumps(x))
        self.assertNotIn(injected_key,json.dumps(x))
        self.assertNotIn("PRIVATE_THOUGHTS",json.dumps(x))
    def test_33_success_has_no_rejection_fingerprint(self):
        x=simulate(good())
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertFalse(any("rejected_tail_shape" in v for v in x))
    def test_34_prefinish_heartbeat_after_real_deltas_completes(self):
        text=good()[:2]
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[]})
        x=simulate(text+[heartbeat]+good()[2:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(i["event"]=="delta" for i in x),2)
        self.assertEqual(sum(i["event"]=="provider_done" for i in x),1)
    def test_35_prefinish_heartbeat_with_bounded_usage_completes(self):
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[],
          "usage":{"prompt_tokens":12,"completion_tokens":21,"total_tokens":33}})
        x=simulate(good()[:2]+[heartbeat]+good()[2:])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(i["event"]=="delta" for i in x),2)
    def test_36_heartbeat_before_material_text_cannot_attest(self):
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[]})
        x=simulate([frame("",model=MODEL),heartbeat]+good())
        self.assertNotIn("provider_done",[i["event"] for i in x])
        self.assertTrue(any(i.get("category")==
                "CLOUDFLARE_PRETERMINAL_HEARTBEAT_DENIED" for i in x))
    def test_37_duplicate_prefinish_heartbeat_denied(self):
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[]})
        x=simulate(good()[:2]+[heartbeat,heartbeat]+good()[2:])
        self.assertNotIn("provider_done",[i["event"] for i in x])
    def test_38_heartbeat_with_unknown_fields_denied(self):
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[],
          "unknown_extra":"PRIVATE_UNTRUSTED_FIELD"})
        x=simulate(good()[:2]+[heartbeat]+good()[2:])
        self.assertNotIn("provider_done",[i["event"] for i in x])
        self.assertNotIn("PRIVATE_UNTRUSTED_FIELD",json.dumps(x))
    def test_39_heartbeat_with_malformed_usage_denied(self):
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[],
          "usage":{"prompt_tokens":-1,"completion_tokens":10,
                   "total_tokens":9}})
        x=simulate(good()[:2]+[heartbeat]+good()[2:])
        self.assertNotIn("provider_done",[i["event"] for i in x])
    def test_40_heartbeat_does_not_replace_required_stop(self):
        heartbeat="data: "+json.dumps({"model":MODEL,"choices":[]})
        x=simulate(good()[:2]+[heartbeat,"data: [DONE]"])
        self.assertNotIn("provider_done",[i["event"] for i in x])
        self.assertTrue(any(i.get("category")=="CLOUDFLARE_PREMATURE_DONE_DENIED"
                            for i in x))
    def test_41_empty_reasoning_placeholder_after_stop_is_not_late_text(self):
        tail={"model":MODEL,"choices":[{"index":0,
              "delta":{"content":"","reasoning_content":None,"reasoning":""},
              "finish_reason":"stop"}],
              "usage":{"prompt_tokens":12,"completion_tokens":21,"total_tokens":33}}
        x=simulate(good()[:-1]+["data: "+json.dumps(tail),"data: [DONE]"])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertEqual(sum(i["event"]=="delta" for i in x),2)
    def test_42_bounded_opaque_openai_obfuscation_is_metadata_only(self):
        tail={"model":MODEL,"choices":[],
              "usage":{"prompt_tokens":12,"completion_tokens":21,"total_tokens":33},
              "obfuscation":"p9x6v3"}
        x=simulate(good()[:-1]+["data: "+json.dumps(tail),"data: [DONE]"])
        self.assertEqual(x[-1]["event"],"stream_end")
        self.assertNotIn("p9x6v3",json.dumps(x))
    def test_43_nonempty_reasoning_after_stop_must_failclosed_and_not_leak(self):
        tail={"model":MODEL,"choices":[{"index":0,
             "delta":{"content":"","reasoning_content":"SECRET PRIVATE CHAIN"},
             "finish_reason":"stop"}]}
        x=simulate(good()[:-1]+["data: "+json.dumps(tail),"data: [DONE]"])
        self.assertNotIn("provider_done",[i["event"] for i in x])
        self.assertTrue(any(i.get("category")=="CLOUDFLARE_POSTFINISH_DATA_DENIED" for i in x))
        self.assertNotIn("SECRET PRIVATE CHAIN",json.dumps(x))
    def test_44_nonstring_or_oversized_obfuscation_denied(self):
        for pad in ({"payload":"FORGED"},None,"x"*513,"abc\nmalformed"):
            with self.subTest(pad=type(pad).__name__):
                tail={"model":MODEL,"choices":[],"obfuscation":pad,
                     "usage":{"prompt_tokens":12,"completion_tokens":21,"total_tokens":33}}
                x=simulate(good()[:-1]+["data: "+json.dumps(tail),"data: [DONE]"])
                self.assertNotIn("provider_done",[i["event"] for i in x])
    def test_45_unknown_extra_after_stop_still_denied(self):
        tail={"model":MODEL,"choices":[],"untrusted_arbitrary":"UNKNOWN LATE ANSWER",
              "usage":{"prompt_tokens":12,"completion_tokens":21,"total_tokens":33}}
        x=simulate(good()[:-1]+["data: "+json.dumps(tail),"data: [DONE]"])
        self.assertNotIn("provider_done",[i["event"] for i in x])
        self.assertNotIn("UNKNOWN LATE ANSWER",json.dumps(x))
    def test_46_late_tool_calls_still_denied(self):
        tail={"model":MODEL,"choices":[{"index":0,"finish_reason":"stop",
                "delta":{"content":"","tool_calls":[{"id":"forged"}]}}]}
        x=simulate(good()[:-1]+["data: "+json.dumps(tail),"data: [DONE]"])
        self.assertNotIn("provider_done",[i["event"] for i in x])
    def test_47_bounded_metadata_cannot_substitute_done(self):
        tail={"model":MODEL,"choices":[{"index":0,
              "delta":{"content":"","reasoning_content":None},"finish_reason":"stop"}],
              "obfuscation":"p9x6v3"}
        x=simulate(good()[:-1]+["data: "+json.dumps(tail)])
        self.assertNotIn("provider_done",[i["event"] for i in x])
if __name__=="__main__":unittest.main()
