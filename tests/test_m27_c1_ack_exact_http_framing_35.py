"""Native C1 ACK must bind exactly to HTTP Content-Length, including EOF.

Uses actual AF_UNIX HTTP socket/Handler, not a mock HTTP parser; no provider.
"""
import json
import socket
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as dev


class AckHandler(dev.Handler):
    CLIENT_IO_TIMEOUT_SECONDS=0.35
    def authorized(self): return True


class AckServer(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def __init__(self,path):
        self.pending={}
        self.acked=[]
        self.done=False
        self.deadline_ns=time.monotonic_ns()+20_000_000_000
        self.first_preterminal_ack=False
        self.ack_cond=threading.Condition()
        self.audit_records=[]
        super().__init__(path,AckHandler)
    def current(self):return []
    def audit(self,event):self.audit_records.append(event)
    def handle_error(self,*args):pass


class NativeAckExactFraming(unittest.TestCase):
    def exchange(self, declared_delta=0):
        claim=dev.c1live.OBLIGATIONS[0]
        ack={"request_id":"req-native","claim_id":claim,
             "challenge":"test-ack-challenge","text_sha256":"abc123"}
        body=json.dumps(ack,separators=(",",":")).encode()
        with tempfile.TemporaryDirectory(prefix="c1-ack-framing-") as td:
            path=str(Path(td)/"c1.sock")
            with AckServer(path) as server:
                server.pending[claim]=dict(ack)
                worker=threading.Thread(target=server.serve_forever,daemon=True)
                worker.start()
                client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                try:
                    client.settimeout(2)
                    client.connect(path)
                    wire=(b"POST /ack HTTP/1.0\r\nHost: c1-dev-unix.local\r\n"+
                          b"Content-Length: "+str(len(body)+declared_delta).encode()+
                          b"\r\n\r\n"+body)
                    client.sendall(wire)
                    # Actual early EOF: the declared body is larger than the
                    # complete, syntactically valid JSON ACK already sent.
                    client.shutdown(socket.SHUT_WR)
                    chunks=[]
                    while True:
                        part=client.recv(4096)
                        if not part:break
                        chunks.append(part)
                    return b"".join(chunks),list(server.acked),list(server.audit_records)
                finally:
                    client.close()
                    server.shutdown()
                    worker.join(timeout=2)
    def test_complete_exact_ack_is_accepted(self):
        response,acked,events=self.exchange()
        self.assertIn(b"HTTP/1.0 200",response)
        self.assertEqual(acked,[dev.c1live.OBLIGATIONS[0]])
        self.assertEqual(len(events),1)
    def test_early_eof_after_valid_json_must_not_be_accepted(self):
        response,acked,events=self.exchange(declared_delta=20)
        self.assertNotIn(b"HTTP/1.0 200",response)
        self.assertEqual(acked,[])
        self.assertEqual(events,[])

if __name__=="__main__":unittest.main()
