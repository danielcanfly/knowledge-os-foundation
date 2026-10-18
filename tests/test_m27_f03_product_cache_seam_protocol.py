"""F03 new non-fixture Native Product Consumer protocol seam.

This is a local simulated upstream authority ONLY; never real IdP or verifier.
The HTTP tests traverse a genuine loopback TCP request, not CACHE04 fixture UI.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import http.client
import json
import threading
import unittest
import sys
import types
from pathlib import Path

# Isolate the new seam without initializing the unrelated M26 production runtime
# (which imports third-party dependencies such as httpx). No global app boot.
if "knowledge_engine" not in sys.modules:
    package = types.ModuleType("knowledge_engine")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "src" / "knowledge_engine")]
    sys.modules["knowledge_engine"] = package
from knowledge_engine import m27_f03_product_cache_seam_protocol as seam

H = lambda ch: ch * 64
SCHEMA = "m27.native-cache-client/v1"
NOW = dt.datetime(2026, 10, 18, 14, 30, tzinfo=dt.timezone.utc)


def z(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def body(mode="AUTO", question="Is the limit 40 units?", request_id="native-req-0001"):
    return {"schema_version": SCHEMA, "request_id": request_id,
            "cache_mode": mode, "question": question}


class SimulatedNativeAuthority:
    """TEST DOUBLE. External-looking subject identifiers are NOT real authentication."""

    def __init__(self):
        self.resolve_calls = 0
        self.recheck_calls = 0
        self.original = None
        self.next_lease = None
        self.override = None

    def resolve(self, request):
        self.resolve_calls += 1
        self.original = {
            "identity": {"tenant_id": "external-tenant-A",
                         "principal_id": "oidc-subject-023",
                         "auth_context_sha256": H("a"), "authenticated": True},
            "question": {"text": request["question"], "language": "en", "task_kind": "QA",
                         "intent_id": "policy-limit", "obligations": ["citation", "units"],
                         "negated": False, "numeric_literals": ["40"],
                         "temporal_scope": "STATIC", "answer_type": "FACT"},
            "source": {"corpus_id": "external-corpus", "corpus_revision": "r3",
                       "corpus_sha256": H("b"), "source_manifest_sha256": H("c"),
                       "acl_sha256": H("d"), "rights_sha256": H("e"),
                       "source_ids": ["document-009"]},
            "policy": {"policy_version": "native-policy-7", "policy_sha256": H("f"),
                       "verifier_version": "unqualified-in-test",
                       "embedding_version": "embed-2", "admission_version": "a3",
                       "revocation_epoch": 9},
            "cache_window": {"requested_at": z(NOW), "ttl_seconds": 60},
        }
        lease = {"tenant_id": "external-tenant-A", "principal_id": "oidc-subject-023",
                 "auth_context_sha256": H("a"), "source_manifest_sha256": H("c"),
                 "rights_sha256": H("e"), "revocation_epoch": 9,
                 "expires_at": z(NOW + dt.timedelta(minutes=5)),
                 "source_current": True, "rights_current": True, "acl_current": True}
        if self.override:
            self.override(self.original, lease)
        self.next_lease = copy.deepcopy(lease)
        return {"context": copy.deepcopy(self.original), "lease": lease}

    def recheck(self, request, identity, source):
        self.recheck_calls += 1
        return copy.deepcopy(self.next_lease)


def candidate(request, *, text=None):
    life = {"created_at": z(NOW - dt.timedelta(seconds=2)),
            "expires_at": z(NOW + dt.timedelta(seconds=45)),
            "ttl_seconds": 60, "revocation_epoch": 9, "state": "ACTIVE"}
    answer = "This is a sample nonreleasable candidate."
    question = copy.deepcopy(request["question"])
    if text is not None:
        question["text"] = text
    return {"schema_version": request["schema_version"], "identity": copy.deepcopy(request["identity"]),
            "question": question, "source": copy.deepcopy(request["source"]),
            "policy": copy.deepcopy(request["policy"]), "lifecycle": life,
            "answer": answer,
            "citations": [{"source_id": "document-009", "source_sha256": H("1"),
                           "revision": "r3", "citation_sha256": H("2")}],
            "provenance": {"answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                           "final_verifier_receipt_sha256": H("3"),
                           "source_verifier_receipt_sha256": H("4"),
                           "rights_receipt_sha256": H("5"),
                           "qualification_class": "FIXTURE_ONLY"}}


class NativeProductCacheSeamTests(unittest.TestCase):
    def setUp(self):
        self.auth = SimulatedNativeAuthority()
        self.store_creations = []
        self.consumer = seam.NativeProductCacheSeam(
            authority=self.auth, clock=lambda: NOW,
            store_factory=lambda: self.store_creations.append("CONSTRUCTED"))

    def test_native_identity_and_revocation_epoch_are_not_rewritten_to_fixture(self):
        result = self.consumer.consume(body())
        self.assertEqual(result["cache_status"], "DISABLED")
        self.assertEqual(result["proposed_mode_decision"], "LOOKUP_REQUIRED")
        self.assertEqual(self.auth.original["identity"]["principal_id"], "oidc-subject-023")
        self.assertEqual(self.consumer.last_envelope["identity"]["tenant_id"], "external-tenant-A")
        self.assertEqual(self.consumer.last_envelope["policy"]["revocation_epoch"], 9)
        self.assertNotIn("fixture", json.dumps(self.consumer.last_envelope).lower())
        self.assertFalse(result["answer_cache_hit_admitted"])
        self.assertFalse(result["answer_cache_write_admitted"])
        self.assertFalse(result["cache_io_performed"])
        self.assertEqual(self.store_creations, [])

    def test_bad_cache_mode_fails_before_authority_or_store(self):
        for bad in ("AUTO ", "auto", "HIT", "WRITE", None, True):
            with self.subTest(bad=bad), self.assertRaises(seam.NativeCacheProtocolError):
                self.consumer.consume(body(mode=bad, request_id="bad-mode-001"))
        self.assertEqual(self.auth.resolve_calls, 0)
        self.assertEqual(self.store_creations, [])

    def test_client_privileged_authority_fields_rejected(self):
        for extra in ("identity", "source", "policy", "lease", "verified_final"):
            request = body()
            request[extra] = {"authenticated": True}
            with self.subTest(extra=extra), self.assertRaises(seam.NativeCacheProtocolError):
                self.consumer.consume(request)
        self.assertEqual(self.auth.resolve_calls, 0)

    def test_auto_refresh_bypass_have_correct_proposals_but_no_answer_cache_io(self):
        expected = {"AUTO": ("DISABLED", "LOOKUP_REQUIRED"),
                    "REFRESH": ("DISABLED", "REGENERATE_NO_LOOKUP"),
                    "BYPASS": ("BYPASSED", "BYPASSED")}
        for mode, (status, proposal) in expected.items():
            with self.subTest(mode=mode):
                result = self.consumer.consume(body(mode=mode, request_id="native-mode-" + mode))
                self.assertEqual((result["cache_status"], result["proposed_mode_decision"]),
                                 (status, proposal))
                self.assertEqual(result["answer_cache_lookup_invocations"], 0)
                self.assertEqual(result["answer_cache_write_invocations"], 0)
        self.assertEqual(self.store_creations, [])

    def test_feature_enabled_true_must_fail_even_with_fake_verifier(self):
        with self.assertRaises(ValueError):
            seam.NativeProductCacheSeam(authority=self.auth, feature_enabled=True,
                                        clock=lambda: NOW, verifier=lambda _: True)
        self.assertEqual(self.store_creations, [])

    def test_replay_does_not_repeat_upstream_resolution(self):
        self.consumer.consume(body())
        with self.assertRaises(seam.NativeCacheProtocolError) as err:
            self.consumer.consume(body())
        self.assertEqual(err.exception.code, "REPLAY_DENIED")
        self.assertEqual(self.auth.resolve_calls, 1)

    def test_expired_or_noncurrent_source_denied(self):
        for mutation in ({"expires_at": z(NOW)}, {"source_current": False},
                         {"rights_current": False}, {"acl_current": False},
                         {"revocation_epoch": 8}, {"source_manifest_sha256": H("0")}):
            authority = SimulatedNativeAuthority()
            authority.override = lambda ctx, lease, mut=mutation: lease.update(mut)
            consumer = seam.NativeProductCacheSeam(authority=authority, clock=lambda: NOW)
            with self.subTest(mutation=mutation), self.assertRaises(seam.NativeCacheProtocolError):
                consumer.consume(body())
            self.assertIsNone(consumer.last_envelope)

    def test_expiry_and_revocation_races_fail_closed(self):
        for mutation in ({"revocation_epoch": 10}, {"expires_at": z(NOW)},
                         {"rights_current": False}, {"source_manifest_sha256": H("0")}):
            authority = SimulatedNativeAuthority()
            original_recheck = authority.recheck
            def changed(*args, mut=mutation):
                lease = original_recheck(*args)
                lease.update(mut)
                return lease
            authority.recheck = changed
            consumer = seam.NativeProductCacheSeam(authority=authority, clock=lambda: NOW)
            with self.subTest(mutation=mutation), self.assertRaises(seam.NativeCacheProtocolError):
                consumer.consume(body())
            self.assertEqual(authority.recheck_calls, 1)

    def test_cross_tenant_principal_negation_numeric_obligations_denied(self):
        self.consumer.consume(body())
        request = self.consumer.last_envelope
        c = candidate(request)
        self.assertEqual(seam.screen_untrusted_candidate(request, c, now=NOW),
                         "PROVER_REQUIRED_NOT_ADMITTED")
        for changed in (
            lambda c: c["identity"].update(tenant_id="external-tenant-B"),
            lambda c: c["identity"].update(principal_id="other-principal"),
            lambda c: c["question"].update(text="Is the limit 60 units?"),
            lambda c: c["question"].update(text="Is the limit not 40 units?"),
            lambda c: c["question"].update(obligations=["citation"]),
            lambda c: c["policy"].update(revocation_epoch=10),
            lambda c: c["source"].update(rights_sha256=H("0")),
            lambda c: c["lifecycle"].update(expires_at=z(NOW)),
        ):
            with self.subTest(changed=str(changed)):
                trial = copy.deepcopy(c)
                changed(trial)
                self.assertEqual(seam.screen_untrusted_candidate(request, trial, now=NOW),
                                 "DENY_CANDIDATE")

    def test_unqualified_source_and_question_cannot_fabricate_product_hits(self):
        def source_mismatch(ctx, lease):
            ctx["question"]["text"] = "wrong question"
        self.auth.override = source_mismatch
        with self.assertRaises(seam.NativeCacheProtocolError):
            self.consumer.consume(body())
        self.assertEqual(self.store_creations, [])

    def test_scope_digest_changes_with_principal_rights_source_epoch_versions_expiry_and_obligations(self):
        original = self.consumer.consume(body())["cache_scope_fingerprint_sha256"]
        def scope_change(field, value):
            authority = SimulatedNativeAuthority()
            def override(ctx, lease):
                if field in ("tenant_id", "principal_id", "auth_context_sha256"):
                    ctx["identity"][field] = value
                    lease[field] = value
                elif field in ("rights_sha256", "source_manifest_sha256"):
                    ctx["source"][field] = value
                    lease[field] = value
                elif field == "revocation_epoch":
                    ctx["policy"][field] = value
                    lease[field] = value
                elif field == "expires_at":
                    lease[field] = value
                elif field == "obligations":
                    ctx["question"][field] = value
                else:
                    ctx["policy"][field] = value
            authority.override = override
            return seam.NativeProductCacheSeam(
                authority=authority, clock=lambda: NOW).consume(body())["cache_scope_fingerprint_sha256"]
        mutations = {"tenant_id": "external-tenant-B", "principal_id": "oidc-other",
                     "auth_context_sha256": H("0"), "rights_sha256": H("0"),
                     "source_manifest_sha256": H("0"), "revocation_epoch": 10,
                     "policy_version": "native-policy-8", "verifier_version": "v8",
                     "embedding_version": "embed-3", "admission_version": "a4",
                     "expires_at": z(NOW + dt.timedelta(minutes=10)),
                     "obligations": ["citation", "units", "provenance"]}
        digests = []
        for key, value in mutations.items():
            with self.subTest(scope_dimension=key):
                fingerprint = scope_change(key, value)
                self.assertNotEqual(fingerprint, original)
                digests.append(fingerprint)
        self.assertEqual(len(set(digests)), len(digests))

    def test_semantic_metadata_cannot_disagree_with_client_question(self):
        for change in (
            lambda ctx: ctx["question"].update(negated=True),
            lambda ctx: ctx["question"].update(numeric_literals=["60"]),
        ):
            authority = SimulatedNativeAuthority()
            authority.override = lambda ctx, lease, change=change: change(ctx)
            with self.subTest(change=str(change)), self.assertRaises(seam.NativeCacheProtocolError):
                seam.NativeProductCacheSeam(authority=authority, clock=lambda: NOW).consume(body())

    def test_dynamic_and_nonqa_are_never_proposed_for_reusable_cache(self):
        for question_mutation in (
            {"task_kind": "CODING"}, {"temporal_scope": "LIVE"},
            {"temporal_scope": "RELATIVE"},
        ):
            authority = SimulatedNativeAuthority()
            authority.override = lambda ctx, lease, m=question_mutation: ctx["question"].update(m)
            result = seam.NativeProductCacheSeam(
                authority=authority, clock=lambda: NOW).consume(body())
            self.assertEqual(result["proposed_mode_decision"], "REFUSED_NON_QA")
            self.assertEqual(result["cache_status"], "DISABLED")
            self.assertFalse(result["cache_io_performed"])

    def test_native_http_nonfixture_envelope_and_fail_closed_client_mode(self):
        server = seam.NativeProductCacheLoopback(self.consumer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def post(data, token=None):
                con = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                headers = {"Content-Type": "application/json",
                           "X-Native-Seam-Token": token if token is not None else server.transport_token}
                con.request("POST", seam.NATIVE_PATH, body=json.dumps(data).encode(), headers=headers)
                r = con.getresponse()
                outcome = (r.status, json.loads(r.read()))
                con.close()
                return outcome
            status, response = post(body(request_id="native-http-001"))
            self.assertEqual(status, 200)
            self.assertEqual(response["cache_status"], "DISABLED")
            self.assertEqual(response["proposed_mode_decision"], "LOOKUP_REQUIRED")
            self.assertFalse(response["product_cache_enabled"])
            status, response = post(body(mode="LOOKUP", request_id="native-http-002"))
            self.assertEqual(status, 400)
            self.assertEqual(response["error"], "INVALID_CACHE_MODE")
            calls = self.auth.resolve_calls
            status, _ = post(body(request_id="native-http-003"), token="unauthenticated")
            self.assertEqual(status, 403)
            self.assertEqual(self.auth.resolve_calls, calls)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
