#!/usr/bin/env python3
"""Independent, read-only outcome verifier. Does not import the workload runner."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

HOME = Path(__file__).resolve().parent
DATA = HOME / "data"

def sha(b):
    return hashlib.sha256(b).hexdigest()

def verify(db, run_id):
    db = Path(db)
    uri = f"file:{db}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        record = con.execute("SELECT stage,contract FROM runs WHERE run_id=?", (run_id,)).fetchone()
        assert record and record[0] == "VERIFIED", "RUN_NOT_VERIFIED"
        c = json.loads(record[1])
        assert c["tenant"] == "tenant-a" and c["run_id"] == run_id, "RUN_IDENTITY"
        assert c["sources"] == ["CHARTER", "DELIVERY", "I37_ACCEPTANCE"], "SOURCE_SCOPE"
        revoked = con.execute("SELECT source_id FROM revoked").fetchall()
        assert not set(x[0] for x in revoked).intersection(c["sources"]), "REVOKED_SOURCE"
        row = con.execute("SELECT before_state,after_state,attempts,status FROM actions WHERE run_id=?",
                          (run_id,)).fetchone()
        assert row and row[2] == 1 and row[3] in ("APPLIED", "RECONCILED"), "ACTION_RECEIPT"
        assert json.loads(row[0]) == {"observation": "idle", "revision": 0}, "ACTION_BEFORE"
        obs = json.loads((HOME / "state" / run_id / "observation.json").read_text("utf-8"))
        assert obs == json.loads(row[1]), "INDEPENDENT_OUTCOME_OBSERVATION"
        assert obs == {"observation": "reviewed", "revision": 1, "run_id": run_id}, "UNEXPECTED_ACTION"
        events = [x[0] for x in con.execute("SELECT event FROM journal WHERE run_id=? ORDER BY seq", (run_id,))]
        assert events[0] == "ADMITTED" and "PLAN_PERSISTED" in events, "JOURNAL_PLAN_MISSING"
        assert events.count("SOURCE_READ") == 3 and events.count("EFFECT_ATTEMPT_PERSISTED_BEFORE_IO") == 1, "JOURNAL_CARDINALITY"
        assert events[-1] == "INDEPENDENTLY_VERIFIABLE_OUTCOME", "TERMINAL_EVENT"
        assert "ARTIFACT_VERIFIED" in events and "ACTION_INTENT_PERSISTED" in events, "JOURNAL_CHAIN"
        art = (HOME / "state" / run_id / "research.json")
        report = json.loads(art.read_text("utf-8"))
        md = art.with_suffix(".md").read_text("utf-8")
        assert report["run_id"] == run_id and report["tenant"] == "tenant-a", "ARTIFACT_OWNER"
        assert report["source_ids"] == c["sources"], "ARTIFACT_SCOPE"
        assert len(report["evidence"]) == 3 and len(report["findings"]) == 3, "RESEARCH_COVERAGE"
        manifest = json.loads((DATA / "source_manifest.json").read_text("utf-8"))
        expected_needles = {"CHARTER": "Task/Outcome 優先於 Chat 回答",
                            "DELIVERY": "I37 is already **DONE in isolated NONPROD scope**.",
                            "I37_ACCEPTANCE": "**AR08 same-TaskContract persisted coding outcome**"}
        ids = set()
        for e in report["evidence"]:
            sid = e["source_id"]
            assert sid in expected_needles and sid not in ids, "SOURCE_DUPLICATED"
            ids.add(sid)
            raw = (DATA / "sources" / (sid + ".md")).read_bytes()
            assert sha(raw) == manifest[sid]["sha256"] == e["sha256"], "SOURCE_HASH"
            assert manifest[sid]["tenant"] == "tenant-a" and manifest[sid]["role"] == "researcher", "SOURCE_ACL"
            text = raw.decode("utf-8")
            lines = [(n, line) for n, line in enumerate(text.splitlines(), 1) if expected_needles[sid] in line]
            assert len(lines) == 1 and lines[0] == (e["line"], e["quote"]), "SOURCE_AMBIGUITY_OR_MISMATCH"
            piece = raw[e["start_byte"]:e["end_byte"]]
            assert piece.decode("utf-8") == e["quote"] and sha(piece) == e["quote_sha256"], "SOURCE_BYTE_RANGE"
            assert f"## {sid}" in md and e["quote"] in md, "MARKDOWN_MISMATCH"
        assert ids == set(c["sources"]), "SOURCE_INCOMPLETE"
        for finding in report["findings"]:
            assert finding["source_id"] in ids
            assert any(e["source_id"] == finding["source_id"] and
                       e["quote_sha256"] == finding["quote_sha256"] for e in report["evidence"]), "FINDING_NOT_GROUNDED"
        return {"verdict": "PASS", "run_id": run_id, "source_count": len(ids),
                "journal_events": len(events), "attempts": row[2], "effect_status": row[3],
                "artifact_sha256": sha(art.read_bytes()), "sources": sorted(ids)}
    finally:
        con.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--json-out")
    args = p.parse_args()
    try:
        result = verify(args.db, args.run_id)
    except Exception as exc:
        result = {"verdict": "FAIL", "run_id": args.run_id, "reason": str(exc)}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(result["verdict"] != "PASS")

if __name__ == "__main__":
    sys.exit(main())
