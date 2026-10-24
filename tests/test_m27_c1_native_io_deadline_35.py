"""C1 native AF_UNIX HTTP slow-header/body deadline, no provider/network."""
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

class ProbeHandler(dev.Handler):
    CLIENT_IO_TIMEOUT_SECONDS=0.15
    def authorized(self):return True
    def do_POST(self):
        try:
            n=int(self.headers.get("Content-Length","0"))
            self.rfile.read(n)
            self.reply({"status":"UNEXPECTED_COMPLETE"})
        except (TimeoutError, OSError):
            return
    def do_GET(self):self.reply({"status":"OK"})

class ProbeServer(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def handle_error(self,*args):pass

class NativeDeadline(unittest.TestCase):
    def test_incomplete_headers_do_not_hold_native_worker(self):
        self._run(b"POST /ack HTTP/1.0\r\nHost: c1-dev-unix.local\r\n")
    def test_incomplete_ack_body_does_not_hold_native_worker(self):
        self._run(b"POST /ack HTTP/1.0\r\nHost: c1-dev-unix.local\r\nContent-Length: 100\r\n\r\n{}")
    def _run(self,wire):
        with tempfile.TemporaryDirectory(prefix="c1-http-io-") as d:
            with ProbeServer(str(Path(d)/"c1.sock"),ProbeHandler) as server:
                worker=threading.Thread(target=server.serve_forever,daemon=True)
                worker.start()
                client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                try:
                    client.settimeout(0.65)
                    client.connect(str(Path(d)/"c1.sock"))
                    client.sendall(wire)
                    started=time.monotonic()
                    try:response=client.recv(1024)
                    except socket.timeout:
                        self.fail("Native HTTP worker held an incomplete request beyond I/O budget")
                    self.assertLess(time.monotonic()-started,0.6)
                    self.assertNotIn(b"UNEXPECTED_COMPLETE",response)
                finally:
                    client.close()
                    server.shutdown()
                    worker.join(timeout=2)

if __name__=="__main__":unittest.main()
