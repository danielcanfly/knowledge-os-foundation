"""Native HTTPS transport delta: real parser and budgets, no provider calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

CODE=Path(__file__).resolve().parents[1]/"packaging/m27_f04_owner_native_01/native_https_provider.py"
spec=importlib.util.spec_from_file_location("f04_direct_delta",CODE)
native=importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

class FakeHTTP:
    def __init__(self,host,timeout=0):
        assert host=="api.minimax.io" and timeout<=26
        self.sent=None
        self.closed=False
        self.status=200
        self.events=[
            {"type":"message_start","message":{"model":"MiniMax-M3"}},
            {"type":"content_block_delta","delta":{"type":"text_delta","text":"Verification is in the Execution & Governance Plane.\n"}},
            {"type":"content_block_delta","delta":{"type":"text_delta","text":"PolicyEngine decides deterministic enforcement."}},
            {"type":"message_stop"},
        ]
    def request(self, method,path,body,headers):
        self.sent=(method,path,json.loads(body),headers)
        assert method=="POST" and path=="/anthropic/v1/messages"
    def getresponse(self):
        class Response:
            def __init__(self,owner):self.status=owner.status;self.owner=owner
            def __iter__(self):
                return iter([("data:"+json.dumps(event)+"\n").encode() for event in self.owner.events])
        return Response(self)
    def close(self):self.closed=True

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key=Path(self.tmp.name)/"secret"
        self.key.write_text("TESTONLY0123456789ABCDEFGHIJKL")
        self.key.chmod(0o600)
    def call(self):
        with mock.patch.object(native.http.client,"HTTPSConnection",FakeHTTP):
            return list(native.stream(provider_secret=self.key,prompt="X"*300))
    def test_verified_real_sse_event_contract(self):
        events=self.call()
        self.assertEqual([v["event"] for v in events],
            ["request_start","response_headers","model_identity",
             "delta","delta","provider_done","stream_end"])
        self.assertEqual(events[-1]["provider_done"],True)
        self.assertTrue(events[0]["in_container_https"])
        self.assertEqual(events[0]["max_tokens"],128)
        self.assertNotIn("TESTONLY",json.dumps(events))
    def test_invalid_owner_secret_mode_denied(self):
        self.key.chmod(0o644)
        with self.assertRaisesRegex(native.Denied,"PROVIDER_SECRET_OWNER_MODE_OR_LENGTH_DENIED"):
            self.call()
    def test_model_identity_mismatch_fail_closed(self):
        class Wrong(FakeHTTP):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.events[0]["message"]["model"]="wrong"
        with mock.patch.object(native.http.client,"HTTPSConnection",Wrong):
            events=list(native.stream(provider_secret=self.key,prompt="X"*300))
            self.assertEqual(events[-1]["event"],"error")
            self.assertEqual(events[-1]["category"],"MODEL_ORIGIN_NOT_ATTESTED")
            self.assertFalse(any(x["event"]=="provider_done" for x in events))
    def test_malformed_sse_denied_without_done(self):
        class Malformed(FakeHTTP):
            def getresponse(self):
                class Response:
                    status=200
                    def __iter__(self):return iter([b"data:{malformed}\n"])
                return Response()
        with mock.patch.object(native.http.client,"HTTPSConnection",Malformed):
            events=list(native.stream(provider_secret=self.key,prompt="X"*300))
            self.assertEqual(events[-1]["event"],"error")
            self.assertEqual(events[-1]["category"],"INVALID_PROVIDER_SSE_JSON")
            self.assertFalse(any(x["event"]=="provider_done" for x in events))
    def test_unauthorized_prompt_denied_before_network(self):
        with self.assertRaisesRegex(native.Denied,"PROMPT_NOT_AUTHORIZED"):
            list(native.stream(provider_secret=self.key,prompt="tiny"))
    def test_wrong_credentials_owner_denied(self):
        with mock.patch.object(native.os,"geteuid",return_value=65532):
            with self.assertRaisesRegex(native.Denied,"PROVIDER_SECRET_OWNER_MODE_OR_LENGTH_DENIED"):
                native.secret(self.key)

if __name__=="__main__":unittest.main()
