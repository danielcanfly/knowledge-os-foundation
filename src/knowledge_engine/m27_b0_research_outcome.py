"""G02: local owner-authorized *real-document* durable research outcome.

Separate Nonprod workload; no shared API, external model, action, or fixture output.
Source words are copied from live owner-controlled documents with SHA and line pins.
SQLite journal uses WAL/FULL, immutable events, and deterministic recovery.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from m27_task_contracts_v1 import task_contract

ANCHORS = {
    "charter": (
        "- **Research**：多步檢索/整理/中斷恢復",
        "6. checkpoint→kill→restart/resume",
    ),
    "audit": (
        "**Nearest lawful real outcome:** G02",
        "3. **Dispatch one G02 durable Research outcome**",
    ),
}
STAGES = ("CHARTER_EXTRACTED", "AUDIT_COMPARED", "OUTCOME_COMMITTED")
SCHEMA = "M27-B0-G02/1"


class ResearchDenied(ValueError):
    """Fail-closed authority, integrity, or recovery fence."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ResearchDenied(code)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def load_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "INVALID_INPUT_FILE")
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ResearchDenied("INVALID_JSON") from exc
    require(type(data) is dict, "INVALID_INPUT_OBJECT")
    return data


def source_lines(registry: dict, source_id: str, contract: dict) -> list[str]:
    require(set(registry) == {"root", "sources", "schema"}, "UNKNOWN_REGISTRY_FIELD")
    require(registry["schema"] == SCHEMA, "REGISTRY_VERSION")
    require(type(registry["sources"]) is dict and
            set(registry["sources"]) == set(ANCHORS), "SOURCE_SET_MISMATCH")
    src = registry["sources"][source_id]
    require(type(src) is dict and set(src) == {
        "path", "sha256", "rights_basis", "license", "tenant_id",
        "principals", "purpose", "valid_until", "revoked",
    }, "INVALID_SOURCE_RECORD")
    require(src["rights_basis"] == "OWNER_AUTHORIZED_FIRST_PARTY_NONPROD" and
            src["license"] == "internal-owner-controlled-not-public-license" and
            src["purpose"] == "m27-research-read-only", "SOURCE_RIGHTS_UNPROVEN")
    require(src["tenant_id"] == contract["tenant_id"] and
            contract["actor"]["principal_id"] in src["principals"],
            "SOURCE_ACL_DENIED")
    require(src["revoked"] is False, "SOURCE_REVOKED")
    require(dt.datetime.fromisoformat(src["valid_until"].replace("Z", "+00:00")) > utcnow(),
            "SOURCE_RIGHTS_EXPIRED")
    root = Path(registry["root"])
    path = Path(src["path"])
    require(root.is_absolute() and path.is_absolute() and
            ".." not in path.parts and not path.is_symlink(), "UNSAFE_SOURCE_PATH")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        require(resolved_path.is_relative_to(resolved_root), "SOURCE_PATH_OUT_OF_SCOPE")
        require(path.is_file(), "SOURCE_NOT_REGULAR_FILE")
        with path.open("rb") as fp:
            content = fp.read(250_001)
            require(len(content) <= 250_000, "SOURCE_TOO_LARGE")
        require(sha(content) == src["sha256"], "SOURCE_DIGEST_DRIFT")
        return content.decode("utf-8").splitlines()
    except (OSError, UnicodeError, RuntimeError) as exc:
        raise ResearchDenied("SOURCE_UNREADABLE") from exc


def extract(lines: list[str], source_id: str, registry: dict) -> list[dict]:
    hits = []
    for anchor in ANCHORS[source_id]:
        matched = [(i, line) for i, line in enumerate(lines, start=1) if anchor in line]
        require(len(matched) == 1, "MISSING_OR_AMBIGUOUS_SOURCE_EVIDENCE")
        line_no, quote = matched[0]
        hits.append({"source_id": source_id, "line": line_no,
                     "quote": quote, "quote_sha256": sha(quote.encode("utf-8")),
                     "source_sha256": registry["sources"][source_id]["sha256"],
                     "locator": registry["sources"][source_id]["path"]})
    return hits


def render(stages: list[dict], contract: dict) -> tuple[bytes, bytes]:
    first = stages[0]["citations"]
    second = stages[1]["citations"]
    citations = first + second
    lines = [
        "# M27 G02: Durable Research Outcome, evidence-based gap decision",
        "",
        f"Task: {contract['task_id']} (v{contract['task_version']}); "
        f"tenant: {contract['tenant_id']}; principal: {contract['actor']['principal_id']}",
        "",
        "## Question and method",
        "What must M27's first real Research slice deliver, and what is independently "
        "recommended next? This is a deterministic two-source document comparison, "
        "not an LLM-generated claim or semantic provider certification.",
        "",
        "## Step 1: architecture requirement (Charter)",
    ]
    for cite in first:
        lines.extend([f"- [{cite['source_id']}:{cite['line']}] {cite['quote']}", ""])
    lines.extend([
        "## Step 2: independent audit and decision",
    ])
    for cite in second:
        lines.extend([f"- [{cite['source_id']}:{cite['line']}] {cite['quote']}", ""])
    lines.extend([
        "## Synthesis and bounded recommendation",
        "The Charter demands a multi-step Research artifact with provenance and "
        "checkpoint/kill/resume. The independent audit prioritizes G02 as the nearest "
        "permissible real outcome and calls for a source-cited persisted artifact plus "
        "independent byte/SHA and revocation evidence. The documents therefore agree "
        "on the immediate Nonprod Research slice, not on any claim of formal Product "
        "admission, independent semantic verification, or external model use.",
        "",
        "Recommendation: verify this exact report with source-line receipts, test "
        "process kill/restart at a mid-task checkpoint and after finalization, "
        "and keep it in an isolated Nonprod artifact namespace until H02 review.",
        "",
        "## Source provenance",
    ])
    for c in citations:
        lines.append(f"- [{c['source_id']}:{c['line']}] "
                     f"source_sha256={c['source_sha256']} "
                     f"quote_sha256={c['quote_sha256']} locator={c['locator']}")
    lines.extend(["", "Scope: local owned documents only; no paid model/tool calls; "
                  "no external side effects."])
    md = ("\n".join(lines) + "\n").encode("utf-8")
    result = {"schema": SCHEMA, "task_id": contract["task_id"],
              "tenant_id": contract["tenant_id"],
              "principal_id": contract["actor"]["principal_id"],
              "method": "real-owner-documents-deterministic-comparative-analysis",
              "citations": citations,
              "source_decision": "CHARTER_AUDIT_CONVERGE_ON_G02_NONPROD",
              "markdown_sha256": sha(md)}
    return md, canonical(result) + b"\n"


def connection(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_path), isolation_level=None, timeout=8)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA busy_timeout=8000")
    return db


def initialize(db: sqlite3.Connection) -> None:
    db.executescript("""
      CREATE TABLE IF NOT EXISTS g02_runs(
        run_id TEXT PRIMARY KEY, contract_sha TEXT NOT NULL,
        tenant TEXT NOT NULL, principal TEXT NOT NULL, task TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS g02_events(
        run_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
        payload BLOB NOT NULL, prev TEXT NOT NULL, digest TEXT NOT NULL,
        PRIMARY KEY(run_id,seq));
      CREATE TRIGGER IF NOT EXISTS g02_no_update BEFORE UPDATE ON g02_events
        BEGIN SELECT RAISE(ABORT,'immutable event'); END;
      CREATE TRIGGER IF NOT EXISTS g02_no_delete BEFORE DELETE ON g02_events
        BEGIN SELECT RAISE(ABORT,'immutable event'); END;
    """)


def read_events(db: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = db.execute("SELECT * FROM g02_events WHERE run_id=? ORDER BY seq",
                      (run_id,)).fetchall()
    prior = sha(canonical([SCHEMA, run_id]))
    events = []
    for idx, row in enumerate(rows, 1):
        event = json.loads(row["payload"])
        expected = sha(prior.encode() + b"|" + canonical(
            {"seq": idx, "kind": row["kind"], "payload": event}))
        require(row["seq"] == idx and row["prev"] == prior and
                row["digest"] == expected, "JOURNAL_CHAIN_CORRUPT")
        prior = expected
        events.append({"seq": idx, "kind": row["kind"],
                       "payload": event, "digest": expected})
    return events


def append(db: sqlite3.Connection, run_id: str, kind: str, payload: dict) -> None:
    prior_events = read_events(db, run_id)
    seq = len(prior_events) + 1
    prior = prior_events[-1]["digest"] if prior_events else sha(canonical([SCHEMA, run_id]))
    digest = sha(prior.encode() + b"|" + canonical(
        {"seq": seq, "kind": kind, "payload": payload}))
    db.execute("INSERT INTO g02_events VALUES(?,?,?,?,?,?)",
               (run_id, seq, kind, canonical(payload), prior, digest))


def fsync_write(path: Path, data: bytes) -> None:
    require(path.parent.is_dir() and not path.is_symlink(), "UNSAFE_OUTCOME_PATH")
    tmp = path.with_name(path.name + ".g02-staging")
    require(not tmp.is_symlink(), "UNSAFE_STAGING_PATH")
    with tmp.open("wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def pause_at(name: str, requested: str) -> None:
    if requested == name:
        print("G02_PAUSE_BOUNDARY=" + name, flush=True)
        while True:
            time.sleep(1)


def execute(db_path: Path, contract_path: Path, registry_path: Path,
            outcome_dir: Path, run_id: str, *, pause: str = "") -> dict:
    contract = load_json(contract_path)
    task_contract(contract)
    require(contract["workload_kind"] == "research" and
            contract["authority"]["max_side_effect"] == "read" and
            contract["authority"]["allowed_capability_ids"] == ["local_owner_document_read"],
            "RESEARCH_AUTHORITY_DENIED")
    require(contract["budget"]["max_tool_calls"] >= 2 and
            contract["budget"]["max_attempts"] >= 1 and
            contract["budget"]["max_cost_microunits"] == 0 and
            contract["budget"]["max_tokens"] == 0, "QUOTA_OR_PROVIDER_DENIED")
    require({x["scope_id"] for x in contract["context_scopes"]} ==
            set(ANCHORS) and
            all(x["access"] == "read" for x in contract["context_scopes"]),
            "RESEARCH_SCOPE_DENIED")
    require(len(contract["output_specs"]) == 1 and
            contract["output_specs"][0]["kind"] == "report" and
            contract["output_specs"][0]["expected_uri_scope"] == "local-nonprod",
            "RESEARCH_OUTCOME_SCOPE")
    require(run_id and all(c.isalnum() or c in "-_" for c in run_id),
            "INVALID_RUN_ID")
    require(db_path.parent.is_dir() and not db_path.is_symlink() and
            outcome_dir.is_dir() and not outcome_dir.is_symlink(), "ISOLATED_STORAGE_REQUIRED")
    registry = load_json(registry_path)
    # Live read for ACL, revocation, expiry and source SHA even on completed resumes.
    current = {name: extract(source_lines(registry, name, contract), name, registry)
               for name in ANCHORS}
    contract_digest = sha(canonical(contract))
    with connection(db_path) as db:
        initialize(db)
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT * FROM g02_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                db.execute("INSERT INTO g02_runs VALUES(?,?,?,?,?)",
                           (run_id, contract_digest, contract["tenant_id"],
                            contract["actor"]["principal_id"], contract["task_id"]))
                append(db, run_id, "PLANNED", {
                    "contract_sha256": contract_digest,
                    "plan": ["CHARTER_EXTRACTED", "AUDIT_COMPARED", "OUTCOME_COMMITTED"],
                    "source_sha256": {name: registry["sources"][name]["sha256"]
                                      for name in ANCHORS}})
            else:
                require(row["contract_sha"] == contract_digest and
                        row["tenant"] == contract["tenant_id"] and
                        row["principal"] == contract["actor"]["principal_id"] and
                        row["task"] == contract["task_id"], "TASK_IDENTITY_MISMATCH")
            events = read_events(db, run_id)
            require(events[0]["kind"] == "PLANNED" and
                    events[0]["payload"]["contract_sha256"] == contract_digest and
                    events[0]["payload"]["source_sha256"] ==
                    {name: registry["sources"][name]["sha256"]
                     for name in ANCHORS}, "SOURCE_PINS_CHANGED")
            db.commit()
        except BaseException:
            db.rollback()
            raise
        if not any(x["kind"] == "CHARTER_EXTRACTED" for x in events):
            db.execute("BEGIN IMMEDIATE")
            try:
                append(db, run_id, "CHARTER_EXTRACTED",
                       {"citations": current["charter"],
                        "decision": "CHARTER_RESEARCH_AND_RESTART_REQUIRED",
                        "checkpoint_id": run_id + "/step-1"})
                db.commit()
            except BaseException:
                db.rollback()
                raise
            pause_at("AFTER_STEP_1", pause)
        events = read_events(db, run_id)
        first = next(x for x in events if x["kind"] == "CHARTER_EXTRACTED")
        require(first["payload"]["citations"] == current["charter"],
                "CHECKPOINT_SOURCE_DRIFT")
        if not any(x["kind"] == "AUDIT_COMPARED" for x in events):
            db.execute("BEGIN IMMEDIATE")
            try:
                append(db, run_id, "AUDIT_COMPARED",
                       {"citations": current["audit"],
                        "decision": "CHARTER_AUDIT_CONVERGE_ON_G02_NONPROD",
                        "depends_on": first["digest"],
                        "checkpoint_id": run_id + "/step-2"})
                db.commit()
            except BaseException:
                db.rollback()
                raise
        events = read_events(db, run_id)
        second = next(x for x in events if x["kind"] == "AUDIT_COMPARED")
        require(second["payload"]["citations"] == current["audit"] and
                second["payload"]["depends_on"] == first["digest"],
                "DEPENDENT_EVIDENCE_CHANGED")
        md, result_json = render([first["payload"], second["payload"]], contract)
        md_path = outcome_dir / (run_id + ".md")
        json_path = outcome_dir / (run_id + ".json")
        completed = [x for x in events if x["kind"] == "OUTCOME_COMMITTED"]
        require(len(completed) <= 1, "DUPLICATED_TERMINAL")
        if completed:
            receipt = completed[0]["payload"]
            require(md_path.is_file() and json_path.is_file() and
                    not md_path.is_symlink() and not json_path.is_symlink(),
                    "OUTCOME_MISSING_OR_PARTIAL")
            require(md_path.read_bytes() == md and json_path.read_bytes() == result_json and
                    receipt["markdown_sha256"] == sha(md) and
                    receipt["json_sha256"] == sha(result_json),
                    "OUTCOME_BYTES_CHANGED")
        else:
            # Recovery if kill occurred after atomic file write but before journal commit.
            fsync_write(md_path, md)
            fsync_write(json_path, result_json)
            require(md_path.read_bytes() == md and json_path.read_bytes() == result_json,
                    "OUTCOME_READBACK_FAILED")
            db.execute("BEGIN IMMEDIATE")
            try:
                append(db, run_id, "OUTCOME_COMMITTED",
                       {"markdown_sha256": sha(md), "json_sha256": sha(result_json),
                        "markdown_bytes": len(md), "json_bytes": len(result_json),
                        "outcome_id": contract["output_specs"][0]["outcome_id"],
                        "verified_citations": len(first["payload"]["citations"]) +
                                              len(second["payload"]["citations"]),
                        "depends_on": second["digest"]})
                db.commit()
            except BaseException:
                db.rollback()
                raise
            pause_at("AFTER_FINALIZATION", pause)
        final_events = read_events(db, run_id)
        require([x["kind"] for x in final_events] ==
                ["PLANNED", *STAGES], "UNEXPECTED_JOURNAL_STATE")
        return {"run_id": run_id, "task_id": contract["task_id"],
                "tenant_id": contract["tenant_id"],
                "principal": contract["actor"]["principal_id"],
                "markdown": str(md_path), "markdown_sha256": sha(md),
                "json": str(json_path), "json_sha256": sha(result_json),
                "events": len(final_events),
                "journal_head": final_events[-1]["digest"],
                "result": "LOCAL_OWNER_SOURCE_DURABLE_RESEARCH_SUCCEEDED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pause-at", default="", choices=("", "AFTER_STEP_1",
                                                            "AFTER_FINALIZATION"))
    args = parser.parse_args()
    print(json.dumps(execute(args.db, args.contract, args.sources, args.out,
                             args.run_id, pause=args.pause_at),
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
