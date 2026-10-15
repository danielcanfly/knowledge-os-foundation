#!/usr/bin/env python3
"""Standalone read-only OS observer for A06 reversible sandbox state."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--run-id", required=True)
a = p.parse_args()
if not a.run_id.startswith("a06-") or "/" in a.run_id:
    raise SystemExit("UNAUTHORIZED_RUN_ID")
path = Path(__file__).resolve().parent / "state" / a.run_id / "observation.json"
if path.exists():
    raw = path.read_bytes()
    state = json.loads(raw.decode("utf-8"))
    result = {"run_id": a.run_id, "physical_file_exists": True,
              "observed_state": state, "sha256": hashlib.sha256(raw).hexdigest(),
              "absolute_path": str(path)}
else:
    result = {"run_id": a.run_id, "physical_file_exists": False,
              "observed_state": {"observation": "idle", "revision": 0},
              "sha256": None, "absolute_path": str(path)}
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
