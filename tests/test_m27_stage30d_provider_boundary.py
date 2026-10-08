import importlib.util
import sys
import unittest
from pathlib import Path
path = Path(__file__).resolve().parents[1] / "src/knowledge_engine/m27_semantic_entailment.py"
spec = importlib.util.spec_from_file_location("m27_semantic_entailment_standalone", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
MaterialClaim = module.MaterialClaim
EvidencePassage = module.EvidencePassage
EntailmentVerdict = module.EntailmentVerdict
SupportLabel = module.SupportLabel
verify_material_claim = module.verify_material_claim
MISSING_PROVIDER_STATE = module.MISSING_PROVIDER_STATE

C = MaterialClaim("a", "Kubernetes schedules containers", 0, 32, "en", ("e1",))
E = [EvidencePassage("s", "l", "e1", "Kubernetes schedules containers", "en")]

class TestProviderBoundary(unittest.TestCase):
    def test_missing_provider_fail_closed(self):
        result=verify_material_claim(C,E)
        self.assertFalse(result.verified)
        self.assertEqual(result.reason,MISSING_PROVIDER_STATE)
    def test_citation_without_provider_not_support(self):
        self.assertEqual(verify_material_claim(C,E).label,SupportLabel.INSUFFICIENT)
    def test_missing_bound_source_rejected(self):
        class P:
            def verify(self,*args): raise AssertionError("must not call provider")
        self.assertFalse(verify_material_claim(C,[],P()).verified)
    def test_provider_exception_fail_closed(self):
        class P:
            def verify(self,*args): raise RuntimeError("down")
        self.assertFalse(verify_material_claim(C,E,P()).verified)
    def test_unverified_positive_rejected(self):
        class P:
            def verify(self,*args): return EntailmentVerdict(SupportLabel.DIRECT,False,("e1",),"dummy","")
        self.assertFalse(verify_material_claim(C,E,P()).verified)
    def test_unbound_passage_rejected(self):
        class P:
            def verify(self,*args): return EntailmentVerdict(SupportLabel.CLUSTERED,True,("other",),"dummy","")
        self.assertFalse(verify_material_claim(C,E,P()).verified)
    def test_cross_language_missing_provider_fail_closed(self):
        claim=MaterialClaim("b","Kubernetes 管理容器排程",0,17,"zh",("e1",))
        self.assertFalse(verify_material_claim(claim,E).verified)
    def test_topic_overlap_no_semantic_support(self):
        claim=MaterialClaim("c","Kubernetes provisions GPU",0,26,"en",("e1",))
        self.assertFalse(verify_material_claim(claim,[EvidencePassage("s","l","e1","Kubernetes payments for hotels", "en")]).verified)

if __name__ == "__main__": unittest.main()
