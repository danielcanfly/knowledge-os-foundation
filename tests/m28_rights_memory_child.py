"""OS subprocess performs resumed reads using the SAME durable SQLite ledger."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from knowledge_engine.m27_m28_local_rights_memory_fence import (
    LifecycleDenied,
    LocalLease,
    LocalRightsMemoryFence,
)


def main() -> int:
    db_path, root, lease_path, ready_path, resume_path = map(Path, sys.argv[1:6])
    lease = LocalLease(**json.loads(lease_path.read_text()))
    fence = LocalRightsMemoryFence(db_path, root, fixture_only=True)
    ready_path.write_text(str(os.getpid()))
    deadline = time.monotonic() + 15
    while not resume_path.exists() and time.monotonic() < deadline:
        time.sleep(.025)
    if not resume_path.exists():
        print("CHILD_NO_RESUME_SIGNAL", flush=True)
        return 4
    attempts = {
        "source_read": lambda: fence.read(lease, "source1"),
        "queued_citation": lambda: fence.publish_queued(lease, "citation1"),
        "index_query": lambda: fence.query_cache(lease, "cache1"),
        "tool_send": lambda: fence.dispatch_local_tool(lease, "permit1"),
        "checkpoint_replay": lambda: fence.replay(lease, "checkpoint1"),
        "memory_read": lambda: fence.read(lease, "memory1", kind="memory"),
        "trace_read": lambda: fence.read(lease, "trace1", kind="trace"),
        "backup_restore": lambda: fence.restore_quarantined(lease, "backup1"),
    }
    for operation, attempt in attempts.items():
        try:
            attempt()
        except LifecycleDenied:
            continue
        print("CHILD_LEAK_" + operation, flush=True)
        return 3
    print("CHILD_DENY_ALL pid=" + str(os.getpid()) + " cases=8", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
