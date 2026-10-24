"""Offline diagnostics custody tests for an actually rejected Cloudflare tail.

These tests never call a provider. They verify the Native Server persists the
safe static rejection reason, hashes and structural metadata, not raw model
text, keys, prompt or untrusted diagnostic fields.
"""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as c1

VALID={
    "event":"stream_diagnostic","model_attested":True,
    "finish_stop":True,"done_frame":False,"delta_count":16,
    "rejected_tail_reason":"TAIL_MATERIAL_OR_INVALID_CHOICE",
    "rejected_tail_shape":{"top_known":["choices"],"top_unknown_count":0},
    "rejected_tail_wire_sha256":"a"*64,
    "text":"FORBIDDEN SECRET MODEL BODY",
    "credential":"SECRET_TOKEN_SHOULD_NOT_LEAK",
}
class CloudflareNativeAuditRejectReason(unittest.TestCase):
    def test_static_postfinish_reason_survives_exact_native_audit_projection(self):
        event=c1.safe_cloudflare_stream_diagnostic(VALID)
        self.assertEqual(event["event"],"cloudflare_stream_completion_evidence")
        self.assertEqual(event["rejected_tail_reason"],
                         "TAIL_MATERIAL_OR_INVALID_CHOICE")
        self.assertEqual(event["rejected_tail_wire_sha256"],"a"*64)
        self.assertEqual(event["rejected_tail_shape"]["top_unknown_count"],0)
        self.assertNotIn("credential",event)
        self.assertNotIn("text",event)
    def test_reject_reason_payload_injection_without_leak(self):
        event=c1.safe_cloudflare_stream_diagnostic({
           **VALID,"rejected_tail_reason":"SECRET\nFALSIFIED_AUDIT_PASS"})
        self.assertEqual(event["rejected_tail_reason"],"TAIL_UNKNOWN_REASON")
        self.assertNotIn("SECRET",str(event))
    def test_diagnostic_refuses_untrusted_shape_and_hash(self):
        with self.assertRaisesRegex(ValueError,"C1_CLOUDFLARE_DIAG"):
            c1.safe_cloudflare_stream_diagnostic({**VALID,
                   "rejected_tail_shape":{"untrusted_text":"model answer"}})
        with self.assertRaisesRegex(ValueError,"C1_CLOUDFLARE_DIAG"):
            c1.safe_cloudflare_stream_diagnostic({**VALID,
                   "rejected_tail_wire_sha256":"untrusted"})
    def test_successful_stream_has_no_spurious_rejection_reason(self):
        event=c1.safe_cloudflare_stream_diagnostic({
          "event":"stream_diagnostic","model_attested":True,
          "finish_stop":True,"done_frame":True,"delta_count":4})
        self.assertNotIn("rejected_tail_reason",event)
        self.assertNotIn("rejected_tail_wire_sha256",event)
        self.assertNotIn("rejected_tail_shape",event)

if __name__=="__main__":unittest.main()
