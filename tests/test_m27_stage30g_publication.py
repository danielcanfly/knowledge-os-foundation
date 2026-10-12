"""Offline fail-closed checks for Stage30G partial integration."""
import unittest

from knowledge_engine.m27_agent_product_runtime import build_agent_native_product_answer
from knowledge_engine.m27_semantic_entailment import EntailmentVerdict, SupportLabel

QUESTION = "How does Kubernetes schedule inference containers?"
TEXT = ("Kubernetes schedules model inference containers across compute nodes and coordinates "
        "deployment health across multiple services. It can restart failed application pods "
        "after health probes detect issues, distribute workloads with scheduler constraints, "
        "and let operators specify resource requests and limits. Teams typically configure "
        "autoscaling through additional components while observing workload availability "
        "and cluster capacity. These controls support service operations but do not "
        "automatically guarantee zero downtime or unrestricted GPU sharing.")
EVIDENCE = [{"passage_text": TEXT, "section_id": "k8s-ops", "source_id": "k8s-docs",
             "artifact_key": "knowledge/kubernetes", "evidence_id": "k8s-1"},
            {"passage_text": TEXT, "section_id": "k8s-guide", "source_id": "cloud-guide",
             "artifact_key": "knowledge/cloud", "evidence_id": "k8s-2"}]

class Provider:
    def __init__(self, label, verified=True):
        self.label = label
        self.verified = verified
        self.calls = []
    def verify(self, claim, evidence):
        self.calls.append((claim, evidence))
        return EntailmentVerdict(self.label, self.verified,
            (evidence[0].passage_id,) if self.verified else (),
            "offline-test-provider", "synthetic-test-verdict")

class Publication(unittest.TestCase):
    def test_missing_provider_fail_closed(self):
        class Broken:
            def verify(self, claim, evidence):
                raise RuntimeError("unavailable")
        r = build_agent_native_product_answer(question=QUESTION, intent_class="factual",
            evidence=EVIDENCE, semantic_provider=Broken())
        self.assertFalse(r.publishable)
        self.assertNotIn("stream_publishable", [x["type"] for x in r.state_events])

    def test_topical_only_rejected(self):
        r = build_agent_native_product_answer(question=QUESTION, intent_class="factual",
            evidence=EVIDENCE, semantic_provider=Provider(SupportLabel.UNSUPPORTED, False))
        self.assertFalse(r.publishable)
        self.assertNotIn("stream_publishable", [x["type"] for x in r.state_events])

    def test_contradicted_rejected(self):
        r = build_agent_native_product_answer(question=QUESTION, intent_class="factual",
            evidence=EVIDENCE, semantic_provider=Provider(SupportLabel.CONTRADICTED, False))
        self.assertFalse(r.publishable)

    def test_direct_requires_provider_verdict(self):
        provider = Provider(SupportLabel.DIRECT)
        r = build_agent_native_product_answer(question=QUESTION, intent_class="factual",
            evidence=EVIDENCE, semantic_provider=provider)
        self.assertTrue(provider.calls)
        self.assertTrue(all(call[1] for call in provider.calls))
        # Even positive mock verdicts cannot overcome the publication thin-answer gate.
        self.assertFalse(r.publishable)
        self.assertIn("PRODUCT_THIN_SURFACE", r.gap_taxonomy)

    def test_unverified_direct_rejected(self):
        r = build_agent_native_product_answer(question=QUESTION, intent_class="factual",
            evidence=EVIDENCE, semantic_provider=Provider(SupportLabel.DIRECT, False))
        self.assertFalse(r.publishable)

if __name__ == "__main__":
    unittest.main()
