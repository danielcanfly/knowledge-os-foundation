"""Exact C1 owner-firstparty M26 direct Cloudflare-primary failover controls.

Synthetic provider units are marked as testing ONLY. Positive Product proof
requires a new real Worker AI response + real A05/Native Client receipts.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/knowledge_engine"))
import m27_c1_m26_provider_parity_nonprod as p

PROMPT="Using A05 owner source answer which plane includes Verification and which authority decides deterministic policy?"
def cloud_ok(prompt):
    assert prompt==PROMPT
    yield {"event":"request_start","model":p.MODEL,"route":p.ROUTE}
    yield {"event":"response_headers","status":200}
    yield {"event":"model_identity","model":p.MODEL,"model_match":True}
    yield {"event":"delta","text":"Verification is in the Execution & Governance Plane.\n"}
    yield {"event":"delta","text":"PolicyEngine decides deterministic enforcement."}
    yield {"event":"provider_done"}
    yield {"event":"stream_end","provider_done":True}

def minimax_ok():
    yield {"event":"request_start","model":"MiniMax-M3",
           "route":"VM_OWNER_CANARY_NONPROD"}
    yield {"event":"response_headers","status":200}
    yield {"event":"model_identity","model":"MiniMax-M3","model_match":True}
    yield {"event":"delta","text":"Valid response"}
    yield {"event":"provider_done"}
    yield {"event":"stream_end","provider_done":True}

class CloudflareM26ScopedParity(unittest.TestCase):
    def routed(self,fn,fallback=minimax_ok):
        return list(p.cloudflare_first_with_minimax_backup(
            prompt=PROMPT,vendor=Path("."),primary_fn=fn,fallback_fn=fallback))

    def test_01_actual_primary_prefers_cloudflare_and_never_calls_minimax(self):
        def forbidden():
            raise AssertionError("UNAUTHORIZED_MINIMAX_FALLBACK")
        result=self.routed(cloud_ok,forbidden)
        self.assertEqual([e["event"] for e in result],
              ["request_start","response_headers","model_identity",
               "delta","delta","provider_done","stream_end"])
        self.assertEqual(result[0]["model"],p.MODEL)

    def test_02_real_infra_quota_error_triggers_real_recorded_minimax_attempt(self):
        def cf(prompt):
            yield {"event":"request_start","model":p.MODEL,"route":p.ROUTE}
            yield {"event":"response_headers","status":429}
            yield {"event":"error","category":"CLOUDFLARE_DAILY_QUOTA_EXHAUSTED_3036"}
        result=self.routed(cf)
        self.assertEqual([e["event"] for e in result],
          ["request_start","response_headers","failover","request_start",
           "response_headers","model_identity","delta","provider_done","stream_end"])
        self.assertEqual(result[2]["reason"],
                         "CLOUDFLARE_DAILY_QUOTA_EXHAUSTED_3036")
        self.assertEqual(result[3]["model"],"MiniMax-M3")

    def test_03_refuses_fallback_after_any_primary_generated_text(self):
        def cf(prompt):
            yield {"event":"request_start","model":p.MODEL,"route":p.ROUTE}
            yield {"event":"delta","text":"One real token"}
            yield {"event":"error","category":"CLOUDFLARE_TIMEOUT_OR_NETWORK_TRANSIENT"}
        result=self.routed(cf)
        self.assertEqual(result[-1]["event"],"error")
        self.assertNotIn("failover",[e["event"] for e in result])

    def test_04_refuses_fallback_after_semantic_or_protocol_error(self):
        for error in ("CLOUDFLARE_MODEL_MISMATCH",
                      "CLOUDFLARE_INVALID_SSE_JSON",
                      "CLOUDFLARE_INCOMPLETE_STREAM",
                      "C1_PROMPT_BAD_SCOPE","CLOUDFLARE_HTTP_418",
                      "CLOUDFLARE_PAID_PLAN_ONLY_5035",
                      "CLOUDFLARE_AUTH_OR_CONFIG"):
            with self.subTest(error=error):
                def cf(prompt):
                    yield {"event":"error","category":error}
                result=self.routed(cf)
                self.assertEqual(len(result),1)
                self.assertEqual(result[0]["category"],error)

    def test_05_pin_current_m26_direct_primary_and_nonprod_budget(self):
        self.assertEqual(p.MODEL,"@cf/openai/gpt-oss-120b")
        self.assertIn("/ai/v1/chat/completions",p.VM_STREAM_SCRIPT)
        self.assertNotIn("gateway.ai.cloudflare.com",p.VM_STREAM_SCRIPT)
        self.assertIn("'stream':True",p.VM_STREAM_SCRIPT)
        self.assertIn("'max_tokens':192",p.VM_STREAM_SCRIPT)
        self.assertNotIn("os.environ['CLOUDFLARE",p.VM_STREAM_SCRIPT)
        self.assertFalse("MINIMAX_API_KEY" in p.VM_STREAM_SCRIPT)

    def test_06_failclosed_malformed_and_oversized_provider_event(self):
        with self.assertRaisesRegex(ValueError,"DELTA_BOUND"):
            p.only_safe_event({"event":"delta","text":"x"*4097})
        with self.assertRaisesRegex(ValueError,"NOT_IN_WIRE_CONTRACT"):
            p.only_safe_event({"event":"fake_provider_done"})
        with self.assertRaisesRegex(ValueError,"PROMPT_SCOPE"):
            list(p.invoke_direct_cloudflare("hi"))

if __name__=="__main__":unittest.main()
