"""Signed-gated direct Workers AI SSE adapter negative/positive parser tests.

Fixture events are synthetics for parser only; no inference about external
signer identity, genuine Provider delivery, Product C1 PASS or billing.
"""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_formal_workers_ai_sse as m
import m27_c1_genuine_native_generation_seam as formal

def line(text="",*,model=m.MODEL,finish=None):
    return b"data: "+json.dumps({"model":model,"choices":[{
      "delta":{"content":text}, "finish_reason":finish
    }]}).encode()+b"\n"
def complete():
    return [line("Verification is in the Execution & Governance Plane.\n"),
            line("PolicyEngine decides deterministic enforcement."),
            line(finish="stop"),b"data: [DONE]\n"]
def parse(source):
    audit=[]
    events=list(m.decode_sse(source,model=m.MODEL,request_id="REQ-A05-01",
                             audit=audit.append))
    return audit,events

class WireAdmission(unittest.TestCase):
    def test_01_accept_only_real_direct_cloudflare_origin(self):
        yes="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions"
        self.assertTrue(m.approved_direct_url(yes))
        for url in [
          "https://gateway.ai.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
          "https://api.cloudflare.com:444/client/v4/accounts/abc123456/ai/v1/chat/completions",
          "http://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
          yes+"?token=leak",yes+"#sig",yes+"/../modify",
          "https://api.cloudflare.com.evil.io/client/v4/accounts/abc123456/ai/v1/chat/completions",
          "https://u:p@api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
          "https://api.cloudflare.com/client/v4/accounts/x/ai/v1/chat/completions"
        ]:
            with self.subTest(url=url):
                self.assertFalse(m.approved_direct_url(url))

    def test_02_actual_wire_semantics_to_internal_normalized_events(self):
        audit,events=parse(complete())
        self.assertEqual([e["kind"] for _,e in events],["delta","delta","done"])
        self.assertEqual(events[0][1]["model"],m.MODEL)
        self.assertEqual(events[2][1]["text"],"")
        for raw,event in events:
            self.assertEqual(json.loads(raw),event)
        self.assertTrue(all(e["origin"]=="CLOUDFLARE_ORIGINAL_SSE_WIRE"
                            for e in audit))
        self.assertEqual([e["meaning"] for e in audit],
          ["LIVE_NEW_PROVIDER_DELTA","LIVE_NEW_PROVIDER_DELTA",
           "REAL_PROVIDER_FINISH_STOP","REAL_PROVIDER_DONE_FRAME"])
        self.assertEqual(formal.PROVIDER_SSE_ABI,m.ABI)
        self.assertIsNone(formal.TRUST_ROOT_MANIFEST_SHA256)

    def test_03_no_fake_done_without_real_upstream_done(self):
        with self.assertRaisesRegex(m.WireRejected,"INCOMPLETE"):
            parse(complete()[:-1])
        with self.assertRaisesRegex(m.WireRejected,"EARLY"):
            parse([line("partial text"),b"data: [DONE]\n"])
        with self.assertRaisesRegex(m.WireRejected,"EARLY"):
            parse([line(finish="stop"),b"data: [DONE]\n"])

    def test_04_reject_wrong_model_and_missing_attestation(self):
        with self.assertRaisesRegex(m.WireRejected,"MODEL_MISMATCH"):
            parse([line("wrong",model="GPT-FAKE")]+complete())
        with self.assertRaisesRegex(m.WireRejected,"MODEL_UNATTESTED"):
            parse([line("must reject",model=None)]+complete())

    def test_05_reject_unsafe_completion(self):
        for finish in ["length","tool_calls","content_filter","other"]:
            with self.subTest(finish=finish):
                with self.assertRaisesRegex(m.WireRejected,"NONSTOP"):
                    parse([line("hello"),line(finish=finish),b"data: [DONE]\n"])

    def test_06_reject_invalid_shape_and_truncated_json(self):
        with self.assertRaisesRegex(m.WireRejected,"INVALID_JSON"):
            parse([b"data: {x\n"]+complete())
        with self.assertRaisesRegex(m.WireRejected,"CHOICES_INVALID"):
            parse([b'data: {"model":"'+m.MODEL.encode()+b'","choices":[]}\n']+complete())
        with self.assertRaisesRegex(m.WireRejected,"DELTA_NOT_OBJECT"):
            parse([b'data: {"model":"'+m.MODEL.encode()+b'","choices":[{"delta":null}]}\n']+complete())

    def test_07_reject_event_overbudget_and_oversized_delta(self):
        with self.assertRaisesRegex(m.WireRejected,"TOTAL_BUDGET"):
            parse([b"data: "+b"x"*m.MAX_RAW_TOTAL+b"\n"]+complete())
        with self.assertRaisesRegex(m.WireRejected,"OVERSIZED"):
            parse([line("x"*(m.MAX_DELTA_CHARS+1))]+complete())
        with self.assertRaisesRegex(m.WireRejected,"FRAME_BUDGET"):
            parse([line()]*(m.MAX_EVENTS+1)+complete())

    def test_08_require_actual_signed_authority_before_any_formal_provider(self):
        self.assertIsNone(formal.TRUST_ROOT_MANIFEST_SHA256)
        self.assertIn("PROVIDER_SSE_ABI",Path(formal.__file__).read_text())
        self.assertNotEqual(formal.PROVIDER_ABI,formal.PROVIDER_SSE_ABI)

if __name__=="__main__":unittest.main()
