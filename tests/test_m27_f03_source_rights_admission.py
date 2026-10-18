"""F03 independent tests use actual B3-05 Git-tracked documents, not a copied
synthetic corpus or B3-06 fixture cache. All rights files are OS-local TEST scope.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'src' / 'knowledge_engine' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


f03 = _load('m27_f03_source_rights_admission')
abi = _load('m27_b0_cache_contracts')
DOC1 = "docs/m27/b3_h02_gateway_routing_successor_nonprod.md"
DOC2 = "docs/m27/b1_cache03_rights_integration.md"


class RealSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m27-f03-rights-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.registry = root / "local_lease.json"
        self.fence = root / "independent_local_fence.json"
        self.tenant = "owner-nonprod"
        self.principal = f"os-uid:{os.geteuid()}"
        self.now = int(time.time())
        self.doc = DOC1
        self.set_source(DOC1)
        self.reader = f03.LocalFirstPartySourceReader(REPO, self.registry, self.fence)

    def save(self, path, value):
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)

    def set_source(self, doc):
        git_blob = subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "blob", f"{f03.BASE_H02}:{doc}"],
            check=True, capture_output=True).stdout
        disk = (REPO / doc).read_bytes()
        self.assertEqual(disk, git_blob, "real disk source must equal pinned Git")
        self.doc = doc
        self.lease = {
            "scope": f03.SCOPE, "tenant": self.tenant,
            "principal": self.principal, "source_id": doc,
            "source_sha256": f03.sha(disk), "revision": f03.BASE_H02,
            "epoch": 1, "expires_at": self.now + 900,
            "retention_seconds": 60, "status": "ACTIVE",
            "rights_class": "owner-local-repo-read",
        }
        self.fence_data = {"source_id": doc, "minimum_epoch": 1}
        self.save(self.registry, self.lease)
        self.save(self.fence, self.fence_data)

    def read(self, **kwargs):
        return self.reader.read_source(self.doc, tenant=self.tenant,
                                       principal=self.principal, now=self.now,
                                       **kwargs)

    def excerpt(self, *, require_negation=False, obligations=None, numbers=None,
                line=None, quote=None, citation_doc=None,
                before_publish=None):
        source = self.read()
        self.assertTrue(source["candidate_only"], source)
        chosen = next((r for r in source["rows"] if
                       "MiniMax" in r["excerpt"] and "PRIMARY" in r["excerpt"]),
                      source["rows"][0])
        if line:
            chosen = next(r for r in source["rows"] if r["line"] == line)
        return self.reader.admit_excerpts(
            self.doc, tenant=self.tenant, principal=self.principal,
            excerpts=[{"source_id": citation_doc or self.doc,
                       "line": chosen["line"],
                       "quote": chosen["excerpt"] if quote is None else quote,
                       "line_sha256": chosen["line_sha256"]}],
            obligations=obligations or ["PRIMARY"],
            numbers=numbers, require_negation=require_negation,
            now=self.now, before_publish=before_publish)

    def revoke(self):
        self.lease["status"] = "REVOKED"
        self.lease["epoch"] += 1
        self.fence_data["minimum_epoch"] += 1
        self.save(self.registry, self.lease)
        self.save(self.fence, self.fence_data)

    def test_real_git_source_read_and_row_digests(self):
        result = self.read()
        self.assertEqual(result["decision"], "LOCAL_SOURCE_READ_ONLY_CANDIDATE")
        self.assertEqual(result["source_sha256"],
                         f03.sha((REPO / self.doc).read_bytes()))
        self.assertGreater(result["line_count"], 10)
        for row in result["rows"]:
            self.assertEqual(row["line_sha256"],
                             f03.sha(row["excerpt"].encode("utf-8")))
        self.assertFalse(result["product_admitted"])
        self.assertFalse(result["answer_cache_enabled"])

    def test_second_actual_first_party_file(self):
        self.set_source(DOC2)
        r = self.read()
        self.assertTrue(r["candidate_only"], r)
        self.assertNotEqual(r["source_sha256"],
                            f03.sha((REPO / DOC1).read_bytes()))

    def test_separate_process_independent_disk_readback(self):
        expected = self.read()
        code = ("import json,sys,importlib.util;from pathlib import Path;"
                "s=importlib.util.spec_from_file_location('f03',"
                "Path(sys.argv[1])/'src/knowledge_engine/m27_f03_source_rights_admission.py');"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                "r=m.LocalFirstPartySourceReader(Path(sys.argv[1]),"
                "Path(sys.argv[2]),Path(sys.argv[3]));"
                "print(json.dumps(r.read_source(sys.argv[4],"
                "tenant=sys.argv[5],principal=sys.argv[6],"
                "now=int(sys.argv[7])),sort_keys=True))")
        env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
        result = subprocess.run(
            [sys.executable, "-c", code, str(REPO), str(self.registry),
             str(self.fence), self.doc, self.tenant, self.principal,
             str(self.now)],
            env=env, capture_output=True, text=True, check=True)
        reread = json.loads(result.stdout)
        self.assertEqual(reread["source_sha256"], expected["source_sha256"])
        self.assertEqual(reread["rows"], expected["rows"])

    def test_wrong_tenant_and_principal(self):
        for t, p in [("other-tenant", self.principal),
                     (self.tenant, "different-principal"),
                     (self.tenant, "os-uid:999999")]:
            r = self.reader.read_source(self.doc, tenant=t,
                                        principal=p, now=self.now)
            self.assertTrue(r["decision"].startswith("DENY_"), r)
            self.assertFalse(r["product_admitted"])

    def test_revocation_before_read_and_stale_registry_restore(self):
        old = copy.deepcopy(self.lease)
        self.revoke()
        self.assertEqual(self.read()["decision"], "DENY_REVOKED")
        self.save(self.registry, old)
        self.assertEqual(self.read()["decision"],
                         "DENY_STALE_RIGHTS_OR_RESTORE")

    def test_revocation_during_source_read(self):
        out = self.read(mid_read=self.revoke)
        self.assertTrue(out["decision"].startswith("DENY_"))
        self.assertFalse(out["candidate_only"])

    def test_revocation_after_read_prepublication(self):
        initial = self.read()
        self.assertTrue(initial["candidate_only"])
        failed = self.excerpt(before_publish=self.revoke)
        self.assertEqual(failed["decision"],
                         "DENY_PREPUBLICATION_REVOKED_OR_CHANGED")

    def test_expiry_ttl_and_retention(self):
        self.lease["expires_at"] = self.now
        self.save(self.registry, self.lease)
        self.assertEqual(self.read()["decision"], "DENY_EXPIRED")
        self.lease["expires_at"] = self.now + 900
        self.lease["retention_seconds"] = 3601
        self.save(self.registry, self.lease)
        self.assertEqual(self.read()["decision"], "DENY_RETENTION_OR_TTL")
        self.lease["retention_seconds"] = 60
        self.lease["expires_at"] = self.now + 30
        self.save(self.registry, self.lease)
        self.assertEqual(self.read()["decision"], "DENY_RETENTION_OR_TTL")

    def test_wrong_source_digest_or_version(self):
        self.lease["source_sha256"] = "a" * 64
        self.save(self.registry, self.lease)
        self.assertEqual(self.read()["decision"], "DENY_STALE_METADATA")
        self.lease["source_sha256"] = f03.sha((REPO / self.doc).read_bytes())
        self.lease["revision"] = "previous-backup-version"
        self.save(self.registry, self.lease)
        self.assertEqual(self.read()["decision"],
                         "DENY_STALE_SOURCE_REVISION")

    def test_cross_source_citation_injection(self):
        bad = self.excerpt(citation_doc=DOC2)
        self.assertEqual(bad["decision"], "DENY_CROSS_SOURCE_INJECTION")

    def test_quote_and_obligation_mismatch(self):
        self.assertEqual(self.excerpt(quote="MiniMax is always primary")["decision"],
                         "DENY_QUOTE_NOT_SOURCE_EXACT")
        self.assertEqual(self.excerpt(obligations=["Product Issuer signed"])["decision"],
                         "DENY_ANSWER_OBLIGATION_MISMATCH")

    def test_numeric_negation_exact_evidence_constraints(self):
        self.assertEqual(self.excerpt(numbers=["34567890"])["decision"],
                         "DENY_NUMBER_MISMATCH")
        neg = self.excerpt(require_negation=True, obligations=["PRIMARY"])
        # Exact source quote may contain a negation, but never semantic final.
        self.assertIn(neg["decision"],
                      {"EXTRACTIVE_SOURCE_BOUND_CANDIDATE_ONLY",
                       "DENY_NEGATION_UNSUPPORTED"})
        self.assertFalse(neg["product_admitted"])

    def test_positive_exact_extractive_binds_cache01_source_shape(self):
        good = self.excerpt(obligations=["PRIMARY"])
        self.assertEqual(good["decision"],
                         "EXTRACTIVE_SOURCE_BOUND_CANDIDATE_ONLY")
        abi._parse_source(good["source"])  # shape only, NOT full Product auth
        self.assertEqual(good["cache_mode"], "BYPASS")
        self.assertFalse(good["verified_final"])
        self.assertFalse(good["answer_cache_hit"])
        self.assertFalse(good["answer_cache_write"])

    def test_missing_rights_or_fence_and_unlicensed_source(self):
        self.registry.unlink()
        self.assertTrue(self.read()["decision"].startswith("DENY_"))
        bad = self.reader.read_source("docs/m27/unknown.md",
                                      tenant=self.tenant,
                                      principal=self.principal, now=self.now)
        self.assertEqual(bad["decision"], "DENY_UNLICENSED_SOURCE")
        self.set_source(DOC1)
        self.fence.unlink()
        self.assertTrue(self.read()["decision"].startswith("DENY_"))

    def test_bad_registry_permission_and_product_license(self):
        self.registry.chmod(0o644)
        self.assertEqual(self.read()["decision"],
                         "DENY_UNTRUSTED_REGISTRY_PERMISSIONS")
        self.registry.chmod(0o600)
        self.lease["rights_class"] = "third-party-licensed-product"
        self.save(self.registry, self.lease)
        self.assertEqual(self.read()["decision"],
                         "DENY_UNLICENSED_OR_PRODUCT_SCOPE")

    def test_product_issuer_missing_fail_closed(self):
        self.assertEqual(
            f03.product_source_admission()["decision"],
            "DENY_MISSING_INDEPENDENT_PRODUCT_IDP_RIGHTS_ISSUER")
        self.assertFalse(f03.product_source_admission()["answer_cache_enabled"])
        self.assertFalse(f03.product_source_admission()["product_admitted"])


if __name__ == "__main__":
    unittest.main()


class RealOwnerA05CorpusTest(unittest.TestCase):
    """Real 11-doc A05 release; test-only revocation mutation uses copied tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m27-f03-a05-")
        self.addCleanup(self.tmp.cleanup)
        self.tmp_root = Path(self.tmp.name)
        self.repo = REPO
        self.fence = self.tmp_root / "source_epoch_fence.json"
        self.tenant = "owner-internal"
        self.principal = "os-uid:" + str(os.geteuid())
        self.write_fence(1)
        self.reader = f03.A05OwnerCorpusAdmission(
            self.repo, fence=self.fence)
        self.question = "PolicyEngine"
        self.obligations = ["PolicyEngine decides."]

    def write_fence(self, epoch: int):
        self.fence.write_text(json.dumps({
            "release_id": f03.A05_RELEASE_ID, "minimum_epoch": epoch
        }))
        self.fence.chmod(0o600)

    def read(self, **overrides):
        opts = dict(tenant=self.tenant, principal=self.principal,
                    obligations=self.obligations)
        opts.update(overrides)
        return self.reader.source_retrieval(
            self.question, **opts)

    def copied_reader(self):
        import shutil
        copy = self.tmp_root / "isolated_a05_test_copy"
        shutil.copytree(REPO / f03.A05_SOURCE, copy)
        reader = f03.A05OwnerCorpusAdmission(
            REPO, source_root=copy, fence=self.fence,
            isolated_test_copy=True)
        return reader, copy

    def test_real_owner_corpus_manifest_all_11_and_21_spans(self):
        corpus, release, release_sha = self.reader._pinned_release()
        self.assertEqual(len(corpus["docs"]), 11)
        self.assertEqual(len(corpus["chunks"]), 21)
        self.assertEqual(release["tenant_acl"], {"owner-internal": ["internal"]})
        self.assertEqual(release["source_manifest_sha256"], f03.A05_SOURCE_PIN)
        self.assertEqual(
            f03.sha((REPO / f03.A05_SOURCE / "corpus.json").read_bytes()),
            f03.A05_SOURCE_PIN)
        self.assertFalse(release["production_qualified"])
        self.assertFalse(release["source_release_ci_signed"])
        self.assertEqual(len(release_sha), 64)

    def test_genuine_native_source_retrieval_and_citation_bytes(self):
        x = self.read()
        self.assertEqual(x["decision"], "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE", x)
        self.assertEqual(x["source_manifest_sha256"], f03.A05_SOURCE_PIN)
        self.assertEqual(x["retrieval"],
                         "BM25_plus_local_distributional_rerank_NOT_product_vector")
        self.assertEqual(x["nonprod_file_mode"], "REAL_GIT_SOURCE")
        self.assertTrue(x["candidate_only"])
        self.assertGreaterEqual(len(x["sources"]), 1)
        for c in x["sources"]:
            data = (REPO / f03.A05_SOURCE / c["document"]).read_bytes()
            self.assertEqual(f03.sha(data), c["document_sha256"])
            self.assertEqual(f03.sha(data[c["byte_start"]:c["byte_end"]]),
                             c["excerpt_sha256"])
        abi._parse_source(x["source"])
        self.assertFalse(x["product_admitted"])
        self.assertFalse(x["answer_cache_enabled"])
        self.assertFalse(x["answer_cache_hit"])
        self.assertFalse(x["answer_cache_write"])
        self.assertFalse(x["native_consumer_joined"])

    def test_independent_child_process_real_owner_source_readback(self):
        program = (
            "import importlib.util,json,sys;from pathlib import Path;"
            "s=importlib.util.spec_from_file_location('f03',Path(sys.argv[1])/"
            "'src/knowledge_engine/m27_f03_source_rights_admission.py');"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "reader=m.A05OwnerCorpusAdmission(Path(sys.argv[1]),"
            "fence=Path(sys.argv[2]));"
            "r=reader.source_retrieval('PolicyEngine',tenant='owner-internal',"
            "principal=sys.argv[3],obligations=['PolicyEngine decides.']);"
            "print(json.dumps({'decision':r['decision'],"
            "'corpus_sha':r['source_manifest_sha256'],"
            "'passage_shas':[x['excerpt_sha256'] for x in r['sources']]},"
            "sort_keys=True))"
        )
        r = subprocess.run(
            [sys.executable, "-c", program, str(REPO), str(self.fence),
             self.principal], capture_output=True, check=True, text=True)
        new = json.loads(r.stdout)
        old = self.read()
        self.assertEqual(new["decision"], old["decision"])
        self.assertEqual(new["corpus_sha"], old["source_manifest_sha256"])
        self.assertEqual(new["passage_shas"],
                         [c["excerpt_sha256"] for c in old["sources"]])

    def test_wrong_tenant_principal_explicit_denials(self):
        for kwargs in [
            {"tenant": "foreign-tenant"},
            {"principal": "os-uid:0"},
            {"principal": "external-fake-principal"},
        ]:
            x = self.read(**kwargs)
            self.assertEqual(x["decision"],
                             "DENY_TENANT_OR_OS_PRINCIPAL_DENIED")
            self.assertFalse(x["candidate_only"])

    def test_source_stale_wrong_release_and_ttl(self):
        self.assertEqual(
            self.read(source_revision="different-revision")["decision"],
            "DENY_WRONG_RELEASE_OR_REVISION")
        self.assertEqual(self.read(release_id="other-release")["decision"],
                         "DENY_WRONG_RELEASE_OR_REVISION")
        self.assertEqual(self.read(ttl_seconds=3601)["decision"],
                         "DENY_TTL_TOO_LONG")
        expired = __import__("datetime").datetime.fromisoformat(
            "2027-01-12T00:00:00+00:00")
        self.assertEqual(self.read(now=expired)["decision"],
                         "DENY_RELEASE_FRESHNESS_TTL")

    def test_true_source_answer_obligation_safety(self):
        self.assertEqual(self.read(obligations=["Never trust a fake source"])["decision"],
                         "DENY_SOURCE_ANSWER_OBLIGATION_UNSUPPORTED")
        self.assertEqual(self.read(
            obligations=["PolicyEngine decides."],
            ttl_seconds=0)["decision"], "DENY_TTL_TOO_LONG")
        self.assertEqual(self.read(
            obligations=["PolicyEngine decides."],
            )["decision"], "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")

    def test_number_negation_and_unsupported_semantics(self):
        for question in [
            "What is not required by PolicyEngine?",
            "PolicyEngine should use 99 calls",
            "How does the 2029 policy work?",
        ]:
            x = self.reader.source_retrieval(
                question, tenant=self.tenant, principal=self.principal,
                obligations=["PolicyEngine"])
            self.assertEqual(
                x["decision"], "DENY_NEGATED_OR_NUMBER_QUERY_NEEDS_SEMANTIC_VERIFIER")
        unknown = self.read(obligations=["zzz_not_a_real_obligation"])
        self.assertEqual(unknown["decision"],
                         "DENY_SOURCE_ANSWER_OBLIGATION_UNSUPPORTED")

    def test_no_fence_denies_even_when_corpus_real(self):
        a = f03.A05OwnerCorpusAdmission(REPO)
        x = a.source_retrieval(self.question, tenant=self.tenant,
                              principal=self.principal,
                              obligations=self.obligations)
        self.assertEqual(x["decision"],
                         "DENY_REMOTE_EPOCH_NOT_AVAILABLE_LOCAL_HOLD")

    def test_fence_insecure_permissions_deny(self):
        self.fence.chmod(0o644)
        self.assertEqual(self.read()["decision"],
                         "DENY_UNTRUSTED_LOCAL_FENCE")

    def test_revocation_before_retrieval_nonprod_isolated_copy(self):
        reader, root = self.copied_reader()
        state = json.loads((root / "revocations.json").read_text())
        state["epoch"] += 1
        state["revoked_document_sha256"] = [
            f03.sha((root / "01_contracts.md").read_bytes())]
        (root / "revocations.json").write_text(json.dumps(state))
        self.write_fence(2)
        denied = reader.source_retrieval(
            "PolicyEngine", tenant=self.tenant, principal=self.principal,
            obligations=self.obligations)
        self.assertEqual(denied["decision"], "DENY_UNSUPPORTED_SOURCE_QUERY")

    def test_revocation_during_search_and_before_delivery(self):
        reader, root = self.copied_reader()
        state_path = root / "revocations.json"
        state = json.loads(state_path.read_text())
        def revoke():
            state["epoch"] += 1
            state["revoked_document_sha256"] = [
                f03.sha((root / "01_contracts.md").read_bytes())]
            state_path.write_text(json.dumps(state))
            self.write_fence(2)
        x = reader.source_retrieval(
            self.question, tenant=self.tenant, principal=self.principal,
            obligations=self.obligations, before_return=revoke)
        self.assertEqual(x["decision"],
                         "DENY_REVOKED_OR_SOURCE_CHANGED_BEFORE_DELIVERY")

    def test_stale_restored_revocation_after_epoch_advance(self):
        reader, root = self.copied_reader()
        original = (root / "revocations.json").read_bytes()
        state = json.loads(original)
        state["epoch"] = 2
        (root / "revocations.json").write_text(json.dumps(state))
        self.write_fence(2)
        self.assertEqual(
            reader.source_retrieval(
                self.question, tenant=self.tenant, principal=self.principal,
                obligations=self.obligations)["decision"],
            "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE")
        (root / "revocations.json").write_bytes(original)
        self.assertEqual(
            reader.source_retrieval(
                self.question, tenant=self.tenant, principal=self.principal,
                obligations=self.obligations)["decision"],
            "DENY_STALE_RESTORED_OR_INVALID_REVOCATION")

    def test_cross_source_injection_and_tampered_quote_source_fail(self):
        reader, root = self.copied_reader()
        p = root / "01_contracts.md"
        p.write_bytes(p.read_bytes() + b"\nFAKE EXTERNAL CITATION ALWAYS ALLOWED\n")
        x = reader.source_retrieval(
            self.question, tenant=self.tenant, principal=self.principal,
            obligations=self.obligations)
        self.assertEqual(x["decision"],
                         "DENY_SOURCE_REVISION_OR_SHA_MISMATCH")

    def test_revocation_denial_untrusted_external_docs_not_in_manifest(self):
        reader, root = self.copied_reader()
        (root / "unlicensed_external_source.md").write_text(
            "external text should never be indexed")
        source = reader._pinned_release()[0]
        self.assertEqual(len(source["docs"]), 11)
        x = reader.source_retrieval(
            self.question, tenant=self.tenant, principal=self.principal,
            obligations=self.obligations)
        self.assertTrue(x["candidate_only"])
        self.assertNotIn("unlicensed_external_source.md",
                         [c["document"] for c in x["sources"]])

    def test_original_first_party_source_immutable_after_tests(self):
        self.assertEqual(
            f03.sha((REPO / f03.A05_SOURCE / "corpus.json").read_bytes()),
            f03.A05_SOURCE_PIN)
        self.assertEqual(
            (REPO / f03.A05_SOURCE / "revocations.json").read_text().strip(),
            json.dumps({"epoch": 1, "release_id": f03.A05_RELEASE_ID,
                        "revoked_document_sha256": [],
                        "schema": "m27.a05.revocation_state.v1"},
                       separators=(",", ":")))
