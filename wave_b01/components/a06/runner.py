#!/usr/bin/env python3
"""A06 isolated nonprod research + reversible observation workload; no coding patch capability."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "data" / "sources"
MANIFEST = ROOT / "data" / "source_manifest.json"
ALLOWED = ("CHARTER", "DELIVERY", "I37_ACCEPTANCE")
NEEDLES = {
    "CHARTER": "Task/Outcome 優先於 Chat 回答",
    "DELIVERY": "I37 is already **DONE in isolated NONPROD scope**.",
    "I37_ACCEPTANCE": "**AR08 same-TaskContract persisted coding outcome**",
}
STAGES = {"ADMITTED", "PLANNED", "GATHERED_1", "GATHERED_2",
          "GATHERED_3", "RESEARCH_ACCEPTED", "ACTION_PREPARED", "ACTION_DONE", "VERIFIED"}
TERMINAL = {"VERIFIED", "CANCELED", "ABSTAINED"}
STATE = ROOT / "state"

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp." + str(os.getpid()))
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def encode(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")

def connection(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db, isolation_level=None, timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, contract TEXT NOT NULL,
          stage TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL, at TEXT NOT NULL, event TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence(run_id TEXT NOT NULL, source_id TEXT NOT NULL,
          payload TEXT NOT NULL, PRIMARY KEY(run_id,source_id));
        CREATE TABLE IF NOT EXISTS actions(run_id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL,
          before_state TEXT NOT NULL, after_state TEXT NOT NULL, attempts INTEGER NOT NULL,
          status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revoked(source_id TEXT PRIMARY KEY, at TEXT NOT NULL);
    """)
    return con

def emit(con, run, event, obj=None):
    con.execute("INSERT INTO journal(run_id,at,event,body) VALUES(?,?,?,?)",
                (run, now(), event, json.dumps(obj or {}, ensure_ascii=False, sort_keys=True)))

def stage(con, run, name, event, info=None):
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("UPDATE runs SET stage=? WHERE run_id=?", (name, run))
        emit(con, run, event, info)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise

def get_run(con, run):
    row = con.execute("SELECT contract,stage FROM runs WHERE run_id=?", (run,)).fetchone()
    if not row:
        raise ValueError("UNKNOWN_RUN")
    return json.loads(row[0]), row[1]

def contract_valid(c):
    if set(c) != {"run_id", "tenant", "actor", "goal", "deadline", "budget", "sources",
                  "rights", "outcome", "version"}:
        raise ValueError("CONTRACT_FIELDS")
    if c["version"] != "a06-v1" or c["tenant"] != "tenant-a" or c["actor"] != "owner-researcher":
        raise PermissionError("AUTHORITY_OR_TENANT_DENIED")
    if not isinstance(c["run_id"], str) or not c["run_id"].startswith("a06-") or "/" in c["run_id"]:
        raise ValueError("INVALID_RUN_ID")
    if c["sources"] != list(ALLOWED) or c["rights"] != ["read-firstparty", "write-own-observation"]:
        raise PermissionError("SCOPES_DENIED")
    if c["budget"] != {"max_source_reads": 3, "max_action_attempts": 1}:
        raise ValueError("BUDGET_DENIED")
    if c["outcome"] != "verified-research-and-reversible-observation" or not c["goal"]:
        raise ValueError("OUTCOME_INVALID")
    if datetime.fromisoformat(c["deadline"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise ValueError("DEADLINE_EXPIRED")

def admission(con, c):
    contract_valid(c)
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("INSERT INTO runs(run_id,contract,stage,created) VALUES(?,?,?,?)",
                    (c["run_id"], json.dumps(c, ensure_ascii=False, sort_keys=True),
                     "ADMITTED", now()))
        emit(con, c["run_id"], "ADMITTED", {"contract_hash": digest(encode(c))})
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise

def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))

def source_proof(source_id):
    m = manifest()[source_id]
    if m["source_id"] != source_id or m["tenant"] != "tenant-a" or m["role"] != "researcher":
        raise PermissionError("SOURCE_ACL_DENIED")
    path = SOURCE_ROOT / (source_id + ".md")
    raw = path.read_bytes()
    if digest(raw) != m["sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    txt = raw.decode("utf-8")
    needle = NEEDLES[source_id]
    matching = [(i, line) for i, line in enumerate(txt.splitlines(), 1) if needle in line]
    if len(matching) != 1:
        raise ValueError("SOURCE_AMBIGUOUS_OR_MISSING:" + source_id)
    line_no, line = matching[0]
    offset = raw.find(line.encode("utf-8"))
    if offset < 0:
        raise ValueError("SOURCE_BYTE_RANGE_INVALID")
    return {"source_id": source_id, "sha256": m["sha256"], "line": line_no,
            "start_byte": offset, "end_byte": offset + len(line.encode("utf-8")),
            "quote": line, "quote_sha256": digest(line.encode("utf-8"))}

def ensure_sources(con, run):
    if con.execute("SELECT count(*) FROM revoked WHERE source_id IN (?,?,?)",
                   ALLOWED).fetchone()[0]:
        raise PermissionError("REVOKED_SOURCE")
    c, _ = get_run(con, run)
    contract_valid(c)

def artifact_path(run):
    return STATE / run / "research.json"

def observation_path(run):
    return STATE / run / "observation.json"

def action_expected(run):
    return {"observation": "reviewed", "revision": 1, "run_id": run}

def read_observation(run):
    p = observation_path(run)
    return json.loads(p.read_text("utf-8")) if p.exists() else {"observation": "idle", "revision": 0}

def build_research(con, run):
    rows = con.execute("SELECT source_id,payload FROM evidence WHERE run_id=? ORDER BY source_id",
                       (run,)).fetchall()
    items = [json.loads(p) for sid, p in rows]
    if {e["source_id"] for e in items} != set(ALLOWED):
        raise ValueError("INSUFFICIENT_SOURCE_COVERAGE")
    r = {"run_id": run, "tenant": "tenant-a", "question": get_run(con, run)[0]["goal"],
         "method": "owner-firstparty exact-byte source extraction; no LLM or live provider",
         "source_ids": list(ALLOWED), "evidence": items,
         "findings": [
             {"label": "Charter task-native mandate", "source_id": "CHARTER", "quote_sha256": next(x["quote_sha256"] for x in items if x["source_id"] == "CHARTER")},
             {"label": "I37 scoped acceptance boundary", "source_id": "DELIVERY", "quote_sha256": next(x["quote_sha256"] for x in items if x["source_id"] == "DELIVERY")},
             {"label": "AR08 unresolved coding gate", "source_id": "I37_ACCEPTANCE", "quote_sha256": next(x["quote_sha256"] for x in items if x["source_id"] == "I37_ACCEPTANCE")},
         ],
         "limitations": ["Local owner-firstparty documents, not third-party independently signed",
                         "Exact source provenance verified, not an independently judged LLM semantic answer",
                         "Coding-source edit not attempted; historical refusal remains binding"]}
    atomic(artifact_path(run), encode(r))
    md = ["# A06 persisted M27 research", "", "RunID: " + run, "",
          "Method: Owner-firstparty exact bytes, deterministic extraction. No paid Provider.", ""]
    for v in items:
        md += ["## " + v["source_id"], "Source sha256: `" + v["sha256"] + "`",
               "Line " + str(v["line"]) + ": " + v["quote"], ""]
    md += ["## Limits", "AR08 persisted coding patch is not implemented or authorized here.",
           "External or formal quality gates remain open.", ""]
    atomic(artifact_path(run).with_suffix(".md"), ("\n".join(md)).encode("utf-8"))

def verify_research(con, run):
    r = json.loads(artifact_path(run).read_text("utf-8"))
    if r["run_id"] != run or r["tenant"] != "tenant-a" or r["source_ids"] != list(ALLOWED):
        raise ValueError("ARTIFACT_IDENTITY")
    if {i["source_id"] for i in r["evidence"]} != set(ALLOWED):
        raise ValueError("ARTIFACT_COVERAGE")
    for i in r["evidence"]:
        if source_proof(i["source_id"]) != i:
            raise ValueError("ARTIFACT_PROVENANCE")
    ensure_sources(con, run)

def step(con, run, inject_unknown=False):
    c, current = get_run(con, run)
    if current in TERMINAL:
        return current
    try:
        ensure_sources(con, run)
        if current == "ADMITTED":
            stage(con, run, "PLANNED", "PLAN_PERSISTED",
                  {"steps": ["source_1", "source_2", "source_3", "persist_artifact",
                             "reversible_observation", "independent_verify"]})
        elif current in ("PLANNED", "GATHERED_1", "GATHERED_2"):
            index = {"PLANNED": 0, "GATHERED_1": 1, "GATHERED_2": 2}[current]
            sid = ALLOWED[index]
            proof = source_proof(sid)
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute("INSERT INTO evidence VALUES(?,?,?)", (run, sid, json.dumps(proof, ensure_ascii=False)))
                con.execute("UPDATE runs SET stage=? WHERE run_id=?", ("GATHERED_" + str(index + 1), run))
                emit(con, run, "SOURCE_READ", {"source_id": sid, "sha256": proof["sha256"]})
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        elif current == "GATHERED_3":
            build_research(con, run)
            verify_research(con, run)
            stage(con, run, "RESEARCH_ACCEPTED", "ARTIFACT_VERIFIED",
                  {"artifact_sha256": digest(artifact_path(run).read_bytes())})
        elif current == "RESEARCH_ACCEPTED":
            verify_research(con, run)
            before = read_observation(run)
            if before != {"observation": "idle", "revision": 0}:
                raise ValueError("ACTION_PRECONDITION")
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute("INSERT INTO actions VALUES(?,?,?,?,?,?)",
                            (run, "A06-OBSERVE-" + run, json.dumps(before, sort_keys=True),
                             json.dumps(action_expected(run), sort_keys=True), 0, "PREPARED"))
                con.execute("UPDATE runs SET stage='ACTION_PREPARED' WHERE run_id=?", (run,))
                emit(con, run, "ACTION_INTENT_PERSISTED", {"key": "A06-OBSERVE-" + run, "before": before})
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        elif current == "ACTION_PREPARED":
            row = con.execute("SELECT attempts,before_state,after_state FROM actions WHERE run_id=?",
                              (run,)).fetchone()
            attempts, before, after = row
            expected = json.loads(after)
            if attempts > 0:
                observed = read_observation(run)
                if observed != expected:
                    emit(con, run, "UNKNOWN_EFFECT_RECONCILE_HOLD", {"observed": observed})
                    raise RuntimeError("UNKNOWN_EFFECT_NOT_REPLAYED")
                con.execute("BEGIN IMMEDIATE")
                try:
                    con.execute("UPDATE actions SET status='RECONCILED' WHERE run_id=?", (run,))
                    con.execute("UPDATE runs SET stage='ACTION_DONE' WHERE run_id=?", (run,))
                    emit(con, run, "RECONCILED_BY_OBSERVATION", {"attempts": attempts, "observed": observed})
                    con.execute("COMMIT")
                except BaseException:
                    con.execute("ROLLBACK")
                    raise
            else:
                if read_observation(run) != json.loads(before):
                    raise RuntimeError("PRECONDITION_DRIFT_NO_ACTION")
                con.execute("BEGIN IMMEDIATE")
                try:
                    con.execute("UPDATE actions SET attempts=1,status='UNKNOWN' WHERE run_id=?", (run,))
                    emit(con, run, "EFFECT_ATTEMPT_PERSISTED_BEFORE_IO", {"attempts": 1})
                    con.execute("COMMIT")
                except BaseException:
                    con.execute("ROLLBACK")
                    raise
                atomic(observation_path(run), encode(expected))
                if inject_unknown:
                    os._exit(73)
                con.execute("BEGIN IMMEDIATE")
                try:
                    con.execute("UPDATE actions SET status='APPLIED' WHERE run_id=?", (run,))
                    con.execute("UPDATE runs SET stage='ACTION_DONE' WHERE run_id=?", (run,))
                    emit(con, run, "SIDE_EFFECT_OBSERVED", {"after": read_observation(run), "attempts": 1})
                    con.execute("COMMIT")
                except BaseException:
                    con.execute("ROLLBACK")
                    raise
        elif current == "ACTION_DONE":
            verify_research(con, run)
            row = con.execute("SELECT attempts,status,after_state FROM actions WHERE run_id=?", (run,)).fetchone()
            if not row or row[0] != 1 or row[1] not in ("APPLIED", "RECONCILED") or read_observation(run) != json.loads(row[2]):
                raise ValueError("OUTCOME_NOT_OBSERVED")
            stage(con, run, "VERIFIED", "INDEPENDENTLY_VERIFIABLE_OUTCOME",
                  {"research_sha256": digest(artifact_path(run).read_bytes()), "action_receipt": row[1]})
        else:
            raise ValueError("ILLEGAL_STAGE:" + current)
    except (ValueError, PermissionError) as ex:
        # Revocation / source failure after an effect cannot leave an ungoverned changed state.
        # UNKNOWN effects must be observed and reconciled before any cancellation/abstention.
        cleanup_observed_effect(con, run)
        stage(con, run, "ABSTAINED", "SAFE_ABSTAIN", {"reason": str(ex)})
    return get_run(con, run)[1]

def run_loop(con, run, hold_at=None, inject_unknown=False):
    while True:
        _, before = get_run(con, run)
        if before in TERMINAL:
            return before
        after = step(con, run, inject_unknown=inject_unknown)
        print(json.dumps({"run_id": run, "stage": after}, sort_keys=True), flush=True)
        if hold_at == after:
            print("HOLD_POINT " + after, flush=True)
            while True:
                time.sleep(60)
        if after == before:
            return after

def rollback(con, run):
    row = con.execute("SELECT before_state,after_state,status FROM actions WHERE run_id=?",
                      (run,)).fetchone()
    if not row:
        raise ValueError("NO_ACTION_TO_ROLLBACK")
    before, after, status = map(str, row)
    if status not in ("APPLIED", "RECONCILED"):
        raise ValueError("ACTION_NOT_COMMITTED")
    if read_observation(run) != json.loads(after):
        raise RuntimeError("ROLLBACK_PRECONDITION_DRIFT")
    atomic(observation_path(run), encode(json.loads(before)))
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("UPDATE actions SET status='ROLLED_BACK' WHERE run_id=?", (run,))
        emit(con, run, "REVERSIBLE_ACTION_ROLLED_BACK", {"before": json.loads(before)})
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise

def cleanup_observed_effect(con, run):
    """Reconcile and compensate own reversible effect, or hold if its outcome is unknown."""
    row = con.execute("SELECT attempts,status,before_state,after_state FROM actions WHERE run_id=?",
                      (run,)).fetchone()
    if row is None:
        return
    attempts, status, before, after = row
    if status == "ROLLED_BACK":
        return
    if status == "PREPARED" and attempts == 0:
        return
    observed = read_observation(run)
    if status == "UNKNOWN":
        # Absence is not proof a timed-out effect never happened: require human reconciliation.
        if attempts != 1 or observed != json.loads(after):
            emit(con, run, "UNKNOWN_CANCELLATION_HOLD", {"observed": observed, "attempts": attempts})
            raise RuntimeError("UNKNOWN_EFFECT_UNRESOLVED_NO_CANCEL")
        con.execute("BEGIN IMMEDIATE")
        try:
            con.execute("UPDATE actions SET status='RECONCILED' WHERE run_id=?", (run,))
            emit(con, run, "UNKNOWN_RECONCILED_FOR_COMPENSATION", {"observed": observed, "attempts": 1})
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    elif status not in ("APPLIED", "RECONCILED"):
        raise RuntimeError("UNRECOGNIZED_ACTION_EFFECT_STATUS")
    rollback(con, run)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["admit", "run", "cancel", "revoke", "rollback", "status"])
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--run-id")
    p.add_argument("--contract", type=Path)
    p.add_argument("--source-id", choices=ALLOWED)
    p.add_argument("--hold-at", choices=sorted(STAGES))
    p.add_argument("--inject-unknown", action="store_true")
    a = p.parse_args()
    con = connection(a.db)
    try:
        if a.command == "admit":
            c = json.loads(a.contract.read_text("utf-8"))
            admission(con, c)
            print("ADMITTED " + c["run_id"])
        elif a.command == "run":
            print("RESULT " + run_loop(con, a.run_id, a.hold_at, a.inject_unknown))
        elif a.command == "status":
            c, s = get_run(con, a.run_id)
            ev = con.execute("SELECT seq,event,body FROM journal WHERE run_id=? ORDER BY seq", (a.run_id,)).fetchall()
            ledger = con.execute("SELECT attempts,status FROM actions WHERE run_id=?", (a.run_id,)).fetchone()
            print(json.dumps({"stage": s, "run_id": a.run_id, "journal": ev, "ledger": ledger}, ensure_ascii=False))
        elif a.command == "revoke":
            con.execute("INSERT OR REPLACE INTO revoked VALUES(?,?)", (a.source_id, now()))
            emit(con, a.run_id or "_policy", "SOURCE_REVOKED", {"source_id": a.source_id})
            print("REVOKED " + a.source_id)
        elif a.command == "rollback":
            rollback(con, a.run_id)
            print("ROLLED_BACK " + a.run_id)
        elif a.command == "cancel":
            c, s = get_run(con, a.run_id)
            if s in TERMINAL:
                raise ValueError("CANNOT_CANCEL_TERMINAL")
            cleanup_observed_effect(con, a.run_id)
            stage(con, a.run_id, "CANCELED", "CANCELLED_NO_FURTHER_EFFECT")
            print("CANCELED " + a.run_id)
    except Exception as ex:
        print(type(ex).__name__ + ": " + str(ex), file=sys.stderr)
        return 2
    finally:
        con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
