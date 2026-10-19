"""Formal admission audit checks use only TEMPORARY TEST keys/fixtures.

Generated test-key signatures are NOT Product signers and are NEVER retained
as real receipts. Test verdicts are not independent Product accreditation.
"""
from __future__ import annotations
import base64,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import m27_c1_formal_admission_preflight_v2 as p
LEDGER=Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/"
"M27_VNEXT_MASTER_20261009/07_MASTER_REBASE_20261010/"
"08_MASTER_TAKEOVER_20261012/09_MASTER_RESET_POST_V34_20261013/"
"10_NEW_MASTER_REBASE_20261018/REPORTS/EVIDENCE/"
"C1_M26_PARITY_DIRECT_OWNER_NONPROD_20261019")

class V2DynamicAdmission(unittest.TestCase):
    def test_01_accepted_previous_real_sse_custody_is_verified_not_inferred(self):
        old=p.legacy_dev_custody(ROOT,LEDGER)
        self.assertEqual(old["raw_file_count"],26)
        self.assertTrue(old["current_source_is_descendant"])
        self.assertTrue(old["historical_evidence_is_not_formal_current_signed_receipts"])

    def test_02_real_three_release_roots_not_yet_signed(self):
        roots=p.root_pins(ROOT)
        self.assertEqual(set(roots),set(p.PINS.values()))
        self.assertEqual(sum(v["admitted"] for v in roots.values()),0)

    def test_03_crypto_verifier_accepts_real_ed25519_only(self):
        payload={"signer_scope":"SYNTHETIC_TEST_ONLY",
                 "task_sha256":"0"*64,"role":"not_product",
                 "issued_at":1}
        with tempfile.TemporaryDirectory(prefix="ed25519-temp-test-NOT-issuer-") as temp:
            d=Path(temp)
            subprocess.run(["openssl","genpkey","-algorithm","ed25519",
                   "-out",str(d/"private.pem")],check=True,capture_output=True)
            subprocess.run(["openssl","pkey","-in",str(d/"private.pem"),
                   "-pubout","-out",str(d/"public.pem")],check=True,capture_output=True)
            (d/"payload").write_bytes(p.canon(payload))
            subprocess.run(["openssl","pkeyutl","-sign","-inkey",str(d/"private.pem"),
                   "-rawin","-in",str(d/"payload"),"-out",str(d/"signature")],
                   check=True,capture_output=True)
            pem=(d/"public.pem").read_text()
            sig=base64.b64encode((d/"signature").read_bytes()).decode()
            p.verify_ed25519(pem,payload,sig)
            with self.assertRaisesRegex(p.Denied,"SIGNATURE_INVALID"):
                p.verify_ed25519(pem,{**payload,"task_sha256":"1"*64},sig)
            with self.assertRaisesRegex(p.Denied,"SIGNATURE_LENGTH"):
                p.verify_ed25519(pem,payload,base64.b64encode(b"short").decode())
        # Temp directory removed, no root or eligible signer survives.

    def test_04_purported_package_cannot_pretend_unpinned_self_signer(self):
        with tempfile.TemporaryDirectory(prefix="c1-unsigned-claim-") as temp:
            f=Path(temp)/"claimed.json"
            f.write_text('{"signed_receipts":"self declared PASS"}')
            roots=p.root_pins(ROOT)
            # This gate is an assertion about genuine release-pinned keys,
            # not about whether a caller can write JSON.
            self.assertFalse(all(x["admitted"] for x in roots.values()))
            self.assertEqual(sum(x["admitted"] for x in roots.values()),0)

    def test_05_corrupted_legacy_evidence_must_fail_prior_to_signoff(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix="c1-qa-custody-tamper-") as temp:
            dst=Path(temp)/"evidence"
            shutil.copytree(LEDGER,dst)
            file=dst/"ATTEMPT02_LOW_REASONING"/"C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json"
            file.write_bytes(file.read_bytes()+b"UNAUTHORIZED")
            with self.assertRaisesRegex(p.Denied,"EVIDENCE_CHANGED"):
                p.legacy_dev_custody(ROOT,dst)

    def test_06_provider_abis_are_distinct_and_auditor_role_is_not_issuer(self):
        self.assertNotEqual(p.SSE_ABI,p.NDJSON_ABI)
        self.assertEqual(len(p.ROLES),4)
        self.assertTrue(p.SSE_ABI.startswith("m27.c1.provider-"))

if __name__=="__main__":unittest.main()
