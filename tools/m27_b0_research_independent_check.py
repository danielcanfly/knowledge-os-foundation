"""Standalone G02 reader/verifier: deliberately does NOT import the executor."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3


def fail_if(condition: bool, error: str) -> None:
    if condition:
        raise AssertionError(error)


def canon(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(db_file: Path, registry_file: Path, contract_file: Path,
           outcome_dir: Path, run_id: str) -> dict:
    sources = json.loads(registry_file.read_bytes())
    contract = json.loads(contract_file.read_bytes())
    fail_if(sources["schema"] != "M27-B0-G02/1", "wrong source schema")
    fail_if(set(sources["sources"]) != {"charter", "audit"}, "invalid sources")
    with sqlite3.connect(f"file:{db_file}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        run = db.execute("SELECT * FROM g02_runs WHERE run_id=?", (run_id,)).fetchone()
        fail_if(run is None, "no durable run")
        fail_if(run["tenant"] != contract["tenant_id"] or
                run["principal"] != contract["actor"]["principal_id"] or
                run["task"] != contract["task_id"] or
                run["contract_sha"] != digest(canon(contract)), "identity/contract drift")
        rows = db.execute("SELECT * FROM g02_events WHERE run_id=? ORDER BY seq",
                          (run_id,)).fetchall()
    fail_if(len(rows) != 4 or [r["kind"] for r in rows] !=
            ["PLANNED", "CHARTER_EXTRACTED", "AUDIT_COMPARED", "OUTCOME_COMMITTED"],
            "incomplete or duplicated steps")
    predecessor = digest(canon(["M27-B0-G02/1", run_id]))
    parsed = []
    for index, row in enumerate(rows, 1):
        value = json.loads(row["payload"])
        actual = digest(predecessor.encode() + b"|" + canon(
            {"seq": index, "kind": row["kind"], "payload": value}))
        fail_if(row["seq"] != index or row["prev"] != predecessor or
                row["digest"] != actual, "tampered journal")
        parsed.append(value)
        predecessor = actual
    fail_if(parsed[2]["depends_on"] != rows[1]["digest"] or
            parsed[3]["depends_on"] != rows[2]["digest"], "broken dependency")
    md_path = outcome_dir / (run_id + ".md")
    json_path = outcome_dir / (run_id + ".json")
    fail_if(md_path.is_symlink() or json_path.is_symlink() or
            not md_path.is_file() or not json_path.is_file(), "missing or unsafe artifact")
    md = md_path.read_bytes()
    output = json.loads(json_path.read_bytes())
    fail_if(digest(md) != parsed[3]["markdown_sha256"] or
            digest(json_path.read_bytes()) != parsed[3]["json_sha256"] or
            parsed[3]["markdown_bytes"] != len(md) or
            parsed[3]["json_bytes"] != len(json_path.read_bytes()) or
            output["markdown_sha256"] != digest(md), "artifact hash/size mismatch")
    fail_if(output["tenant_id"] != run["tenant"] or
            output["principal_id"] != run["principal"] or
            output["task_id"] != run["task"] or
            output["source_decision"] != "CHARTER_AUDIT_CONVERGE_ON_G02_NONPROD",
            "artifact scope/decision mismatch")
    citations = parsed[1]["citations"] + parsed[2]["citations"]
    fail_if(len(citations) != 4 or citations != output["citations"], "citation drift")
    fail_if(parsed[3]["verified_citations"] != 4, "citation count mismatch")
    for cite in citations:
        src = sources["sources"][cite["source_id"]]
        origin = Path(src["path"])
        root = Path(sources["root"]).resolve(strict=True)
        fail_if(origin.is_symlink() or not origin.resolve(strict=True).is_relative_to(root),
                "source path traversal")
        fail_if(src["revoked"] is not False or
                src["tenant_id"] != run["tenant"] or
                run["principal"] not in src["principals"] or
                src["rights_basis"] != "OWNER_AUTHORIZED_FIRST_PARTY_NONPROD" or
                src["license"] != "internal-owner-controlled-not-public-license" or
                src["purpose"] != "m27-research-read-only" or
                datetime.datetime.fromisoformat(src["valid_until"].replace(
                    "Z", "+00:00")) <= datetime.datetime.now(datetime.timezone.utc),
                "source not authorized")
        data = origin.read_bytes()
        fail_if(digest(data) != src["sha256"] or
                cite["source_sha256"] != src["sha256"] or
                cite["locator"] != str(origin), "source content pin mismatch")
        lines = data.decode("utf-8").splitlines()
        line = cite["line"]
        fail_if(type(line) is not int or not 1 <= line <= len(lines) or
                lines[line - 1] != cite["quote"] or
                cite["quote_sha256"] != digest(cite["quote"].encode()) or
                f"[{cite['source_id']}:{line}] {cite['quote']}".encode() not in md,
                "citation line/quote not present in live source/report")
    return {
        "verdict": "INDEPENDENT_LOCAL_RESEARCH_BYTES_AND_CITATIONS_PASS",
        "run_id": run_id, "tenant_id": run["tenant"], "principal_id": run["principal"],
        "event_count": len(rows), "verified_live_citations": len(citations),
        "journal_head_sha256": predecessor, "markdown_sha256": digest(md),
        "json_sha256": digest(json_path.read_bytes()),
        "source_sha256": {k: v["sha256"] for k, v in sources["sources"].items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for key in ("db", "sources", "contract", "out", "run_id"):
        parser.add_argument("--" + key.replace("_", "-"), required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()
    result = verify(Path(args.db), Path(args.sources), Path(args.contract),
                    Path(args.out), args.run_id)
    rendered = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
