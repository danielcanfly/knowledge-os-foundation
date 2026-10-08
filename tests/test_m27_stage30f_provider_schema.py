import pytest
from knowledge_engine.m27_native_judge_provider import parse_verdict
def test_invalid_missing_field():
 with pytest.raises(ValueError): parse_verdict({"support_class":"DIRECT_SUPPORT","reason":"yes","evidence_references":["p1"]},["p1"])
def test_hallucinated_evidence():
 with pytest.raises(ValueError): parse_verdict({"support_class":"DIRECT_SUPPORT","confidence":1,"reason":"yes","evidence_references":["fake"]},["p1"])
def test_boolean_confidence():
 with pytest.raises(ValueError): parse_verdict({"support_class":"DIRECT_SUPPORT","confidence":True,"reason":"yes","evidence_references":["p1"]},["p1"])
