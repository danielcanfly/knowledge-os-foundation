from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/knowledge_engine/m27_agent_product_runtime.py"
spec = importlib.util.spec_from_file_location("m27_stage30c_runtime", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

def item(text, section="s", source="source"):
    return {"passage_text":text,"section_id":section,"source_id":source}

def test_cross_topic_rejection():
    q = "What does Kubernetes do for AI infrastructure?"
    bad = item("x402 payment rails for hotel alliances and commercial platforms.")
    assert not mod._topic_supported(q,bad)
    assert not mod._claim_units(q,bad)

def test_citation_existence_not_semantic_support():
    q = "What does Kubernetes do for AI infrastructure?"
    good = item("Kubernetes schedules inference containers on nodes and manages scaling in AI infrastructure.")
    assert not mod._semantic_support(q,"Kubernetes guarantees zero downtime and GPU isolation.",good)

def test_no_weak_breadth_fill():
    q = "What does Kubernetes do for AI infrastructure?"
    good = item("Kubernetes schedules inference containers on nodes and manages scaling in AI infrastructure.","k8s","infra")
    bad = item("Hotel loyalty and x402 payment integration across commercial platforms.","hotel","commerce")
    assert mod._select_evidence(q,[bad,good],broad=True) == (good,)

def test_specific_grounded_extract():
    q = "What does Kubernetes do for AI infrastructure?"
    good = item("Kubernetes schedules inference containers on nodes and manages scaling in AI infrastructure.")
    units = mod._claim_units(q,good)
    assert units and "schedules inference containers" in units[0][0]
    assert mod._semantic_support(q,units[0][0],good)

def test_thin_cited_rejection():
    assert not mod.strict_product_success({"status":"owner_only_cited_answer","thin_cited_answer":True})

def test_no_m26_composer_delegation():
    text = SRC.read_text()
    assert "synthesize_and_verify" not in text and "run_owner_arbitrary_query" not in text

if __name__ == "__main__":
    for name, obj in sorted(globals().items()):
        if name.startswith("test_") and callable(obj):
            obj()
            print("PASS",name)

