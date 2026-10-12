from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

p=Path(__file__).resolve().parents[1]/"src/knowledge_engine/m27_agent_product_runtime.py"
spec=importlib.util.spec_from_file_location("m27_30b_native",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def item(text,loc):return {"section_id":loc,"source_identity":loc,"passage_text":text}
q="How does Kubernetes help AI infrastructure?"
bad=item("x402 payment protocol hotel alliance commercial platform","bad")
good=item("Kubernetes orchestrates container workloads and GPU services","good")
assert not m._topic_supported(q,bad)
assert m._topic_supported(q,good)
selected=m._select_evidence(q,[bad,good],broad=False)
assert len(selected)==1 and selected[0]["section_id"]=="good"
assert not m._select_evidence(q,[bad],broad=True)
assert all("run_owner_arbitrary_query" not in p.read_text() and "synthesize_and_verify" not in p.read_text() for _ in [0])
print("STAGE30B_TARGETED_STATIC_PASS: 5 assertions")
