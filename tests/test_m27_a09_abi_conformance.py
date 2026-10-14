"""Real source-level consumer tests; all identities and effects are synthetic Nonprod."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest

from knowledge_engine import m27_d28_dual_envelope_v1_experimental as d28
from knowledge_engine import m27_a09_abi_conformance as a09

H = "a" * 64
DATA = b'{"original":"unchanged"}'
AUTH_BYTES = b'{"test":"untrusted until independent verifier"}'
OPT = dict(record_id="a09-local", tenant_id="tenant1", run_id="run1",
           policy_generation=2, revocation_generation=1,
           checkpoint_seq=2, checkpoint_head=H)


def new(kind, body):
    return d28.make_new(new_record_kind=kind, new_record_namespace=d28.KIND_NS[kind],
                        body=body, **OPT)


def rev(gen=4):
    return new("revocation", {"exclusion_generation": gen,
                               "subject_ref": "subject1", "reason_code": "revoked"})


def bill(status="UNKNOWN"):
    return new("billing", {"charge_id": "charge-a09", "billing_status": status,
                            "usage_ref": "synthetic-ledger"})


def notice(seq=1, cursor=1, terminal=H, prev="b"*64):
    return new("postterminal", {
        "original_terminal_head_hash": terminal, "notice_seq": seq,
        "notice_prev_hash": prev, "client_cursor": cursor,
        "supersedes_segment_id": "segment1", "kind": "correction"})


class TestA09Conformance(unittest.TestCase):
    def setUp(self):
        self.identity = a09.IdentityScope("tenant1", "subject1", "product1",
                                          "write:a09", 4, "synthetic-registered-test-controller")
        self.claim = b'{"delegation":"NONPROD_FIXTURE"}'
        self.legacy = d28.make_legacy(
            raw_legacy=DATA, original_event_hash=a09.sha(DATA),
            required_sidecars=[{"namespace": "ar01v.authority",
                                "schema_version": d28.VERSION,
                                "body_sha256": a09.sha(AUTH_BYTES)}], **OPT)
        self.supported = {d28.LEGACY_NS: {"1.0.0"}, d28.NEW_NS: {"1.0.0"}}

    def test_x01_positive_old_bytes_preserved(self):
        v = a09.x01_reader(self.legacy, DATA, {"ar01v.authority": AUTH_BYTES}, self.supported)
        self.assertEqual(v["legacy_ref"]["raw_sha256"], a09.sha(DATA))
    def test_x01_negative_sidecar_substitution(self):
        with self.assertRaisesRegex(a09.Denied, "SIDECAR_BODY_MISMATCH"):
            a09.x01_reader(self.legacy, DATA, {"ar01v.authority": b"other"}, self.supported)
    def test_x01_negative_old_reader_bypass(self):
        with self.assertRaises(d28.D28Denied):
            a09.x01_reader(self.legacy, DATA, {"ar01v.authority": AUTH_BYTES},
                           self.supported, old_reader=True)
    def test_x01_negative_raw_tamper_and_version(self):
        with self.assertRaises(d28.D28Denied):
            a09.x01_reader(self.legacy, DATA + b"!", {"ar01v.authority": AUTH_BYTES},
                           self.supported)
        with self.assertRaises(d28.D28Denied):
            a09.x01_reader(self.legacy, DATA, {"ar01v.authority": AUTH_BYTES},
                           {d28.LEGACY_NS: {"0.9"}})
    def test_x01_missing_sidecar_rejected(self):
        with self.assertRaises(d28.D28Denied):
            a09.x01_reader(self.legacy, DATA, {}, self.supported)

    def verify_fixture(self, claim):
        return self.identity if claim == self.claim else None

    def x02(self, **kw):
        args = dict(tenant="tenant1", subject="subject1", audience="product1",
                    scope="write:a09", minimum_generation=2, revoked_generation=3)
        args.update(kw)
        return a09.x02_authority(self.claim, self.verify_fixture, **args)

    def test_x02_positive_injected_test_verifier(self):
        self.assertEqual(self.x02(), self.identity)
    def test_x02_negative_no_verifier_and_claim_flag(self):
        with self.assertRaises(a09.Denied):
            a09.x02_authority(self.claim, None, tenant="tenant1", subject="subject1",
                              audience="product1", scope="write:a09",
                              minimum_generation=1, revoked_generation=0)
        with self.assertRaises(a09.Denied):
            a09.x02_authority(b'{"valid":true}', self.verify_fixture,
                              tenant="tenant1", subject="subject1", audience="product1",
                              scope="write:a09", minimum_generation=1, revoked_generation=0)
    def test_x02_negative_scope_and_revocation(self):
        with self.assertRaisesRegex(a09.Denied, "SCOPE_MISMATCH"):
            self.x02(tenant="tenant-other")
        with self.assertRaisesRegex(a09.Denied, "REVOKED_CONSENT"):
            self.x02(revoked_generation=4)
    def test_x02_negative_self_issued(self):
        with self.assertRaisesRegex(a09.Denied, "UNQUALIFIED_ISSUER"):
            a09.x02_authority(self.claim, lambda _: a09.IdentityScope(
                "tenant1", "subject1", "product1", "write:a09", 4, "self-test"),
                tenant="tenant1", subject="subject1", audience="product1", scope="write:a09",
                minimum_generation=2, revoked_generation=0)

    def permit(self, action=b"send:a09", **kw):
        p = dict(permit_id="test-human-permit", action_sha256=a09.sha(action),
                 tenant_id="tenant1", subject="subject1", scope="write:a09",
                 expires_at=200, human_approval=True)
        p.update(kw)
        return p

    def test_x03_positive_exact_action(self):
        self.assertEqual(a09.x03_permit(self.permit(), b"send:a09", self.identity, 100),
                         "test-human-permit")
    def test_x03_negative_different_action(self):
        with self.assertRaisesRegex(a09.Denied, "ACTION_MISMATCH"):
            a09.x03_permit(self.permit(), b"send:OTHER", self.identity, 100)
    def test_x03_negative_expired_or_no_human(self):
        with self.assertRaisesRegex(a09.Denied, "EXPIRED"):
            a09.x03_permit(self.permit(), b"send:a09", self.identity, 200)
        with self.assertRaisesRegex(a09.Denied, "HUMAN_DENIED"):
            a09.x03_permit(self.permit(human_approval=False),
                           b"send:a09", self.identity, 100)
    def test_x03_negative_wrong_subject(self):
        with self.assertRaisesRegex(a09.Denied, "PERMIT_SCOPE"):
            a09.x03_permit(self.permit(subject="attacker"), b"send:a09", self.identity, 100)

    def test_x04_positive_durable_reservation(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath = os.path.join(td, "cas.db")
            db = a09.NonprodCAS(dbpath)
            db.reserve("permit1", b"action1")
            db.mark("permit1", "DONE")
            db.close()
            c = sqlite3.connect(dbpath)
            self.assertEqual(c.execute("SELECT status FROM outbox").fetchone()[0], "DONE")
            c.close()
    def test_x04_negative_duplicate_action_or_permit(self):
        with tempfile.TemporaryDirectory() as td:
            db = a09.NonprodCAS(os.path.join(td, "cas.db"))
            db.reserve("permit1", b"action1")
            with self.assertRaisesRegex(a09.Denied, "CAS_DUPLICATE"):
                db.reserve("permit2", b"action1")
            with self.assertRaisesRegex(a09.Denied, "CAS_DUPLICATE"):
                db.reserve("permit1", b"action2")
            db.close()
    def test_x04_negative_unknown_no_blind_retry_after_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "cas.db")
            db = a09.NonprodCAS(path)
            db.reserve("permit1", b"action1")
            db.mark("permit1", "UNKNOWN")
            db.close()
            db = a09.NonprodCAS(path)
            with self.assertRaisesRegex(a09.Denied, "CAS_DUPLICATE"):
                db.reserve("permit2", b"action1")
            with self.assertRaisesRegex(a09.Denied, "STATUS_NOT_RESERVABLE"):
                db.mark("permit1", "DONE")
            db.close()

    def test_x05_positive_notice_ack(self):
        self.assertEqual(a09.x05_notice(notice(), immutable_terminal_hash=H,
            expected_prev_hash="b"*64, expected_seq=1,
            authenticated_client_cursor=1)["body"]["kind"], "correction")
    def test_x05_negative_client_ack_mismatch(self):
        with self.assertRaisesRegex(a09.Denied, "UNACKED"):
            a09.x05_notice(notice(), immutable_terminal_hash=H,
                expected_prev_hash="b"*64, expected_seq=1,
                authenticated_client_cursor=0)
    def test_x05_negative_rewrite_and_notice_chain(self):
        with self.assertRaisesRegex(a09.Denied, "TERMINAL_REWRITTEN"):
            a09.x05_notice(notice(), immutable_terminal_hash="c"*64,
                expected_prev_hash="b"*64, expected_seq=1,
                authenticated_client_cursor=1)
        with self.assertRaisesRegex(a09.Denied, "CHAIN_BROKEN"):
            a09.x05_notice(notice(), immutable_terminal_hash=H,
                expected_prev_hash="c"*64, expected_seq=1,
                authenticated_client_cursor=1)

    def x06(self, wire=None, **kw):
        args = dict(previous_generation=3, rights_epoch=2, restore_quarantined=True,
                    acknowledged_controllers={"live-store", "backup"},
                    required_controllers={"live-store", "backup"})
        args.update(kw)
        return a09.x06_revocation(wire or rev(), **args)
    def test_x06_positive_monotonic_all_delete_ack(self):
        self.assertEqual(self.x06(), 4)
    def test_x06_negative_no_backup_ack(self):
        with self.assertRaisesRegex(a09.Denied, "MISSING_DELETE_ACK"):
            self.x06(acknowledged_controllers={"live-store"})
    def test_x06_negative_epoch_and_restoration(self):
        with self.assertRaisesRegex(a09.Denied, "NONMONOTONIC"):
            self.x06(previous_generation=4)
        with self.assertRaisesRegex(a09.Denied, "UNQUARANTINED"):
            self.x06(restore_quarantined=False)

    def test_x07_positive_unknown_billing_never_zeroed(self):
        r = a09.x07_billing(bill(), ledger_usage=2**40,
                           invoice=None, owner_aggregate=2**40 + 10)
        self.assertIsNone(r["invoice_amount"])
        self.assertEqual(r["owner_aggregate"], 2**40 + 10)
        self.assertFalse(r["invoice_verified"])
    def test_x07_positive_separate_trusted_finance_invoice_fixture(self):
        r = a09.x07_billing(bill("FINAL"), ledger_usage=100, owner_aggregate=100,
                           invoice={"source": "trusted_finance_controller", "amount": 3})
        self.assertEqual(r["invoice_amount"], 3)
    def test_x07_negative_missing_invoice_not_zero(self):
        with self.assertRaisesRegex(a09.Denied, "NOT_UNKNOWN"):
            a09.x07_billing(bill("FINAL"), ledger_usage=1,
                            invoice=None, owner_aggregate=1)
    def test_x07_negative_untrusted_invoice(self):
        with self.assertRaisesRegex(a09.Denied, "UNTRUSTED_INVOICE"):
            a09.x07_billing(bill("FINAL"), ledger_usage=1,
                            invoice={"source":"claim_from_app", "amount":0},
                            owner_aggregate=1)
    def test_x07_negative_bad_wire_status(self):
        with self.assertRaises(d28.D28Denied):
            bill("PAID_ZERO")

    def x08proof(self, **kw):
        p = {"verifier_id": "independent-test-verifier",
             "algorithm": "sha256-cited-spans-v1", "accepted": True,
             "source_ids": ["source-a"]}
        p.update(kw)
        return p
    def test_x08_positive_separate_test_verifier(self):
        a09.x08_independent_verification(self.x08proof(), executor_id="executor1",
                                         required_sources={"source-a"})
    def test_x08_negative_self_verifier(self):
        with self.assertRaisesRegex(a09.Denied, "SELF_VERIFICATION"):
            a09.x08_independent_verification(self.x08proof(verifier_id="executor1"),
                                             executor_id="executor1", required_sources={"source-a"})
    def test_x08_negative_unsupported_or_uncited(self):
        with self.assertRaisesRegex(a09.Denied, "UNSUPPORTED_VERIFIER"):
            a09.x08_independent_verification(self.x08proof(algorithm="unknown"),
                                             executor_id="executor1", required_sources={"source-a"})
        with self.assertRaisesRegex(a09.Denied, "UNSUPPORTED_CLAIM"):
            a09.x08_independent_verification(self.x08proof(source_ids=[]),
                                             executor_id="executor1", required_sources={"source-a"})

    def gen(self):
        return {"type":"generated","text":"Fact grounded in the cited source",
                "source_id":"source-a","source_sha256":H,"span":[0,32]}
    def terminal(self):
        return {"type":"terminal","text":"","source_id":"","source_sha256":"","span":[]}
    def progress(self):
        return {"type":"progress","text":"working","source_id":"",
                "source_sha256":"","span":[]}
    def test_x09_positive_grounded_before_terminal(self):
        a09.x09_evidence([self.progress(), self.gen(), self.terminal()],
                         source_manifest={"source-a": H})
    def test_x09_negative_progress_only_not_generated(self):
        with self.assertRaisesRegex(a09.Denied, "ONLY_PROGRESS"):
            a09.x09_evidence([self.progress(), self.terminal()],
                             source_manifest={"source-a": H})
    def test_x09_negative_missing_source_and_span(self):
        with self.assertRaisesRegex(a09.Denied, "UNGROUNDED"):
            a09.x09_evidence([self.gen(), self.terminal()], source_manifest={})
        invalid = self.gen()
        invalid["span"] = [1,1]
        with self.assertRaisesRegex(a09.Denied, "UNGROUNDED"):
            a09.x09_evidence([invalid, self.terminal()], source_manifest={"source-a": H})
    def test_x09_negative_generated_after_terminal(self):
        with self.assertRaisesRegex(a09.Denied, "POSTTERMINAL"):
            a09.x09_evidence([self.gen(), self.terminal(), self.gen()],
                             source_manifest={"source-a": H})


if __name__ == "__main__":
    unittest.main(verbosity=2)
