"""Fail-closed M27 narrow semantic entailment judge adapter. No answer composition."""
import json
from .m27_semantic_entailment import EntailmentVerdict, SupportLabel
LABELS={"DIRECT_SUPPORT":SupportLabel.DIRECT,"PARAPHRASE_SUPPORT":SupportLabel.PARAPHRASE,"CLUSTER_SUPPORT":SupportLabel.CLUSTERED,"TOPICAL_ONLY":SupportLabel.UNSUPPORTED,"UNSUPPORTED":SupportLabel.UNSUPPORTED,"THIN_CITED_NEGATIVE":SupportLabel.UNSUPPORTED,"CONTRADICTED":SupportLabel.CONTRADICTED,"INSUFFICIENT_PROVIDER_CAPABILITY":SupportLabel.INSUFFICIENT}
def parse_verdict(raw,allowed):
 if isinstance(raw,str): raw=json.loads(raw)
 if not isinstance(raw,dict) or set(raw)!={"support_class","confidence","reason","evidence_references"}: raise ValueError("schema_keys")
 k=raw["support_class"]; c=raw["confidence"]; r=raw["evidence_references"]; why=raw["reason"]
 if k not in LABELS or type(c) not in (float,int) or not 0<=c<=1 or not isinstance(why,str) or not why.strip() or len(why)>500 or not isinstance(r,list) or len(set(r))!=len(r) or any(not isinstance(x,str) or x not in allowed for x in r): raise ValueError("schema_fields")
 return raw
class M27NativeJudgeAdapter:
 def __init__(self,invoke,threshold=0.85): self.invoke=invoke;self.threshold=threshold
 def verify(self,claim,evidence):
  allowed=[e.passage_id for e in evidence]
  try:
   result=parse_verdict(self.invoke(claim,evidence),allowed)
   label=LABELS[result["support_class"]]
   ok=label in (SupportLabel.DIRECT,SupportLabel.PARAPHRASE,SupportLabel.CLUSTERED) and result["confidence"]>=self.threshold and bool(result["evidence_references"])
   return EntailmentVerdict(label if ok or label not in (SupportLabel.DIRECT,SupportLabel.PARAPHRASE,SupportLabel.CLUSTERED) else SupportLabel.INSUFFICIENT,ok,tuple(result["evidence_references"]) if ok else (),"m27-minimax-nli",result["reason"])
  except Exception: return EntailmentVerdict(SupportLabel.INSUFFICIENT,False,(),"m27-minimax-nli","schema_or_provider_error")
