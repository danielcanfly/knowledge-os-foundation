#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

C02_CLASSES = {
    "EXTERNAL_SEMANTIC_ENTAILMENT_PROVIDER_GATE",
    "M27_NATIVE_COMPOSER_QUALIFICATION_GAP",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the exact C01 residual 51 cases")
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    with args.classification.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    node_ids = [row["node_id"] for row in rows if row["root_cause_class"] not in C02_CLASSES]
    if len(rows) != 53 or len(node_ids) != 51 or len(set(node_ids)) != 51:
        raise SystemExit("classification must contain 53 unique cases: C01=51, C02=2")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *node_ids,
        f"--junitxml={args.junit}",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(repo_root / part) for part in ("src", "tests", ""))
    start = _utc_now()
    with args.log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        pytest_pid = process.pid
        return_code = process.wait()
    end = _utc_now()
    args.meta.write_text(
        "\n".join(
            [
                f"start_utc={start}",
                f"end_utc={end}",
                f"pytest_pid={pytest_pid}",
                f"python={sys.executable}",
                f"repo_root={repo_root}",
                f"home={env.get('HOME', '')}",
                f"tmpdir={env.get('TMPDIR', '')}",
                f"classification={args.classification.resolve()}",
                "case_count=51",
                "c02_excluded=2",
                f"exit_code={return_code}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(args.log.read_text(encoding="utf-8"), end="")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
