import importlib.util
import sys
import types
import unittest
from pathlib import Path

root=Path(__file__).resolve().parents[1] / "src/knowledge_engine"
pkg=types.ModuleType("knowledge_engine")
pkg.__path__=[str(root)]
sys.modules["knowledge_engine"]=pkg
for name in ("m27_semantic_entailment","m27_native_literal_provider"):
    spec=importlib.util.spec_from_file_location("knowledge_engine."+name,root/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
from knowledge_engine.m27_native_literal_provider import LiteralBaselineProvider
from knowledge_engine.m27_semantic_entailment import (
    EvidencePassage,
    MaterialClaim,
    SupportLabel,
    verify_material_claim,
)


class CalibrationTests(unittest.TestCase):
    def verdict(self, claim, evidence, claim_language="en", evidence_language="en"):
        passage=EvidencePassage("source","locator","p",evidence,evidence_language)
        material=MaterialClaim("claim",claim,0,len(claim),claim_language,("p",))
        return verify_material_claim(material,[passage],LiteralBaselineProvider())

    def test_literal_identity_positive(self):
        self.assertEqual(self.verdict("The API uses TLS.","The API uses TLS.").label,SupportLabel.DIRECT)

    def test_topical_rejected(self):
        self.assertFalse(self.verdict("Kubernetes supports payments.","Kubernetes manages containers.").verified)

    def test_contradiction_rejected(self):
        self.assertFalse(self.verdict("Anonymous login allowed.","Anonymous login forbidden.").verified)

    def test_paraphrase_fails_closed(self):
        self.assertFalse(self.verdict("Traffic is encrypted.","TLS protects connections.").verified)

    def test_cross_language_fails_closed(self):
        self.assertFalse(self.verdict("TLS is used.","使用 TLS。","en","zh").verified)

    def test_missing_text_fails_closed(self):
        self.assertFalse(self.verdict("The API uses TLS.","").verified)
