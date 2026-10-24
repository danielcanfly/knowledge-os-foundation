"""Exercise actual Cloudflare firstparty VM SSE code with mocked HTTP transport.

No network, credentials, independent issuer, or Product promotion.
Failures expose only static safe branch codes, never provider text.
"""
import contextlib,io,json,os,sys,types,unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/knowledge_engine"))
from m27_c1_m26_provider_parity_nonprod import VM_STREAM_SCRIPT

PROMPT="Which A05 source documents describe the execution and governance plane and deterministic PolicyEngine enforcement?"

class _Response:
    status_code=200
    headers={"content-type":"text/event-stream"}
    def __init__(self,frames): self.frames=frames
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def iter_lines(self):return iter(self.frames)

def data(payload):
    return "data: "+json.dumps(payload,separators=(",",":"))

START={"model":"@cf/openai/gpt-oss-120b","choices":[{"index":0,"delta":{"content":"Verification is in the Execution and Governance Plane.\n"},"finish_reason":None}]}
STOP={"model":"@cf/openai/gpt-oss-120b","choices":[{"index":0,"delta":{"content":""},"finish_reason":"stop"}]}
USAGE={"model":"@cf/openai/gpt-oss-120b","choices":[],"usage":{"prompt_tokens":50,"completion_tokens":20,"total_tokens":70}}

def replay(extra):
    out=io.StringIO()
    fake=types.ModuleType("httpx")
    fake.Timeout=lambda *args,**kwargs:object()
    fake.TimeoutException=type("TimeoutException",(Exception,),{})
    fake.NetworkError=type("NetworkError",(Exception,),{})
    fake.stream=lambda *args,**kwargs:_Response([data(START),data(STOP)]+[data(x) for x in extra]+["data: [DONE]"])
    with patch.dict(sys.modules,{"httpx":fake}),patch.dict(os.environ,{"CLOUDFLARE_ACCOUNT_ID":"LOCAL_TEST_NONSECRET","CLOUDFLARE_AI_TOKEN":"LOCAL_TEST_NONSECRET"}),patch.object(sys,"stdin",io.StringIO(json.dumps(PROMPT)+"\n")),contextlib.redirect_stdout(out):
        exec(compile(VM_STREAM_SCRIPT,"<offline_cloudflare_vm_script>","exec"),{"__name__":"__main__"})
    return [json.loads(line) for line in out.getvalue().splitlines()]

class CloudflarePostfinishReasonCodes(unittest.TestCase):
    def denied(self,frames,reason):
        ev=replay(frames)
        diag=[x for x in ev if x["event"]=="stream_diagnostic" and "rejected_tail_shape" in x]
        self.assertEqual(len(diag),1)
        self.assertEqual(diag[0].get("rejected_tail_reason"),reason)
        self.assertEqual([x["category"] for x in ev if x["event"]=="error" and x["category"]=="CLOUDFLARE_POSTFINISH_DATA_DENIED"],["CLOUDFLARE_POSTFINISH_DATA_DENIED"])
        self.assertFalse(any(x["event"]=="provider_done" for x in ev))
        self.assertNotIn("LOCAL_TEST_NONSECRET",json.dumps(ev))
        self.assertNotIn("Verification is",json.dumps(diag))
    def test_postfinish_material_text_reason(self):
        self.denied([{"choices":[{"index":0,"delta":{"content":"late material"},"finish_reason":None}]}],"TAIL_MATERIAL_OR_INVALID_CHOICE")
    def test_postfinish_unrecognized_top_level_reason(self):
        self.denied([{"choices":[],"new_opaque_content":{"text":"forbidden"}}],"TAIL_UNKNOWN_TOP_FIELDS")
    def test_postfinish_replayed_usage_reason(self):
        self.denied([USAGE,USAGE],"TAIL_USAGE_DUPLICATE_OR_INVALID")
    def test_normal_finish_done_remains_accepted(self):
        ev=replay([])
        self.assertEqual(sum(x["event"]=="provider_done" for x in ev),1)
        self.assertFalse(any(x["event"]=="error" for x in ev))
if __name__=="__main__":unittest.main()
