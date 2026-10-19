"""New regression from independent C1-AUDIT-02 D01/D02, not fixture signoff.

Must fail on original 14f4e235: duplicate [DONE], trailing actual SSE,
corrupt terminal frame, and total wall-clock overrun despite live iterator
making progress within socket timeout.
No network, no real issuer, no state effects.
"""
import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_formal_workers_ai_sse as sse
from test_m27_c1_formal_workers_ai_sse import complete,line,parse

class Audit02NegativeCases(unittest.TestCase):
    def test_d01_01_duplicate_done_must_be_rejected(self):
        with self.assertRaisesRegex(sse.WireRejected,"AFTER_DONE|DUPLICATE_DONE"):
            parse(complete()+[b"data: [DONE]\n"])

    def test_d01_02_substantive_text_after_done_must_be_rejected(self):
        with self.assertRaisesRegex(sse.WireRejected,"AFTER_DONE"):
            parse(complete()+[line("UNAUTHORIZED LATE MODEL TEXT")])

    def test_d01_03_malformed_data_after_done_must_be_rejected(self):
        with self.assertRaisesRegex(sse.WireRejected,"AFTER_DONE"):
            parse(complete()+[b"data: {'truncated'\n"])

    def test_d01_04_only_explicitly_safe_terminal_whitespace_and_comments(self):
        _,events=parse(complete()+[b"\n",b": owner-compatible keepalive\n",b"\r\n"])
        self.assertEqual([e["kind"] for _,e in events],["delta","delta","done"])
        with self.assertRaisesRegex(sse.WireRejected,"AFTER_DONE"):
            parse(complete()+[b"event: new-response\n"])

    def test_d02_01_adversarial_delayed_finite_live_response_must_fail(self):
        class SlowActualResponse:
            status=200
            headers={"Content-Type":"text/event-stream"}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def __iter__(self):
                yield line("One real partial sentence\n")
                time.sleep(.080)
                yield line("A second material sentence.")
                yield line(finish="stop")
                yield b"data: [DONE]\n"
        class Opener:
            def open(self,*args,**kwargs):return SlowActualResponse()
        adapter=sse.DirectWorkersAISSE(
            url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
            model=sse.MODEL,
            token_path=Path("/fake/no-read"),
            private_file=lambda *args,**kwargs:b"dummy-do-not-save",
            max_wall_seconds=.01)
        start=time.monotonic()
        with patch.object(sse,"build_opener",return_value=Opener()):
            with self.assertRaisesRegex(sse.WireRejected,"DEADLINE"):
                list(adapter.one_bounded_stream(
                    prompt="Answer based exclusively on the authorized A05 source.",
                    task_sha="3"*64,request_id="c1-new-task-1",max_tokens=64))
        self.assertLess(time.monotonic()-start,.5)

    def test_d02_02_adversarial_initial_delay_before_first_frame(self):
        class SlowOpen:
            status=200
            headers={"Content-Type":"text/event-stream"}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def __iter__(self):
                time.sleep(.04)
                yield from complete()
        class Opener:
            def open(self,*args,**kwargs):return SlowOpen()
        adapter=sse.DirectWorkersAISSE(
            url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
            model=sse.MODEL,
            token_path="test-only",
            private_file=lambda *args,**kwargs:b"dummy",
            max_wall_seconds=.01)
        with patch.object(sse,"build_opener",return_value=Opener()):
            with self.assertRaisesRegex(sse.WireRejected,"DEADLINE"):
                list(adapter.one_bounded_stream(
                    prompt="Answer based exclusively on authorized owner A05 source.",
                    task_sha="4"*64,request_id="new-c1-task-02",max_tokens=64))

    def test_d01_05_terminal_audit_cannot_claim_success_before_trailing_validation(self):
        evidence=[]
        with self.assertRaisesRegex(sse.WireRejected,"AFTER_DONE"):
            list(sse.decode_sse(
                complete()+[b"data: [DONE]\n"],
                model=sse.MODEL,request_id="real-one-task",
                audit=evidence.append))
        self.assertFalse(any(x.get("meaning")=="REAL_PROVIDER_DONE_FRAME"
                             for x in evidence))

    def test_d02_03_connect_elapsed_counts_against_entire_deadline(self):
        class NoData:
            status=200
            headers={"Content-Type":"text/event-stream"}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def __iter__(self):return iter(complete())
        class SlowConnect:
            def open(self,*args,**kwargs):
                time.sleep(.04)
                return NoData()
        adapter=sse.DirectWorkersAISSE(
            url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
            model=sse.MODEL,token_path="synthetic",
            private_file=lambda *args,**kwargs:b"dummy",max_wall_seconds=.01)
        with patch.object(sse,"build_opener",return_value=SlowConnect()):
            with self.assertRaisesRegex(sse.WireRejected,"DEADLINE"):
                list(adapter.one_bounded_stream(
                    prompt="Answer based on the authorized firstparty A05 source.",
                    task_sha="a"*64,request_id="test-connection-budget",max_tokens=64))

    def test_d02_04_real_response_socket_receives_remaining_not_reset_budget(self):
        class RawSocket:
            def __init__(self):self.samples=[]
            def settimeout(self,x):self.samples.append(x)
        sock=RawSocket()
        class FakeResponse:
            status=200
            headers={"Content-Type":"text/event-stream"}
            fp=type("F",(),{"raw":type("R",(),{"_sock":sock})()})()
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def __iter__(self):
                for fragment in complete():
                    time.sleep(.004)
                    yield fragment
        class Opener:
            def open(self,*args,**kwargs):return FakeResponse()
        adapter=sse.DirectWorkersAISSE(
            url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
            model=sse.MODEL,token_path="synthetic",
            private_file=lambda *args,**kwargs:b"dummy",max_wall_seconds=.5)
        with patch.object(sse,"build_opener",return_value=Opener()):
            result=list(adapter.one_bounded_stream(
                    prompt="Answer based on the authorized firstparty A05 source.",
                    task_sha="a"*64,request_id="test-socket-total-time",max_tokens=64))
        self.assertEqual([r[1]["kind"] for r in result],["delta","delta","done"])
        self.assertGreaterEqual(len(sock.samples),4)
        self.assertTrue(all(0<x<=.5 for x in sock.samples))
        self.assertLess(sock.samples[-1],sock.samples[0])

    def test_d02_05_no_zero_negative_or_unbounded_deadline(self):
        for n in (-1,0,31,float("inf"),float("nan"),"30",None):
            with self.subTest(value=n):
                with self.assertRaises(sse.WireRejected):
                    sse.DirectWorkersAISSE(
                        url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
                        model=sse.MODEL,token_path="synthetic",
                        private_file=lambda *args,**kwargs:b"dummy",max_wall_seconds=n)

    def test_d02_06_urllib_wrapped_tls_socket_gets_true_remaining_budget(self):
        class PhysicalSocket:
            def __init__(self):self.timeouts=[]
            def settimeout(self,t):self.timeouts.append(t)
        sock=PhysicalSocket()
        class SSLReader:
            raw=type("SocketIO",(),{"_sock":sock})()
        class HTTPResponse:
            fp=SSLReader()
        class WrappedResponse:
            fp=HTTPResponse()
            status=200
            headers={"Content-Type":"text/event-stream"}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def __iter__(self):
                for raw in complete():
                    time.sleep(.002)
                    yield raw
        class Opener:
            def open(self,*a,**kw):return WrappedResponse()
        adapter=sse.DirectWorkersAISSE(
            url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
            model=sse.MODEL,token_path="test-only",
            private_file=lambda *a,**kw:b"dummy",max_wall_seconds=2.0)
        with patch.object(sse,"build_opener",return_value=Opener()):
            output=list(adapter.one_bounded_stream(
              prompt="Answer only from Owner A05 primary authorized source.",
              task_sha="5"*64,request_id="SSE-WRAPPED-RESP-01",max_tokens=64))
        self.assertEqual([x[1]["kind"] for x in output],["delta","delta","done"])
        self.assertGreaterEqual(len(sock.timeouts),5)
        self.assertLess(sock.timeouts[-1],sock.timeouts[0])
        self.assertTrue(all(0<t<=2.0 for t in sock.timeouts))

    def test_d02_07_missing_physical_socket_from_real_urllib_response_fails_closed(self):
        from urllib.response import addinfourl
        class Source:
            closed=False
            def read(self,*a):return b""
            def close(self):pass
            def __iter__(self):return iter(complete())
        real_wrapper=addinfourl(Source(),{"Content-Type":"text/event-stream"},
                               "https://api.cloudflare.com",code=200)
        class Opener:
            def open(self,*a,**kw):return real_wrapper
        adapter=sse.DirectWorkersAISSE(
            url="https://api.cloudflare.com/client/v4/accounts/abc123456/ai/v1/chat/completions",
            model=sse.MODEL,token_path="test-only",
            private_file=lambda *a,**kw:b"dummy",max_wall_seconds=.2)
        with patch.object(sse,"build_opener",return_value=Opener()):
            with self.assertRaisesRegex(sse.WireRejected,"PHYSICAL_SOCKET_DEADLINE_UNAVAILABLE"):
                list(adapter.one_bounded_stream(
                  prompt="Answer only from Owner A05 primary authorized source.",
                  task_sha="6"*64,request_id="SSE-WRAPPED-NOSOCK-01",max_tokens=64))

if __name__=="__main__":unittest.main()


