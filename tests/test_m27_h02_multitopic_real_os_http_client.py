"""Real separate OS Python client against loopback-only H02 Nonprod source review."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
import m27_h02_multitopic_local_source_review as local


class RealLocalClientTransport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m27-h02-source-review-http-")
        self.addCleanup(self.temp.cleanup)
        d = Path(self.temp.name)
        fence = d / "fence.json"
        fence.write_text(json.dumps({"release_id": local.h02.f03.A05_RELEASE_ID,
                                     "minimum_epoch": 1}))
        fence.chmod(0o600)
        self.review = local.SourceReview(
            repo=ROOT, fence=fence, journal=d / "journal.jsonl"
        )
        self.server = local.LocalSourceReviewServer(self.review, port=0)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.endpoint = "http://127.0.0.1:" + str(self.server.server_address[1])

    def _client(self, topic: str):
        client = r'''
import json,sys,urllib.request,urllib.error
base, topic = sys.argv[1:]
token=sys.stdin.read().strip()
def post(url, data):
    b=json.dumps(data).encode()
    request=urllib.request.Request(base+url,b,{"Content-Type":"application/json","Authorization":"Bearer "+token},
                                  method="POST")
    try:
        with urllib.request.urlopen(request,timeout=6) as x:
            return x.status,json.loads(x.read())
    except urllib.error.HTTPError as e:
        return e.code,json.loads(e.read())
s,source=post("/nonprod/source-review/start",{"topic":topic})
if topic=="Tool Registry":
    assert s==403 and source["status"]=="SOURCE_REVIEW_REQUEST_DENIED", (s,source)
    print(json.dumps({"code":s,"denied":True}))
else:
    assert s==200 and source["model_generated"] is False and source["complete_answer"] is False
    assert source["provider"]=="NOT_RUN" and source["product_qualified"] is False
    assert source["claims"],source
    for claim in source["claims"]:
        status,res=post("/nonprod/source-review/ack",
            {"session_id":source["session_id"],"claim_id":claim["claim_id"],
             "challenge":claim["challenge"],"text_sha256":claim["text_sha256"]})
        assert status==200 and res["status"]=="SOURCE_REVIEW_ACK_RECEIVED",(status,res)
    status,done=post("/nonprod/source-review/terminal",{"session_id":source["session_id"]})
    assert status==200 and done["status"]=="LOCAL_SOURCE_REVIEW_ACKED_NOT_PRODUCT"
    assert done["model_generated_answer"] is False and done["product_pass"] is False
    print(json.dumps({"code":status,"topic":topic,"claims":len(source["claims"]),
                      "terminal":done["status"],"provider":source["provider"],
                      "independent_os_source_verified":source["independent_os_source_verified"]}))
'''
        p=subprocess.run([sys.executable,"-c",client,self.endpoint,topic],
                         cwd=ROOT,input=self.server.client_auth_token,capture_output=True,text=True,timeout=35)
        self.assertEqual(p.returncode,0, p.stderr + p.stdout)
        return json.loads(p.stdout)

    def test_independent_os_client_context_planner(self):
        out=self._client("Context Planner")
        self.assertEqual(out["terminal"],"LOCAL_SOURCE_REVIEW_ACKED_NOT_PRODUCT")
        self.assertTrue(out["independent_os_source_verified"])

    def test_independent_os_client_workspace_memory(self):
        out=self._client("Workspace Memory")
        self.assertEqual(out["provider"],"NOT_RUN")

    def test_independent_os_client_unsupported_denied(self):
        self.assertTrue(self._client("Tool Registry")["denied"])


if __name__ == "__main__":
    unittest.main()
