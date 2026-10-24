"""A06/A07 RED→GREEN. Real ACK body hashes must bind client, server and SSE to one challenge.

All isolated deterministic fixture contracts are TEST-ONLY; no invented issuer.
"""
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as d

RID="a"*48
TASK="b"*64
CLAIM="execution_governance_verification"
CHALLENGE="c"*40
TEXT_SHA="d"*64
def sha(raw):return hashlib.sha256(raw).hexdigest()

class AckNonceCustodyContracts(unittest.TestCase):
    def test_real_ack_body_challenge_digest_binds_all_5_fields(self):
        raw=json.dumps({"request_id":RID,"claim_id":CLAIM,
              "challenge":CHALLENGE,"text_sha256":TEXT_SHA}).encode()
        x=d.ack_custody_fields(request_id=RID,task_sha256=TASK,
              claim_id=CLAIM,challenge=CHALLENGE,text_sha256=TEXT_SHA,
              raw_ack_body=raw)
        self.assertEqual(x["challenge_sha256"],sha(CHALLENGE.encode()))
        self.assertEqual(x["ack_binding_sha256"],
            sha("|".join((RID,TASK,CLAIM,CHALLENGE,TEXT_SHA)).encode()))
        self.assertEqual(x["ack_request_body_sha256"],sha(raw))
        self.assertNotIn(CHALLENGE,json.dumps(x))
    def test_changed_task_challenge_claim_text_or_body_changes_sha(self):
        raw=json.dumps({"request_id":RID,"claim_id":CLAIM,
              "challenge":CHALLENGE,"text_sha256":TEXT_SHA}).encode()
        base=dict(request_id=RID,task_sha256=TASK,claim_id=CLAIM,
                  challenge=CHALLENGE,text_sha256=TEXT_SHA,raw_ack_body=raw)
        expected=d.ack_custody_fields(**base)
        for field,new in (("request_id","f"*48),("task_sha256","e"*64),
                          ("claim_id","policy_engine_enforcement"),
                          ("challenge","e"*40),("text_sha256","f"*64)):
            with self.subTest(field=field):
                changed={**base,field:new}
                changed["raw_ack_body"]=json.dumps({
                    k:changed[k] for k in ("request_id","claim_id",
                                           "challenge","text_sha256")}).encode()
                modified=d.ack_custody_fields(**changed)
                self.assertNotEqual(modified["ack_binding_sha256"],
                                    expected["ack_binding_sha256"])
        whitespace=d.ack_custody_fields(**{**base,"raw_ack_body":raw+b" "})
        self.assertNotEqual(whitespace["ack_request_body_sha256"],
                            expected["ack_request_body_sha256"])
        self.assertEqual(whitespace["ack_binding_sha256"],
                         expected["ack_binding_sha256"])
    def test_invalid_or_exfiltrating_nonce_denied_without_print(self):
        raw=b"{}"
        for malformed in ("", "x|abc","x"*512):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    d.ack_custody_fields(request_id=RID,task_sha256=TASK,
                      claim_id=CLAIM,challenge=malformed,
                      text_sha256=TEXT_SHA,raw_ack_body=raw)

if __name__=="__main__":unittest.main()
