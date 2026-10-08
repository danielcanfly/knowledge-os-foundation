"""Deterministic provenance identity contract tests, no external provider calls."""
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m27_provenance", ROOT / "src/knowledge_engine/m27_provenance_obligations.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows = list(csv.DictReader((ROOT / "docs/m27/research/91_m27_direct100_provenance_obligation_diagnosis.csv").open()))
assert len(rows) == 8
for row in rows:
    result = module.retrieve_provenance_identity(row["query"])
    assert result is not None and len(result) == 1
    item = result[0]
    assert item["source_id"] == row["source_id"]
    assert row["available_retrieved_at_evidence"] in item["passage_text"]
    assert row["available_source_commit_evidence"] in item["passage_text"]
    assert row["available_release_identity_evidence"] in item["passage_text"]
    assert all(s in item["passage_text"].casefold() for s in ("retrieved-at", "source-commit", "release"))
    assert len(item["passage_text"].split()) >= 45
assert module.retrieve_provenance_identity("What exact production traffic volume did the harness service serve?") is None
assert module.retrieve_provenance_identity("Before treating accepted claim set for harness as current, which retrieved-at/source-commit/release identities from source source_m23_4_harness_proposed_concepts must be checked?") is None
assert module.retrieve_provenance_identity('Before treating the accepted claim set for "absent topic" as current, which retrieved-at/source-commit/release identities from source "source_m23_4_harness_proposed_concepts" must be checked?') == []
assert module.retrieve_provenance_identity('Before treating the accepted claim set for "harness" as current, which retrieved-at/source-commit/release identities from source "source_blog_agent_planning_strategies" must be checked?') == []
print("PASS: 8 provenance mappings, evidence assertions, and 4 negatives")
