"""A05 localhost HTTP receipt route. Test-only, not external authentication."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from a05_retrieval import ContextIndex, SourceError

class Handler(BaseHTTPRequestHandler):
    index = None
    server_version = "A05ContextNonprod/1"
    def log_message(self, fmt, *args):
        sys.stderr.write("HTTP " + fmt % args + "\n")
    def send_json(self, status, value):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/v1/health":
            self.send_json(200, {"healthy": True, "environment": "nonprod-loopback",
                                 "real_idp": False, "product_vector": False,
                                 "release_id": self.index.release["release_id"]})
        else:
            self.send_json(404, {"status": "not_found"})
    def do_POST(self):
        if self.path != "/v1/query":
            return self.send_json(404, {"status": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 32768:
                raise SourceError(400, "invalid_payload")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise SourceError(400, "invalid_payload")
            # These are unverified local test claims, not a Production IdP.
            result = self.index.search(
                question=payload.get("question"), tenant=payload.get("tenant"),
                roles=payload.get("roles"), release_id=payload.get("release_id"),
                source_revision=payload.get("source_revision"), limit=payload.get("limit", 5))
            self.send_json(200, result)
        except SourceError as e:
            self.send_json(e.http_code, {"status": "refused", "reason": e.code,
                                         "results": [], "answer_generated": False})
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.send_json(400, {"status": "refused", "reason": "invalid_payload",
                                 "results": [], "answer_generated": False})

if __name__ == "__main__":
    port = int(sys.argv[1])
    Handler.index = ContextIndex()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"event": "ready", "listen": "127.0.0.1", "port": port,
                      "product_qdrant": False, "auth": "test-only"}), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
