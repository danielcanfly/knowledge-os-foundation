"""New image-native MiniMax transport safety tests, NO network or provider key."""
import importlib.util,io,json,os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PROVIDER=Path(__file__).resolve().parents[1]/"packaging/m27_f04_owner_native_01/native_https_provider.py"
spec=importlib.util.spec_from_file_location("native_https_provider",PROVIDER)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
PROMPT="Source A. "*45
class FakeResponse:
    def __init__(self,events,status=200):
        self.lines=[b"data: "+json.dumps(v).encode()+b"\n" for v in events]
        self.status=status
    def __iter__(self):return iter(self.lines)
class FakeConnection:
    def __init__(self,events,status=200):self.events=events;self.status=status;self.sent=False;self.closed=False
    def request(self,method,path,body,headers):
        assert method=="POST" and path=="/anthropic/v1/messages"
        parsed=json.loads(body)
        assert parsed["max_tokens"]==128 and parsed["stream"] is True
        assert headers.get("Authorization")=="Bearer "+"a"*32
        self.sent=True
    def getresponse(self):return FakeResponse(self.events,self.status)
    def close(self):self.closed=True
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"secret"
        self.path.write_text("a"*32);self.path.chmod(0o600)
    def invoke(self,events,status=200):
        fake=FakeConnection(events,status=status)
        with mock.patch.object(mod.http.client,"HTTPSConnection",return_value=fake):
            receipts=list(mod.stream(provider_secret=self.path,prompt=PROMPT))
        return receipts,fake
    def test_native_stream_true_response(self):
        events=[{"type":"message_start","message":{"model":"MiniMax-M3"}},
          {"type":"content_block_delta","delta":{"type":"text_delta","text":"Verified sentence.\n"}},
          {"type":"message_stop"}]
        received,conn=self.invoke(events)
        self.assertEqual([x["event"] for x in received],["request_start","response_headers","model_identity","delta","provider_done","stream_end"])
        self.assertTrue(received[-1]["provider_done"])
        self.assertTrue(conn.sent and conn.closed)
        self.assertNotIn("a"*32,json.dumps(received))
    def test_wrong_model_is_no_done(self):
        events=[{"type":"message_start","message":{"model":"WRONG"}}]
        received,_=self.invoke(events)
        self.assertNotIn("provider_done",[x["event"] for x in received])
        self.assertEqual(received[-1]["category"],"MODEL_ORIGIN_NOT_ATTESTED")
    def test_denied_initial_http_no_fallback(self):
        received,_=self.invoke([],status=403)
        self.assertEqual(received[-1],{"event":"error","category":"HTTP_403"})
    def test_no_message_stop_failclosed(self):
        events=[{"type":"message_start","message":{"model":"MiniMax-M3"}},
           {"type":"content_block_delta","delta":{"type":"text_delta","text":"Partial"}}]
        received,_=self.invoke(events)
        self.assertFalse(received[-1]["provider_done"])
    def test_secret_permission_denied(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(mod.Denied,"PROVIDER_SECRET_OWNER_MODE"):
            mod.secret(self.path)
    def test_secret_symlink_denied(self):
        alias=Path(self.tmp.name)/"alias";alias.symlink_to(self.path)
        with self.assertRaises(OSError):mod.secret(alias)
if __name__=="__main__":unittest.main()
