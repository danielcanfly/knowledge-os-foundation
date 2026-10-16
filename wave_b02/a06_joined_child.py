#!/usr/bin/env python3
"""Process boundary for existing A06 action semantics with B02-owned scratch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from wave_b01.components.a06 import runner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("admit", "run", "rollback", "status"))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--inject-unknown", action="store_true")
    args = parser.parse_args()
    runner.STATE = args.state
    con = runner.connection(args.db)
    try:
        if args.command == "admit":
            contract = json.loads(args.contract.read_text(encoding="utf-8"))
            runner.admission(con, contract)
            print(json.dumps({"status": "ADMITTED", "run_id": args.run_id}))
        elif args.command == "run":
            result = runner.run_loop(con, args.run_id, inject_unknown=args.inject_unknown)
            print(json.dumps({"status": result, "run_id": args.run_id}))
        elif args.command == "rollback":
            runner.rollback(con, args.run_id)
            print(json.dumps({"status": "ROLLED_BACK", "run_id": args.run_id}))
        else:
            contract, stage = runner.get_run(con, args.run_id)
            action = con.execute(
                "SELECT attempts,status,before_state,after_state FROM actions WHERE run_id=?",
                (args.run_id,),
            ).fetchone()
            journal = con.execute(
                "SELECT seq,at,event,body FROM journal WHERE run_id=? ORDER BY seq",
                (args.run_id,),
            ).fetchall()
            print(json.dumps({"run_id": args.run_id, "stage": stage, "contract": contract,
                              "action": action, "journal": journal,
                              "observation": runner.read_observation(args.run_id)},
                             ensure_ascii=False))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
