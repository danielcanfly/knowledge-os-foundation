#!/usr/bin/env python3
"""EXTERNAL DETERMINISTIC STUB. Not a model. JSONL candidate transport fixture."""
import json
import sys
import time
from pathlib import Path

mode = sys.argv[1]
manifest = json.loads(Path(sys.argv[2]).read_text())
texts = {
    "atlas-A": "The Atlas trial has two distinct review stages.",
    "delta-B": "The Delta notebook runs once every four hours.",
    "cedar-C": "The Cedar sandbox keeps five audit records.",
}
def candidate(index, source_id):
    m = manifest[source_id]
    return {"type": "claim", "index": index, "source_id": source_id,
            "source_sha256": m["sha256"], "fact_key": m["fact"]["key"],
            "span": [m["fact"]["start"], m["fact"]["end"]],
            "quote": m["fact"]["quote"], "text": texts[source_id]}
def push(item):
    sys.stdout.write(json.dumps(item, sort_keys=True) + "\n")
    sys.stdout.flush()

if mode == "refuse":
    push({"type":"refusal", "reason":"missing_support"})
    sys.exit(0)
a = candidate(1, "atlas-A")
b = candidate(2, "delta-B")
if mode == "forged_ref":
    a["source_id"] = "cedar-C"
elif mode == "forged_hash":
    a["source_sha256"] = "0" * 64
elif mode == "forged_span":
    a["span"][0] += 1
elif mode == "contradiction":
    a["text"] = "The Atlas trial has three review stages."
elif mode == "out_of_order":
    a["index"] = 2
    push(a)
    a["index"] = 1
elif mode == "repair":
    bad = dict(a)
    bad["text"] = "The Atlas trial has three review stages."
    push(bad)
push(a)
if mode == "duplicate":
    push(dict(a))
time.sleep(0.65 if mode == "slow" else 0.19)
if mode != "one":
    push(b)
time.sleep(0.7 if mode == "slow" else 0.45)
push({"type": "done"})
