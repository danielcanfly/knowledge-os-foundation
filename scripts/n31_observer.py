"""Read only independent R29 OS observer for N31 receipts."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, type=Path)
    args = p.parse_args()
    with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as conn:
        posts = conn.execute(
            "SELECT run,COUNT(*) FROM posts GROUP BY run ORDER BY run"
        ).fetchall()
        effects = conn.execute(
            "SELECT run,COUNT(*) FROM effects GROUP BY run ORDER BY run"
        ).fetchall()
    print(json.dumps({
        "separate_sqlite_process": True,
        "posts_by_run": {run: count for run, count in posts},
        "effects_by_run": {run: count for run, count in effects},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
