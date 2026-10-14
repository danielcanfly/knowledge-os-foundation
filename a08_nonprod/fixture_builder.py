"""One-time reproducible, owner-firstparty-only fixture builder. No external sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SOURCES = (
    "README.md",
    "docs/m27/handoffs/ADAPTIVE_POLICY_HANDOFF.md",
    "docs/m27/handoffs/LEARNING_META_HANDOFF.md",
    "docs/m27/m27_w3_ar07_compute_budget_v1_experimental_receipts.md",
    "docs/m27/research/47_adaptive_planner_compute_report.md",
    "docs/m27/research/50_learning_meta_harness_loop_report.md",
    "docs/m27/research/stage11_autonomous_agent_learning_report.md",
)

def build():
    pool = []
    for file in SOURCES:
        raw = (ROOT / file).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        for line in raw.decode().splitlines():
            quote = line.strip()
            if not 35 <= len(quote) <= 175 or quote.startswith(("#", "|", "[")):
                continue
            pool.append({"path": file, "sha256": sha, "quote": quote})
    assert len(pool) > 120
    seen = set()
    unique = []
    for entry in pool:
        if entry["quote"] not in seen:
            unique.append(entry)
            seen.add(entry["quote"])
    assert len(unique) > 90
    # Interleave owned documents deterministically to avoid exhausting one source.
    unique.sort(key=lambda row: hashlib.sha256(row["quote"].encode()).hexdigest())
    cases = []
    pos = 0
    for i in range(48):
        research = i % 2 == 1
        first = unique[pos]
        pos += 1
        sources = [first]
        if research:
            while unique[pos]["path"] == first["path"]:
                pos += 1
            sources.append(unique[pos])
            pos += 1
        split = "development" if i < 32 else "independent_holdout"
        kind = "RESEARCH" if research else "QA"
        names = " and ".join(s["path"].split("/")[-1] for s in sources)
        cases.append({
            "id": "A08-" + str(i + 1).zfill(3), "split": split, "kind": kind,
            "question": f"Using immutable firstparty evidence from {names}, return verified excerpts for task {i + 1}.",
            "source_evidence": sources, "needed_rounds": len(sources),
            "quota_calls": 3 if research else 2,
            "max_fee_usd_per_task": 0.0018,
            "source_rights": "OWNER_FIRSTPARTY_CODEBASE",
        })
    obj = {
        "abi": "m27-a08-firstparty-workload/v1",
        "source_base_commit": "216f912994d20d134b1c8af50f7b2dd1a1c89a15",
        "sealed_holdout_note": "16 predeclared records; separate quote and IDs; not externally blind",
        "scenario": "fixture deterministic tokens + modeled latency; not live LLM",
        "cases": cases,
    }
    out = HERE / "workload.json"
    out.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"count": len(cases), "development": 32, "holdout": 16,
                      "source_quote_count": sum(len(c["source_evidence"]) for c in cases),
                      "workload_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                      "paths": list(SOURCES)}, sort_keys=True))


if __name__ == "__main__":
    build()
