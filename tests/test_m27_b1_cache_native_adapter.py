"""CACHE04 scoped tests: local HTTP, client validation, CACHE01 mode planning and IO spy."""
import http.cookiejar
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor, urlopen
from uuid import uuid4
# Pure-source isolated import: avoids unrelated M26 package startup (httpx absent).
# This namespace still loads the real frozen CACHE01 contract by its original path.
import sys
import types
from pathlib import Path
pkg = types.ModuleType('knowledge_engine')
pkg.__path__ = [str(Path(__file__).resolve().parents[1] / 'src/knowledge_engine')]
sys.modules['knowledge_engine'] = pkg
from knowledge_engine.m27_b1_cache_native_adapter import (
 Cache04Demo, DEMO_PATH, UI_SCHEMA, UI_FILE, FixtureCacheIOSpy,
 internal_demo_envelope, parse_ui_request, run_adapter
)
def payload(mode="AUTO"):
 return {"schema_version":UI_SCHEMA,"request_id":uuid4().hex,"cache_mode":mode,"question":"A source-bound question?"}
class Cache04ModeTests(unittest.TestCase):
 def test_default_modes(self):
  for mode,status in [("AUTO","DISABLED"),("BYPASS","BYPASSED"),("REFRESH","DISABLED")]:
   with self.subTest(mode=mode):
    r=run_adapter(internal_demo_envelope(mode,"question",uuid4().hex))
    self.assertEqual((r["cache_mode"],r["cache_status"]),(mode,status))
    self.assertFalse(r["cache_io_performed"]);self.assertFalse(r["answer_cache_hit_admitted"]);self.assertIsNone(r["answer"])
 def test_bypass_never_reads_writes(self):
  spy=FixtureCacheIOSpy()
  r=run_adapter(internal_demo_envelope("BYPASS","question",uuid4().hex),
    feature_enabled=True,fixture_io=spy,fixture_authority=True,fixture_verified_final={"answer":"forged"})
  self.assertEqual(r["cache_status"],"BYPASSED");self.assertEqual((spy.reads,spy.writes),(0,0))
 def test_auto_only_candidate_not_hit(self):
  spy=FixtureCacheIOSpy();req=internal_demo_envelope("AUTO","question",uuid4().hex)
  self.assertEqual(run_adapter(req,feature_enabled=True,fixture_io=spy,fixture_authority=True)["cache_status"],"LOOKUP_REQUIRED")
  self.assertTrue(spy.cas_fixture("fixture-tenant|fixture-principal","local fixture",None))
  r=run_adapter(req,feature_enabled=True,fixture_io=spy,fixture_authority=True)
  self.assertEqual(r["cache_status"],"PROVER_REQUIRED");self.assertFalse(r["answer_cache_hit_admitted"])
  self.assertEqual((spy.reads,spy.writes),(2,1))
 def test_refresh_conditional_fixture_cas_and_old_safe(self):
  spy=FixtureCacheIOSpy();req=internal_demo_envelope("REFRESH","question",uuid4().hex)
  proof={"qualification_class":"FIXTURE_ONLY","final_verified":False,"source_current":True,
         "rights_current":True,"answer":"fixture","prior":None}
  self.assertEqual(run_adapter(req,feature_enabled=True,fixture_io=spy,fixture_authority=True,
    fixture_verified_final=proof)["cache_status"],"WRITE_NOT_ADMITTED")
  self.assertEqual((spy.reads,spy.writes),(0,0))
  proof["final_verified"]=True
  r=run_adapter(req,feature_enabled=True,fixture_io=spy,fixture_authority=True,fixture_verified_final=proof)
  self.assertEqual(r["cache_status"],"VERIFIED_FIXTURE_ONLY");self.assertFalse(r["answer_cache_hit_admitted"])
  old=dict(spy.entries);proof["source_current"]=False
  self.assertEqual(run_adapter(req,feature_enabled=True,fixture_io=spy,fixture_authority=True,
    fixture_verified_final=proof)["cache_status"],"WRITE_NOT_ADMITTED")
  self.assertEqual(spy.entries,old);proof["source_current"]=True;proof["prior"]="wrong_revision"
  self.assertEqual(run_adapter(req,feature_enabled=True,fixture_io=spy,fixture_authority=True,
    fixture_verified_final=proof)["cache_status"],"WRITE_NOT_ADMITTED")
  self.assertEqual(spy.entries,old);self.assertEqual(spy.reads,0)
 def test_without_demo_authority_no_io(self):
  spy=FixtureCacheIOSpy()
  for mode in ("AUTO","REFRESH","BYPASS"):
   run_adapter(internal_demo_envelope(mode,"question",uuid4().hex),feature_enabled=True,
      fixture_io=spy,fixture_authority=False,fixture_verified_final={"answer":"fake"})
  self.assertEqual((spy.reads,spy.writes),(0,0))
 def test_invalid_client_payloads(self):
  v=payload()
  for bad in ({**v,"tenant_id":"victim"},{**v,"identity":{"authenticated":True}},
      {**v,"source":{"acl_sha256":"forged"}},{**v,"cache_mode":"HIT"},
      {**v,"cache_mode":False},{**v,"cache_mode":"refresh"},
      {**v,"schema_version":"v0"},{**v,"question":"<script>alert(1)</script>"},
      {**v,"question":"javascript:alert(1)"},{**v,"question":"bad\nstring"},
      {**v,"request_id":"bad"}):
   with self.subTest(case=str(bad)[:70]),self.assertRaises(ValueError):parse_ui_request(bad)
 def test_bounds(self):
  with self.assertRaises(ValueError):Cache04Demo("0.0.0.0")
  with self.assertRaises(ValueError):Cache04Demo(feature_enabled="true")
  with self.assertRaises(ValueError):FixtureCacheIOSpy(max_entries=999)
  html=UI_FILE.read_text()
  for x in ['id="allow"','id="refresh"','id="send"','aria-live="polite"','X-Cache-Demo-Request']:
   self.assertIn(x,html)

class Cache04HTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=Cache04Demo();cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join(2)
 def setUp(self):
  self.opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
  with self.opener.open(self.server.origin+"/__cache04/demo/") as page:
   self.assertEqual(page.status,200);self.assertEqual(page.headers["Cache-Control"],"no-store")
   self.assertIn("HttpOnly",page.headers["Set-Cookie"])
   self.assertIn("Content-Security-Policy",page.headers)
   self.assertIn("NONPROD LOCAL FIXTURE ONLY",page.read().decode())
 def post(self,data,*,noauth=False,origin=None,headers=None):
  body=json.dumps(data).encode() if isinstance(data,dict) else data
  meta={"Content-Type":"application/json","X-Cache-Demo-Request":"1",
    "Origin":self.server.origin if origin is None else origin}
  meta.update(headers or {})
  request=Request(self.server.origin+DEMO_PATH,data=body,headers=meta,method="POST")
  try:response=urlopen(request,timeout=5) if noauth else self.opener.open(request,timeout=5)
  except HTTPError as e:
   try:return (e.code,json.loads(e.read()))
   finally:e.close()
  with response:return (response.status,json.loads(response.read()))
 def test_real_http_modes(self):
  for mode,status in (("AUTO","DISABLED"),("BYPASS","BYPASSED"),("REFRESH","DISABLED")):
   with self.subTest(mode=mode):
    req=payload(mode);code,out=self.post(req);self.assertEqual(code,200)
    self.assertEqual((out["request_id"],out["cache_mode"],out["cache_status"]),
                     (req["request_id"],mode,status))
    self.assertFalse(out["cache_io_performed"]);self.assertFalse(out["product_authenticated"])
    self.assertEqual(out["scope"],"LOCAL_FIXTURE_ONLY")
 def test_replay(self):
  q=payload();self.assertEqual(self.post(q)[0],200)
  self.assertEqual(self.post(q),(409,{"error":"REPLAY_DENIED"}))
 def test_invalid_auth_origin_cancellation(self):
  self.assertEqual(self.post(payload(),noauth=True)[0],403)
  self.assertEqual(self.post(payload(),origin="https://attacker.example")[0],403)
  self.assertEqual(self.post(payload(),headers={"X-Cache-Demo-Request":"fake"})[0],403)
  self.assertEqual(self.post(payload(),headers={"X-Cache-Demo-Cancelled":"1"})[0],409)
 def test_http_forgery_and_injection(self):
  for x in ({**payload(),"principal_id":"admin"},{**payload(),"cache_mode":"HIT"},
   {**payload(),"question":"<img src=x onerror=alert(1)>"},
   {**payload(),"policy":{"rights":"fake"}}):
   with self.subTest(x=x):
    code,out=self.post(x);self.assertEqual(code,400);self.assertIn("error",out)
 def test_body_and_type(self):
  self.assertEqual(self.post(b"{bad json")[0],400)
  self.assertEqual(self.post(payload(),headers={"Content-Type":"text/plain"})[0],415)
  self.assertEqual(self.post(b"x"*4097)[0],413)
 def test_no_shared_native_route(self):
  with self.assertRaises(HTTPError) as cm:self.opener.open(self.server.origin+"/v1/answers/stream")
  self.assertEqual(cm.exception.code,404)
  cm.exception.close()
if __name__=="__main__":unittest.main()
