import sys
import types
from pathlib import Path

w=Path('/home/ubuntu/LLM_Wiki-m27-semantic-entailment-30f')
sys.path.insert(0,str(w/'src'))
p=types.ModuleType('knowledge_engine');p.__path__=[str(w/'src/knowledge_engine')];sys.modules['knowledge_engine']=p
from knowledge_engine.m27_native_judge_provider import M27NativeJudgeAdapter
from knowledge_engine.m27_semantic_entailment import (
 EvidencePassage,
 MaterialClaim,
 verify_material_claim,
)

e=[EvidencePassage('s','l','p1','The API uses TLS.','en')]
c=MaterialClaim('c','The API uses TLS.',0,17,'en',('p1',))
def make(label,confidence=0.96,ids=['p1']): return {'support_class':label,'confidence':confidence,'reason':'reason','evidence_references':ids}
assert verify_material_claim(c,e,M27NativeJudgeAdapter(lambda c,e:make('DIRECT_SUPPORT'))).verified
for payload in [make('direct_support'),make('DIRECT_SUPPORT',0.1),make('DIRECT_SUPPORT',ids=['fake']),make('DIRECT_SUPPORT',ids=[]),make('TOPICAL_ONLY',ids=[]),make('CONTRADICTED',ids=[]),make('DIRECT_SUPPORT',True)]:
 assert not verify_material_claim(c,e,M27NativeJudgeAdapter(lambda c,e,payload=payload:payload)).verified
print('STAGE30F_INTERFACE_PASS 8 assertions')
