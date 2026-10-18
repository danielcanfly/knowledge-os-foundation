"""New S03 cross-client / post-read clock / restored-epoch adversarial proof.

Actual source: frozen Owner A05 11 files / 21 span bytes. Remote identities
and rollback authority: NOT PRESENT; all client contexts are local test inputs.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "knowledge_engine"))
import m27_f03_source_rights_admission as f03
import m27_f03_client_restore_boundary as boundary

UTC = dt.timezone.utc


class S03RightsBoundaryNewCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m27-s03-cross-client-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fence = self.root / "owner_local_epoch.json"
        self._fence(1)
        self.reader = f03.A05OwnerCorpusAdmission(ROOT, fence=self.fence)
        self.ctx = {
            "client_id": "local-A", "session_nonce": "local-session-a",
            "tenant": "owner-internal",
            "principal": "os-uid:" + str(os.geteuid()),
            "channel": "owner-os-local-nonprod",
        }
        self.now = dt.datetime.now(UTC)
        self.candidate = self._retrieve(self.reader)
        self.assertEqual(self.candidate.get("decision"),
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",
                         self.candidate)

    def _fence(self, epoch):
        self.fence.write_text(json.dumps({
            "release_id": f03.A05_RELEASE_ID,
            "minimum_epoch": epoch
        }, sort_keys=True))
        self.fence.chmod(0o600)

    def _retrieve(self, reader):
        return reader.source_retrieval(
            "PolicyEngine", tenant="owner-internal",
            principal=self.ctx["principal"], obligations=["PolicyEngine decides."],
            now=self.now)

    def check_delivery(self, *, reader=None, candidate=None, origin=None,
                       recipient=None, issued_at=None, delivered_at=None,
                       lease_ttl_seconds=180, independent_epoch_floor=1,
                       expected_revision=f03.A05_REVISION):
        return boundary.check_local_candidate_delivery(
            reader if reader is not None else self.reader,
            candidate if candidate is not None else self.candidate,
            origin=origin if origin is not None else self.ctx,
            recipient=recipient if recipient is not None else self.ctx,
            issued_at=issued_at if issued_at is not None else self.now,
            delivered_at=delivered_at if delivered_at is not None else
            self.now + dt.timedelta(seconds=1),
            lease_ttl_seconds=lease_ttl_seconds,
            independent_epoch_floor=independent_epoch_floor,
            expected_revision=expected_revision)

    def _copy_reader(self):
        p = self.root / "isolated_source_copy"
        shutil.copytree(ROOT / f03.A05_SOURCE, p)
        return f03.A05OwnerCorpusAdmission(
            ROOT, fence=self.fence, source_root=p, isolated_test_copy=True), p

    def test_real_disk_11_docs_21_spans_and_delivery_only_candidate(self):
        corpus, release, _ = self.reader._pinned_release()
        self.assertEqual((len(corpus["docs"]), len(corpus["chunks"])), (11, 21))
        for doc in corpus["docs"]:
            disk = (ROOT / f03.A05_SOURCE / doc["filename"]).read_bytes()
            self.assertEqual(f03.sha(disk), doc["sha256"])
        for span in corpus["chunks"]:
            disk = (ROOT / f03.A05_SOURCE /
                    span["source_filename"]).read_bytes()
            self.assertEqual(
                f03.sha(disk[span["byte_start"]:span["byte_end"]]),
                span["quote_sha256"])
        receipt = self.check_delivery()
        self.assertEqual(receipt["decision"],
                         "LOCAL_DELIVERY_CONTEXT_BOUND_SOURCE_CANDIDATE_ONLY",
                         receipt)
        self.assertTrue(receipt["candidate_only"])
        self.assertFalse(receipt["answer_cache_hit"])
        self.assertFalse(receipt["answer_cache_write"])
        self.assertFalse(receipt["product_admitted"])
        self.assertFalse(receipt["remote_store_authorized"])
        self.assertEqual(receipt["source_manifest_sha256"], f03.A05_SOURCE_PIN)

    def test_cross_client_same_owner_uid_must_deny(self):
        recipient = {**self.ctx, "client_id": "local-B"}
        self.assertEqual(self.check_delivery(recipient=recipient)["decision"],
                         "DENY_CROSS_CLIENT_SESSION_OR_TENANT")

    def test_same_client_different_session_nonce_is_not_transferable(self):
        recipient = {**self.ctx, "session_nonce": "different-replay"}
        self.assertEqual(self.check_delivery(recipient=recipient)["decision"],
                         "DENY_CROSS_CLIENT_SESSION_OR_TENANT")

    def test_principal_and_tenant_mutations_denied_even_with_real_bytes(self):
        for altered in (
            {"tenant": "external-tenant"},
            {"principal": "other-product-principal"},
            {"channel": "remote-api"},
        ):
            recipient = {**self.ctx, **altered}
            self.assertEqual(
                self.check_delivery(recipient=recipient)["decision"],
                "DENY_CROSS_CLIENT_SESSION_OR_TENANT")

    def test_origin_cannot_claim_external_product_identity(self):
        origin = {**self.ctx, "principal": "oidc:forged-admin"}
        self.assertEqual(self.check_delivery(origin=origin)["decision"],
                         "DENY_NONLOCAL_OR_UNBOUND_IDENTITY")

    def test_delivery_after_local_lease_expiration_denied(self):
        delivered = self.now + dt.timedelta(seconds=181)
        self.assertEqual(
            self.check_delivery(delivered_at=delivered)["decision"],
            "DENY_EXPIRED_BEFORE_CLIENT_DELIVERY")

    def test_lease_boundary_exact_end_is_expired(self):
        self.assertEqual(
            self.check_delivery(delivered_at=self.now +
                                dt.timedelta(seconds=180))["decision"],
            "DENY_EXPIRED_BEFORE_CLIENT_DELIVERY")

    def test_delivery_after_source_expiration_not_allowed(self):
        expires = dt.datetime.fromisoformat(
            self.reader._pinned_release()[1]["expires_at"])
        self.assertEqual(
            self.check_delivery(issued_at=expires-dt.timedelta(seconds=3),
                                delivered_at=expires)["decision"],
            "DENY_SOURCE_RELEASE_EXPIRED_AT_DELIVERY")

    def test_new_local_lease_cannot_outlive_source_release(self):
        expires = dt.datetime.fromisoformat(
            self.reader._pinned_release()[1]["expires_at"])
        self.assertEqual(
            self.check_delivery(issued_at=expires-dt.timedelta(seconds=120),
                                delivered_at=expires-dt.timedelta(seconds=119),
                                lease_ttl_seconds=180)["decision"],
            "DENY_SOURCE_RELEASE_EXPIRED_AT_DELIVERY")

    def test_wrong_source_revision_does_not_transfer(self):
        self.assertEqual(self.check_delivery(
            expected_revision="unaccepted-next-release")["decision"],
            "DENY_SOURCE_RELEASE_VERSION_MISMATCH")

    def test_rollback_of_revocations_and_local_fence_still_needs_external_floor(self):
        reader, root = self._copy_reader()
        original = (root / "revocations.json").read_bytes()
        changed = json.loads(original)
        changed["epoch"] = 2
        (root / "revocations.json").write_text(json.dumps(changed))
        self._fence(2)
        candidate_2 = self._retrieve(reader)
        self.assertEqual(candidate_2["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        self.assertEqual(
            self.check_delivery(reader=reader, candidate=candidate_2,
                                independent_epoch_floor=2)["decision"],
            "LOCAL_DELIVERY_CONTEXT_BOUND_SOURCE_CANDIDATE_ONLY")
        (root / "revocations.json").write_bytes(original)
        self._fence(1)
        restored = self._retrieve(reader)
        self.assertEqual(restored["decision"],
                         "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        self.assertEqual(
            self.check_delivery(reader=reader, candidate=restored,
                                independent_epoch_floor=2)["decision"],
            "DENY_RESTORED_BELOW_INDEPENDENT_EPOCH_FLOOR")

    def test_changed_epoch_between_read_and_delivery_is_denied(self):
        reader, root = self._copy_reader()
        candidate = self._retrieve(reader)
        rec = json.loads((root / "revocations.json").read_text())
        rec["epoch"] = 2
        (root / "revocations.json").write_text(json.dumps(rec))
        self._fence(2)
        self.assertEqual(
            self.check_delivery(reader=reader, candidate=candidate)["decision"],
            "DENY_RIGHTS_REVOCATION_CHANGED")

    def test_citation_must_be_actual_frozen_span_not_just_filename_and_sha(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["sources"][0]["byte_end"] -= 1
        self.assertEqual(self.check_delivery(candidate=candidate)["decision"],
                         "DENY_CITATION_NOT_FROZEN_SPAN")

    def test_trusted_disk_file_change_between_retrieval_and_delivery_denied(self):
        reader, root = self._copy_reader()
        candidate = self._retrieve(reader)
        target = root / candidate["sources"][0]["document"]
        target.write_bytes(target.read_bytes() + b"\nAFTER-READ-INJECTION\n")
        self.assertEqual(
            self.check_delivery(reader=reader, candidate=candidate)["decision"],
            "DENY_SOURCE_REVISION_OR_SHA_MISMATCH")

    def test_cache_write_or_claimed_product_auth_is_rejected(self):
        for key in ("answer_cache_hit", "answer_cache_write",
                    "product_admitted", "product_authenticated",
                    "independent_issuer", "verified_final"):
            fake = copy.deepcopy(self.candidate)
            fake[key] = True
            self.assertEqual(
                self.check_delivery(candidate=fake)["decision"],
                "DENY_NOT_SAFE_LOCAL_CANDIDATE", key)

    def test_missing_external_grant_cannot_be_promoted_by_boolean_or_receipt(self):
        for claim in ({}, {"signed": True, "controller": "owner"},
                      {"jwt": "fabricated", "jwks": "local-test"}):
            state = boundary.remote_product_rights_decision(claim)
            self.assertEqual(state["product_rights_status"],
                             "PRODUCT_RIGHTS_HOLD")
            self.assertFalse(state["g04_remote_authorized"])
            self.assertFalse(state["answer_cache_hit"])
            self.assertFalse(state["answer_cache_write"])

    def test_untrusted_missing_client_binding_or_epoch_anchor_denied(self):
        missing = {k:v for k,v in self.ctx.items() if k != "session_nonce"}
        self.assertEqual(self.check_delivery(origin=missing)["decision"],
                         "DENY_MISSING_OR_EXTRA_CLIENT_BINDING")
        self.assertEqual(self.check_delivery(
            independent_epoch_floor=0)["decision"],
            "DENY_MISSING_MONOTONIC_EPOCH_FLOOR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
